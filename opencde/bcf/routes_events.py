# This file was generated with the assistance of an AI coding tool.
"""BCF API 3.9 Topics events and 3.10 Comments events.

Registered before the topic and comment routers so that the literal paths
``/topics/events`` and ``/topics/comments/events`` win over ``/topics/{topic_id}``.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Path

from opencde.bcf import events
from opencde.bcf.access import ProjectCtx, parse_guid
from opencde.bcf.comments import CommentsDep
from opencde.bcf.odata_params import ODataDep, ODataParams
from opencde.bcf.topic_access import TopicCtx
from opencde.deps import GraphDep
from opencde.odata import Compiled

router = APIRouter(prefix="/bcf/3.0/projects/{project_id}", tags=["BCF API"])

CommentId = Annotated[str, Path(alias="comment_id", max_length=64)]


def _compiled(odata: ODataParams) -> Compiled:
    return odata.compile(events.EVENT_FIELDS, events.EVENT_ORDERABLE, events.EVENT_DEFAULT_ORDER)


@router.get("/topics/events", summary="3.9.1 GET Topics Events")
async def topics_events_get(ctx: ProjectCtx, graph: GraphDep, odata: ODataDep) -> list[dict[str, Any]]:
    """Topic events of the whole project; ``$filter`` on ``topic_guid``, ``author``, ``type``, ``date``."""
    return await events.query(
        graph, user_id=ctx.user_id, project_id=ctx.project_id, kind="topic", compiled=_compiled(odata)
    )


@router.get("/topics/comments/events", summary="3.10.1 GET Comments Events")
async def comments_events_get(ctx: ProjectCtx, graph: GraphDep, odata: ODataDep) -> list[dict[str, Any]]:
    """Comment events of the whole project; ``$filter`` also on ``comment_guid``."""
    return await events.query(
        graph, user_id=ctx.user_id, project_id=ctx.project_id, kind="comment", compiled=_compiled(odata)
    )


@router.get("/topics/{topic_id}/events", summary="3.9.2 GET Topic Events")
async def topic_events_get(topic: TopicCtx, graph: GraphDep, odata: ODataDep) -> list[dict[str, Any]]:
    return await events.query(
        graph,
        user_id=topic.user_id,
        project_id=topic.project_id,
        kind="topic",
        compiled=_compiled(odata),
        topic_guid=topic.guid,
    )


@router.get("/topics/{topic_id}/comments/{comment_id}/events", summary="3.10.2 GET Comment Events")
async def comment_events_get(
    topic: TopicCtx, comment_id: CommentId, graph: GraphDep, comments: CommentsDep, odata: ODataDep
) -> list[dict[str, Any]]:
    guid = parse_guid(comment_id, "Comment")
    if await comments.get(user_id=topic.user_id, project_id=topic.project_id, topic_guid=topic.guid, guid=guid) is None:
        raise HTTPException(404, "Comment not found")
    return await events.query(
        graph,
        user_id=topic.user_id,
        project_id=topic.project_id,
        kind="comment",
        compiled=_compiled(odata),
        topic_guid=topic.guid,
        comment_guid=guid,
    )
