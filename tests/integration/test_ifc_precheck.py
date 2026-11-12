# This file was generated with the assistance of an AI coding tool.
"""A file checked without becoming a version, and a project that refuses uploads with validation errors (ADR 0021)."""

from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from opencde.main import create_app
from tests.integration.conftest import GraphTarget
from tests.integration.conftest_accounts import World, build_world, login_as, login_with_scope
from tests.integration.helpers import Session
from tests.integration.test_documents_api import save_metadata, start_upload
from tests.integration.test_ifc_validation import MODEL, WALLS, settings_for, upload
from tests.integration.test_web_signin import form_token, web_sign_in

pytestmark = pytest.mark.integration
pytest.importorskip("ifcopenshell", reason="the ifc-db extra is not installed")

CALLBACK = "https://app.example/callback"


@pytest.fixture
def ifc_client(graph_target: GraphTarget, clean_database: None, tmp_path: Any) -> Iterator[tuple[TestClient, World]]:
    settings = settings_for(graph_target, tmp_path)
    world = build_world(settings)
    with TestClient(create_app(settings, startup_wait_seconds=30)) as client:
        yield client, world


def wait_for(client: TestClient, session: Session, url: str) -> dict[str, Any]:
    deadline = time.monotonic() + 240
    while True:
        response = client.get(url, headers=session.headers)
        assert response.status_code == 200, response.text
        report = response.json()
        if report["status"] != "pending":
            return report
        assert time.monotonic() < deadline, "the precheck did not finish in time"
        time.sleep(0.5)


def send(client: TestClient, world: World, session: Session, name: str, data: bytes) -> httpx.Response:
    """Upload a file through the Documents API and return the completion's answer, whatever it is."""
    started = start_upload(client, session, [{"file_name": name, "session_file_id": "m"}])
    instructions_url = save_metadata(
        client, started["upload_ui_url"], world.project_id, {"title_0": name, "version_0": "1"}
    )
    plan = client.post(
        instructions_url,
        json={"files": [{"session_file_id": "m", "size_in_bytes": len(data)}]},
        headers=session.headers,
    ).json()["documents_to_upload"][0]
    for part in plan["upload_file_parts"]:
        put = client.put(
            part["url"],
            content=data[part["content_range_start"] : part["content_range_end"] + 1],
            headers=session.headers,
        )
        assert put.status_code == 200, put.text
    return client.post(plan["upload_completion"]["url"], headers=session.headers)


def documents_in(client: TestClient, admin: Session, project_id: str) -> int:
    return int(client.get(f"/admin/api/projects/{project_id}", headers=admin.headers).json()["documents"])


def test_a_member_checks_a_file_first_and_a_project_can_refuse_errors(ifc_client: tuple[TestClient, World]) -> None:
    client, world = ifc_client
    editor = login_as(client, world, "editor")
    web_sign_in(client, world, "editor")
    viewer = login_as(client, world, "viewer")
    outsider = login_as(client, world, "outsider")
    admin = login_with_scope(client, world, "admin", "profile admin")
    bad = MODEL.read_bytes().replace(WALLS[1].encode(), WALLS[0].encode())
    base = f"/documents/1.0/projects/{world.project_id}/ifc-precheck"
    as_ifc = {"Content-Disposition": 'attachment; filename="twice.ifc"'}

    # The precheck: editors start it, every member reads it, nobody else does.
    assert client.post(base, content=bad, headers={**viewer.headers, **as_ifc}).status_code == 403
    assert client.post(base, content=bad, headers={**outsider.headers, **as_ifc}).status_code == 404
    not_ifc = {"Content-Disposition": 'attachment; filename="notes.txt"'}
    assert client.post(base, content=b"notes", headers={**editor.headers, **not_ifc}).status_code == 400
    assert client.post(base, content=b"", headers={**editor.headers, **as_ifc}).status_code == 400
    started = client.post(base, content=bad, headers={**editor.headers, **as_ifc})
    assert started.status_code == 202, started.text
    url = started.json()["url"]
    assert started.headers["Location"] == url and url.startswith(f"http://testserver{base}/")
    assert started.json()["status"] == "pending" and started.json()["file_name"] == "twice.ifc"
    assert started.json()["expires_at"] > started.json()["created_at"]
    report = wait_for(client, viewer, url)
    assert report["status"] == "issues" and report["error_count"] >= 1
    assert any(issue["global_id"] == WALLS[0] and "IfcRoot.UR1" in issue["message"] for issue in report["issues"])
    assert client.get(url, headers=outsider.headers).status_code == 404
    assert client.get(url).status_code == 401
    assert client.get(base + "/not-an-id", headers=editor.headers).status_code == 404
    assert documents_in(client, admin, world.project_id) == 0, "a precheck is not a document"

    # The project refuses the file once the administrator says so; the report of the refused file can be read.
    turned_on = client.put(
        f"/admin/api/projects/{world.project_id}", json={"block_on_validation_errors": True}, headers=admin.headers
    )
    assert turned_on.status_code == 200 and turned_on.json()["block_on_validation_errors"] is True
    refused = send(client, world, editor, "twice.ifc", bad)
    assert refused.status_code in (422, 200), refused.text  # 200 once the keep-alive whitespace has started
    body = refused.json()
    assert body["code"] == "ifc_validation_failed" and "does not accept" in body["message"]
    assert client.get(body["report"], headers=viewer.headers).json()["status"] == "issues"
    assert documents_in(client, admin, world.project_id) == 0, "the refused file made no version"

    # A clean file goes through, checked once: its result is there as soon as the version is.
    accepted = send(client, world, editor, "three_walls_gtin.ifc", MODEL.read_bytes())
    assert accepted.status_code == 200, accepted.text
    version = accepted.json()
    metadata = client.get(version["links"]["document_version_metadata"]["url"], headers=editor.headers).json()
    entries = {entry["name"]: entry["value"] for entry in metadata["metadata"]}
    assert entries["ifc_validation_status"] == ["passed"] and entries["ifc_validation_issues"] == ["0"]
    report_url = entries["ifc_validation_report"][0]
    assert client.get(report_url, headers=viewer.headers).json()["status"] == "passed"
    notes = upload(client, world, editor, "notes.txt", b"not a model")
    assert notes["version_index"] == 1, "a file that is not IFC is not checked, and not refused"

    # The page refuses the file too.
    selection = client.post(
        "/documents/1.0/select-documents",
        json={"callback": {"url": CALLBACK, "expires_in": 600}},
        headers=editor.headers,
    ).json()
    page = client.get(selection["select_documents_url"], headers={"Accept-Language": "en"})
    from_page = client.post(
        selection["select_documents_url"] + "/upload",
        data={"form_token": form_token(page.text), "project_id": world.project_id, "title": "Twice"},
        files={"file": ("twice.ifc", bad, "application/octet-stream")},
        headers={"Accept-Language": "en"},
        follow_redirects=False,
    )
    assert from_page.status_code == 422 and "does not accept such files" in from_page.text
    assert documents_in(client, admin, world.project_id) == 2

    # Off again: the same file is stored, and checked afterwards as before.
    turned_off = client.put(
        f"/admin/api/projects/{world.project_id}", json={"block_on_validation_errors": False}, headers=admin.headers
    )
    assert turned_off.json()["block_on_validation_errors"] is False
    stored = send(client, world, editor, "twice.ifc", bad)
    assert stored.status_code == 200, stored.text
