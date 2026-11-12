# This file was generated with the assistance of an AI coding tool.
"""BCF API 3.2.6 snippets, 3.3 files, 3.6 related topics, 3.7 document references and 3.8 documents."""

from __future__ import annotations

import time
from typing import Any

import pytest
from fastapi.testclient import TestClient

from opencde.main import create_app
from opencde.settings import Settings
from tests.conformance.schemas import validate
from tests.integration.conftest_accounts import World, build_world, login_as
from tests.integration.helpers import Session

pytestmark = [pytest.mark.integration, pytest.mark.conformance]

SCHEMAS = "bcf-api/Schemas/Collaboration"
IFC = b"ISO-10303-21;\nHEADER;\nFILE_DESCRIPTION(('ViewDefinition [CoordinationView]'),'2;1');\nENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n"


@pytest.fixture
def world(settings: Settings, clean_database: None) -> World:
    return build_world(settings)


def make_topic(client: TestClient, world: World, session: Session, **fields: Any) -> dict[str, Any]:
    response = client.post(
        f"/bcf/3.0/projects/{world.project_id}/topics", json={"title": "Topic", **fields}, headers=session.headers
    )
    assert response.status_code == 201, response.text
    return response.json()


def upload(
    client: TestClient, world: World, session: Session, filename: str | None, data: bytes = IFC, **params: str
) -> Any:
    headers = dict(session.headers)
    if filename is not None:
        headers["Content-Disposition"] = filename
    return client.post(f"/bcf/3.0/projects/{world.project_id}/documents", content=data, headers=headers, params=params)


def test_upload_works_with_rate_limits_enabled(settings: Settings, clean_database: None) -> None:
    """3.8.2 with the limiter on: slowapi needs a Response to write its headers into (a deployment found this)."""
    limited = settings.model_copy(update={"rate_limits_enabled": True})
    world = build_world(limited)
    with TestClient(create_app(limited, startup_wait_seconds=30)) as client:
        editor = login_as(client, world, "editor")
        created = upload(client, world, editor, 'attachment; filename="walls.ifc"')
        assert created.status_code == 201, created.text
        assert "x-ratelimit-limit" in created.headers


def test_documents_and_files_information(client: TestClient, world: World) -> None:
    editor = login_as(client, world, "editor")
    contributor = login_as(client, world, "contributor")
    viewer = login_as(client, world, "viewer")
    outsider = login_as(client, world, "outsider")
    base = f"/bcf/3.0/projects/{world.project_id}/documents"

    created = upload(client, world, editor, "attachment; filename*=UTF-8''V%C3%A4ggar.ifc")
    assert created.status_code == 201, created.text
    document = created.json()
    validate(document, f"{SCHEMAS}/Document/document_GET.json")
    assert document["filename"] == "Väggar.ifc"

    chosen = upload(
        client, world, editor, 'attachment; filename="../../etc/passwd"', guid="472AB37A-6122-448E-86FC-86503183B520"
    )
    assert chosen.status_code == 201 and chosen.json() == {
        "guid": "472ab37a-6122-448e-86fc-86503183b520",
        "filename": "passwd",
    }
    assert upload(client, world, editor, None, guid=chosen.json()["guid"]).status_code == 409, "Foundation API 1.5.1"
    assert upload(client, world, editor, None, guid="not-a-uuid").status_code == 400
    unnamed = upload(client, world, editor, None, data=b"%PDF-1.7 ...")
    assert unnamed.status_code == 201 and unnamed.json()["filename"] == "document"

    assert upload(client, world, contributor, None).status_code == 201, "a contributor attaches documents (B-67)"
    assert upload(client, world, viewer, None).status_code == 403
    assert upload(client, world, outsider, None).status_code == 404
    too_big = client.post(base, content=b"x", headers={**editor.headers, "Content-Length": str(2 * 1024**3)})
    assert too_big.status_code == 413

    listed = client.get(base, headers=viewer.headers)
    assert listed.status_code == 200 and [d["filename"] for d in listed.json()] == ["Väggar.ifc", "passwd", "document"]
    for item in listed.json():
        validate(item, f"{SCHEMAS}/Document/document_GET.json")
    assert client.get(base, headers=outsider.headers).status_code == 404

    download = client.get(f"{base}/{document['guid']}", headers=viewer.headers)
    assert download.status_code == 200 and download.content == IFC
    assert download.headers["content-type"] == "application/octet-stream"
    assert download.headers["content-length"] == str(len(IFC))
    assert download.headers[
        "content-disposition"
    ] == "attachment; filename=\"V?ggar.ifc\"; filename*=UTF-8''V%C3%A4ggar.ifc".replace("?", "_")
    assert download.headers["x-content-type-options"] == "nosniff"
    assert client.get(f"{base}/{document['guid']}", headers=outsider.headers).status_code == 404
    assert client.get(f"{base}/00000000-0000-0000-0000-000000000000", headers=viewer.headers).status_code == 404

    information = client.get(f"/bcf/3.0/projects/{world.project_id}/files_information", headers=viewer.headers)
    assert information.status_code == 200
    validate(information.json(), f"{SCHEMAS}/File/project_files_information_GET.json")
    entries = information.json()
    assert len(entries) == 3
    assert {tuple(field["field_display_name"] for field in e["display_information"]) for e in entries} == {
        ("File name", "Uploaded", "Uploaded by", "Source", "Document id", "Version index")
    }, "consistent display fields (BCF 3.3.1)"
    fields = {field["field_display_name"]: field["field_value"] for field in entries[0]["display_information"]}
    assert fields["Document id"] == document["guid"] and fields["Version index"] == "", "a BCF document has no version"
    assert entries[0]["file"]["filename"] == "Väggar.ifc"
    assert entries[0]["file"]["reference"].endswith(
        f"/bcf/3.0/projects/{world.project_id}/documents/{document['guid']}"
    )


def test_document_references(client: TestClient, world: World) -> None:
    editor = login_as(client, world, "editor")
    contributor = login_as(client, world, "contributor")
    viewer = login_as(client, world, "viewer")
    topic = make_topic(client, world, editor)
    base = f"/bcf/3.0/projects/{world.project_id}/topics/{topic['guid']}/document_references"
    document = upload(client, world, editor, 'attachment; filename="plan.pdf"').json()

    external = client.post(
        base, json={"url": "https://example.test/regulations.pdf", "description": "Regulations"}, headers=editor.headers
    )
    assert external.status_code == 201, external.text
    validate(external.json(), f"{SCHEMAS}/DocumentReference/document_reference_GET.json")
    internal = client.post(base, json={"document_guid": document["guid"].upper()}, headers=editor.headers)
    assert internal.status_code == 201 and internal.json()["document_guid"] == document["guid"]
    assert "url" not in internal.json()

    assert (
        client.post(
            base, json={"url": "https://a.test/x", "document_guid": document["guid"]}, headers=editor.headers
        ).status_code
        == 400
    )
    assert client.post(base, json={"description": "nothing"}, headers=editor.headers).status_code == 400
    assert (
        client.post(
            base, json={"document_guid": "00000000-0000-0000-0000-000000000000"}, headers=editor.headers
        ).status_code
        == 400
    )
    assert client.post(base, json={"url": "ftp://files.test/x"}, headers=editor.headers).status_code == 400
    assert client.post(base, json={"url": "https://a.test/x"}, headers=viewer.headers).status_code == 403
    assert client.post(base, json={"url": "https://a.test/x"}, headers=contributor.headers).status_code == 403, (
        "not the author"
    )

    listed = client.get(base, headers=viewer.headers).json()
    assert [r["guid"] for r in listed] == [external.json()["guid"], internal.json()["guid"]]
    updated = client.put(
        f"{base}/{external.json()['guid']}",
        json={"url": "https://example.test/v2.pdf", "description": "v2"},
        headers=editor.headers,
    )
    assert updated.status_code == 200 and updated.json()["description"] == "v2"
    validate(updated.json(), f"{SCHEMAS}/DocumentReference/document_reference_GET.json")
    assert (
        client.put(f"{base}/{topic['guid']}", json={"url": "https://a.test/x"}, headers=editor.headers).status_code
        == 404
    )
    assert (
        client.put(
            f"{base}/{external.json()['guid']}", json={"url": "https://a.test/x"}, headers=viewer.headers
        ).status_code
        == 403
    )


def test_related_topics_and_files(client: TestClient, world: World) -> None:
    editor = login_as(client, world, "editor")
    viewer = login_as(client, world, "viewer")
    a, b, c = (make_topic(client, world, editor, title=name) for name in ("A", "B", "C"))
    base = f"/bcf/3.0/projects/{world.project_id}/topics/{a['guid']}"

    time.sleep(0.002)
    related = client.put(
        f"{base}/related_topics",
        json=[
            {"related_topic_guid": b["guid"]},
            {"related_topic_guid": c["guid"].upper()},
            {"related_topic_guid": b["guid"]},
        ],
        headers=editor.headers,
    )
    assert related.status_code == 200, related.text
    assert related.json() == [{"related_topic_guid": b["guid"]}, {"related_topic_guid": c["guid"]}]
    for item in related.json():
        validate(item, f"{SCHEMAS}/RelatedTopic/related_topic_GET.json")
    assert client.get(f"{base}/related_topics", headers=viewer.headers).json() == related.json()
    assert (
        client.get(f"/bcf/3.0/projects/{world.project_id}/topics/{a['guid']}", headers=viewer.headers).json()[
            "modified_date"
        ]
        > a["modified_date"]
    )
    assert (
        client.put(
            f"{base}/related_topics", json=[{"related_topic_guid": a["guid"]}], headers=editor.headers
        ).status_code
        == 400
    )
    unknown = "00000000-0000-0000-0000-000000000000"
    assert (
        client.put(f"{base}/related_topics", json=[{"related_topic_guid": unknown}], headers=editor.headers).status_code
        == 400
    )
    assert (
        client.put(
            f"{base}/related_topics", json=[{"related_topic_guid": b["guid"]}], headers=viewer.headers
        ).status_code
        == 403
    )
    assert client.put(f"{base}/related_topics", json=[], headers=editor.headers).json() == []

    files = client.put(
        f"{base}/files",
        json=[
            {
                "ifc_project": "0J$yPqHBD12v72y4qF6XcD",
                "filename": "Walls.ifc",
                "date": "2026-11-05T10:00:00+02:00",
                "reference": "https://example.test/walls.ifc",
            },
            {"ifc_project": "1aBcDeFgHiJkLmNoPqRsTu", "reference": "472ab37a-6122-448e-86fc-86503183b520"},
        ],
        headers=editor.headers,
    )
    assert files.status_code == 200, files.text
    for item in files.json():
        validate(item, f"{SCHEMAS}/File/file_GET.json")
    assert (
        files.json()[0]["date"] == "2026-11-05T08:00:00.000Z" and files.json()[1]["filename"] is None
        if "filename" in files.json()[1]
        else True
    )
    assert client.get(f"{base}/files", headers=viewer.headers).json() == files.json()
    assert client.put(f"{base}/files", json=[{"filename": "x"}], headers=viewer.headers).status_code == 403
    assert client.put(f"{base}/files", json=[{"date": "yesterday"}], headers=editor.headers).status_code == 400
    assert client.put(f"{base}/files", json=[], headers=editor.headers).json() == []


def test_bim_snippet_upload_and_download(client: TestClient, world: World) -> None:
    editor = login_as(client, world, "editor")
    viewer = login_as(client, world, "viewer")
    outsider = login_as(client, world, "outsider")
    plain = make_topic(client, world, editor)
    snippet_topic = make_topic(
        client,
        world,
        editor,
        bim_snippet={
            "snippet_type": ".ifc",
            "is_external": True,
            "reference": "https://example.test/model.ifc",
            "reference_schema": "https://standards.buildingsmart.org/IFC/RELEASE/IFC4/ADD2_TC1/",
        },
    )
    topics = f"/bcf/3.0/projects/{world.project_id}/topics"

    assert client.put(f"{topics}/{plain['guid']}/snippet", content=IFC, headers=editor.headers).status_code == 400
    assert client.get(f"{topics}/{plain['guid']}/snippet", headers=editor.headers).status_code == 404
    assert client.get(f"{topics}/{snippet_topic['guid']}/snippet", headers=editor.headers).status_code == 404, (
        "external"
    )

    url = f"{topics}/{snippet_topic['guid']}/snippet"
    assert client.put(url, content=IFC, headers=viewer.headers).status_code == 403
    assert client.put(url, content=IFC, headers=outsider.headers).status_code == 404
    stored = client.put(
        url, content=IFC, headers={**editor.headers, "Content-Disposition": 'attachment; filename="model.ifc"'}
    )
    assert stored.status_code == 200, stored.text
    topic = client.get(f"{topics}/{snippet_topic['guid']}", headers=viewer.headers).json()
    assert topic["bim_snippet"]["is_external"] is False and topic["bim_snippet"]["reference"] == "model.ifc", (
        "BCF 3.2.7"
    )
    download = client.get(url, headers=viewer.headers)
    assert download.status_code == 200 and download.content == IFC
    assert download.headers["content-type"] == "application/octet-stream"
    assert 'filename="model.ifc"' in download.headers["content-disposition"]

    storage = client.app.state.storage  # type: ignore[attr-defined]
    assert storage.exists(f"snippets/{snippet_topic['guid']}.bin")
    assert client.delete(f"{topics}/{snippet_topic['guid']}", headers=editor.headers).status_code == 200
    assert not storage.exists(f"snippets/{snippet_topic['guid']}.bin"), "files go with the topic"
