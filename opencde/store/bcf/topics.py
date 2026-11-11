# This file was generated with the assistance of an AI coding tool.
"""Topics (BCF API 3.2): the issues of a project.

A ``Topic`` node hangs off its project (``HAS_TOPIC``) and points at its
creator. Values that the project's extensions constrain (type, status,
priority, labels, stage, assigned user) are checked on every write, so a
client can rely on what ``GET /extensions`` told it. Every write also records
the events of BCF 3.9 in the same transaction.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from opencde.bcf import events
from opencde.bcf.schemas import BimSnippet, TopicFields, TopicGET, TopicPOST, TopicPUT
from opencde.graph.graph import Graph, Tx
from opencde.ids import is_uuid, new_id, normalize_guid
from opencde.odata import Compiled, Field
from opencde.timeutil import now_iso

TOPIC_FIELDS = {
    "title": Field("t.title", "string"),
    "creation_author": Field("t.creation_author", "string"),
    "modified_author": Field("t.modified_author", "string"),
    "assigned_to": Field("t.assigned_to", "string"),
    "stage": Field("t.stage", "string"),
    "topic_status": Field("t.topic_status", "string"),
    "topic_type": Field("t.topic_type", "string"),
    "priority": Field("t.priority", "string"),
    "server_assigned_id": Field("t.server_assigned_id", "string"),
    "creation_date": Field("t.creation_date", "datetime"),
    "modified_date": Field("t.modified_date", "datetime"),
    "due_date": Field("t.due_date", "datetime"),
    "index": Field("t.index", "integer"),
    "labels": Field("t.labels", "string_list"),
}
TOPIC_ORDERABLE = ("creation_date", "modified_date", "server_assigned_id", "index")
TOPIC_DEFAULT_ORDER = "t.creation_date ASC, t.server_assigned_id ASC"

# Properties stored on the node, in the order the schema lists them.
STORED = (
    "topic_type",
    "topic_status",
    "reference_links",
    "title",
    "priority",
    "index",
    "labels",
    "assigned_to",
    "stage",
    "description",
    "due_date",
    "snippet_type",
    "snippet_is_external",
    "snippet_reference",
    "snippet_reference_schema",
)


def _flatten(fields: TopicFields) -> dict[str, Any]:
    """Topic fields as node properties (the BIM snippet object becomes four properties)."""
    data = fields.model_dump(exclude={"guid", "bim_snippet"})
    snippet = fields.bim_snippet
    data.update(
        snippet_type=snippet.snippet_type if snippet else None,
        snippet_is_external=snippet.is_external if snippet else None,
        snippet_reference=snippet.reference if snippet else None,
        snippet_reference_schema=snippet.reference_schema if snippet else None,
    )
    return data


def to_model(node: dict[str, Any]) -> TopicGET:
    snippet = None
    if node.get("snippet_type"):
        snippet = BimSnippet(
            snippet_type=node["snippet_type"],
            is_external=bool(node.get("snippet_is_external")),
            reference=node.get("snippet_reference") or "",
            reference_schema=node.get("snippet_reference_schema") or "",
        )
    return TopicGET(
        guid=node["guid"],
        server_assigned_id=node["server_assigned_id"],
        topic_type=node.get("topic_type"),
        topic_status=node.get("topic_status"),
        reference_links=node.get("reference_links"),
        title=node["title"],
        priority=node.get("priority"),
        index=node.get("index"),
        labels=node.get("labels"),
        creation_date=node["creation_date"],
        creation_author=node["creation_author"],
        modified_date=node.get("modified_date"),
        modified_author=node.get("modified_author"),
        assigned_to=node.get("assigned_to"),
        stage=node.get("stage"),
        description=node.get("description"),
        bim_snippet=snippet,
        due_date=node.get("due_date"),
    )


def validate_against_extensions(fields: TopicFields, extensions: dict[str, list[str]]) -> None:
    """400 when a value is not one the project's extensions allow (BCF 3.1.4)."""
    problems = []
    for name, allowed_key in (
        ("topic_type", "topic_type"),
        ("topic_status", "topic_status"),
        ("priority", "priority"),
        ("stage", "stage"),
        ("assigned_to", "users"),
    ):
        value = getattr(fields, name)
        allowed = extensions.get(allowed_key) or []
        if value is not None and value not in allowed:
            problems.append(f"{name} '{value}' is not one of the project's values")
    if fields.labels:
        unknown = [label for label in fields.labels if label not in (extensions.get("topic_label") or [])]
        if unknown:
            problems.append(f"labels not defined for the project: {', '.join(unknown)}")
    if fields.bim_snippet and fields.bim_snippet.snippet_type not in (extensions.get("snippet_type") or []):
        problems.append(f"snippet_type '{fields.bim_snippet.snippet_type}' is not one of the project's values")
    if problems:
        raise HTTPException(400, "; ".join(problems))


class TopicRepository:
    def __init__(self, graph: Graph, *, id_prefix: str = "ISSUE-") -> None:
        self.graph = graph
        self.id_prefix = id_prefix

    @staticmethod
    def _matching(compiled: Compiled) -> str:
        return f"""
            MATCH (:User {{id: $user_id}})-[:MEMBER_OF]->(p:Project {{project_id: $project_id}})-[:HAS_TOPIC]->(t:Topic)
            WHERE true {compiled.where_clause()}
            """

    async def count(self, *, user_id: str, project_id: str, compiled: Compiled) -> int:
        """How many topics the options match, before ``$top`` and ``$skip``."""
        row = await self.graph.one(
            self._matching(compiled) + "RETURN count(t) AS total",
            user_id=user_id,
            project_id=project_id,
            **compiled.params,
        )
        return int(row["total"]) if row else 0

    async def search(self, *, user_id: str, project_id: str, compiled: Compiled) -> list[TopicGET]:
        rows = await self.graph.run(
            self._matching(compiled)
            + f"""
            RETURN properties(t) AS topic
            ORDER BY {compiled.order_by}
            SKIP $skip LIMIT $limit
            """,
            user_id=user_id,
            project_id=project_id,
            skip=compiled.skip,
            limit=compiled.limit,
            **compiled.params,
        )
        return [to_model(row["topic"]) for row in rows]

    async def get(self, *, user_id: str, project_id: str, guid: str) -> TopicGET | None:
        row = await self.graph.one(
            """
            MATCH (:User {id: $user_id})-[:MEMBER_OF]->(:Project {project_id: $project_id})-[:HAS_TOPIC]->(t:Topic {guid: $guid})
            RETURN properties(t) AS topic
            """,
            user_id=user_id,
            project_id=project_id,
            guid=guid,
        )
        return to_model(row["topic"]) if row else None

    async def exists(self, guid: str) -> bool:
        row = await self.graph.one("MATCH (t:Topic {guid: $guid}) RETURN count(t) AS n", guid=guid)
        return bool(row and row["n"])

    async def create(self, *, project_id: str, author: str, body: TopicPOST) -> TopicGET:
        if body.guid and not is_uuid(body.guid):
            raise HTTPException(400, "guid must be a UUID")
        guid = normalize_guid(body.guid) if body.guid else new_id()
        now = now_iso()
        data = _flatten(body)

        async def work(tx: Tx) -> dict[str, Any]:
            if await tx.one("MATCH (t:Topic {guid: $guid}) RETURN t.guid AS g", guid=guid):
                raise HTTPException(409, "A topic with this guid already exists")  # Foundation API 1.5.1
            counter = await tx.one(
                """
                MATCH (p:Project {project_id: $project_id})
                SET p.topic_counter = coalesce(p.topic_counter, 0) + 1
                RETURN p.topic_counter AS n
                """,
                project_id=project_id,
            )
            if counter is None:
                raise HTTPException(404, "Project not found")
            server_assigned_id = f"{self.id_prefix}{int(counter['n']):04d}"
            row = await tx.one(
                """
                MATCH (p:Project {project_id: $project_id}), (u:User {username: $author})
                CREATE (p)-[:HAS_TOPIC]->(t:Topic {
                    guid: $guid, server_assigned_id: $server_assigned_id,
                    creation_date: $now, creation_author: $author, modified_date: $now, modified_author: $author,
                    topic_type: $topic_type, topic_status: $topic_status, reference_links: $reference_links,
                    title: $title, priority: $priority, index: $index, labels: $labels, assigned_to: $assigned_to,
                    stage: $stage, description: $description, due_date: $due_date,
                    snippet_type: $snippet_type, snippet_is_external: $snippet_is_external,
                    snippet_reference: $snippet_reference, snippet_reference_schema: $snippet_reference_schema
                })
                CREATE (t)-[:CREATED_BY]->(u)
                RETURN properties(t) AS topic
                """,
                project_id=project_id,
                author=author,
                guid=guid,
                server_assigned_id=server_assigned_id,
                now=now,
                **data,
            )
            if row is None:
                raise HTTPException(404, "Project not found")
            # BCF 3.9: creation also yields "update" and "add" events for the fields that are initially set.
            actions = [events.Action("topic_created"), *events.topic_diff({}, row["topic"])]
            await events.record(tx, project_id=project_id, topic_guid=guid, author=author, actions=actions, date=now)
            return row["topic"]

        return to_model(await self.graph.write(work))

    async def update(self, *, project_id: str, guid: str, author: str, body: TopicPUT) -> TopicGET | None:
        """Replace the topic as a whole (Foundation API 1.3) and record what changed."""
        now = now_iso()
        data = _flatten(body)
        assignments = ", ".join(f"t.{name} = ${name}" for name in STORED)

        async def work(tx: Tx) -> dict[str, Any] | None:
            before = await tx.one(
                "MATCH (:Project {project_id: $project_id})-[:HAS_TOPIC]->(t:Topic {guid: $guid}) RETURN properties(t) AS topic",
                project_id=project_id,
                guid=guid,
            )
            if before is None:
                return None
            row = await tx.one(
                f"""
                MATCH (:Project {{project_id: $project_id}})-[:HAS_TOPIC]->(t:Topic {{guid: $guid}})
                SET {assignments}, t.modified_date = $now, t.modified_author = $author
                RETURN properties(t) AS topic
                """,
                project_id=project_id,
                guid=guid,
                now=now,
                author=author,
                **data,
            )
            if row is None:
                return None
            actions = events.topic_diff(before["topic"], row["topic"])
            await events.record(tx, project_id=project_id, topic_guid=guid, author=author, actions=actions, date=now)
            return row["topic"]

        result = await self.graph.write(work)
        return to_model(result) if result else None

    async def touch(self, tx: Tx, *, guid: str, author: str, now: str | None = None) -> None:
        """Bump ``modified_date`` (a comment or a floating viewpoint changed the topic, BCF 3.2.1)."""
        await tx.run(
            "MATCH (t:Topic {guid: $guid}) SET t.modified_date = $now, t.modified_author = $author",
            guid=guid,
            now=now or now_iso(),
            author=author,
        )

    async def delete(self, *, project_id: str, guid: str) -> list[str]:
        """Delete the topic with its comments, viewpoints and references. Returns storage keys to remove."""

        async def work(tx: Tx) -> list[str] | None:
            rows = await tx.run(
                """
                MATCH (:Project {project_id: $project_id})-[:HAS_TOPIC]->(t:Topic {guid: $guid})
                OPTIONAL MATCH (t)-[:HAS_COMMENT|HAS_VIEWPOINT|HAS_FILE|HAS_DOCUMENT_REFERENCE|HAS_PROPOSAL]->(child)
                OPTIONAL MATCH (child)-[:HAS_COMPONENT|HAS_LINE|HAS_CLIPPING_PLANE|HAS_BITMAP]->(grandchild)
                WITH t, collect(DISTINCT child) AS children, collect(DISTINCT grandchild) AS grandchildren
                RETURN [n IN children + grandchildren WHERE n.storage_key IS NOT NULL | n.storage_key]
                       + CASE WHEN t.snippet_storage_key IS NOT NULL THEN [t.snippet_storage_key] ELSE [] END AS keys
                """,
                project_id=project_id,
                guid=guid,
            )
            if not rows:
                return None
            await tx.run(
                """
                MATCH (:Project {project_id: $project_id})-[:HAS_TOPIC]->(t:Topic {guid: $guid})
                OPTIONAL MATCH (t)-[:HAS_COMMENT|HAS_VIEWPOINT|HAS_FILE|HAS_DOCUMENT_REFERENCE|HAS_PROPOSAL]->(child)
                OPTIONAL MATCH (child)-[:HAS_COMPONENT|HAS_LINE|HAS_CLIPPING_PLANE|HAS_BITMAP]->(grandchild)
                DETACH DELETE grandchild, child, t
                """,
                project_id=project_id,
                guid=guid,
            )
            return list(rows[0]["keys"] or [])

        keys = await self.graph.write(work)
        if keys is None:
            raise HTTPException(404, "Topic not found")
        return keys
