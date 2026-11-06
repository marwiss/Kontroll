# This file was generated with the assistance of an AI coding tool.
"""A growing wait after failed sign-ins, per user name, on both sign-in forms."""

from __future__ import annotations

import re
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from neo4j import GraphDatabase

from opencde.auth import pkce
from opencde.auth.throttle import delay_after
from opencde.main import create_app
from opencde.settings import Settings
from tests.conftest import test_settings as settings_for_tests
from tests.integration.conftest_accounts import World, build_world

pytestmark = [pytest.mark.integration, pytest.mark.security]

FORM_TOKEN = re.compile(r'name="form_token" value="([^"]+)"')


@pytest.fixture
def world(settings: Settings, clean_database: None) -> World:
    return build_world(settings)


@pytest.fixture
def throttled(settings: Settings, clean_database: None) -> Iterator[TestClient]:
    """The application with the wait on, which the other tests leave off."""
    on = settings.model_copy(update={"sign_in_throttle_enabled": True, "sign_in_free_attempts": 3})
    with TestClient(create_app(on, startup_wait_seconds=30)) as client:
        yield client


def _sign_in(client: TestClient, username: str, password: str):
    client.cookies.clear()  # a browser that is already signed in does not get the form
    page = client.get("/signin")
    token = FORM_TOKEN.search(page.text)
    assert token
    data = {"form_token": token.group(1), "username": username, "password": password}
    return client.post("/signin", data=data, follow_redirects=False)


def _rewind(settings: Settings) -> None:
    """As if the wait had passed."""
    with GraphDatabase.driver(
        settings.graph_uri, auth=(settings.graph_user, settings.graph_password.get_secret_value())
    ) as driver:
        driver.execute_query(
            "MATCH (t:SignInThrottle) SET t.blocked_until = '2000-01-01T00:00:00.000Z'",
            database_=settings.database_name,
        )


def _count(settings: Settings, query: str) -> int:
    with GraphDatabase.driver(
        settings.graph_uri, auth=(settings.graph_user, settings.graph_password.get_secret_value())
    ) as driver:
        records, _, _ = driver.execute_query(query, database_=settings.database_name)
    return records[0]["n"]


def test_the_wait_doubles_from_the_first_delay_up_to_the_ceiling() -> None:
    settings = settings_for_tests(sign_in_free_attempts=5, sign_in_delay_seconds=30, sign_in_max_delay_seconds=900)
    assert [delay_after(n, settings) for n in (1, 4, 5, 6, 7, 8, 9, 10, 50, 10_000)] == [
        0,
        0,
        30,
        60,
        120,
        240,
        480,
        900,
        900,
        900,
    ]


def test_the_right_password_waits_too_and_works_afterwards(
    throttled: TestClient, world: World, settings: Settings
) -> None:
    for _ in range(3):
        assert _sign_in(throttled, "editor", "wrong-password").status_code == 200
    refused = _sign_in(throttled, "editor", world.password)
    assert refused.status_code == 429
    assert "Too many failed attempts" in refused.text and "seconds" in refused.text

    _rewind(settings)
    assert _sign_in(throttled, "editor", world.password).status_code == 302, "the wait has passed"
    assert _count(settings, "MATCH (t:SignInThrottle) RETURN count(t) AS n") == 0, "a success clears the count"


def test_a_success_starts_the_count_over(throttled: TestClient, world: World) -> None:
    for _ in range(2):
        _sign_in(throttled, "editor", "wrong-password")
    assert _sign_in(throttled, "editor", world.password).status_code == 302
    for _ in range(2):
        assert _sign_in(throttled, "editor", "wrong-password").status_code == 200
    assert _sign_in(throttled, "editor", world.password).status_code == 302


def test_an_unknown_name_is_treated_like_a_known_one(throttled: TestClient, world: World, settings: Settings) -> None:
    for _ in range(3):
        assert _sign_in(throttled, "nobody-at-all", "wrong-password").status_code == 200
    assert _sign_in(throttled, "nobody-at-all", "wrong-password").status_code == 429
    keys = _count(settings, "MATCH (t:SignInThrottle) WHERE t.key CONTAINS 'nobody' RETURN count(t) AS n")
    assert keys == 0, "the name is stored as a hash"


def test_the_wait_belongs_to_the_name_not_to_everyone(throttled: TestClient, world: World) -> None:
    for _ in range(3):
        _sign_in(throttled, "editor", "wrong-password")
    assert _sign_in(throttled, "editor", world.password).status_code == 429
    assert _sign_in(throttled, "manager", world.password).status_code == 302
    assert _sign_in(throttled, "  EDITOR ", world.password).status_code == 429, "spelling does not get around it"


def test_the_page_a_client_opens_waits_as_well(throttled: TestClient, world: World) -> None:
    params = {
        "response_type": "code",
        "client_id": world.public_client_id,
        "redirect_uri": world.redirect,
        "state": "s1",
        "code_challenge": pkce.challenge_for("v" * 50),
        "code_challenge_method": "S256",
    }
    page = throttled.get("/foundation/oauth2/auth", params=params)
    for _ in range(3):
        token = FORM_TOKEN.search(page.text)
        assert token
        data = {"form_token": token.group(1), "username": "editor", "password": "wrong-password"}
        page = throttled.post("/foundation/oauth2/auth", data=data, follow_redirects=False)
        assert page.status_code == 200
    token = FORM_TOKEN.search(page.text)
    assert token
    data = {"form_token": token.group(1), "username": "editor", "password": world.password}
    refused = throttled.post("/foundation/oauth2/auth", data=data, follow_redirects=False)
    assert refused.status_code == 429 and "location" not in refused.headers
    assert "Too many failed attempts" in refused.text


def test_every_attempt_that_waits_leaves_an_audit_event(
    throttled: TestClient, world: World, settings: Settings
) -> None:
    for _ in range(4):
        _sign_in(throttled, "editor", "wrong-password")
    query = "MATCH (e:AuditEvent {type: 'web.sign_in.throttled'}) RETURN count(e) AS n"
    assert _count(settings, query) == 1
