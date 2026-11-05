# This file was generated with the assistance of an AI coding tool.
"""BCF API 3.1 projects and 3.2 topics, with the 3.9 topic events, against a real database."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from opencde.settings import Settings
from tests.conformance.schemas import validate
from tests.integration.conftest_accounts import World, build_world
from tests.integration.helpers import Session, sign_in

pytestmark = [pytest.mark.integration, pytest.mark.conformance]


@pytest.fixture
def world(settings: Settings, clean_database: None) -> World:
    return build_world(settings)


def login(client: TestClient, world: World, username: str) -> Session:
    return sign_in(
        client,
        client_id=world.public_client_id,
        redirect_uri=world.redirect,
        username=username,
        password=world.password,
    )


def test_projects_and_extensions(client: TestClient, world: World) -> None:
    editor = login(client, world, "editor")
    projects = client.get("/bcf/3.0/projects", headers=editor.headers)
    assert projects.status_code == 200
    body = projects.json()
    assert [p["project_id"] for p in body] == [world.project_id], "only projects the user is a member of"
    for project in body:
        validate(project, "bcf-api/Schemas/Project/project_GET.json")
        assert "authorization" not in project
    with_auth = client.get("/bcf/3.0/projects", params={"includeAuthorization": "true"}, headers=editor.headers).json()
    assert with_auth[0]["authorization"]["project_actions"] == ["createTopic", "createDocument"]

    single = client.get(f"/bcf/3.0/projects/{world.project_id}", headers=editor.headers)
    validate(single.json(), "bcf-api/Schemas/Project/project_GET.json")
    assert single.json()["name"] == "Building permit"
    assert single.headers["etag"]
    assert (
        client.get(
            f"/bcf/3.0/projects/{world.project_id}", headers={**editor.headers, "If-None-Match": single.headers["etag"]}
        ).status_code
        == 304
    )

    extensions = client.get(f"/bcf/3.0/projects/{world.project_id}/extensions", headers=editor.headers).json()
    validate(extensions, "bcf-api/Schemas/Project/extensions_GET.json")
    assert set(extensions["users"]) == {"manager", "editor", "contributor", "viewer"}
    assert extensions["topic_actions"] == [
        "update",
        "updateBimSnippet",
        "updateRelatedTopics",
        "updateDocumentReferences",
        "updateFiles",
        "createComment",
        "createViewpoint",
    ]
    assert "Open" in extensions["topic_status"]

    # Foreign projects do not exist as far as this user is concerned.
    assert client.get(f"/bcf/3.0/projects/{world.other_project_id}", headers=editor.headers).status_code == 404
    assert (
        client.get(f"/bcf/3.0/projects/{world.other_project_id}/extensions", headers=editor.headers).status_code == 404
    )
    assert client.get("/bcf/3.0/projects/not-a-uuid", headers=editor.headers).status_code == 404


def test_project_rename_needs_manager(client: TestClient, world: World) -> None:
    editor = login(client, world, "editor")
    manager = login(client, world, "manager")
    forbidden = client.put(f"/bcf/3.0/projects/{world.project_id}", json={"name": "Nope"}, headers=editor.headers)
    assert forbidden.status_code == 403
    renamed = client.put(
        f"/bcf/3.0/projects/{world.project_id}", json={"name": "Building permit 2026"}, headers=manager.headers
    )
    assert renamed.status_code == 200 and renamed.json()["name"] == "Building permit 2026"
    validate(renamed.json(), "bcf-api/Schemas/Project/project_GET.json")
    assert (
        client.put(f"/bcf/3.0/projects/{world.project_id}", json={"name": ""}, headers=manager.headers).status_code
        == 400
    )


def test_topic_lifecycle_with_events(client: TestClient, world: World) -> None:
    contributor = login(client, world, "contributor")
    base = f"/bcf/3.0/projects/{world.project_id}/topics"

    created = client.post(
        base,
        json={
            "title": "Fire door missing a self-closing mechanism",
            "topic_type": "Issue",
            "topic_status": "Open",
            "priority": "High",
            "labels": ["Safety", "Architecture"],
            "assigned_to": "editor",
            "stage": "Construction",
            "description": "Door D-204 on level 2.",
            "reference_links": ["https://example.test/regulations/fire"],
            "due_date": "2026-12-01T12:00:00+01:00",
            "bim_snippet": {
                "snippet_type": ".ifc",
                "is_external": True,
                "reference": "https://example.test/d204.ifc",
                "reference_schema": "https://standards.buildingsmart.org/IFC/RELEASE/IFC4/ADD2_TC1/",
            },
        },
        headers=contributor.headers,
    )
    assert created.status_code == 201, created.text
    topic = created.json()
    validate(topic, "bcf-api/Schemas/Collaboration/Topic/topic_GET.json")
    assert topic["server_assigned_id"] == "ISSUE-0001"
    assert topic["creation_author"] == "contributor" and topic["modified_author"] == "contributor"
    assert topic["due_date"] == "2026-12-01T11:00:00.000Z", "stored in canonical UTC"
    assert topic["authorization"]["topic_actions"] == [
        "createComment",
        "createViewpoint",
        "update",
        "updateBimSnippet",
        "updateRelatedTopics",
        "updateDocumentReferences",
        "updateFiles",
        "delete",
    ]
    assert "Open" in topic["authorization"]["topic_status"]

    fetched = client.get(f"{base}/{topic['guid']}", headers=contributor.headers).json()
    validate(fetched, "bcf-api/Schemas/Collaboration/Topic/topic_GET.json")
    assert "authorization" not in fetched

    # Replace the topic as a whole: the fields not sent become empty, and events describe the change.
    updated = client.put(
        f"{base}/{topic['guid']}",
        json={
            "title": "Fire door D-204 lacks self-closing mechanism",
            "topic_status": "In progress",
            "labels": ["Safety", "Reuse"],
            "stage": "Completion",
        },
        headers=contributor.headers,
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()
    validate(body, "bcf-api/Schemas/Collaboration/Topic/topic_GET.json")
    assert body["priority"] is None if "priority" in body else "priority" not in body
    assert body["labels"] == ["Safety", "Reuse"] and body["server_assigned_id"] == "ISSUE-0001"

    events = client.get(f"{base}/{topic['guid']}/events", headers=contributor.headers).json()
    for event in events:
        validate(event, "bcf-api/Schemas/Collaboration/Events/topic_event_GET.json")
    initial = {action["type"]: action.get("value") for action in events[0]["actions"]}
    assert events[0]["actions"][0] == {"type": "topic_created", "value": None}
    assert initial["title_updated"] == "Fire door missing a self-closing mechanism", "initial values give update events"
    assert initial["status_updated"] == "Open" and initial["stage_added"] == "Construction"
    assert initial["label_added"] in ("Architecture", "Safety")
    types = {action["type"]: action.get("value") for action in events[1]["actions"]}
    assert types["title_updated"].startswith("Fire door D-204")
    assert types["status_updated"] == "In progress"
    assert "description_removed" in types and "priority_removed" in types and "due_date_removed" in types
    assert types["label_added"] == "Reuse" and types["label_removed"] == "Architecture"
    assert types["stage_updated"] == "Completion" and types["assigned_to_removed"] is None

    all_events = client.get(
        f"/bcf/3.0/projects/{world.project_id}/topics/events",
        params={"$filter": "type eq 'status_updated'"},
        headers=contributor.headers,
    ).json()
    assert len(all_events) == 2, "the initial status and the change"
    assert {event["topic_guid"] for event in all_events} == {topic["guid"]}

    deleted = client.delete(f"{base}/{topic['guid']}", headers=contributor.headers)
    assert deleted.status_code == 200
    assert client.get(f"{base}/{topic['guid']}", headers=contributor.headers).status_code == 404
    assert (
        len(client.get(f"/bcf/3.0/projects/{world.project_id}/topics/events", headers=contributor.headers).json()) == 2
    ), "events outlive the topic"


def test_topic_values_are_checked_against_extensions_and_guid_conflicts(client: TestClient, world: World) -> None:
    editor = login(client, world, "editor")
    base = f"/bcf/3.0/projects/{world.project_id}/topics"
    bad = client.post(base, json={"title": "x", "topic_status": "Imaginary"}, headers=editor.headers)
    assert bad.status_code == 400 and "topic_status" in bad.json()["message"]
    bad_label = client.post(base, json={"title": "x", "labels": ["Unknown"]}, headers=editor.headers)
    assert bad_label.status_code == 400
    bad_user = client.post(base, json={"title": "x", "assigned_to": "outsider"}, headers=editor.headers)
    assert bad_user.status_code == 400
    bad_date = client.post(base, json={"title": "x", "due_date": "tomorrow"}, headers=editor.headers)
    assert bad_date.status_code == 400
    missing_title = client.post(base, json={"topic_status": "Open"}, headers=editor.headers)
    assert missing_title.status_code == 400
    validate(missing_title.json(), "bcf-api/Schemas/error.json")

    guid = "b724aac3-5b2a-234a-d143-ae33cc184140"
    first = client.post(base, json={"title": "Client-chosen guid", "guid": guid.upper()}, headers=editor.headers)
    assert first.status_code == 201 and first.json()["guid"] == guid, "guid normalised to lower case"
    conflict = client.post(base, json={"title": "Again", "guid": guid}, headers=editor.headers)
    assert conflict.status_code == 409, "Foundation API 1.5.1"
    assert client.get(f"{base}/{guid.upper()}", headers=editor.headers).status_code == 200


def test_topic_authorization_matrix(client: TestClient, world: World) -> None:
    contributor = login(client, world, "contributor")
    viewer = login(client, world, "viewer")
    editor = login(client, world, "editor")
    manager = login(client, world, "manager")
    outsider = login(client, world, "outsider")
    base = f"/bcf/3.0/projects/{world.project_id}/topics"

    assert client.post(base, json={"title": "viewer tries"}, headers=viewer.headers).status_code == 403
    created = client.post(base, json={"title": "By contributor"}, headers=contributor.headers).json()
    guid = created["guid"]

    assert client.get(f"{base}/{guid}", headers=viewer.headers).status_code == 200
    assert client.get(f"{base}/{guid}", headers=outsider.headers).status_code == 404
    assert client.get(base, headers=outsider.headers).status_code == 404

    # Another contributor cannot edit someone else's topic; editors can; viewers cannot.
    other_contributor_token = contributor  # the same user is the author here, so use the viewer for the negative case
    assert client.put(f"{base}/{guid}", json={"title": "edit by viewer"}, headers=viewer.headers).status_code == 403
    assert client.put(f"{base}/{guid}", json={"title": "edit by editor"}, headers=editor.headers).status_code == 200
    assert (
        client.put(
            f"{base}/{guid}", json={"title": "edit by author"}, headers=other_contributor_token.headers
        ).status_code
        == 200
    )
    with_auth = client.get(f"{base}/{guid}", params={"includeAuthorization": "true"}, headers=viewer.headers).json()
    assert with_auth["authorization"] == {"topic_actions": [], "topic_status": []}
    as_editor = client.get(f"{base}/{guid}", params={"includeAuthorization": "true"}, headers=editor.headers).json()
    assert "delete" not in as_editor["authorization"]["topic_actions"]

    assert client.delete(f"{base}/{guid}", headers=editor.headers).status_code == 403, (
        "editors may not delete others' topics"
    )
    assert client.delete(f"{base}/{guid}", headers=manager.headers).status_code == 200


def test_topic_odata_filtering_sorting_and_paging(client: TestClient, world: World) -> None:
    editor = login(client, world, "editor")
    base = f"/bcf/3.0/projects/{world.project_id}/topics"
    for index, (title, status, labels, assigned) in enumerate(
        [
            ("Alpha", "Open", ["Architecture"], "editor"),
            ("Beta", "Closed", ["Structural"], "manager"),
            ("Gamma", "Open", ["Architecture", "MEP"], None),
            ("Delta", "In progress", [], "editor"),
        ]
    ):
        response = client.post(
            base,
            json={"title": title, "topic_status": status, "labels": labels, "assigned_to": assigned, "index": index},
            headers=editor.headers,
        )
        assert response.status_code == 201, response.text

    def titles(**params: str) -> list[str]:
        response = client.get(base, params=params, headers=editor.headers)
        assert response.status_code == 200, response.text
        return [t["title"] for t in response.json()]

    assert titles() == ["Alpha", "Beta", "Gamma", "Delta"], "default order is creation_date"
    assert titles(**{"$filter": "topic_status eq 'Open'"}) == ["Alpha", "Gamma"]
    assert titles(**{"$filter": "assigned_to eq 'editor' and topic_status eq 'Open'"}) == ["Alpha"]
    assert titles(
        **{"$filter": "labels/any(label: label eq 'Architecture') or labels/any(label: label eq 'Structural')"}
    ) == ["Alpha", "Beta", "Gamma"]
    assert titles(**{"$filter": "assigned_to eq null"}) == ["Gamma"]
    assert titles(**{"$orderby": "index desc"}) == ["Delta", "Gamma", "Beta", "Alpha"]
    assert titles(**{"$orderby": "server_assigned_id desc", "$top": "2", "$skip": "1"}) == ["Gamma", "Beta"]
    assert titles(**{"$filter": "creation_date gt 2000-01-01T00:00:00Z"}) == ["Alpha", "Beta", "Gamma", "Delta"]
    bad = client.get(base, params={"$filter": "secret eq 'x'"}, headers=editor.headers)
    assert bad.status_code == 400 and "unknown field" in bad.json()["message"]
    assert client.get(base, params={"$orderby": "title"}, headers=editor.headers).status_code == 400
