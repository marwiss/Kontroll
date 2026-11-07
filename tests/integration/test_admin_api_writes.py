# This file was generated with the assistance of an AI coding tool.
"""The write side of the administration API: users, projects, members, clients, sessions, and the fresh-sign-in rule."""

import pytest
from fastapi.testclient import TestClient
from neo4j import GraphDatabase

from opencde.settings import Settings
from tests.integration.conftest_accounts import World, build_world, login_as, login_with_scope

pytestmark = [pytest.mark.integration, pytest.mark.security]


@pytest.fixture
def world(settings: Settings, clean_database: None) -> World:
    return build_world(settings)


def test_administrators_manage_users_projects_and_clients(client: TestClient, world: World) -> None:
    admin = login_with_scope(client, world, "admin", "profile admin")
    h = admin.headers

    # Users: create with a generated password (returned once), update, roles, reset, revoke, delete.
    created = client.post(
        "/admin/api/users", json={"username": "api_user", "name": "API User", "email": "api@example.test"}, headers=h
    )
    assert created.status_code == 201, created.text
    user = created.json()
    assert user["username"] == "api_user" and user["name"] == "API User" and user["must_change_password"] is True
    assert len(user["initial_password"]) >= 12
    user_id = user["id"]
    updated = client.put(f"/admin/api/users/{user_id}", json={"name": "Renamed", "disabled": True}, headers=h)
    assert updated.status_code == 200 and updated.json()["name"] == "Renamed" and updated.json()["disabled"]
    assert "initial_password" not in updated.json()
    patched = client.patch(f"/admin/api/users/{user_id}", json={"disabled": False}, headers=h)
    assert patched.status_code == 200 and patched.json()["disabled"] is False, "PATCH works like PUT"
    member = client.put(f"/admin/api/projects/{world.project_id}/members/{user_id}", json={"role": "editor"}, headers=h)
    assert member.status_code == 200 and member.json() == {"user_id": user_id, "role": "editor"}
    assert (
        client.put(
            f"/admin/api/projects/{world.project_id}/members/{user_id}", json={"role": "boss"}, headers=h
        ).status_code
        == 400
    )
    one = client.get(f"/admin/api/users/{user_id}", headers=h).json()
    assert [m["role"] for m in one["projects"]] == ["editor"]
    assert client.delete(f"/admin/api/projects/{world.project_id}/members/{user_id}", headers=h).status_code == 204
    reset = client.post(f"/admin/api/users/{user_id}/reset-password", headers=h)
    assert reset.status_code == 200 and len(reset.json()["password"]) >= 12
    assert client.delete("/admin/api/sessions", params={"user": "api_user"}, headers=h).status_code == 204
    assert client.delete(f"/admin/api/users/{user_id}", headers=h).status_code == 204
    assert client.get(f"/admin/api/users/{user_id}", headers=h).status_code == 404
    bad = client.post("/admin/api/users", json={"username": "x"}, headers=h)
    assert bad.status_code == 400 and bad.json()["code"] == "validation_error"

    # Not to yourself: disabling or demoting the calling administrator is refused.
    me = next(u for u in client.get("/admin/api/users", headers=h).json()["items"] if u["username"] == "admin")
    refused = client.put(f"/admin/api/users/{me['id']}", json={"is_admin": False}, headers=h)
    assert refused.status_code == 400 and client.delete(f"/admin/api/users/{me['id']}", headers=h).status_code == 400

    # Projects: create, rename, extensions, delete.
    project = client.post("/admin/api/projects", json={"name": "API project"}, headers=h)
    assert project.status_code == 201 and project.json()["name"] == "API project" and project.json()["members"] == []
    project_id = project.json()["project_id"]
    renamed = client.put(
        f"/admin/api/projects/{project_id}",
        json={"name": "API project 2", "extensions": {"topic_status": ["New", "Done"]}},
        headers=h,
    )
    assert renamed.status_code == 200 and renamed.json()["name"] == "API project 2"
    assert renamed.json()["extensions"]["topic_status"] == ["New", "Done"]
    assert client.delete(f"/admin/api/projects/{project_id}", headers=h).status_code == 204
    assert client.get(f"/admin/api/projects/{project_id}", headers=h).status_code == 404

    # Clients: a confidential client gets its secret once, can rotate it, be revoked and deleted.
    registered = client.post(
        "/admin/api/clients",
        json={"name": "API client", "redirect_uris": ["https://app.example/cb"], "public": False},
        headers=h,
    )
    assert registered.status_code == 201, registered.text
    body = registered.json()
    assert body["client_secret"] and body["public"] is False
    client_id = body["client_id"]
    assert client.get(f"/admin/api/clients/{client_id}", headers=h).json().get("client_secret") is None
    patched = client.put(f"/admin/api/clients/{client_id}", json={"description": "desc"}, headers=h)
    assert patched.status_code == 200 and patched.json()["description"] == "desc"
    rotated = client.post(f"/admin/api/clients/{client_id}/rotate-secret", headers=h)
    assert rotated.status_code == 200 and rotated.json()["client_secret"] != body["client_secret"]
    assert client.post(f"/admin/api/clients/{client_id}/revoke", headers=h).status_code == 204
    assert client.delete(f"/admin/api/clients/{client_id}", headers=h).status_code == 204

    # Sessions: one application session of another user can be ended by its id.
    editor = login_as(client, world, "editor")
    sessions = client.get("/admin/api/sessions", params={"user": "editor"}, headers=h).json()["items"]
    family = next(s for s in sessions if s["kind"] == "oauth2")
    assert client.delete(f"/admin/api/sessions/{family['id']}", headers=h).status_code == 204
    assert client.get("/foundation/1.0/current-user", headers=editor.headers).status_code == 401, "the token died"
    assert client.delete("/admin/api/sessions/no-such-session", headers=h).status_code == 404

    # Everything above left a trace with the caller and the request id.
    events = client.get("/admin/api/audit", params={"type": "admin."}, headers=h).json()["items"]
    types = {event["type"] for event in events}
    assert {"admin.user.create", "admin.user.delete", "admin.client.rotate_secret", "admin.project.delete"} <= types
    assert all(event["actor"] == me["id"] and event["request_id"] for event in events)


def test_deleting_a_project_through_the_api_frees_its_files_and_no_others(client: TestClient, world: World) -> None:
    """The administration's page did; the API left the files on the disk."""
    admin = login_with_scope(client, world, "admin", "profile admin")
    stored = {}
    for project_id, username in ((world.project_id, "editor"), (world.other_project_id, "outsider")):
        session = login_as(client, world, username)
        created = client.post(
            f"/bcf/3.0/projects/{project_id}/documents",
            content=b"ISO-10303-21;",
            headers={**session.headers, "Content-Disposition": 'attachment; filename="walls.ifc"'},
        )
        assert created.status_code == 201, created.text
        stored[project_id] = client.app.state.storage.path(f"bcf-documents/{created.json()['guid']}")  # type: ignore[attr-defined]
        assert stored[project_id].is_file()

    assert client.delete(f"/admin/api/projects/{world.project_id}", headers=admin.headers).status_code == 204
    assert not stored[world.project_id].exists()
    assert stored[world.other_project_id].is_file(), "another project's file stays"
    assert login_as(client, world, "editor").headers, "the member who uploaded is still there"


def test_dangerous_writes_need_a_fresh_sign_in(client: TestClient, world: World) -> None:
    """A token whose authentication is older than the window answers reauthentication_required."""
    admin = login_with_scope(client, world, "admin", "profile admin")
    h = admin.headers
    # Age the token family's authentication directly in the graph: the only way to travel in time in a test.
    settings = client.app.state.settings  # type: ignore[attr-defined]
    auth = (settings.graph_user, settings.graph_password.get_secret_value())
    with GraphDatabase.driver(settings.graph_uri, auth=auth) as driver:
        driver.execute_query(
            "MATCH (t:AccessToken) SET t.auth_time = '2000-01-01T00:00:00Z'", database_=settings.database_name
        )
    project = client.post("/admin/api/projects", json={"name": "Stale"}, headers=h)
    assert project.status_code == 201, "creating a project is not dangerous"
    stale = client.delete(f"/admin/api/projects/{project.json()['project_id']}", headers=h)
    assert stale.status_code == 403 and stale.json()["code"] == "reauthentication_required"
    fresh = login_with_scope(client, world, "admin", "profile admin")
    assert (
        client.delete(f"/admin/api/projects/{project.json()['project_id']}", headers=fresh.headers).status_code == 204
    )
