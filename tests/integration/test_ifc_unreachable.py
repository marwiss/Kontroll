# This file was generated with the assistance of an AI coding tool.
"""Removing what no GlobalId reaches as a proposal (IFC-LPG F13 a, OB-10.4, F10 a): the report warns of a loose
instance, the server proposes a change set that deletes it, the change set is tried, and a manager approves it into
the next version, which no longer has the instance while the first one keeps it."""

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
from tests.integration.test_ifc_proposal import tried
from tests.integration.test_ifc_validation import MODEL, checked, settings_for, upload
from tests.integration.test_web_signin import web_sign_in

pytestmark = pytest.mark.integration


@pytest.fixture
def ifc_client(graph_target: GraphTarget, clean_database: None, tmp_path: Any) -> Iterator[tuple[TestClient, World]]:
    settings = settings_for(graph_target, tmp_path)
    world = build_world(settings)
    with TestClient(create_app(settings, startup_wait_seconds=30)) as client:
        yield client, world


def loose_model() -> bytes:
    """The model with a loose actor role: a node, where a loose point would be kept among the geometry in a block."""
    head, tail = MODEL.read_bytes().rsplit(b"ENDSEC;", 1)  # the end of the data section
    return head + b"#9001=IFCACTORROLE(.ARCHITECT.,$,$);\r\n" + b"ENDSEC;" + tail


def graph_check(client: TestClient, session: Session, document_id: str, version_index: int) -> dict[str, Any]:
    """The report of a version once its model is converted and the check graph is in it."""
    url = f"/documents/1.0/documents/{document_id}/versions/{version_index}/ifc-validation"
    deadline = time.monotonic() + 240
    while True:
        body = client.get(url, headers=session.headers).json()
        if any(check["name"] == "graph" for check in body.get("checks", [])):
            return body
        assert time.monotonic() < deadline, "the model was not converted in time"
        time.sleep(0.5)


def test_the_server_proposes_removing_what_no_global_id_reaches(ifc_client: tuple[TestClient, World]) -> None:
    client, world = ifc_client
    editor = login_as(client, world, "editor")
    web_sign_in(client, world, "editor")
    manager = login_as(client, world, "manager")
    version = upload(client, world, editor, "loose_point.ifc", loose_model())
    checked(client, editor, version)
    document_id = version["document_id"]
    first = graph_check(client, editor, document_id, 1)
    assert [issue["step_id"] for issue in first["issues"] if issue["kind"] == "reachability"] == [9001]

    url = f"/documents/1.0/projects/{world.project_id}/ifc-unreachable"
    request = {"document_id": document_id, "version_index": 1}
    viewer = login_as(client, world, "viewer")
    assert client.post(url, json=request, headers=viewer.headers).status_code == 403, "a viewer makes no topic"
    made = client.post(url, json=request, headers=editor.headers)
    assert made.status_code == 201, made.text
    proposal = made.json()
    assert proposal["changes"] == 1 and "loose_point.ifc" in proposal["title"]
    topics = f"/bcf/3.0/projects/{world.project_id}/topics"
    topic = client.get(f"{topics}/{proposal['topic_guid']}", headers=editor.headers).json()
    assert topic["bim_snippet"]["snippet_type"] == "DataregiumIfcChangeSet"
    snippet = client.get(f"{topics}/{proposal['topic_guid']}/snippet", headers=editor.headers).json()
    assert snippet["changes"] == [{"step_id": 9001, "op": "delete"}]
    assert snippet["provenance"]["user"] == "editor" and snippet["provenance"]["tool_call"] == "ifc-unreachable"

    trial = f"{topics}/{proposal['topic_guid']}/ifc-proposal"
    assert proposal["proposal_url"].endswith(trial)
    assert tried(client, editor, trial)["state"] == "clean"
    approved = client.post(trial + "/approve", headers=manager.headers)
    assert approved.status_code == 201, approved.text
    new = approved.json()
    assert new["version_index"] == 2
    download = client.get(new["links"]["document_version_download"]["url"], headers=editor.headers)
    assert download.status_code == 200 and b"#9001=" not in download.content
    second = graph_check(client, editor, document_id, 2)
    assert not [issue for issue in second["issues"] if issue["kind"] == "reachability"], "nothing is out of reach"
    old = client.get(version["links"]["document_version_download"]["url"], headers=editor.headers)
    assert b"#9001=" in old.content, "the version it came from keeps the instance"

    nothing = client.post(url, json={"document_id": document_id, "version_index": 2}, headers=editor.headers)
    assert nothing.status_code == 409, "every instance of version 2 is reached"
    missing = client.post(url, json={"document_id": document_id, "version_index": 9}, headers=editor.headers)
    assert missing.status_code == 404
    outsider = login_as(client, world, "outsider")
    assert client.post(url, json=request, headers=outsider.headers).status_code == 404
    assert client.post(url, json=request).status_code == 401
