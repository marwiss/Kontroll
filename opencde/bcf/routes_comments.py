# This file was generated with the assistance of an AI coding tool.
"""BCF API 3.4 Comment services."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Path, Query, Response

from opencde.bcf.access import ProjectContext, parse_guid
from opencde.bcf.comments import COMMENT_DEFAULT_ORDER, COMMENT_FIELDS, COMMENT_ORDERABLE, CommentsDep
from opencde.bcf.odata_params import ODataDep
from opencde.bcf.schemas import CommentAuthorization, CommentGET, CommentPOST, CommentPUT, dump
from opencde.bcf.topic_access import TopicCtx

router = APIRouter(prefix="/bcf/3.0/projects/{project_id}/topics/{topic_id}/comments", tags=["BCF API"])

IncludeAuthorization = Annotated[bool, Query(alias="includeAuthorization")]
CommentId = Annotated[str, Path(alias="comment_id", max_length=64)]


def with_authorization(comment: CommentGET, ctx: ProjectContext, include: bool) -> dict[str, Any]:
    if include:
        comment.authorization = CommentAuthorization(comment_actions=ctx.comment_actions(comment.author))
    return dump(comment)


@router.get("", summary="3.4.1 GET Comments")
async def comments_get(
    topic: TopicCtx, comments: CommentsDep, odata: ODataDep, include_authorization: IncludeAuthorization = False
) -> list[dict[str, Any]]:
    """Comments of the topic, oldest first; ``$filter`` on ``author`` and ``date``, ``$orderby`` on ``date``."""
    compiled = odata.compile(COMMENT_FIELDS, COMMENT_ORDERABLE, COMMENT_DEFAULT_ORDER)
    found = await comments.search(
        user_id=topic.user_id, project_id=topic.project_id, topic_guid=topic.guid, compiled=compiled
    )
    return [with_authorization(comment, topic.project, include_authorization) for comment in found]


@router.post("", summary="3.4.2 POST Comment", status_code=201)
async def comment_post(topic: TopicCtx, body: CommentPOST, comments: CommentsDep) -> dict[str, Any]:
    """Add a comment. Needs the ``createComment`` topic action."""
    topic.require_topic_action("createComment")
    comment = await comments.create(
        project_id=topic.project_id, topic_guid=topic.guid, author=topic.username, body=body
    )
    return with_authorization(comment, topic.project, True)


@router.get("/{comment_id}", summary="3.4.3 GET Comment")
async def comment_get(
    topic: TopicCtx, comment_id: CommentId, comments: CommentsDep, include_authorization: IncludeAuthorization = False
) -> dict[str, Any]:
    guid = parse_guid(comment_id, "Comment")
    comment = await comments.get(user_id=topic.user_id, project_id=topic.project_id, topic_guid=topic.guid, guid=guid)
    if comment is None:
        raise HTTPException(404, "Comment not found")
    return with_authorization(comment, topic.project, include_authorization)


@router.put("/{comment_id}", summary="3.4.4 PUT Comment")
async def comment_put(
    topic: TopicCtx, comment_id: CommentId, body: CommentPUT, comments: CommentsDep
) -> dict[str, Any]:
    """Replace the comment. Needs the ``update`` comment action (authors, editors, managers)."""
    guid = parse_guid(comment_id, "Comment")
    existing = await comments.get(user_id=topic.user_id, project_id=topic.project_id, topic_guid=topic.guid, guid=guid)
    if existing is None:
        raise HTTPException(404, "Comment not found")
    topic.project.require(topic.project.can("update", existing.author, entity="comment"), "update")
    comment = await comments.update(
        project_id=topic.project_id, topic_guid=topic.guid, guid=guid, author=topic.username, body=body
    )
    if comment is None:
        raise HTTPException(404, "Comment not found")
    return with_authorization(comment, topic.project, True)


@router.delete("/{comment_id}", summary="3.4.5 DELETE Comment", status_code=200)
async def comment_delete(topic: TopicCtx, comment_id: CommentId, comments: CommentsDep) -> Response:
    """Delete the comment. Needs the ``delete`` comment action."""
    guid = parse_guid(comment_id, "Comment")
    existing = await comments.get(user_id=topic.user_id, project_id=topic.project_id, topic_guid=topic.guid, guid=guid)
    if existing is None:
        raise HTTPException(404, "Comment not found")
    topic.project.require(topic.project.can("delete", existing.author, entity="comment"), "delete")
    if not await comments.delete(topic_guid=topic.guid, guid=guid):
        raise HTTPException(404, "Comment not found")
    return Response(status_code=200)
