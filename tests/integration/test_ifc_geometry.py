# This file was generated with the assistance of an AI coding tool.
"""The spatial layer and the geometry API (OB-37): after a conversion every product has its box in the graph, and
the version's geometry comes as binary glTF, built once and cached, for the members of the project."""

from __future__ import annotations

import functools
import time
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from neo4j import GraphDatabase

from opencde.ifcgraph.gltf import read_glb
from opencde.ifcgraph.maintenance import prune_models
from opencde.main import create_app
from tests.integration.conftest import GraphTarget
from tests.integration.conftest_accounts import World, build_world, login_as
from tests.integration.test_ifc_validation import MODEL, settings_for, upload
from tests.integration.test_ifcgraph import WALLS
from tests.integration.test_web_signin import web_sign_in

pytestmark = pytest.mark.integration
pytest.importorskip("ifcopenshell", reason="the ifc-db extra is not installed")


@pytest.fixture
def ifc_client(graph_target: GraphTarget, clean_database: None, tmp_path: Any) -> Iterator[tuple[TestClient, World]]:
    settings = settings_for(graph_target, tmp_path, ifcgraph_validate_uploads=False)
    world = build_world(settings)
    with TestClient(create_app(settings, startup_wait_seconds=30)) as client:
        yield client, world


def wait_for_geometry(client: TestClient, graph_target: GraphTarget, timeout: float = 240.0) -> dict[str, Any]:
    """The model once its geometry pass is over, one way or the other."""
    database = client.app.state.settings.database_name  # type: ignore[attr-defined]
    deadline = time.monotonic() + timeout
    with GraphDatabase.driver(graph_target.uri, auth=(graph_target.user, graph_target.password)) as driver:
        while time.monotonic() < deadline:
            records, _, _ = driver.execute_query("MATCH (c:Conversion) RETURN properties(c) AS m", database_=database)
            model = records[0]["m"] if records else {}
            if model.get("state") == "failed" or (model.get("state") == "done" and not model.get("spatial_pending")):
                return model
            time.sleep(0.5)
    raise AssertionError("the geometry pass did not finish in time")


def test_the_products_get_boxes_and_the_version_comes_as_gltf(
    ifc_client: tuple[TestClient, World], graph_target: GraphTarget
) -> None:
    client, world = ifc_client
    editor = login_as(client, world, "editor")
    web_sign_in(client, world, "editor")
    viewer = login_as(client, world, "viewer")
    outsider = login_as(client, world, "outsider")
    assert client.get("/.well-known/dataregium").json()["extensions"]["ifc_geometry"]["enabled"] is True
    version = upload(client, world, editor, "three_walls_gtin.ifc", MODEL.read_bytes())
    url = f"/documents/1.0/documents/{version['document_id']}/versions/1/ifc-geometry"

    model = wait_for_geometry(client, graph_target)
    assert model["state"] == "done" and not model.get("spatial_error"), model
    assert model["spatial_products"] == 3 and model["spatial_failed"] == 0 and model["geometry_key"]
    database = client.app.state.settings.database_name  # type: ignore[attr-defined]
    with GraphDatabase.driver(graph_target.uri, auth=(graph_target.user, graph_target.password)) as driver:
        rows, _, _ = driver.execute_query(
            """
            MATCH (w:Entity:IfcWallStandardCase) WHERE w.bbox_centre IS NOT NULL
            RETURN w.GlobalId AS guid, w.bbox_min.z AS low, w.bbox_max.z AS high ORDER BY guid
            """,
            database_=database,
        )
        assert [row["guid"] for row in rows] == sorted(WALLS), "every wall has its box"
        assert all(row["high"] > row["low"] for row in rows)
        near, _, _ = driver.execute_query(
            """
            MATCH (w:Entity {GlobalId: $guid})
            MATCH (e:Entity {model_id: w.model_id}) WHERE e.bbox_centre IS NOT NULL AND e <> w
            RETURN e.GlobalId AS guid, point.distance(e.bbox_centre, w.bbox_centre) AS distance ORDER BY distance
            """,
            guid=WALLS[0],
            database_=database,
        )
        assert len(near) == 2 and near[0]["distance"] > 0, "a nearness query over the point index"

    answer = client.get(url, headers=viewer.headers)
    assert answer.status_code == 200, answer.text
    assert answer.headers["content-type"] == "model/gltf-binary" and answer.headers["etag"]
    assert answer.headers["cache-control"] == "private, max-age=3600"
    document, binary = read_glb(answer.content)
    products = [node for node in document["nodes"] if "mesh" in node]
    assert sorted(node["name"] for node in products) == sorted(WALLS) and len(document["meshes"]) == 3
    assert document["asset"]["extras"]["lod"] == "full" and len(binary) > 0
    again = client.get(url, headers={**viewer.headers, "If-None-Match": answer.headers["etag"]})
    assert again.status_code == 304 and again.content == b""

    boxes = client.get(url, params={"lod": "box", "classes": "IfcWallStandardCase"}, headers=editor.headers)
    assert boxes.status_code == 200 and boxes.headers["etag"] != answer.headers["etag"]
    document, _ = read_glb(boxes.content)
    assert len(document["meshes"]) == 1 and document["asset"]["extras"]["products"] == 3
    none = client.get(url, params={"classes": "IfcSlab"}, headers=editor.headers)
    assert none.status_code == 200 and read_glb(none.content)[0]["asset"]["extras"]["products"] == 0
    assert client.get(url, params={"lod": "points"}, headers=editor.headers).status_code == 400
    assert client.get(url, params={"classes": "DROP TABLE"}, headers=editor.headers).status_code == 400
    assert client.get(url, params={"storey": "short"}, headers=editor.headers).status_code == 400
    assert client.get(url, headers=outsider.headers).status_code == 404, "not a member"
    assert client.get(url.replace("/versions/1/", "/versions/9/"), headers=editor.headers).status_code == 404

    # A model converted before the geometry pass existed has no records: 404, not a wait that never ends.
    with GraphDatabase.driver(graph_target.uri, auth=(graph_target.user, graph_target.password)) as driver:
        driver.execute_query("MATCH (c:Conversion) REMOVE c.geometry_key", database_=database)
    assert client.get(url, headers=editor.headers).status_code == 404
    with GraphDatabase.driver(graph_target.uri, auth=(graph_target.user, graph_target.password)) as driver:
        driver.execute_query(
            "MATCH (c:Conversion) SET c.geometry_key = $key", key=model["geometry_key"], database_=database
        )

    storage = client.app.state.storage  # type: ignore[attr-defined]
    kept = [key for key in storage.iter_keys("geometry") if key.startswith(f"geometry/{model['id']}.")]
    assert len(kept) == 4, "the records and the three glTF files built from them"
    graph = client.app.state.graph  # type: ignore[attr-defined]
    pruned = client.portal.call(
        functools.partial(prune_models, graph, project_id=world.project_id, everything=True, storage=storage)
    )
    assert pruned["models"] == 1
    assert not [key for key in storage.iter_keys("geometry") if key.startswith(f"geometry/{model['id']}.")]
