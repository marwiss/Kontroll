# This file was generated with the assistance of an AI coding tool.
"""The JSON administration API: what administrators read, what everyone else gets, and the fresh-sign-in rule."""

import pytest
from fastapi.testclient import TestClient

from opencde.auth.dependencies import REAUTHENTICATION_WINDOW_SECONDS, fresh_admin_principal
from opencde.errors import ApiError
from opencde.settings import Settings
from opencde.store.oauth2.tokens import Principal
from opencde.timeutil import later_iso
from tests.integration.conftest_accounts import World, build_world, login_as, login_with_scope

pytestmark = [pytest.mark.integration, pytest.mark.security]

USER_FIELDS = {
    "id",
    "username",
    "name",
    "email",
    "is_admin",
    "disabled",
    "must_change_password",
    "created_at",
    "last_sign_in_at",
    "projects",
}


@pytest.fixture
def world(settings: Settings, clean_database: None) -> World:
    return build_world(settings)


def test_administrators_read_the_server_through_the_api(client: TestClient, world: World) -> None:
    admin = login_with_scope(client, world, "admin", "profile admin")
    editor = login_as(client, world, "editor")
    client.get("/foundation/1.0/current-user", headers={**editor.headers, "X-Request-ID": "admin-api-trace"})

    overview = client.get("/admin/api/overview", headers=admin.headers)
    assert overview.status_code == 200, overview.text
    body = overview.json()
    assert body["graph_ok"] is True and body["users"] >= 6 and body["projects"] == 2 and body["version"]
    assert body["request_log"] == {"enabled": False, "rows": 0} and body["models"] == 0
    assert body["uptime_s"] is not None and body["sessions"] >= 2

    users = client.get("/admin/api/users", headers=admin.headers)
    assert users.status_code == 200
    listing = users.json()
    assert listing["total"] == len(listing["items"]) >= 6
    editor_row = next(item for item in listing["items"] if item["username"] == "editor")
    assert editor_row["projects"] == [{"project_id": world.project_id, "role": "editor"}]
    assert editor_row["last_sign_in_at"], "the sign-in just now was remembered"
    assert "password_hash" not in str(listing) and set(editor_row) == USER_FIELDS
    searched = client.get("/admin/api/users", params={"q": "edit"}, headers=admin.headers).json()
    assert [item["username"] for item in searched["items"]] == ["editor"] and searched["total"] == 1
    one = client.get(f"/admin/api/users/{editor_row['id']}", headers=admin.headers).json()
    assert one["projects"] == [{"project_id": world.project_id, "name": "Building permit", "role": "editor"}]
    assert client.get("/admin/api/users/nope", headers=admin.headers).json()["code"] == "not_found"

    projects = client.get("/admin/api/projects", headers=admin.headers).json()
    assert {item["name"] for item in projects["items"]} == {"Building permit", "Demolition permit"}
    building = next(item for item in projects["items"] if item["project_id"] == world.project_id)
    assert {member["username"] for member in building["members"]} == {"manager", "editor", "contributor", "viewer"}
    assert building["topics"] == 0 and building["documents"] == 0 and building["models"] == 0
    assert [p["name"] for p in client.get("/admin/api/projects?q=demo", headers=admin.headers).json()["items"]] == [
        "Demolition permit"
    ]
    project = client.get(f"/admin/api/projects/{world.project_id}", headers=admin.headers).json()
    assert "topic_status" in project["extensions"] and len(project["members"]) == 4

    clients = client.get("/admin/api/clients", headers=admin.headers).json()
    public = next(item for item in clients["items"] if item["client_id"] == world.public_client_id)
    assert public["public"] is True and public["last_used_at"], "token issuance was noted"
    assert "secret" not in str(clients).lower()

    sessions = client.get("/admin/api/sessions", headers=admin.headers).json()
    kinds = {item["kind"] for item in sessions["items"]}
    assert "oauth2" in kinds and sessions["total"] >= 2 and all(item["id"] for item in sessions["items"])
    mine = client.get("/admin/api/sessions", params={"user": "editor"}, headers=admin.headers).json()
    assert mine["items"] and all(item["username"] == "editor" for item in mine["items"])

    events = client.get("/admin/api/audit", params={"type": "auth.code"}, headers=admin.headers).json()
    assert events["items"] and all(item["type"].startswith("auth.code") for item in events["items"])
    assert any(item["request_id"] for item in events["items"]), "events carry the request id of their request"
    since = client.get("/admin/api/audit", params={"since": "2999-01-01T00:00:00Z"}, headers=admin.headers).json()
    assert since["items"] == []

    settings = client.get("/admin/api/settings", headers=admin.headers).json()
    assert settings["environment"] == "test" and settings["request_log"]["retention_hours"] == 72
    assert "admin_api" in settings["modules"] and "OPENCDE_SECRET_KEY" not in settings["raw"]
    assert "OPENCDE_GRAPH_PASSWORD" not in str(settings)
    health = client.get("/admin/api/health", headers=admin.headers).json()
    assert health["checks"] and all({"name", "ok", "detail"} <= set(item) for item in health["checks"])


def test_the_api_refuses_everyone_but_administrators_with_the_scope(client: TestClient, world: World) -> None:
    editor = login_with_scope(client, world, "editor", "profile admin")  # the scope without the role
    assert client.get("/admin/api/users", headers=editor.headers).json()["code"] == "forbidden"
    admin_without_scope = login_as(client, world, "admin")
    assert client.get("/admin/api/users", headers=admin_without_scope.headers).json()["code"] == "insufficient_scope"
    assert client.get("/admin/api/users").json()["code"] == "unauthenticated"


def test_dangerous_calls_need_a_recent_authentication() -> None:
    def principal(auth_time: str | None) -> Principal:
        return Principal(
            user_id="u",
            username="admin",
            display_name="admin",
            is_admin=True,
            client_id="c",
            scopes=("admin",),
            token_hash="h",
            auth_time=auth_time,
        )

    assert fresh_admin_principal(principal(later_iso(-60))).username == "admin"
    for stale in (None, later_iso(-REAUTHENTICATION_WINDOW_SECONDS - 5)):
        with pytest.raises(ApiError) as refused:
            fresh_admin_principal(principal(stale))
        assert refused.value.status_code == 403 and refused.value.code == "reauthentication_required"
