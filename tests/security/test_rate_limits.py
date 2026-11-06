# This file was generated with the assistance of an AI coding tool.
"""The limit per address on every request, the tighter one on the administration, and the store behind them."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from limits.errors import ConfigurationError
from pydantic import ValidationError

from opencde import ratelimit
from opencde.main import create_app
from opencde.ratelimit import limiter, registration_limit
from tests.conftest import test_settings as settings_for_tests

pytestmark = pytest.mark.security

API = "/foundation/versions"


@pytest.fixture
def limited(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setattr(ratelimit, "RATE_ADMIN", "2/minute")
    settings = settings_for_tests(tmp_path, rate_limits_enabled=True, rate_limit_api="4/minute")
    with TestClient(create_app(settings, startup_wait_seconds=0)) as client:
        yield client


def _statuses(client: TestClient, path: str, count: int) -> list[int]:
    return [client.get(path, follow_redirects=False).status_code for _ in range(count)]


def test_the_api_has_a_limit_and_answers_with_the_error_body(limited: TestClient) -> None:
    assert _statuses(limited, API, 4) == [200] * 4
    refused = limited.get(API)
    assert refused.status_code == 429
    assert refused.json()["code"] == "rate_limited"
    assert refused.headers["retry-after"] == "60"
    assert refused.headers["x-content-type-options"] == "nosniff", "the security headers apply"


def test_the_administration_has_a_tighter_limit_of_its_own(limited: TestClient) -> None:
    assert _statuses(limited, "/admin", 3) == [302, 302, 429]
    assert limited.get(API).status_code == 200, "the two are counted apart"


def test_health_checks_and_static_files_are_exempt(limited: TestClient) -> None:
    assert set(_statuses(limited, "/healthz", 8)) == {200}
    assert set(_statuses(limited, "/static/icon.svg", 8)) == {200}


def test_nothing_is_limited_when_limits_are_off(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = settings_for_tests(tmp_path, rate_limits_enabled=False, rate_limit_api="1/minute")
    with TestClient(create_app(settings, startup_wait_seconds=0)) as client:
        assert _statuses(client, API, 5) == [200] * 5


def test_a_new_application_starts_with_its_own_counts(limited: TestClient, tmp_path: Path) -> None:
    assert _statuses(limited, API, 5)[-1] == 429
    settings = settings_for_tests(tmp_path, rate_limits_enabled=True, rate_limit_api="4/minute")
    with TestClient(create_app(settings, startup_wait_seconds=0)) as client:
        assert client.get(API).status_code == 200


def test_a_failing_store_stops_nothing(limited: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(*_args: object, **_kwargs: object) -> int:
        raise ConnectionError("the store is gone")

    for method in ("incr", "get", "get_expiry"):
        monkeypatch.setattr(limiter._storage, method, broken)
    assert _statuses(limited, API, 8) == [200] * 8
    # A route with a limit of its own also writes the state of that limit into its answer.
    expired = limited.post("/signin", data={"form_token": "old", "username": "a", "password": "b"})
    assert expired.status_code == 400 and "x-ratelimit-limit" in expired.headers


def test_the_limit_on_signing_in_is_a_setting(tmp_path: Path) -> None:
    settings = settings_for_tests(tmp_path, rate_limits_enabled=True, rate_limit_sign_in="2/minute")
    form = {"form_token": "old", "username": "a", "password": "b"}
    with TestClient(create_app(settings, startup_wait_seconds=0)) as client:
        assert [client.post("/signin", data=form).status_code for _ in range(3)] == [400, 400, 429]


def test_a_server_people_try_out_lets_them_register_more_often(tmp_path: Path) -> None:
    create_app(settings_for_tests(tmp_path, environment="development"))
    assert registration_limit() == ratelimit.RATE_REGISTRATION_DEVELOPMENT
    create_app(
        settings_for_tests(
            tmp_path, environment="production", public_url="https://cde.example.org", graph_password="x" * 20
        )
    )
    assert registration_limit() == ratelimit.RATE_REGISTRATION


def test_an_address_of_a_store_that_cannot_work_stops_the_start_without_being_repeated(tmp_path: Path) -> None:
    with pytest.raises(ValidationError) as refused:
        settings_for_tests(tmp_path, rate_limit_storage="redsi://:a-password@redis:6379/0")
    assert "OPENCDE_RATE_LIMIT_STORAGE" in str(refused.value) and "a-password" not in str(refused.value)


def test_a_redis_address_without_the_extra_stops_the_start(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(uri: str, **_options: object) -> None:
        raise ConfigurationError(f"prerequisites not available for {uri}")

    monkeypatch.setattr(ratelimit, "storage_from_string", missing)
    settings = settings_for_tests(tmp_path, rate_limit_storage="redis://:a-password@redis:6379/0")
    with pytest.raises(RuntimeError, match="redis extra") as refused:
        create_app(settings)
    assert "a-password" not in str(refused.value)


def test_the_store_address_is_not_shown_with_the_settings(tmp_path: Path) -> None:
    settings = settings_for_tests(tmp_path, rate_limit_storage="redis://:a-password@redis:6379/0")
    assert "a-password" not in repr(settings)


@pytest.mark.parametrize("value", ["", "many", "600", "600 per fortnight"])
def test_a_limit_that_cannot_be_read_stops_the_start(tmp_path: Path, value: str) -> None:
    with pytest.raises(ValidationError, match="OPENCDE_RATE_LIMIT_API"):
        settings_for_tests(tmp_path, rate_limit_api=value)
    with pytest.raises(ValidationError, match="OPENCDE_RATE_LIMIT_SIGN_IN"):
        settings_for_tests(tmp_path, rate_limit_sign_in=value)
