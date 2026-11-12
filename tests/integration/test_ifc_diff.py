# This file was generated with the assistance of an AI coding tool.
"""Two IFC versions compared element by element, through the API and on the version's page (ADR 0021, OB-30)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from opencde.main import create_app
from tests.integration.conftest import GraphTarget
from tests.integration.conftest_accounts import World, build_world, login_as
from tests.integration.test_documents_api import save_metadata, start_upload, upload_file
from tests.integration.test_ifc_validation import MODEL, WALLS, settings_for, upload
from tests.integration.test_web_signin import web_sign_in
from tests.unit.test_ifc_diff import edited_copy

pytestmark = pytest.mark.integration
pytest.importorskip("ifcopenshell", reason="the ifc-db extra is not installed")


@pytest.fixture
def ifc_client(graph_target: GraphTarget, clean_database: None, tmp_path: Any) -> Iterator[tuple[TestClient, World]]:
    settings = settings_for(graph_target, tmp_path, ifcgraph_validate_uploads=False)
    world = build_world(settings)
    with TestClient(create_app(settings, startup_wait_seconds=30)) as client:
        yield client, world


def test_two_versions_are_compared_through_the_api_and_on_the_page(
    ifc_client: tuple[TestClient, World], tmp_path: Any
) -> None:
    client, world = ifc_client
    editor = login_as(client, world, "editor")
    web_sign_in(client, world, "editor")
    viewer = login_as(client, world, "viewer")
    outsider = login_as(client, world, "outsider")
    assert client.get("/.well-known/dataregium").json()["extensions"]["ifc_diff"]["enabled"] is True
    first = upload(client, world, editor, "three_walls_gtin.ifc", MODEL.read_bytes())
    document_id = first["document_id"]
    edited = tmp_path / "edited.ifc"
    added_guid, removed_guid = edited_copy(edited)
    started = start_upload(
        client, editor, [{"file_name": "three_walls_gtin.ifc", "session_file_id": "e", "document_id": document_id}]
    )
    instructions = save_metadata(
        client, started["upload_ui_url"], world.project_id, {"title_0": "walls", "version_0": "2"}
    )
    plan = client.post(
        instructions,
        json={"files": [{"session_file_id": "e", "size_in_bytes": edited.stat().st_size}]},
        headers=editor.headers,
    ).json()["documents_to_upload"][0]
    second = upload_file(client, editor, plan, edited.read_bytes())
    assert second["version_index"] == 2
    notes = upload(client, world, editor, "notes.txt", b"not a model")

    url = f"/documents/1.0/documents/{document_id}/versions/1/ifc-diff/2"
    report = client.get(url, headers=viewer.headers)
    assert report.status_code == 200, report.text
    body = report.json()
    assert body["a"] == {"document_id": document_id, "version_index": 1}
    assert body["b"] == {"document_id": document_id, "version_index": 2}
    assert [e["guid"] for e in body["added"]] == [added_guid] and [e["guid"] for e in body["removed"]] == [removed_guid]
    changed = {e["guid"]: e for e in body["changed"]}
    assert set(changed) == {WALLS[0]} and changed[WALLS[0]]["storey"] == "1. etasje"
    paths = {a["path"]: a for a in changed[WALLS[0]]["attributes"]}
    assert paths["Name"] == {"path": "Name", "old": "YVT-A", "new": "Renamed"}
    assert paths["Reuse.GTIN"]["new"] == "4" and "ObjectPlacement" in paths
    assert body["same"] > 0 and body["truncated"] is False

    # The other way round, with another document, and what is refused.
    reverse = client.get(f"/documents/1.0/documents/{document_id}/versions/2/ifc-diff/1", headers=viewer.headers).json()
    assert [e["guid"] for e in reverse["added"]] == [removed_guid]
    other = client.get(
        f"/documents/1.0/documents/{document_id}/versions/1/ifc-diff/2?other_document_id={document_id}",
        headers=viewer.headers,
    )
    assert other.status_code == 200 and other.json()["b"]["version_index"] == 2
    assert (
        client.get(f"/documents/1.0/documents/{document_id}/versions/1/ifc-diff/1", headers=viewer.headers).status_code
        == 400
    )
    not_ifc = client.get(
        f"/documents/1.0/documents/{document_id}/versions/1/ifc-diff/1?other_document_id={notes['document_id']}",
        headers=viewer.headers,
    )
    assert not_ifc.status_code == 400 and "not an IFC file" in not_ifc.json()["message"]
    assert client.get(url, headers=outsider.headers).status_code == 404
    assert client.get(url).status_code == 401
    assert (
        client.get(f"/documents/1.0/documents/{document_id}/versions/1/ifc-diff/9", headers=viewer.headers).status_code
        == 404
    )

    # The version's page offers the comparison and shows it as lists.
    details = client.get(first["links"]["document_details"]["url"], headers={"Accept-Language": "en"})
    assert details.status_code == 200 and "Compare with" in details.text and 'name="other"' in details.text
    page = client.get(
        first["links"]["document_details"]["url"] + "/ifc-diff?other=2", headers={"Accept-Language": "en"}
    )
    assert page.status_code == 200, page.text
    assert "Version 1 compared with version 2" in page.text and "Renamed" in page.text and added_guid in page.text
    assert "Reuse.GTIN" in page.text and "Removed" in page.text
    assert client.get(first["links"]["document_details"]["url"] + "/ifc-diff?other=1").status_code == 404
    assert client.get(notes["links"]["document_details"]["url"], headers={"Accept-Language": "en"}).status_code == 200
    assert "Compare with" not in client.get(notes["links"]["document_details"]["url"]).text, "not for a text file"
