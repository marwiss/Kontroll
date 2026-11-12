# This file was generated with the assistance of an AI coding tool.
"""The whole stack in Docker: what people stored outlives the containers (the verification scenario, step 5).

The image is built from the last commit, in a copy of its own, so that a ``.env`` in the working tree stays out
of it. The Compose project and the ports are its own too. It takes minutes, so it belongs to the nightly job;
``OPENCDE_TEST_COMPOSE=1`` runs it anywhere.
"""

from __future__ import annotations

import io
import os
import re
import subprocess
import tarfile
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from opencde_client import OpenCdeClient
from opencde_client.testing import HeadlessBrowser, headless_authorize
from tests.conftest import FIXTURES_DIR

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(os.environ.get("OPENCDE_TEST_COMPOSE") != "1", reason="the long run belongs to the nightly job"),
]

ROOT = Path(__file__).resolve().parents[2]
PROJECT = "dataregium-restart"
PORT = 8311
URL = f"http://127.0.0.1:{PORT}"
USER = "inspection_manager"
PASSWORD = "restart-test-password"  # a throwaway stack on the loopback address
REDIRECT = "http://127.0.0.1/callback"
CALLBACK = "http://127.0.0.1:9/callback"
ENV = f"""\
OPENCDE_GRAPH_PASSWORD={PASSWORD}
OPENCDE_IFC_DB_ENABLED=true
OPENCDE_DEV_PORT={PORT}
OPENCDE_DEV_NEO4J_HTTP_PORT=7611
OPENCDE_DEV_NEO4J_BOLT_PORT=7711
"""

Compose = Callable[..., str]


@pytest.fixture
def compose(tmp_path: Path) -> Iterator[Compose]:
    archive = subprocess.run(  # fixed arguments, on the developer's or runner's own tools
        ["git", "archive", "--format=tar", "HEAD"],  # noqa: S607
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as tar:
        tar.extractall(tmp_path, filter="data")
    files = "COMPOSE_PATH_SEPARATOR=:\nCOMPOSE_FILE=docker/compose.yaml:docker/compose.dev.yaml\n"
    (tmp_path / ".env").write_text(files + ENV, encoding="utf-8")

    def run(*args: str) -> str:
        command = ["docker", "compose", "-p", PROJECT, *args]
        done = subprocess.run(  # noqa: S603  # the arguments are this test's own
            command, cwd=tmp_path, capture_output=True, text=True, encoding="utf-8", timeout=900
        )
        assert done.returncode == 0, f"{' '.join(args)}: {done.stderr[-2000:]}"
        return done.stdout

    try:
        yield run
    finally:
        run("down", "-v", "--remove-orphans")


def _signed_in(client_id: str) -> OpenCdeClient:
    cde = OpenCdeClient(URL, client_id=client_id)
    cde.use_tokens(headless_authorize(cde.oauth, username=USER, password=PASSWORD, redirect_uri=REDIRECT))
    return cde


def _count(compose: Compose, query: str) -> int:
    shell = ("exec", "-T", "graph", "cypher-shell", "-u", "neo4j", "-p", PASSWORD, "--format", "plain", query)
    return int(compose(*shell).split()[-1])


def test_what_people_stored_outlives_the_containers(compose: Compose) -> None:
    compose("up", "-d", "--build", "--wait")
    seeded = compose("exec", "-T", "api", "opencde", "seed", "--password", PASSWORD)
    client_id = re.search(r"client\s+public\s+(\S+)", seeded).group(1)  # type: ignore[union-attr]
    project_id = re.search(r"project\s+Building permit\s+(\S+)", seeded).group(1)  # type: ignore[union-attr]
    model = (FIXTURES_DIR / "three_walls_gtin.ifc").read_bytes()

    with _signed_in(client_id) as before:
        topic = before.bcf.create_topic(project_id, {"title": "Still here after the restart", "topic_type": "Issue"})
        before.bcf.create_comment(project_id, topic["guid"], {"comment": "So is this."})
        started = before.documents.start_upload(
            [{"file_name": "restart.ifc", "session_file_id": "model"}], callback_url=CALLBACK
        )
        browser = HeadlessBrowser(URL)
        browser.sign_in(USER, PASSWORD)
        params = browser.finish_upload_page(
            started["upload_ui_url"], project_id=project_id, titles={0: ("Restart model", "1")}
        )
        browser.close()
        plan = before.documents.upload_instructions(params["upload_documents_url"], {"model": len(model)})
        version = before.documents.upload_file(plan["documents_to_upload"][0], model)
        tokens = before.tokens

        deadline = time.monotonic() + 180
        done = "MATCH (c:Conversion {file_name: 'restart.ifc', state: 'done'}) RETURN count(c) AS models"
        while _count(compose, done) != 1:
            assert time.monotonic() < deadline, "the IFC import did not finish in time"
            time.sleep(2)
    entities = _count(compose, "MATCH (e:Entity) RETURN count(e) AS entities")
    assert entities > 0

    compose("down")
    compose("up", "-d", "--wait")

    with OpenCdeClient(URL, client_id=client_id) as still_signed_in:
        still_signed_in.use_tokens(tokens)
        assert still_signed_in.foundation.current_user()["id"] == USER, "a token given before the restart still works"
    with _signed_in(client_id) as after:
        titles = [found["title"] for found in after.bcf.topics(project_id)]
        assert "Still here after the restart" in titles
        comments = after.bcf.comments(project_id, topic["guid"])
        assert [comment["comment"] for comment in comments] == ["So is this."]
        assert after.documents.download(version) == model, "the file itself is on its own volume"
    assert _count(compose, done) == 1
    assert _count(compose, "MATCH (e:Entity) RETURN count(e) AS entities") == entities
