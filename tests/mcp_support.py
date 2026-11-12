# This file was generated with the assistance of an AI coding tool.
"""What the tests of the MCP endpoint share: the application with a token store that stands in for the database,
and requests as the two eras of the protocol write them. The token store knows one token, bound to the endpoint."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from opencde.auth.dependencies import get_tokens
from opencde.main import create_app
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


BOUND = principal()


@contextmanager
def endpoint(
    tmp_path: Path,
    found: Principal | None = BOUND,
    *,
    base_url: str = "http://testserver",
    **overrides: Any,
) -> Iterator[TestClient]:
    """The application with the endpoint on and the token store standing in for the database; ``found`` None is a
    token the store does not know."""
    settings = make_settings(tmp_path, **{"mcp_enabled": True, **overrides})
    app = create_app(settings, startup_wait_seconds=0)
    app.dependency_overrides[get_tokens] = lambda: OneToken(found)
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
