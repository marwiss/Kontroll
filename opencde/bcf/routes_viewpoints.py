# This file was generated with the assistance of an AI coding tool.
"""BCF API 3.5 Viewpoint services."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Path, Query, Response
from fastapi.responses import StreamingResponse

from opencde.bcf.access import ProjectContext, parse_guid
from opencde.bcf.binary import file_response
from opencde.bcf.images import CONTENT_TYPES
from opencde.bcf.schemas import ColoringGET, SelectionGET, ViewpointAuthorization, ViewpointPOST, VisibilityGET, dump
from opencde.bcf.topic_access import TopicCtx
from opencde.bcf.viewpoints import ViewpointRecord, ViewpointsDep
from opencde.deps import StorageDep
from opencde.ifcgraph.service import IfcGraphDep
from opencde.logging import get_logger

log = get_logger(__name__)

router = APIRouter(prefix="/projects/{project_id}/topics/{topic_id}/viewpoints", tags=["BCF API"])

IncludeAuthorization = Annotated[bool, Query(alias="includeAuthorization")]
ViewpointId = Annotated[str, Path(alias="viewpoint_id", max_length=64)]
BitmapId = Annotated[str, Path(alias="bitmap_id", max_length=64)]


def with_authorization(record: ViewpointRecord, ctx: ProjectContext, include: bool) -> dict[str, Any]:
    if include:
        record.model.authorization = ViewpointAuthorization(viewpoint_actions=ctx.viewpoint_actions(record.author))
    return dump(record.model)


async def _record(topic: TopicCtx, viewpoints: ViewpointsDep, viewpoint_id: str) -> ViewpointRecord:
    guid = parse_guid(viewpoint_id, "Viewpoint")
    record = await viewpoints.get(user_id=topic.user_id, project_id=topic.project_id, topic_guid=topic.guid, guid=guid)
    if record is None:
        raise HTTPException(404, "Viewpoint not found")
    return record


def _scope(topic: TopicCtx, guid: str) -> dict[str, str]:
    return {"user_id": topic.user_id, "project_id": topic.project_id, "topic_guid": topic.guid, "guid": guid}


@router.get("", summary="3.5.1 GET Viewpoints")
async def viewpoints_get(
    topic: TopicCtx, viewpoints: ViewpointsDep, include_authorization: IncludeAuthorization = False
) -> list[dict[str, Any]]:
    found = await viewpoints.search(user_id=topic.user_id, project_id=topic.project_id, topic_guid=topic.guid)
    return [with_authorization(record, topic.project, include_authorization) for record in found]


@router.post("", summary="3.5.2 POST Viewpoint", status_code=201)
async def viewpoint_post(
    topic: TopicCtx, body: ViewpointPOST, viewpoints: ViewpointsDep, ifcgraph: IfcGraphDep
) -> dict[str, Any]:
    """Create an immutable viewpoint with its images and components. Needs ``createViewpoint``."""
    topic.require_topic_action("createViewpoint")
    record = await viewpoints.create(
        project_id=topic.project_id, topic_guid=topic.guid, author=topic.username, body=body
    )
    if ifcgraph is not None and body.components is not None:
        await ifcgraph.link_viewpoint(project_id=topic.project_id, viewpoint_guid=record.model.guid)
    return with_authorization(record, topic.project, True)


@router.get("/{viewpoint_id}", summary="3.5.3 GET Viewpoint")
async def viewpoint_get(
    topic: TopicCtx,
    viewpoint_id: ViewpointId,
    viewpoints: ViewpointsDep,
    include_authorization: IncludeAuthorization = False,
) -> dict[str, Any]:
    record = await _record(topic, viewpoints, viewpoint_id)
    return with_authorization(record, topic.project, include_authorization)


@router.get("/{viewpoint_id}/snapshot", summary="3.5.4 GET Snapshot", response_class=StreamingResponse)
async def snapshot_get(
    topic: TopicCtx, viewpoint_id: ViewpointId, viewpoints: ViewpointsDep, storage: StorageDep
) -> StreamingResponse:
    """The snapshot as a PNG or JPEG file."""
    record = await _record(topic, viewpoints, viewpoint_id)
    if not record.snapshot_key or not record.snapshot_type:
        raise HTTPException(404, "Viewpoint has no snapshot")
    return file_response(
        storage,
        record.snapshot_key,
        media_type=CONTENT_TYPES[record.snapshot_type],
        filename=f"{record.model.guid}.{record.snapshot_type}",
    )


@router.get("/{viewpoint_id}/bitmaps/{bitmap_id}", summary="3.5.5 GET Bitmap", response_class=StreamingResponse)
async def bitmap_get(
    topic: TopicCtx, viewpoint_id: ViewpointId, bitmap_id: BitmapId, viewpoints: ViewpointsDep, storage: StorageDep
) -> StreamingResponse:
    guid = parse_guid(viewpoint_id, "Viewpoint")
    bitmap_guid = parse_guid(bitmap_id, "Bitmap")
    bitmap = await viewpoints.bitmap(**_scope(topic, guid), bitmap_guid=bitmap_guid)
    if bitmap is None:
        raise HTTPException(404, "Bitmap not found")
    return file_response(
        storage,
        bitmap["storage_key"],
        media_type=CONTENT_TYPES[bitmap["bitmap_type"]],
        filename=f"{bitmap_guid}.{bitmap['bitmap_type']}",
    )


@router.get("/{viewpoint_id}/selection", summary="3.5.6 GET selected Components")
async def selection_get(topic: TopicCtx, viewpoint_id: ViewpointId, viewpoints: ViewpointsDep) -> dict[str, Any]:
    guid = parse_guid(viewpoint_id, "Viewpoint")
    if await viewpoints.node(**_scope(topic, guid)) is None:
        raise HTTPException(404, "Viewpoint not found")
    return dump(SelectionGET(selection=await viewpoints.selection(**_scope(topic, guid))))


@router.get("/{viewpoint_id}/coloring", summary="3.5.7 GET colored Components")
async def coloring_get(topic: TopicCtx, viewpoint_id: ViewpointId, viewpoints: ViewpointsDep) -> dict[str, Any]:
    guid = parse_guid(viewpoint_id, "Viewpoint")
    if await viewpoints.node(**_scope(topic, guid)) is None:
        raise HTTPException(404, "Viewpoint not found")
    return dump(ColoringGET(coloring=await viewpoints.coloring(**_scope(topic, guid))))


@router.get("/{viewpoint_id}/visibility", summary="3.5.8 GET visibility of Components")
async def visibility_get(topic: TopicCtx, viewpoint_id: ViewpointId, viewpoints: ViewpointsDep) -> dict[str, Any]:
    guid = parse_guid(viewpoint_id, "Viewpoint")
    node = await viewpoints.node(**_scope(topic, guid))
    if node is None:
        raise HTTPException(404, "Viewpoint not found")
    return dump(VisibilityGET(visibility=await viewpoints.visibility(node, **_scope(topic, guid))))


@router.delete("/{viewpoint_id}", summary="3.5.9 DELETE Viewpoint", status_code=200, response_class=Response)
async def viewpoint_delete(
    topic: TopicCtx, viewpoint_id: ViewpointId, viewpoints: ViewpointsDep, storage: StorageDep
) -> Response:
    """Delete the viewpoint and its images. Needs the ``delete`` viewpoint action; 409 while a comment refers to it."""
    record = await _record(topic, viewpoints, viewpoint_id)
    topic.project.require(topic.project.can("delete", record.author, entity="viewpoint"), "delete")
    for key in await viewpoints.delete(topic_guid=topic.guid, guid=record.model.guid):
        try:
            storage.delete(key)
        except ValueError:
            log.warning("storage_key_invalid", key=key)
    return Response(status_code=200)
