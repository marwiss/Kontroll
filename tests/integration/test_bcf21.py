# This file was generated with the assistance of an AI coding tool.
"""BCF API 2.1 against a real database, validated against its own pinned schemas.

Each test writes through one version and reads through the other where the two say different things, since both
work on the same data: a client of 2.1 and a client of 3.0 can share a project.
"""

from __future__ import annotations

import base64
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from opencde import ratelimit
from opencde.main import create_app
from opencde.settings import Settings
from tests.conformance.schemas import validate
from tests.integration.conftest_accounts import REDIRECT, World, build_world, login_as
from tests.integration.helpers import FORM_TOKEN, Session, basic_auth

pytestmark = [pytest.mark.integration, pytest.mark.conformance]

SCHEMAS = "bcf-api-2.1/Schemas_draft-03"
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c63f8ffff3f0005fe02fea7358184"
    "0000000049454e44ae426082"
)
AN_ID = "00000000-0000-4000-8000-000000000000"
POINT = {"x": 1.0, "y": 2.0, "z": 3.0}
PERSPECTIVE = {
    "camera_view_point": POINT,
    "camera_direction": {"x": 0.0, "y": 1.0, "z": 0.0},
    "camera_up_vector": {"x": 0.0, "y": 0.0, "z": 1.0},
    "field_of_view": 60.0,
}
ORTHOGONAL = {
    "camera_view_point": POINT,
    "camera_direction": {"x": 0.0, "y": -1.0, "z": 0.0},
    "camera_up_vector": {"x": 0.0, "y": 0.0, "z": 1.0},
    "view_to_world_scale": 2.0,
}


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


@pytest.fixture
def world(settings: Settings, clean_database: None) -> World:
    return build_world(settings)


def _project(world: World, version: str = "2.1") -> str:
    return f"/bcf/{version}/projects/{world.project_id}"


def _topic(client: TestClient, world: World, session: Session, **fields: Any) -> dict[str, Any]:
    response = client.post(f"{_project(world)}/topics", json={"title": "A topic", **fields}, headers=session.headers)
    assert response.status_code == 201, response.text
    return response.json()


def test_the_current_user_and_who_may_ask(client: TestClient, world: World) -> None:
    assert client.get("/bcf/2.1/current-user").status_code == 401
    editor = login_as(client, world, "editor")
    body = client.get("/bcf/2.1/current-user", headers=editor.headers).json()
    validate(body, f"{SCHEMAS}/User/user_GET.json")
    assert body["id"] == "editor"


def test_projects_and_extensions(client: TestClient, world: World) -> None:
    manager = login_as(client, world, "manager")
    listed = client.get("/bcf/2.1/projects", params={"includeAuthorization": "true"}, headers=manager.headers).json()
    assert [project["project_id"] for project in listed] == [world.project_id]
    validate(listed[0], f"{SCHEMAS}/Project/project_GET.json")
    assert "createTopic" in listed[0]["authorization"]["project_actions"]

    renamed = client.put(_project(world), json={"name": "Renamed"}, headers=manager.headers)
    assert renamed.status_code == 200 and renamed.json()["name"] == "Renamed"
    validate(client.get(_project(world), headers=manager.headers).json(), f"{SCHEMAS}/Project/project_GET.json")

    extensions = client.get(f"{_project(world)}/extensions", headers=manager.headers).json()
    validate(extensions, f"{SCHEMAS}/Project/extensions_GET.json")
    assert (
        set(extensions["user_id_type"]) == {"manager", "editor", "contributor", "viewer"} and "users" not in extensions
    )
    newer = client.get(f"{_project(world, '3.0')}/extensions", headers=manager.headers).json()
    assert newer["users"] == extensions["user_id_type"] and "user_id_type" not in newer


def test_a_topic_has_the_shape_of_2_1(client: TestClient, world: World) -> None:
    editor = login_as(client, world, "editor")
    created = _topic(client, world, editor, topic_status="Open", labels=["Architecture"], guid=AN_ID)
    validate(created, f"{SCHEMAS}/Collaboration/Topic/topic_GET.json")
    assert created["guid"] != AN_ID, "the server makes the guid, and an unknown property is ignored"
    assert "server_assigned_id" not in created
    assert created["authorization"]["topic_actions"], "a write answers with what the user may do next"

    topic = f"{_project(world)}/topics/{created['guid']}"
    plain = client.get(topic, headers=editor.headers).json()
    validate(plain, f"{SCHEMAS}/Collaboration/Topic/topic_GET.json")
    assert "authorization" not in plain and "server_assigned_id" not in plain
    authorized = client.get(topic, params={"includeAuthorization": "true"}, headers=editor.headers).json()
    assert "update" in authorized["authorization"]["topic_actions"]

    changed = client.put(topic, json={"title": "Another title", "topic_status": "Closed"}, headers=editor.headers)
    assert changed.status_code == 200 and changed.json()["title"] == "Another title"
    assert "server_assigned_id" not in changed.json()

    through_3_0 = client.get(f"{_project(world, '3.0')}/topics/{created['guid']}", headers=editor.headers).json()
    assert through_3_0["title"] == "Another title" and through_3_0["server_assigned_id"].startswith("ISSUE-")


def test_a_label_is_asked_after_the_way_2_1_writes_it(client: TestClient, world: World) -> None:
    editor = login_as(client, world, "editor")
    wanted = _topic(client, world, editor, labels=["Architecture"])
    _topic(client, world, editor, labels=["Structural"])
    _topic(client, world, editor)
    found = client.get(
        f"{_project(world)}/topics", params={"$filter": "contains(labels, 'Architecture')"}, headers=editor.headers
    )
    assert found.status_code == 200, found.text
    assert [topic["guid"] for topic in found.json()] == [wanted["guid"]]
    assert all("server_assigned_id" not in topic for topic in found.json())
    ordered = client.get(f"{_project(world)}/topics", params={"$orderby": "creation_date desc"}, headers=editor.headers)
    assert len(ordered.json()) == 3


def test_a_file_is_a_file_name_in_2_1_and_a_filename_in_3_0(client: TestClient, world: World) -> None:
    editor = login_as(client, world, "editor")
    guid = _topic(client, world, editor)["guid"]
    files = f"{_project(world)}/topics/{guid}/files"
    reference = {
        "ifc_project": "0J$yPqHBD12v72y4qF6XcD",
        "file_name": "OfficeBuilding_Architecture_0001.ifc",
        "reference": "https://example.com/files/0J$yPqHBD12v72y4qF6XcD_0001.ifc",
    }
    stored = client.put(files, json=[reference], headers=editor.headers)
    assert stored.status_code == 200, stored.text
    assert stored.json() == [reference]
    read = client.get(files, headers=editor.headers).json()
    assert read == [reference]
    validate(read[0], f"{SCHEMAS}/Collaboration/File/file_GET.json")
    newer = client.get(f"{_project(world, '3.0')}/topics/{guid}/files", headers=editor.headers).json()
    assert newer[0]["filename"] == reference["file_name"] and "file_name" not in newer[0]


def test_comments_can_answer_each_other(client: TestClient, world: World) -> None:
    editor = login_as(client, world, "editor")
    guid = _topic(client, world, editor)["guid"]
    comments = f"{_project(world)}/topics/{guid}/comments"

    first = client.post(comments, json={"comment": "What about the door?", "guid": AN_ID}, headers=editor.headers)
    assert first.status_code == 201, first.text
    validate(first.json(), f"{SCHEMAS}/Collaboration/Comment/comment_GET.json")
    assert first.json()["guid"] != AN_ID and "reply_to_comment_guid" not in first.json()
    assert first.json()["authorization"]["comment_actions"]

    reply = client.post(
        comments, json={"comment": "It stays.", "reply_to_comment_guid": first.json()["guid"]}, headers=editor.headers
    )
    assert reply.status_code == 201, reply.text
    answer = reply.json()
    validate(answer, f"{SCHEMAS}/Collaboration/Comment/comment_GET.json")
    assert answer["reply_to_comment_guid"] == first.json()["guid"]

    read = client.get(f"{comments}/{answer['guid']}", headers=editor.headers).json()
    assert read["reply_to_comment_guid"] == first.json()["guid"] and "authorization" not in read
    listed = client.get(comments, headers=editor.headers).json()
    assert {item["guid"]: item.get("reply_to_comment_guid") for item in listed} == {
        first.json()["guid"]: None,
        answer["guid"]: first.json()["guid"],
    }

    # 3.0 knows nothing of replies: it does not show one, and its PUT leaves it where it is.
    newer = f"{_project(world, '3.0')}/topics/{guid}/comments/{answer['guid']}"
    assert "reply_to_comment_guid" not in client.get(newer, headers=editor.headers).json()
    put = client.put(newer, json={"comment": "It stays open."}, headers=editor.headers)
    assert put.status_code == 200 and "reply_to_comment_guid" not in put.json()
    kept = client.get(f"{comments}/{answer['guid']}", headers=editor.headers).json()
    assert kept["comment"] == "It stays open." and kept["reply_to_comment_guid"] == first.json()["guid"]

    # 2.1's PUT replaces the whole comment, the reply with it.
    cleared = client.put(f"{comments}/{answer['guid']}", json={"comment": "Standalone"}, headers=editor.headers)
    assert cleared.status_code == 200 and "reply_to_comment_guid" not in cleared.json()
    again = client.put(
        f"{comments}/{answer['guid']}",
        json={"comment": "Answering", "reply_to_comment_guid": first.json()["guid"]},
        headers=editor.headers,
    )
    assert again.json()["reply_to_comment_guid"] == first.json()["guid"]


def test_a_reply_has_to_answer_a_comment_of_the_topic(client: TestClient, world: World) -> None:
    editor = login_as(client, world, "editor")
    guid = _topic(client, world, editor)["guid"]
    other = _topic(client, world, editor)["guid"]
    comments = f"{_project(world)}/topics/{guid}/comments"
    elsewhere = client.post(
        f"{_project(world)}/topics/{other}/comments", json={"comment": "Elsewhere"}, headers=editor.headers
    ).json()["guid"]

    for bad in ("not-a-guid", AN_ID, elsewhere):
        refused = client.post(comments, json={"comment": "x", "reply_to_comment_guid": bad}, headers=editor.headers)
        assert refused.status_code == 400, refused.text

    own = client.post(comments, json={"comment": "x"}, headers=editor.headers).json()["guid"]
    to_itself = client.put(
        f"{comments}/{own}", json={"comment": "x", "reply_to_comment_guid": own}, headers=editor.headers
    )
    assert to_itself.status_code == 400, to_itself.text


def test_deleting_what_a_comment_answers_ends_the_reply(client: TestClient, world: World) -> None:
    editor = login_as(client, world, "editor")
    guid = _topic(client, world, editor)["guid"]
    comments = f"{_project(world)}/topics/{guid}/comments"
    first = client.post(comments, json={"comment": "Question"}, headers=editor.headers).json()["guid"]
    answer = client.post(
        comments, json={"comment": "Answer", "reply_to_comment_guid": first}, headers=editor.headers
    ).json()["guid"]

    assert client.delete(f"{comments}/{first}", headers=editor.headers).status_code == 200
    assert "reply_to_comment_guid" not in client.get(f"{comments}/{answer}", headers=editor.headers).json()
    events = client.get(f"{comments}/{answer}/events", headers=editor.headers).json()
    types = [action["type"] for event in events for action in event["actions"]]
    assert types.count("reply_to_comment_updated") == 1 and types.count("reply_to_comment_removed") == 1


def test_each_version_answers_with_the_events_it_knows(client: TestClient, world: World) -> None:
    editor = login_as(client, world, "editor")
    created = _topic(client, world, editor, stage="Construction", topic_status="Open")
    guid = created["guid"]
    older, newer = _project(world), _project(world, "3.0")

    topic_events = client.get(f"{older}/topics/{guid}/events", headers=editor.headers).json()
    for event in topic_events:
        validate(event, f"{SCHEMAS}/Collaboration/Events/topic_event_GET.json")
    types = {action["type"] for event in topic_events for action in event["actions"]}
    assert "topic_created" in types and "status_updated" in types and not any("stage" in kind for kind in types)
    newer_types = {
        action["type"]
        for event in client.get(f"{newer}/topics/{guid}/events", headers=editor.headers).json()
        for action in event["actions"]
    }
    assert "stage_added" in newer_types

    # An event of nothing but stages has no action left in 2.1, so it is not there at all.
    client.put(
        f"{older}/topics/{guid}",
        json={"title": "A topic", "topic_status": "Open", "stage": "Completion"},
        headers=editor.headers,
    )
    assert len(client.get(f"{older}/topics/{guid}/events", headers=editor.headers).json()) == len(topic_events)
    everywhere = client.get(
        f"{older}/topics/events", params={"$filter": f"topic_guid eq '{guid}'"}, headers=editor.headers
    )
    assert everywhere.status_code == 200 and len(everywhere.json()) == len(topic_events)

    comments = f"{older}/topics/{guid}/comments"
    first = client.post(comments, json={"comment": "Question"}, headers=editor.headers).json()["guid"]
    answer = client.post(
        comments, json={"comment": "Answer", "reply_to_comment_guid": first}, headers=editor.headers
    ).json()["guid"]
    comment_events = client.get(f"{comments}/{answer}/events", headers=editor.headers).json()
    validate(comment_events[0], f"{SCHEMAS}/Collaboration/Events/comment_event_GET.json")
    assert "reply_to_comment_updated" in {action["type"] for action in comment_events[0]["actions"]}
    in_3_0 = client.get(f"{newer}/topics/{guid}/comments/{answer}/events", headers=editor.headers).json()
    assert "reply_to_comment_updated" not in {action["type"] for action in in_3_0[0]["actions"]}
    assert {
        event["comment_guid"] for event in client.get(f"{older}/topics/comments/events", headers=editor.headers).json()
    } == {first, answer}


def test_a_viewpoint_has_no_aspect_ratio_in_2_1(client: TestClient, world: World) -> None:
    editor = login_as(client, world, "editor")
    viewer = login_as(client, world, "viewer")
    guid = _topic(client, world, editor)["guid"]
    viewpoints = f"{_project(world)}/topics/{guid}/viewpoints"
    body = {
        "guid": AN_ID,
        "index": 3,
        "perspective_camera": PERSPECTIVE,
        "lines": [{"start_point": POINT, "end_point": {"x": 0.0, "y": 0.0, "z": 0.0}}],
        "clipping_planes": [{"location": POINT, "direction": {"x": 0.0, "y": 0.0, "z": -1.0}}],
        "bitmaps": [
            {
                "bitmap_type": "png",
                "bitmap_data": b64(PNG),
                "location": POINT,
                "normal": {"x": 0.0, "y": 0.0, "z": 1.0},
                "up": {"x": 0.0, "y": 1.0, "z": 0.0},
                "height": 1.0,
            }
        ],
        "snapshot": {"snapshot_type": "png", "snapshot_data": b64(PNG)},
        "components": {
            "selection": [{"ifc_guid": "1Xezbq735AdBO_4DerG66G", "originating_system": "Archicad"}],
            # The specification's own example writes a colour like this, though its text says hexadecimal digits.
            "coloring": [{"color": "#ff0000", "components": [{"ifc_guid": "3eT96F_cnDsOufCEsotwtp"}]}],
            "visibility": {"default_visibility": True, "exceptions": [{"ifc_guid": "3k3LbXmTfDWODxdSuyCGYE"}]},
        },
    }
    created = client.post(viewpoints, json=body, headers=editor.headers)
    assert created.status_code == 201, created.text
    viewpoint = created.json()
    validate(viewpoint, f"{SCHEMAS}/Collaboration/Viewpoint/viewpoint_GET.json")
    assert viewpoint["guid"] != AN_ID and viewpoint["perspective_camera"] == PERSPECTIVE
    assert "authorization" not in viewpoint and viewpoint["snapshot"] == {"snapshot_type": "png"}
    one = f"{viewpoints}/{viewpoint['guid']}"

    listed = client.get(viewpoints, headers=viewer.headers).json()
    assert [item["guid"] for item in listed] == [viewpoint["guid"]]
    validate(listed[0], f"{SCHEMAS}/Collaboration/Viewpoint/viewpoint_GET.json")
    assert client.get(one, headers=viewer.headers).json() == viewpoint

    assert client.get(f"{one}/snapshot", headers=viewer.headers).content == PNG
    bitmap = client.get(f"{one}/bitmaps/{viewpoint['bitmaps'][0]['guid']}", headers=viewer.headers)
    assert bitmap.status_code == 200 and bitmap.content == PNG
    selection = client.get(f"{one}/selection", headers=viewer.headers).json()
    validate(selection, f"{SCHEMAS}/Collaboration/Viewpoint/selection_GET.json")
    assert selection["selection"][0]["ifc_guid"] == "1Xezbq735AdBO_4DerG66G"
    coloring = client.get(f"{one}/coloring", headers=viewer.headers).json()
    validate(coloring, f"{SCHEMAS}/Collaboration/Viewpoint/coloring_GET.json")
    assert coloring["coloring"][0]["color"] == "FF0000"
    visibility = client.get(f"{one}/visibility", headers=viewer.headers).json()
    validate(visibility, f"{SCHEMAS}/Collaboration/Viewpoint/visibility_GET.json")
    assert visibility["visibility"]["default_visibility"] is True

    newer = f"{_project(world, '3.0')}/topics/{guid}/viewpoints/{viewpoint['guid']}"
    through_3_0 = client.get(newer, headers=viewer.headers).json()
    assert through_3_0["perspective_camera"]["aspect_ratio"] == 1.0, "3.0 requires one, so it gets a neutral value"

    assert client.delete(one, headers=editor.headers).status_code == 405, "deleting a viewpoint came with 3.0"
    assert client.delete(newer, headers=editor.headers).status_code == 200


def test_a_viewpoint_made_through_3_0_reads_as_2_1(client: TestClient, world: World) -> None:
    editor = login_as(client, world, "editor")
    guid = _topic(client, world, editor)["guid"]
    camera = {**ORTHOGONAL, "aspect_ratio": 1.5}
    created = client.post(
        f"{_project(world, '3.0')}/topics/{guid}/viewpoints", json={"orthogonal_camera": camera}, headers=editor.headers
    )
    assert created.status_code == 201, created.text
    assert created.json()["authorization"]["viewpoint_actions"]
    read = client.get(f"{_project(world)}/topics/{guid}/viewpoints/{created.json()['guid']}", headers=editor.headers)
    validate(read.json(), f"{SCHEMAS}/Collaboration/Viewpoint/viewpoint_GET.json")
    assert read.json()["orthogonal_camera"] == ORTHOGONAL and "authorization" not in read.json()


def test_the_rules_of_3_0_on_what_a_viewpoint_must_hold_are_not_those_of_2_1(client: TestClient, world: World) -> None:
    editor = login_as(client, world, "editor")
    guid = _topic(client, world, editor)["guid"]
    older = f"{_project(world)}/topics/{guid}/viewpoints"
    only_components = {"components": {"visibility": {"default_visibility": False}}}
    made = client.post(older, json=only_components, headers=editor.headers)
    assert made.status_code == 201, made.text
    assert (
        client.post(
            f"{_project(world, '3.0')}/topics/{guid}/viewpoints", json=only_components, headers=editor.headers
        ).status_code
        == 400
    )

    # What 3.0 then reads has no camera, which its rules do not allow but its schema does. It must still answer.
    through_3_0 = client.get(
        f"{_project(world, '3.0')}/topics/{guid}/viewpoints/{made.json()['guid']}", headers=editor.headers
    )
    assert through_3_0.status_code == 200 and through_3_0.json()["guid"] == made.json()["guid"]

    both = {"perspective_camera": PERSPECTIVE, "orthogonal_camera": ORTHOGONAL}
    assert client.post(older, json=both, headers=editor.headers).status_code == 400, "a viewpoint keeps one camera"


def test_related_topics_references_documents_and_snippets(client: TestClient, world: World) -> None:
    editor = login_as(client, world, "editor")
    project = _project(world)
    guid = _topic(
        client,
        world,
        editor,
        bim_snippet={
            "snippet_type": ".bcf",
            "is_external": False,
            "reference": "a.bcf",
            "reference_schema": "https://example.com/s.xsd",
        },
    )["guid"]
    other = _topic(client, world, editor)["guid"]
    topic = f"{project}/topics/{guid}"

    related = client.put(f"{topic}/related_topics", json=[{"related_topic_guid": other}], headers=editor.headers)
    assert related.status_code == 200, related.text
    read = client.get(f"{topic}/related_topics", headers=editor.headers).json()
    assert read == [{"related_topic_guid": other}]
    validate(read[0], f"{SCHEMAS}/Collaboration/RelatedTopic/related_topic_GET.json")

    upload = client.post(
        f"{project}/documents",
        content=b"the document's bytes",
        headers={
            **editor.headers,
            "Content-Type": "application/octet-stream",
            "Content-Disposition": 'attachment; filename="Plan.pdf"',
        },
    )
    assert upload.status_code == 201, upload.text
    document = upload.json()
    validate(document, f"{SCHEMAS}/Collaboration/Document/document_GET.json")
    assert document["filename"] == "Plan.pdf"
    assert client.get(f"{project}/documents", headers=editor.headers).json() == [document]
    assert (
        client.get(f"{project}/documents/{document['guid']}", headers=editor.headers).content == b"the document's bytes"
    )

    made = client.post(
        f"{topic}/document_references",
        json={"guid": AN_ID, "document_guid": document["guid"], "description": "The plan"},
        headers=editor.headers,
    )
    assert made.status_code == 201, made.text
    reference = made.json()
    validate(reference, f"{SCHEMAS}/Collaboration/DocumentReference/document_reference_GET.json")
    assert reference["guid"] != AN_ID, "the server makes the guid"
    changed = client.put(
        f"{topic}/document_references/{reference['guid']}",
        json={"guid": reference["guid"], "url": "https://example.com/plan.pdf", "description": "Elsewhere"},
        headers=editor.headers,
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["url"] == "https://example.com/plan.pdf" and "document_guid" not in changed.json()
    listed = client.get(f"{topic}/document_references", headers=editor.headers).json()
    assert [item["guid"] for item in listed] == [reference["guid"]]

    stored = client.put(
        f"{topic}/snippet",
        content=b"<snippet/>",
        headers={
            **editor.headers,
            "Content-Type": "application/octet-stream",
            "Content-Disposition": 'attachment; filename="a.bcf"',
        },
    )
    assert stored.status_code == 200, stored.text
    assert client.get(f"{topic}/snippet", headers=editor.headers).content == b"<snippet/>"

    assert client.delete(f"{project}/topics/{other}", headers=editor.headers).status_code == 200


def test_what_only_3_0_has_is_not_here(client: TestClient, world: World) -> None:
    editor = login_as(client, world, "editor")
    assert client.get(f"{_project(world)}/files_information", headers=editor.headers).status_code == 404
    assert client.get("/bcf/1.0/projects", headers=editor.headers).status_code == 404


def test_the_two_versions_agree_on_who_may_do_what(client: TestClient, world: World) -> None:
    viewer = login_as(client, world, "viewer")
    outsider = login_as(client, world, "outsider")
    editor = login_as(client, world, "editor")
    guid = _topic(client, world, editor)["guid"]
    project = _project(world)

    assert client.get(f"{project}/topics").status_code == 401
    assert client.get(f"{project}/topics", headers=outsider.headers).status_code == 404
    assert client.post(f"{project}/topics", json={"title": "No"}, headers=viewer.headers).status_code == 403
    topic = f"{project}/topics/{guid}"
    assert client.put(topic, json={"title": "No"}, headers=viewer.headers).status_code == 403
    assert client.delete(topic, headers=viewer.headers).status_code == 403
    assert client.post(f"{topic}/comments", json={"comment": "No"}, headers=viewer.headers).status_code == 403
    assert (
        client.post(f"{topic}/viewpoints", json={"perspective_camera": PERSPECTIVE}, headers=viewer.headers).status_code
        == 403
    )
    assert client.put(f"{topic}/files", json=[], headers=viewer.headers).status_code == 403
    extensions = client.get(f"{project}/extensions", headers=viewer.headers).json()
    assert "createTopic" not in extensions["project_actions"]


def test_an_error_has_the_body_of_2_1(client: TestClient, world: World) -> None:
    editor = login_as(client, world, "editor")
    answer = client.get(f"{_project(world)}/topics/{AN_ID}", headers=editor.headers)
    assert answer.status_code == 404
    validate(answer.json(), f"{SCHEMAS}/error.json")


# -- a client that registers itself the way 2.1 says -------------------------------------------------


@pytest.fixture
def open_for_registration(settings: Settings, world: World) -> Iterator[TestClient]:
    ratelimit.limiter.reset()
    with TestClient(
        create_app(settings.model_copy(update={"dynamic_client_registration": True}), startup_wait_seconds=30)
    ) as client:
        yield client


def _code(client: TestClient, world: World, client_id: str) -> str:
    page = client.get(
        "/foundation/oauth2/auth", params={"response_type": "code", "client_id": client_id, "state": "unique"}
    )
    assert page.status_code == 200, page.text[:300]
    token = FORM_TOKEN.search(page.text)
    assert token
    answer = client.post(
        "/foundation/oauth2/auth",
        data={"form_token": token.group(1), "username": "editor", "password": world.password, "decision": "allow"},
        follow_redirects=False,
    )
    assert answer.status_code == 302, answer.text[:300]
    return answer.headers["location"].split("code=")[1].split("&")[0]


def test_a_client_of_2_1_from_discovery_to_a_topic(open_for_registration: TestClient, world: World) -> None:
    """All that a client knowing nothing but 2.1 does: it never sees the Foundation API or PKCE."""
    client = open_for_registration
    assert "2.1" in [item["version_id"] for item in client.get("/bcf/versions").json()["versions"]]
    auth = client.get("/bcf/2.1/auth").json()
    registration = auth["oauth2_dynamic_client_reg_url"].removeprefix("http://testserver")
    assert registration == "/bcf/2.1/oauth2/reg"

    registered = client.post(
        registration,
        json={
            "client_name": "Example Application",
            "client_description": "x" * 4000,
            "client_url": "http://example.com",
            "redirect_url": REDIRECT,
        },
    )
    assert registered.status_code == 201, registered.text
    validate(registered.json(), f"{SCHEMAS}/Authentication/dynRegClient_GET.json")
    client_id, secret = registered.json()["client_id"], registered.json()["client_secret"]

    code = _code(client, world, client_id)
    token_url = auth["oauth2_token_url"].removeprefix("http://testserver")
    tokens = client.post(
        f"{token_url}?grant_type=authorization_code&code={code}", headers=basic_auth(client_id, secret)
    )
    assert tokens.status_code == 201, tokens.text
    bearer = {"Authorization": f"Bearer {tokens.json()['access_token']}"}

    assert client.get("/bcf/2.1/current-user", headers=bearer).json()["id"] == "editor"
    created = client.post(f"/bcf/2.1/projects/{world.project_id}/topics", json={"title": "From 2.1"}, headers=bearer)
    assert created.status_code == 201, created.text


def test_only_the_door_of_2_1_lets_a_client_leave_pkce_out(open_for_registration: TestClient, world: World) -> None:
    client = open_for_registration
    foundation = client.post("/foundation/oauth2/reg", json={"client_name": "Newer", "redirect_url": REDIRECT}).json()
    refused = client.get(
        "/foundation/oauth2/auth",
        params={"response_type": "code", "client_id": foundation["client_id"], "state": "s"},
        follow_redirects=False,
    )
    assert refused.status_code == 302 and "invalid_request" in refused.headers["location"]

    # A public client registered through that door gets no such thing: it has no secret to stand in for PKCE.
    public = client.post(
        "/bcf/2.1/oauth2/reg",
        json={"client_name": "Public", "redirect_url": REDIRECT, "token_endpoint_auth_method": "none"},
    ).json()
    assert "client_secret" not in public
    refused = client.get(
        "/foundation/oauth2/auth",
        params={"response_type": "code", "client_id": public["client_id"], "state": "s"},
        follow_redirects=False,
    )
    assert refused.status_code == 302 and "invalid_request" in refused.headers["location"]


def test_registration_through_2_1_is_off_with_the_rest(client: TestClient, world: World) -> None:
    answer = client.post("/bcf/2.1/oauth2/reg", json={"client_name": "No", "redirect_url": REDIRECT})
    assert answer.status_code == 404
