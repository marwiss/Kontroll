# This file was generated with the assistance of an AI coding tool.
"""The server's own data in a graph of its own (``OPENCDE_STORE_GRAPH_URI``, ADR 0027): an upload, its check, its
model and a change set proposed and approved, with the store in a second database beside the IFC graph.

The store is a Memgraph container of its own: beside Neo4j it is another product, beside Memgraph another database
of the same one. Neo4j's community edition holds one database, so two databases of one Neo4j container cannot be
had here."""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from neo4j import GraphDatabase
from testcontainers.core.container import DockerContainer
from testcontainers.core.wait_strategies import LogMessageWaitStrategy

from opencde.documents.changes import SCHEMA_PATH, SNIPPET_TYPE
from opencde.graph.dialect import GraphDialect
from opencde.main import create_app
from opencde.settings import Settings
from tests.integration.conftest import MEMGRAPH_IMAGE, GraphTarget
from tests.integration.conftest_accounts import World, build_world, login_as
from tests.integration.test_bcf_links_documents import make_topic
from tests.integration.test_ifc_proposal import change_set, tried
from tests.integration.test_ifc_queries import ask, converted, rows_of
from tests.integration.test_ifc_validation import MODEL, WALLS, checked, settings_for, upload
from tests.integration.test_web_signin import web_sign_in

pytestmark = pytest.mark.integration
pytest.importorskip("ifcopenshell", reason="the ifc-lpg extra is not installed")

MODEL_LABELS = ("Model", "Entity", "StepBlock")
SERVER_LABELS = ("User", "Project", "Document", "DocumentVersion", "Conversion", "Validation", "Topic", "Proposal")


@pytest.fixture(scope="session")
def store_uri() -> Iterator[str]:
    container = (
        DockerContainer(MEMGRAPH_IMAGE)
        .with_exposed_ports(7687)
        .waiting_for(LogMessageWaitStrategy(re.compile(r"You are running Memgraph")).with_startup_timeout(120))
    )
    with container:
        yield f"bolt://{container.get_container_host_ip()}:{container.get_exposed_port(7687)}"


@pytest.fixture
def apart(
    graph_target: GraphTarget, clean_database: None, tmp_path: Any, store_uri: str
) -> Iterator[tuple[TestClient, World, Settings]]:
    with GraphDatabase.driver(store_uri, auth=("", "")) as driver:
        driver.execute_query("MATCH (n) DETACH DELETE n")
    settings = settings_for(
        graph_target, tmp_path, store_graph_uri=store_uri, store_graph_dialect=GraphDialect.MEMGRAPH
    )
    world = build_world(settings)  # into the store, where the accounts live
    with TestClient(create_app(settings, startup_wait_seconds=30)) as client:
        yield client, world, settings


def counts(uri: str, user: str, password: str, database: str, labels: tuple[str, ...]) -> dict[str, int]:
    """How many nodes of each label a database holds."""
    found = {}
    with GraphDatabase.driver(uri, auth=(user, password)) as driver:
        for label in labels:
            records, _, _ = driver.execute_query(f"MATCH (n:{label}) RETURN count(n) AS n", database_=database)
            found[label] = int(records[0]["n"])
    return found


def assert_apart(graph_target: GraphTarget, settings: Settings) -> dict[str, int]:
    """Nothing of the server's own in the IFC graph and nothing of the models in the store; returns the IFC graph's
    counts of the library's labels."""
    ifc = (graph_target.uri, graph_target.user, graph_target.password, settings.database_name)
    store = (str(settings.store_graph_uri), "", "", settings.store_database_name)
    assert set(counts(*ifc, SERVER_LABELS).values()) == {0}, "the IFC graph holds the server's own nodes"
    assert set(counts(*store, MODEL_LABELS).values()) == {0}, "the store holds a model"
    assert counts(*store, ("User", "Project"))["User"] > 0, "the accounts are in the store"
    return counts(*ifc, MODEL_LABELS)


def test_an_upload_is_checked_converted_proposed_and_approved_with_the_store_apart(
    apart: tuple[TestClient, World, Settings], graph_target: GraphTarget
) -> None:
    client, world, settings = apart
    editor = login_as(client, world, "editor")
    web_sign_in(client, world, "editor")
    manager = login_as(client, world, "manager")
    assert client.get("/readyz").json()["store"] == "ok"

    version = upload(client, world, editor, "three_walls_gtin.ifc", MODEL.read_bytes())
    assert checked(client, editor, version)["ifc_validation_status"] == ["passed"]
    assert converted(client, editor, version)["model_state"] == "done"
    classes = {row["class"]: row["count"] for row in rows_of(ask(client, editor, version, "element-classes"))}
    assert classes, "the named queries answer from the IFC graph"
    models = assert_apart(graph_target, settings)
    assert models["Model"] == 1 and models["Entity"] > 100, "the whole model is in the IFC graph"

    topics = f"/bcf/3.0/projects/{world.project_id}/topics"
    snippet_fields = {
        "snippet_type": SNIPPET_TYPE,
        "is_external": False,
        "reference": "changes.json",
        "reference_schema": f"http://testserver{SCHEMA_PATH}",
    }
    topic = make_topic(client, world, editor, bim_snippet=snippet_fields)
    snippet = f"{topics}/{topic['guid']}/snippet"
    proposal = f"{topics}/{topic['guid']}/ifc-proposal"
    rename = {"guid": WALLS[0], "attribute": "Name", "op": "set", "old": "YVT-A", "new": "YVT-A2"}
    put = client.put(snippet, content=change_set(version["document_id"], rename), headers=editor.headers)
    assert put.status_code == 200, put.text
    assert tried(client, editor, proposal)["state"] == "clean"

    approved = client.post(proposal + "/approve", headers=manager.headers)
    assert approved.status_code == 201, approved.text
    new = approved.json()
    assert new["version_index"] == 2
    assert checked(client, editor, new)["ifc_validation_status"] == ["passed"], "the new version is checked as any"
    assert converted(client, editor, new)["model_state"] == "done"
    report = client.get(proposal, headers=editor.headers).json()
    assert report["state"] == "approved" and report["version_index"] == 2
    download = client.get(new["links"]["document_version_download"]["url"], headers=editor.headers)
    assert download.status_code == 200 and b"YVT-A2" in download.content

    models = assert_apart(graph_target, settings)
    assert models["Model"] == 2, "each version has its model in the IFC graph"
