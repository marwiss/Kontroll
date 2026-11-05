# This file was generated with the assistance of an AI coding tool.
"""Documents API 1.0 end to end: upload flow, download flow, version queries, browser pages."""

from __future__ import annotations

import hashlib
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from opencde.settings import Settings
from tests.conformance.schemas import validate, validate_documents
from tests.integration.conftest_accounts import World, build_world, login_as
from tests.integration.helpers import Session
from tests.integration.test_web_signin import form_token, web_sign_in

pytestmark = [pytest.mark.integration, pytest.mark.conformance]

CALLBACK = "http://127.0.0.1:9/callback?app=1"
WALLS = b"ISO-10303-21;\n" + b"#1=IFCWALL('1Xezbq735AdBO_4DerG66G',$,$,$,$,$,$,$,$);\n" * 60 + b"END-ISO-10303-21;\n"
NOTES = b"%PDF-1.7\n" + b"x" * 500


@pytest.fixture
def world(settings: Settings, clean_database: None) -> World:
    return build_world(settings)


def callback_params(response: Any) -> dict[str, list[str]]:
    assert response.status_code == 302, response.text
    location = response.headers["location"]
    assert location.startswith("http://127.0.0.1:9/callback?app=1&"), location
    return parse_qs(urlsplit(location).query)


def start_upload(client: TestClient, session: Session, files: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
    response = client.post(
        "/documents/1.0/upload-documents",
        json={"callback": {"url": CALLBACK, "expires_in": 600}, "files": files, **extra},
        headers=session.headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    validate_documents(body, "DocumentUploadSessionInitialization")
    return body


def save_metadata(client: TestClient, page_url: str, project_id: str, fields: dict[str, str]) -> str:
    page = client.get(page_url)
    assert page.status_code == 200, page.text[:400]
    response = client.post(
        page_url,
        data={"form_token": form_token(page.text), "project_id": project_id, "action": "save", **fields},
        follow_redirects=False,
    )
    params = callback_params(response)
    return params["upload_documents_url"][0]


def upload_file(client: TestClient, session: Session, instructions: dict[str, Any], data: bytes) -> dict[str, Any]:
    for part in instructions["upload_file_parts"]:
        assert part["http_method"] == "PUT" and part["include_authorization"] is True
        chunk = data[part["content_range_start"] : part["content_range_end"] + 1]
        response = client.put(part["url"], content=chunk, headers=session.headers)
        assert response.status_code == 200, response.text
    completed = client.post(instructions["upload_completion"]["url"], headers=session.headers)
    assert completed.status_code == 200, completed.text
    version = completed.json()
    validate_documents(version, "DocumentVersion")
    return version


def test_upload_flow_versions_and_queries(client: TestClient, world: World) -> None:
    editor = login_as(client, world, "editor")
    viewer = login_as(client, world, "viewer")
    outsider = login_as(client, world, "outsider")

    started = start_upload(
        client,
        editor,
        [{"file_name": "walls.ifc", "session_file_id": "f1"}, {"file_name": "notes.pdf", "session_file_id": "f2"}],
        server_context=world.project_id,
    )
    assert started["max_size_in_bytes"] == client.app.state.settings.max_upload_bytes  # type: ignore[attr-defined]
    page_url = started["upload_ui_url"]
    assert page_url.startswith("http://testserver/documents/1.0/upload-ui/")

    # The browser must be signed in as the user who started the flow.
    anonymous = client.get(page_url, follow_redirects=False)
    assert anonymous.status_code == 302 and anonymous.headers["location"].startswith(
        "/signin?next=%2Fdocuments%2F1.0%2Fupload-ui%2F"
    )
    web_sign_in(client, world, "viewer")
    assert client.get(page_url).status_code == 403, "another account"
    client.cookies.clear()
    web_sign_in(client, world, "editor")
    page = client.get(page_url)
    assert page.status_code == 200 and "walls.ifc" in page.text and "notes.pdf" in page.text
    assert "Building permit" in page.text and "Demolition permit" not in page.text, "only projects with createDocument"

    no_token = client.post(page_url, data={"project_id": world.project_id, "action": "save"}, follow_redirects=False)
    assert no_token.status_code == 400
    cross_site = client.post(
        page_url, data={"action": "save"}, headers={"Sec-Fetch-Site": "cross-site"}, follow_redirects=False
    )
    assert cross_site.status_code == 403

    instructions_url = save_metadata(
        client,
        page_url,
        world.project_id,
        {"title_0": "Walls model", "version_0": "A", "title_1": "Notes", "version_1": "1"},
    )
    assert instructions_url.startswith("http://testserver/documents/1.0/upload-sessions/")
    assert client.get(page_url).status_code == 200, "the user may still go back and change the metadata"

    details = {
        "files": [
            {"session_file_id": "f1", "size_in_bytes": len(WALLS)},
            {"session_file_id": "f2", "size_in_bytes": len(NOTES)},
        ]
    }
    assert client.post(instructions_url, json=details, headers=viewer.headers).status_code == 404, (
        "another user's session"
    )
    too_big = client.post(
        instructions_url,
        json={"files": [{"session_file_id": "f1", "size_in_bytes": 2 * 1024**4}]},
        headers=editor.headers,
    )
    assert too_big.status_code == 413 and too_big.json()["code"] == "upload_too_large"
    unknown_file = client.post(
        instructions_url, json={"files": [{"session_file_id": "nope", "size_in_bytes": 10}]}, headers=editor.headers
    )
    assert unknown_file.status_code == 400
    response = client.post(instructions_url, json=details, headers=editor.headers)
    assert response.status_code == 200, response.text
    assert client.get(page_url).status_code == 404, "once the upload has started the page link is used up"
    plan = response.json()
    validate_documents(plan, "DocumentsToUpload")
    by_id = {doc["session_file_id"]: doc for doc in plan["documents_to_upload"]}
    parts = by_id["f1"]["upload_file_parts"]
    assert len(parts) == -(-len(WALLS) // 1024) and parts[0]["content_range_start"] == 0
    assert parts[-1]["content_range_end"] == len(WALLS) - 1
    assert all(parts[i]["content_range_end"] + 1 == parts[i + 1]["content_range_start"] for i in range(len(parts) - 1))

    # Parts: wrong size and wrong user are refused; completion needs every part.
    first = parts[0]
    assert client.put(first["url"], content=b"short", headers=editor.headers).status_code == 400
    assert client.put(first["url"], content=WALLS[:1024], headers=viewer.headers).status_code == 404
    early = client.post(by_id["f1"]["upload_completion"]["url"], headers=editor.headers)
    assert early.status_code == 400 and "part" in early.json()["message"].lower()

    version = upload_file(client, editor, by_id["f1"], WALLS)
    assert version["version_index"] == 1 and version["version_number"] == "A" and version["title"] == "Walls model"
    assert version["file_description"] == {"name": "walls.ifc", "size_in_bytes": len(WALLS)}
    links = version["links"]
    assert links["document_version_download"]["url"].startswith("http://testserver/documents/1.0/documents/")
    again = client.post(by_id["f1"]["upload_completion"]["url"], headers=editor.headers)
    assert again.status_code == 200 and again.json()["document_id"] == version["document_id"], (
        "completion is idempotent"
    )

    download = client.get(links["document_version_download"]["url"], headers=viewer.headers)
    assert download.status_code == 200 and download.content == WALLS
    assert download.headers["content-type"] == "application/octet-stream"
    assert 'filename="walls.ifc"' in download.headers["content-disposition"]
    assert client.get(links["document_version_download"]["url"], headers=outsider.headers).status_code == 404
    assert client.get(links["document_version_download"]["url"]).status_code == 401
    metadata = client.get(links["document_version_metadata"]["url"], headers=viewer.headers).json()
    validate_documents(metadata, "DocumentMetadata")
    entries = {entry["name"]: entry["value"] for entry in metadata["metadata"]}
    assert entries["sha256"] == [hashlib.sha256(WALLS).hexdigest()] and entries["uploaded_by"] == ["editor"]
    assert client.get(links["document_version"]["url"], headers=viewer.headers).json() == version
    versions = client.get(links["document_versions"]["url"], headers=viewer.headers).json()
    validate_documents(versions, "DocumentVersions")
    assert [v["version_index"] for v in versions["documents"]] == [1]

    # Aggregate query with ETag.
    query = {"document_ids": [version["document_id"], "00000000-0000-0000-0000-000000000000", "junk"]}
    result = client.post("/documents/1.0/document-versions", json=query, headers=viewer.headers)
    assert result.status_code == 200 and result.headers["etag"]
    validate_documents(result.json(), "DocumentQueryResult")
    assert [v["document_id"] for v in result.json()["versions"]] == [version["document_id"]]
    cached = client.post(
        "/documents/1.0/document-versions",
        json=query,
        headers={**viewer.headers, "If-None-Match": result.headers["etag"]},
    )
    assert cached.status_code == 304 and cached.content == b""
    assert client.post("/documents/1.0/document-versions", json=query, headers=outsider.headers).json() == {
        "versions": []
    }

    # Cancel the second file.
    cancel = client.post(by_id["f2"]["upload_cancellation"]["url"], headers=editor.headers)
    assert cancel.status_code == 204
    assert client.post(by_id["f2"]["upload_completion"]["url"], headers=editor.headers).status_code == 400

    # A new version of the existing document, from the client's document_id.
    started = start_upload(
        client, editor, [{"file_name": "walls-v2.ifc", "session_file_id": "g1", "document_id": version["document_id"]}]
    )
    page = client.get(started["upload_ui_url"])
    assert "New version of" in page.text and "Walls model" in page.text
    instructions_url = save_metadata(
        client, started["upload_ui_url"], world.project_id, {"title_0": "ignored", "version_0": "B"}
    )
    plan = client.post(
        instructions_url,
        json={"files": [{"session_file_id": "g1", "size_in_bytes": len(NOTES)}]},
        headers=editor.headers,
    ).json()
    second = upload_file(client, editor, plan["documents_to_upload"][0], NOTES)
    assert second["document_id"] == version["document_id"] and second["version_index"] == 2
    assert second["version_number"] == "B" and second["title"] == "Walls model"
    versions = client.get(links["document_versions"]["url"], headers=viewer.headers).json()
    assert [v["version_index"] for v in versions["documents"]] == [1, 2]
    changed = client.post(
        "/documents/1.0/document-versions",
        json=query,
        headers={**viewer.headers, "If-None-Match": result.headers["etag"]},
    )
    assert changed.status_code == 200 and changed.json()["versions"][0]["version_index"] == 2

    # BCF files information lists the Documents API file too.
    information = client.get(f"/bcf/3.0/projects/{world.project_id}/files_information", headers=viewer.headers).json()
    validate(information, "bcf-api/Schemas/Collaboration/File/project_files_information_GET.json")
    assert [e["file"]["filename"] for e in information] == ["walls-v2.ifc"]
    assert information[0]["file"]["reference"].endswith("/versions/2/download")
    fields = {f["field_display_name"]: f["field_value"] for f in information[0]["display_information"]}
    assert fields["Version index"] == "2" and fields["Source"] == "Documents API"
    assert information[0]["file"]["reference"].endswith(f"/documents/{fields['Document id']}/versions/2/download")

    # Details page in the browser (signed in as editor).
    details_page = client.get(links["document_details"]["url"])
    assert details_page.status_code == 200 and "Walls model" in details_page.text and "walls.ifc" in details_page.text
    browser_download = client.get(links["document_details"]["url"] + "/download")
    assert browser_download.status_code == 200 and browser_download.content == WALLS
    client.cookies.clear()
    assert client.get(links["document_details"]["url"], follow_redirects=False).status_code == 302, "sign in first"


def test_upload_cancelled_in_the_browser(client: TestClient, world: World) -> None:
    editor = login_as(client, world, "editor")
    started = start_upload(client, editor, [{"file_name": "a.ifc", "session_file_id": "a"}])
    web_sign_in(client, world, "editor")
    page = client.get(started["upload_ui_url"])
    cancelled = client.post(
        started["upload_ui_url"], data={"form_token": form_token(page.text), "action": "cancel"}, follow_redirects=False
    )
    assert callback_params(cancelled) == {"app": ["1"], "user_cancelled_upload": ["true"]}
    assert client.get(started["upload_ui_url"]).status_code == 404

    # Contributors cannot upload: the page offers no project to save into.
    contributor = login_as(client, world, "contributor")
    started = start_upload(client, contributor, [{"file_name": "b.ifc", "session_file_id": "b"}])
    client.cookies.clear()
    web_sign_in(client, world, "contributor")
    page = client.get(started["upload_ui_url"])
    assert page.status_code == 200 and "not allowed to add documents" in page.text
    forced = client.post(
        started["upload_ui_url"],
        data={
            "form_token": form_token(page.text),
            "action": "save",
            "project_id": world.project_id,
            "title_0": "x",
            "version_0": "1",
        },
        follow_redirects=False,
    )
    assert forced.status_code == 400

    bad_callback = client.post(
        "/documents/1.0/upload-documents",
        json={
            "callback": {"url": "ftp://x/cb", "expires_in": 60},
            "files": [{"file_name": "a", "session_file_id": "a"}],
        },
        headers=editor.headers,
    )
    assert bad_callback.status_code == 400
    duplicate_ids = client.post(
        "/documents/1.0/upload-documents",
        json={
            "callback": {"url": CALLBACK, "expires_in": 60},
            "files": [{"file_name": "a", "session_file_id": "a"}, {"file_name": "b", "session_file_id": "a"}],
        },
        headers=editor.headers,
    )
    assert duplicate_ids.status_code == 400
    assert client.post("/documents/1.0/upload-documents", json={}, headers=editor.headers).status_code == 400


def test_selection_flow_with_filtering_and_browser_upload(client: TestClient, world: World) -> None:
    editor = login_as(client, world, "editor")
    viewer = login_as(client, world, "viewer")
    outsider = login_as(client, world, "outsider")

    # Two documents in the project: an IFC and a PDF.
    web_sign_in(client, world, "editor")
    for name, data, title in (("walls.ifc", WALLS, "Walls"), ("notes.pdf", NOTES, "Notes")):
        started = start_upload(client, editor, [{"file_name": name, "session_file_id": "f"}])
        instructions_url = save_metadata(
            client, started["upload_ui_url"], world.project_id, {"title_0": title, "version_0": "1"}
        )
        plan = client.post(
            instructions_url,
            json={"files": [{"session_file_id": "f", "size_in_bytes": len(data)}]},
            headers=editor.headers,
        ).json()
        upload_file(client, editor, plan["documents_to_upload"][0], data)

    selection = client.post(
        "/documents/1.0/select-documents",
        json={
            "callback": {"url": CALLBACK, "expires_in": 600},
            "supported_file_extensions": [".ifc"],
            "server_context": "ctx-1",
        },
        headers=viewer.headers,
    )
    assert selection.status_code == 200, selection.text
    validate_documents(selection.json(), "DocumentDiscoverySessionInitialization")
    page_url = selection.json()["select_documents_url"]

    assert client.get(page_url).status_code == 403, "signed in as editor, flow started by viewer"
    client.cookies.clear()
    web_sign_in(client, world, "viewer")
    page = client.get(page_url)
    assert page.status_code == 200 and "Walls" in page.text and "Notes" not in page.text
    assert "1 document with other file types" in page.text and "Upload a file" not in page.text, "viewers cannot upload"
    everything = client.get(page_url, params={"all": "1"})
    assert "Notes" in everything.text

    empty = client.post(
        page_url, data={"form_token": form_token(page.text), "action": "select"}, follow_redirects=False
    )
    assert empty.status_code == 400
    walls_id = page.text.split('name="selected" value="')[1].split('"')[0]
    chosen = client.post(
        page_url,
        data={"form_token": form_token(page.text), "action": "select", "selected": [walls_id]},
        follow_redirects=False,
    )
    selected_url = callback_params(chosen)["selected_documents_url"][0]
    assert client.get(page_url).status_code == 404, "a finished selection cannot be reopened"

    assert client.get(selected_url, headers=editor.headers).status_code == 404, "bound to the user who selected"
    result = client.get(selected_url, headers=viewer.headers)
    assert result.status_code == 200, result.text
    validate_documents(result.json(), "SelectedDocuments")
    assert result.json()["server_context"] == "ctx-1"
    assert [d["title"] for d in result.json()["documents"]] == ["Walls"]
    assert (
        client.get(
            result.json()["documents"][0]["links"]["document_version_download"]["url"], headers=viewer.headers
        ).content
        == WALLS
    )

    # Cancelling sends the browser back with user_cancelled_selection=true.
    second = client.post(
        "/documents/1.0/select-documents",
        json={"callback": {"url": CALLBACK, "expires_in": 600}},
        headers=viewer.headers,
    ).json()
    page = client.get(second["select_documents_url"])
    cancelled = client.post(
        second["select_documents_url"],
        data={"form_token": form_token(page.text), "action": "cancel"},
        follow_redirects=False,
    )
    assert callback_params(cancelled) == {"app": ["1"], "user_cancelled_selection": ["true"]}
    pending = client.post(
        "/documents/1.0/select-documents",
        json={"callback": {"url": CALLBACK, "expires_in": 600}},
        headers=viewer.headers,
    ).json()
    session_id = pending["select_documents_url"].rsplit("/", 1)[-1]
    assert (
        client.get(f"/documents/1.0/selection-sessions/{session_id}/documents", headers=viewer.headers).status_code
        == 404
    )

    # Outsiders see nothing.
    assert (
        client.post(
            "/documents/1.0/select-documents",
            json={"callback": {"url": CALLBACK, "expires_in": 600}},
            headers=outsider.headers,
        ).status_code
        == 200
    )
    assert client.get(f"/documents/1.0/documents/{walls_id}/versions", headers=outsider.headers).status_code == 404

    # Editors can upload straight from the selection page; the new document is listed.
    client.cookies.clear()
    web_sign_in(client, world, "editor")
    third = client.post(
        "/documents/1.0/select-documents",
        json={"callback": {"url": CALLBACK, "expires_in": 600}},
        headers=editor.headers,
    ).json()
    page = client.get(third["select_documents_url"])
    assert "Upload a file" in page.text
    uploaded = client.post(
        third["select_documents_url"] + "/upload",
        data={"form_token": form_token(page.text), "project_id": world.project_id, "title": "Site plan"},
        files={"file": ("site plan.ifc", b"ISO-10303-21;\nENDSEC;\n", "application/octet-stream")},
        follow_redirects=False,
    )
    assert uploaded.status_code == 303, uploaded.text
    refreshed = client.get(third["select_documents_url"])
    assert "Site plan" in refreshed.text and "site plan.ifc" in refreshed.text
    empty_file = client.post(
        third["select_documents_url"] + "/upload",
        data={"form_token": form_token(page.text), "project_id": world.project_id},
        files={"file": ("empty.ifc", b"", "application/octet-stream")},
        follow_redirects=False,
    )
    assert empty_file.status_code == 400
    wrong_project = client.post(
        third["select_documents_url"] + "/upload",
        data={"form_token": form_token(page.text), "project_id": world.other_project_id},
        files={"file": ("x.ifc", b"data", "application/octet-stream")},
        follow_redirects=False,
    )
    assert wrong_project.status_code == 403
