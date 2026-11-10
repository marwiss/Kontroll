# This file was generated with the assistance of an AI coding tool.
"""A building of one model into another project's model (IFC-LPG F21 a and F22 a): the report, the choices, the job
a manager starts, and the next version of A's document that it becomes, while A and B stay as they were."""

from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from opencde.main import create_app
from tests.integration.conftest import GraphTarget
from tests.integration.conftest_accounts import World, build_world, login_as
from tests.integration.helpers import Session
from tests.integration.test_ifc_unreachable import graph_check
from tests.integration.test_ifc_validation import MODEL, settings_for, upload
from tests.integration.test_web_signin import web_sign_in

pytestmark = pytest.mark.integration

BUILDING = "3AMeTOOFsdVLZuNV0$27s5"
WALL = "1Xezbq735AdBO_4DerG66G"


@pytest.fixture
def ifc_client(graph_target: GraphTarget, clean_database: None, tmp_path: Any) -> Iterator[tuple[TestClient, World]]:
    settings = settings_for(graph_target, tmp_path)
    world = build_world(settings)
    with TestClient(create_app(settings, startup_wait_seconds=30)) as client:
        yield client, world


def finished(client: TestClient, session: Session, url: str) -> dict[str, Any]:
    deadline = time.monotonic() + 300
    while True:
        body = client.get(url, headers=session.headers).json()
        if body["state"] not in ("queued", "running"):
            return body
        assert time.monotonic() < deadline, "the merge did not finish in time"
        time.sleep(0.5)


def test_a_manager_brings_a_building_into_the_model_as_its_next_version(ifc_client: tuple[TestClient, World]) -> None:
    client, world = ifc_client
    editor = login_as(client, world, "editor")
    web_sign_in(client, world, "editor")
    manager = login_as(client, world, "manager")
    a = upload(client, world, editor, "a.ifc", MODEL.read_bytes())
    b = upload(client, world, editor, "b.ifc", MODEL.read_bytes().replace(b"'YVT-A'", b"'YVT-Z'", 1))
    graph_check(client, editor, a["document_id"], 1)
    graph_check(client, editor, b["document_id"], 1)
    url = f"/documents/1.0/projects/{world.project_id}/ifc-merge"
    request: dict[str, Any] = {
        "base": {"document_id": a["document_id"], "version_index": 1},
        "other": {"project_id": world.project_id, "document_id": b["document_id"], "version_index": 1},
        "building": BUILDING,
    }

    report = client.post(url + "/report", json=request, headers=editor.headers)
    assert report.status_code == 200, report.text
    found = report.json()
    assert found["base"] == request["base"] and found["other"] == request["other"], "the versions, not the models"
    differing = [c for c in found["collisions"] if not c["same"]]
    assert [c["global_id"] for c in differing] == [WALL] and differing[0]["choice"] is None
    assert all(c["choice"] == "a" for c in found["collisions"] if c["same"]), "the same content keeps A's"
    nowhere = client.post(url + "/report", json={**request, "building": "0" * 22}, headers=editor.headers)
    assert nowhere.status_code == 422 and "has no building" in nowhere.json()["message"]

    assert client.post(url, json=request, headers=editor.headers).status_code == 403, "an editor does not merge"
    outsider = login_as(client, world, "outsider")
    assert client.post(url + "/report", json=request, headers=outsider.headers).status_code == 404
    assert client.post(url, json=request).status_code == 401

    open_choice = client.post(url, json=request, headers=manager.headers)
    assert open_choice.status_code == 202, open_choice.text
    assert open_choice.headers["location"].endswith(open_choice.json()["merge_id"])
    conflict = finished(client, manager, open_choice.json()["url"])
    assert conflict["state"] == "conflict" and "version_index" not in conflict
    assert [c["global_id"] for c in conflict["report"]["collisions"] if c["choice"] is None] == [WALL]

    chosen = client.post(url, json={**request, "choices": {WALL: "b"}}, headers=manager.headers)
    assert chosen.status_code == 202, chosen.text
    done = finished(client, editor, chosen.json()["url"])
    assert done["state"] == "done", done
    assert done["version_index"] == 2 and done["author"] == "manager"
    versions = client.get(a["links"]["document_versions"]["url"], headers=editor.headers).json()["documents"]
    assert [version["version_index"] for version in versions] == [1, 2]
    second = versions[1]
    metadata = client.get(second["links"]["document_version_metadata"]["url"], headers=editor.headers).json()
    entries = {entry["name"]: entry["value"] for entry in metadata["metadata"]}
    assert entries["merged_building"] == [BUILDING] and entries["merged_from_document"] == [b["document_id"]]
    assert entries["base_version_index"] == ["1"] and entries["approved_by"] == ["manager"]
    merged = client.get(second["links"]["document_version_download"]["url"], headers=editor.headers).content
    assert b"'YVT-Z'" in merged and b"'YVT-A'" not in merged, "B's wall took the place of A's"
    first = client.get(a["links"]["document_version_download"]["url"], headers=editor.headers).content
    assert first == MODEL.read_bytes(), "A's version is as it was"
    graph_check(client, editor, a["document_id"], 2)  # the new version is converted and checked as an upload is

    stale = client.post(url, json={**request, "default": "a"}, headers=manager.headers)
    assert stale.status_code == 412 and stale.json()["code"] == "version_conflict", "version 1 is no longer the latest"
    viewer = login_as(client, world, "viewer")
    assert client.get(done["url"], headers=viewer.headers).json()["state"] == "done", "every member follows it"
    assert client.get(done["url"], headers=outsider.headers).status_code == 404


def test_a_model_in_another_length_unit_is_prepared_first(ifc_client: tuple[TestClient, World]) -> None:
    """IFC-LPG F25 a: B in metres is refused as it is, and a copy of it with A's millimetres stands in for it."""
    client, world = ifc_client
    editor = login_as(client, world, "editor")
    web_sign_in(client, world, "editor")
    manager = login_as(client, world, "manager")
    a = upload(client, world, editor, "a.ifc", MODEL.read_bytes())
    metres = MODEL.read_bytes().replace(
        b"IFCSIUNIT(*,.LENGTHUNIT.,.MILLI.,.METRE.)", b"IFCSIUNIT(*,.LENGTHUNIT.,$,.METRE.)"
    )
    assert metres != MODEL.read_bytes()
    b = upload(client, world, editor, "b.ifc", metres)
    graph_check(client, editor, a["document_id"], 1)
    graph_check(client, editor, b["document_id"], 1)
    url = f"/documents/1.0/projects/{world.project_id}/ifc-merge"
    sides: dict[str, Any] = {
        "base": {"document_id": a["document_id"], "version_index": 1},
        "other": {"project_id": world.project_id, "document_id": b["document_id"], "version_index": 1},
    }
    refused = client.post(url + "/report", json={**sides, "building": BUILDING}, headers=editor.headers)
    assert refused.status_code == 422 and "units differ" in refused.json()["message"]

    viewer = login_as(client, world, "viewer")
    assert client.post(url + "/prepare", json=sides, headers=viewer.headers).status_code == 403
    started = client.post(url + "/prepare", json=sides, headers=editor.headers)
    assert started.status_code == 202, started.text
    assert started.json()["kind"] == "prepare"
    prepared = finished(client, editor, started.json()["url"])
    assert prepared["state"] == "done", prepared
    assert prepared["expires_at"] > prepared["finished_at"], "the copy stands in for a day"

    other = {**sides["other"], "prepared": prepared["merge_id"]}
    report = client.post(url + "/report", json={**sides, "other": other, "building": BUILDING}, headers=editor.headers)
    assert report.status_code == 200, report.text
    assert report.json()["other"] == sides["other"], "the report names B's version, not the copy"
    wrong = {**other, "version_index": 2}
    assert (
        client.post(
            url + "/report", json={**sides, "other": wrong, "building": BUILDING}, headers=editor.headers
        ).status_code
        == 404
    )

    merged = client.post(
        url, json={**sides, "other": other, "building": BUILDING, "default": "a"}, headers=manager.headers
    )
    assert merged.status_code == 202, merged.text
    done = finished(client, manager, merged.json()["url"])
    assert done["state"] == "done" and done["version_index"] == 2, done
