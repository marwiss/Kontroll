# This file was generated with the assistance of an AI coding tool.
"""Penetration-style checks of the authorization server (RFC 9700, OAuth 2.1)."""

import logging
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from opencde.auth import pkce
from opencde.settings import Settings
from tests.integration.conftest_accounts import World, build_world
from tests.integration.helpers import FORM_TOKEN, authorize, basic_auth, exchange

pytestmark = [pytest.mark.integration, pytest.mark.security]


@pytest.fixture
def world(settings: Settings, clean_database: None) -> World:
    return build_world(settings)


def _authorize_params(world: World, **overrides: str) -> dict[str, str]:
    params = {
        "response_type": "code",
        "client_id": world.public_client_id,
        "redirect_uri": world.redirect,
        "state": "s1",
        "code_challenge": pkce.challenge_for("v" * 50),
        "code_challenge_method": "S256",
    }
    params.update(overrides)
    return params


def _redirect_query(response) -> dict[str, list[str]]:
    assert response.status_code == 302
    return parse_qs(urlsplit(response.headers["location"]).query)


def test_unregistered_redirect_uri_is_shown_not_followed(client: TestClient, world: World) -> None:
    for evil in ("https://evil.test/callback", "http://127.0.0.1/callback/../evil", "http://127.0.0.1/other2"):
        response = client.get("/foundation/oauth2/auth", params=_authorize_params(world, redirect_uri=evil))
        assert response.status_code == 400 and "location" not in response.headers, evil
        assert "not registered" in response.text


def test_loopback_port_may_vary_but_host_may_not(client: TestClient, world: World) -> None:
    ok = client.get(
        "/foundation/oauth2/auth", params=_authorize_params(world, redirect_uri="http://127.0.0.1:53421/callback")
    )
    assert ok.status_code == 200
    bad = client.get(
        "/foundation/oauth2/auth", params=_authorize_params(world, redirect_uri="http://localhost:53421/callback")
    )
    assert bad.status_code == 400


def test_pkce_is_mandatory_and_plain_is_refused(client: TestClient, world: World) -> None:
    missing = _authorize_params(world)
    del missing["code_challenge"]
    query = _redirect_query(client.get("/foundation/oauth2/auth", params=missing, follow_redirects=False))
    assert query["error"] == ["invalid_request"] and "S256" in query["error_description"][0]
    plain = _redirect_query(
        client.get(
            "/foundation/oauth2/auth",
            params=_authorize_params(world, code_challenge="v" * 50, code_challenge_method="plain"),
            follow_redirects=False,
        )
    )
    assert plain["error"] == ["invalid_request"]


def test_state_is_required_and_unknown_scope_is_refused(client: TestClient, world: World) -> None:
    params = _authorize_params(world)
    del params["state"]
    assert _redirect_query(client.get("/foundation/oauth2/auth", params=params, follow_redirects=False))["error"] == [
        "invalid_request"
    ]
    query = _redirect_query(
        client.get(
            "/foundation/oauth2/auth", params=_authorize_params(world, scope="superuser"), follow_redirects=False
        )
    )
    assert query["error"] == ["invalid_scope"] and query["state"] == ["s1"]
    query = _redirect_query(
        client.get(
            "/foundation/oauth2/auth", params=_authorize_params(world, response_type="token"), follow_redirects=False
        )
    )
    assert query["error"] == ["unsupported_response_type"]


def test_wrong_verifier_wrong_client_and_wrong_redirect_are_invalid_grant(client: TestClient, world: World) -> None:
    code, _, verifier = authorize(
        client,
        client_id=world.public_client_id,
        redirect_uri=world.redirect,
        username="viewer",
        password=world.password,
    )
    bad_verifier = client.post(
        "/foundation/oauth2/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": "w" * 50,
            "client_id": world.public_client_id,
        },
    )
    assert bad_verifier.status_code == 400 and bad_verifier.json()["error"] == "invalid_grant"
    other_client = client.post(
        "/foundation/oauth2/token",
        data={"grant_type": "authorization_code", "code": code, "code_verifier": verifier},
        headers=basic_auth(world.confidential_client_id, world.confidential_secret),
    )
    assert other_client.status_code == 400 and other_client.json()["error"] == "invalid_grant"
    wrong_redirect = client.post(
        "/foundation/oauth2/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": verifier,
            "client_id": world.public_client_id,
            "redirect_uri": "http://127.0.0.1/other",
        },
    )
    assert wrong_redirect.status_code == 400
    # The code itself is still valid after mismatches that do not prove a leak.
    assert exchange(client, code=code, verifier=verifier, client_id=world.public_client_id).access_token


def test_client_authentication_failures(client: TestClient, world: World) -> None:
    wrong_secret = client.post(
        "/foundation/oauth2/token",
        data={"grant_type": "refresh_token", "refresh_token": "x"},
        headers=basic_auth(world.confidential_client_id, "wrong"),
    )
    assert wrong_secret.status_code == 401 and wrong_secret.json()["error"] == "invalid_client"
    assert wrong_secret.headers["www-authenticate"].startswith("Basic")
    no_auth = client.post("/foundation/oauth2/token", data={"grant_type": "refresh_token", "refresh_token": "x"})
    assert no_auth.status_code == 401
    public_with_secret = client.post(
        "/foundation/oauth2/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": "x",
            "client_id": world.public_client_id,
            "client_secret": "anything",
        },
    )
    assert public_with_secret.status_code == 401, "a public client never has a secret; presenting one is suspicious"
    unsupported = client.post(
        "/foundation/oauth2/token",
        data={"grant_type": "password", "username": "a", "password": "b", "client_id": world.public_client_id},
    )
    assert unsupported.status_code == 400 and unsupported.json()["error"] == "unsupported_grant_type"


def test_tampered_or_replayed_form_token_is_refused(client: TestClient, world: World) -> None:
    page = client.get("/foundation/oauth2/auth", params=_authorize_params(world))
    token = FORM_TOKEN.search(page.text).group(1)  # type: ignore[union-attr]
    tampered = client.post(
        "/foundation/oauth2/auth",
        data={"form_token": token[:-4] + "aaaa", "username": "viewer", "password": world.password, "decision": "allow"},
        follow_redirects=False,
    )
    assert tampered.status_code == 400 and "location" not in tampered.headers
    missing = client.post(
        "/foundation/oauth2/auth", data={"username": "viewer", "password": world.password}, follow_redirects=False
    )
    assert missing.status_code == 400


def test_passwords_and_codes_never_reach_the_logs(
    client: TestClient, world: World, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    secret_password = world.password
    code, _, verifier = authorize(
        client,
        client_id=world.public_client_id,
        redirect_uri=world.redirect,
        username="viewer",
        password=secret_password,
    )
    session = exchange(client, code=code, verifier=verifier, client_id=world.public_client_id)
    text = caplog.text
    assert secret_password not in text
    assert code not in text and verifier not in text
    assert session.access_token not in text and session.refresh_token not in text


def test_disabled_user_cannot_sign_in_and_loses_tokens(
    client: TestClient, world: World, graph_target, settings: Settings
) -> None:
    import asyncio

    from opencde.accounts.users import UserRepository
    from opencde.bootstrap import make_graph

    code, _, verifier = authorize(
        client,
        client_id=world.public_client_id,
        redirect_uri=world.redirect,
        username="viewer",
        password=world.password,
    )
    session = exchange(client, code=code, verifier=verifier, client_id=world.public_client_id)

    async def disable() -> None:
        graph = make_graph(settings)
        try:
            await UserRepository(graph).update(world.users["viewer"], disabled=True)
        finally:
            await graph.close()

    asyncio.run(disable())
    assert client.get("/foundation/1.0/current-user", headers=session.headers).status_code == 401
    code2, query, _ = authorize(
        client,
        client_id=world.public_client_id,
        redirect_uri=world.redirect,
        username="viewer",
        password=world.password,
    )
    assert code2 is None and query == {}


def test_sign_in_is_rate_limited(graph_target, tmp_path, clean_database: None) -> None:
    from opencde.main import create_app
    from tests.conftest import test_settings

    settings = test_settings(
        tmp_path,
        graph_dialect=graph_target.dialect,
        graph_uri=graph_target.uri,
        graph_user=graph_target.user,
        graph_password=graph_target.password,
        graph_connect_timeout_seconds=10.0,
        rate_limits_enabled=True,
    )
    world = build_world(settings)
    with TestClient(create_app(settings, startup_wait_seconds=30)) as client:
        statuses = []
        for _ in range(12):
            page = client.get("/foundation/oauth2/auth", params=_authorize_params(world))
            token = FORM_TOKEN.search(page.text).group(1)  # type: ignore[union-attr]
            response = client.post(
                "/foundation/oauth2/auth",
                data={"form_token": token, "username": "viewer", "password": "wrong-password-123", "decision": "allow"},
                follow_redirects=False,
            )
            statuses.append(response.status_code)
        assert 429 in statuses, statuses
        assert statuses.index(429) <= 10
