# This file was generated with the assistance of an AI coding tool.
"""A confidential client an administrator approved uploads without the browser page (OB-39): the request names the
project and the titles, the session is ready for the instructions, and the audit log has it."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from opencde.settings import Settings
from tests.integration.conftest_accounts import PASSWORD, REDIRECT, World, build_world, login_as, login_with_scope
from tests.integration.helpers import sign_in
from tests.integration.test_documents_api import CALLBACK, upload_file

pytestmark = pytest.mark.integration


@pytest.fixture
def world(settings: Settings, clean_database: None) -> World:
    return build_world(settings)


def test_an_approved_confidential_client_uploads_without_the_page(client: TestClient, world: World) -> None:
    admin = login_with_scope(client, world, "admin", "profile admin")
    editor_via_app = sign_in(
        client,
        client_id=world.confidential_client_id,
        redirect_uri=REDIRECT,
        username="editor",
        password=PASSWORD,
        client_secret=world.confidential_secret,
    )
    request = {
        "callback": {"url": CALLBACK, "expires_in": 600},
        "project_id": world.project_id,
        "files": [{"file_name": "agent.ifc", "session_file_id": "a", "title": "From an agent", "version_number": "A"}],
    }
    assert client.get("/.well-known/dataregium").json()["extensions"]["headless_uploads"]["enabled"] is True
    assert (
        client.post("/documents/1.0/upload-documents", json=request, headers=editor_via_app.headers).status_code == 403
    ), "not until an administrator approves the client"
    public = login_as(client, world, "editor")
    assert client.post("/documents/1.0/upload-documents", json=request, headers=public.headers).status_code == 403, (
        "never for a public client"
    )
    approved = client.put(
        f"/admin/api/clients/{world.confidential_client_id}", json={"headless_uploads": True}, headers=admin.headers
    )
    assert approved.status_code == 200 and approved.json()["headless_uploads"] is True
    refused = client.put(
        f"/admin/api/clients/{world.public_client_id}", json={"headless_uploads": True}, headers=admin.headers
    )
    assert refused.status_code == 400, "a public client cannot be approved"

    started = client.post("/documents/1.0/upload-documents", json=request, headers=editor_via_app.headers)
    assert started.status_code == 200, started.text
    session_id = started.json()["upload_ui_url"].rsplit("/", 1)[-1]
    assert session_id, "the spec's answer is given all the same"
    # The session is ready for the instructions: the page is not needed.
    sessions = client.app.state.graph  # type: ignore[attr-defined]
    row = client.portal.call(
        sessions.one, "MATCH (s:UploadSession {state: 'metadata'}) RETURN s.id AS id, s.project_id AS project"
    )
    assert row is not None and row["project"] == world.project_id
    instructions = f"/documents/1.0/upload-sessions/{row['id']}/instructions"
    plan = client.post(
        instructions, json={"files": [{"session_file_id": "a", "size_in_bytes": 5}]}, headers=editor_via_app.headers
    )
    assert plan.status_code == 200, plan.text
    version = upload_file(client, editor_via_app, plan.json()["documents_to_upload"][0], b"ISO-1")
    assert version["title"] == "From an agent" and version["version_number"] == "A"
    events = client.get("/admin/api/audit", params={"type": "documents.headless_upload"}, headers=admin.headers).json()
    assert events["items"] and events["items"][0]["client_id"] == world.confidential_client_id
    assert events["items"][0]["details"]["files"] == ["agent.ifc"]

    # A viewer may not add documents, headless or not; a document of another project is refused.
    viewer_via_app = sign_in(
        client,
        client_id=world.confidential_client_id,
        redirect_uri=REDIRECT,
        username="viewer",
        password=PASSWORD,
        client_secret=world.confidential_secret,
    )
    assert (
        client.post("/documents/1.0/upload-documents", json=request, headers=viewer_via_app.headers).status_code == 403
    )
    elsewhere = {
        **request,
        "files": [{**request["files"][0], "document_id": version["document_id"]}],
        "project_id": world.other_project_id,
    }
    assert client.post(
        "/documents/1.0/upload-documents", json=elsewhere, headers=editor_via_app.headers
    ).status_code in (400, 403)
