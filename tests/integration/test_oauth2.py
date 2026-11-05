# This file was generated with the assistance of an AI coding tool.
"""The OAuth2 authorization code flow end to end, against a real database."""

from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from opencde.auth import pkce
from opencde.settings import Settings
from tests.conformance.schemas import validate
from tests.integration.conftest_accounts import World, build_world
from tests.integration.helpers import authorize, basic_auth, exchange, sign_in

pytestmark = pytest.mark.integration


@pytest.fixture
def world(settings: Settings, clean_database: None) -> World:
    return build_world(settings)


def test_public_client_flow_with_pkce(client: TestClient, world: World) -> None:
    code, query, verifier = authorize(
        client,
        client_id=world.public_client_id,
        redirect_uri=world.redirect,
        username="editor",
        password=world.password,
    )
    assert code and query["state"] == ["state-123"]
    assert query["iss"] == ["http://testserver"], "RFC 9207 issuer identifier"

    session = exchange(
        client, code=code, verifier=verifier, client_id=world.public_client_id, redirect_uri=world.redirect
    )
    assert session.scope == "profile bcf documents"

    me = client.get("/foundation/1.0/current-user", headers=session.headers)
    assert me.status_code == 200
    validate(me.json(), "foundation-api/schemas/user_GET.json")
    assert me.json() == {"id": "editor", "name": "Editor"}
    assert client.get("/bcf/3.0/current-user", headers=session.headers).json()["id"] == "editor"


def test_confidential_client_flow_with_basic_auth_and_scopes(client: TestClient, world: World) -> None:
    session = sign_in(
        client,
        client_id=world.confidential_client_id,
        client_secret=world.confidential_secret,
        redirect_uri=world.redirect,
        username="manager",
        password=world.password,
        scope="bcf",
    )
    assert session.scope == "bcf"
    assert client.get("/foundation/1.0/current-user", headers=session.headers).status_code == 200


def test_token_response_is_never_cached_and_has_spec_fields(client: TestClient, world: World) -> None:
    code, _, verifier = authorize(
        client,
        client_id=world.public_client_id,
        redirect_uri=world.redirect,
        username="viewer",
        password=world.password,
    )
    response = client.post(
        "/foundation/oauth2/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": verifier,
            "client_id": world.public_client_id,
        },
    )
    assert response.status_code == 201
    assert response.headers["cache-control"] == "no-store" and response.headers["pragma"] == "no-cache"
    body = response.json()
    assert set(body) == {"access_token", "token_type", "expires_in", "refresh_token", "scope"}
    assert body["token_type"] == "bearer" and body["expires_in"] == 3600


def test_refresh_rotates_and_reuse_revokes_the_family(client: TestClient, world: World) -> None:
    session = sign_in(
        client,
        client_id=world.public_client_id,
        redirect_uri=world.redirect,
        username="viewer",
        password=world.password,
    )
    first = client.post(
        "/foundation/oauth2/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": session.refresh_token,
            "client_id": world.public_client_id,
        },
    )
    assert first.status_code == 201
    rotated = first.json()
    assert rotated["refresh_token"] != session.refresh_token
    assert client.get("/foundation/1.0/current-user", headers=session.headers).status_code == 401, (
        "old access token gone"
    )
    assert (
        client.get(
            "/foundation/1.0/current-user", headers={"Authorization": f"Bearer {rotated['access_token']}"}
        ).status_code
        == 200
    )

    replay = client.post(
        "/foundation/oauth2/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": session.refresh_token,
            "client_id": world.public_client_id,
        },
    )
    assert replay.status_code == 400 and replay.json()["error"] == "invalid_grant"
    assert (
        client.get(
            "/foundation/1.0/current-user", headers={"Authorization": f"Bearer {rotated['access_token']}"}
        ).status_code
        == 401
    ), "reuse of a spent refresh token revokes the whole family"


def test_code_is_single_use_and_replay_revokes_tokens(client: TestClient, world: World) -> None:
    code, _, verifier = authorize(
        client,
        client_id=world.public_client_id,
        redirect_uri=world.redirect,
        username="viewer",
        password=world.password,
    )
    session = exchange(client, code=code, verifier=verifier, client_id=world.public_client_id)
    assert client.get("/foundation/1.0/current-user", headers=session.headers).status_code == 200
    again = client.post(
        "/foundation/oauth2/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": verifier,
            "client_id": world.public_client_id,
        },
    )
    assert again.status_code == 400 and again.json()["error"] == "invalid_grant"
    assert client.get("/foundation/1.0/current-user", headers=session.headers).status_code == 401


def test_revocation(client: TestClient, world: World) -> None:
    session = sign_in(
        client,
        client_id=world.public_client_id,
        redirect_uri=world.redirect,
        username="viewer",
        password=world.password,
    )
    response = client.post(
        "/foundation/oauth2/revoke", data={"token": session.refresh_token, "client_id": world.public_client_id}
    )
    assert response.status_code == 200
    assert client.get("/foundation/1.0/current-user", headers=session.headers).status_code == 401
    unknown = client.post("/foundation/oauth2/revoke", data={"token": "nope", "client_id": world.public_client_id})
    assert unknown.status_code == 200, "RFC 7009: unknown tokens are not an error"
    assert client.post("/foundation/oauth2/revoke", data={"token": "x", "client_id": "nope"}).status_code == 401


def test_deny_redirects_with_access_denied(client: TestClient, world: World) -> None:
    code, query, _ = authorize(
        client, client_id=world.public_client_id, redirect_uri=world.redirect, username="", password="", decision="deny"
    )
    assert code is None and query["error"] == ["access_denied"] and query["state"] == ["state-123"]


def test_wrong_password_shows_the_form_again_without_redirect(client: TestClient, world: World) -> None:
    code, query, _ = authorize(
        client,
        client_id=world.public_client_id,
        redirect_uri=world.redirect,
        username="viewer",
        password="wrong-password-123",
    )
    assert code is None and query == {}


def test_dynamic_registration_when_enabled(graph_target, tmp_path, clean_database: None) -> None:
    from opencde.main import create_app
    from tests.conftest import test_settings

    settings = test_settings(
        tmp_path,
        graph_dialect=graph_target.dialect,
        graph_uri=graph_target.uri,
        graph_user=graph_target.user,
        graph_password=graph_target.password,
        graph_connect_timeout_seconds=10.0,
        dynamic_client_registration=True,
    )
    with TestClient(create_app(settings, startup_wait_seconds=30)) as client:
        assert (
            client.get("/foundation/1.0/auth")
            .json()["oauth2_dynamic_client_reg_url"]
            .endswith("/foundation/oauth2/reg")
        )
        response = client.post(
            "/foundation/oauth2/reg",
            json={
                "client_name": "Example Application",
                "client_description": "Example CAD desktop application",
                "client_url": "http://example.com",
                "redirect_url": "http://127.0.0.1:8080/callback",
            },
        )
        assert response.status_code == 201, response.text
        body = response.json()
        validate(body, "foundation-api/schemas/dynRegClient_GET.json")
        bad = client.post("/foundation/oauth2/reg", json={"client_name": "x", "redirect_url": "http://example.com/cb"})
        assert bad.status_code == 400
        # The new client works for a token request.
        probe = client.post(
            "/foundation/oauth2/token",
            data={"grant_type": "refresh_token", "refresh_token": "x"},
            headers=basic_auth(body["client_id"], body["client_secret"]),
        )
        assert probe.status_code == 400 and probe.json()["error"] == "invalid_grant"


def test_registration_is_404_when_disabled(client: TestClient, world: World) -> None:
    response = client.post("/foundation/oauth2/reg", json={"client_name": "x", "redirect_url": "https://a.test/cb"})
    assert response.status_code == 404


def test_pkce_challenge_round_trip_helper() -> None:
    verifier = "a" * 43
    assert pkce.verify(verifier, pkce.challenge_for(verifier))
    assert urlsplit("http://127.0.0.1/callback?code=1").query and parse_qs("a=1") == {"a": ["1"]}
