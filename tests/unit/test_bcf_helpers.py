# This file was generated with the assistance of an AI coding tool.
"""Pure helpers of the BCF implementation: image checks, file names and schema rules."""

from __future__ import annotations

import base64

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from opencde.bcf import events
from opencde.bcf.binary import attachment_header, filename_from_content_disposition, sanitize_filename
from opencde.bcf.images import decode_image
from opencde.bcf.schemas import (
    CommentPOST,
    Component,
    Direction,
    DocumentReferencePOST,
    FileRef,
    ViewpointPOST,
)

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 20
CAMERA = {
    "camera_view_point": {"x": 0, "y": 0, "z": 0},
    "camera_direction": {"x": 1, "y": 0, "z": 0},
    "camera_up_vector": {"x": 0, "y": 0, "z": 1},
    "field_of_view": 60,
    "aspect_ratio": 1,
}


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def test_decode_image_accepts_matching_type_with_prefix_and_whitespace() -> None:
    assert decode_image(b64(PNG), "png", 1000) == PNG
    assert decode_image("data:image/png;base64," + b64(PNG), "png", 1000) == PNG
    wrapped = "\n".join(b64(JPEG)[i : i + 8] for i in range(0, len(b64(JPEG)), 8))
    assert decode_image(wrapped, "jpg", 1000) == JPEG


@pytest.mark.parametrize(
    ("encoded", "declared", "limit", "message"),
    [
        (b64(JPEG), "png", 1000, "not a png"),
        (b64(PNG), "jpg", 1000, "not a jpg"),
        ("@@not base64@@", "png", 1000, "not valid base64"),
        (b64(PNG), "png", 10, "exceeds 10 bytes"),
        (b64(PNG), "gif", 1000, "type must be one of"),
        (b64(b"<html>evil</html>"), "png", 1000, "not a png"),
    ],
)
def test_decode_image_rejects(encoded: str, declared: str, limit: int, message: str) -> None:
    with pytest.raises(HTTPException) as info:
        decode_image(encoded, declared, limit)
    assert info.value.status_code == 400 and message in info.value.detail


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ('attachment; filename="walls.ifc"', "walls.ifc"),
        ("attachment; filename*=UTF-8''V%C3%A4ggar.ifc", "Väggar.ifc"),
        ("attachment; filename=plain.txt", "plain.txt"),
        ('attachment; filename="../../etc/passwd"', "passwd"),
        ('attachment; filename="C:\\Users\\x\\model.ifc"', "model.ifc"),
        ('attachment; filename="bad\r\nname.ifc"', "badname.ifc"),
        ("attachment", None),
        (None, None),
        ('attachment; filename=""', None),
    ],
)
def test_filename_from_content_disposition(header: str | None, expected: str | None) -> None:
    assert filename_from_content_disposition(header) == expected


def test_sanitize_filename_limits_length_and_strips_dots() -> None:
    assert len(sanitize_filename("a" * 300 + ".ifc")) == 255
    assert sanitize_filename("...hidden...") == "hidden"


def test_attachment_header_has_ascii_fallback_and_utf8_form() -> None:
    header = attachment_header("Väggar plan.ifc")
    assert header.startswith("attachment; filename=\"V_ggar plan.ifc\"; filename*=UTF-8''V%C3%A4ggar%20plan.ifc")
    assert attachment_header("plain.pdf") == "attachment; filename=\"plain.pdf\"; filename*=UTF-8''plain.pdf"


def test_viewpoint_rules() -> None:
    ViewpointPOST(perspective_camera=CAMERA)
    ViewpointPOST(snapshot={"snapshot_type": "png", "snapshot_data": "x"})
    with pytest.raises(ValidationError, match="exactly one"):
        ViewpointPOST(perspective_camera=CAMERA, orthogonal_camera={**CAMERA, "view_to_world_scale": 1})
    with pytest.raises(ValidationError, match="camera, a snapshot or both"):
        ViewpointPOST(index=1)
    with pytest.raises(ValidationError, match="need a camera"):
        ViewpointPOST(
            snapshot={"snapshot_type": "png", "snapshot_data": "x"},
            lines=[{"start_point": {"x": 0, "y": 0, "z": 0}, "end_point": {"x": 1, "y": 0, "z": 0}}],
        )
    with pytest.raises(ValidationError, match="zero vector"):
        Direction(x=0, y=0, z=0)
    with pytest.raises(ValidationError):
        ViewpointPOST(perspective_camera={**CAMERA, "field_of_view": "NaN"})


def test_component_comment_and_reference_rules() -> None:
    Component(ifc_guid="x")
    Component(authoring_tool_id="y")
    with pytest.raises(ValidationError, match="ifc_guid or authoring_tool_id"):
        Component(originating_system="only")
    CommentPOST(viewpoint_guid="a")
    with pytest.raises(ValidationError, match="must not be blank"):
        CommentPOST(comment="   ")
    DocumentReferencePOST(url="https://example.test/doc.pdf")
    with pytest.raises(ValidationError, match="exactly one"):
        DocumentReferencePOST(url="https://example.test/doc.pdf", document_guid="abc")
    with pytest.raises(ValidationError, match="http"):
        DocumentReferencePOST(url="javascript:alert(1)")
    assert FileRef(date="2026-01-01T12:00:00+01:00").date == "2026-01-01T11:00:00.000Z"
    with pytest.raises(ValidationError):
        FileRef(date="not a date")


def test_topic_diff_covers_every_event_type() -> None:
    old = {
        "title": "a",
        "description": "d",
        "topic_status": "Open",
        "topic_type": "Issue",
        "priority": "High",
        "due_date": "x",
        "assigned_to": "u",
        "labels": ["A", "B"],
        "stage": "S1",
    }
    new = {"title": "b", "topic_status": "Closed", "topic_type": "Request", "labels": ["B", "C"], "stage": "S2"}
    types = [action.type for action in events.topic_diff(old, new)]
    assert types == [
        "title_updated",
        "description_removed",
        "status_updated",
        "type_updated",
        "priority_removed",
        "due_date_removed",
        "assigned_to_removed",
        "label_added",
        "label_removed",
        "stage_updated",
    ]
    assert [a.type for a in events.topic_diff({}, {"title": "t", "stage": "S"})] == ["title_updated", "stage_added"]
    assert [a.type for a in events.topic_diff({"stage": "S", "title": "t"}, {"title": "t"})] == ["stage_removed"]
    assert set(types) | {
        "topic_created",
        "description_updated",
        "priority_updated",
        "due_date_updated",
        "assigned_to_updated",
        "stage_added",
        "stage_removed",
    } == set(events.TOPIC_EVENT_TYPES)
