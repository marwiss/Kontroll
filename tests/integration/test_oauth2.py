# This file was generated with the assistance of an AI coding tool.
"""The OAuth2 authorization code flow end to end, against a real database."""

import time
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient
from neo4j import GraphDatabase

from opencde.auth import pkce
from opencde.settings import Settings
from opencde.timeutil import later_iso
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
    world = build_world(settings)
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

        # A public client (RFC 7591 token_endpoint_auth_method "none"): no secret, PKCE protects the flow.
        redirect = "http://127.0.0.1:8093/oauth-callback.html"
        public = client.post(
            "/foundation/oauth2/reg",
            json={
                "client_name": "Browser application",
                "redirect_uris": [redirect],
                "token_endpoint_auth_method": "none",
                "grant_types": ["authorization_code", "refresh_token"],
                "software_id": "dataspatium",
                "software_version": "2.33.0",
            },
        )
        assert public.status_code == 201, public.text
        registered = public.json()
        assert "client_secret" not in registered and registered["token_endpoint_auth_method"] == "none"
        assert registered["redirect_uris"] == [redirect] and isinstance(registered["client_id_issued_at"], int)
        # RFC 7591 software_id/software_version are stored and echoed, so the operator can tell apps apart.
        assert registered["software_id"] == "dataspatium" and registered["software_version"] == "2.33.0"
        assert "software_id" not in body, "absent when the client did not send it"

        # Self-registered clients expire when unused; a token issuance moves the expiry forward.
        def stored(client_id: str) -> dict[str, str | None]:
            with GraphDatabase.driver(graph_target.uri, auth=(graph_target.user, graph_target.password)) as driver:
                rows, _, _ = driver.execute_query(
                    "MATCH (c:Client {client_id: $id}) "
                    "RETURN c.expires_at AS e, c.software_id AS sid, c.software_version AS sv",
                    id=client_id,
                    database_=settings.database_name,
                )
                return dict(rows[0])

        def expiry(client_id: str) -> str:
            return stored(client_id)["e"] or ""

        assert stored(registered["client_id"])["sid"] == "dataspatium"
        assert stored(registered["client_id"])["sv"] == "2.33.0"
        before = expiry(registered["client_id"])
        assert before > later_iso(29 * 86400), "about 30 days (OPENCDE_DYNAMIC_CLIENT_UNUSED_DAYS)"
        time.sleep(0.01)
        code, _query, verifier = authorize(
            client, client_id=registered["client_id"], redirect_uri=redirect, username="editor", password=world.password
        )
        assert code is not None
        session = exchange(
            client, code=code, verifier=verifier, client_id=registered["client_id"], redirect_uri=redirect
        )
        assert client.get("/foundation/1.0/current-user", headers=session.headers).json()["id"] == "editor"
        assert expiry(registered["client_id"]) > before, "the exchange touched the registration"
        for invalid in ({"grant_types": ["implicit"]}, {"token_endpoint_auth_method": "private_key_jwt"}):
            rejected = client.post(
                "/foundation/oauth2/reg", json={"client_name": "x", "redirect_uris": [redirect], **invalid}
            )
            assert rejected.status_code == 400, rejected.text


def test_registration_is_404_when_disabled(client: TestClient, world: World) -> None:
    response = client.post("/foundation/oauth2/reg", json={"client_name": "x", "redirect_url": "https://a.test/cb"})
    assert response.status_code == 404


def test_pkce_challenge_round_trip_helper() -> None:
    verifier = "a" * 43
    assert pkce.verify(verifier, pkce.challenge_for(verifier))
    assert urlsplit("http://127.0.0.1/callback?code=1").query and parse_qs("a=1") == {"a": ["1"]}
