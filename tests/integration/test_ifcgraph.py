# This file was generated with the assistance of an AI coding tool.
"""IFC-graph end to end: upload the model, wait for the import, link viewpoint components, read GTINs."""

from __future__ import annotations

import time
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from neo4j import GraphDatabase

from opencde.main import create_app
from tests.conftest import FIXTURES_DIR, test_settings
from tests.integration.conftest import GraphTarget
from tests.integration.conftest_accounts import World, build_world, login_as
from tests.integration.test_documents_api import save_metadata, start_upload, upload_file
from tests.integration.test_web_signin import web_sign_in

pytestmark = pytest.mark.integration
pytest.importorskip("ifcopenshell", reason="the ifcgraph extra is not installed")

WALLS = ("1Xezbq735AdBO_4DerG66G", "3eT96F_cnDsOufCEsotwtp", "3k3LbXmTfDWODxdSuyCGYE")
CALLBACK = "http://127.0.0.1:9/callback"


@pytest.fixture
def ifc_client(graph_target: GraphTarget, clean_database: None, tmp_path) -> Iterator[tuple[TestClient, World]]:
    settings = test_settings(
        tmp_path,
        graph_dialect=graph_target.dialect,
        graph_uri=graph_target.uri,
        graph_user=graph_target.user,
        graph_password=graph_target.password,
        graph_connect_timeout_seconds=10.0,
        cleanup_interval_seconds=3600,
        upload_part_bytes=4096,
        ifcgraph_enabled=True,
        ifcgraph_timeout_seconds=300,
    )
    world = build_world(settings)
    with TestClient(create_app(settings, startup_wait_seconds=30)) as client:
        yield client, world


def wait_for_model(graph_target: GraphTarget, database: str | None, timeout: float = 240.0) -> dict:
    deadline = time.monotonic() + timeout
    with GraphDatabase.driver(graph_target.uri, auth=(graph_target.user, graph_target.password)) as driver:
        while time.monotonic() < deadline:
            records, _, _ = driver.execute_query("MATCH (m:IfcModel) RETURN properties(m) AS m", database_=database)
            if records and records[0]["m"].get("state") in ("done", "failed"):
                return records[0]["m"]
            time.sleep(1.0)
    raise AssertionError("the IFC import did not finish in time")


def test_uploaded_model_becomes_graph_and_components_link(
    ifc_client: tuple[TestClient, World], graph_target: GraphTarget
) -> None:
    client, world = ifc_client
    editor = login_as(client, world, "editor")
    web_sign_in(client, world, "editor")
    ifc = (FIXTURES_DIR / "three_walls_gtin.ifc").read_bytes()

    started = start_upload(client, editor, [{"file_name": "three_walls_gtin.ifc", "session_file_id": "m"}])
    instructions_url = save_metadata(
        client, started["upload_ui_url"], world.project_id, {"title_0": "Three walls", "version_0": "1"}
    )
    plan = client.post(
        instructions_url, json={"files": [{"session_file_id": "m", "size_in_bytes": len(ifc)}]}, headers=editor.headers
    ).json()
    version = upload_file(client, editor, plan["documents_to_upload"][0], ifc)

    model = wait_for_model(graph_target, client.app.state.settings.database_name)  # type: ignore[attr-defined]
    assert model["state"] == "done", model.get("error")
    assert model["schema"] == "IFC2X3" and model["ifc_project_guid"] == "1CGyzxdzHaJybf9L4wHy3R"
    assert model["entities"] > 100 and model["relationships"] > 100 and model["document_id"] == version["document_id"]

    information = client.get(f"/bcf/3.0/projects/{world.project_id}/files_information", headers=editor.headers).json()
    assert information[0]["file"]["ifc_project"] == "1CGyzxdzHaJybf9L4wHy3R", "the IfcProject guid comes from the model"

    topic = client.post(
        f"/bcf/3.0/projects/{world.project_id}/topics", json={"title": "Walls"}, headers=editor.headers
    ).json()
    viewpoint = client.post(
        f"/bcf/3.0/projects/{world.project_id}/topics/{topic['guid']}/viewpoints",
        json={
            "perspective_camera": {
                "camera_view_point": {"x": 0, "y": 0, "z": 0},
                "camera_direction": {"x": 1, "y": 0, "z": 0},
                "camera_up_vector": {"x": 0, "y": 0, "z": 1},
                "field_of_view": 60,
                "aspect_ratio": 1,
            },
            "components": {
                "selection": [{"ifc_guid": guid} for guid in WALLS] + [{"ifc_guid": "0NotInTheModel00000000"}],
                "visibility": {"default_visibility": True},
            },
        },
        headers=editor.headers,
    )
    assert viewpoint.status_code == 201, viewpoint.text

    with GraphDatabase.driver(graph_target.uri, auth=(graph_target.user, graph_target.password)) as driver:
        database = client.app.state.settings.database_name  # type: ignore[attr-defined]
        rows, _, _ = driver.execute_query(
            """
            MATCH (c:Component)-[:SAME_AS]->(e:IfcEntity)
            RETURN c.ifc_guid AS guid, c.gtin AS gtin, e.Name AS name ORDER BY c.position
            """,
            database_=database,
        )
        linked = [(r["guid"], r["gtin"], r["name"]) for r in rows]
        assert linked == [(WALLS[0], "3", "YVT-A"), (WALLS[1], "2", "YVT-B"), (WALLS[2], "1", "YVT-C")]
        # The query from the research report, on the imported graph.
        gtins, _, _ = driver.execute_query(
            """
            MATCH (w:IfcWall)-[:IsDefinedBy]->(:IfcRelDefinesByProperties)-[:RelatingPropertyDefinition]
                  ->(:IfcPropertySet {Name: 'Reuse'})-[:HasProperties]->(p:IfcPropertySingleValue {Name: 'GTIN'})
            RETURN w.GlobalId AS guid, p.NominalValue AS gtin ORDER BY gtin
            """,
            database_=database,
        )
        assert [(r["guid"], r["gtin"]) for r in gtins] == [(WALLS[2], "1"), (WALLS[1], "2"), (WALLS[0], "3")]
        walls, _, _ = driver.execute_query("MATCH (w:IfcEntity:IfcWall) RETURN count(w) AS n", database_=database)
        assert walls[0]["n"] == 3
