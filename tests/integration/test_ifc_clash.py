# This file was generated with the assistance of an AI coding tool.
"""The clash check between two document versions, as a member, with topics made of its findings (ADR 0019)."""

from __future__ import annotations

import time
from typing import Any

import pytest
from fastapi.testclient import TestClient

from opencde.main import create_app
from tests.conftest import FIXTURES_DIR
from tests.integration.conftest import GraphTarget
from tests.integration.conftest_accounts import build_world, login_as
from tests.integration.helpers import Session
from tests.integration.test_ifc_validation import settings_for, upload
from tests.integration.test_web_signin import web_sign_in

pytestmark = pytest.mark.integration
pytest.importorskip("ifcclash", reason="the ifc-lpg extra is not installed")


def shifted_copy() -> bytes:
    """The wall fixture with new GlobalIds and its walls moved sideways and up, so that they clash with the original."""
    import ifcopenshell
    import ifcopenshell.guid

    model = ifcopenshell.open(str(FIXTURES_DIR / "three_walls_gtin.ifc"))
    for wall in model.by_type("IfcWall"):
        wall.GlobalId = ifcopenshell.guid.new()
        location = wall.ObjectPlacement.RelativePlacement.Location
        x, y, z = location.Coordinates
        location.Coordinates = (x, y + 0.1, z + 0.3)
    return model.to_string().encode("utf-8")


def wait_for(client: TestClient, session: Session, url: str) -> dict[str, Any]:
    deadline = time.monotonic() + 300
    while True:
        response = client.get(url, headers=session.headers)
        assert response.status_code == 200, response.text
        report = response.json()
        if report["state"] in ("done", "failed"):
            return report
        assert time.monotonic() < deadline, "the clash check did not finish in time"
        time.sleep(0.5)


def test_a_member_compares_two_versions_and_makes_topics_of_the_clashes(
    graph_target: GraphTarget, clean_database: None, tmp_path: Any
) -> None:
    settings = settings_for(graph_target, tmp_path, ifcgraph_clash_enabled=True, ifcgraph_validate_uploads=False)
    world = build_world(settings)
    with TestClient(create_app(settings, startup_wait_seconds=30)) as client:
        editor = login_as(client, world, "editor")
        web_sign_in(client, world, "editor")  # the upload page asks for a browser session
        viewer = login_as(client, world, "viewer")
        original = upload(client, world, editor, "walls.ifc", (FIXTURES_DIR / "three_walls_gtin.ifc").read_bytes())
        moved = upload(client, world, editor, "walls-moved.ifc", shifted_copy())
        base = f"/documents/1.0/projects/{world.project_id}/ifc-clash"
        request = {
            "a": {"document_id": original["document_id"], "version_index": original["version_index"]},
            "b": {"document_id": moved["document_id"], "version_index": moved["version_index"], "types": ["IfcWall"]},
            "mode": "intersection",
            "tolerance": 0.001,
        }

        assert client.post(base, json={**request, "mode": "collision"}, headers=editor.headers).status_code == 400
        started = client.post(base, json=request, headers=editor.headers)
        assert started.status_code == 202, started.text
        assert started.json()["state"] == "queued" and started.headers["Location"] == started.json()["url"]
        report = wait_for(client, viewer, started.json()["url"])
        assert report["state"] == "done", report.get("error")
        assert report["count"] >= 1 and report["set_a"] == 3 and report["set_b"] == 3 and not report["truncated"]
        clash = report["clashes"][0]
        assert clash["kind"] == "intersection" and clash["depth"] > 0.001 and len(clash["point"]) == 3
        assert clash["a"]["document_id"] == original["document_id"] and clash["a"]["version_index"] == 1
        assert clash["b"]["document_id"] == moved["document_id"] and clash["b"]["guid"] != clash["a"]["guid"]
        assert clash["a"]["type"].startswith("IfcWall") and clash["a"]["storey"]

        listed = client.get(base, headers=viewer.headers).json()
        assert [row["id"] for row in listed] == [report["id"]] and "clashes" not in listed[0]

        # Topics are made only on request, by someone who may create topics; the viewer may not.
        topics_url = f"{base}/{report['id']}/topics"
        assert client.post(topics_url, json={"clashes": [0]}, headers=viewer.headers).status_code == 403
        made = client.post(topics_url, json={"clashes": [0]}, headers=editor.headers)
        assert made.status_code == 201, made.text
        topic = made.json()[0]
        assert topic["clash"] == 0 and "against" in topic["title"]
        got = client.get(f"/bcf/3.0/projects/{world.project_id}/topics/{topic['topic_guid']}", headers=editor.headers)
        assert got.status_code == 200 and got.json()["title"] == topic["title"]
        viewpoint_url = (
            f"/bcf/3.0/projects/{world.project_id}/topics/{topic['topic_guid']}/viewpoints/{topic['viewpoint_guid']}"
        )
        viewpoint = client.get(viewpoint_url, headers=editor.headers).json()
        assert viewpoint["perspective_camera"]["camera_up_vector"]["z"] == 1
        selection = client.get(f"{viewpoint_url}/selection", headers=editor.headers).json()["selection"]
        assert {component["ifc_guid"] for component in selection} == {clash["a"]["guid"], clash["b"]["guid"]}
        past_the_end = client.post(topics_url, json={"clashes": [report["count"]]}, headers=editor.headers)
        assert past_the_end.status_code == 400

        # Someone outside the project cannot tell the check exists.
        outsider = login_as(client, world, "outsider")
        assert client.get(started.json()["url"], headers=outsider.headers).status_code == 404
        assert client.post(base, json=request, headers=outsider.headers).status_code == 404


def test_a_version_that_is_not_an_ifc_file_fails_the_check(
    graph_target: GraphTarget, clean_database: None, tmp_path: Any
) -> None:
    settings = settings_for(graph_target, tmp_path, ifcgraph_clash_enabled=True, ifcgraph_validate_uploads=False)
    world = build_world(settings)
    with TestClient(create_app(settings, startup_wait_seconds=30)) as client:
        editor = login_as(client, world, "editor")
        web_sign_in(client, world, "editor")  # the upload page asks for a browser session
        walls = upload(client, world, editor, "walls.ifc", (FIXTURES_DIR / "three_walls_gtin.ifc").read_bytes())
        text = upload(client, world, editor, "notes.txt", b"not a model")
        base = f"/documents/1.0/projects/{world.project_id}/ifc-clash"
        started = client.post(
            base,
            json={
                "a": {"document_id": walls["document_id"], "version_index": 1},
                "b": {"document_id": text["document_id"], "version_index": 1},
            },
            headers=editor.headers,
        )
        assert started.status_code == 202
        report = wait_for(client, editor, started.json()["url"])
        assert report["state"] == "failed" and "not an IFC file" in report["error"]
