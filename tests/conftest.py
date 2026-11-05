# This file was generated with the assistance of an AI coding tool.
"""Shared fixtures.

Unit tests run the app without a database: the graph URI points at a closed
port and the app does not wait for it. Integration tests (``tests/integration``)
start a real Neo4j, and optionally Memgraph, with testcontainers.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from opencde.main import create_app
from opencde.settings import Settings

REPO_ROOT = Path(__file__).resolve().parents[1]
SPEC_DIR = REPO_ROOT / "spec"
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def test_settings(tmp_path: Path | None = None, **overrides: object) -> Settings:
    """Settings for tests: no .env file, readable logs, generous limits where tests need them."""
    values: dict[str, object] = {
        "environment": "test",
        "public_url": "http://testserver",
        "secret_key": "test-secret-key-that-is-long-enough-for-signing",
        "graph_uri": "bolt://127.0.0.1:9",  # discard port: connection refused immediately
        "graph_password": "test-password",
        "graph_connect_timeout_seconds": 1.0,
        "log_json": False,
        "log_level": "WARNING",
        "rate_limits_enabled": False,
    }
    if tmp_path is not None:
        values["data_dir"] = tmp_path / "data"
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[call-arg]


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return test_settings(tmp_path)


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    """App without a database (startup does not wait for one)."""
    with TestClient(create_app(settings, startup_wait_seconds=0)) as test_client:
        yield test_client
