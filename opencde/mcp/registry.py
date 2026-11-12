# This file was generated with the assistance of an AI coding tool.
"""The MCP endpoint's tools (ADR 0028): how a tool is defined, listed and called.

A tool's arguments are a pydantic model, a flat object in which every field is required and ``null`` means "not
given", as Dataspatium's strict schemas are; a field may hold an object of the same form, or a list of them, written
out in place. ``tools/list`` gives the JSON Schema generated from it, in the order the tools are registered. A call validates the arguments, and a refusal (arguments the model does not take, a project
that is not the caller's, a policy, a role) is a tool result with ``isError`` that the AI can read and act on, in
fixed words that never quote the arguments or the files. An answer is ``structuredContent`` and the same JSON as
text, at most 256 kB. ``mcp.*`` events go to the audit log through :meth:`ToolContext.record`, never with an argument
or a text from the projects.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, NoReturn

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, ValidationError

from opencde import audit
from opencde.accounts.roles import Role
from opencde.auth.scopes import MCP_READ
from opencde.graph.graph import Graph
from opencde.ids import is_uuid, normalize_guid
from opencde.mcp.protocol import CLIENT_INFO_KEY
from opencde.settings import Settings
from opencde.store.accounts.projects import Project, ProjectRepository
from opencde.store.documents.versions import DocumentRepository, VersionRecord
from opencde.store.oauth2.tokens import Principal

if TYPE_CHECKING:
    from opencde.ifcgraph.service import IfcGraphService

#: The most an answer holds, as JSON; the client gets it twice, as ``structuredContent`` and as text.
MAX_ANSWER_BYTES = 256 * 1024
#: How much of a text from the projects an answer carries: a name or a title.
MAX_NAME = 200
_CLIENT_TEXT = 100  # how much of the name and version a client gives of itself goes to the audit log


class Arguments(BaseModel):
    """A tool's arguments: a flat object; every field required, null for what is not given."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class ToolRefusal(Exception):
    """A refusal the AI can read, answered as a tool result with ``isError``. A fixed text: never the arguments."""


@contextmanager
def refusing() -> Generator[None, None, None]:
    """A refusal of a function a tool shares with a REST route, as the tool's own: the route's fixed text, which never
    quotes the request, without its status. A server error stays one."""
    try:
        yield
    except HTTPException as exc:
        if exc.status_code >= 500:
            raise
        raise ToolRefusal(str(exc.detail)) from None


@dataclass(frozen=True)
class ToolContext:
    """What a call knows: who calls, through which client, the server's own graph, and the IFC-LPG module's service
    while the module is on (the IFC graph, the working copy and the clash checks)."""

    principal: Principal
    settings: Settings
    graph: Graph
    tool: str
    ip: str | None = None
    client_info: dict[str, str] = field(default_factory=dict)
    ifcgraph: IfcGraphService | None = None

    async def record(self, event: str, **details: Any) -> None:
        """An ``mcp.*`` event in the audit log: who, through which client and tool; identifiers, never texts."""
        client = {"client_info": self.client_info} if self.client_info else {}
        await audit.record(
            self.graph,
            event,
            actor=self.principal.user_id,
            client_id=self.principal.client_id,
            ip=self.ip,
            details={"tool": self.tool, **client, **details},
        )

    async def deny(self, reason: str, message: str, **details: Any) -> NoReturn:
        """Refuse for a reason the audit log keeps (``policy``, ``role`` or ``scope``), and tell the AI why."""
        await self.record("mcp.denied", reason=reason, **details)
        raise ToolRefusal(message)


@dataclass(frozen=True)
class Tool:
    name: str
    title: str
    description: str
    arguments: type[Arguments]
    run: Callable[[ToolContext, Any], Awaitable[dict[str, Any]]]
    scope: str = MCP_READ
    read_only: bool = True

    def definition(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "inputSchema": input_schema(self.arguments),
            "annotations": {"readOnlyHint": self.read_only, "openWorldHint": False},
        }


def input_schema(model: type[Arguments]) -> dict[str, Any]:
    """The arguments as JSON Schema 2020-12, generated from the model: a flat object without titles, and an object a
    field holds written out in place, of the same form, as the strict modes of the AI providers take them."""
    generated = model.model_json_schema()
    return _strict(generated, generated.get("$defs", {}), model.__name__)


def _strict(schema: dict[str, Any], definitions: dict[str, Any], where: str) -> dict[str, Any]:
    """An object of which every property is required and no other is taken."""
    properties = {
        name: _in_place(value, definitions, f"{where}.{name}") for name, value in schema.get("properties", {}).items()
    }
    if sorted(schema.get("required", [])) != sorted(properties):
        raise ValueError(f"{where}: every argument is required, with null for what is not given")
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


def _in_place(schema: Any, definitions: dict[str, Any], where: str) -> Any:
    """A part of a schema without its titles, and each object it refers to written out where it is referred to."""
    if isinstance(schema, list):
        return [_in_place(part, definitions, where) for part in schema]
    if not isinstance(schema, dict):
        return schema
    if "$ref" in schema:
        found = definitions[schema["$ref"].rsplit("/", 1)[-1]]
        if "properties" not in found:
            raise ValueError(f"{where}: a field refers to an object or to nothing")
        own = {key: value for key, value in schema.items() if key not in ("$ref", "title")}
        return _strict(found, definitions, where) | own
    if "properties" in schema:
        return _strict(schema, definitions, where)
    return {key: _in_place(value, definitions, where) for key, value in schema.items() if key != "title"}


def _field_names(schema: Any) -> set[str]:
    """The name of every argument a schema takes, at any depth."""
    if isinstance(schema, list):
        return set().union(*(_field_names(part) for part in schema))
    if not isinstance(schema, dict):
        return set()
    properties = schema.get("properties", {})
    found = set(properties).union(*(_field_names(part) for part in properties.values()))
    return found.union(*(_field_names(value) for key, value in schema.items() if key != "properties"))


def client_info(meta: Any) -> dict[str, str]:
    """The name and version a client gives of itself, cut short: self-reported, for the audit log only."""
    info = meta.get(CLIENT_INFO_KEY) if isinstance(meta, dict) else None
    if not isinstance(info, dict):
        return {}
    return {key: info[key][:_CLIENT_TEXT] for key in ("name", "version") if isinstance(info.get(key), str)}


def text_result(answer: dict[str, Any]) -> dict[str, Any]:
    text = json.dumps(answer, ensure_ascii=False, separators=(",", ":"))
    if len(text.encode("utf-8")) > MAX_ANSWER_BYTES:
        return error_result(f"The answer would be larger than {MAX_ANSWER_BYTES // 1024} kB; ask for less")
    return {"content": [{"type": "text", "text": text}], "structuredContent": answer, "isError": False}


def error_result(message: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": message}], "isError": True}


def problems(exc: ValidationError, model: type[Arguments]) -> str:
    """What is wrong with the arguments, naming the fields the tool takes (``a.version_index`` within an object, with
    a list's positions) and never a value given, nor a name the tool does not take."""
    known = _field_names(input_schema(model))
    found: list[str] = []
    for error in exc.errors(include_input=False, include_url=False, include_context=False):
        location = error.get("loc", ())
        named = bool(location) and error.get("type") != "extra_forbidden"
        if named and all(isinstance(part, int) or part in known for part in location):
            problem = ".".join(str(part) for part in location) + f": {error.get('msg', 'invalid')}"
        else:
            problem = "an argument the tool does not take"
        if problem not in found:
            found.append(problem)
    return "Invalid arguments: " + "; ".join(found[:5])


async def call(tool: Tool, context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """Validate and run, and answer the tool's result or its refusal; the caller has checked the scope."""
    try:
        parsed = tool.arguments.model_validate(arguments)
    except ValidationError as exc:
        return error_result(problems(exc, tool.arguments))
    try:
        answer = await tool.run(context, parsed)
    except ToolRefusal as refusal:
        return error_result(str(refusal))
    return text_result(answer)


def text(value: Any) -> str | None:
    """A name or a title from the projects as an answer carries it: as it is, cut at a fixed length."""
    return value[:MAX_NAME] if isinstance(value, str) else None


def serves(settings: Settings, ai_policy: str) -> bool:
    """Whether this server may give a project's data to AI tools (F29 a): the local engine every project, since the
    computer is the boundary; any other server only a project whose policy is ``cloud``."""
    return settings.is_local or ai_policy == "cloud"


async def member_version(context: ToolContext, document_id: str, version_index: int | None) -> VersionRecord:
    """A version of a document in one of the caller's projects, the latest when ``version_index`` is None, reached
    from the user through ``MEMBER_OF``, in a project this server may give to AI tools; a refusal otherwise, and
    ``mcp.denied`` when the policy is why (:func:`member_project`)."""
    did = normalize_guid(document_id) if is_uuid(document_id) else None
    record = None
    if did is not None:
        documents, user_id = DocumentRepository(context.graph), context.principal.user_id
        record = await (
            documents.latest(user_id=user_id, document_id=did)
            if version_index is None
            else documents.version(user_id=user_id, document_id=did, version_index=version_index)
        )
    if record is None:
        raise ToolRefusal("There is no such document version among your projects")
    await member_project(context, record.project_id)
    return record


async def member_project(context: ToolContext, project_id: str) -> tuple[Project, Role]:
    """One of the caller's projects, reached from the user through ``MEMBER_OF``, that this server may give to AI
    tools; a refusal otherwise, and ``mcp.denied`` when the policy is why."""
    pid = normalize_guid(project_id) if is_uuid(project_id) else None
    memberships = await ProjectRepository(context.graph).list_for_user(context.principal.user_id) if pid else []
    found = next(((project, role) for project, role in memberships if project.project_id == pid), None)
    if found is None:
        raise ToolRefusal("There is no project with this id among your projects")
    if not serves(context.settings, found[0].ai_policy):
        await context.deny(
            "policy",
            "This project's AI policy is local only: its data goes to AI tools only through the local engine on the "
            "user's own computer. A manager of the project can change the policy.",
            project_id=pid,
        )
    return found
