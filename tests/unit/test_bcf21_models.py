# This file was generated with the assistance of an AI coding tool.
"""What BCF API 2.1 says differently from 3.0 in its requests, and what the API document says of it."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from opencde.bcf.schemas_v21 import (
    DEFAULT_ASPECT_RATIO,
    CommentPOST21,
    CommentPUT21,
    DocumentReferencePOST21,
    FileRef21,
    TopicPOST21,
    ViewpointPOST21,
)

CAMERA = {
    "camera_view_point": {"x": 0.0, "y": 0.0, "z": 0.0},
    "camera_direction": {"x": 0.0, "y": 1.0, "z": 0.0},
    "camera_up_vector": {"x": 0.0, "y": 0.0, "z": 1.0},
}


@pytest.mark.parametrize(
    ("model", "body"),
    [
        (TopicPOST21, {"title": "A topic"}),
        (CommentPOST21, {"comment": "A comment"}),
        (DocumentReferencePOST21, {"url": "https://example.com/a.pdf"}),
        (ViewpointPOST21, {"perspective_camera": {**CAMERA, "field_of_view": 60.0}}),
    ],
)
def test_a_guid_is_an_unknown_property_and_is_not_in_the_document(model: type, body: dict) -> None:
    assert model.model_validate({**body, "guid": "00000000-0000-4000-8000-000000000000"}).guid is None
    assert model.model_validate({**body, "guid": 5}).guid is None, "whatever it is, it is ignored"
    assert "guid" not in model.model_json_schema()["properties"]


def test_a_camera_needs_no_aspect_ratio_but_may_bring_one() -> None:
    perspective = {**CAMERA, "field_of_view": 60.0}
    assert (
        ViewpointPOST21.model_validate({"perspective_camera": perspective}).perspective_camera.aspect_ratio
        == DEFAULT_ASPECT_RATIO
    )
    orthogonal = {**CAMERA, "view_to_world_scale": 2.0, "aspect_ratio": 1.5}
    assert ViewpointPOST21.model_validate({"orthogonal_camera": orthogonal}).orthogonal_camera.aspect_ratio == 1.5
    assert "aspect_ratio" not in ViewpointPOST21.model_json_schema()["$defs"]["PerspectiveCamera21"].get("required", [])


def test_a_viewpoint_may_hold_little_but_not_two_cameras() -> None:
    ViewpointPOST21.model_validate({})
    ViewpointPOST21.model_validate({"components": {"visibility": {"default_visibility": True}}})
    with pytest.raises(ValidationError, match="at most one"):
        ViewpointPOST21.model_validate(
            {
                "perspective_camera": {**CAMERA, "field_of_view": 60.0},
                "orthogonal_camera": {**CAMERA, "view_to_world_scale": 2.0},
            }
        )


@pytest.mark.parametrize(("sent", "kept"), [("#ff0000", "ff0000"), ("ff0000", "ff0000"), ("#ff0000ff", "ff0000ff")])
def test_a_colour_may_be_written_as_the_example_of_the_specification(sent: str, kept: str) -> None:
    body = {"coloring": [{"color": sent, "components": []}], "visibility": {"default_visibility": True}}
    viewpoint = ViewpointPOST21.model_validate({"components": body})
    assert viewpoint.components.coloring[0].color == kept


@pytest.mark.parametrize("sent", ["red", "#ff00", "##ff0000", "#gg0000"])
def test_a_colour_is_still_a_colour(sent: str) -> None:
    body = {"coloring": [{"color": sent, "components": []}], "visibility": {"default_visibility": True}}
    with pytest.raises(ValidationError):
        ViewpointPOST21.model_validate({"components": body})


def test_a_file_is_called_file_name_and_kept_as_filename() -> None:
    file = FileRef21.model_validate({"file_name": "A.ifc", "filename": "ignored.ifc", "date": "2026-11-06T12:00:00Z"})
    assert file.filename == "A.ifc" and file.model_dump()["filename"] == "A.ifc"
    assert "file_name" in FileRef21.model_json_schema()["properties"]
    assert "filename" not in FileRef21.model_json_schema()["properties"]
    with pytest.raises(ValidationError):
        FileRef21.model_validate({"file_name": "x" * 256})


def test_a_comment_can_name_what_it_answers() -> None:
    answer = "00000000-0000-4000-8000-000000000000"
    assert (
        CommentPOST21.model_validate({"comment": "Yes", "reply_to_comment_guid": answer}).reply_to_comment_guid
        == answer
    )
    assert CommentPUT21.model_validate({"comment": "Yes"}).reply_to_comment_guid is None
    with pytest.raises(ValidationError):
        CommentPOST21.model_validate({"comment": "Yes", "reply_to_comment_guid": "x" * 65})
