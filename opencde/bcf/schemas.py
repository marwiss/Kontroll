# This file was generated with the assistance of an AI coding tool.
"""Request and response bodies of the BCF API, mirroring ``spec/bcf-api/Schemas``.

Field names and optionality follow the JSON schemas one to one; the comments
give the schema file. Lengths are bounded so a client cannot store megabytes
in a title. Unknown fields are ignored on input (Foundation API 1.8) and
``None`` fields are left out of responses, except where the schema requires
them.
"""

from __future__ import annotations

import re
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from opencde.timeutil import canonical_iso

TITLE_MAX = 512
TEXT_MAX = 10_000
VALUE_MAX = 200
LIST_MAX = 100
URL_MAX = 2000
GUID_MAX = 64
IFC_GUID_MAX = 64
MAX_COMPONENTS = 50_000
MAX_LINES = 10_000
MAX_CLIPPING_PLANES = 1_000
MAX_BITMAPS = 50
MAX_FILES = 200
MAX_RELATED = 500

Finite = Annotated[float, Field(allow_inf_nan=False)]
ImageType = Literal["png", "jpg"]
_COLOR = re.compile(r"^[0-9A-Fa-f]{6}(?:[0-9A-Fa-f]{2})?$")
_HTTP_URL = re.compile(r"^https?://[^\s]+$", re.IGNORECASE)


class BcfModel(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


def _optional_datetime(value: str | None) -> str | None:
    if value is None or value == "":
        return None
    try:
        return canonical_iso(value)
    except ValueError as exc:
        raise ValueError("must be an ISO 8601 date-time") from exc


# ---------------------------------------------------------------------------- projects (3.1)


class ProjectAuthorization(BcfModel):
    project_actions: list[str] | None = None


class ProjectGET(BcfModel):
    """``Project/project_GET.json``"""

    project_id: str
    name: str
    authorization: ProjectAuthorization | None = None


class ProjectPUT(BcfModel):
    """``Project/project_PUT.json``"""

    name: str = Field(min_length=1, max_length=VALUE_MAX)


class ExtensionsGET(BcfModel):
    """``Project/extensions_GET.json`` plus ``custom_information`` (additional property)."""

    topic_type: list[str]
    topic_status: list[str]
    topic_label: list[str]
    snippet_type: list[str]
    priority: list[str]
    users: list[str]
    stage: list[str]
    custom_information: list[str] = []
    project_actions: list[str] = []
    topic_actions: list[str] = []
    comment_actions: list[str] = []


# ---------------------------------------------------------------------------- topics (3.2)


class BimSnippet(BcfModel):
    """``Topic/bim_snippet.json``"""

    snippet_type: str = Field(min_length=1, max_length=VALUE_MAX)
    is_external: bool
    reference: str = Field(min_length=1, max_length=URL_MAX)
    reference_schema: str = Field(min_length=1, max_length=URL_MAX)


class TopicFields(BcfModel):
    """Fields shared by ``topic_POST.json`` and ``topic_PUT.json``."""

    topic_type: str | None = Field(None, max_length=VALUE_MAX)
    topic_status: str | None = Field(None, max_length=VALUE_MAX)
    reference_links: list[str] | None = Field(None, max_length=LIST_MAX)
    title: str = Field(min_length=1, max_length=TITLE_MAX)
    priority: str | None = Field(None, max_length=VALUE_MAX)
    index: int | None = Field(None, ge=0, le=1_000_000_000)
    labels: list[str] | None = Field(None, max_length=LIST_MAX)
    assigned_to: str | None = Field(None, max_length=VALUE_MAX)
    stage: str | None = Field(None, max_length=VALUE_MAX)
    description: str | None = Field(None, max_length=TEXT_MAX)
    bim_snippet: BimSnippet | None = None
    due_date: str | None = Field(None, max_length=64)

    @field_validator("due_date")
    @classmethod
    def _due_date(cls, value: str | None) -> str | None:
        return _optional_datetime(value)

    @field_validator("reference_links", "labels")
    @classmethod
    def _string_items(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        cleaned = []
        for item in value:
            if not isinstance(item, str) or not item.strip() or len(item) > URL_MAX:
                raise ValueError("items must be non-empty strings")
            if item not in cleaned:
                cleaned.append(item.strip())
        return cleaned


class TopicPOST(TopicFields):
    """``Topic/topic_POST.json``"""

    guid: str | None = Field(None, max_length=64)


class TopicPUT(TopicFields):
    """``Topic/topic_PUT.json``"""


class TopicAuthorization(BcfModel):
    topic_actions: list[str] | None = None
    topic_status: list[str] | None = None


class TopicGET(BcfModel):
    """``Topic/topic_GET.json``"""

    guid: str
    server_assigned_id: str
    topic_type: str | None = None
    topic_status: str | None = None
    reference_links: list[str] | None = None
    title: str
    priority: str | None = None
    index: int | None = None
    labels: list[str] | None = None
    creation_date: str
    creation_author: str
    modified_date: str | None = None
    modified_author: str | None = None
    assigned_to: str | None = None
    stage: str | None = None
    description: str | None = None
    bim_snippet: BimSnippet | None = None
    due_date: str | None = None
    authorization: TopicAuthorization | None = None


# ---------------------------------------------------------------------------- events (3.9, 3.10)


class EventAction(BcfModel):
    """``Events/event_action.json``"""

    type: str
    value: str | None = None


class TopicEventGET(BcfModel):
    """``Events/topic_event_GET.json``"""

    topic_guid: str
    date: str
    author: str
    actions: list[EventAction]


class CommentEventGET(BcfModel):
    """``Events/comment_event_GET.json``"""

    comment_guid: str
    topic_guid: str
    date: str
    author: str
    actions: list[EventAction]


# ---------------------------------------------------------------------------- comments (3.4)


class CommentFields(BcfModel):
    comment: str | None = Field(None, max_length=TEXT_MAX)
    viewpoint_guid: str | None = Field(None, max_length=GUID_MAX)

    @model_validator(mode="after")
    def _text_or_viewpoint(self) -> CommentFields:
        # BCF 3.4.2: ``comment`` is required unless ``viewpoint_guid`` is provided, and must not be blank.
        if not (self.comment and self.comment.strip()) and not self.viewpoint_guid:
            raise ValueError("comment must not be blank unless viewpoint_guid is provided")
        return self


class CommentPOST(CommentFields):
    """``Comment/comment_POST.json``"""

    guid: str | None = Field(None, max_length=GUID_MAX)


class CommentPUT(CommentFields):
    """``Comment/comment_PUT.json``"""


class CommentAuthorization(BcfModel):
    comment_actions: list[str] | None = None


class CommentGET(BcfModel):
    """``Comment/comment_GET.json``"""

    guid: str
    date: str
    author: str
    comment: str
    topic_guid: str
    viewpoint_guid: str | None = None
    modified_date: str | None = None
    modified_author: str | None = None
    authorization: CommentAuthorization | None = None


# ---------------------------------------------------------------------------- viewpoints (3.5)


class Point(BcfModel):
    """``Viewpoint/point.json`` and ``location.json``"""

    x: Finite
    y: Finite
    z: Finite


class Direction(Point):
    """``Viewpoint/direction.json``: must not be a zero vector."""

    @model_validator(mode="after")
    def _not_zero(self) -> Direction:
        if self.x == 0 and self.y == 0 and self.z == 0:
            raise ValueError("direction must not be a zero vector")
        return self


class OrthogonalCamera(BcfModel):
    """``Viewpoint/orthogonal_camera.json``"""

    camera_view_point: Point
    camera_direction: Direction
    camera_up_vector: Direction
    view_to_world_scale: Finite
    aspect_ratio: Finite = Field(gt=0)


class PerspectiveCamera(BcfModel):
    """``Viewpoint/perspective_camera.json``"""

    camera_view_point: Point
    camera_direction: Direction
    camera_up_vector: Direction
    field_of_view: Finite = Field(gt=0, le=180)
    aspect_ratio: Finite = Field(gt=0)


class Line(BcfModel):
    """``Viewpoint/line.json``"""

    start_point: Point
    end_point: Point


class ClippingPlane(BcfModel):
    """``Viewpoint/clipping_plane.json``"""

    location: Point
    direction: Direction


class SnapshotPOST(BcfModel):
    """``Viewpoint/snapshot_POST.json``"""

    snapshot_type: ImageType
    snapshot_data: str = Field(min_length=1)


class SnapshotGET(BcfModel):
    """``Viewpoint/snapshot_GET.json``"""

    snapshot_type: str


class BitmapFields(BcfModel):
    bitmap_type: ImageType
    location: Point
    normal: Direction
    up: Direction
    height: Finite = Field(gt=0)


class BitmapPOST(BitmapFields):
    """``Viewpoint/bitmap_POST.json``"""

    bitmap_data: str = Field(min_length=1)


class BitmapGET(BitmapFields):
    """``Viewpoint/bitmap_GET.json``"""

    guid: str


class Component(BcfModel):
    """``Viewpoint/component.json``: ``ifc_guid`` if possible, ``authoring_tool_id`` as the fallback."""

    ifc_guid: str | None = Field(None, max_length=IFC_GUID_MAX)
    originating_system: str | None = Field(None, max_length=VALUE_MAX)
    authoring_tool_id: str | None = Field(None, max_length=VALUE_MAX)

    @model_validator(mode="after")
    def _identifiable(self) -> Component:
        if not self.ifc_guid and not self.authoring_tool_id:
            raise ValueError("a component needs ifc_guid or authoring_tool_id")
        return self


class Coloring(BcfModel):
    """``Viewpoint/coloring.json``: ARGB or RGB as 8 or 6 hex digits."""

    color: str = Field(pattern=_COLOR.pattern)
    components: list[Component] = Field(max_length=MAX_COMPONENTS)


class ViewSetupHints(BcfModel):
    """``Viewpoint/view_setup_hints.json``"""

    spaces_visible: bool = False
    space_boundaries_visible: bool = False
    openings_visible: bool = False


class Visibility(BcfModel):
    """``Viewpoint/visibility.json``"""

    default_visibility: bool = False
    exceptions: list[Component] | None = Field(None, max_length=MAX_COMPONENTS)
    view_setup_hints: ViewSetupHints | None = None


class Components(BcfModel):
    """``Viewpoint/components.json``: ``visibility`` is mandatory (BCF 3.5.2)."""

    selection: list[Component] | None = Field(None, max_length=MAX_COMPONENTS)
    coloring: list[Coloring] | None = Field(None, max_length=1_000)
    visibility: Visibility


class ViewpointPOST(BcfModel):
    """``Viewpoint/viewpoint_POST.json`` with the rules of BCF 3.5.2."""

    guid: str | None = Field(None, max_length=GUID_MAX)
    index: int | None = Field(None, ge=0, le=1_000_000_000)
    orthogonal_camera: OrthogonalCamera | None = None
    perspective_camera: PerspectiveCamera | None = None
    lines: list[Line] | None = Field(None, max_length=MAX_LINES)
    clipping_planes: list[ClippingPlane] | None = Field(None, max_length=MAX_CLIPPING_PLANES)
    bitmaps: list[BitmapPOST] | None = Field(None, max_length=MAX_BITMAPS)
    snapshot: SnapshotPOST | None = None
    components: Components | None = None

    @model_validator(mode="after")
    def _rules(self) -> ViewpointPOST:
        has_camera = self.orthogonal_camera is not None or self.perspective_camera is not None
        if self.orthogonal_camera is not None and self.perspective_camera is not None:
            raise ValueError("exactly one of orthogonal_camera and perspective_camera")
        if not has_camera and self.snapshot is None:
            raise ValueError("a viewpoint needs a camera, a snapshot or both")
        visualisation = any(value for value in (self.lines, self.clipping_planes, self.bitmaps)) or self.components
        if visualisation and not has_camera:
            raise ValueError("lines, clipping planes, bitmaps and components need a camera")
        return self


class ViewpointAuthorization(BcfModel):
    viewpoint_actions: list[str] | None = None


class ViewpointGET(BcfModel):
    """``Viewpoint/viewpoint_GET.json``: no image data, no components (they have their own services)."""

    guid: str
    index: int | None = None
    orthogonal_camera: OrthogonalCamera | None = None
    perspective_camera: PerspectiveCamera | None = None
    lines: list[Line] | None = None
    clipping_planes: list[ClippingPlane] | None = None
    bitmaps: list[BitmapGET] | None = None
    snapshot: SnapshotGET | None = None
    authorization: ViewpointAuthorization | None = None


class SelectionGET(BcfModel):
    """``Viewpoint/selection_GET.json``"""

    selection: list[Component]


class ColoringGET(BcfModel):
    """``Viewpoint/coloring_GET.json``"""

    coloring: list[Coloring]


class VisibilityGET(BcfModel):
    """``Viewpoint/visibility_GET.json``"""

    visibility: Visibility


# ---------------------------------------------------------------------------- related topics (3.6)


class RelatedTopic(BcfModel):
    """``RelatedTopic/related_topic_GET.json`` and ``_PUT.json``"""

    related_topic_guid: str = Field(min_length=1, max_length=GUID_MAX)


# ---------------------------------------------------------------------------- document references (3.7)


class DocumentReferenceFields(BcfModel):
    document_guid: str | None = Field(None, max_length=GUID_MAX)
    url: str | None = Field(None, max_length=URL_MAX)
    description: str | None = Field(None, max_length=TEXT_MAX)

    @model_validator(mode="after")
    def _internal_or_external(self) -> DocumentReferenceFields:
        # BCF 3.7: ``url`` and ``document_guid`` are mutually exclusive, and one of them is needed.
        if bool(self.document_guid) == bool(self.url):
            raise ValueError("exactly one of document_guid and url must be set")
        if self.url and not _HTTP_URL.match(self.url):
            raise ValueError("url must be an http(s) URL")
        return self


class DocumentReferencePOST(DocumentReferenceFields):
    """``DocumentReference/document_reference_POST.json``"""

    guid: str | None = Field(None, max_length=GUID_MAX)


class DocumentReferencePUT(DocumentReferenceFields):
    """``DocumentReference/document_reference_PUT.json``"""


class DocumentReferenceGET(BcfModel):
    """``DocumentReference/document_reference_GET.json``"""

    guid: str
    document_guid: str | None = None
    url: str | None = None
    description: str | None = None


# ---------------------------------------------------------------------------- files (3.3)


class FileRef(BcfModel):
    """``File/file_GET.json`` and ``file_PUT.json``: a model referenced in a topic header."""

    ifc_project: str | None = Field(None, max_length=IFC_GUID_MAX)
    ifc_spatial_structure_element: str | None = Field(None, max_length=IFC_GUID_MAX)
    filename: str | None = Field(None, max_length=255)
    date: str | None = Field(None, max_length=64)
    reference: str | None = Field(None, max_length=URL_MAX)

    @field_validator("date")
    @classmethod
    def _date(cls, value: str | None) -> str | None:
        return _optional_datetime(value)


class ProjectFileDisplayInformation(BcfModel):
    """``File/project_file_display_information.json``"""

    field_display_name: str
    field_value: str


class ProjectFileInformation(BcfModel):
    """``File/project_file_information.json``"""

    display_information: list[ProjectFileDisplayInformation]
    file: FileRef


# ---------------------------------------------------------------------------- documents (3.8)


class DocumentGET(BcfModel):
    """``Document/document_GET.json``"""

    guid: str
    filename: str


def dump(model: BaseModel) -> dict[str, Any]:
    """Response body without ``None`` fields (lists stay, even when empty)."""
    return model.model_dump(exclude_none=True)
