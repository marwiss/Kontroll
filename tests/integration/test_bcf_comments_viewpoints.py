# This file was generated with the assistance of an AI coding tool.
"""BCF API 3.4 comments, 3.5 viewpoints and 3.10 comment events, against a real database."""

from __future__ import annotations

import base64
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient

from opencde.settings import Settings
from tests.conformance.schemas import validate
from tests.integration.conftest_accounts import World, build_world, login_as
from tests.integration.helpers import Session

pytestmark = [pytest.mark.integration, pytest.mark.conformance]

SCHEMAS = "bcf-api/Schemas/Collaboration"

# A 1x1 transparent PNG and a minimal JPEG header: the server checks magic bytes, not pixels.
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c63f8ffff3f0005fe02fea7358184"
    "0000000049454e44ae426082"
)
JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00" + b"\x00" * 16 + b"\xff\xd9"

POINT = {"x": 1.0, "y": 2.0, "z": 3.0}
PERSPECTIVE = {
    "camera_view_point": POINT,
    "camera_direction": {"x": 0.0, "y": 1.0, "z": 0.0},
    "camera_up_vector": {"x": 0.0, "y": 0.0, "z": 1.0},
    "field_of_view": 60.0,
    "aspect_ratio": 1.5,
}
ORTHOGONAL = {
    "camera_view_point": POINT,
    "camera_direction": {"x": 0.0, "y": -1.0, "z": 0.0},
    "camera_up_vector": {"x": 0.0, "y": 0.0, "z": 1.0},
    "view_to_world_scale": 2.0,
    "aspect_ratio": 1.0,
}


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def full_viewpoint() -> dict[str, Any]:
    return {
        "index": 1,
        "perspective_camera": PERSPECTIVE,
        "lines": [{"start_point": {"x": 0, "y": 0, "z": 0}, "end_point": {"x": 1, "y": 1, "z": 1}}],
        "clipping_planes": [{"location": {"x": 0, "y": 0, "z": 2.5}, "direction": {"x": 0, "y": 0, "z": -1}}],
        "bitmaps": [
            {
                "bitmap_type": "png",
                "bitmap_data": b64(PNG),
                "location": POINT,
                "normal": {"x": 0, "y": 0, "z": 1},
                "up": {"x": 0, "y": 1, "z": 0},
                "height": 1.0,
            }
        ],
        "snapshot": {"snapshot_type": "png", "snapshot_data": b64(PNG)},
        "components": {
            "selection": [
                {"ifc_guid": "1Xezbq735AdBO_4DerG66G", "originating_system": "Archicad", "authoring_tool_id": "1"}
            ],
            "coloring": [
                {"color": "ff0000ff", "components": [{"ifc_guid": "3eT96F_cnDsOufCEsotwtp"}]},
                {
                    "color": "00ff00",
                    "components": [{"ifc_guid": "3k3LbXmTfDWODxdSuyCGYE"}, {"authoring_tool_id": "wall-3"}],
                },
            ],
            "visibility": {
                "default_visibility": True,
                "exceptions": [{"ifc_guid": "3eT96F_cnDsOufCEsotwtp"}],
                "view_setup_hints": {
                    "spaces_visible": False,
                    "space_boundaries_visible": False,
                    "openings_visible": True,
                },
            },
        },
    }


@pytest.fixture
def world(settings: Settings, clean_database: None) -> World:
    return build_world(settings)


def make_topic(client: TestClient, world: World, session: Session, **fields: Any) -> dict[str, Any]:
    response = client.post(
        f"/bcf/3.0/projects/{world.project_id}/topics", json={"title": "Topic", **fields}, headers=session.headers
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_viewpoint_lifecycle(client: TestClient, world: World) -> None:
    contributor = login_as(client, world, "contributor")
    viewer = login_as(client, world, "viewer")
    outsider = login_as(client, world, "outsider")
    topic = make_topic(client, world, contributor)
    base = f"/bcf/3.0/projects/{world.project_id}/topics/{topic['guid']}/viewpoints"

    time.sleep(0.002)
    created = client.post(base, json=full_viewpoint(), headers=contributor.headers)
    assert created.status_code == 201, created.text
    viewpoint = created.json()
    validate(viewpoint, f"{SCHEMAS}/Viewpoint/viewpoint_GET.json")
    assert viewpoint["snapshot"] == {"snapshot_type": "png"}, "image data is never echoed"
    assert viewpoint["bitmaps"][0]["guid"] and "bitmap_data" not in viewpoint["bitmaps"][0]
    assert "components" not in viewpoint
    assert viewpoint["perspective_camera"] == PERSPECTIVE and "orthogonal_camera" not in viewpoint
    assert viewpoint["authorization"] == {"viewpoint_actions": ["delete"]}
    guid = viewpoint["guid"]

    after = client.get(
        f"/bcf/3.0/projects/{world.project_id}/topics/{topic['guid']}", headers=contributor.headers
    ).json()
    assert after["modified_date"] > topic["modified_date"], "a floating viewpoint moves the topic (BCF 3.2.1)"

    listed = client.get(base, headers=viewer.headers).json()
    assert [v["guid"] for v in listed] == [guid]
    validate(listed[0], f"{SCHEMAS}/Viewpoint/viewpoint_GET.json")
    assert "authorization" not in listed[0]
    as_viewer = client.get(f"{base}/{guid}", params={"includeAuthorization": "true"}, headers=viewer.headers).json()
    assert as_viewer["authorization"] == {"viewpoint_actions": []}
    assert client.get(f"{base}/{guid}", headers=outsider.headers).status_code == 404

    snapshot = client.get(f"{base}/{guid}/snapshot", headers=viewer.headers)
    assert snapshot.status_code == 200 and snapshot.content == PNG
    assert snapshot.headers["content-type"] == "image/png"
    assert snapshot.headers["content-disposition"].startswith("attachment;")
    assert snapshot.headers["x-content-type-options"] == "nosniff"
    bitmap = client.get(f"{base}/{guid}/bitmaps/{viewpoint['bitmaps'][0]['guid']}", headers=viewer.headers)
    assert bitmap.status_code == 200 and bitmap.content == PNG and bitmap.headers["content-type"] == "image/png"
    assert client.get(f"{base}/{guid}/bitmaps/{guid}", headers=viewer.headers).status_code == 404

    selection = client.get(f"{base}/{guid}/selection", headers=viewer.headers).json()
    validate(selection, f"{SCHEMAS}/Viewpoint/selection_GET.json")
    assert selection == {"selection": full_viewpoint()["components"]["selection"]}
    coloring = client.get(f"{base}/{guid}/coloring", headers=viewer.headers).json()
    validate(coloring, f"{SCHEMAS}/Viewpoint/coloring_GET.json")
    assert [c["color"] for c in coloring["coloring"]] == ["FF0000FF", "00FF00"]
    assert coloring["coloring"][1]["components"] == [
        {"ifc_guid": "3k3LbXmTfDWODxdSuyCGYE"},
        {"authoring_tool_id": "wall-3"},
    ]
    visibility = client.get(f"{base}/{guid}/visibility", headers=viewer.headers).json()
    validate(visibility, f"{SCHEMAS}/Viewpoint/visibility_GET.json")
    assert visibility == {"visibility": full_viewpoint()["components"]["visibility"]}

    storage = client.app.state.storage  # type: ignore[attr-defined]
    assert storage.exists(f"snapshots/{guid}.png")

    # A comment that refers to the viewpoint blocks deletion (BCF 3.5.9) until it is updated.
    comments = f"/bcf/3.0/projects/{world.project_id}/topics/{topic['guid']}/comments"
    comment = client.post(comments, json={"comment": "See this", "viewpoint_guid": guid}, headers=contributor.headers)
    assert comment.status_code == 201, comment.text
    assert client.delete(f"{base}/{guid}", headers=contributor.headers).status_code == 409
    assert (
        client.put(
            f"{comments}/{comment.json()['guid']}", json={"comment": "See this"}, headers=contributor.headers
        ).status_code
        == 200
    )
    assert client.delete(f"{base}/{guid}", headers=viewer.headers).status_code == 403
    assert client.delete(f"{base}/{guid}", headers=contributor.headers).status_code == 200
    assert client.get(f"{base}/{guid}", headers=contributor.headers).status_code == 404
    assert client.get(f"{base}/{guid}/snapshot", headers=contributor.headers).status_code == 404
    assert not storage.exists(f"snapshots/{guid}.png"), "images are removed with the viewpoint"


def test_viewpoint_rules_and_image_checks(client: TestClient, world: World) -> None:
    editor = login_as(client, world, "editor")
    viewer = login_as(client, world, "viewer")
    topic = make_topic(client, world, editor)
    base = f"/bcf/3.0/projects/{world.project_id}/topics/{topic['guid']}/viewpoints"

    def post(body: dict[str, Any], session: Session = editor) -> Any:
        return client.post(base, json=body, headers=session.headers)

    assert post({"perspective_camera": PERSPECTIVE, "orthogonal_camera": ORTHOGONAL}).status_code == 400
    assert post({"index": 3}).status_code == 400, "camera or snapshot required"
    assert post({"lines": full_viewpoint()["lines"]}).status_code == 400, "visualisation needs a camera"
    zero = {**PERSPECTIVE, "camera_direction": {"x": 0, "y": 0, "z": 0}}
    assert post({"perspective_camera": zero}).status_code == 400
    assert post({"snapshot": {"snapshot_type": "png", "snapshot_data": b64(JPEG)}}).status_code == 400, "magic bytes"
    assert post({"snapshot": {"snapshot_type": "png", "snapshot_data": "not base64!"}}).status_code == 400
    assert post({"snapshot": {"snapshot_type": "gif", "snapshot_data": b64(PNG)}}).status_code == 400
    no_visibility = {"perspective_camera": PERSPECTIVE, "components": {"selection": [{"ifc_guid": "x"}]}}
    assert post(no_visibility).status_code == 400, "visibility is mandatory (BCF 3.5.2)"
    assert (
        post({"perspective_camera": PERSPECTIVE, "components": {"visibility": {}, "selection": [{}]}}).status_code
        == 400
    )
    assert post({"perspective_camera": PERSPECTIVE}, viewer).status_code == 403

    jpg = post({"snapshot": {"snapshot_type": "jpg", "snapshot_data": b64(JPEG)}})
    assert jpg.status_code == 201, jpg.text
    image = client.get(f"{base}/{jpg.json()['guid']}/snapshot", headers=viewer.headers)
    assert image.headers["content-type"] == "image/jpeg" and image.content == JPEG

    camera_only = post({"orthogonal_camera": ORTHOGONAL, "guid": "0D6F4E1A-0B2C-4F3D-8A9E-1C2B3D4E5F60"})
    assert camera_only.status_code == 201, camera_only.text
    body = camera_only.json()
    assert body["guid"] == "0d6f4e1a-0b2c-4f3d-8a9e-1c2b3d4e5f60" and "snapshot" not in body
    assert client.get(f"{base}/{body['guid']}/snapshot", headers=editor.headers).status_code == 404
    assert post({"orthogonal_camera": ORTHOGONAL, "guid": body["guid"]}).status_code == 409
    visibility = client.get(f"{base}/{body['guid']}/visibility", headers=editor.headers).json()
    validate(visibility, f"{SCHEMAS}/Viewpoint/visibility_GET.json")
    assert visibility["visibility"]["default_visibility"] is True, "no components means everything visible"
    assert client.get(f"{base}/{body['guid']}/coloring", headers=editor.headers).json() == {"coloring": []}


def test_comment_lifecycle_and_events(client: TestClient, world: World) -> None:
    editor = login_as(client, world, "editor")
    contributor = login_as(client, world, "contributor")
    viewer = login_as(client, world, "viewer")
    topic = make_topic(client, world, editor)
    topics = f"/bcf/3.0/projects/{world.project_id}/topics"
    base = f"{topics}/{topic['guid']}/comments"
    viewpoint = client.post(
        f"{topics}/{topic['guid']}/viewpoints", json={"perspective_camera": PERSPECTIVE}, headers=editor.headers
    ).json()

    assert client.post(base, json={"comment": "viewer talks"}, headers=viewer.headers).status_code == 403
    time.sleep(0.002)
    created = client.post(base, json={"comment": "Please check the door schedule."}, headers=contributor.headers)
    assert created.status_code == 201, created.text
    comment = created.json()
    validate(comment, f"{SCHEMAS}/Comment/comment_GET.json")
    assert comment["topic_guid"] == topic["guid"] and comment["author"] == "contributor"
    assert comment["authorization"] == {"comment_actions": ["update", "delete"]}
    guid = comment["guid"]
    topic_after = client.get(f"{topics}/{topic['guid']}", headers=editor.headers).json()
    assert topic_after["modified_date"] > topic["modified_date"], "a comment moves the topic (BCF 3.2.1)"

    listed = client.get(base, headers=viewer.headers).json()
    assert [c["guid"] for c in listed] == [guid] and "authorization" not in listed[0]
    validate(listed[0], f"{SCHEMAS}/Comment/comment_GET.json")
    assert client.get(base, params={"$filter": "author eq 'contributor'"}, headers=viewer.headers).json()
    assert client.get(base, params={"$filter": "author eq 'nobody'"}, headers=viewer.headers).json() == []
    assert client.get(base, params={"$orderby": "date desc"}, headers=viewer.headers).status_code == 200
    assert client.get(base, params={"$filter": "comment eq 'x'"}, headers=viewer.headers).status_code == 400
    with_auth = client.get(f"{base}/{guid}", params={"includeAuthorization": "true"}, headers=viewer.headers).json()
    assert with_auth["authorization"] == {"comment_actions": []}

    assert client.put(f"{base}/{guid}", json={"comment": "viewer edits"}, headers=viewer.headers).status_code == 403
    edited = client.put(
        f"{base}/{guid}", json={"comment": "Checked.", "viewpoint_guid": viewpoint["guid"]}, headers=editor.headers
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["viewpoint_guid"] == viewpoint["guid"] and edited.json()["modified_author"] == "editor"
    removed = client.put(f"{base}/{guid}", json={"comment": "Checked."}, headers=contributor.headers)
    assert removed.status_code == 200 and "viewpoint_guid" not in removed.json()

    events = client.get(f"{base}/{guid}/events", headers=viewer.headers).json()
    for event in events:
        validate(event, f"{SCHEMAS}/Events/comment_event_GET.json")
        assert event["comment_guid"] == guid and event["topic_guid"] == topic["guid"]
    types = [[action["type"] for action in event["actions"]] for event in events]
    assert types == [
        ["comment_created", "comment_text_updated"],
        ["comment_text_updated", "viewpoint_updated"],
        ["viewpoint_removed"],
    ]
    assert events[1]["actions"][1]["value"] == viewpoint["guid"]
    project_wide = f"/bcf/3.0/projects/{world.project_id}/topics/comments/events"
    assert (
        len(client.get(project_wide, params={"$filter": f"comment_guid eq '{guid}'"}, headers=viewer.headers).json())
        == 3
    )
    assert (
        len(client.get(project_wide, params={"$filter": "type eq 'viewpoint_removed'"}, headers=viewer.headers).json())
        == 1
    )
    assert client.get(f"{base}/{viewpoint['guid']}/events", headers=viewer.headers).status_code == 404

    assert client.delete(f"{base}/{guid}", headers=viewer.headers).status_code == 403
    assert client.delete(f"{base}/{guid}", headers=contributor.headers).status_code == 200, "authors delete their own"
    assert client.get(f"{base}/{guid}", headers=viewer.headers).status_code == 404
    other = client.post(base, json={"comment": "Another"}, headers=contributor.headers).json()
    assert client.delete(f"{base}/{other['guid']}", headers=editor.headers).status_code == 200, "editors delete any"
    assert len(client.get(project_wide, headers=viewer.headers).json()) == 4, "events outlive the comments"


def test_comment_needs_text_or_viewpoint(client: TestClient, world: World) -> None:
    editor = login_as(client, world, "editor")
    topic = make_topic(client, world, editor)
    other = make_topic(client, world, editor)
    topics = f"/bcf/3.0/projects/{world.project_id}/topics"
    base = f"{topics}/{topic['guid']}/comments"
    viewpoint = client.post(
        f"{topics}/{topic['guid']}/viewpoints", json={"perspective_camera": PERSPECTIVE}, headers=editor.headers
    ).json()
    foreign = client.post(
        f"{topics}/{other['guid']}/viewpoints", json={"perspective_camera": PERSPECTIVE}, headers=editor.headers
    ).json()

    assert client.post(base, json={}, headers=editor.headers).status_code == 400
    assert client.post(base, json={"comment": "   "}, headers=editor.headers).status_code == 400
    assert client.post(base, json={"viewpoint_guid": "not-a-uuid"}, headers=editor.headers).status_code == 400
    assert client.post(base, json={"viewpoint_guid": foreign["guid"]}, headers=editor.headers).status_code == 400
    only_viewpoint = client.post(base, json={"viewpoint_guid": viewpoint["guid"]}, headers=editor.headers)
    assert only_viewpoint.status_code == 201, only_viewpoint.text
    validate(only_viewpoint.json(), f"{SCHEMAS}/Comment/comment_GET.json")
    assert only_viewpoint.json()["comment"] == ""
    duplicate = client.post(
        base, json={"comment": "again", "guid": only_viewpoint.json()["guid"]}, headers=editor.headers
    )
    assert duplicate.status_code == 409
