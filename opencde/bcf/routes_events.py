# This file was generated with the assistance of an AI coding tool.
"""BCF API 3.9 Topics events and 3.10 Comments events.

Registered before the topic and comment routers so that the literal paths
``/topics/events`` and ``/topics/comments/events`` win over ``/topics/{topic_id}``.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Path

from opencde.bcf import events
from opencde.bcf.access import ProjectContext, ProjectCtx, parse_guid
from opencde.bcf.odata_params import ODataDep, ODataParams
from opencde.bcf.topic_access import TopicContext, TopicCtx
from opencde.odata import Compiled
from opencde.store.bcf.comments import CommentsDep
from opencde.store.bcf.events import EventsDep
from opencde.store.protocols import BcfEventStore, CommentStore

router = APIRouter(prefix="/projects/{project_id}", tags=["BCF API"])

CommentId = Annotated[str, Path(alias="comment_id", max_length=64)]


def _compiled(odata: ODataParams) -> Compiled:
    return odata.compile(events.EVENT_FIELDS, events.EVENT_ORDERABLE, events.EVENT_DEFAULT_ORDER)


async def _events(store: BcfEventStore, odata: ODataParams, **where: Any) -> list[dict[str, Any]]:
    """The events ``where`` names, and the headers of a list the server's limit cut (F14 a)."""
    compiled = _compiled(odata)
    found = await store.query(compiled=compiled, **where)
    await odata.say_if_cut(compiled, len(found), lambda: store.count(compiled=compiled, **where))
    return found


async def of_project(
    ctx: ProjectContext, store: BcfEventStore, odata: ODataParams, kind: str, left_out: frozenset[str]
) -> list[dict[str, Any]]:
    return await _events(store, odata, user_id=ctx.user_id, project_id=ctx.project_id, kind=kind, left_out=left_out)


async def of_topic(
    topic: TopicContext, store: BcfEventStore, odata: ODataParams, left_out: frozenset[str]
) -> list[dict[str, Any]]:
    return await _events(
        store,
        odata,
        user_id=topic.user_id,
        project_id=topic.project_id,
        kind="topic",
        topic_guid=topic.guid,
        left_out=left_out,
    )


async def of_comment(
    topic: TopicContext,
    comment_id: str,
    store: BcfEventStore,
    comments: CommentStore,
    odata: ODataParams,
    left_out: frozenset[str],
) -> list[dict[str, Any]]:
    guid = parse_guid(comment_id, "Comment")
    if await comments.get(user_id=topic.user_id, project_id=topic.project_id, topic_guid=topic.guid, guid=guid) is None:
        raise HTTPException(404, "Comment not found")
    return await _events(
        store,
        odata,
        user_id=topic.user_id,
        project_id=topic.project_id,
        kind="comment",
        topic_guid=topic.guid,
        comment_guid=guid,
        left_out=left_out,
    )


@router.get("/topics/events", summary="3.9.1 GET Topics Events")
async def topics_events_get(ctx: ProjectCtx, store: EventsDep, odata: ODataDep) -> list[dict[str, Any]]:
    """Topic events of the whole project; ``$filter`` on ``topic_guid``, ``author``, ``type``, ``date``."""
    return await of_project(ctx, store, odata, "topic", events.NOT_IN_30)


@router.get("/topics/comments/events", summary="3.10.1 GET Comments Events")
async def comments_events_get(ctx: ProjectCtx, store: EventsDep, odata: ODataDep) -> list[dict[str, Any]]:
    """Comment events of the whole project; ``$filter`` also on ``comment_guid``."""
    return await of_project(ctx, store, odata, "comment", events.NOT_IN_30)


@router.get("/topics/{topic_id}/events", summary="3.9.2 GET Topic Events")
async def topic_events_get(topic: TopicCtx, store: EventsDep, odata: ODataDep) -> list[dict[str, Any]]:
    return await of_topic(topic, store, odata, events.NOT_IN_30)


@router.get("/topics/{topic_id}/comments/{comment_id}/events", summary="3.10.2 GET Comment Events")
async def comment_events_get(
    topic: TopicCtx, comment_id: CommentId, store: EventsDep, comments: CommentsDep, odata: ODataDep
) -> list[dict[str, Any]]:
    return await of_comment(topic, comment_id, store, comments, odata, events.NOT_IN_30)
