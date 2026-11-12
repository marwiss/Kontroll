# This file was generated with the assistance of an AI coding tool.
"""``POST /mcp``: the MCP endpoint (ADR 0028), Streamable HTTP with JSON answers only, mounted while
``OPENCDE_MCP_ENABLED`` is true.

A request passes, in order: the ``Origin`` check against DNS rebinding (403); the token, bound to the endpoint, with
``mcp`` (401 and 403 from :mod:`opencde.mcp.auth`); the body, at most 1 MB of JSON (413, 415); one JSON-RPC message
and no batch (400). A notification is accepted with 202. A request of revision 2026-07-28 then has its ``_meta``
checked (``-32602``), its headers against its body (``-32020``) and its revision (``-32022``), all 400, and is one of
``server/discover``, ``tools/list`` and ``tools/call`` (else 404 and ``-32601``). A request of a handshake revision
(2025-11-25, 2025-06-18, 2025-03-26) may be ``initialize``, ``ping``, ``tools/list`` or ``tools/call``, and is answered
without a session: no ``Mcp-Session-Id`` is ever made, and one sent is ignored. GET and DELETE answer 405. A tool
needs its scope (403 ``insufficient_scope`` for a step-up), and a token makes at most 120 tool calls a minute. The
request log gets the method and the tool's name, never the body; nothing a client sends is logged.
"""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from neo4j.exceptions import ServiceUnavailable

from opencde.auth.resources import MCP_PATH
from opencde.deps import GraphDep, SettingsDep, client_ip
from opencde.errors import CODE_FORBIDDEN, CODE_PAYLOAD_TOO_LARGE, ApiError, error_response
from opencde.graph.graph import Graph
from opencde.logging import get_logger
from opencde.mcp import protocol, registry
from opencde.mcp.auth import McpPrincipal, require_mcp_scope
from opencde.mcp.ifc_models import LIST_MODELS
from opencde.mcp.protocol import (
    CLIENT_CAPABILITIES_KEY,
    HANDSHAKE_VERSIONS,
    HEADER_MISMATCH,
    INTERNAL_ERROR,
    INVALID_PARAMS,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    MODERN_VERSION,
    PARSE_ERROR,
    PROTOCOL_VERSION_KEY,
    McpError,
)
from opencde.ratelimit import RATE_MCP_TOOL_CALLS, wait_seconds
from opencde.settings import Settings
from opencde.store.oauth2.tokens import Principal

TAG = "MCP (extension)"
MAX_BODY_BYTES = 1_048_576

#: The tools in the order ``tools/list`` gives them, which stays the same between releases but for what is added.
TOOLS: tuple[registry.Tool, ...] = (LIST_MODELS,)
_BY_NAME = {tool.name: tool for tool in TOOLS}
_MODERN_METHODS = ("server/discover", "tools/list", "tools/call")
_HANDSHAKE_METHODS = ("initialize", "ping", "tools/list", "tools/call")

log = get_logger(__name__)


def _own_origin(settings: Settings) -> str:
    parts = urlsplit(settings.public_url)
    return f"{parts.scheme}://{parts.netloc}".lower()


def check_origin(request: Request, settings: SettingsDep) -> None:
    """A browser's request comes from the server's own origin or one ``OPENCDE_CORS_ORIGINS`` names, never ``null``
    and not through ``*`` (the specification's guard against DNS rebinding); the usual MCP clients send none."""
    origin = request.headers.get("origin")
    if origin is None:
        return
    allowed = {_own_origin(settings), *(value.lower() for value in settings.cors_origins if value != "*")} - {"null"}
    if origin.lower() not in allowed:
        raise ApiError(403, "Requests from this origin may not reach the MCP endpoint", code=CODE_FORBIDDEN)


router = APIRouter(tags=[TAG])

_JSONRPC_BODY = {"type": "object", "description": "One JSON-RPC 2.0 request or notification; no batches."}


@router.post(
    MCP_PATH,
    summary="Call the MCP endpoint: server/discover, tools/list and tools/call (extension)",
    dependencies=[Depends(check_origin)],
    response_class=JSONResponse,
    openapi_extra={"requestBody": {"required": True, "content": {"application/json": {"schema": _JSONRPC_BODY}}}},
    responses={
        202: {"description": "A notification, accepted"},
        400: {"description": "A JSON-RPC error: a body or `_meta` that is not right, headers that do not match it"},
        404: {"description": "A JSON-RPC error: a method the endpoint does not have (`-32601`)"},
        413: {"description": "The body is larger than 1 MB"},
    },
)
async def mcp_endpoint(request: Request, caller: McpPrincipal, settings: SettingsDep, graph: GraphDep) -> Response:
    """One JSON-RPC message per request, answered with one JSON object (Streamable HTTP without SSE). Revision
    2026-07-28, and 2025-11-25 to 2025-03-26 without sessions. The answers are data from the projects."""
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type != "application/json":
        return error_response(415, "The body must be JSON (Content-Type: application/json)")
    raw = await _body(request)
    if raw is None:
        return error_response(413, f"Request body exceeds {MAX_BODY_BYTES} bytes", code=CODE_PAYLOAD_TOO_LARGE)
    try:
        message = json.loads(raw, parse_constant=_refuse_constant)
    except (ValueError, RecursionError):
        return _error(None, McpError(PARSE_ERROR, "Parse error: the body is not JSON"), modern=True)
    if isinstance(message, list):
        return _error(None, McpError(INVALID_REQUEST, "Batches are not accepted: one message per request"), True)
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0" or not isinstance(message.get("method"), str):
        failure = McpError(INVALID_REQUEST, "The body must be one JSON-RPC 2.0 request or notification")
        return _error(message.get("id") if isinstance(message, dict) else None, failure, True)
    version = request.headers.get(protocol.VERSION_HEADER)
    modern = version is not None and version not in HANDSHAKE_VERSIONS
    if "id" not in message:
        if modern and version != MODERN_VERSION:
            return _error(None, protocol.unsupported_version(version or ""), True)
        return Response(status_code=202)
    request_id = message["id"]
    if not protocol.is_request_id(request_id):
        return _error(None, McpError(INVALID_REQUEST, "The id must be a string or an integer"), True)
    method: str = message["method"]
    params = message.get("params", {})
    request.state.mcp_operation = _operation(method, params, modern)
    try:
        if not isinstance(params, dict):
            raise McpError(INVALID_PARAMS, "params must be an object")
        if modern:
            _check_modern(request, method, params)
        result = await _answer(request, caller, settings, graph, method, params, modern)
    except McpError as failure:
        return _error(request_id, failure, modern)
    except (ApiError, ServiceUnavailable):
        raise
    except Exception as exc:  # the answer names no cause; the log has the type and the method, never the body
        log.exception("mcp_internal_error", operation=request.state.mcp_operation, error_type=type(exc).__name__)
        return _error(request_id, McpError(INTERNAL_ERROR, "Internal error"), modern)
    return JSONResponse({"jsonrpc": "2.0", "id": request_id, "result": result})


def _refuse_constant(name: str) -> None:
    raise ValueError(f"{name} is not JSON")


async def _body(request: Request) -> bytes | None:
    """The body, or None when it is over the limit, declared or counted."""
    declared = request.headers.get("content-length")
    if declared is not None and (not declared.isdigit() or int(declared) > MAX_BODY_BYTES):
        return None
    body = bytearray()
    async for chunk in request.stream():
        body += chunk
        if len(body) > MAX_BODY_BYTES:
            return None
    return bytes(body)


def _error(request_id: Any, failure: McpError, modern: bool) -> JSONResponse:
    status = protocol.MODERN_STATUS.get(failure.code, 200) if modern else 200
    if failure.code in (PARSE_ERROR, INVALID_REQUEST):
        status = 400  # a body that is no request, whatever the revision
    return JSONResponse(protocol.error_message(request_id, failure), status_code=status)


def _check_modern(request: Request, method: str, params: dict[str, Any]) -> None:
    """Revision 2026-07-28: ``_meta`` carries the revision and the capabilities, the headers say what the body says,
    and the revision is one this endpoint answers, in this order, as the official SDK checks them."""
    meta = params.get("_meta")
    if not isinstance(meta, dict) or PROTOCOL_VERSION_KEY not in meta or CLIENT_CAPABILITIES_KEY not in meta:
        raise McpError(INVALID_PARAMS, f"params._meta must carry {PROTOCOL_VERSION_KEY} and {CLIENT_CAPABILITIES_KEY}")
    if not isinstance(meta[CLIENT_CAPABILITIES_KEY], dict):
        raise McpError(INVALID_PARAMS, f"{CLIENT_CAPABILITIES_KEY} must be an object")
    for header in protocol.ROUTING_HEADERS:
        if len(request.headers.getlist(header)) > 1:
            raise McpError(HEADER_MISMATCH, f"The {header} header appears more than once")
    if request.headers.get(protocol.VERSION_HEADER) != meta[PROTOCOL_VERSION_KEY]:
        raise McpError(HEADER_MISMATCH, f"The MCP-Protocol-Version header does not match {PROTOCOL_VERSION_KEY}")
    if request.headers.get(protocol.METHOD_HEADER) != method:
        raise McpError(HEADER_MISMATCH, "The Mcp-Method header does not match the method")
    name = params.get("name")
    if method == "tools/call" and name is not None:
        if protocol.decode_header(request.headers.get(protocol.NAME_HEADER)) != name:
            raise McpError(HEADER_MISMATCH, "The Mcp-Name header does not match the tool's name")
    if meta[PROTOCOL_VERSION_KEY] != MODERN_VERSION:
        version = meta[PROTOCOL_VERSION_KEY]
        if not isinstance(version, str):
            raise McpError(INVALID_PARAMS, f"{PROTOCOL_VERSION_KEY} must be a string")
        raise protocol.unsupported_version(version)


def _operation(method: str, params: Any, modern: bool) -> str:
    """What the request log keeps of a request: a method the endpoint has and a tool it has, never what else the
    client wrote."""
    if method not in (_MODERN_METHODS if modern else _HANDSHAKE_METHODS):
        return "unknown method"
    name = params.get("name") if isinstance(params, dict) else None
    return f"{method} {name}" if method == "tools/call" and isinstance(name, str) and name in _BY_NAME else method


async def _answer(
    request: Request,
    caller: Principal,
    settings: Settings,
    graph: Graph,
    method: str,
    params: dict[str, Any],
    modern: bool,
) -> dict[str, Any]:
    if modern and method == "server/discover":
        discovery = {
            "supportedVersions": list(protocol.PROTOCOL_VERSIONS),
            "capabilities": protocol.CAPABILITIES,
            "instructions": protocol.INSTRUCTIONS,
        }
        return protocol.complete(discovery, modern=True, cacheable=True)
    if not modern and method == "initialize":
        return _initialize(params)
    if not modern and method == "ping":
        return {}
    if method == "tools/list":
        if params.get("cursor") is not None:
            raise McpError(INVALID_PARAMS, "There is one page of tools and no cursor")
        tools = [tool.definition() for tool in TOOLS]
        return protocol.complete({"tools": tools}, modern=modern, cacheable=True)
    if method == "tools/call":
        return protocol.complete(await _call(request, caller, settings, graph, params), modern=modern)
    raise McpError(METHOD_NOT_FOUND, "Method not found")


def _initialize(params: dict[str, Any]) -> dict[str, Any]:
    """The handshake of 2025-11-25 and before, without a session: the client's revision when it is one of them,
    else the newest, as the handshake has it."""
    asked = params.get("protocolVersion")
    if not isinstance(asked, str):
        raise McpError(INVALID_PARAMS, "initialize needs protocolVersion")
    return {
        "protocolVersion": asked if asked in HANDSHAKE_VERSIONS else HANDSHAKE_VERSIONS[0],
        "capabilities": protocol.CAPABILITIES,
        "serverInfo": dict(protocol.SERVER_INFO),
        "instructions": protocol.INSTRUCTIONS,
    }


async def _call(
    request: Request, caller: Principal, settings: Settings, graph: Graph, params: dict[str, Any]
) -> dict[str, Any]:
    name, arguments = params.get("name"), params.get("arguments", {})
    if not isinstance(name, str):
        raise McpError(INVALID_PARAMS, "tools/call needs the tool's name")
    tool = _BY_NAME.get(name)
    if tool is None:
        raise McpError(INVALID_PARAMS, "Unknown tool: tools/list names the tools")
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        raise McpError(INVALID_PARAMS, "The arguments must be an object")
    context = registry.ToolContext(
        principal=caller,
        settings=settings,
        graph=graph,
        tool=tool.name,
        ip=client_ip(request),
        client_info=registry.client_info(params.get("_meta")),
    )
    if not caller.has_scope(tool.scope):
        await context.record("mcp.denied", reason="scope", scope=tool.scope)
        require_mcp_scope(caller, tool.scope, settings)
    wait = wait_seconds(RATE_MCP_TOOL_CALLS, "mcp-tool-calls", caller.token_hash)
    if wait is not None:
        log.warning("mcp_tool_calls_limited", client_id=caller.client_id)
        return registry.error_result(
            f"Too many tool calls: at most {RATE_MCP_TOOL_CALLS.replace('/', ' a ')} for each token. "
            f"Try again in {wait} seconds."
        )
    return await registry.call(tool, context, arguments)
