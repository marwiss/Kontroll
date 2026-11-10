# This file was generated with the assistance of an AI coding tool.
"""An upload that names the version it builds on is refused with 412 once the document has moved on (ADR 0021)."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from opencde.settings import Settings
from tests.integration.conftest_accounts import World, build_world, login_as
from tests.integration.helpers import Session
from tests.integration.test_documents_api import save_metadata, start_upload, upload_file
from tests.integration.test_web_signin import web_sign_in

pytestmark = pytest.mark.integration


@pytest.fixture
def world(settings: Settings, clean_database: None) -> World:
    return build_world(settings)


def _instructions(
    client: TestClient, session: Session, world: World, file: dict[str, Any], size: int
) -> dict[str, Any]:
    started = start_upload(client, session, [file])
    url = save_metadata(
        client, started["upload_ui_url"], world.project_id, {"title_0": file["file_name"], "version_0": "1"}
    )
    plan = client.post(
        url,
        json={"files": [{"session_file_id": file["session_file_id"], "size_in_bytes": size}]},
        headers=session.headers,
    )
    assert plan.status_code == 200, plan.text
    return plan.json()["documents_to_upload"][0]


def test_an_upload_on_an_outdated_base_is_refused(client: TestClient, world: World) -> None:
    editor = login_as(client, world, "editor")
    web_sign_in(client, world, "editor")
    first = upload_file(
        client, editor, _instructions(client, editor, world, {"file_name": "a.txt", "session_file_id": "f"}, 3), b"one"
    )
    document_id = first["document_id"]
    assert first["version_index"] == 1

    # Two uploads build on version 1; the first becomes version 2, the second is refused.
    on_one = {"file_name": "a.txt", "session_file_id": "f", "document_id": document_id, "base_version_index": 1}
    plan_a = _instructions(client, editor, world, on_one, 3)
    plan_b = _instructions(client, editor, world, on_one, 5)
    second = upload_file(client, editor, plan_a, b"two")
    assert second["version_index"] == 2
    for part in plan_b["upload_file_parts"]:
        assert (
            client.put(
                part["url"],
                content=b"three"[part["content_range_start"] : part["content_range_end"] + 1],
                headers=editor.headers,
            ).status_code
            == 200
        )
    refused = client.post(plan_b["upload_completion"]["url"], headers=editor.headers)
    assert refused.status_code == 412, refused.text
    assert refused.json()["code"] == "version_conflict" and "latest version is 2" in refused.json()["message"]
    versions = client.get(f"/documents/1.0/documents/{document_id}/versions", headers=editor.headers).json()
    assert [v["version_index"] for v in versions["documents"]] == [1, 2], "the refused upload left no version"

    # The version that went through records its base in its metadata.
    metadata = client.get(f"/documents/1.0/documents/{document_id}/versions/2/metadata", headers=editor.headers).json()
    assert {"name": "base_version_index", "value": ["1"], "data_type": "integer32"} in metadata["metadata"]
    first_metadata = client.get(
        f"/documents/1.0/documents/{document_id}/versions/1/metadata", headers=editor.headers
    ).json()
    assert all(entry["name"] != "base_version_index" for entry in first_metadata["metadata"])

    # A base without a document is a mistake the client made.
    bad = client.post(
        "/documents/1.0/upload-documents",
        json={
            "callback": {"url": "https://app.example/callback", "expires_in": 600},
            "files": [{"file_name": "b.txt", "session_file_id": "g", "base_version_index": 1}],
        },
        headers=editor.headers,
    )
    assert bad.status_code == 400 and "document_id" in bad.json()["message"]
