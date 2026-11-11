# This file was generated with the assistance of an AI coding tool.
"""Tokens bound to the MCP endpoint against a real database (RFC 8707, ADR 0028, F31 a).

The resource is recorded on the code and on the token family, a refresh keeps it, the REST APIs refuse the token,
and ``mcp_principal`` takes it and no other. A probe route stands in for the endpoint, which comes later.
"""

from __future__ import annotations

import asyncio
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient
from neo4j import GraphDatabase

from opencde.auth.scopes import MCP_PROPOSE
from opencde.bootstrap import make_graph
from opencde.deps import SettingsDep
from opencde.mcp.auth import McpPrincipal, require_mcp_scope
from opencde.settings import Settings
from opencde.store.accounts.users import UserRepository
from tests.integration.conftest_accounts import World, build_world, login_as
from tests.integration.helpers import FORM_TOKEN, Session, authorize, exchange

pytestmark = [pytest.mark.integration, pytest.mark.security]

MCP = "http://testserver/mcp"
METADATA = "http://testserver/.well-known/oauth-protected-resource/mcp"
AN_ID = "00000000-0000-4000-8000-000000000000"


@pytest.fixture
def settings(settings: Settings) -> Settings:
    """The integration settings with the MCP endpoint on."""
    return settings.model_copy(update={"mcp_enabled": True})


@pytest.fixture
def world(settings: Settings, clean_database: None) -> World:
    return build_world(settings)


@pytest.fixture
def probe(client: TestClient) -> TestClient:
    """Two routes as the MCP endpoint will have them, on the application with its database."""

    async def read(caller: McpPrincipal) -> dict[str, str]:
        return {"user": caller.username}

    async def propose(caller: McpPrincipal, settings: SettingsDep) -> dict[str, str]:
        require_mcp_scope(caller, MCP_PROPOSE, settings)
        return {"user": caller.username}

    client.app.add_api_route("/test/mcp-read", read, methods=["POST"])
    client.app.add_api_route("/test/mcp-propose", propose, methods=["POST"])
    return client


def _stored(settings: Settings, label: str) -> list[str | None]:
    password = settings.graph_password.get_secret_value()
    with GraphDatabase.driver(settings.graph_uri, auth=(settings.graph_user, password)) as driver:
        rows, _, _ = driver.execute_query(
            "MATCH (n) WHERE $label IN labels(n) RETURN n.resource AS resource ORDER BY n.created_at",
            label=label,
            database_=settings.database_name,
        )
    return [row["resource"] for row in rows]


def _mcp_sign_in(client: TestClient, world: World, scope: str = "mcp mcp:propose") -> Session:
    code, query, verifier = authorize(
        client,
        client_id=world.public_client_id,
        redirect_uri=world.redirect,
        username="editor",
        password=world.password,
        scope=scope,
        resource=MCP,
    )
    assert code, query
    return exchange(
        client,
        code=code,
        verifier=verifier,
        client_id=world.public_client_id,
        redirect_uri=world.redirect,
        resource=MCP,
    )


def _refresh(client: TestClient, world: World, session: Session, *resource: str):
    data = {"grant_type": "refresh_token", "refresh_token": session.refresh_token, "client_id": world.public_client_id}
    return client.post("/foundation/oauth2/token", data={**data, "resource": list(resource)} if resource else data)


def _refused_by_rest(client: TestClient, session: Session) -> None:
    for path in ("/foundation/1.0/current-user", "/bcf/3.0/projects", f"/documents/1.0/documents/{AN_ID}/versions"):
        response = client.get(path, headers=session.headers)
        assert response.status_code == 401 and response.json()["code"] == "invalid_token", path


def test_the_binding_is_kept_from_the_code_through_every_refresh(
    probe: TestClient, world: World, settings: Settings
) -> None:
    session = _mcp_sign_in(probe, world)
    assert session.scope == "mcp mcp:propose"
    assert _stored(settings, "AuthorizationCode") == [MCP]
    assert _stored(settings, "AccessToken") == [MCP] and _stored(settings, "RefreshToken") == [MCP]
    _refused_by_rest(probe, session)
    assert probe.post("/test/mcp-read", headers=session.headers).json() == {"user": "editor"}
    assert probe.post("/test/mcp-propose", headers=session.headers).json() == {"user": "editor"}

    elsewhere = _refresh(probe, world, session, "https://evil.example/mcp")
    assert elsewhere.status_code == 400 and elsewhere.json()["error"] == "invalid_target"
    rotated = _refresh(probe, world, session)  # the refused request spent nothing
    assert rotated.status_code == 201, rotated.text
    body = rotated.json()
    renewed = Session(body["access_token"], body["refresh_token"], body["scope"])
    assert renewed.scope == "mcp mcp:propose"
    assert set(_stored(settings, "RefreshToken")) == {MCP} and _stored(settings, "AccessToken") == [MCP]
    _refused_by_rest(probe, renewed)
    assert probe.post("/test/mcp-read", headers=renewed.headers).status_code == 200
    named = _refresh(probe, world, renewed, MCP)
    assert named.status_code == 201, "naming its own resource is fine"


def test_a_code_answers_only_for_its_own_resource(probe: TestClient, world: World) -> None:
    code, _, verifier = authorize(
        probe, client_id=world.public_client_id, redirect_uri=world.redirect, username="viewer", password=world.password
    )
    assert code
    request = {"grant_type": "authorization_code", "code": code, "code_verifier": verifier}
    moved = probe.post(
        "/foundation/oauth2/token", data={**request, "client_id": world.public_client_id, "resource": MCP}
    )
    assert moved.status_code == 400 and moved.json()["error"] == "invalid_target", (
        "a REST code is not for the MCP endpoint"
    )
    session = exchange(probe, code=code, verifier=verifier, client_id=world.public_client_id)  # still unspent
    assert probe.get("/foundation/1.0/current-user", headers=session.headers).status_code == 200
    refused = probe.post("/test/mcp-read", headers=session.headers)
    assert refused.status_code == 401 and refused.json()["code"] == "invalid_token", "and its token not for /mcp"
    assert (
        refused.headers["www-authenticate"]
        == f'Bearer error="invalid_token", resource_metadata="{METADATA}", scope="mcp"'
    )


def test_a_rest_token_works_as_before_and_reaches_no_mcp_tool(probe: TestClient, world: World) -> None:
    session = login_as(probe, world, "manager")
    assert session.scope == "profile bcf documents"
    assert probe.get("/bcf/3.0/projects", headers=session.headers).status_code == 200
    assert probe.post("/test/mcp-read", headers=session.headers).status_code == 401
    assert (
        probe.post("/test/mcp-read").headers["www-authenticate"]
        == f'Bearer resource_metadata="{METADATA}", scope="mcp"'
    )


def test_reading_only_is_a_consent_of_its_own_and_proposing_a_step_up(probe: TestClient, world: World) -> None:
    reader = _mcp_sign_in(probe, world, scope="mcp")
    assert probe.post("/test/mcp-read", headers=reader.headers).status_code == 200
    refused = probe.post("/test/mcp-propose", headers=reader.headers)
    assert refused.status_code == 403 and refused.json()["code"] == "insufficient_scope"
    assert 'scope="mcp mcp:propose"' in refused.headers["www-authenticate"]
    proposer = _mcp_sign_in(probe, world, scope="mcp mcp:propose")
    assert probe.post("/test/mcp-propose", headers=proposer.headers).status_code == 200


def test_the_scopes_and_the_resource_come_together(probe: TestClient, world: World) -> None:
    for scope, resource, error in (("mcp", None, "invalid_target"), ("profile bcf", MCP, "invalid_scope")):
        params = {
            "response_type": "code",
            "client_id": world.public_client_id,
            "redirect_uri": world.redirect,
            "state": "s1",
            "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
            "code_challenge_method": "S256",
            "scope": scope,
        }
        if resource:
            params["resource"] = resource
        response = probe.get("/foundation/oauth2/auth", params=params, follow_redirects=False)
        assert response.status_code == 302, response.text[:300]
        assert parse_qs(urlsplit(response.headers["location"]).query)["error"] == [error], scope


def test_a_sign_in_that_must_change_its_password_comes_back_with_the_resource(
    probe: TestClient, world: World, settings: Settings
) -> None:
    async def reset() -> None:
        graph = make_graph(settings)
        try:
            users = UserRepository(graph)
            user = await users.get_by_username("editor")
            assert user is not None
            await users.set_password(user.id, world.password, must_change=True)
        finally:
            await graph.close()

    asyncio.run(reset())
    params = {
        "response_type": "code",
        "client_id": world.public_client_id,
        "redirect_uri": world.redirect,
        "state": "s1",
        "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
        "code_challenge_method": "S256",
        "scope": "mcp",
        "resource": MCP,
    }
    page = probe.get("/foundation/oauth2/auth", params=params)
    token = FORM_TOKEN.search(page.text)
    assert token
    answer = probe.post(
        "/foundation/oauth2/auth",
        data={"form_token": token.group(1), "username": "editor", "password": world.password, "decision": "allow"},
        follow_redirects=False,
    )
    assert answer.status_code == 303
    again = parse_qs(urlsplit(parse_qs(urlsplit(answer.headers["location"]).query)["next"][0]).query)
    assert again["resource"] == [MCP] and again["scope"] == ["mcp"], "the flow starts over bound as it was asked"
