# This file was generated with the assistance of an AI coding tool.
"""IFC-graph end to end: upload the model, wait for the import, link viewpoint components, read GTINs."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from neo4j import GraphDatabase

from opencde import seed as seeding
from opencde.bootstrap import make_graph, make_storage
from opencde.documents.assembly import store_stream
from opencde.graph.schema import apply_schema
from opencde.ids import new_id
from opencde.main import create_app
from opencde.storage import make_key
from opencde.timeutil import later_iso, now_iso
from tests.conftest import FIXTURES_DIR, test_settings
from tests.integration.conftest import GraphTarget
from tests.integration.conftest_accounts import World, build_world, login_as
from tests.integration.test_documents_api import save_metadata, start_upload, upload_file
from tests.integration.test_web_signin import web_sign_in

pytestmark = pytest.mark.integration
pytest.importorskip("ifcopenshell", reason="the ifc-lpg extra is not installed")

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
            records, _, _ = driver.execute_query("MATCH (c:Conversion) RETURN properties(c) AS m", database_=database)
            if records and records[0]["m"].get("state") in ("done", "failed"):
                return records[0]["m"]
            time.sleep(1.0)
    raise AssertionError("the IFC import did not finish in time")


def test_seeding_builds_the_graph_of_the_sample_model(
    graph_target: GraphTarget, clean_database: None, tmp_path
) -> None:
    settings = test_settings(
        tmp_path,
        graph_dialect=graph_target.dialect,
        graph_uri=graph_target.uri,
        graph_user=graph_target.user,
        graph_password=graph_target.password,
        graph_connect_timeout_seconds=10.0,
        ifcgraph_enabled=True,
        ifcgraph_timeout_seconds=300,
    )

    async def work() -> tuple[dict, list[dict]]:
        graph = make_graph(settings)
        storage = make_storage(settings)
        try:
            await apply_schema(graph)
            loaded = await seeding.seed(graph, storage=storage)
            model = await seeding.build_sample_graph(graph, storage, settings, loaded)
            links = await graph.run("MATCH (c:Component), (w:IfcWall {GlobalId: c.ifc_guid}) RETURN w.GlobalId AS guid")
            return model, links
        finally:
            await graph.close()

    model, links = asyncio.run(work())
    assert model["state"] == "done", model.get("error")
    assert model["entities"] > 0
    assert [link["guid"] for link in links] == [next(iter(seeding.SAMPLE_MODEL_WALLS))], "the viewpoint's wall"


def test_a_conversion_a_stopped_server_left_behind_starts_over(
    graph_target: GraphTarget, clean_database: None, tmp_path
) -> None:
    settings = test_settings(
        tmp_path,
        graph_dialect=graph_target.dialect,
        graph_uri=graph_target.uri,
        graph_user=graph_target.user,
        graph_password=graph_target.password,
        graph_connect_timeout_seconds=10.0,
        ifcgraph_enabled=True,
        ifcgraph_timeout_seconds=300,
    )
    world = build_world(settings)
    key = make_key("documents", new_id())
    with (FIXTURES_DIR / "three_walls_gtin.ifc").open("rb") as source:
        store_stream(make_storage(settings), source, key, 10_000_000)
    left_behind = {
        "queued": {},
        "long-gone": {"running_at": later_iso(-3600)},
        "just-started": {"running_at": now_iso()},
    }
    with GraphDatabase.driver(graph_target.uri, auth=(graph_target.user, graph_target.password)) as driver:
        for model_id, fields in left_behind.items():
            driver.execute_query(
                """
                MATCH (p:Project {project_id: $project_id})
                CREATE (p)-[:HAS_CONVERSION]->(m:Conversion {
                    id: $id, model_id: $id, project_id: $project_id, file_name: 'a.ifc', storage_key: $key,
                    created_at: $now
                })
                SET m.state = CASE WHEN $id = 'queued' THEN 'queued' ELSE 'running' END, m += $fields
                """,
                project_id=world.project_id,
                id=model_id,
                key=key,
                now=now_iso(),
                fields=fields,
                database_=settings.database_name,
            )
        driver.execute_query(
            "CREATE (:Entity {model_id: 'long-gone', GlobalId: 'half-way-through'})",
            database_=settings.database_name,
        )

        def states() -> dict[str, str]:
            records, _, _ = driver.execute_query(
                "MATCH (c:Conversion) RETURN c.id AS id, c.state AS state", database_=settings.database_name
            )
            return {record["id"]: record["state"] for record in records}

        with TestClient(create_app(settings, startup_wait_seconds=30)):
            deadline = time.monotonic() + 240
            while {states()["queued"], states()["long-gone"]} != {"done"}:
                assert time.monotonic() < deadline, states()
                assert "failed" not in states().values(), states()
                time.sleep(1.0)
        assert states()["just-started"] == "running", "it may be running in another server process"
        half_way, _, _ = driver.execute_query(
            "MATCH (e:Entity {GlobalId: 'half-way-through'}) RETURN count(e) AS n", database_=settings.database_name
        )
        assert half_way[0]["n"] == 0


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
            MATCH (c:Component), (e:Entity {GlobalId: c.ifc_guid})
            RETURN c.ifc_guid AS guid, c.gtin AS gtin, e.Name AS name ORDER BY c.position
            """,
            database_=database,
        )
        linked = [(r["guid"], r["gtin"], r["name"]) for r in rows]
        assert linked == [(WALLS[0], "3", "YVT-A"), (WALLS[1], "2", "YVT-B"), (WALLS[2], "1", "YVT-C")]
        # The query from the research report, on the imported graph.
        gtins, _, _ = driver.execute_query(
            """
            MATCH (w:IfcWall)-[:IS_DEFINED_BY]->(:IfcRelDefinesByProperties)-[:RELATING_PROPERTY_DEFINITION]
                  ->(:IfcPropertySet {Name: 'Reuse'})-[:HAS_PROPERTIES]->(p:IfcPropertySingleValue {Name: 'GTIN'})
            RETURN w.GlobalId AS guid, p.NominalValue AS gtin ORDER BY gtin
            """,
            database_=database,
        )
        assert [(r["guid"], r["gtin"]) for r in gtins] == [(WALLS[2], "1"), (WALLS[1], "2"), (WALLS[0], "3")]
        walls, _, _ = driver.execute_query("MATCH (w:Entity:IfcWall) RETURN count(w) AS n", database_=database)
        assert walls[0]["n"] == 3


def test_components_created_before_the_model_are_linked_when_it_finishes(
    ifc_client: tuple[TestClient, World], graph_target: GraphTarget
) -> None:
    """A viewpoint may exist before the model is uploaded or while it is still importing (a client test suite does
    exactly that); the links are made when the model reaches `done`. The model arrives as a BCF document here."""
    client, world = ifc_client
    editor = login_as(client, world, "editor")
    topic = client.post(
        f"/bcf/3.0/projects/{world.project_id}/topics", json={"title": "Before the model"}, headers=editor.headers
    ).json()
    viewpoint = client.post(
        f"/bcf/3.0/projects/{world.project_id}/topics/{topic['guid']}/viewpoints",
        json={
            "orthogonal_camera": {
                "camera_view_point": {"x": 0, "y": 0, "z": 10},
                "camera_direction": {"x": 0, "y": 0, "z": -1},
                "camera_up_vector": {"x": 0, "y": 1, "z": 0},
                "view_to_world_scale": 1,
                "aspect_ratio": 1,
            },
            "components": {
                "selection": [{"ifc_guid": WALLS[0]}, {"ifc_guid": WALLS[2]}],
                "visibility": {"default_visibility": True},
            },
        },
        headers=editor.headers,
    )
    assert viewpoint.status_code == 201, viewpoint.text

    uploaded = client.post(
        f"/bcf/3.0/projects/{world.project_id}/documents",
        content=(FIXTURES_DIR / "three_walls_gtin.ifc").read_bytes(),
        headers={**editor.headers, "Content-Disposition": 'attachment; filename="three_walls_gtin.ifc"'},
    )
    assert uploaded.status_code == 201, uploaded.text
    model = wait_for_model(graph_target, client.app.state.settings.database_name)  # type: ignore[attr-defined]
    assert model["state"] == "done", model.get("error")
    assert model["bcf_document_guid"] == uploaded.json()["guid"]

    # A model is `done` a moment before its components are linked: a viewpoint made after `done` is linked by its own
    # call, one made before by the model's, and none in between is missed. So the links are waited for.
    expected = sorted([(WALLS[0], "3"), (WALLS[2], "1")])
    deadline = time.monotonic() + 30
    with GraphDatabase.driver(graph_target.uri, auth=(graph_target.user, graph_target.password)) as driver:
        while True:
            rows, _, _ = driver.execute_query(
                "MATCH (c:Component) WHERE c.gtin IS NOT NULL RETURN c.ifc_guid AS guid, c.gtin AS gtin ORDER BY guid",
                database_=client.app.state.settings.database_name,  # type: ignore[attr-defined]
            )
            linked = [(r["guid"], r["gtin"]) for r in rows]
            if linked == expected or time.monotonic() > deadline:
                break
            time.sleep(0.2)
    assert linked == expected
