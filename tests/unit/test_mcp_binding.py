# This file was generated with the assistance of an AI coding tool.
"""Resource indicators (RFC 8707) and the MCP scopes at the authorization and token endpoints (ADR 0028, F31 a).

The stores stand in for the database: what the endpoints accept, refuse and pass on is tested here, and what the
database keeps in ``tests/integration/test_mcp_tokens.py``.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fastapi.testclient import TestClient

from opencde.auth import pkce, resources
from opencde.auth.dependencies import get_tokens
from opencde.auth.forms import FormTokens
from opencde.auth.routes import FORM_PURPOSE
from opencde.auth.scopes import DEFAULT_SCOPES, ScopeError, offered_scopes, parse_scope
from opencde.deps import get_clients, get_graph
from opencde.main import create_app
from opencde.store.oauth2.clients import Client
from opencde.store.oauth2.tokens import TokenPair
from tests.conftest import test_settings as make_settings

MCP = "http://testserver/mcp"
REDIRECT = "http://127.0.0.1/callback"
FORM_TOKEN = re.compile(r'name="form_token" value="([^"]+)"')
CLIENT = Client(
    client_id="ai-client",
    name="An AI client",
    description=None,
    url=None,
    redirect_uris=[REDIRECT],
    is_public=True,
    disabled=False,
    created_at="2026-11-12T00:00:00Z",
    created_by=None,
    dynamic=False,
)


class Clients:
    async def get(self, client_id: str) -> Client | None:
        return CLIENT if client_id == CLIENT.client_id else None

    async def authenticate(self, client_id: str, secret: str | None) -> Client | None:
        return CLIENT if client_id == CLIENT.client_id and not secret else None

    async def touch(self, client_id: str, *, expires_at: str) -> None:
        return None


class Tokens:
    """Notes what the token endpoint asks of the store."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def redeem_code(self, **request: Any) -> TokenPair:
        self.calls.append(("code", request))
        return TokenPair("access", "refresh", 3600, "mcp")

    async def refresh(self, **request: Any) -> TokenPair:
        self.calls.append(("refresh", request))
        return TokenPair("access", "refresh", 3600, "mcp")


class Graph:
    """Where the audit events go: nowhere."""

    async def run(self, *_args: Any, **_params: Any) -> list[dict[str, Any]]:
        return []


def _client(tmp_path: Path, **overrides: object) -> Iterator[tuple[TestClient, Tokens]]:
    app = create_app(make_settings(tmp_path, **overrides), startup_wait_seconds=0)
    tokens = Tokens()
    app.dependency_overrides[get_clients] = Clients
    app.dependency_overrides[get_tokens] = lambda: tokens
    app.dependency_overrides[get_graph] = Graph
    with TestClient(app) as client:
        yield client, tokens


@pytest.fixture
def mcp_on(tmp_path: Path) -> Iterator[tuple[TestClient, Tokens]]:
    yield from _client(tmp_path, mcp_enabled=True)


@pytest.fixture
def mcp_off(tmp_path: Path) -> Iterator[tuple[TestClient, Tokens]]:
    yield from _client(tmp_path)


def _authorize(client: TestClient, *pairs: tuple[str, str], scope: str | None = None) -> httpx.Response:
    params = [
        ("response_type", "code"),
        ("client_id", CLIENT.client_id),
        ("redirect_uri", REDIRECT),
        ("state", "s1"),
        ("code_challenge", pkce.challenge_for("v" * 50)),
        ("code_challenge_method", "S256"),
        *pairs,
    ]
    if scope is not None:
        params.append(("scope", scope))
    return client.get("/foundation/oauth2/auth", params=params, follow_redirects=False)


def _refusal(response: httpx.Response) -> tuple[str, str]:
    """The error and its description from the redirect, which also carries ``state`` and ``iss``."""
    assert response.status_code == 302, response.text[:300]
    query = parse_qs(urlsplit(response.headers["location"]).query)
    assert query["state"] == ["s1"] and query["iss"] == ["http://testserver"]
    return query["error"][0], query["error_description"][0]


def _signed(client: TestClient, page: httpx.Response) -> dict[str, Any]:
    """What the consent page carries to its form, as the server signed it."""
    assert page.status_code == 200, page.text[:300]
    match = FORM_TOKEN.search(page.text)
    assert match, "the page carries a form token"
    settings = client.app.state.settings
    signer = FormTokens(settings.secret_key.get_secret_value(), settings.form_token_ttl_seconds)
    return signer.load(match.group(1), FORM_PURPOSE)


def test_the_mcp_scopes_are_never_given_by_default_and_offered_only_with_the_endpoint() -> None:
    assert not set(parse_scope(None)) & {"mcp", "mcp:propose"} and tuple(parse_scope(None)) == DEFAULT_SCOPES
    assert parse_scope("mcp mcp:propose") == ["mcp", "mcp:propose"]
    assert offered_scopes(make_settings()) == ["profile", "bcf", "documents", "project", "admin"]
    assert offered_scopes(make_settings(mcp_enabled=True))[-2:] == ["mcp", "mcp:propose"]


def test_a_resource_is_compared_in_its_canonical_form_and_only_the_mcp_endpoint_is_one() -> None:
    on = make_settings(mcp_enabled=True)
    assert resources.mcp_resource(on) == MCP
    for spelling in (MCP, MCP + "/", "HTTP://TestServer/mcp", "http://testserver/mcp//"):
        assert resources.requested([spelling], on) == MCP, spelling
    assert resources.requested(None, on) is None and resources.requested(["", "  "], on) is None
    assert resources.requested([MCP, MCP + "/"], on) == MCP, "two spellings of one resource are one"
    others = (
        "https://testserver/mcp",
        "http://testserver",
        "http://testserver/mcp/tools",
        "http://testserver/MCP",
        "http://testserver/mcp?x=1",
        "http://testserver/mcp#part",
        "mcp",
        "/mcp",
        "http://[::1/mcp",
    )
    for other in others:
        with pytest.raises(resources.TargetError):
            resources.requested([other], on)
    with pytest.raises(resources.TargetError, match="one resource"):
        resources.requested([MCP, "https://other.example/mcp"], on)
    with pytest.raises(resources.TargetError, match="unknown resource"):
        resources.requested([MCP], make_settings())


def test_the_binding_rules_of_scope_and_resource() -> None:
    on = make_settings(mcp_enabled=True)
    assert resources.binding(["mcp"], [MCP], on) == MCP
    assert resources.binding(["mcp", "mcp:propose"], [MCP], on) == MCP
    assert resources.binding(["profile", "bcf", "documents"], None, on) is None
    with pytest.raises(resources.TargetError, match="needs resource=http://testserver/mcp"):
        resources.binding(["mcp"], None, on)
    with pytest.raises(resources.TargetError):
        resources.binding(["mcp:propose"], [], on)
    for scopes in (["mcp:propose"], ["mcp", "bcf"], ["profile", "mcp"], ["profile", "bcf", "documents"], ["admin"]):
        with pytest.raises(ScopeError):
            resources.binding(scopes, [MCP], on)
    with pytest.raises(resources.TargetError, match="unknown resource"):
        resources.binding(["mcp"], [MCP], make_settings())
    with pytest.raises(ScopeError, match="unknown scope 'mcp'"):
        resources.binding(["mcp"], None, make_settings())


def test_the_authorization_request_binds_the_token_to_the_mcp_endpoint(mcp_on: tuple[TestClient, Tokens]) -> None:
    client, _ = mcp_on
    page = _authorize(client, ("resource", MCP), scope="mcp mcp:propose")
    signed = _signed(client, page)
    assert signed["resource"] == MCP and signed["scope"] == "mcp mcp:propose"
    canonical = _signed(client, _authorize(client, ("resource", "HTTP://TESTSERVER/mcp/"), scope="mcp"))
    assert canonical["resource"] == MCP, "the binding is stored in its canonical form"
    rest = _signed(client, _authorize(client, scope="profile bcf documents"))
    assert rest["resource"] is None, "without a resource the token is for the REST APIs, as before"
    blank = _signed(client, _authorize(client, ("resource", "")))
    assert blank["resource"] is None and blank["scope"] == "profile bcf documents"


def test_any_other_resource_is_invalid_target_and_never_repeated(mcp_on: tuple[TestClient, Tokens]) -> None:
    client, _ = mcp_on
    for other in ("https://evil.example/mcp", "http://testserver/evil", "http://testserver/mcp#evil", "evil"):
        error, description = _refusal(_authorize(client, ("resource", other), scope="mcp"))
        assert error == "invalid_target", other
        assert "evil" not in description, "the client's value is not echoed"
    error, _ = _refusal(_authorize(client, ("resource", MCP), ("resource", "https://evil.example/mcp"), scope="mcp"))
    assert error == "invalid_target", "one resource at most"


def test_the_mcp_scopes_and_the_resource_come_together(mcp_on: tuple[TestClient, Tokens]) -> None:
    client, _ = mcp_on
    assert _refusal(_authorize(client, scope="mcp"))[0] == "invalid_target", "the resource is missing"
    assert _refusal(_authorize(client, scope="profile mcp:propose"))[0] == "invalid_target"
    for scope in (None, "mcp:propose", "mcp bcf", "profile mcp", "mcp mcp:propose documents", "admin"):
        error, description = _refusal(_authorize(client, ("resource", MCP), scope=scope))
        assert error == "invalid_scope", scope
        assert "MCP endpoint" in description, scope


def test_without_the_mcp_endpoint_there_is_neither_resource_nor_mcp_scope(mcp_off: tuple[TestClient, Tokens]) -> None:
    client, _ = mcp_off
    assert _refusal(_authorize(client, ("resource", MCP), scope="mcp")) == ("invalid_target", "unknown resource")
    assert _refusal(_authorize(client, ("resource", MCP)))[0] == "invalid_target"
    assert _refusal(_authorize(client, scope="mcp mcp:propose")) == ("invalid_scope", "unknown scope 'mcp'")
    assert _signed(client, _authorize(client))["resource"] is None, "a REST client notices nothing"


def test_the_consent_page_says_what_the_mcp_scopes_give(mcp_on: tuple[TestClient, Tokens]) -> None:
    client, _ = mcp_on
    english = _authorize(client, ("resource", MCP), ("lang", "en"), scope="mcp mcp:propose").text
    assert "reading the models, queries and proposals of your projects" in english
    assert "proposing change sets, which a person then approves or rejects" in english
    assert english.count("Nothing is approved or published this way.") == 2
    swedish = _authorize(client, ("resource", MCP), ("lang", "sv"), scope="mcp mcp:propose").text
    assert swedish.count("Inget godkänns eller publiceras den vägen.") == 2


def _token(client: TestClient, *pairs: tuple[str, str], query: str = "") -> httpx.Response:
    form: dict[str, list[str]] = {}
    for name, value in pairs:
        form.setdefault(name, []).append(value)  # a name given twice is sent twice
    return client.post(f"/foundation/oauth2/token{query}", data=form)


def test_the_token_request_passes_the_resource_on(mcp_on: tuple[TestClient, Tokens]) -> None:
    client, tokens = mcp_on
    code = [("grant_type", "authorization_code"), ("code", "c"), ("code_verifier", "v" * 50)]
    with_client = [*code, ("client_id", CLIENT.client_id)]
    assert _token(client, *with_client, ("resource", MCP + "/")).status_code == 201
    assert tokens.calls[-1] == (
        "code",
        {
            "code": "c",
            "client_id": CLIENT.client_id,
            "redirect_uri": None,
            "code_verifier": "v" * 50,
            "resource": MCP,
        },
    )
    assert _token(client, *with_client).status_code == 201
    assert tokens.calls[-1][1]["resource"] is None, "the store then binds the tokens as the code is"
    refresh = [("grant_type", "refresh_token"), ("refresh_token", "r"), ("client_id", CLIENT.client_id)]
    assert _token(client, *refresh, ("resource", MCP)).status_code == 201
    assert tokens.calls[-1] == ("refresh", {"refresh_token": "r", "client_id": CLIENT.client_id, "resource": MCP})
    assert _token(client, *refresh, ("resource", " ")).status_code == 201
    assert tokens.calls[-1][1]["resource"] is None


def test_the_token_request_refuses_any_other_resource(
    mcp_on: tuple[TestClient, Tokens], mcp_off: tuple[TestClient, Tokens]
) -> None:
    client, tokens = mcp_on
    refresh = [("grant_type", "refresh_token"), ("refresh_token", "r"), ("client_id", CLIENT.client_id)]
    for pairs, query in (
        ([("resource", "https://evil.example/mcp")], ""),
        ([("resource", MCP), ("resource", "http://testserver/other")], ""),
        ([], "?resource=https%3A%2F%2Fevil.example%2Fmcp"),
    ):
        refused = _token(client, *refresh, *pairs, query=query)
        assert refused.status_code == 400 and refused.json()["error"] == "invalid_target", (pairs, query)
        assert "evil" not in refused.json()["error_description"]
        assert refused.headers["cache-control"] == "no-store"
    assert tokens.calls == [], "nothing reached the store"
    off, untouched = mcp_off
    refused = _token(off, *refresh, ("resource", MCP))
    assert refused.status_code == 400 and refused.json()["error"] == "invalid_target"
    assert untouched.calls == []


def test_the_capabilities_name_the_mcp_scopes_only_with_the_endpoint(
    mcp_on: tuple[TestClient, Tokens], mcp_off: tuple[TestClient, Tokens]
) -> None:
    assert mcp_on[0].get("/.well-known/dataregium").json()["scopes"][-2:] == ["mcp", "mcp:propose"]
    assert "mcp" not in mcp_off[0].get("/.well-known/dataregium").json()["scopes"]


LOCALHOST = "http://localhost/callback"


class LocalhostClients(Clients):
    """A program that comes back to http://localhost, as several MCP programs do."""

    async def get(self, client_id: str) -> Client | None:
        found = await super().get(client_id)
        return None if found is None else replace(found, redirect_uris=[LOCALHOST])


def _localhost(client: TestClient, *pairs: tuple[str, str], scope: str | None = None) -> httpx.Response:
    params = [
        ("response_type", "code"),
        ("client_id", CLIENT.client_id),
        ("redirect_uri", "http://localhost:53682/callback"),
        ("state", "s1"),
        ("code_challenge", pkce.challenge_for("v" * 50)),
        ("code_challenge_method", "S256"),
        *pairs,
    ]
    if scope is not None:
        params.append(("scope", scope))
    return client.get("/foundation/oauth2/auth", params=params, follow_redirects=False)


def test_a_way_back_to_localhost_is_for_a_sign_in_to_the_mcp_endpoint_alone(tmp_path: Path) -> None:
    """F40 b: the MCP programs come back to localhost on a port of their own; no other sign-in goes there."""
    app = create_app(make_settings(tmp_path, mcp_enabled=True), startup_wait_seconds=0)
    app.dependency_overrides[get_clients] = LocalhostClients
    app.dependency_overrides[get_graph] = Graph
    with TestClient(app) as client:
        for_mcp = _localhost(client, ("resource", MCP), scope="mcp")
        for_rest = _localhost(client, scope="profile bcf")
        unscoped = _localhost(client)
    assert _signed(client, for_mcp)["resource"] == MCP, "the consent page, bound to the endpoint"
    for refused in (for_rest, unscoped):
        assert refused.status_code == 400 and "location" not in refused.headers, "nothing is sent to localhost"
        assert "only when it signs in to the server" in refused.text
