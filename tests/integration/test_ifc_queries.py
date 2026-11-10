# This file was generated with the assistance of an AI coding tool.
"""Named queries on the IFC graph of a document version, asked as a member, against Neo4j and Memgraph (ADR 0016)."""

from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from opencde.ifcgraph.queries import QUERIES
from opencde.main import create_app
from tests.conftest import FIXTURES_DIR
from tests.integration.conftest import GraphTarget
from tests.integration.conftest_accounts import World, build_world, login_as
from tests.integration.helpers import Session
from tests.integration.test_ifc_validation import settings_for, upload
from tests.integration.test_web_signin import web_sign_in

pytestmark = pytest.mark.integration
pytest.importorskip("ifcopenshell", reason="the ifc-lpg extra is not installed")

WALLS = {"1Xezbq735AdBO_4DerG66G", "3eT96F_cnDsOufCEsotwtp", "3k3LbXmTfDWODxdSuyCGYE"}


@pytest.fixture
def query_client(graph_target: GraphTarget, clean_database: None, tmp_path: Any) -> Iterator[tuple[TestClient, World]]:
    settings = settings_for(graph_target, tmp_path)
    world = build_world(settings)
    with TestClient(create_app(settings, startup_wait_seconds=30)) as client:
        yield client, world


def queries_url(version: dict[str, Any]) -> str:
    return f"/documents/1.0/documents/{version['document_id']}/versions/{version['version_index']}/ifc-queries"


def converted(client: TestClient, session: Session, version: dict[str, Any]) -> dict[str, Any]:
    """The list of queries once the version's model has been converted."""
    deadline = time.monotonic() + 240
    while True:
        response = client.get(queries_url(version), headers=session.headers)
        assert response.status_code == 200, response.text
        if response.json()["model_state"] in ("done", "failed"):
            return response.json()
        assert time.monotonic() < deadline, "the model was not converted in time"
        time.sleep(0.5)


def ask(client: TestClient, session: Session, version: dict[str, Any], name: str, **params: str) -> dict[str, Any]:
    response = client.get(f"{queries_url(version)}/{name}", params=params, headers=session.headers)
    assert response.status_code == 200, response.text
    answer = response.json()
    assert answer["name"] == name and answer["columns"] == list(QUERIES[name].columns) and not answer["truncated"]
    return answer


def rows_of(answer: dict[str, Any]) -> list[dict[str, Any]]:
    return [dict(zip(answer["columns"], row, strict=True)) for row in answer["rows"]]


def test_a_member_asks_the_walls_their_classes_storey_materials_and_gtin(
    query_client: tuple[TestClient, World],
) -> None:
    client, world = query_client
    editor = login_as(client, world, "editor")
    web_sign_in(client, world, "editor")  # the upload page asks for a browser session
    walls = upload(client, world, editor, "three_walls_gtin.ifc", (FIXTURES_DIR / "three_walls_gtin.ifc").read_bytes())
    listed = converted(client, editor, walls)
    assert listed["model_state"] == "done"
    assert [query["name"] for query in listed["queries"]] == [*QUERIES, "changed-since"]

    classes = {row["class"]: row["count"] for row in rows_of(ask(client, editor, walls, "element-classes"))}
    assert classes["IfcWallStandardCase"] == 3
    elements = rows_of(ask(client, editor, walls, "elements", **{"class": "IfcWall"}))
    assert {row["global_id"] for row in elements} == WALLS, "a class takes its subclasses with it"
    assert {row["container"] for row in elements} == {"1. etasje"}
    (storey,) = rows_of(ask(client, editor, walls, "storeys"))
    assert storey["name"] == "1. etasje" and storey["elements"] >= 3 and storey["spaces"] == 0
    materials = rows_of(ask(client, editor, walls, "materials", **{"class": "IfcWall"}))
    assert len(materials) == 3 and all(row["materials"] == ["Yttervegg"] for row in materials)
    gtin = rows_of(ask(client, editor, walls, "property", pset="Reuse", property="GTIN"))
    assert sorted(row["value"] for row in gtin) == ["1", "2", "3"] and {row["type"] for row in gtin} == {"IFCLABEL"}
    assert ask(client, editor, walls, "property", pset="Reuse", property="GTIN", **{"class": "IfcDoor"})["rows"] == []
    assert ask(client, editor, walls, "spaces")["rows"] == []
    (wall,) = rows_of(ask(client, editor, walls, "entity", global_id="1Xezbq735AdBO_4DerG66G"))
    assert wall["class"].startswith("IfcWall") and wall["step_id"] == 242 and wall["attributes"]["Name"] == "YVT-A"
    assert {ref["attribute"] for ref in wall["references"]} >= {"OBJECT_PLACEMENT", "REPRESENTATION"}
    back = {ref["attribute"]: ref for ref in wall["referenced_by"]}
    assert (
        back["RELATED_ELEMENTS"]["class"] == "IfcRelContainedInSpatialStructure"
        and back["RELATED_ELEMENTS"]["global_id"]
    )
    assert ask(client, editor, walls, "entity", global_id="0000000000000000000000")["rows"] == []
    assert listed["queries"][-1]["name"] == "changed-since"
    only_the_upload = client.get(f"{queries_url(walls)}/changed-since", params={"since": "0"}, headers=editor.headers)
    assert only_the_upload.status_code == 200, only_the_upload.text
    assert only_the_upload.json()["rows"] == [[1, None, "editor", None, True, None, None, None, None, None]]


def test_spaces_and_the_area_of_their_storey(query_client: tuple[TestClient, World]) -> None:
    client, world = query_client
    editor = login_as(client, world, "editor")
    web_sign_in(client, world, "editor")  # the upload page asks for a browser session
    model = upload(client, world, editor, "two_spaces.ifc", (FIXTURES_DIR / "two_spaces.ifc").read_bytes())
    assert converted(client, editor, model)["model_state"] == "done"

    spaces = rows_of(ask(client, editor, model, "spaces"))
    assert [(row["name"], row["long_name"], row["storey"]) for row in spaces] == [
        ("101", "Kitchen", "Plan 1"),
        ("102", "Living room", "Plan 1"),
    ]
    assert [(row["net_floor_area"], row["gross_floor_area"]) for row in spaces] == [(12.5, 14.0), (20.0, None)]
    (storey,) = rows_of(ask(client, editor, model, "areas"))
    assert (storey["storey"], storey["spaces"], storey["net_floor_area"]) == ("Plan 1", 2, 32.5)


def test_only_a_member_may_ask_and_only_what_is_named(query_client: tuple[TestClient, World]) -> None:
    client, world = query_client
    editor = login_as(client, world, "editor")
    web_sign_in(client, world, "editor")  # the upload page asks for a browser session
    walls = upload(client, world, editor, "three_walls_gtin.ifc", (FIXTURES_DIR / "three_walls_gtin.ifc").read_bytes())
    notes = upload(client, world, editor, "notes.txt", b"not a model")
    converted(client, editor, walls)
    url = queries_url(walls)

    viewer = login_as(client, world, "viewer")
    assert client.get(f"{url}/element-classes", headers=viewer.headers).status_code == 200, "every member may ask"
    outsider = login_as(client, world, "outsider")
    assert client.get(url, headers=outsider.headers).status_code == 404
    assert client.get(f"{url}/element-classes", headers=outsider.headers).status_code == 404
    assert client.get(f"{url}/element-classes").status_code == 401

    def refused(path: str, **params: str) -> tuple[int, str]:
        response = client.get(f"{url}{path}", params=params, headers=editor.headers)
        return response.status_code, response.json().get("message", "")

    assert refused("/no-such-query")[0] == 404
    status, message = refused("/elements", **{"class": "IfcWall) DETACH DELETE (n"})
    assert status == 400 and "IFC class" in message, "a value is only ever a parameter, and this one is no class"
    assert refused("/storeys", limit="5")[0] == 400
    assert refused("/property", pset="Reuse")[0] == 400
    response = client.get(queries_url(notes), headers=editor.headers)
    assert response.status_code == 404 and "no IFC graph" in response.json().get("message", "")
