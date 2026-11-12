# This file was generated with the assistance of an AI coding tool.
"""Text from files and clients stays data through the whole server (OB-44), with a database and the worker.

The strings and the fixtures made at test time are ``tests/security/test_prompt_injection.py``'s, which proves the
same without a database. Here they go in as an IFC file, an IDS document, BCF topics, comments and viewpoints, a change
set, Documents API titles and file names, and requests; and come back verbatim from the APIs, the named queries and
the MCP endpoint's tools, change nothing but what they name, are escaped on every page, are one string each in the
request and audit logs, and leave the MCP endpoint's list of tools as it was.
"""

from __future__ import annotations

import asyncio
import base64
import csv
import io
import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote

import pytest
from fastapi.testclient import TestClient
from ifc_lpg.ids import MAX_RULE
from neo4j import GraphDatabase

from opencde.bcf.binary import sanitize_filename
from opencde.bcf.events import TEXT_VALUE_LIMIT, TITLE_VALUE_LIMIT
from opencde.bcf.schemas import TITLE_MAX, URL_MAX, VALUE_MAX
from opencde.documents.changes import SCHEMA_PATH, SNIPPET_TYPE
from opencde.documents.routes_publication import archive_names
from opencde.documents.schemas import MAX_VERSION_NUMBER
from opencde.ids import is_uuid
from opencde.main import create_app
from opencde.mcp.queries import MAX_TEXT
from opencde.mcp.registry import MAX_NAME as MCP_NAME
from opencde.settings import Settings
from opencde.store.accounts.projects import MAX_NAME
from tests.integration.conftest import GraphTarget
from tests.integration.conftest_accounts import World, build_world, login_as, login_with_scope
from tests.integration.helpers import Session
from tests.integration.test_bcf_comments_viewpoints import PERSPECTIVE
from tests.integration.test_bcf_links_documents import make_topic
from tests.integration.test_bcf_links_documents import upload as bcf_upload
from tests.integration.test_documents_api import CALLBACK, save_metadata, start_upload, upload_file
from tests.integration.test_ifc_proposal import change_set, tried
from tests.integration.test_ifc_queries import ask, converted, rows_of
from tests.integration.test_ifc_validation import MODEL, checked, settings_for, settled, upload
from tests.integration.test_mcp_server_query import NOTHING, bound, set_policy, tool
from tests.integration.test_mcp_server_query import ask as ask_mcp
from tests.integration.test_web_signin import form_token, web_sign_in
from tests.mcp_support import META, MODERN
from tests.security.test_prompt_injection import (
    CONTROL,
    CONTROL_XML,
    CYPHER,
    GTIN_PATH,
    HANDSHAKE,
    IDS_IDENTIFIERS,
    IDS_NAMES,
    IDS_SPECIFICATIONS,
    INJECTIONS,
    INSTRUCTION,
    LONG,
    SCRIPT,
    TEMPLATE,
    WALL_A,
    WALL_B,
    WALL_C,
    WALLS_TEXT,
    assert_shown_as_data,
    injected_ids,
    injected_model,
    step_string,
    untraced,
    within,
)

pytestmark = [pytest.mark.integration, pytest.mark.security]
pytest.importorskip("ifcopenshell", reason="the ifc-lpg extra is not installed")

SNIPPET = {
    "snippet_type": SNIPPET_TYPE,
    "is_external": False,
    "reference": "changes.json",
    "reference_schema": f"http://testserver{SCHEMA_PATH}",
}
WALL_OF = {"YVT-A": WALL_A, "YVT-B": WALL_B, "YVT-C": WALL_C}
STOREY = "1. etasje"
COUNTED = ("schema", "ifc_project_guid", "entities", "relationships", "skipped", "geometry")
NOTES = b"%PDF-1.7 not a model"
MARKER = "DO-NOT-STORE-THIS-BODY"


@pytest.fixture
def injected(graph_target: GraphTarget, clean_database: None, tmp_path: Path) -> Iterator[tuple[TestClient, World]]:
    """The server with the IFC-LPG module and the request log on."""
    settings = settings_for(graph_target, tmp_path, request_log_enabled=True)
    world = build_world(settings)
    with TestClient(create_app(settings, startup_wait_seconds=30)) as client:
        yield client, world


def report_url(version: dict[str, Any]) -> str:
    return f"http://testserver/documents/1.0/documents/{version['document_id']}/versions/{version['version_index']}/ifc-validation"


def never_quoted(text: str) -> None:
    assert not any(string[:40] in text for string in INJECTIONS), text[:300]


def version_of(name: str) -> str:
    """A version number from the name: the form trims it, and the field holds 50 characters."""
    return name[:MAX_VERSION_NUMBER].strip()


# ---------------------------------------------------------------------------- 1. an IFC file


def test_text_in_an_ifc_file_comes_back_verbatim_and_changes_nothing(injected: tuple[TestClient, World]) -> None:
    """The walls' names, a description and a property value carry the strings: the check and the conversion count
    the same as for the fixture, and the named queries give the text back as it was written."""
    client, world = injected
    editor = login_as(client, world, "editor")
    web_sign_in(client, world, "editor")
    original = upload(client, world, editor, "three_walls_gtin.ifc", MODEL.read_bytes())
    hostile = upload(client, world, editor, "injected.ifc", injected_model())
    for version in (original, hostile):
        entries = checked(client, editor, version)
        assert entries["ifc_validation_status"] == ["passed"] and entries["ifc_validation_issues"] == ["0"]
        assert converted(client, editor, version)["model_state"] == "done"
    reports = [settled(client, editor, report_url(version)) for version in (original, hostile)]
    assert [(r["status"], r["issue_count"], r["error_count"], [c["name"] for c in r["checks"]]) for r in reports] == [
        ("passed", 0, 0, ["schema", "graph"])
    ] * 2
    conversions = client.portal.call(client.app.state.ifcgraph.status, world.project_id)  # type: ignore[attr-defined]
    counted = {c["document_id"]: {name: c.get(name) for name in COUNTED} for c in conversions if c["state"] == "done"}
    assert counted[hostile["document_id"]] == counted[original["document_id"]], "the same model, by every count"

    for name in ("element-classes", "storeys"):
        assert ask(client, editor, hostile, name)["rows"] == ask(client, editor, original, name)["rows"], name
    walls = {
        row["global_id"]: (row["name"], row["container"])
        for row in rows_of(ask(client, editor, hostile, "elements", **{"class": "IfcWall"}))
    }
    assert walls == {WALL_OF[wall]: (name, STOREY) for wall, (name, _description) in WALLS_TEXT.items()}
    for wall, (name, description) in WALLS_TEXT.items():
        (entity,) = rows_of(ask(client, editor, hostile, "entity", global_id=WALL_OF[wall]))
        assert entity["attributes"]["Name"] == name and entity["attributes"]["Description"] == description
        assert entity["class"] == "IfcWallStandardCase"
    gtin = {
        row["global_id"]: row["value"]
        for row in rows_of(ask(client, editor, hostile, "property", pset="Reuse", property="GTIN"))
    }
    assert gtin == {WALL_A: CYPHER, WALL_B: "2", WALL_C: "1"}
    download = client.get(hostile["links"]["document_version_download"]["url"], headers=editor.headers)
    assert download.status_code == 200 and download.content == injected_model(), "the file is kept as it came"


# ---------------------------------------------------------------------------- 4. an IDS document


def test_text_in_an_ids_is_quoted_as_data_in_the_report_and_on_the_page(injected: tuple[TestClient, World]) -> None:
    client, world = injected
    editor = login_as(client, world, "editor")
    web_sign_in(client, world, "editor")
    upload(client, world, editor, "rules.ids", injected_ids())
    model = upload(client, world, editor, "three_walls_gtin.ifc", MODEL.read_bytes())
    entries = checked(client, editor, model)
    assert entries["ifc_validation_status"] == ["issues"], "two of the three specifications fail"
    body = client.get(entries["ifc_validation_report"][0], headers=editor.headers).json()
    (check,) = [check for check in body["checks"] if check["name"] == "ids"]
    assert check["state"] == "done" and check["rules_not_run"] == []
    assert [(s["name"], s.get("identifier"), s["status"]) for s in check["specifications"]] == [
        (name, identifier, verdict)
        for (_kind, verdict), name, identifier in zip(IDS_SPECIFICATIONS, IDS_NAMES, IDS_IDENTIFIERS, strict=True)
    ]
    found = [issue for issue in body["issues"] if issue["kind"] == "ids"]
    assert len(found) == 4 and all(issue["severity"] == "error" for issue in found)
    walls = [issue for issue in found if issue["rule"] == CYPHER[:MAX_RULE]]
    assert {issue["global_id"] for issue in walls} == {WALL_A, WALL_B, WALL_C}
    assert all(issue["message"].startswith(f"{SCRIPT}: ") for issue in walls)
    (door,) = [issue for issue in found if issue["rule"] == TEMPLATE]
    assert door["message"].startswith(f"{TEMPLATE}: required") and door.get("global_id") is None

    page = client.get(model["links"]["document_details"]["url"], headers={"Accept-Language": "en"})
    assert page.status_code == 200 and "IDS check" in page.text
    for text in (SCRIPT, TEMPLATE, CYPHER, CONTROL_XML, LONG):
        assert_shown_as_data(page.text, text)
    assert "{{ 7 * 7 }}" in page.text, "a template in a specification's name is text on the page"


# ---------------------------------------------------------------------------- 3. a change set


def test_a_change_set_with_the_text_changes_only_what_it_names(injected: tuple[TestClient, World]) -> None:
    """The trial applies the text to the attributes the changes name and reports nothing of it; approved, the new
    version holds the text where it was put and the same model everywhere else."""
    client, world = injected
    editor = login_as(client, world, "editor")
    web_sign_in(client, world, "editor")
    manager = login_as(client, world, "manager")
    version = upload(client, world, editor, "three_walls_gtin.ifc", MODEL.read_bytes())
    assert checked(client, editor, version)["ifc_validation_status"] == ["passed"]
    assert converted(client, editor, version)["model_state"] == "done"
    document_id = version["document_id"]
    topics = f"/bcf/3.0/projects/{world.project_id}/topics"
    changes = [
        {"guid": WALL_A, "attribute": "Name", "op": "set", "old": "YVT-A", "new": INSTRUCTION},
        {"guid": WALL_A, "attribute": "Description", "op": "set", "new": CYPHER},
        {
            "guid": WALL_A,
            "path": GTIN_PATH,
            "attribute": "NominalValue",
            "op": "set",
            "new": {"type": "IfcLabel", "value": SCRIPT},
        },
        {"guid": WALL_B, "attribute": "Name", "op": "set", "new": CONTROL},
        {"guid": WALL_B, "attribute": "Description", "op": "set", "new": LONG},
        {"guid": WALL_C, "attribute": "Name", "op": "set", "new": TEMPLATE},
    ]
    topic = make_topic(client, world, editor, bim_snippet=SNIPPET)
    snippet = f"{topics}/{topic['guid']}/snippet"
    proposal = f"{topics}/{topic['guid']}/ifc-proposal"
    assert client.put(snippet, content=change_set(document_id, *changes), headers=editor.headers).status_code == 200
    assert client.get(snippet, headers=editor.headers).json()["changes"] == changes, "the snippet is kept as sent"
    report = tried(client, editor, proposal)
    assert report["state"] == "clean" and report["applied"] == 6 and report["change_count"] == 6, report
    never_quoted(json.dumps(report))

    approved = client.post(proposal + "/approve", headers=manager.headers)
    assert approved.status_code == 201, approved.text
    new = approved.json()
    assert new["version_index"] == 2
    stored = client.get(new["links"]["document_version"]["url"] + "/ifc-changes", headers=editor.headers).json()
    assert stored["changes"] == changes
    since = client.get(
        new["links"]["document_version"]["url"] + "/ifc-queries/changed-since",
        params={"since": "1"},
        headers=editor.headers,
    ).json()
    assert [(row[5], row[8], row[9]) for row in since["rows"]] == [(c["guid"], c["attribute"], "set") for c in changes]
    assert converted(client, editor, new)["model_state"] == "done"
    for guid, name, description in ((WALL_A, INSTRUCTION, CYPHER), (WALL_B, CONTROL, LONG), (WALL_C, TEMPLATE, None)):
        (entity,) = rows_of(ask(client, editor, new, "entity", global_id=guid))
        assert entity["attributes"]["Name"] == name
        if description is not None:
            assert entity["attributes"]["Description"] == description
    gtin = {
        row["global_id"]: row["value"]
        for row in rows_of(ask(client, editor, new, "property", pset="Reuse", property="GTIN"))
    }
    assert gtin == {WALL_A: SCRIPT, WALL_B: "2", WALL_C: "1"}
    for name in ("element-classes", "storeys"):
        assert ask(client, editor, new, name)["rows"] == ask(client, editor, version, name)["rows"], name
    download = client.get(new["links"]["document_version_download"]["url"], headers=editor.headers)
    assert download.status_code == 200 and step_string(INSTRUCTION).encode("ascii") in download.content

    # The text where only a name may stand is refused at the upload, in words that never repeat it.
    for change in (
        {"guid": WALL_A, "path": SCRIPT, "attribute": "Name", "op": "set", "new": "x"},
        {"guid": WALL_A, "attribute": CYPHER, "op": "set", "new": "x"},
        {"guid": INSTRUCTION[:22], "attribute": "Name", "op": "set", "new": "x"},
    ):
        other = make_topic(client, world, editor, bim_snippet=SNIPPET)
        refused = client.put(
            f"{topics}/{other['guid']}/snippet", content=change_set(document_id, change), headers=editor.headers
        )
        assert refused.status_code == 400, refused.text
        never_quoted(refused.text)
    # A change that cannot be applied is an issue that names the change, never the values.
    stale = make_topic(client, world, editor, bim_snippet=SNIPPET)
    old_value = {"guid": WALL_A, "attribute": "Name", "op": "set", "old": CYPHER, "new": SCRIPT}
    assert (
        client.put(
            f"{topics}/{stale['guid']}/snippet", content=change_set(document_id, old_value), headers=editor.headers
        ).status_code
        == 200
    )
    report = tried(client, editor, f"{topics}/{stale['guid']}/ifc-proposal")
    assert report["state"] == "issues" and report["applied"] == 0
    assert [issue["message"] for issue in report["issues"] if issue["kind"] == "proposal"] == [
        "change 0: Name no longer holds the old value"
    ]
    never_quoted(json.dumps(report))


# ---------------------------------------------------------------------------- 2. BCF topics, comments and viewpoints


def test_bcf_text_is_stored_and_returned_verbatim(injected: tuple[TestClient, World]) -> None:
    """Titles, descriptions, reference links, comments and the components of a viewpoint come back as they went in,
    through BCF 3.0 and 2.1, in the events (cut at their limits) and as parameters of a filter."""
    client, world = injected
    editor = login_as(client, world, "editor")
    viewer = login_as(client, world, "viewer")
    topics = f"/bcf/3.0/projects/{world.project_id}/topics"
    for text in INJECTIONS:
        title = text[:TITLE_MAX]
        body: dict[str, Any] = {"title": title, "description": text}
        if len(text) <= URL_MAX:
            body["reference_links"] = [text]
        created = client.post(topics, json=body, headers=editor.headers)
        assert created.status_code == 201, created.text
        topic = created.json()
        assert topic["title"] == title and topic["description"] == text
        read = client.get(f"{topics}/{topic['guid']}", headers=viewer.headers).json()
        assert read["title"] == title and read["description"] == text
        if "reference_links" in body:
            assert read["reference_links"] == [text.strip()]
        as_21 = client.get(
            f"/bcf/2.1/projects/{world.project_id}/topics/{topic['guid']}", headers=viewer.headers
        ).json()
        assert as_21["title"] == title and as_21["description"] == text
        events = client.get(f"{topics}/{topic['guid']}/events", headers=viewer.headers).json()
        values = {action["type"]: action.get("value") for event in events for action in event["actions"]}
        assert values["title_updated"] == title[:TITLE_VALUE_LIMIT]
        assert values["description_updated"] == text[:TEXT_VALUE_LIMIT]
        literal = title.replace("'", "''")
        filtered = client.get(topics, params={"$filter": f"title eq '{literal}'"}, headers=viewer.headers)
        assert filtered.status_code == 200, filtered.text
        assert {found["guid"] for found in filtered.json()} == {topic["guid"]}, "a filter value is a parameter"

        comments = f"{topics}/{topic['guid']}/comments"
        comment = client.post(comments, json={"comment": text}, headers=editor.headers)
        assert comment.status_code == 201, comment.text
        assert comment.json()["comment"] == text.strip()
        assert (
            client.get(f"{comments}/{comment.json()['guid']}", headers=viewer.headers).json()["comment"] == text.strip()
        )
        assert client.get(comments, headers=viewer.headers).json()[0]["comment"] == text.strip()

        if len(text) <= VALUE_MAX:
            components = {
                "selection": [{"ifc_guid": WALL_A, "originating_system": text, "authoring_tool_id": text}],
                "coloring": [{"color": "ff0000", "components": [{"authoring_tool_id": text}]}],
                "visibility": {
                    "default_visibility": True,
                    "exceptions": [{"ifc_guid": WALL_B, "originating_system": text}],
                },
            }
            viewpoint = client.post(
                f"{topics}/{topic['guid']}/viewpoints",
                json={"perspective_camera": PERSPECTIVE, "components": components},
                headers=editor.headers,
            )
            assert viewpoint.status_code == 201, viewpoint.text
            base = f"{topics}/{topic['guid']}/viewpoints/{viewpoint.json()['guid']}"
            assert client.get(f"{base}/selection", headers=viewer.headers).json() == {
                "selection": components["selection"]
            }
            coloring = client.get(f"{base}/coloring", headers=viewer.headers).json()["coloring"]
            assert [item["components"] for item in coloring] == [[{"authoring_tool_id": text}]]
            visibility = client.get(f"{base}/visibility", headers=viewer.headers).json()["visibility"]
            assert visibility["exceptions"] == components["visibility"]["exceptions"]

        reference = client.post(
            f"{topics}/{topic['guid']}/document_references",
            json={"url": "https://example.test/plan.pdf", "description": text},
            headers=editor.headers,
        )
        assert reference.status_code == 201 and reference.json()["description"] == text


# ---------------------------------------------------------------------------- 5. Documents API titles and file names


def test_document_titles_and_file_names_are_data_and_never_paths(injected: tuple[TestClient, World]) -> None:
    """A title and a file name are stored and returned as given; the file lies under a key the server made; every
    page that shows them escapes them; the download names the file in a header nothing in the name can break."""
    client, world = injected
    editor = login_as(client, world, "editor")
    viewer = login_as(client, world, "viewer")
    manager = login_as(client, world, "manager")
    names = within(255)  # the file name's limit; every one fits a title (200) as well
    started = start_upload(
        client, editor, [{"file_name": name, "session_file_id": f"f{index}"} for index, name in enumerate(names)]
    )
    web_sign_in(client, world, "editor")
    page = client.get(started["upload_ui_url"])
    assert page.status_code == 200
    for name in names:
        assert_shown_as_data(page.text, name)
    fields = {}
    for index, name in enumerate(names):
        fields[f"title_{index}"] = name
        fields[f"version_{index}"] = version_of(name)
    instructions_url = save_metadata(client, started["upload_ui_url"], world.project_id, fields)
    plan = client.post(
        instructions_url,
        json={"files": [{"session_file_id": f"f{index}", "size_in_bytes": len(NOTES)} for index in range(len(names))]},
        headers=editor.headers,
    )
    assert plan.status_code == 200, plan.text
    versions = {
        item["session_file_id"]: upload_file(client, editor, item, NOTES) for item in plan.json()["documents_to_upload"]
    }

    for index, name in enumerate(names):
        version = versions[f"f{index}"]
        assert version["title"] == name and version["file_description"]["name"] == name
        assert version["version_number"] == version_of(name)
        again = client.get(version["links"]["document_version"]["url"], headers=viewer.headers).json()
        assert again["title"] == name and again["file_description"]["name"] == name
        metadata = client.get(version["links"]["document_version_metadata"]["url"], headers=viewer.headers).json()
        entries = {entry["name"]: entry["value"] for entry in metadata["metadata"]}
        assert entries["file_name"] == [name] and entries["project"] == ["Building permit"]
        download = client.get(version["links"]["document_version_download"]["url"], headers=viewer.headers)
        assert download.status_code == 200 and download.content == NOTES
        disposition = download.headers["content-disposition"]
        assert disposition.startswith('attachment; filename="') and not any(ord(char) < 0x20 for char in disposition)
        quoted = disposition.split('filename="', 1)[1].split('"; filename*=', 1)[0]
        assert '"' not in quoted and "\\" not in quoted
        assert unquote(disposition.rsplit("filename*=UTF-8''", 1)[1]) == name
        details = client.get(version["links"]["document_details"]["url"])
        assert details.status_code == 200
        assert_shown_as_data(details.text, name)
    information = client.get(f"/bcf/3.0/projects/{world.project_id}/files_information", headers=viewer.headers).json()
    assert {entry["file"]["filename"] for entry in information} >= set(names)

    storage = client.app.state.storage  # type: ignore[attr-defined]
    kept = list(storage.iter_keys("documents"))
    assert len(kept) == len(names) and all(is_uuid(key.removeprefix("documents/")) for key in kept)
    for path in Path(client.app.state.settings.data_dir).rglob("*"):  # type: ignore[attr-defined]
        never_quoted(str(path))

    # A BCF document's name comes from a header and is cleaned on the way in; its download header is clean too.
    for text in names:
        created = bcf_upload(client, world, editor, f"attachment; filename*=UTF-8''{quote(text, safe='')}", data=NOTES)
        assert created.status_code == 201, created.text
        assert created.json()["filename"] == sanitize_filename(text)
        download = client.get(
            f"/bcf/3.0/projects/{world.project_id}/documents/{created.json()['guid']}", headers=viewer.headers
        )
        assert download.status_code == 200 and not any(
            ord(char) < 0x20 for char in download.headers["content-disposition"]
        )

    # The project's name, renamed through the BCF API, is data on the pages that show it.
    for text in within(MAX_NAME):
        renamed = client.put(f"/bcf/3.0/projects/{world.project_id}", json={"name": text}, headers=manager.headers)
        assert renamed.status_code == 200 and renamed.json()["name"] == text.strip(), renamed.text
    assert (
        client.get(f"/bcf/3.0/projects/{world.project_id}", headers=viewer.headers).json()["name"] == TEMPLATE.strip()
    )
    selection = client.post(
        "/documents/1.0/select-documents",
        json={"callback": {"url": CALLBACK, "expires_in": 600}},
        headers=viewer.headers,
    ).json()
    client.cookies.clear()
    web_sign_in(client, world, "viewer")
    select_page = client.get(selection["select_documents_url"])
    assert select_page.status_code == 200
    for text in (*names, TEMPLATE.strip()):
        assert_shown_as_data(select_page.text, text)
    client.cookies.clear()
    web_sign_in(client, world, "admin")
    for path in ("/admin/projects", f"/admin/projects/{world.project_id}"):
        admin_page = client.get(path)
        assert admin_page.status_code == 200, path
        assert_shown_as_data(admin_page.text, TEMPLATE.strip())


# ---------------------------------------------------------------------------- 6. the logs


def test_the_logs_keep_the_text_as_one_string_each(injected: tuple[TestClient, World]) -> None:
    """A request whose path and request id carry the text is one request log entry with the path as one string and a
    minted id, never the body; a failed sign-in with the text as the user name is one audit event whose details are one
    JSON string, on the page and in the CSV."""
    client, world = injected
    editor = login_as(client, world, "editor")
    admin_api = login_with_scope(client, world, "admin", "profile admin")
    paths = {text: f"/bcf/3.0/projects/{text}/topics" for text in within(2000)}
    statuses: dict[str, int] = {}
    for text, path in paths.items():
        response = client.get(
            f"/bcf/3.0/projects/{quote(text, safe='')}/topics", headers={**editor.headers, "X-Request-ID": text}
        )
        # No such project (404), or a text too long for a project id (400); never the text as the request id.
        assert response.status_code in (400, 404) and response.headers["x-request-id"] != text
        statuses[path] = response.status_code
    created = client.post(
        f"/bcf/3.0/projects/{world.project_id}/topics",
        json={"title": "Logged", "description": f"{INSTRUCTION} {MARKER}"},
        headers=editor.headers,
    )
    assert created.status_code == 201, created.text
    page = client.get("/signin")
    for text in within(128):
        refused = client.post(
            "/signin", data={"form_token": form_token(page.text), "username": text, "password": "not the password"}
        )
        assert refused.status_code == 200 and "not correct" in refused.text
        never_quoted(refused.text)
    client.portal.call(client.app.state.requestlog.wait_idle)  # type: ignore[attr-defined]

    rows = client.get("/admin/api/requests", params={"path": "/bcf/3.0/projects/"}, headers=admin_api.headers)
    assert rows.status_code == 200, rows.text
    logged = {row["path"]: row for row in rows.json()["requests"]}
    for text, path in paths.items():
        assert path in logged, path[:80]
        assert logged[path]["status"] == statuses[path] and re.fullmatch(r"[0-9a-f]{32}", logged[path]["request_id"])
        if statuses[path] == 404 and "/" not in text:  # a slash in the id leaves the route: no principal is made
            assert logged[path]["username"] == "editor"
    assert MARKER not in rows.text, "never a body"

    web_sign_in(client, world, "admin")
    requests_page = client.get("/admin/requests", params={"path": "/bcf/3.0/projects/"})
    assert requests_page.status_code == 200
    for path in paths.values():
        assert_shown_as_data(requests_page.text, path)
    audit_page = client.get("/admin/audit", params={"type": "web.sign_in.failed"})
    assert audit_page.status_code == 200
    for text in within(128):
        assert_shown_as_data(audit_page.text, json.dumps({"username": text}, sort_keys=True))
    exported = client.get("/admin/audit.csv", params={"type": "web.sign_in.failed"})
    assert exported.status_code == 200
    table = list(csv.reader(io.StringIO(exported.text)))
    assert table[0] == ["at", "type", "actor", "client_id", "ip", "details"]
    details = [json.loads(row[5]) for row in table[1:]]
    assert all(len(row) == 6 for row in table), "one row per event, whatever the text holds"
    assert {entry.get("username") for entry in details} >= set(within(128))


# ---------------------------------------------------------------------------- 7. the MCP endpoint

#: The model's title and file name: without a folder, so that the published archive keeps the name whole.
HOSTILE_FILE = f"{TEMPLATE}.ifc"


@pytest.fixture
def injected_mcp(
    graph_target: GraphTarget, clean_database: None, tmp_path: Path
) -> Iterator[tuple[TestClient, World, Settings]]:
    """The server with the IFC-LPG module, the clash check, the request log and the MCP endpoint on, and the
    project's AI policy cloud, so that a team server gives its data to AI tools."""
    settings = settings_for(
        graph_target, tmp_path, request_log_enabled=True, mcp_enabled=True, ifcgraph_clash_enabled=True
    )
    world = build_world(settings)
    asyncio.run(set_policy(settings, world.project_id, "cloud"))
    with TestClient(create_app(settings, startup_wait_seconds=30)) as client:
        yield client, world, settings


def _said_of_itself(client: TestClient, session: Session) -> list[Any]:
    """The tools, the discovery with the instructions, and the handshake, as an AI program's client asks them."""
    found = []
    for method in ("tools/list", "server/discover"):
        message = {"jsonrpc": "2.0", "id": 1, "method": method, "params": {"_meta": META}}
        sent = {**session.headers, "MCP-Protocol-Version": MODERN, "Mcp-Method": method}
        answer = client.post("/mcp", json=message, headers=sent)
        assert answer.status_code == 200, answer.text
        found.append(answer.json()["result"])
    handshake = {"jsonrpc": "2.0", "id": 2, "method": "initialize", "params": HANDSHAKE}
    answer = client.post("/mcp", json=handshake, headers=session.headers)
    assert answer.status_code == 200, answer.text
    return [*found, answer.json()["result"]]


def data_of(result: dict[str, Any]) -> dict[str, Any]:
    """A tool's answer: no error, and its text the same JSON as its ``structuredContent``."""
    assert result["isError"] is False, result["content"][0]["text"]
    assert json.loads(result["content"][0]["text"]) == result["structuredContent"]
    return result["structuredContent"]


def _mcp_events(settings: Settings) -> list[dict[str, Any]]:
    password = settings.graph_password.get_secret_value()
    with GraphDatabase.driver(settings.graph_uri, auth=(settings.graph_user, password)) as driver:
        rows, _, _ = driver.execute_query(
            "MATCH (e:AuditEvent) WHERE e.type STARTS WITH $prefix RETURN e.type AS type, e.details AS details",
            prefix="mcp.",
            database_=settings.database_name,
        )
    return [dict(row) for row in rows]


def test_the_mcp_tools_give_the_text_back_as_data_and_list_the_same_tools(
    injected_mcp: tuple[TestClient, World, Settings],
) -> None:
    """The text in a project's name, a model's title and file name, the names, descriptions and properties of its
    elements, its publication and its clashes, and in BCF topics, comments and an IDS: every read tool gives it back
    verbatim, cut at its lengths, in ``structuredContent`` and as the same JSON in the text; a refusal and a JSON-RPC
    error never quote it; the tools and the instructions are what they were while the project held none of it; and
    neither the request log nor the audit log keeps any of it."""
    pytest.importorskip("ifcclash", reason="the ifc-lpg extra is not installed")
    from tests.integration.test_ifc_clash import shifted_copy
    from tests.integration.test_mcp_clash import waited

    client, world, settings = injected_mcp
    ai = bound(client, world, "viewer")
    before = _said_of_itself(client, ai)
    untraced(json.dumps(before))
    assert data_of(tool(client, ai, "list_models", {"project_id": None}))["models"] == []

    editor = login_as(client, world, "editor")
    manager = login_as(client, world, "manager")
    renamed = client.put(f"/bcf/3.0/projects/{world.project_id}", json={"name": INSTRUCTION}, headers=manager.headers)
    assert renamed.status_code == 200, renamed.text
    web_sign_in(client, world, "editor")  # the upload page asks for a browser session
    hostile = upload(client, world, editor, HOSTILE_FILE, injected_model())
    assert checked(client, editor, hostile)["ifc_validation_status"] == ["passed"]
    assert converted(client, editor, hostile)["model_state"] == "done"
    published = client.post(hostile["links"]["document_version"]["url"] + "/publication", headers=manager.headers)
    assert published.status_code == 201, published.text
    moved = upload(client, world, editor, "walls-moved.ifc", shifted_copy())

    listed = data_of(tool(client, ai, "list_models", {"project_id": None}))["models"]
    models = {row["document_id"]: row for row in listed}
    assert set(models) == {hostile["document_id"], moved["document_id"]}
    row = models[hostile["document_id"]]
    assert (row["project_name"], row["title"], row["file_name"]) == (INSTRUCTION[:MCP_NAME], HOSTILE_FILE, HOSTILE_FILE)

    walls = rows_of(data_of(ask_mcp(client, ai, hostile, name="elements", **{"class": "IfcWall"})))
    assert {row["global_id"]: (row["name"], row["container"]) for row in walls} == {
        WALL_OF[wall]: (name[:MAX_TEXT], STOREY) for wall, (name, _description) in WALLS_TEXT.items()
    }
    for wall, (name, description) in WALLS_TEXT.items():
        (entity,) = rows_of(data_of(ask_mcp(client, ai, hostile, name="entity", global_id=WALL_OF[wall])))
        assert entity["attributes"]["Name"] == name[:MAX_TEXT]
        assert entity["attributes"]["Description"] == description[:MAX_TEXT]
    gtin = rows_of(data_of(ask_mcp(client, ai, hostile, name="property", pset="Reuse", property="GTIN")))
    assert {row["global_id"]: row["value"] for row in gtin} == {WALL_A: CYPHER, WALL_B: "2", WALL_C: "1"}
    where = {"document_id": hostile["document_id"], "version_index": hostile["version_index"]}
    publication = data_of(tool(client, ai, "get_publication", where))
    assert publication["published"] is True and publication["file_name"] == archive_names(HOSTILE_FILE)[1]

    sides = {
        "a": where | {"types": None},
        "b": {"document_id": moved["document_id"], "version_index": moved["version_index"], "types": ["IfcWall"]},
    }
    check = {"project_id": world.project_id, **sides, "mode": None, "tolerance": None, "clearance": None}
    clash_id = data_of(tool(client, ai, "start_clash_check", check))["clash_id"]
    assert waited(client, ai, world.project_id, clash_id)["state"] == "done"
    asked = {"project_id": world.project_id, "clash_id": clash_id, "wait_seconds": None}
    report = data_of(tool(client, ai, "get_clash_check", asked))
    assert report["count"] >= 1 and report["clashes"], "the moved walls go into the hostile ones"
    assert {clash["a"]["name"] for clash in report["clashes"]} <= {name[:MCP_NAME] for name, _ in WALLS_TEXT.values()}
    assert {clash["a"]["storey"] for clash in report["clashes"]} == {STOREY}

    topics = f"/bcf/3.0/projects/{world.project_id}/topics"
    for text in INJECTIONS:
        topic = client.post(topics, json={"title": text[:TITLE_MAX], "description": text}, headers=editor.headers)
        assert topic.status_code == 201, topic.text
        comments = f"{topics}/{topic.json()['guid']}/comments"
        assert client.post(comments, json={"comment": text}, headers=editor.headers).status_code == 201
    rules = upload(client, world, editor, "rules.ids", injected_ids())
    after = {row["document_id"] for row in data_of(tool(client, ai, "list_models", {"project_id": None}))["models"]}
    assert rules["document_id"] not in after and after == set(models), "an IDS is no model"
    assert _said_of_itself(client, ai) == before, "the tools and the instructions are the code's own"

    # The text in the arguments, the id, the tool's name and _meta: refusals and errors in the code's own words.
    for text in INJECTIONS:
        for name, arguments in (
            ("list_models", {"project_id": text[:64]}),
            ("server_query", {"document_id": text[:64], "version_index": None, **NOTHING}),
            ("get_publication", {"document_id": text[:64], "version_index": 1}),
            ("get_clash_check", asked | {"clash_id": text[:64]}),
            ("start_clash_check", check | {"a": sides["a"] | {"document_id": text[:64]}}),
        ):
            refused = tool(client, ai, name, arguments)
            assert refused["isError"] is True, name
            untraced(refused["content"][0]["text"])
        query = tool(client, ai, "server_query", where | NOTHING | {"name": "property", "pset": text, "property": "x"})
        if query["isError"]:  # control characters, or longer than a parameter
            untraced(query["content"][0]["text"])
        else:
            assert data_of(query)["rows"] == [], "the text is a value the graph is asked for, and holds nowhere"
        encoded = "=?base64?" + base64.b64encode(text.encode("utf-8")).decode("ascii") + "?="
        message = {
            "jsonrpc": "2.0",
            "id": text,
            "method": "tools/call",
            "params": {"name": text, "arguments": {text: text}, "_meta": META | {text: text}},
        }
        sent = {**ai.headers, "MCP-Protocol-Version": MODERN, "Mcp-Method": "tools/call", "Mcp-Name": encoded}
        answer = client.post("/mcp", json=message, headers=sent)
        assert answer.status_code == 400
        error = {"code": -32602, "message": "Unknown tool: tools/list names the tools"}
        assert answer.json() == {"jsonrpc": "2.0", "id": text, "error": error}, "the id comes back, as JSON-RPC has it"

    client.portal.call(client.app.state.requestlog.wait_idle)  # type: ignore[attr-defined]
    admin_api = login_with_scope(client, world, "admin", "profile admin")
    logged = client.get("/admin/api/requests", params={"path": "/mcp", "limit": 1000}, headers=admin_api.headers)
    assert logged.status_code == 200, logged.text
    entries = logged.json()["requests"]
    assert entries and all(entry["operation"].startswith("MCP ") for entry in entries)
    untraced(json.dumps(entries))
    events = _mcp_events(settings)
    assert [event["type"] for event in events] == ["mcp.clash.started"]
    untraced(events[0]["details"])
