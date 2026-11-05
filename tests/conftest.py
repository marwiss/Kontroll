# This file was generated with the assistance of an AI coding tool.
"""Shared fixtures.

Unit tests run the app without a database: the graph URI points at a closed
port so readiness fails fast. Integration tests (stage 1 onwards) start a
real Neo4j or Memgraph with testcontainers.
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


def test_settings(**overrides: object) -> Settings:
    """Settings for tests: no .env file, no database, readable logs."""
    values: dict[str, object] = {
        "environment": "test",
        "public_url": "http://testserver",
        "graph_uri": "bolt://127.0.0.1:9",  # discard port: connection refused immediately
        "graph_password": "test-password",
        "graph_connect_timeout_seconds": 1.0,
        "log_json": False,
        "log_level": "WARNING",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[call-arg]


@pytest.fixture
def settings() -> Settings:
    return test_settings()


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as test_client:
        yield test_client
