# This file was generated with the assistance of an AI coding tool.
"""The teams of a project and who approves a change set (F11 b, F19 a, F20 a, F21 b): a manager sets a team up with a
responsible, members and an IDS document; a change to the team's part is approved by its responsible alone."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from opencde.documents.changes import SCHEMA_PATH, SNIPPET_TYPE
from tests.conftest import FIXTURES_DIR
from tests.integration.conftest_accounts import World, login_as, login_with_scope
from tests.integration.test_bcf_links_documents import make_topic
from tests.integration.test_ifc_proposal import change_set, ifc_client, tried
from tests.integration.test_ifc_validation import MODEL, WALLS, checked, upload
from tests.integration.test_web_signin import web_sign_in

pytestmark = pytest.mark.integration
pytest.importorskip("ifcopenshell", reason="the ifc-lpg extra is not installed")

__all__ = ["ifc_client"]  # the fixture, shared with the trials of change sets
BUILDING = "3AMeTOOFsdVLZuNV0$27s5"
SNIPPET = {
    "snippet_type": SNIPPET_TYPE,
    "is_external": False,
    "reference": "changes.json",
    "reference_schema": f"http://testserver{SCHEMA_PATH}",
}


def test_a_change_to_a_teams_part_is_approved_by_its_responsible(ifc_client: tuple[TestClient, World]) -> None:
    client, world = ifc_client
    editor = login_as(client, world, "editor")
    web_sign_in(client, world, "editor")
    manager = login_as(client, world, "manager")
    administrator = login_with_scope(client, world, "manager", "profile bcf project")
    model = upload(client, world, editor, "three_walls_gtin.ifc", MODEL.read_bytes())
    ids = upload(client, world, editor, "walls.ids", (FIXTURES_DIR / "walls.ids").read_bytes())
    checked(client, editor, model)
    teams = f"/manage/1.0/projects/{world.project_id}/teams"
    team = {"name": "Walls", "responsible": "editor", "members": ["contributor"], "ids_document_id": ids["document_id"]}

    assert client.post(teams, json={**team, "responsible": "viewer"}, headers=administrator.headers).status_code == 400
    assert client.post(teams, json={**team, "members": ["outsider"]}, headers=administrator.headers).status_code == 400
    wrong = {**team, "ids_document_id": model["document_id"]}
    assert client.post(teams, json=wrong, headers=administrator.headers).status_code == 400, "an IFC file is no IDS"
    project_editor = login_with_scope(client, world, "editor", "profile bcf project")
    assert client.post(teams, json=team, headers=project_editor.headers).status_code == 403
    made = client.post(teams, json=team, headers=administrator.headers)
    assert made.status_code == 201, made.text
    assert made.json()["responsible"] == "editor" and made.json()["members"] == ["contributor"]
    listed = client.get(teams, headers=administrator.headers).json()
    assert listed["total"] == 1 and listed["items"][0]["team_id"] == made.json()["team_id"]

    topics = f"/bcf/3.0/projects/{world.project_id}/topics"

    def proposed(*changes: dict[str, object]) -> str:
        topic = make_topic(client, world, editor, bim_snippet=SNIPPET)
        snippet = f"{topics}/{topic['guid']}/snippet"
        body = change_set(model["document_id"], *changes)
        assert client.put(snippet, content=body, headers=editor.headers).status_code == 200
        return f"{topics}/{topic['guid']}/ifc-proposal"

    wall = proposed({"guid": WALLS[0], "attribute": "Name", "op": "set", "old": "YVT-A", "new": "YVT-A2"})
    report = tried(client, editor, wall)
    assert report["state"] == "clean", report
    assert report["teams"] == [{"team_id": made.json()["team_id"], "name": "Walls"}]
    refused = client.post(wall + "/approve", headers=manager.headers)
    assert refused.status_code == 403 and "Walls" in refused.json()["message"], "a manager does not go past the team"
    approved = client.post(wall + "/approve", headers=editor.headers)
    assert approved.status_code == 201, approved.text

    building = proposed({"guid": BUILDING, "attribute": "Description", "op": "set", "new": "No team's part"})
    assert tried(client, editor, building)["teams"] == []
    assert client.post(building + "/approve", headers=editor.headers).status_code == 403, "outside every part"

    team_id = made.json()["team_id"]
    moved = client.put(f"{teams}/{team_id}", json={**team, "responsible": "manager"}, headers=administrator.headers)
    assert moved.status_code == 200 and moved.json()["responsible"] == "manager"
    assert client.delete(f"{teams}/{team_id}", headers=administrator.headers).status_code == 204
    assert client.get(teams, headers=administrator.headers).json()["total"] == 0
    assert client.delete(f"{teams}/{team_id}", headers=administrator.headers).status_code == 404
    outsider = login_with_scope(client, world, "outsider", "profile bcf project")
    assert client.get(teams, headers=outsider.headers).status_code == 404
