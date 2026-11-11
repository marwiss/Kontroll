# This file was generated with the assistance of an AI coding tool.
"""BCF API 3.4 Comment services."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Path, Query, Response

from opencde.bcf.access import ProjectContext, parse_guid
from opencde.bcf.odata_params import ODataDep, ODataParams
from opencde.bcf.schemas import CommentAuthorization, CommentGET, CommentPOST, CommentPUT, dump
from opencde.bcf.topic_access import TopicContext, TopicCtx
from opencde.store.bcf.comments import (
    COMMENT_DEFAULT_ORDER,
    COMMENT_FIELDS,
    COMMENT_ORDERABLE,
    CommentsDep,
)
from opencde.store.protocols import CommentStore

router = APIRouter(prefix="/projects/{project_id}/topics/{topic_id}/comments", tags=["BCF API"])

IncludeAuthorization = Annotated[bool, Query(alias="includeAuthorization")]
CommentId = Annotated[str, Path(alias="comment_id", max_length=64)]


def authorized(comment: CommentGET, ctx: ProjectContext, include: bool) -> CommentGET:
    if include:
        comment.authorization = CommentAuthorization(comment_actions=ctx.comment_actions(comment.author))
    return comment


def with_authorization(comment: CommentGET, ctx: ProjectContext, include: bool) -> dict[str, Any]:
    """The answer of 3.0, which has no replies between comments; a client of 2.1 may have left one."""
    body = dump(authorized(comment, ctx, include))
    body.pop("reply_to_comment_guid", None)
    return body


async def found_comments(topic: TopicContext, comments: CommentStore, odata: ODataParams) -> list[CommentGET]:
    compiled = odata.compile(COMMENT_FIELDS, COMMENT_ORDERABLE, COMMENT_DEFAULT_ORDER)
    where = {"user_id": topic.user_id, "project_id": topic.project_id, "topic_guid": topic.guid}
    found = await comments.search(**where, compiled=compiled)
    await odata.say_if_cut(compiled, len(found), lambda: comments.count(**where, compiled=compiled))
    return found


async def found_comment(topic: TopicContext, comment_id: str, comments: CommentStore) -> CommentGET:
    guid = parse_guid(comment_id, "Comment")
    comment = await comments.get(user_id=topic.user_id, project_id=topic.project_id, topic_guid=topic.guid, guid=guid)
    if comment is None:
        raise HTTPException(404, "Comment not found")
    return comment


async def create_comment(
    topic: TopicContext, body: CommentPOST, comments: CommentStore, *, reply_to: str | None = None
) -> CommentGET:
    """Add a comment. Needs the ``createComment`` topic action."""
    topic.require_topic_action("createComment")
    return await comments.create(
        project_id=topic.project_id, topic_guid=topic.guid, author=topic.username, body=body, reply_to=reply_to
    )


async def update_comment(
    topic: TopicContext,
    comment_id: str,
    body: CommentPUT,
    comments: CommentStore,
    *,
    change_reply: bool = False,
    reply_to: str | None = None,
) -> CommentGET:
    """Replace the comment. Needs the ``update`` comment action (authors, editors, managers)."""
    existing = await found_comment(topic, comment_id, comments)
    topic.project.require(topic.project.can("update", existing.author, entity="comment"), "update")
    comment = await comments.update(
        project_id=topic.project_id,
        topic_guid=topic.guid,
        guid=existing.guid,
        author=topic.username,
        body=body,
        change_reply=change_reply,
        reply_to=reply_to,
    )
    if comment is None:
        raise HTTPException(404, "Comment not found")
    return comment


@router.get("", summary="3.4.1 GET Comments")
async def comments_get(
    topic: TopicCtx, comments: CommentsDep, odata: ODataDep, include_authorization: IncludeAuthorization = False
) -> list[dict[str, Any]]:
    """Comments of the topic, oldest first; ``$filter`` on ``author`` and ``date``, ``$orderby`` on ``date``."""
    found = await found_comments(topic, comments, odata)
    return [with_authorization(comment, topic.project, include_authorization) for comment in found]


@router.post("", summary="3.4.2 POST Comment", status_code=201)
async def comment_post(topic: TopicCtx, body: CommentPOST, comments: CommentsDep) -> dict[str, Any]:
    """Add a comment. Needs the ``createComment`` topic action."""
    return with_authorization(await create_comment(topic, body, comments), topic.project, True)


@router.get("/{comment_id}", summary="3.4.3 GET Comment")
async def comment_get(
    topic: TopicCtx, comment_id: CommentId, comments: CommentsDep, include_authorization: IncludeAuthorization = False
) -> dict[str, Any]:
    comment = await found_comment(topic, comment_id, comments)
    return with_authorization(comment, topic.project, include_authorization)


@router.put("/{comment_id}", summary="3.4.4 PUT Comment")
async def comment_put(
    topic: TopicCtx, comment_id: CommentId, body: CommentPUT, comments: CommentsDep
) -> dict[str, Any]:
    """Replace the comment. Needs the ``update`` comment action (authors, editors, managers)."""
    return with_authorization(await update_comment(topic, comment_id, body, comments), topic.project, True)


@router.delete("/{comment_id}", summary="3.4.5 DELETE Comment", status_code=200, response_class=Response)
async def comment_delete(topic: TopicCtx, comment_id: CommentId, comments: CommentsDep) -> Response:
    """Delete the comment. Needs the ``delete`` comment action."""
    existing = await found_comment(topic, comment_id, comments)
    topic.project.require(topic.project.can("delete", existing.author, entity="comment"), "delete")
    if not await comments.delete(
        project_id=topic.project_id, topic_guid=topic.guid, guid=existing.guid, author=topic.username
    ):
        raise HTTPException(404, "Comment not found")
    return Response(status_code=200)
