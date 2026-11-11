# This file was generated with the assistance of an AI coding tool.
"""A project's AI policy (F29 a, F30 a, ADR 0028): local from the start, set by its manager in the project
administration and by an administrator in the administration, every change audited, and read by every member through
the Documents API, never through an answer the OpenCDE specifications define."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from opencde.settings import Settings
from tests.conformance.schemas import validate
from tests.integration.conftest_accounts import World, build_world, login_as, login_with_scope
from tests.integration.test_admin_ui import notice_of, post
from tests.integration.test_web_signin import web_sign_in

pytestmark = [pytest.mark.integration, pytest.mark.conformance, pytest.mark.security]


@pytest.fixture
def world(settings: Settings, clean_database: None) -> World:
    return build_world(settings)


def audited(client: TestClient, world: World, prefix: str) -> list[tuple[str, dict]]:
    admin = login_with_scope(client, world, "admin", "profile admin")
    events = client.get("/admin/api/audit", params={"type": prefix}, headers=admin.headers).json()["items"]
    return [(event["actor"], event["details"]) for event in events]


def test_a_manager_sets_the_policy_and_every_member_reads_it(client: TestClient, world: World) -> None:
    policy = f"/documents/1.0/projects/{world.project_id}/ai-policy"
    project = f"/manage/1.0/projects/{world.project_id}"
    viewer = login_as(client, world, "viewer")
    first = client.get(policy, headers=viewer.headers)
    assert first.status_code == 200 and first.json() == {"project_id": world.project_id, "ai_policy": "local"}

    manager = login_with_scope(client, world, "manager", "profile bcf documents project")
    shown = client.get(project, headers=manager.headers)
    assert shown.status_code == 200, shown.text
    assert shown.json() == {"project_id": world.project_id, "name": "Building permit", "ai_policy": "local"}
    assert client.get("/manage/1.0/projects", headers=manager.headers).json()["items"] == [shown.json()]
    changed = client.put(project, json={"ai_policy": "cloud"}, headers=manager.headers)
    assert changed.status_code == 200 and changed.json() == {**shown.json(), "ai_policy": "cloud"}
    for name in ("viewer", "contributor", "editor", "manager"):
        member = login_as(client, world, name)
        assert client.get(policy, headers=member.headers).json()["ai_policy"] == "cloud", name

    # Refused: a value or a field the policy does not have, and every caller who is not a manager with the scope.
    assert client.put(project, json={"ai_policy": "anywhere"}, headers=manager.headers).status_code == 400
    assert client.put(project, json={"ai_policy": "local", "name": "x"}, headers=manager.headers).status_code == 400
    editor = login_with_scope(client, world, "editor", "profile project")
    assert client.put(project, json={"ai_policy": "local"}, headers=editor.headers).status_code == 403
    assert client.get(project, headers=editor.headers).status_code == 403
    outsider = login_with_scope(client, world, "outsider", "profile documents project")
    assert client.put(project, json={"ai_policy": "local"}, headers=outsider.headers).status_code == 404
    assert client.get(policy, headers=outsider.headers).status_code == 404, "not a member: the project is not there"
    other = f"/manage/1.0/projects/{world.other_project_id}"
    assert client.put(other, json={"ai_policy": "cloud"}, headers=manager.headers).status_code == 404
    unscoped = client.put(project, json={"ai_policy": "local"}, headers=login_as(client, world, "manager").headers)
    assert unscoped.status_code == 403 and unscoped.json()["code"] == "insufficient_scope", "asked for explicitly"
    assert client.get(policy, headers=viewer.headers).json()["ai_policy"] == "cloud", "nothing refused changed it"
    elsewhere = client.get(f"/documents/1.0/projects/{world.other_project_id}/ai-policy", headers=viewer.headers)
    assert elsewhere.status_code == 404 and elsewhere.json()["code"] == "not_found"

    # The answers the specifications define stay as buildingSMART defines them.
    bcf = client.get(f"/bcf/3.0/projects/{world.project_id}", headers=viewer.headers).json()
    validate(bcf, "bcf-api/Schemas/Project/project_GET.json")
    older = client.get(f"/bcf/2.1/projects/{world.project_id}", headers=viewer.headers).json()
    assert "ai_policy" not in bcf and "ai_policy" not in older

    expected = {"project_id": world.project_id, "ai_policy": "cloud"}
    assert audited(client, world, "manage.project.ai_policy") == [(world.users["manager"], expected)]


def test_an_administrator_sets_the_policy_in_the_api_and_on_the_page(client: TestClient, world: World) -> None:
    admin = login_with_scope(client, world, "admin", "profile admin")
    url = f"/admin/api/projects/{world.project_id}"
    assert client.get(url, headers=admin.headers).json()["ai_policy"] == "local"
    changed = client.patch(url, json={"ai_policy": "cloud"}, headers=admin.headers)
    assert changed.status_code == 200 and changed.json()["ai_policy"] == "cloud"
    assert client.patch(url, json={"ai_policy": "anywhere"}, headers=admin.headers).status_code == 400
    listed = client.get("/admin/api/projects", headers=admin.headers).json()["items"]
    assert {item["project_id"]: item["ai_policy"] for item in listed} == {
        world.project_id: "cloud",
        world.other_project_id: "local",
    }
    [(actor, details)] = audited(client, world, "admin.project.update")
    assert actor == world.users["admin"] and details == {"project_id": world.project_id, "ai_policy": "cloud"}

    web_sign_in(client, world, "admin")
    path = f"/admin/projects/{world.project_id}"
    page = client.get(path).text
    assert '<option value="cloud" selected>' in page and 'name="action" value="ai_policy"' in page
    assert notice_of(post(client, path, page, action="ai_policy", ai_policy="local")) == "saved"
    assert '<option value="local" selected>' in client.get(path).text
    assert notice_of(post(client, path, page, action="ai_policy", ai_policy="anywhere")) == "invalid"
    viewer = login_as(client, world, "viewer")
    policy = client.get(f"/documents/1.0/projects/{world.project_id}/ai-policy", headers=viewer.headers).json()
    assert policy["ai_policy"] == "local", "the page's choice, and nothing from the refused one"
    expected = {"project_id": world.project_id, "ai_policy": "local"}
    assert audited(client, world, "admin.project.ai_policy") == [(world.users["admin"], expected)]
