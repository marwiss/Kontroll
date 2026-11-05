# This file was generated with the assistance of an AI coding tool.
"""Comments (BCF API 3.4) and their events (3.10).

A ``Comment`` hangs off its topic. It may point at one of the topic's
viewpoints through ``viewpoint_guid``; a comment with a viewpoint and no text
is allowed (3.4.2). Creating or editing a comment moves the topic's
``modified_date`` (3.2.1) and records comment events in the same transaction.
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


class CommentRepository:
    def __init__(self, graph: Graph, topics: TopicRepository) -> None:
        self.graph = graph
        self.topics = topics

    async def search(self, *, user_id: str, project_id: str, topic_guid: str, compiled: Compiled) -> list[CommentGET]:
        rows = await self.graph.run(
            f"""
            MATCH (:User {{id: $user_id}})-[:MEMBER_OF]->(:Project {{project_id: $project_id}})
                  -[:HAS_TOPIC]->(:Topic {{guid: $topic_guid}})-[:HAS_COMMENT]->(c:Comment)
            WHERE true {compiled.where_clause()}
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

    async def create(self, *, project_id: str, topic_guid: str, author: str, body: CommentPOST) -> CommentGET:
        if body.guid and not is_uuid(body.guid):
            raise HTTPException(400, "guid must be a UUID")
        guid = normalize_guid(body.guid) if body.guid else new_id()
        text = _text(body)
        viewpoint_guid = _viewpoint_guid(body)
        now = now_iso()

        async def work(tx: Tx) -> dict[str, Any]:
            if await tx.one("MATCH (c:Comment {guid: $guid}) RETURN c.guid AS guid", guid=guid):
                raise HTTPException(409, "A comment with this guid already exists")  # Foundation API 1.5.1
            await self._check_viewpoint(tx, topic_guid, viewpoint_guid)
            row = await tx.one(
                """
                MATCH (:Project {project_id: $project_id})-[:HAS_TOPIC]->(t:Topic {guid: $topic_guid}),
                      (u:User {username: $author})
                CREATE (t)-[:HAS_COMMENT]->(c:Comment {
                    guid: $guid, topic_guid: $topic_guid, date: $now, author: $author, comment: $text,
                    viewpoint_guid: $viewpoint_guid, modified_date: $now, modified_author: $author
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
            )
            if row is None:
                raise HTTPException(404, "Topic not found")
            # BCF 3.10: creation also yields "update" events for the fields that are initially set.
            actions = [events.Action("comment_created")]
            if text:
                actions.append(events.Action("comment_text_updated", text[:TEXT_EVENT_LIMIT]))
            if viewpoint_guid:
                actions.append(events.Action("viewpoint_updated", viewpoint_guid))
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
        self, *, project_id: str, topic_guid: str, guid: str, author: str, body: CommentPUT
    ) -> CommentGET | None:
        text = _text(body)
        viewpoint_guid = _viewpoint_guid(body)
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
            row = await tx.one(
                """
                MATCH (:Topic {guid: $topic_guid})-[:HAS_COMMENT]->(c:Comment {guid: $guid})
                SET c.comment = $text, c.viewpoint_guid = $viewpoint_guid, c.modified_date = $now, c.modified_author = $author
                RETURN properties(c) AS comment
                """,
                topic_guid=topic_guid,
                guid=guid,
                text=text,
                viewpoint_guid=viewpoint_guid,
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

    async def delete(self, *, topic_guid: str, guid: str) -> bool:
        counters = await self.graph.write(
            lambda tx: tx.counters(
                "MATCH (:Topic {guid: $topic_guid})-[:HAS_COMMENT]->(c:Comment {guid: $guid}) DETACH DELETE c",
                topic_guid=topic_guid,
                guid=guid,
            )
        )
        return counters.nodes_deleted > 0


def comment_repository(graph: GraphDep, topics: TopicsDep) -> CommentRepository:
    return CommentRepository(graph, topics)


CommentsDep = Annotated[CommentRepository, Depends(comment_repository)]
