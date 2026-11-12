# This file was generated with the assistance of an AI coding tool.
"""What the tests of the MCP endpoint share: the application with a token store and a graph that stand in for the
database, and requests as the two eras of the protocol write them.

The token store knows one token, bound to the endpoint; the graph answers the memberships and the models it is
given and keeps every statement with its parameters, so that a test sees what reached the database. The database's
own side is in ``tests/integration/test_mcp_list_models.py``.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from opencde import audit
from opencde.auth.dependencies import get_tokens
from opencde.deps import get_graph
from opencde.main import create_app
from opencde.mcp.ifc_models import MODELS
from opencde.store.oauth2.tokens import Principal
from tests.conftest import test_settings as make_settings

MCP = "http://testserver/mcp"
MODERN = "2026-07-28"
BEARER = {"Authorization": "Bearer a-token-the-store-knows"}
META = {
    "io.modelcontextprotocol/protocolVersion": MODERN,
    "io.modelcontextprotocol/clientCapabilities": {},
    "io.modelcontextprotocol/clientInfo": {"name": "test-client", "version": "1.0"},
}
CLOUD = "11111111-1111-4111-8111-111111111111"
LOCAL = "22222222-2222-4222-8222-222222222222"
DOCUMENT = "33333333-3333-4333-8333-333333333333"


def principal(
    scopes: tuple[str, ...] = ("mcp",), resource: str | None = MCP, hashed: str = "hash-of-the-token"
) -> Principal:
    return Principal(
        user_id="u-anna",
        username="anna",
        display_name="Anna",
        is_admin=False,
        client_id="ai-client",
        scopes=scopes,
        token_hash=hashed,
        auth_time="2999-01-01T00:00:00Z",
        resource=resource,
    )


class OneToken:
    """A token store that knows one principal, whatever token is presented, or none."""

    def __init__(self, found: Principal | None) -> None:
        self.found = found

    async def principal(self, access_token: str) -> Principal | None:
        return self.found


def project(project_id: str, name: str, ai_policy: str | None) -> dict[str, Any]:
    found = {"project_id": project_id, "name": name, "created_at": "2026-11-01T00:00:00.000Z"}
    return found | ({"ai_policy": ai_policy} if ai_policy else {})


def model_row(project_id: str = CLOUD, index: int = 1, **values: Any) -> dict[str, Any]:
    """A row as the statement of ``list_models`` returns it."""
    return {
        "project_id": project_id,
        "project_name": "Cloud project",
        "role": "editor",
        "ai_policy": "cloud",
        "document_id": DOCUMENT,
        "title": f"Model {index}",
        "file_name": f"model-{index}.ifc",
        "version_index": 3,
        "model_state": "done",
        "schema": "IFC4",
    } | values


class FakeGraph:
    """The server's own graph as far as the endpoint reads and writes it."""

    def __init__(self, memberships: list[tuple[dict[str, Any], str]] | None = None, models: list | None = None):
        self.memberships = (
            memberships if memberships is not None else [(project(CLOUD, "Cloud project", "cloud"), "editor")]
        )
        self.models = models if models is not None else [model_row()]
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def run(self, query: str, **params: Any) -> list[dict[str, Any]]:
        self.calls.append((query, params))
        if query == MODELS:
            return list(self.models)
        if "RETURN properties(p) AS project, m.role AS role" in query:
            return [{"project": found, "role": role} for found, role in self.memberships]
        return []

    def events(self) -> list[dict[str, Any]]:
        """The audit events written, with their details read back."""
        return [
            {**params, "details": json.loads(params["details"])}
            for query, params in self.calls
            if query == audit.CREATE
        ]

    def model_queries(self) -> list[dict[str, Any]]:
        return [params for query, params in self.calls if query == MODELS]


BOUND = principal()


@contextmanager
def endpoint(
    tmp_path: Path,
    graph: FakeGraph | None = None,
    found: Principal | None = BOUND,
    *,
    base_url: str = "http://testserver",
    **overrides: Any,
) -> Iterator[TestClient]:
    """The application with the endpoint on, the token store and the graph standing in for the database; ``found``
    None is a token the store does not know."""
    settings = make_settings(tmp_path, **{"mcp_enabled": True, **overrides})
    app = create_app(settings, startup_wait_seconds=0)
    app.dependency_overrides[get_tokens] = lambda: OneToken(found)
    app.dependency_overrides[get_graph] = lambda: graph if graph is not None else FakeGraph()
    with TestClient(app, base_url=base_url) as client:
        yield client


def headers(method: str, name: str | None = None, version: str = MODERN, **extra: str) -> dict[str, str]:
    """The headers a client of 2026-07-28 sends with a request."""
    sent = {**BEARER, "MCP-Protocol-Version": version, "Mcp-Method": method}
    if name is not None:
        sent["Mcp-Name"] = name
    return sent | extra


def rpc(
    client: TestClient,
    method: str,
    params: dict[str, Any] | None = None,
    *,
    request_id: int | str = 1,
    meta: dict[str, Any] | None = None,
    sent: dict[str, str] | None = None,
) -> Any:
    """A request of 2026-07-28, with its ``_meta`` and its headers; either can be given to make it wrong."""
    body_params = {**(params or {}), "_meta": META if meta is None else meta}
    name = body_params.get("name") if method == "tools/call" else None
    message = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": body_params}
    return client.post("/mcp", json=message, headers=headers(method, name) if sent is None else sent)


def call(client: TestClient, name: str, arguments: dict[str, Any] | None, **kwargs: Any) -> Any:
    return rpc(client, "tools/call", {"name": name, "arguments": arguments}, **kwargs)


def legacy(
    client: TestClient, method: str, params: dict[str, Any] | None = None, *, version: str | None = "2025-11-25"
) -> Any:
    """A request of a handshake revision: its revision in the header after ``initialize``, no ``_meta``."""
    sent = {**BEARER} | ({"MCP-Protocol-Version": version} if version else {})
    message: dict[str, Any] = {"jsonrpc": "2.0", "id": 7, "method": method}
    if params is not None:
        message["params"] = params
    return client.post("/mcp", json=message, headers=sent)
