# This file was generated with the assistance of an AI coding tool.
"""The clash check between two IFC document versions: an extension of the Documents API (ADR 0019).

``POST /documents/1.0/projects/{project_id}/ifc-clash`` asks the server to compare the elements of two document
versions of the project, with IfcClash in a worker process; ``GET …/ifc-clash`` lists the checks and
``GET …/ifc-clash/{id}`` gives one with its clashes, in the form Dataspatium's own clash core writes, so that a client
shows the server's result as it shows its own. ``POST …/ifc-clash/{id}/topics`` turns chosen clashes into BCF topics
with a viewpoint each, on request only: the server never makes topics by itself. The same bearer token as the
Documents API reads and starts checks; making topics needs the ``bcf`` scope and the ``createTopic`` action.
"""

from __future__ import annotations

import math
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Path, Request, Response
from pydantic import BaseModel, Field

from opencde.auth.dependencies import DocumentsPrincipal
from opencde.bcf.access import ProjectCtx
from opencde.bcf.schemas import (
    Coloring,
    Component,
    Components,
    Direction,
    PerspectiveCamera,
    Point,
    TopicPOST,
    ViewpointPOST,
    Visibility,
)
from opencde.bcf.topic_access import TopicsDep
from opencde.deps import ProjectsDep, SettingsDep, UsersDep
from opencde.ids import is_uuid, normalize_guid
from opencde.ifcgraph.service import IfcGraphDep, IfcGraphService
from opencde.store.bcf.topics import validate_against_extensions
from opencde.store.bcf.viewpoints import ViewpointsDep

TAG = "IFC clash check (extension)"

router = APIRouter(prefix="/documents/1.0", tags=[TAG])

ProjectId = Annotated[str, Path(alias="project_id", max_length=64)]
ClashId = Annotated[str, Path(alias="clash_id", max_length=64)]

MAX_TOPICS_AT_ONCE = 100
# The colours the viewpoint gives the two sides, as Dataspatium colours them.
COLOUR_A = "FFE53935"
COLOUR_B = "FF1E88E5"


class IfcClashSide(BaseModel):
    document_id: str = Field(max_length=64)
    version_index: int = Field(ge=1, le=1_000_000_000)
    types: list[str] | None = Field(
        None,
        max_length=50,
        description="IFC classes to include, such as IfcWall; every element with a body by default.",
    )


class IfcClashRequest(BaseModel):
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "a": {
                        "document_id": "f4c8c3c2-1b8e-4a5f-9a0b-2d2a0f1a9c11",
                        "version_index": 1,
                        "types": ["IfcWall"],
                    },
                    "b": {"document_id": "0b1c4a7e-77d5-4b8b-8f2f-5b3f6a2b9d22", "version_index": 2},
                    "mode": "intersection",
                    "tolerance": 0.001,
                }
            ]
        }
    }

    a: IfcClashSide
    b: IfcClashSide
    mode: Literal["intersection", "clearance"] = Field(
        "intersection",
        description="`intersection`: elements that go into each other deeper than `tolerance`; `clearance`: elements "
        "closer to each other than `clearance`.",
    )
    tolerance: float = Field(0.001, ge=0, le=1, description="Metres; a shallower intersection does not count.")
    clearance: float = Field(0.05, gt=0, le=10, description="Metres; the least distance the clearance mode accepts.")


class IfcClashElement(BaseModel):
    document_id: str
    version_index: int
    id: int = Field(description="The element's STEP id in its file.")
    guid: str = Field(description="The element's GlobalId.")
    type: str = Field(description="The element's IFC class.")
    name: str | None = None
    storey: str | None = Field(None, description="The name of the storey that contains the element, where known.")


class IfcClashPair(BaseModel):
    a: IfcClashElement
    b: IfcClashElement
    kind: Literal["intersection", "clearance"]
    depth: float | None = Field(None, description="Metres: how far the elements go into each other (intersection).")
    distance: float = Field(description="Metres: the least distance between the elements (clearance), else 0.")
    point: list[float] = Field(description="Where it was measured, in the model's own coordinates with Z up.")
    extent: float | None = Field(None, description="The size of the elements, for a camera's distance; absent here.")


class IfcClashReport(BaseModel):
    id: str
    state: str = Field(description="`queued`, `running`, `done` or `failed`.")
    request: IfcClashRequest
    author: str
    created_at: str
    done_at: str | None = None
    error: str | None = None
    count: int | None = Field(None, description="The clashes found, once `done`.")
    set_a: int | None = Field(None, description="The elements of side A the check covered.")
    set_b: int | None = None
    missing: int | None = Field(None, description="Elements without geometry, left out.")
    seconds: float | None = None
    truncated: bool | None = Field(None, description="True when there were more clashes than a report keeps.")
    clashes: list[IfcClashPair] | None = Field(None, description="Given by `GET …/ifc-clash/{id}` only.")
    url: str


class IfcClashTopicsRequest(BaseModel):
    clashes: list[int] = Field(
        min_length=1, max_length=MAX_TOPICS_AT_ONCE, description="Positions in the report's `clashes`, from 0."
    )


class IfcClashTopic(BaseModel):
    clash: int
    topic_guid: str
    viewpoint_guid: str
    title: str


def _url(request: Request, project_id: str, clash_id: str) -> str:
    return f"{str(request.base_url).rstrip('/')}/documents/1.0/projects/{project_id}/ifc-clash/{clash_id}"


def _report(request: Request, row: dict[str, Any]) -> IfcClashReport:
    return IfcClashReport(
        id=row["id"],
        state=row["state"],
        request=IfcClashRequest.model_validate(row["request"]),
        author=row["author"],
        created_at=row["created_at"],
        done_at=row.get("done_at"),
        error=row.get("error"),
        count=row.get("count"),
        set_a=row.get("set_a"),
        set_b=row.get("set_b"),
        missing=row.get("missing"),
        seconds=row.get("seconds"),
        truncated=row.get("truncated"),
        clashes=[IfcClashPair.model_validate(c) for c in row["clashes"]] if row.get("clashes") is not None else None,
        url=_url(request, row["project_id"], row["id"]),
    )


async def _service(
    ifcgraph: IfcGraphService | None, settings: Any, users: Any, user_id: str, project_id: str
) -> tuple[IfcGraphService, str]:
    """The service and the project id, for a member of the project on a server with the check turned on."""
    if ifcgraph is None or not settings.ifcgraph_enabled or not settings.ifcgraph_clash_enabled:
        raise HTTPException(404, "The clash check is off on this server")
    if not is_uuid(project_id):
        raise HTTPException(404, "Project not found")
    pid = normalize_guid(project_id)
    if await users.project_role(user_id, pid) is None:
        raise HTTPException(404, "Project not found")
    return ifcgraph, pid


@router.post(
    "/projects/{project_id}/ifc-clash",
    summary="Start a clash check between two IFC document versions of a project",
    response_model=IfcClashReport,
    response_model_exclude_none=True,
    status_code=202,
)
async def start_clash(
    request: Request,
    response: Response,
    principal: DocumentsPrincipal,
    project_id: ProjectId,
    body: IfcClashRequest,
    ifcgraph: IfcGraphDep,
    settings: SettingsDep,
    users: UsersDep,
) -> IfcClashReport:
    """The check runs in the background; `GET` the answer's `url` until its state is `done` or `failed`.

    Both versions must be IFC files of this project. 404 when the project is not yours or the check is off.
    """
    service, pid = await _service(ifcgraph, settings, users, principal.user_id, project_id)
    spec = body.model_dump()
    for side in ("a", "b"):
        if not is_uuid(spec[side]["document_id"]):
            raise HTTPException(404, "Document version not found")
        spec[side]["document_id"] = normalize_guid(spec[side]["document_id"])
    clash_id = await service.schedule_clash(project_id=pid, author=principal.username, request=spec)
    row = await service.clash_report(user_id=principal.user_id, project_id=pid, clash_id=clash_id, with_clashes=False)
    if row is None:  # the project vanished under us
        raise HTTPException(404, "Project not found")
    response.headers["Location"] = _url(request, pid, clash_id)
    return _report(request, row)


@router.get(
    "/projects/{project_id}/ifc-clash",
    summary="List the clash checks of a project",
    response_model=list[IfcClashReport],
    response_model_exclude_none=True,
)
async def list_clashes(
    request: Request,
    principal: DocumentsPrincipal,
    project_id: ProjectId,
    ifcgraph: IfcGraphDep,
    settings: SettingsDep,
    users: UsersDep,
) -> list[IfcClashReport]:
    """The newest 100 checks, without their clashes."""
    service, pid = await _service(ifcgraph, settings, users, principal.user_id, project_id)
    rows = await service.clash_reports(user_id=principal.user_id, project_id=pid)
    return [_report(request, row) for row in rows]


@router.get(
    "/projects/{project_id}/ifc-clash/{clash_id}",
    summary="Get a clash check with its clashes",
    response_model=IfcClashReport,
    response_model_exclude_none=True,
)
async def get_clash(
    request: Request,
    principal: DocumentsPrincipal,
    project_id: ProjectId,
    clash_id: ClashId,
    ifcgraph: IfcGraphDep,
    settings: SettingsDep,
    users: UsersDep,
) -> IfcClashReport:
    """Each clash names both elements (STEP id, GlobalId, class, name, storey), its kind, depth or distance and point."""
    service, pid = await _service(ifcgraph, settings, users, principal.user_id, project_id)
    if not is_uuid(clash_id):
        raise HTTPException(404, "Clash check not found")
    row = await service.clash_report(
        user_id=principal.user_id, project_id=pid, clash_id=normalize_guid(clash_id), with_clashes=True
    )
    if row is None:
        raise HTTPException(404, "Clash check not found")
    return _report(request, row)


def camera_looking_at(point: list[float], extent: float | None) -> PerspectiveCamera:
    """A camera that looks down at the point from the south-east, at a distance set by the elements' size."""
    distance = min(40.0, max(2.5, (extent or 2.0) * 1.5 + 2.0))
    step = distance / math.sqrt(3)
    return PerspectiveCamera(
        camera_view_point=Point(x=point[0] + step, y=point[1] - step, z=point[2] + step),
        camera_direction=Direction(x=-1 / math.sqrt(3), y=1 / math.sqrt(3), z=-1 / math.sqrt(3)),
        camera_up_vector=Direction(x=0.0, y=0.0, z=1.0),
        field_of_view=60.0,
        aspect_ratio=1.6,
    )


def _topic_body(pair: dict[str, Any], extensions: dict[str, list[str]]) -> TopicPOST:
    """A topic for one clash: type, status and label only where the project's extensions allow them."""
    a, b = pair["a"], pair["b"]
    what = (
        f"{pair['kind']}, depth {pair['depth'] * 1000:.0f} mm"
        if pair["kind"] == "intersection" and pair.get("depth") is not None
        else f"{pair['kind']}, distance {pair['distance'] * 1000:.0f} mm"
    )
    description = (
        f"Clash check: {what} at ({pair['point'][0]:.3f}, {pair['point'][1]:.3f}, {pair['point'][2]:.3f}).\n"
        f"A: {a['type']} {a.get('name') or ''} ({a['guid']}), {a.get('storey') or 'no storey'}, "
        f"version {a['version_index']} of document {a['document_id']}.\n"
        f"B: {b['type']} {b.get('name') or ''} ({b['guid']}), {b.get('storey') or 'no storey'}, "
        f"version {b['version_index']} of document {b['document_id']}."
    )
    body = TopicPOST(
        title=f"{a['type']} {a.get('name') or a['guid']} against {b['type']} {b.get('name') or b['guid']}"[:200],
        description=description,
        topic_type="Clash" if "Clash" in (extensions.get("topic_type") or []) else None,
        topic_status="Open" if "Open" in (extensions.get("topic_status") or []) else None,
        labels=["Clash"] if "Clash" in (extensions.get("topic_label") or []) else None,
    )
    validate_against_extensions(body, extensions)
    return body


def _viewpoint_body(pair: dict[str, Any]) -> ViewpointPOST:
    a, b = Component(ifc_guid=pair["a"]["guid"]), Component(ifc_guid=pair["b"]["guid"])
    return ViewpointPOST(
        perspective_camera=camera_looking_at(pair["point"], pair.get("extent")),
        components=Components(
            selection=[a, b],
            coloring=[Coloring(color=COLOUR_A, components=[a]), Coloring(color=COLOUR_B, components=[b])],
            visibility=Visibility(default_visibility=True),
        ),
    )


@router.post(
    "/projects/{project_id}/ifc-clash/{clash_id}/topics",
    summary="Make BCF topics of chosen clashes, with a viewpoint each",
    response_model=list[IfcClashTopic],
    status_code=201,
)
async def clash_topics(
    ctx: ProjectCtx,
    clash_id: ClashId,
    body: IfcClashTopicsRequest,
    ifcgraph: IfcGraphDep,
    settings: SettingsDep,
    projects: ProjectsDep,
    topics: TopicsDep,
    viewpoints: ViewpointsDep,
) -> list[IfcClashTopic]:
    """One topic per chosen clash, titled after the two elements, with both selected and coloured in the viewpoint.

    Needs the `bcf` scope and the `createTopic` action. Nothing is made unless asked for here.
    """
    if ifcgraph is None or not settings.ifcgraph_enabled or not settings.ifcgraph_clash_enabled:
        raise HTTPException(404, "The clash check is off on this server")
    ctx.require(ctx.can("createTopic", entity="project"), "createTopic")
    if not is_uuid(clash_id):
        raise HTTPException(404, "Clash check not found")
    row = await ifcgraph.clash_report(
        user_id=ctx.user_id, project_id=ctx.project_id, clash_id=normalize_guid(clash_id), with_clashes=True
    )
    if row is None:
        raise HTTPException(404, "Clash check not found")
    pairs = row.get("clashes") or []
    chosen = sorted(set(body.clashes))
    if any(index >= len(pairs) for index in chosen):
        raise HTTPException(400, f"The report has {len(pairs)} clashes; a position is past the end")
    extensions = await projects.extensions(ctx.project_id) or {}
    made: list[IfcClashTopic] = []
    for index in chosen:
        pair = pairs[index]
        topic = await topics.create(project_id=ctx.project_id, author=ctx.username, body=_topic_body(pair, extensions))
        viewpoint = await viewpoints.create(
            project_id=ctx.project_id, topic_guid=topic.guid, author=ctx.username, body=_viewpoint_body(pair)
        )
        if ifcgraph is not None:
            await ifcgraph.link_viewpoint(project_id=ctx.project_id, viewpoint_guid=viewpoint.model.guid)
        made.append(
            IfcClashTopic(clash=index, topic_guid=topic.guid, viewpoint_guid=viewpoint.model.guid, title=topic.title)
        )
    return made
