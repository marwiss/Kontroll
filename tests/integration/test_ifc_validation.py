# This file was generated with the assistance of an AI coding tool.
"""Checking uploads against the IFC schema and buildingSMART's rules: the result in a version's metadata, its report,
and who may read it."""

from __future__ import annotations

import os
import time
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from neo4j import GraphDatabase

from opencde.bootstrap import make_storage
from opencde.documents.assembly import store_stream
from opencde.ids import new_id
from opencde.main import create_app
from opencde.storage import make_key
from opencde.timeutil import later_iso, now_iso
from tests.conformance.schemas import validate_documents
from tests.conftest import FIXTURES_DIR
from tests.conftest import test_settings as make_settings  # aliased so pytest does not collect it as a test
from tests.integration.conftest import GraphTarget
from tests.integration.conftest_accounts import World, build_world, login_as
from tests.integration.helpers import Session
from tests.integration.test_documents_api import save_metadata, start_upload, upload_file
from tests.integration.test_web_signin import web_sign_in

pytestmark = pytest.mark.integration
pytest.importorskip("ifcopenshell", reason="the ifc-lpg extra is not installed")

MODEL = FIXTURES_DIR / "three_walls_gtin.ifc"
WALLS = ("1Xezbq735AdBO_4DerG66G", "3eT96F_cnDsOufCEsotwtp")
# An environment made with `python -m ifc_lpg.gherkin_install`, for the test with buildingSMART's rules.
GHERKIN_ENV = os.environ.get("OPENCDE_TEST_GHERKIN_ENV", "")


def settings_for(graph_target: GraphTarget, tmp_path: Any, **extra: Any) -> Any:
    return make_settings(
        tmp_path,
        graph_dialect=graph_target.dialect,
        graph_uri=graph_target.uri,
        graph_user=graph_target.user,
        graph_password=graph_target.password,
        graph_connect_timeout_seconds=10.0,
        cleanup_interval_seconds=3600,
        upload_part_bytes=4096,
        ifcgraph_enabled=True,
        ifcgraph_timeout_seconds=300,
        **extra,
    )


@pytest.fixture
def ifc_client(graph_target: GraphTarget, clean_database: None, tmp_path: Any) -> Iterator[tuple[TestClient, World]]:
    settings = settings_for(graph_target, tmp_path)
    world = build_world(settings)
    with TestClient(create_app(settings, startup_wait_seconds=30)) as client:
        yield client, world


def upload(client: TestClient, world: World, session: Session, name: str, data: bytes) -> dict[str, Any]:
    started = start_upload(client, session, [{"file_name": name, "session_file_id": "m"}])
    instructions_url = save_metadata(
        client, started["upload_ui_url"], world.project_id, {"title_0": name, "version_0": "1"}
    )
    plan = client.post(
        instructions_url,
        json={"files": [{"session_file_id": "m", "size_in_bytes": len(data)}]},
        headers=session.headers,
    ).json()
    return upload_file(client, session, plan["documents_to_upload"][0], data)


def checked(client: TestClient, session: Session, version: dict[str, Any]) -> dict[str, list[str]]:
    """The version's metadata once the check is over, each answer held to the Documents API's schema on the way."""
    deadline = time.monotonic() + 240
    while True:
        response = client.get(version["links"]["document_version_metadata"]["url"], headers=session.headers)
        assert response.status_code == 200, response.text
        validate_documents(response.json(), "DocumentMetadata")
        entries = {entry["name"]: entry["value"] for entry in response.json()["metadata"]}
        if entries["ifc_validation_status"] != ["pending"]:
            return entries
        assert time.monotonic() < deadline, "the check did not finish in time"
        time.sleep(0.5)


def test_an_upload_is_checked_and_the_report_names_its_elements(ifc_client: tuple[TestClient, World]) -> None:
    client, world = ifc_client
    editor = login_as(client, world, "editor")
    web_sign_in(client, world, "editor")
    good = upload(client, world, editor, "three_walls_gtin.ifc", MODEL.read_bytes())
    twice = upload(client, world, editor, "twice.ifc", MODEL.read_bytes().replace(WALLS[1].encode(), WALLS[0].encode()))
    assert twice["version_index"] == 1, "the upload is kept, whatever the check finds"

    entries = checked(client, editor, good)
    assert entries["ifc_validation_status"] == ["passed"] and entries["ifc_validation_issues"] == ["0"]
    assert entries["ifc_validation_ruleset"][0].startswith("IfcOpenShell ")
    assert entries["file_name"] == ["three_walls_gtin.ifc"], "the metadata given at upload is still there"
    good_report = entries["ifc_validation_report"][0]
    assert good_report == f"http://testserver/documents/1.0/documents/{good['document_id']}/versions/1/ifc-validation"
    assert client.get(good_report, headers=editor.headers).json()["status"] == "passed"

    entries = checked(client, editor, twice)
    assert entries["ifc_validation_status"] == ["issues"] and int(entries["ifc_validation_issues"][0]) >= 1
    report_url = entries["ifc_validation_report"][0]
    body = client.get(report_url, headers=editor.headers).json()
    assert body["status"] == "issues" and body["issue_count"] == len(body["issues"]) and body["truncated"] is False
    assert body["checked_at"] == entries["ifc_validation_checked_at"][0]
    assert any(issue["global_id"] == WALLS[0] and "IfcRoot.UR1" in issue["message"] for issue in body["issues"])

    viewer = login_as(client, world, "viewer")
    assert client.get(report_url, headers=viewer.headers).json() == body, "every member may read it"
    outsider = login_as(client, world, "outsider")
    assert client.get(report_url, headers=outsider.headers).status_code == 404
    assert client.get(report_url).status_code == 401
    missing = report_url.replace(twice["document_id"], new_id())
    assert client.get(missing, headers=editor.headers).status_code == 404

    page = client.get(twice["links"]["document_details"]["url"], headers={"Accept-Language": "en"})
    assert page.status_code == 200
    assert "Findings: " in page.text and WALLS[0] in page.text and "IfcRoot.UR1" in page.text
    assert "No findings" in client.get(good["links"]["document_details"]["url"]).text
    download = client.get(twice["links"]["document_details"]["url"] + "/ifc-validation")
    assert download.headers["content-disposition"].startswith("attachment")
    assert download.json() == body


@pytest.mark.skipif(not GHERKIN_ENV, reason="OPENCDE_TEST_GHERKIN_ENV names no environment for ifc-gherkin-rules")
def test_the_gherkin_rules_add_their_findings(graph_target: GraphTarget, clean_database: None, tmp_path: Any) -> None:
    settings = settings_for(graph_target, tmp_path, ifcgraph_gherkin_env=GHERKIN_ENV)
    world = build_world(settings)
    head, tail = MODEL.read_bytes().rsplit(b"ENDSEC;", 1)
    orphan = head + b"#99999=IFCCARTESIANPOINT((1.,2.,3.));\n" + b"ENDSEC;" + tail  # a point nothing refers to
    with TestClient(create_app(settings, startup_wait_seconds=30)) as client:
        editor = login_as(client, world, "editor")
        web_sign_in(client, world, "editor")
        version = upload(client, world, editor, "orphan.ifc", orphan)
        entries = checked(client, editor, version)
        assert entries["ifc_validation_status"] == ["warnings"], "IFC106 only warns, as buildingSMART holds it"
        assert entries["ifc_validation_issues"] == ["1"]
        schema, rules = entries["ifc_validation_ruleset"]
        assert schema.startswith("IfcOpenShell ") and rules.startswith("ifc-gherkin-rules ")
        body = client.get(entries["ifc_validation_report"][0], headers=editor.headers).json()
        assert [check["name"] for check in body["checks"]] == ["schema", "gherkin"]
        assert body["error_count"] == 0 and body["checks"][1]["state"] == "done"
        [finding] = body["issues"]
        assert (finding["kind"], finding["rule"], finding["severity"], finding["step_id"]) == (
            "gherkin",
            "IFC106",
            "warning",
            99999,
        )
        page = client.get(version["links"]["document_details"]["url"], headers={"Accept-Language": "en"}).text
        assert "Findings: 1, only warnings" in page and "IFC106" in page and "ifc-gherkin-rules " in page


def test_a_text_file_is_not_checked(ifc_client: tuple[TestClient, World]) -> None:
    client, world = ifc_client
    editor = login_as(client, world, "editor")
    web_sign_in(client, world, "editor")
    notes = upload(client, world, editor, "notes.txt", b"not a model")
    metadata = client.get(notes["links"]["document_version_metadata"]["url"], headers=editor.headers).json()
    assert not [entry for entry in metadata["metadata"] if entry["name"].startswith("ifc_validation_")]
    report_url = notes["links"]["document_version"]["url"] + "/ifc-validation"
    assert client.get(report_url, headers=editor.headers).status_code == 404


def test_a_check_a_stopped_server_left_behind_starts_over(
    graph_target: GraphTarget, clean_database: None, tmp_path: Any
) -> None:
    settings = settings_for(graph_target, tmp_path)
    world = build_world(settings)
    key = make_key("documents", new_id())
    with MODEL.open("rb") as source:
        store_stream(make_storage(settings), source, key, 10_000_000)
    left_behind = {
        "queued": {},
        "long-gone": {"running_at": later_iso(-3600)},
        "just-started": {"running_at": now_iso()},
    }
    with GraphDatabase.driver(graph_target.uri, auth=(graph_target.user, graph_target.password)) as driver:
        for check_id, fields in left_behind.items():
            driver.execute_query(
                """
                MATCH (p:Project {project_id: $project_id})
                CREATE (p)-[:HAS_DOCUMENT]->(:Document {document_id: $document_id, title: 'a', latest_index: 1})
                       -[:HAS_VERSION]->(:DocumentVersion {id: $version_id, version_index: 1})
                       -[:HAS_VALIDATION]->(r:IfcValidation {
                           id: $id, file_name: 'a.ifc', storage_key: $key, created_at: $now
                       })
                SET r.state = CASE WHEN $id = 'queued' THEN 'queued' ELSE 'running' END, r += $fields
                """,
                project_id=world.project_id,
                document_id=new_id(),
                version_id=new_id(),
                id=check_id,
                key=key,
                now=now_iso(),
                fields=fields,
                database_=settings.database_name,
            )

        def states() -> dict[str, str]:
            records, _, _ = driver.execute_query(
                "MATCH (r:IfcValidation) RETURN r.id AS id, r.state AS state", database_=settings.database_name
            )
            return {record["id"]: record["state"] for record in records}

        with TestClient(create_app(settings, startup_wait_seconds=30)):
            deadline = time.monotonic() + 240
            while {states()["queued"], states()["long-gone"]} != {"done"}:
                assert time.monotonic() < deadline, states()
                assert "failed" not in states().values(), states()
                time.sleep(0.5)
        assert states()["just-started"] == "running", "it may be running in another server process"
