# This file was generated with the assistance of an AI coding tool.
"""The MCP endpoint's tools (ADR 0028): how a tool is defined, listed and called.

A tool's arguments are a pydantic model, a flat object in which every field is required and ``null`` means "not
given", as Dataspatium's strict schemas are; ``tools/list`` gives the JSON Schema generated from it, in the order the
tools are registered. A call validates the arguments, and a refusal (arguments the model does not take, a project
that is not the caller's, a policy, a role) is a tool result with ``isError`` that the AI can read and act on, in
fixed words that never quote the arguments or the files. An answer is ``structuredContent`` and the same JSON as
text, at most 256 kB. ``mcp.*`` events go to the audit log through :meth:`ToolContext.record`, never with an argument
or a text from the projects.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, NoReturn

from pydantic import BaseModel, ConfigDict, ValidationError

from opencde import audit
from opencde.accounts.roles import Role
from opencde.auth.scopes import MCP_READ
from opencde.graph.graph import Graph
from opencde.ids import is_uuid, normalize_guid
from opencde.mcp.protocol import CLIENT_INFO_KEY
from opencde.settings import Settings
from opencde.store.accounts.projects import Project, ProjectRepository
from opencde.store.oauth2.tokens import Principal

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


@dataclass(frozen=True)
class ToolContext:
    """What a call knows: who calls, through which client, and the server's own graph."""

    principal: Principal
    settings: Settings
    graph: Graph
    tool: str
    ip: str | None = None
    client_info: dict[str, str] = field(default_factory=dict)

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
    """The arguments as JSON Schema 2020-12, generated from the model: a flat object without titles."""
    generated = model.model_json_schema()
    if "$defs" in generated:
        raise ValueError(f"{model.__name__} is not flat: a tool's arguments hold no objects")
    properties = {
        name: {key: value for key, value in schema.items() if key != "title"}
        for name, schema in generated.get("properties", {}).items()
    }
    if sorted(generated.get("required", [])) != sorted(properties):
        raise ValueError(f"{model.__name__}: every argument is required, with null for what is not given")
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


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
    """What is wrong with the arguments, naming the fields the tool takes and never a value given."""
    known = set(model.model_fields)
    found: list[str] = []
    for error in exc.errors(include_input=False, include_url=False, include_context=False):
        location = error.get("loc", ())
        name = str(location[0]) if location else ""
        problem = f"{name}: {error.get('msg', 'invalid')}" if name in known else "an argument the tool does not take"
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
