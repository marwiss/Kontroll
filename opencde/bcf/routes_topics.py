# This file was generated with the assistance of an AI coding tool.
"""BCF API 3.2 Topic services and 3.9 Topics events."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response

from opencde.bcf import events
from opencde.bcf.access import ProjectContext, ProjectCtx, parse_guid
from opencde.bcf.odata_params import ODataParams, odata_params
from opencde.bcf.schemas import TopicAuthorization, TopicGET, TopicPOST, TopicPUT, dump
from opencde.bcf.topics import (
    TOPIC_DEFAULT_ORDER,
    TOPIC_FIELDS,
    TOPIC_ORDERABLE,
    TopicRepository,
    validate_against_extensions,
)
from opencde.deps import GraphDep, ProjectsDep, SettingsDep, StorageDep
from opencde.logging import get_logger

log = get_logger(__name__)

router = APIRouter(prefix="/bcf/3.0/projects/{project_id}", tags=["BCF API"])

IncludeAuthorization = Annotated[bool, Query(alias="includeAuthorization")]
TopicId = Annotated[str, Path(alias="topic_id", max_length=64)]
OData = Annotated[ODataParams, Depends(odata_params)]


def topic_repository(graph: GraphDep, settings: SettingsDep) -> TopicRepository:
    return TopicRepository(graph, id_prefix=settings.server_assigned_id_prefix)


TopicsDep = Annotated[TopicRepository, Depends(topic_repository)]


def with_authorization(topic: TopicGET, ctx: ProjectContext, statuses: list[str], include: bool) -> dict[str, Any]:
    if include:
        actions = ctx.topic_actions(topic.creation_author)
        topic.authorization = TopicAuthorization(
            topic_actions=actions, topic_status=statuses if "update" in actions else []
        )
    return dump(topic)


async def _statuses(ctx: ProjectContext, projects: ProjectsDep) -> list[str]:
    values = await projects.extensions(ctx.project_id)
    return list((values or {}).get("topic_status") or [])


# -- events (declared before /topics/{topic_id} so the literal path wins) -----------------------


@router.get("/topics/events", summary="3.9.1 GET Topics Events")
async def topics_events_get(ctx: ProjectCtx, graph: GraphDep, odata: OData) -> list[dict[str, Any]]:
    compiled = odata.compile(events.EVENT_FIELDS, events.EVENT_ORDERABLE, events.EVENT_DEFAULT_ORDER)
    return await events.query(graph, user_id=ctx.user_id, project_id=ctx.project_id, kind="topic", compiled=compiled)


@router.get("/topics/{topic_id}/events", summary="3.9.2 GET Topic Events")
async def topic_events_get(
    ctx: ProjectCtx, topic_id: TopicId, graph: GraphDep, topics: TopicsDep, odata: OData
) -> list[dict[str, Any]]:
    guid = parse_guid(topic_id, "Topic")
    if await topics.get(user_id=ctx.user_id, project_id=ctx.project_id, guid=guid) is None:
        raise HTTPException(404, "Topic not found")
    compiled = odata.compile(events.EVENT_FIELDS, events.EVENT_ORDERABLE, events.EVENT_DEFAULT_ORDER)
    return await events.query(
        graph, user_id=ctx.user_id, project_id=ctx.project_id, kind="topic", compiled=compiled, topic_guid=guid
    )


# -- topics -----------------------------------------------------------------------------------


@router.get("/topics", summary="3.2.1 GET Topics")
async def topics_get(
    ctx: ProjectCtx,
    topics: TopicsDep,
    projects: ProjectsDep,
    odata: OData,
    include_authorization: IncludeAuthorization = False,
) -> list[dict[str, Any]]:
    """Topics of the project; ``$filter``, ``$orderby``, ``$top`` and ``$skip`` as in BCF 3.2.1."""
    compiled = odata.compile(TOPIC_FIELDS, TOPIC_ORDERABLE, TOPIC_DEFAULT_ORDER)
    found = await topics.search(user_id=ctx.user_id, project_id=ctx.project_id, compiled=compiled)
    statuses = await _statuses(ctx, projects) if include_authorization else []
    return [with_authorization(topic, ctx, statuses, include_authorization) for topic in found]


@router.post("/topics", summary="3.2.2 POST Topic", status_code=201)
async def topic_post(ctx: ProjectCtx, body: TopicPOST, topics: TopicsDep, projects: ProjectsDep) -> dict[str, Any]:
    """Create a topic. Needs the ``createTopic`` project action. ``409`` when the guid exists."""
    ctx.require(ctx.can("createTopic", entity="project"), "createTopic")
    extensions = await projects.extensions(ctx.project_id) or {}
    validate_against_extensions(body, extensions)
    topic = await topics.create(project_id=ctx.project_id, author=ctx.username, body=body)
    return with_authorization(topic, ctx, extensions.get("topic_status", []), True)


@router.get("/topics/{topic_id}", summary="3.2.3 GET Topic")
async def topic_get(
    ctx: ProjectCtx,
    topic_id: TopicId,
    topics: TopicsDep,
    projects: ProjectsDep,
    include_authorization: IncludeAuthorization = False,
) -> dict[str, Any]:
    guid = parse_guid(topic_id, "Topic")
    topic = await topics.get(user_id=ctx.user_id, project_id=ctx.project_id, guid=guid)
    if topic is None:
        raise HTTPException(404, "Topic not found")
    statuses = await _statuses(ctx, projects) if include_authorization else []
    return with_authorization(topic, ctx, statuses, include_authorization)


@router.put("/topics/{topic_id}", summary="3.2.4 PUT Topic")
async def topic_put(
    ctx: ProjectCtx, topic_id: TopicId, body: TopicPUT, topics: TopicsDep, projects: ProjectsDep
) -> dict[str, Any]:
    """Replace the topic (Foundation API 1.3: PUT updates the whole object). Needs ``update``."""
    guid = parse_guid(topic_id, "Topic")
    existing = await topics.get(user_id=ctx.user_id, project_id=ctx.project_id, guid=guid)
    if existing is None:
        raise HTTPException(404, "Topic not found")
    ctx.require(ctx.can("update", existing.creation_author), "update")
    extensions = await projects.extensions(ctx.project_id) or {}
    validate_against_extensions(body, extensions)
    topic = await topics.update(project_id=ctx.project_id, guid=guid, author=ctx.username, body=body)
    if topic is None:
        raise HTTPException(404, "Topic not found")
    return with_authorization(topic, ctx, extensions.get("topic_status", []), True)


@router.delete("/topics/{topic_id}", summary="3.2.5 DELETE Topic", status_code=200)
async def topic_delete(ctx: ProjectCtx, topic_id: TopicId, topics: TopicsDep, storage: StorageDep) -> Response:
    """Delete the topic with its comments, viewpoints and references. Needs ``delete``."""
    guid = parse_guid(topic_id, "Topic")
    existing = await topics.get(user_id=ctx.user_id, project_id=ctx.project_id, guid=guid)
    if existing is None:
        raise HTTPException(404, "Topic not found")
    ctx.require(ctx.can("delete", existing.creation_author), "delete")
    for key in await topics.delete(project_id=ctx.project_id, guid=guid):
        try:
            storage.delete(key)
        except ValueError:
            log.warning("storage_key_invalid", key=key)
    return Response(status_code=200)
