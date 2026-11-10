# This file was generated with the assistance of an AI coding tool.
"""Comments (BCF API 3.4) and their events (3.10).

A ``Comment`` hangs off its topic. It may point at one of the topic's
viewpoints through ``viewpoint_guid``; a comment with a viewpoint and no text
is allowed (3.4.2). Creating or editing a comment moves the topic's
``modified_date`` (3.2.1) and records comment events in the same transaction.

BCF API 2.1 also lets a comment answer another through ``reply_to_comment_guid``.
3.0 took that away, so its routes neither show nor touch it.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends, HTTPException

from opencde.bcf import events
from opencde.bcf.schemas import CommentFields, CommentGET, CommentPOST, CommentPUT
from opencde.bcf.topic_access import TopicsDep
from opencde.bcf.topics import TopicRepository
from opencde.deps import GraphDep
from opencde.graph.graph import Graph, Tx
from opencde.ids import is_uuid, new_id, normalize_guid
from opencde.odata import Compiled, Field
from opencde.timeutil import now_iso

COMMENT_FIELDS = {"author": Field("c.author", "string"), "date": Field("c.date", "datetime")}
COMMENT_ORDERABLE = ("date",)
COMMENT_DEFAULT_ORDER = "c.date ASC, c.guid ASC"
TEXT_EVENT_LIMIT = 1024


def to_model(node: dict[str, Any]) -> CommentGET:
    return CommentGET(
        guid=node["guid"],
        date=node["date"],
        author=node["author"],
        comment=node.get("comment") or "",
        topic_guid=node["topic_guid"],
        viewpoint_guid=node.get("viewpoint_guid"),
        reply_to_comment_guid=node.get("reply_to_comment_guid"),
        modified_date=node.get("modified_date"),
        modified_author=node.get("modified_author"),
    )


def _text(fields: CommentFields) -> str:
    return (fields.comment or "").strip()


def _viewpoint_guid(fields: CommentFields) -> str | None:
    if fields.viewpoint_guid is None:
        return None
    if not is_uuid(fields.viewpoint_guid):
        raise HTTPException(400, "viewpoint_guid must be a UUID")
    return normalize_guid(fields.viewpoint_guid)


def _reply_guid(value: str | None) -> str | None:
    if value is None:
        return None
    if not is_uuid(value):
        raise HTTPException(400, "reply_to_comment_guid must be a UUID")
    return normalize_guid(value)


class CommentRepository:
    def __init__(self, graph: Graph, topics: TopicRepository) -> None:
        self.graph = graph
        self.topics = topics

    @staticmethod
    def _matching(compiled: Compiled) -> str:
        return f"""
            MATCH (:User {{id: $user_id}})-[:MEMBER_OF]->(:Project {{project_id: $project_id}})
                  -[:HAS_TOPIC]->(:Topic {{guid: $topic_guid}})-[:HAS_COMMENT]->(c:Comment)
            WHERE true {compiled.where_clause()}
            """

    async def count(self, *, user_id: str, project_id: str, topic_guid: str, compiled: Compiled) -> int:
        """How many comments of the topic the options match, before ``$top`` and ``$skip``."""
        row = await self.graph.one(
            self._matching(compiled) + "RETURN count(c) AS total",
            user_id=user_id,
            project_id=project_id,
            topic_guid=topic_guid,
            **compiled.params,
        )
        return int(row["total"]) if row else 0

    async def search(self, *, user_id: str, project_id: str, topic_guid: str, compiled: Compiled) -> list[CommentGET]:
        rows = await self.graph.run(
            self._matching(compiled)
            + f"""
            RETURN properties(c) AS comment
            ORDER BY {compiled.order_by}
            SKIP $skip LIMIT $limit
            """,
            user_id=user_id,
            project_id=project_id,
            topic_guid=topic_guid,
            skip=compiled.skip,
            limit=compiled.limit,
            **compiled.params,
        )
        return [to_model(row["comment"]) for row in rows]

    async def get(self, *, user_id: str, project_id: str, topic_guid: str, guid: str) -> CommentGET | None:
        row = await self.graph.one(
            """
            MATCH (:User {id: $user_id})-[:MEMBER_OF]->(:Project {project_id: $project_id})
                  -[:HAS_TOPIC]->(:Topic {guid: $topic_guid})-[:HAS_COMMENT]->(c:Comment {guid: $guid})
            RETURN properties(c) AS comment
            """,
            user_id=user_id,
            project_id=project_id,
            topic_guid=topic_guid,
            guid=guid,
        )
        return to_model(row["comment"]) if row else None

    async def _check_viewpoint(self, tx: Tx, topic_guid: str, viewpoint_guid: str | None) -> None:
        if viewpoint_guid is None:
            return
        row = await tx.one(
            "MATCH (:Topic {guid: $topic_guid})-[:HAS_VIEWPOINT]->(v:Viewpoint {guid: $guid}) RETURN v.guid AS guid",
            topic_guid=topic_guid,
            guid=viewpoint_guid,
        )
        if row is None:
            raise HTTPException(400, "viewpoint_guid is not a viewpoint of this topic")

    async def _check_reply(self, tx: Tx, topic_guid: str, reply_to: str | None, guid: str) -> None:
        if reply_to is None:
            return
        if reply_to == guid:
            raise HTTPException(400, "a comment cannot reply to itself")
        row = await tx.one(
            "MATCH (:Topic {guid: $topic_guid})-[:HAS_COMMENT]->(c:Comment {guid: $guid}) RETURN c.guid AS guid",
            topic_guid=topic_guid,
            guid=reply_to,
        )
        if row is None:
            raise HTTPException(400, "reply_to_comment_guid is not a comment of this topic")

    async def create(
        self, *, project_id: str, topic_guid: str, author: str, body: CommentPOST, reply_to: str | None = None
    ) -> CommentGET:
        if body.guid and not is_uuid(body.guid):
            raise HTTPException(400, "guid must be a UUID")
        guid = normalize_guid(body.guid) if body.guid else new_id()
        text = _text(body)
        viewpoint_guid = _viewpoint_guid(body)
        reply_guid = _reply_guid(reply_to)
        now = now_iso()

        async def work(tx: Tx) -> dict[str, Any]:
            if await tx.one("MATCH (c:Comment {guid: $guid}) RETURN c.guid AS guid", guid=guid):
                raise HTTPException(409, "A comment with this guid already exists")  # Foundation API 1.5.1
            await self._check_viewpoint(tx, topic_guid, viewpoint_guid)
            await self._check_reply(tx, topic_guid, reply_guid, guid)
            row = await tx.one(
                """
                MATCH (:Project {project_id: $project_id})-[:HAS_TOPIC]->(t:Topic {guid: $topic_guid}),
                      (u:User {username: $author})
                CREATE (t)-[:HAS_COMMENT]->(c:Comment {
                    guid: $guid, topic_guid: $topic_guid, date: $now, author: $author, comment: $text,
                    viewpoint_guid: $viewpoint_guid, reply_to_comment_guid: $reply_guid,
                    modified_date: $now, modified_author: $author
                })
                CREATE (c)-[:CREATED_BY]->(u)
                RETURN properties(c) AS comment
                """,
                project_id=project_id,
                topic_guid=topic_guid,
                author=author,
                guid=guid,
                now=now,
                text=text,
                viewpoint_guid=viewpoint_guid,
                reply_guid=reply_guid,
            )
            if row is None:
                raise HTTPException(404, "Topic not found")
            # BCF 3.10: creation also yields "update" events for the fields that are initially set.
            actions = [events.Action("comment_created")]
            if text:
                actions.append(events.Action("comment_text_updated", text[:TEXT_EVENT_LIMIT]))
            if viewpoint_guid:
                actions.append(events.Action("viewpoint_updated", viewpoint_guid))
            if reply_guid:
                actions.append(events.Action("reply_to_comment_updated", reply_guid))
            await events.record(
                tx,
                project_id=project_id,
                topic_guid=topic_guid,
                author=author,
                actions=actions,
                comment_guid=guid,
                date=now,
            )
            await self.topics.touch(tx, guid=topic_guid, author=author, now=now)
            return row["comment"]

        return to_model(await self.graph.write(work))

    async def update(
        self,
        *,
        project_id: str,
        topic_guid: str,
        guid: str,
        author: str,
        body: CommentPUT,
        change_reply: bool = False,
        reply_to: str | None = None,
    ) -> CommentGET | None:
        """Replace the comment. Only 2.1 knows of replies, so only it passes ``change_reply``."""
        text = _text(body)
        viewpoint_guid = _viewpoint_guid(body)
        reply_guid = _reply_guid(reply_to)
        now = now_iso()

        async def work(tx: Tx) -> dict[str, Any] | None:
            before = await tx.one(
                "MATCH (:Topic {guid: $topic_guid})-[:HAS_COMMENT]->(c:Comment {guid: $guid}) RETURN properties(c) AS comment",
                topic_guid=topic_guid,
                guid=guid,
            )
            if before is None:
                return None
            await self._check_viewpoint(tx, topic_guid, viewpoint_guid)
            old_reply = before["comment"].get("reply_to_comment_guid")
            new_reply = reply_guid if change_reply else old_reply
            await self._check_reply(tx, topic_guid, new_reply, guid)
            row = await tx.one(
                """
                MATCH (:Topic {guid: $topic_guid})-[:HAS_COMMENT]->(c:Comment {guid: $guid})
                SET c.comment = $text, c.viewpoint_guid = $viewpoint_guid, c.reply_to_comment_guid = $new_reply,
                    c.modified_date = $now, c.modified_author = $author
                RETURN properties(c) AS comment
                """,
                topic_guid=topic_guid,
                guid=guid,
                text=text,
                viewpoint_guid=viewpoint_guid,
                new_reply=new_reply,
                now=now,
                author=author,
            )
            if row is None:
                return None
            old = before["comment"]
            actions = []
            if (old.get("comment") or "") != text:
                actions.append(events.Action("comment_text_updated", text[:TEXT_EVENT_LIMIT]))
            if old.get("viewpoint_guid") != viewpoint_guid:
                if viewpoint_guid is None:
                    actions.append(events.Action("viewpoint_removed"))
                else:
                    actions.append(events.Action("viewpoint_updated", viewpoint_guid))
            if old_reply != new_reply:
                if new_reply is None:
                    actions.append(events.Action("reply_to_comment_removed"))
                else:
                    actions.append(events.Action("reply_to_comment_updated", new_reply))
            await events.record(
                tx,
                project_id=project_id,
                topic_guid=topic_guid,
                author=author,
                actions=actions,
                comment_guid=guid,
                date=now,
            )
            await self.topics.touch(tx, guid=topic_guid, author=author, now=now)
            return row["comment"]

        result = await self.graph.write(work)
        return to_model(result) if result else None

    async def delete(self, *, project_id: str, topic_guid: str, guid: str, author: str) -> bool:
        """Delete the comment. A comment that replied to it stops being a reply, and says so in its events."""

        async def work(tx: Tx) -> bool:
            replies = await tx.run(
                """
                MATCH (:Topic {guid: $topic_guid})-[:HAS_COMMENT]->(c:Comment {reply_to_comment_guid: $guid})
                SET c.reply_to_comment_guid = null
                RETURN c.guid AS guid
                """,
                topic_guid=topic_guid,
                guid=guid,
            )
            for row in replies:
                await events.record(
                    tx,
                    project_id=project_id,
                    topic_guid=topic_guid,
                    author=author,
                    actions=[events.Action("reply_to_comment_removed")],
                    comment_guid=row["guid"],
                )
            counters = await tx.counters(
                "MATCH (:Topic {guid: $topic_guid})-[:HAS_COMMENT]->(c:Comment {guid: $guid}) DETACH DELETE c",
                topic_guid=topic_guid,
                guid=guid,
            )
            return counters.nodes_deleted > 0

        return await self.graph.write(work)


def comment_repository(graph: GraphDep, topics: TopicsDep) -> CommentRepository:
    return CommentRepository(graph, topics)


CommentsDep = Annotated[CommentRepository, Depends(comment_repository)]
