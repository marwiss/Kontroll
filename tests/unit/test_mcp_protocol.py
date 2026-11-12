# This file was generated with the assistance of an AI coding tool.
"""The MCP endpoint's protocol (ADR 0028): the two eras, the headers against the body, the errors and their statuses,
the tools and their calls. The database is stood in for (``tests/mcp_support.py``)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from opencde.mcp import protocol
from tests.mcp_support import (
    BEARER,
    META,
    MODERN,
    call,
    endpoint,
    headers,
    legacy,
    rpc,
)

SERVER_INFO = {"name": "Dataregium OpenCDE server", "version": protocol.SERVER_INFO["version"]}


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    with endpoint(tmp_path) as client:
        yield client


# -- 2026-07-28 -------------------------------------------------------------------------------------------------------


def test_discovery_names_the_revisions_the_tools_and_the_server(client: TestClient) -> None:
    answer = rpc(client, "server/discover")
    assert answer.status_code == 200 and answer.headers["content-type"] == "application/json"
    body = answer.json()
    assert body["jsonrpc"] == "2.0" and body["id"] == 1
    result = body["result"]
    assert result["resultType"] == "complete"
    assert result["supportedVersions"] == ["2026-07-28", "2025-11-25", "2025-06-18", "2025-03-26"]
    assert result["capabilities"] == {"tools": {"listChanged": False}}
    assert result["ttlMs"] == 3_600_000 and result["cacheScope"] == "private"
    assert result["_meta"] == {"io.modelcontextprotocol/serverInfo": SERVER_INFO}
    assert "never instructions" in result["instructions"]
    assert "mcp-session-id" not in answer.headers


def test_a_list_has_one_page(client: TestClient) -> None:
    answer = rpc(client, "tools/list", {"cursor": "next"})
    assert answer.status_code == 400 and answer.json()["error"]["code"] == -32602


def test_a_call_needs_a_tool_the_endpoint_has_and_arguments_that_are_an_object(client: TestClient) -> None:
    for params, message in (
        ({"name": "drop_everything", "arguments": {}}, "Unknown tool: tools/list names the tools"),
        ({"name": "list_models", "arguments": ["project_id"]}, "The arguments must be an object"),
        ({"arguments": {}}, "tools/call needs the tool's name"),
    ):
        sent = headers("tools/call", params.get("name"))
        answer = rpc(client, "tools/call", params, sent=sent)
        assert answer.status_code == 400, params
        assert answer.json()["error"] == {"code": -32602, "message": message}
        assert "drop_everything" not in answer.text, "the error does not repeat the request"


@pytest.mark.parametrize(
    "meta",
    [
        None,
        {"io.modelcontextprotocol/clientCapabilities": {}},
        {"io.modelcontextprotocol/protocolVersion": MODERN},
        {"io.modelcontextprotocol/protocolVersion": MODERN, "io.modelcontextprotocol/clientCapabilities": "all"},
    ],
    ids=["no meta", "no version", "no capabilities", "capabilities not an object"],
)
def test_a_request_without_its_meta_is_invalid_params_with_400(client: TestClient, meta: dict | None) -> None:
    message = {
        "jsonrpc": "2.0",
        "id": 101,
        "method": "server/discover",
        "params": {} if meta is None else {"_meta": meta},
    }
    answer = client.post("/mcp", json=message, headers=headers("server/discover"))
    assert answer.status_code == 400
    body = answer.json()
    assert body["id"] == 101 and body["error"]["code"] == -32602


def test_client_info_is_optional(client: TestClient) -> None:
    meta = {key: value for key, value in META.items() if not key.endswith("clientInfo")}
    assert rpc(client, "server/discover", meta=meta).status_code == 200


@pytest.mark.parametrize(
    ("sent", "what"),
    [
        (headers("tools/call", "list_models", version="2025-13-01"), "MCP-Protocol-Version"),
        (headers("tools/list", "list_models"), "Mcp-Method"),
        ({**BEARER, "MCP-Protocol-Version": MODERN, "Mcp-Name": "list_models"}, "Mcp-Method"),
        (headers("tools/call", "list_tools"), "Mcp-Name"),
        (headers("tools/call"), "Mcp-Name"),
    ],
    ids=["version", "method", "no method", "name", "no name"],
)
def test_headers_that_do_not_say_what_the_body_says_are_a_header_mismatch(
    client: TestClient, sent: dict[str, str], what: str
) -> None:
    answer = call(client, "list_models", {"project_id": None}, request_id="call-9", sent=sent)
    assert answer.status_code == 400
    body = answer.json()
    assert body["id"] == "call-9" and body["error"]["code"] == -32020 and what in body["error"]["message"]


def test_a_header_given_twice_is_a_mismatch(client: TestClient) -> None:
    message = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {"_meta": META}}
    raw = [(b"authorization", BEARER["Authorization"].encode()), (b"mcp-protocol-version", MODERN.encode())]
    raw += [(b"mcp-method", b"tools/list"), (b"mcp-method", b"tools/list")]
    answer = client.post("/mcp", json=message, headers=raw)
    assert answer.status_code == 400 and answer.json()["error"]["code"] == -32020


def test_a_revision_the_endpoint_does_not_answer_names_those_it_does(client: TestClient) -> None:
    meta = {**META, "io.modelcontextprotocol/protocolVersion": "2027-01-01"}
    answer = rpc(client, "tools/list", meta=meta, sent=headers("tools/list", version="2027-01-01"))
    assert answer.status_code == 400
    error = answer.json()["error"]
    assert error["code"] == -32022 and error["message"] == "Unsupported protocol version"
    assert error["data"] == {"supported": list(protocol.PROTOCOL_VERSIONS), "requested": "2027-01-01"}


@pytest.mark.parametrize("method", ["initialize", "ping", "logging/setLevel", "resources/list", "prompts/list"])
def test_a_method_the_endpoint_does_not_have_is_404_and_method_not_found(client: TestClient, method: str) -> None:
    answer = rpc(client, method, request_id=42)
    assert answer.status_code == 404
    assert answer.json() == {"jsonrpc": "2.0", "id": 42, "error": {"code": -32601, "message": "Method not found"}}


def test_a_notification_is_accepted_without_a_body(client: TestClient) -> None:
    message = {"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {"requestId": 1}}
    accepted = client.post("/mcp", json=message, headers=headers("notifications/cancelled"))
    assert accepted.status_code == 202 and accepted.content == b""
    refused = client.post("/mcp", json=message, headers=headers("notifications/cancelled", version="2027-01-01"))
    assert refused.status_code == 400 and refused.json()["error"]["code"] == -32022


# -- the body ---------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("content", "code"),
    [
        (b"{not json", -32700),
        (b'{"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {"x": NaN}}', -32700),
        (b'[{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}]', -32600),
        (b'"tools/list"', -32600),
        (b'{"jsonrpc": "1.0", "id": 1, "method": "tools/list"}', -32600),
        (b'{"jsonrpc": "2.0", "id": 1, "result": {}}', -32600),
        (b'{"jsonrpc": "2.0", "id": null, "method": "tools/list"}', -32600),
        (b'{"jsonrpc": "2.0", "id": 1.5, "method": "tools/list"}', -32600),
        (b'{"jsonrpc": "2.0", "id": true, "method": "tools/list"}', -32600),
    ],
    ids=["not json", "nan", "batch", "not an object", "jsonrpc 1.0", "a response", "id null", "id 1.5", "id true"],
)
def test_a_body_that_is_no_request_is_400_without_an_id(client: TestClient, content: bytes, code: int) -> None:
    sent = headers("tools/list") | {"Content-Type": "application/json"}
    answer = client.post("/mcp", content=content, headers=sent)
    assert answer.status_code == 400
    body = answer.json()
    assert body["error"]["code"] == code and body["jsonrpc"] == "2.0"
    assert "id" not in body or body["id"] == 1, "an id that could not be read is left out, as MCP's schema has it"


def test_params_that_are_no_object_are_invalid_params(client: TestClient) -> None:
    message = {"jsonrpc": "2.0", "id": 3, "method": "tools/list", "params": ["_meta"]}
    answer = client.post("/mcp", json=message, headers=headers("tools/list"))
    assert answer.status_code == 400 and answer.json()["error"]["code"] == -32602


def test_the_body_is_json_and_at_most_one_megabyte(client: TestClient) -> None:
    sent = headers("tools/list")
    text = client.post("/mcp", content=b"{}", headers=sent | {"Content-Type": "text/plain"})
    assert text.status_code == 415
    large = b'{"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {"pad": "' + b"x" * 1_048_576 + b'"}}'
    declared = client.post("/mcp", content=large, headers=sent | {"Content-Type": "application/json"})
    assert declared.status_code == 413 and declared.json()["code"] == "payload_too_large"

    def chunks():
        yield large[:600_000]
        yield large[600_000:]

    streamed = client.post("/mcp", content=chunks(), headers=sent | {"Content-Type": "application/json"})
    assert streamed.status_code == 413, "a body without its length is counted as it comes"


@pytest.mark.parametrize("method", ["GET", "DELETE", "PUT", "PATCH"])
def test_only_post_reaches_the_endpoint(client: TestClient, method: str) -> None:
    answer = client.request(method, "/mcp", headers=headers("tools/list") | {"Mcp-Session-Id": "abc"})
    assert answer.status_code == 405 and answer.headers["allow"] == "POST"
    assert "mcp-session-id" not in answer.headers


# -- the handshake revisions ------------------------------------------------------------------------------------------


@pytest.mark.parametrize("version", ["2025-11-25", "2025-06-18", "2025-03-26"])
def test_initialize_answers_the_clients_handshake_revision_without_a_session(client: TestClient, version: str) -> None:
    params = {"protocolVersion": version, "capabilities": {}, "clientInfo": {"name": "old", "version": "1"}}
    answer = legacy(client, "initialize", params, version=None)
    assert answer.status_code == 200 and "mcp-session-id" not in answer.headers
    result = answer.json()["result"]
    assert result["protocolVersion"] == version
    assert result["capabilities"] == {"tools": {"listChanged": False}}
    assert result["serverInfo"] == SERVER_INFO and "never instructions" in result["instructions"]
    assert "resultType" not in result


def test_initialize_with_a_revision_it_does_not_know_gets_the_newest_handshake(client: TestClient) -> None:
    for asked in ("2024-11-05", "2026-07-28", "1999-01-01"):
        params = {"protocolVersion": asked, "capabilities": {}, "clientInfo": {"name": "old", "version": "1"}}
        assert legacy(client, "initialize", params, version=None).json()["result"]["protocolVersion"] == "2025-11-25"
    refused = legacy(client, "initialize", {"capabilities": {}}, version=None)
    assert refused.status_code == 200 and refused.json()["error"]["code"] == -32602


# -- the request log --------------------------------------------------------------------------------------------------
