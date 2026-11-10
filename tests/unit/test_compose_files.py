# This file was generated with the assistance of an AI coding tool.
"""What the Compose files add up to, as Docker reads them; nothing is started."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DOCKER = shutil.which("docker")

pytestmark = pytest.mark.skipif(DOCKER is None, reason="needs Docker's command line")

ENV = """\
OPENCDE_GRAPH_PASSWORD=a-password-for-this-test
OPENCDE_DOMAIN=cde.example.org
"""


def _config(tmp_path: Path, *overlays: str, extra_env: str = "") -> dict:
    # A copy of docker/ with a .env of its own beside it, as in a checkout: .env names the files.
    shutil.copytree(ROOT / "docker", tmp_path / "docker")
    names = ":".join(f"docker/{name}" for name in ("compose.yaml", *overlays))
    env = f"COMPOSE_PATH_SEPARATOR=:\nCOMPOSE_FILE={names}\n" + ENV + extra_env
    (tmp_path / ".env").write_text(env, encoding="utf-8")
    done = subprocess.run(  # noqa: S603  # the arguments are this test's own
        [str(DOCKER), "compose", "config", "--format", "json"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)["services"]


def test_the_stack_has_its_database_by_default(tmp_path: Path) -> None:
    services = _config(tmp_path, "compose.prod.yaml")
    assert {"graph", "api", "proxy", "backup"} <= set(services)
    assert services["api"]["environment"]["OPENCDE_GRAPH_URI"] == "bolt://graph:7687"
    assert services["backup"]["environment"]["OPENCDE_GRAPH_URI"] == "bolt://graph:7687"
    assert services["api"]["depends_on"]["graph"]["condition"] == "service_healthy"


def test_the_local_engine_publishes_the_api_on_the_loopback_only(tmp_path: Path) -> None:
    services = _config(tmp_path, "compose.local.yaml")
    assert services["api"]["environment"]["OPENCDE_ENVIRONMENT"] == "local"
    assert services["api"]["environment"]["OPENCDE_PUBLIC_URL"] == "http://127.0.0.1:8000"
    (published,) = services["api"]["ports"]
    assert published["host_ip"] == "127.0.0.1" and published["published"] == "8000"
    assert "ports" not in services["graph"], "the database is never published"


def test_the_working_copy_joins_the_private_network_unpublished(tmp_path: Path) -> None:
    services = _config(tmp_path, "compose.local.yaml", "compose.workcopy.yaml")
    assert "ports" not in services["workcopy"] and services["workcopy"]["image"].startswith("docker.io/memgraph/")
    assert services["api"]["environment"]["OPENCDE_WORKCOPY_GRAPH_URI"] == "bolt://workcopy:7687"
    assert services["api"]["depends_on"]["workcopy"]["condition"] == "service_healthy"


def test_an_external_database_leaves_the_container_out(tmp_path: Path) -> None:
    address = "neo4j+s://xxxx.databases.neo4j.io"
    services = _config(
        tmp_path,
        "compose.prod.yaml",
        "compose.external-db.yaml",
        extra_env=f"OPENCDE_STACK_GRAPH_URI={address}\n",
    )
    assert "graph" not in services
    assert services["api"]["environment"]["OPENCDE_GRAPH_URI"] == address
    assert services["backup"]["environment"]["OPENCDE_GRAPH_URI"] == address
