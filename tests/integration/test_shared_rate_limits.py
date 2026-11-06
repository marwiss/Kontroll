# This file was generated with the assistance of an AI coding tool.
"""The counts in a real shared store: two servers count together, and a store that goes away stops nothing."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from testcontainers.core.container import DockerContainer
from testcontainers.core.wait_strategies import LogMessageWaitStrategy

from opencde.main import create_app
from tests.conftest import test_settings as settings_for_tests

pytestmark = [pytest.mark.integration, pytest.mark.security]

REDIS_IMAGE = "redis:8-alpine"
API = "/foundation/versions"


def _server(tmp_path: Path, store: str) -> TestClient:
    settings = settings_for_tests(
        tmp_path, rate_limits_enabled=True, rate_limit_api="3/minute", rate_limit_storage=store
    )
    return TestClient(create_app(settings, startup_wait_seconds=0))


def test_two_servers_count_together_and_a_lost_store_stops_nothing(tmp_path: Path) -> None:
    pytest.importorskip("redis")
    ready = LogMessageWaitStrategy(re.compile(r"Ready to accept connections")).with_startup_timeout(60)
    store = DockerContainer(REDIS_IMAGE).with_exposed_ports(6379).waiting_for(ready)
    with store:
        address = f"redis://{store.get_container_host_ip()}:{store.get_exposed_port(6379)}/0"
        with _server(tmp_path, address) as first:
            assert [first.get(API).status_code for _ in range(3)] == [200, 200, 200]
        with _server(tmp_path, address) as second:
            assert second.get(API).status_code == 429, "the second server sees the first one's count"
            store.get_wrapped_container().stop(timeout=1)
            assert second.get(API).status_code == 200, "the server answers without its store"
