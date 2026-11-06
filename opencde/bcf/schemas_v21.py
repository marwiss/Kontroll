# This file was generated with the assistance of an AI coding tool.
"""What BCF API 2.1 sends differently from 3.0, mirroring ``spec/bcf-api-2.1/Schemas_draft-03``.

Everything else in its requests has the shape of :mod:`opencde.bcf.schemas`, so the classes here inherit from those
and the repositories take them as they are. The specification's version of the differences:

* the server makes every guid, and a client's ``guid`` is an unknown property to ignore (2.1 section 1.9);
* a file reference says ``file_name``, and a comment can answer another through ``reply_to_comment_guid``;
* a camera has no ``aspect_ratio``, and the rules of 3.0's section 3.5.2 about what a viewpoint must hold are not there;
* the example of a colour is ``#ff0000``, though the text says six or eight hexadecimal digits.
"""

from __future__ import annotations

from typing import Any

from pydantic import ConfigDict, Field, field_validator, model_validator
from pydantic.json_schema import SkipJsonSchema

from opencde.bcf.schemas import (
    GUID_MAX,
    BcfModel,
    Coloring,
    CommentPOST,
    CommentPUT,
    Components,
    DocumentReferencePOST,
    FileRef,
    Finite,
    OrthogonalCamera,
    PerspectiveCamera,
    TopicPOST,
    ViewpointPOST,
)

# 2.1 has no aspect ratio and 3.0 requires one, so a viewpoint made through 2.1 has to have something to show through
# 3.0. A square says the least about the view it came from.
DEFAULT_ASPECT_RATIO = 1.0


class _ServerMakesTheGuid(BcfModel):
    """No ``guid`` in the request's schema, and one that comes along anyway is left out."""

    guid: SkipJsonSchema[str | None] = None

    @model_validator(mode="before")
    @classmethod
    def _ignore_guid(cls, data: Any) -> Any:
        return {name: value for name, value in data.items() if name != "guid"} if isinstance(data, dict) else data


class TopicPOST21(_ServerMakesTheGuid, TopicPOST):
    """``Collaboration/Topic/topic_POST.json``"""


class DocumentReferencePOST21(_ServerMakesTheGuid, DocumentReferencePOST):
    """``Collaboration/DocumentReference/document_reference_POST.json``"""


class CommentPOST21(_ServerMakesTheGuid, CommentPOST):
    """``Collaboration/Comment/comment_POST.json``"""

    reply_to_comment_guid: str | None = Field(None, max_length=GUID_MAX)


class CommentPUT21(CommentPUT):
    """``Collaboration/Comment/comment_PUT.json``"""

    reply_to_comment_guid: str | None = Field(None, max_length=GUID_MAX)


class FileRef21(FileRef):
    """``Collaboration/File/file_PUT.json``"""

    filename: str | None = Field(None, max_length=255, alias="file_name")


class OrthogonalCamera21(OrthogonalCamera):
    """``Collaboration/Viewpoint/orthogonal_camera.json``"""

    aspect_ratio: Finite = Field(DEFAULT_ASPECT_RATIO, gt=0)


class PerspectiveCamera21(PerspectiveCamera):
    """``Collaboration/Viewpoint/perspective_camera.json``"""

    aspect_ratio: Finite = Field(DEFAULT_ASPECT_RATIO, gt=0)


class Coloring21(Coloring):
    """``Collaboration/Viewpoint/coloring.json``"""

    @field_validator("color", mode="before")
    @classmethod
    def _as_in_the_example(cls, value: Any) -> Any:
        return value.removeprefix("#") if isinstance(value, str) else value


class Components21(Components):
    """``Collaboration/Viewpoint/components.json``"""

    coloring: list[Coloring21] | None = Field(None, max_length=1_000)  # ty: ignore[invalid-attribute-override]


class ViewpointPOST21(_ServerMakesTheGuid, ViewpointPOST):
    """``Collaboration/Viewpoint/viewpoint_POST.json``"""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "perspective_camera": {
                        "camera_view_point": {"x": 8.0, "y": -6.0, "z": 4.0},
                        "camera_direction": {"x": -0.6, "y": 0.7, "z": -0.3},
                        "camera_up_vector": {"x": 0.0, "y": 0.0, "z": 1.0},
                        "field_of_view": 60.0,
                    },
                    "components": {
                        "selection": [{"ifc_guid": "1Xezbq735AdBO_4DerG66G"}],
                        "visibility": {"default_visibility": True},
                    },
                }
            ]
        }
    )

    # Narrower than the parent's, which a type checker rightly questions of something writable. Nothing writes to a
    # request's body, and the API document has to say that these need no aspect ratio.
    orthogonal_camera: OrthogonalCamera21 | None = None  # ty: ignore[invalid-mutable-override]
    perspective_camera: PerspectiveCamera21 | None = None  # ty: ignore[invalid-mutable-override]
    components: Components21 | None = None  # ty: ignore[invalid-mutable-override]

    @model_validator(mode="after")
    def _rules(self) -> ViewpointPOST21:
        # Everything is optional in 2.1. A viewpoint holds one camera, though, and two would have to lose one.
        if self.orthogonal_camera is not None and self.perspective_camera is not None:
            raise ValueError("at most one of orthogonal_camera and perspective_camera")
        return self
