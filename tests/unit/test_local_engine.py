# This file was generated with the assistance of an AI coding tool.
"""The local engine (ADR 0023): it answers only on the loopback, and a public page may reach it through Private
Network Access only through the preflight it asks with."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from opencde.main import create_app
from tests.conftest import test_settings as make_settings  # aliased so pytest does not collect it as a test


@pytest.fixture
def local(tmp_path: Path) -> TestClient:
    settings = make_settings(
        tmp_path,
        environment="local",
        public_url="http://127.0.0.1:8000",
        cors_origins=["null", "https://marwiss.github.io"],
        graph_connect_timeout_seconds=0.5,
    )
    return TestClient(create_app(settings, startup_wait_seconds=0), base_url="http://127.0.0.1:8000")


def test_a_request_addressed_to_another_name_is_refused(local: TestClient) -> None:
    for host in ("127.0.0.1:8000", "localhost:8000", "127.0.0.1", "[::1]:8000", "LOCALHOST"):
        assert local.get("/healthz", headers={"Host": host}).status_code == 200, host
    for host in ("engine.example", "engine.example:8000", "127.0.0.1.evil.example", "", "10.0.0.5:8000"):
        rebinding = local.get("/healthz", headers={"Host": host})
        assert rebinding.status_code == 421, host
        assert rebinding.json()["message"] == "This server answers only on the loopback"
    assert local.get("/.well-known/dataregium", headers={"Host": "evil.example"}).status_code == 421, "every path"


def test_a_public_page_is_allowed_through_the_preflight_it_asks_with(local: TestClient) -> None:
    preflight = local.options(
        "/foundation/versions",
        headers={
            "Origin": "https://marwiss.github.io",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Private-Network": "true",
        },
    )
    assert preflight.status_code == 200, preflight.text
    assert preflight.headers["access-control-allow-private-network"] == "true"
    assert preflight.headers["access-control-allow-origin"] == "https://marwiss.github.io"
    plain = local.options(
        "/foundation/versions", headers={"Origin": "https://marwiss.github.io", "Access-Control-Request-Method": "GET"}
    )
    assert "access-control-allow-private-network" not in plain.headers, "only when asked"
    stranger = local.options(
        "/foundation/versions",
        headers={
            "Origin": "https://stranger.example",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Private-Network": "true",
        },
    )
    assert "access-control-allow-origin" not in stranger.headers, "the origins are named, never *"
