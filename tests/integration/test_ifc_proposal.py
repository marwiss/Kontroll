# This file was generated with the assistance of an AI coding tool.
"""A change set tried on its base version when it is uploaded as a topic's snippet (ADR 0021)."""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from opencde.documents.changes import SCHEMA_PATH, SNIPPET_TYPE
from opencde.main import create_app
from tests.integration.conftest import GraphTarget
from tests.integration.conftest_accounts import World, build_world, login_as
from tests.integration.helpers import Session
from tests.integration.test_bcf_links_documents import make_topic
from tests.integration.test_ifc_validation import MODEL, WALLS, checked, settings_for, upload
from tests.integration.test_web_signin import web_sign_in

pytestmark = pytest.mark.integration
pytest.importorskip("ifcopenshell", reason="the ifc-lpg extra is not installed")


@pytest.fixture
def ifc_client(graph_target: GraphTarget, clean_database: None, tmp_path: Any) -> Iterator[tuple[TestClient, World]]:
    settings = settings_for(graph_target, tmp_path)
    world = build_world(settings)
    with TestClient(create_app(settings, startup_wait_seconds=30)) as client:
        yield client, world


def tried(client: TestClient, session: Session, url: str) -> dict[str, Any]:
    deadline = time.monotonic() + 300
    while True:
        response = client.get(url, headers=session.headers)
        assert response.status_code == 200, response.text
        report = response.json()
        if report["state"] not in ("queued", "running"):
            return report
        assert time.monotonic() < deadline, "the trial did not finish in time"
        time.sleep(0.5)


def change_set(document_id: str, *changes: dict[str, Any]) -> bytes:
    return json.dumps(
        {
            "schema": f"http://testserver{SCHEMA_PATH}",
            "base": {"document_id": document_id, "version_index": 1},
            "provenance": {"user": "editor", "ai_model": "claude-opus-5-5", "tool_call": "rename"},
            "changes": list(changes),
        }
    ).encode("utf-8")


def test_a_change_set_is_tried_on_its_base_and_judged_against_its_findings(
    ifc_client: tuple[TestClient, World],
) -> None:
    client, world = ifc_client
    editor = login_as(client, world, "editor")
    web_sign_in(client, world, "editor")
    viewer = login_as(client, world, "viewer")
    outsider = login_as(client, world, "outsider")
    assert client.get("/.well-known/dataregium").json()["extensions"]["ifc_changes"]["tried"] is True
    version = upload(client, world, editor, "three_walls_gtin.ifc", MODEL.read_bytes())
    assert checked(client, editor, version)["ifc_validation_status"] == ["passed"]
    document_id = version["document_id"]
    topics = f"/bcf/3.0/projects/{world.project_id}/topics"
    topic = make_topic(
        client,
        world,
        editor,
        bim_snippet={
            "snippet_type": SNIPPET_TYPE,
            "is_external": False,
            "reference": "changes.json",
            "reference_schema": f"http://testserver{SCHEMA_PATH}",
        },
    )
    snippet = f"{topics}/{topic['guid']}/snippet"
    proposal = f"{topics}/{topic['guid']}/ifc-proposal"
    assert client.get(proposal, headers=viewer.headers).status_code == 404, "nothing uploaded yet"

    # A clean change: one wall renamed, nothing the base lacks.
    rename = {"guid": WALLS[0], "attribute": "Name", "op": "set", "old": "YVT-A", "new": "YVT-A2"}
    assert client.put(snippet, content=change_set(document_id, rename), headers=editor.headers).status_code == 200
    report = tried(client, viewer, proposal)
    assert report["state"] == "clean", report
    assert report["applied"] == 1 and report["change_count"] == 1 and report["issue_count"] == 0
    assert report["base"] == {"document_id": document_id, "version_index": 1}
    assert report["ruleset"].startswith("IfcOpenShell ") and report["checks"][0]["name"] == "schema"
    assert client.get(proposal, headers=outsider.headers).status_code == 404
    assert client.get(proposal).status_code == 401
    storage = client.app.state.storage  # type: ignore[attr-defined]
    kept = [key for key in storage.iter_keys("proposals")]
    assert len(kept) == 1, "the applied file is kept for the approval"

    # A change set that breaks the schema, and one change that cannot be applied: both are issues.
    duplicate = {"guid": WALLS[0], "attribute": "GlobalId", "op": "set", "new": WALLS[1]}
    stale = {"guid": WALLS[1], "attribute": "Name", "op": "set", "old": "not its name", "new": "x"}
    assert (
        client.put(snippet, content=change_set(document_id, duplicate, stale), headers=editor.headers).status_code
        == 200
    )
    report = tried(client, viewer, proposal)
    assert report["state"] == "issues", report
    assert report["applied"] == 1 and report["change_count"] == 2 and report["error_count"] >= 2
    kinds = {issue["kind"] for issue in report["issues"]}
    assert "proposal" in kinds and kinds - {"proposal"}, "a change that did not apply, and a new finding"
    stale_issue = next(issue for issue in report["issues"] if issue["kind"] == "proposal")
    assert stale_issue["message"] == "change 1: Name no longer holds the old value"
    assert any(issue.get("global_id") == WALLS[1] and "IfcRoot.UR1" in issue["message"] for issue in report["issues"])
    assert [key for key in storage.iter_keys("proposals")] != kept, "a new snippet replaces the trial and its file"
    assert len(list(storage.iter_keys("proposals"))) == 1

    # A base that is not in the project cannot be tried.
    elsewhere = change_set("11111111-2222-4333-8444-555555555555", rename)
    assert client.put(snippet, content=elsewhere, headers=editor.headers).status_code == 200
    report = tried(client, viewer, proposal)
    assert report["state"] == "failed" and "not in this project" in report["error"]

    # The trial goes with the topic, file and all.
    assert client.delete(f"{topics}/{topic['guid']}", headers=editor.headers).status_code == 200
    assert list(storage.iter_keys("proposals")) == []
