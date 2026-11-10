# This file was generated with the assistance of an AI coding tool.
"""A manager administers their own project (OB-41): members and roles through the project administration, the name
through the BCF API's PUT Project, never a deletion and never another project."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from opencde.settings import Settings
from tests.integration.conftest_accounts import World, build_world, login_as, login_with_scope

pytestmark = pytest.mark.integration


@pytest.fixture
def world(settings: Settings, clean_database: None) -> World:
    return build_world(settings)


def test_a_manager_administers_the_members_of_their_project(client: TestClient, world: World) -> None:
    manager = login_with_scope(client, world, "manager", "profile bcf project")
    members = f"/manage/1.0/projects/{world.project_id}/members"
    assert client.get("/.well-known/dataregium").json()["extensions"]["project_administration"]["enabled"] is True

    listed = client.get(members, headers=manager.headers)
    assert listed.status_code == 200, listed.text
    roles = {item["username"]: item["role"] for item in listed.json()["items"]}
    assert roles == {"contributor": "contributor", "editor": "editor", "manager": "manager", "viewer": "viewer"}
    assert "email" not in listed.json()["items"][0], "no more personal data than a manager needs"
    managed = client.get("/manage/1.0/projects", headers=manager.headers).json()["items"]
    assert [project["project_id"] for project in managed] == [world.project_id]

    # Added by exact user name; added again, the role is set.
    added = client.post(members, json={"username": "outsider", "role": "viewer"}, headers=manager.headers)
    assert added.status_code == 201 and added.json()["role"] == "viewer"
    again = client.post(members, json={"username": "outsider", "role": "editor"}, headers=manager.headers)
    assert again.status_code == 200 and again.json()["role"] == "editor"
    assert (
        client.post(members, json={"username": "nobody", "role": "viewer"}, headers=manager.headers).status_code == 404
    )
    assert client.post(members, json={"username": "viewer", "role": "owner"}, headers=manager.headers).status_code in (
        400,
        422,
    )
    outsider = world.users["outsider"]
    assert client.put(f"{members}/{outsider}", json={"role": "contributor"}, headers=manager.headers).json() == {
        "user_id": outsider,
        "role": "contributor",
    }
    assert client.delete(f"{members}/{outsider}", headers=manager.headers).status_code == 204
    assert client.delete(f"{members}/{outsider}", headers=manager.headers).status_code == 404

    # The project keeps a manager; once there are two, one may step down.
    me = world.users["manager"]
    last = client.put(f"{members}/{me}", json={"role": "editor"}, headers=manager.headers)
    assert last.status_code == 409 and last.json()["code"] == "conflict"
    assert client.delete(f"{members}/{me}", headers=manager.headers).status_code == 409
    editor = world.users["editor"]
    assert client.put(f"{members}/{editor}", json={"role": "manager"}, headers=manager.headers).status_code == 200
    assert client.put(f"{members}/{me}", json={"role": "editor"}, headers=manager.headers).status_code == 200
    assert client.get(members, headers=manager.headers).status_code == 403, "an editor now, no longer a manager"

    # The new manager renames the project through the BCF API; nothing here deletes it.
    new_manager = login_with_scope(client, world, "editor", "profile bcf project")
    renamed = client.put(
        f"/bcf/3.0/projects/{world.project_id}", json={"name": "Building permit, phase 2"}, headers=new_manager.headers
    )
    assert renamed.status_code == 200 and renamed.json()["name"] == "Building permit, phase 2"
    assert client.delete(f"/manage/1.0/projects/{world.project_id}", headers=new_manager.headers).status_code in (
        404,
        405,
    )

    # Every write is in the audit log, with the caller.
    admin = login_with_scope(client, world, "admin", "profile admin")
    events = client.get("/admin/api/audit", params={"type": "manage.membership"}, headers=admin.headers).json()
    assert len(events["items"]) >= 6 and {event["actor"] for event in events["items"]} == {me}


def test_only_a_manager_with_the_scope_reaches_a_project_they_manage(client: TestClient, world: World) -> None:
    members = f"/manage/1.0/projects/{world.project_id}/members"
    without_scope = login_as(client, world, "manager")
    refused = client.get(members, headers=without_scope.headers)
    assert refused.status_code == 403 and refused.json()["code"] == "insufficient_scope", "asked for explicitly"
    editor = login_with_scope(client, world, "editor", "profile project")
    assert client.get(members, headers=editor.headers).status_code == 403
    assert (
        client.post(members, json={"username": "outsider", "role": "manager"}, headers=editor.headers).status_code
        == 403
    )
    outsider = login_with_scope(client, world, "outsider", "profile project")
    assert client.get(members, headers=outsider.headers).status_code == 404, "not a member: the project is not there"
    other = f"/manage/1.0/projects/{world.other_project_id}/members"
    manager = login_with_scope(client, world, "manager", "profile project")
    assert client.get(other, headers=manager.headers).status_code == 404, "a manager of one project, not of all"
    assert client.get(members, headers={}).status_code == 401
