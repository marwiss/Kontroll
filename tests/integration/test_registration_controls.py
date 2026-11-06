# This file was generated with the assistance of an AI coding tool.
"""The two optional controls on dynamic client registration: an initial access token, and approval."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from opencde import ratelimit
from opencde.auth import pkce
from opencde.main import create_app
from opencde.settings import Settings
from tests.integration.conftest_accounts import World, build_world
from tests.integration.test_admin_ui import notice_of, post
from tests.integration.test_web_signin import web_sign_in

pytestmark = [pytest.mark.integration, pytest.mark.security]

BODY = {
    "client_name": "A viewer",
    "redirect_uris": ["http://127.0.0.1:8093/callback"],
    "token_endpoint_auth_method": "none",
}


def _client_for(settings: Settings, **overrides: object) -> TestClient:
    return TestClient(create_app(settings.model_copy(update=overrides), startup_wait_seconds=30))


@pytest.fixture
def world(settings: Settings, clean_database: None) -> World:
    return build_world(settings)


@pytest.fixture
def with_token(settings: Settings, world: World) -> Iterator[TestClient]:
    from pydantic import SecretStr

    updates = {
        "dynamic_client_registration": True,
        "dynamic_client_registration_token": SecretStr("an-invitation-to-register"),
    }
    with _client_for(settings, **updates) as client:
        yield client


@pytest.fixture
def with_approval(settings: Settings, world: World) -> Iterator[TestClient]:
    with _client_for(settings, dynamic_client_registration=True, dynamic_client_approval=True) as client:
        yield client


def _authorize(client: TestClient, client_id: str, redirect_uri: str = BODY["redirect_uris"][0]):
    return client.get(
        "/foundation/oauth2/auth",
        params={
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "state": "s1",
            "code_challenge": pkce.challenge_for("v" * 50),
            "code_challenge_method": "S256",
        },
    )


def test_registering_takes_the_token_when_one_is_set(with_token: TestClient) -> None:
    url = "/foundation/oauth2/reg"
    nothing = with_token.post(url, json=BODY)
    assert nothing.status_code == 401 and nothing.json()["code"] == "unauthenticated"
    assert nothing.headers["www-authenticate"].startswith("Bearer")
    wrong = with_token.post(url, json=BODY, headers={"Authorization": "Bearer something-else"})
    assert wrong.status_code == 401
    right = with_token.post(url, json=BODY, headers={"Authorization": "Bearer an-invitation-to-register"})
    assert right.status_code == 201


def test_the_capabilities_say_what_it_takes_to_register(with_token: TestClient, settings: Settings) -> None:
    found = with_token.get("/.well-known/kontroll").json()["extensions"]["dynamic_client_registration"]
    assert found["initial_access_token"] is True and found["approval"] is False
    assert "an-invitation-to-register" not in str(found), "the value itself is a secret"


def test_the_registration_limit_follows_the_environment(
    settings: Settings, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ratelimit, "RATE_REGISTRATION_DEVELOPMENT", "2/hour")
    with _client_for(settings, dynamic_client_registration=True, rate_limits_enabled=True) as client:
        statuses = [client.post("/foundation/oauth2/reg", json=BODY).status_code for _ in range(3)]
    assert statuses == [201, 201, 429]


def test_a_client_waits_for_approval_and_then_works(with_approval: TestClient, world: World) -> None:
    client_id = with_approval.post("/foundation/oauth2/reg", json=BODY).json()["client_id"]

    refused = _authorize(with_approval, client_id)
    assert refused.status_code == 400 and "has not approved" in refused.text, "the page says why"

    web_sign_in(with_approval, world, "admin")
    listing = with_approval.get("/admin/clients").text
    assert "Waiting for approval" in listing
    page = with_approval.get(f"/admin/clients/{client_id}")
    assert "Waiting for approval" in page.text
    assert notice_of(post(with_approval, f"/admin/clients/{client_id}", page.text, action="approve")) == "approved"

    assert _authorize(with_approval, client_id).status_code == 200
    again = with_approval.get(f"/admin/clients/{client_id}").text
    assert "Waiting for approval" not in again


def test_a_client_an_administrator_made_needs_no_approval(with_approval: TestClient, world: World) -> None:
    assert _authorize(with_approval, world.public_client_id, world.redirect).status_code == 200


def test_a_non_administrator_cannot_approve(with_approval: TestClient, world: World) -> None:
    client_id = with_approval.post("/foundation/oauth2/reg", json=BODY).json()["client_id"]
    web_sign_in(with_approval, world, "viewer")
    answer = with_approval.post(f"/admin/clients/{client_id}", data={"action": "approve"}, follow_redirects=False)
    assert answer.status_code == 404
    assert _authorize(with_approval, client_id).status_code == 400
