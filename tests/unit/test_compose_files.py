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
    # The files in a folder of their own, since each of them reads the .env next to it.
    for name in ("compose.yaml", *overlays):
        shutil.copy(ROOT / name, tmp_path / name)
    (tmp_path / ".env").write_text(ENV + extra_env, encoding="utf-8")
    files = [arg for name in ("compose.yaml", *overlays) for arg in ("-f", name)]
    done = subprocess.run(  # noqa: S603  # the arguments are this test's own
        [str(DOCKER), "compose", *files, "config", "--format", "json"],
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
