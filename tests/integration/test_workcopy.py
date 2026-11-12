# This file was generated with the assistance of an AI coding tool.
"""The working copy (ADR 0024): the head model of a document imported into a second graph, where the named queries
answer from, replaced by the next version and dropped with the archive's model."""

from __future__ import annotations

import re
import time
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from neo4j import GraphDatabase
from testcontainers.core.container import DockerContainer
from testcontainers.core.wait_strategies import LogMessageWaitStrategy

from opencde.main import create_app
from tests.integration.conftest import MEMGRAPH_IMAGE, GraphTarget
from tests.integration.conftest_accounts import World, build_world, login_as, login_with_scope
from tests.integration.test_documents_api import save_metadata, start_upload, upload_file
from tests.integration.test_ifc_queries import ask, converted, queries_url, rows_of
from tests.integration.test_ifc_validation import MODEL, settings_for, upload
from tests.integration.test_web_signin import web_sign_in

pytestmark = pytest.mark.integration
pytest.importorskip("ifcopenshell", reason="the ifc-db extra is not installed")


@pytest.fixture(scope="session")
def workcopy_uri() -> Iterator[str]:
    container = (
        DockerContainer(MEMGRAPH_IMAGE)
        .with_exposed_ports(7687)
        .waiting_for(LogMessageWaitStrategy(re.compile(r"You are running Memgraph")).with_startup_timeout(120))
    )
    with container:
        yield f"bolt://{container.get_container_host_ip()}:{container.get_exposed_port(7687)}"


@pytest.fixture
def workcopy_client(
    graph_target: GraphTarget, clean_database: None, tmp_path: Any, workcopy_uri: str
) -> Iterator[tuple[TestClient, World, str]]:
    with GraphDatabase.driver(workcopy_uri, auth=("", "")) as driver:
        driver.execute_query("MATCH (n) DETACH DELETE n")
    settings = settings_for(graph_target, tmp_path, ifcgraph_validate_uploads=False, workcopy_graph_uri=workcopy_uri)
    world = build_world(settings)
    with TestClient(create_app(settings, startup_wait_seconds=30)) as client:
        yield client, world, workcopy_uri


def wait_for_boxes(uri: str, timeout: float = 120.0) -> int:
    """How many walls of the working copy have a box, once the geometry pass has reached it."""
    deadline = time.monotonic() + timeout
    with GraphDatabase.driver(uri, auth=("", "")) as driver:
        while time.monotonic() < deadline:
            records, _, _ = driver.execute_query(
                "MATCH (w:Entity:IfcWallStandardCase) WHERE w.bbox_centre IS NOT NULL RETURN count(w) AS n"
            )
            if records and int(records[0]["n"]) > 0:
                return int(records[0]["n"])
            time.sleep(0.5)
    return 0


def models_in(uri: str) -> dict[str, int]:
    """The models the working copy holds, each with how many entities it has."""
    with GraphDatabase.driver(uri, auth=("", "")) as driver:
        records, _, _ = driver.execute_query(
            "MATCH (m:Model) OPTIONAL MATCH (e:Entity {model_id: m.id}) RETURN m.id AS id, count(e) AS entities"
        )
    return {record["id"]: int(record["entities"]) for record in records}


def test_the_head_model_lives_in_the_working_copy_and_answers_the_queries(
    workcopy_client: tuple[TestClient, World, str],
) -> None:
    client, world, uri = workcopy_client
    editor = login_as(client, world, "editor")
    web_sign_in(client, world, "editor")
    admin = login_with_scope(client, world, "admin", "profile admin")
    assert client.get("/readyz").json()["workcopy"] == "ok"
    assert client.get("/.well-known/dataregium").json()["extensions"]["ifcgraph"]["workcopy"] is True

    first = upload(client, world, editor, "three_walls_gtin.ifc", MODEL.read_bytes())
    listed = converted(client, editor, first)
    assert listed["workcopy"] is True, "the head model is in the working copy"
    copies = models_in(uri)
    assert len(copies) == 1 and next(iter(copies.values())) > 100, "the whole model, entities and all"
    classes = {row["class"]: row["count"] for row in rows_of(ask(client, editor, first, "element-classes"))}
    assert classes["IfcWallStandardCase"] == 3, "answered from the working copy"
    (wall,) = rows_of(ask(client, editor, first, "entity", global_id="1Xezbq735AdBO_4DerG66G"))
    assert wall["attributes"]["Name"] == "YVT-A"
    assert wait_for_boxes(uri) == 3, "the boxes of the spatial layer reach the working copy too"

    # The next version replaces the head; the one before leaves the working copy, the archive keeps both.
    started = start_upload(
        client,
        editor,
        [{"file_name": "three_walls_gtin.ifc", "session_file_id": "n", "document_id": first["document_id"]}],
    )
    instructions = save_metadata(
        client, started["upload_ui_url"], world.project_id, {"title_0": "walls", "version_0": "2"}
    )
    plan = client.post(
        instructions,
        json={"files": [{"session_file_id": "n", "size_in_bytes": len(MODEL.read_bytes())}]},
        headers=editor.headers,
    ).json()["documents_to_upload"][0]
    second = upload_file(client, editor, plan, MODEL.read_bytes())
    assert converted(client, editor, second)["workcopy"] is True
    assert len(models_in(uri)) == 1, "one head per document"
    assert client.get(f"{queries_url(first)}", headers=editor.headers).json()["workcopy"] is False
    assert rows_of(ask(client, editor, first, "element-classes"))[0]["count"] == 3, "the archive still answers"

    # A model the archive no longer has leaves the working copy at the next round.
    assert client.delete(f"/admin/api/projects/{world.project_id}", headers=admin.headers).status_code == 204
    ifcgraph = client.app.state.ifcgraph  # type: ignore[attr-defined]
    assert client.portal.call(ifcgraph.tidy_workcopy) == 1  # on the application's own loop
    assert models_in(uri) == {}
