# This file was generated with the assistance of an AI coding tool.
"""What every API body holds to: types as the schemas say them, and the length of what was sent."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from opencde.bcf.schemas import TEXT_MAX, CommentPOST, TopicPOST, ViewpointPOST
from opencde.documents.schemas import CallbackLink


def test_whitespace_counts_towards_the_length_that_is_sent() -> None:
    assert CommentPOST.model_validate({"comment": "  A remark  "}).comment == "A remark"
    assert CommentPOST.model_validate({"comment": "A" + " " * (TEXT_MAX - 1)}).comment == "A"
    with pytest.raises(ValidationError, match="at most"):
        CommentPOST.model_validate({"comment": "A" + " " * TEXT_MAX})


@pytest.mark.parametrize("hints", [{"openings_visible": "yes"}, {"openings_visible": 1}])
def test_a_boolean_is_a_boolean(hints: dict[str, object]) -> None:
    components = {"visibility": {"default_visibility": True, "view_setup_hints": hints}}
    with pytest.raises(ValidationError):
        ViewpointPOST.model_validate({"components": components})


def test_an_integer_is_an_integer_and_a_number_may_be_written_without_decimals() -> None:
    with pytest.raises(ValidationError):
        CallbackLink.model_validate({"url": "http://127.0.0.1/cb", "expires_in": "60"})
    point = {"x": 1, "y": 2.5, "z": 3}
    camera = {
        "camera_view_point": point,
        "camera_direction": point,
        "camera_up_vector": point,
        "field_of_view": 60,
        "aspect_ratio": 1.5,
    }
    assert ViewpointPOST.model_validate({"perspective_camera": camera}).perspective_camera is not None


def test_unknown_fields_are_still_ignored() -> None:
    assert TopicPOST.model_validate({"title": "A title", "no_such_field": 1}).title == "A title"
