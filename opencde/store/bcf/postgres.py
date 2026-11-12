# This file was generated with the assistance of an AI coding tool.
"""The BCF area in PostgreSQL (ADR 0029): topics and their links, comments, viewpoints, BCF documents and events.

The same protocols as the graph's repositories (``opencde.store.protocols``), over the tables of
``opencde/postgres/migrations/0004_bcf.sql``, with the same rules, answers and events. A member's read joins
``memberships`` on the user's id, as the graph's statements start at the user and follow ``MEMBER_OF``; a write is
made for a project the route has already let the caller into, as in the graph. Foreign keys delete what a topic, a
viewpoint or a project owns. Every statement is one string literal with numbered parameters; a list's filter and
order come from the OData compiler's whitelist (``Compiled.sql``), and their values are arguments too. A ``dict`` that
the graph answers with a node's properties leaves out what is null, as ``properties()`` does.

The ``*_store`` functions choose between the two: PostgreSQL when ``OPENCDE_STORE_URL`` names it, the graph
otherwise.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from fastapi import HTTPException

from opencde.bcf import events
from opencde.bcf.events import _row_to_event
from opencde.bcf.images import decode_image
from opencde.bcf.schemas import (
    Coloring,
    CommentGET,
    CommentPOST,
    CommentPUT,
    Component,
    DocumentGET,
    DocumentReferenceFields,
    DocumentReferenceGET,
    DocumentReferencePOST,
    DocumentReferencePUT,
    FileRef,
    OrthogonalCamera,
    PerspectiveCamera,
    ProjectFileInformation,
    TopicGET,
    TopicPOST,
    TopicPUT,
    ViewpointPOST,
    ViewSetupHints,
    Visibility,
)
from opencde.ids import is_uuid, new_id, normalize_guid
from opencde.storage import LocalStorage, make_key
from opencde.store.bcf import comments as graph_comments
from opencde.store.bcf.comments import TEXT_EVENT_LIMIT, _reply_guid, _text, _viewpoint_guid
from opencde.store.bcf.documents import BcfDocumentRepository, _entry
from opencde.store.bcf.events import BcfEventRepository
from opencde.store.bcf.topic_links import TopicLinkRepository, _file, _reference
from opencde.store.bcf.topics import TopicRepository, _flatten, to_model
from opencde.store.bcf.viewpoints import (
    BATCH,
    ROLE_COLORING,
    ROLE_EXCEPTION,
    ROLE_SELECTION,
    ViewpointRecord,
    ViewpointRepository,
    _component,
    _component_rows,
    to_record,
)
from opencde.timeutil import now_iso

if TYPE_CHECKING:
    from opencde.graph.graph import Graph
    from opencde.odata import Compiled
    from opencde.postgres.database import Postgres, Tx
    from opencde.store.protocols import (
        BcfDocumentStore,
        BcfEventStore,
        CommentStore,
        TopicLinkStore,
        TopicStore,
        ViewpointStore,
    )


def _properties(row: dict[str, Any]) -> dict[str, Any]:
    """A row as the graph gives a node's properties: without what is null."""
    return {key: value for key, value in row.items() if value is not None}


# -- events (BCF 3.9, 3.10) --------------------------------------------------------------------------------------

EVENT_INSERT = """
INSERT INTO bcf_events (id, project_id, kind, topic_guid, comment_guid, author, date, action_types, action_values)
SELECT $1, p.project_id, $3, $4, $5, $6, $7, $8, $9 FROM projects p WHERE p.project_id = $2
"""
EVENTS_COUNT = """
SELECT count(*) AS total
FROM bcf_events e JOIN memberships m ON m.project_id = e.project_id AND m.user_id = $1
WHERE e.project_id = $2 AND e.kind = $3
  AND ($4::text IS NULL OR e.topic_guid = $4) AND ($5::text IS NULL OR e.comment_guid = $5)
  AND EXISTS (SELECT 1 FROM unnest(e.action_types) AS a (type) WHERE NOT a.type = ANY($6::text[]))
  AND $filter
"""
EVENTS = """
SELECT e.topic_guid, e.comment_guid, e.author, e.date, e.action_types, e.action_values
FROM bcf_events e JOIN memberships m ON m.project_id = e.project_id AND m.user_id = $1
WHERE e.project_id = $2 AND e.kind = $3
  AND ($4::text IS NULL OR e.topic_guid = $4) AND ($5::text IS NULL OR e.comment_guid = $5)
  AND EXISTS (SELECT 1 FROM unnest(e.action_types) AS a (type) WHERE NOT a.type = ANY($6::text[]))
  AND $filter
ORDER BY $orderby
OFFSET $7 LIMIT $8
"""


async def record(
    tx: Tx,
    *,
    project_id: str,
    topic_guid: str,
    author: str,
    actions: list[events.Action],
    comment_guid: str | None = None,
    date: str | None = None,
) -> None:
    """``opencde.bcf.events.record`` in PostgreSQL: one event with its actions, inside the caller's transaction."""
    if not actions:
        return
    await tx.execute(
        EVENT_INSERT,
        new_id(),
        project_id,
        "comment" if comment_guid else "topic",
        topic_guid,
        comment_guid,
        author,
        date or now_iso(),
        [action.type for action in actions],
        [action.value if action.value is not None else "" for action in actions],
    )


class PostgresBcfEventRepository:
    def __init__(self, postgres: Postgres) -> None:
        self.postgres = postgres

    async def count(
        self,
        *,
        user_id: str,
        project_id: str,
        kind: str,
        compiled: Compiled,
        topic_guid: str | None = None,
        comment_guid: str | None = None,
        left_out: frozenset[str] = frozenset(),
    ) -> int:
        """How many events the options match, before ``$top`` and ``$skip``."""
        row = await self.postgres.one(
            compiled.sql(EVENTS_COUNT),
            user_id,
            project_id,
            kind,
            topic_guid,
            comment_guid,
            sorted(left_out),
            *compiled.sql_params,
        )
        return int(row["total"]) if row else 0

    async def query(
        self,
        *,
        user_id: str,
        project_id: str,
        kind: str,
        compiled: Compiled,
        topic_guid: str | None = None,
        comment_guid: str | None = None,
        left_out: frozenset[str] = frozenset(),
    ) -> list[dict[str, Any]]:
        """Events of a project (optionally one topic or comment) without the actions of ``left_out``, and without
        the events that then have none left."""
        rows = await self.postgres.run(
            compiled.sql(EVENTS),
            user_id,
            project_id,
            kind,
            topic_guid,
            comment_guid,
            sorted(left_out),
            compiled.skip,
            compiled.limit,
            *compiled.sql_params,
        )
        return [_row_to_event({"event": row}, left_out) for row in rows]


# -- topics (BCF 3.2) --------------------------------------------------------------------------------------------

TOPICS_COUNT = """
SELECT count(*) AS total
FROM topics t JOIN memberships m ON m.project_id = t.project_id AND m.user_id = $1
WHERE t.project_id = $2 AND $filter
"""
TOPICS = """
SELECT t.*
FROM topics t JOIN memberships m ON m.project_id = t.project_id AND m.user_id = $1
WHERE t.project_id = $2 AND $filter
ORDER BY $orderby
OFFSET $3 LIMIT $4
"""
TOPIC = """
SELECT t.*
FROM topics t JOIN memberships m ON m.project_id = t.project_id AND m.user_id = $1
WHERE t.project_id = $2 AND t.guid = $3
"""
TOPIC_COUNTER = """
UPDATE projects SET topic_counter = topic_counter + 1 WHERE project_id = $1 RETURNING topic_counter AS n
"""
TOPIC_INSERT = """
INSERT INTO topics AS t (
    guid, project_id, server_assigned_id, creation_date, creation_author, modified_date, modified_author,
    topic_type, topic_status, reference_links, title, priority, "index", labels, assigned_to, stage, description,
    due_date, snippet_type, snippet_is_external, snippet_reference, snippet_reference_schema
)
SELECT $1, p.project_id, $3, $4, $5, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20
FROM projects p JOIN users u ON u.username = $5
WHERE p.project_id = $2
RETURNING t.*
"""
TOPIC_LOCKED = "SELECT t.* FROM topics t WHERE t.project_id = $1 AND t.guid = $2 FOR UPDATE"
TOPIC_UPDATE = """
UPDATE topics t
SET topic_type = $3, topic_status = $4, reference_links = $5, title = $6, priority = $7, "index" = $8, labels = $9,
    assigned_to = $10, stage = $11, description = $12, due_date = $13, snippet_type = $14,
    snippet_is_external = $15, snippet_reference = $16, snippet_reference_schema = $17,
    modified_date = $18, modified_author = $19
WHERE t.project_id = $1 AND t.guid = $2
RETURNING t.*
"""
TOPIC_TOUCH = "UPDATE topics SET modified_date = $2, modified_author = $3 WHERE guid = $1"
TOPIC_FILES = """
SELECT v.storage_key FROM viewpoints v WHERE v.topic_guid = $1 AND v.storage_key IS NOT NULL
UNION ALL
SELECT b.storage_key FROM bitmaps b JOIN viewpoints v ON v.guid = b.viewpoint_guid WHERE v.topic_guid = $1
UNION ALL
SELECT f.storage_key FROM proposal_files f WHERE f.topic_guid = $1 AND f.storage_key IS NOT NULL
UNION ALL
SELECT t.snippet_storage_key FROM topics t WHERE t.guid = $1 AND t.snippet_storage_key IS NOT NULL
"""


def _topic_values(fields: dict[str, Any]) -> tuple[Any, ...]:
    """The stored fields in the order of the statements' parameters."""
    return tuple(
        fields[name]
        for name in (
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
    )


async def _touch(tx: Tx, guid: str, author: str, now: str | None = None) -> None:
    await tx.execute(TOPIC_TOUCH, guid, now or now_iso(), author)


class PostgresTopicRepository:
    def __init__(self, postgres: Postgres, *, id_prefix: str = "ISSUE-") -> None:
        self.postgres = postgres
        self.id_prefix = id_prefix

    async def count(self, *, user_id: str, project_id: str, compiled: Compiled) -> int:
        """How many topics the options match, before ``$top`` and ``$skip``."""
        row = await self.postgres.one(compiled.sql(TOPICS_COUNT), user_id, project_id, *compiled.sql_params)
        return int(row["total"]) if row else 0

    async def search(self, *, user_id: str, project_id: str, compiled: Compiled) -> list[TopicGET]:
        rows = await self.postgres.run(
            compiled.sql(TOPICS), user_id, project_id, compiled.skip, compiled.limit, *compiled.sql_params
        )
        return [to_model(row) for row in rows]

    async def get(self, *, user_id: str, project_id: str, guid: str) -> TopicGET | None:
        row = await self.postgres.one(TOPIC, user_id, project_id, guid)
        return to_model(row) if row else None

    async def exists(self, guid: str) -> bool:
        return await self.postgres.one("SELECT 1 AS n FROM topics WHERE guid = $1", guid) is not None

    async def create(self, *, project_id: str, author: str, body: TopicPOST) -> TopicGET:
        if body.guid and not is_uuid(body.guid):
            raise HTTPException(400, "guid must be a UUID")
        guid = normalize_guid(body.guid) if body.guid else new_id()
        now = now_iso()
        values = _topic_values(_flatten(body))

        async def work(tx: Tx) -> dict[str, Any]:
            if await tx.one("SELECT 1 AS n FROM topics WHERE guid = $1", guid):
                raise HTTPException(409, "A topic with this guid already exists")  # Foundation API 1.5.1
            counter = await tx.one(TOPIC_COUNTER, project_id)
            if counter is None:
                raise HTTPException(404, "Project not found")
            server_assigned_id = f"{self.id_prefix}{int(counter['n']):04d}"
            row = await tx.one(TOPIC_INSERT, guid, project_id, server_assigned_id, now, author, *values)
            if row is None:
                raise HTTPException(404, "Project not found")
            # BCF 3.9: creation also yields "update" and "add" events for the fields that are initially set.
            actions = [events.Action("topic_created"), *events.topic_diff({}, row)]
            await record(tx, project_id=project_id, topic_guid=guid, author=author, actions=actions, date=now)
            return row

        return to_model(await self.postgres.write(work))

    async def update(self, *, project_id: str, guid: str, author: str, body: TopicPUT) -> TopicGET | None:
        """Replace the topic as a whole (Foundation API 1.3) and record what changed."""
        now = now_iso()
        values = _topic_values(_flatten(body))

        async def work(tx: Tx) -> dict[str, Any] | None:
            before = await tx.one(TOPIC_LOCKED, project_id, guid)
            if before is None:
                return None
            row = await tx.one(TOPIC_UPDATE, project_id, guid, *values, now, author)
            if row is None:
                return None
            actions = events.topic_diff(before, row)
            await record(tx, project_id=project_id, topic_guid=guid, author=author, actions=actions, date=now)
            return row

        result = await self.postgres.write(work)
        return to_model(result) if result else None

    async def touch(self, tx: Tx, *, guid: str, author: str, now: str | None = None) -> None:
        """Bump ``modified_date`` (a comment or a floating viewpoint changed the topic, BCF 3.2.1)."""
        await _touch(tx, guid, author, now)

    async def delete(self, *, project_id: str, guid: str) -> list[str]:
        """Delete the topic with its comments, viewpoints and references. Returns storage keys to remove."""

        async def work(tx: Tx) -> list[str] | None:
            if await tx.one(TOPIC_LOCKED, project_id, guid) is None:
                return None
            keys = [row["storage_key"] for row in await tx.run(TOPIC_FILES, guid)]
            await tx.execute("DELETE FROM topics WHERE project_id = $1 AND guid = $2", project_id, guid)
            return keys

        keys = await self.postgres.write(work)
        if keys is None:
            raise HTTPException(404, "Topic not found")
        return keys


# -- comments (BCF 3.4) ------------------------------------------------------------------------------------------

COMMENTS_COUNT = """
SELECT count(*) AS total
FROM comments c
JOIN topics t ON t.guid = c.topic_guid
JOIN memberships m ON m.project_id = t.project_id AND m.user_id = $1
WHERE t.project_id = $2 AND c.topic_guid = $3 AND $filter
"""
COMMENTS = """
SELECT c.*
FROM comments c
JOIN topics t ON t.guid = c.topic_guid
JOIN memberships m ON m.project_id = t.project_id AND m.user_id = $1
WHERE t.project_id = $2 AND c.topic_guid = $3 AND $filter
ORDER BY $orderby
OFFSET $4 LIMIT $5
"""
COMMENT = """
SELECT c.*
FROM comments c
JOIN topics t ON t.guid = c.topic_guid
JOIN memberships m ON m.project_id = t.project_id AND m.user_id = $1
WHERE t.project_id = $2 AND c.topic_guid = $3 AND c.guid = $4
"""
COMMENT_INSERT = """
INSERT INTO comments AS c (
    guid, topic_guid, date, author, comment, viewpoint_guid, reply_to_comment_guid, modified_date, modified_author
)
SELECT $1, t.guid, $4, $5, $6, $7, $8, $4, $5
FROM topics t JOIN users u ON u.username = $5
WHERE t.project_id = $2 AND t.guid = $3
RETURNING c.*
"""
COMMENT_LOCKED = "SELECT c.* FROM comments c WHERE c.topic_guid = $1 AND c.guid = $2 FOR UPDATE"
COMMENT_UPDATE = """
UPDATE comments c
SET comment = $3, viewpoint_guid = $4, reply_to_comment_guid = $5, modified_date = $6, modified_author = $7
WHERE c.topic_guid = $1 AND c.guid = $2
RETURNING c.*
"""
COMMENT_OF_TOPIC = "SELECT c.guid FROM comments c WHERE c.topic_guid = $1 AND c.guid = $2"
VIEWPOINT_OF_TOPIC = "SELECT v.guid FROM viewpoints v WHERE v.topic_guid = $1 AND v.guid = $2"
REPLIES_UNDONE = """
UPDATE comments c SET reply_to_comment_guid = NULL
WHERE c.topic_guid = $1 AND c.reply_to_comment_guid = $2
RETURNING c.guid
"""


class PostgresCommentRepository:
    def __init__(self, postgres: Postgres) -> None:
        self.postgres = postgres

    async def count(self, *, user_id: str, project_id: str, topic_guid: str, compiled: Compiled) -> int:
        """How many comments of the topic the options match, before ``$top`` and ``$skip``."""
        row = await self.postgres.one(
            compiled.sql(COMMENTS_COUNT), user_id, project_id, topic_guid, *compiled.sql_params
        )
        return int(row["total"]) if row else 0

    async def search(self, *, user_id: str, project_id: str, topic_guid: str, compiled: Compiled) -> list[CommentGET]:
        rows = await self.postgres.run(
            compiled.sql(COMMENTS),
            user_id,
            project_id,
            topic_guid,
            compiled.skip,
            compiled.limit,
            *compiled.sql_params,
        )
        return [graph_comments.to_model(row) for row in rows]

    async def get(self, *, user_id: str, project_id: str, topic_guid: str, guid: str) -> CommentGET | None:
        row = await self.postgres.one(COMMENT, user_id, project_id, topic_guid, guid)
        return graph_comments.to_model(row) if row else None

    @staticmethod
    async def _check_viewpoint(tx: Tx, topic_guid: str, viewpoint_guid: str | None) -> None:
        if viewpoint_guid is None:
            return
        if await tx.one(VIEWPOINT_OF_TOPIC, topic_guid, viewpoint_guid) is None:
            raise HTTPException(400, "viewpoint_guid is not a viewpoint of this topic")

    @staticmethod
    async def _check_reply(tx: Tx, topic_guid: str, reply_to: str | None, guid: str) -> None:
        if reply_to is None:
            return
        if reply_to == guid:
            raise HTTPException(400, "a comment cannot reply to itself")
        if await tx.one(COMMENT_OF_TOPIC, topic_guid, reply_to) is None:
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
            if await tx.one("SELECT 1 AS n FROM comments WHERE guid = $1", guid):
                raise HTTPException(409, "A comment with this guid already exists")  # Foundation API 1.5.1
            await self._check_viewpoint(tx, topic_guid, viewpoint_guid)
            await self._check_reply(tx, topic_guid, reply_guid, guid)
            row = await tx.one(
                COMMENT_INSERT, guid, project_id, topic_guid, now, author, text, viewpoint_guid, reply_guid
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
            await record(
                tx,
                project_id=project_id,
                topic_guid=topic_guid,
                author=author,
                actions=actions,
                comment_guid=guid,
                date=now,
            )
            await _touch(tx, topic_guid, author, now)
            return row

        return graph_comments.to_model(await self.postgres.write(work))

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
            old = await tx.one(COMMENT_LOCKED, topic_guid, guid)
            if old is None:
                return None
            await self._check_viewpoint(tx, topic_guid, viewpoint_guid)
            old_reply = old.get("reply_to_comment_guid")
            new_reply = reply_guid if change_reply else old_reply
            await self._check_reply(tx, topic_guid, new_reply, guid)
            row = await tx.one(COMMENT_UPDATE, topic_guid, guid, text, viewpoint_guid, new_reply, now, author)
            if row is None:
                return None
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
            await record(
                tx,
                project_id=project_id,
                topic_guid=topic_guid,
                author=author,
                actions=actions,
                comment_guid=guid,
                date=now,
            )
            await _touch(tx, topic_guid, author, now)
            return row

        result = await self.postgres.write(work)
        return graph_comments.to_model(result) if result else None

    async def delete(self, *, project_id: str, topic_guid: str, guid: str, author: str) -> bool:
        """Delete the comment. A comment that replied to it stops being a reply, and says so in its events."""

        async def work(tx: Tx) -> bool:
            for row in await tx.run(REPLIES_UNDONE, topic_guid, guid):
                await record(
                    tx,
                    project_id=project_id,
                    topic_guid=topic_guid,
                    author=author,
                    actions=[events.Action("reply_to_comment_removed")],
                    comment_guid=row["guid"],
                )
            deleted = await tx.execute("DELETE FROM comments WHERE topic_guid = $1 AND guid = $2", topic_guid, guid)
            return deleted > 0

        return await self.postgres.write(work)


# -- viewpoints (BCF 3.5) ----------------------------------------------------------------------------------------

VIEWPOINTS = """
SELECT v.guid, v."index", v.author, v.creation_date, v.camera_kind, v.camera, v.lines, v.clipping_planes,
       v.snapshot_type, v.storage_key,
       coalesce((SELECT json_agg(b ORDER BY b.position) FROM bitmaps b WHERE b.viewpoint_guid = v.guid), '[]') AS bitmaps
FROM viewpoints v
JOIN topics t ON t.guid = v.topic_guid
JOIN memberships m ON m.project_id = t.project_id AND m.user_id = $1
WHERE t.project_id = $2 AND v.topic_guid = $3
ORDER BY v.creation_date, v.guid COLLATE "C"
"""
VIEWPOINT = """
SELECT v.guid, v."index", v.author, v.creation_date, v.camera_kind, v.camera, v.lines, v.clipping_planes,
       v.snapshot_type, v.storage_key,
       coalesce((SELECT json_agg(b ORDER BY b.position) FROM bitmaps b WHERE b.viewpoint_guid = v.guid), '[]') AS bitmaps
FROM viewpoints v
JOIN topics t ON t.guid = v.topic_guid
JOIN memberships m ON m.project_id = t.project_id AND m.user_id = $1
WHERE t.project_id = $2 AND v.topic_guid = $3 AND v.guid = $4
"""
VIEWPOINT_NODE = """
SELECT v.guid, v."index", v.author, v.creation_date, v.camera_kind, v.camera, v.lines, v.clipping_planes,
       v.snapshot_type, v.storage_key, v.has_components, v.default_visibility, v.has_hints, v.spaces_visible,
       v.space_boundaries_visible, v.openings_visible
FROM viewpoints v
JOIN topics t ON t.guid = v.topic_guid
JOIN memberships m ON m.project_id = t.project_id AND m.user_id = $1
WHERE t.project_id = $2 AND v.topic_guid = $3 AND v.guid = $4
"""
BITMAP = """
SELECT b.guid, b.position, b.bitmap_type, b.storage_key, b.height, b.loc_x, b.loc_y, b.loc_z, b.nrm_x, b.nrm_y,
       b.nrm_z, b.up_x, b.up_y, b.up_z
FROM bitmaps b
JOIN viewpoints v ON v.guid = b.viewpoint_guid
JOIN topics t ON t.guid = v.topic_guid
JOIN memberships m ON m.project_id = t.project_id AND m.user_id = $1
WHERE t.project_id = $2 AND v.topic_guid = $3 AND v.guid = $4 AND b.guid = $5
"""
COMPONENTS = """
SELECT c.id, c.role, c.group_index, c.position, c.color, c.ifc_guid, c.originating_system, c.authoring_tool_id,
       c.gtin
FROM components c
JOIN viewpoints v ON v.guid = c.viewpoint_guid
JOIN topics t ON t.guid = v.topic_guid
JOIN memberships m ON m.project_id = t.project_id AND m.user_id = $1
WHERE t.project_id = $2 AND v.topic_guid = $3 AND v.guid = $4 AND c.role = $5
ORDER BY c.group_index, c.position
"""
VIEWPOINT_INSERT = """
INSERT INTO viewpoints AS v (
    guid, topic_guid, "index", author, creation_date, camera_kind, camera, lines, clipping_planes, snapshot_type,
    storage_key, has_components, default_visibility, has_hints, spaces_visible, space_boundaries_visible,
    openings_visible
)
SELECT $1, t.guid, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18
FROM topics t JOIN users u ON u.username = $5
WHERE t.project_id = $2 AND t.guid = $3
RETURNING v.guid, v."index", v.author, v.creation_date, v.camera_kind, v.camera, v.lines, v.clipping_planes,
          v.snapshot_type, v.storage_key
"""
COMPONENTS_INSERT = """
INSERT INTO components (
    id, viewpoint_guid, role, group_index, position, color, ifc_guid, originating_system, authoring_tool_id
)
SELECT r.id, $1, r.role, r.group_index, r.position, r.color, r.ifc_guid, r.originating_system, r.authoring_tool_id
FROM unnest($2::text[], $3::text[], $4::integer[], $5::integer[], $6::text[], $7::text[], $8::text[], $9::text[])
     AS r (id, role, group_index, position, color, ifc_guid, originating_system, authoring_tool_id)
"""
BITMAPS_INSERT = """
INSERT INTO bitmaps (
    guid, viewpoint_guid, position, bitmap_type, storage_key, height,
    loc_x, loc_y, loc_z, nrm_x, nrm_y, nrm_z, up_x, up_y, up_z
)
SELECT r.guid, $1, r.position, r.bitmap_type, r.storage_key, r.height,
       r.loc_x, r.loc_y, r.loc_z, r.nrm_x, r.nrm_y, r.nrm_z, r.up_x, r.up_y, r.up_z
FROM unnest($2::text[], $3::integer[], $4::text[], $5::text[], $6::float8[],
            $7::float8[], $8::float8[], $9::float8[], $10::float8[], $11::float8[], $12::float8[],
            $13::float8[], $14::float8[], $15::float8[])
     AS r (guid, position, bitmap_type, storage_key, height, loc_x, loc_y, loc_z, nrm_x, nrm_y, nrm_z, up_x, up_y, up_z)
"""
VIEWPOINT_GOING = """
SELECT v.storage_key AS snapshot_key,
       (SELECT count(*) FROM comments c WHERE c.topic_guid = v.topic_guid AND c.viewpoint_guid = v.guid) AS comments,
       ARRAY(SELECT b.storage_key FROM bitmaps b WHERE b.viewpoint_guid = v.guid) AS bitmap_keys
FROM viewpoints v
WHERE v.topic_guid = $1 AND v.guid = $2
FOR UPDATE
"""

_COMPONENT_COLUMNS = (
    "id",
    "role",
    "group_index",
    "position",
    "color",
    "ifc_guid",
    "originating_system",
    "authoring_tool_id",
)
_BITMAP_COLUMNS = (
    "guid",
    "position",
    "bitmap_type",
    "storage_key",
    "height",
    "loc_x",
    "loc_y",
    "loc_z",
    "nrm_x",
    "nrm_y",
    "nrm_z",
    "up_x",
    "up_y",
    "up_z",
)


def _columns(rows: list[dict[str, Any]], names: tuple[str, ...]) -> list[list[Any]]:
    """Rows as one list per column, for ``unnest``."""
    return [[row[name] for row in rows] for name in names]


def _viewpoint(row: dict[str, Any]) -> ViewpointRecord:
    return to_record(_properties({key: value for key, value in row.items() if key != "bitmaps"}), row["bitmaps"])


class PostgresViewpointRepository:
    def __init__(self, postgres: Postgres, storage: LocalStorage, *, max_image_bytes: int) -> None:
        self.postgres = postgres
        self.storage = storage
        self.max_image_bytes = max_image_bytes

    async def search(self, *, user_id: str, project_id: str, topic_guid: str) -> list[ViewpointRecord]:
        return [_viewpoint(row) for row in await self.postgres.run(VIEWPOINTS, user_id, project_id, topic_guid)]

    async def get(self, *, user_id: str, project_id: str, topic_guid: str, guid: str) -> ViewpointRecord | None:
        row = await self.postgres.one(VIEWPOINT, user_id, project_id, topic_guid, guid)
        return _viewpoint(row) if row else None

    async def bitmap(
        self, *, user_id: str, project_id: str, topic_guid: str, guid: str, bitmap_guid: str
    ) -> dict[str, Any] | None:
        row = await self.postgres.one(BITMAP, user_id, project_id, topic_guid, guid, bitmap_guid)
        return _properties(row) if row else None

    async def components(
        self, *, user_id: str, project_id: str, topic_guid: str, guid: str, role: str
    ) -> list[dict[str, Any]]:
        rows = await self.postgres.run(COMPONENTS, user_id, project_id, topic_guid, guid, role)
        return [_properties(row) for row in rows]

    async def selection(self, **scope: str) -> list[Component]:
        return [_component(node) for node in await self.components(role=ROLE_SELECTION, **scope)]

    async def coloring(self, **scope: str) -> list[Coloring]:
        groups: dict[int, Coloring] = {}
        for node in await self.components(role=ROLE_COLORING, **scope):
            group = groups.setdefault(node["group_index"], Coloring(color=node["color"], components=[]))
            group.components.append(_component(node))
        return [groups[key] for key in sorted(groups)]

    async def visibility(self, node: dict[str, Any], **scope: str) -> Visibility:
        exceptions = [_component(item) for item in await self.components(role=ROLE_EXCEPTION, **scope)]
        hints = None
        if node.get("has_hints"):
            hints = ViewSetupHints(
                spaces_visible=bool(node.get("spaces_visible")),
                space_boundaries_visible=bool(node.get("space_boundaries_visible")),
                openings_visible=bool(node.get("openings_visible")),
            )
        return Visibility(
            default_visibility=bool(node.get("default_visibility", True)), exceptions=exceptions, view_setup_hints=hints
        )

    async def node(self, *, user_id: str, project_id: str, topic_guid: str, guid: str) -> dict[str, Any] | None:
        row = await self.postgres.one(VIEWPOINT_NODE, user_id, project_id, topic_guid, guid)
        return _properties(row) if row else None

    async def create(self, *, project_id: str, topic_guid: str, author: str, body: ViewpointPOST) -> ViewpointRecord:
        if body.guid and not is_uuid(body.guid):
            raise HTTPException(400, "guid must be a UUID")
        guid = normalize_guid(body.guid) if body.guid else new_id()
        if await self.postgres.one("SELECT 1 AS n FROM viewpoints WHERE guid = $1", guid):
            raise HTTPException(409, "A viewpoint with this guid already exists")  # Foundation API 1.5.1
        now = now_iso()

        # Decode and verify every image before anything is written.
        snapshot: tuple[str, bytes] | None = None
        if body.snapshot:
            data = decode_image(
                body.snapshot.snapshot_data, body.snapshot.snapshot_type, self.max_image_bytes, "snapshot"
            )
            snapshot = (make_key("snapshots", guid, body.snapshot.snapshot_type), data)
        bitmap_rows: list[dict[str, Any]] = []
        bitmap_files: list[tuple[str, bytes]] = []
        for position, bitmap in enumerate(body.bitmaps or []):
            data = decode_image(bitmap.bitmap_data, bitmap.bitmap_type, self.max_image_bytes, f"bitmaps[{position}]")
            bitmap_guid = new_id()
            key = make_key("bitmaps", bitmap_guid, bitmap.bitmap_type)
            bitmap_files.append((key, data))
            bitmap_rows.append(
                {
                    "guid": bitmap_guid,
                    "position": position,
                    "bitmap_type": bitmap.bitmap_type,
                    "storage_key": key,
                    "height": bitmap.height,
                    "loc_x": bitmap.location.x,
                    "loc_y": bitmap.location.y,
                    "loc_z": bitmap.location.z,
                    "nrm_x": bitmap.normal.x,
                    "nrm_y": bitmap.normal.y,
                    "nrm_z": bitmap.normal.z,
                    "up_x": bitmap.up.x,
                    "up_y": bitmap.up.y,
                    "up_z": bitmap.up.z,
                }
            )

        camera: OrthogonalCamera | PerspectiveCamera | None = body.orthogonal_camera or body.perspective_camera
        components = body.components
        hints = components.visibility.view_setup_hints if components else None
        values = (
            body.index,
            author,
            now,
            "orthogonal" if body.orthogonal_camera else ("perspective" if body.perspective_camera else None),
            camera.model_dump_json() if camera else None,
            json.dumps([line.model_dump() for line in body.lines]) if body.lines else None,
            json.dumps([plane.model_dump() for plane in body.clipping_planes]) if body.clipping_planes else None,
            body.snapshot.snapshot_type if body.snapshot else None,
            snapshot[0] if snapshot else None,
            components is not None,
            components.visibility.default_visibility if components else True,
            hints is not None,
            hints.spaces_visible if hints else None,
            hints.space_boundaries_visible if hints else None,
            hints.openings_visible if hints else None,
        )
        component_rows = _component_rows(body)

        async def work(tx: Tx) -> dict[str, Any]:
            if await tx.one("SELECT 1 AS n FROM viewpoints WHERE guid = $1", guid):
                raise HTTPException(409, "A viewpoint with this guid already exists")
            row = await tx.one(VIEWPOINT_INSERT, guid, project_id, topic_guid, *values)
            if row is None:
                raise HTTPException(404, "Topic not found")
            for start in range(0, len(component_rows), BATCH):
                batch = _columns(component_rows[start : start + BATCH], _COMPONENT_COLUMNS)
                await tx.execute(COMPONENTS_INSERT, guid, *batch)
            if bitmap_rows:
                await tx.execute(BITMAPS_INSERT, guid, *_columns(bitmap_rows, _BITMAP_COLUMNS))
            # A new viewpoint is "floating" until a comment refers to it, which moves the topic (BCF 3.2.1).
            await _touch(tx, topic_guid, author, now)
            return row

        written: list[str] = []
        try:
            for key, data in ([snapshot] if snapshot else []) + bitmap_files:
                self.storage.write_bytes(key, data)
                written.append(key)
            row = await self.postgres.write(work)
        except BaseException:
            for key in written:
                self.storage.delete(key)
            raise
        return to_record(_properties(row), bitmap_rows)

    async def delete(self, *, topic_guid: str, guid: str) -> list[str]:
        """Delete the viewpoint with its components and bitmaps; 409 while a comment refers to it (BCF 3.5.9)."""

        async def work(tx: Tx) -> list[str] | None:
            row = await tx.one(VIEWPOINT_GOING, topic_guid, guid)
            if row is None:
                return None
            if row["comments"]:
                raise HTTPException(409, "A comment refers to this viewpoint; update the comment first")
            await tx.execute("DELETE FROM viewpoints WHERE topic_guid = $1 AND guid = $2", topic_guid, guid)
            keys = [key for key in row["bitmap_keys"] or [] if key]
            if row["snapshot_key"]:
                keys.append(row["snapshot_key"])
            return keys

        keys = await self.postgres.write(work)
        if keys is None:
            raise HTTPException(404, "Viewpoint not found")
        return keys


# -- what a topic points at (BCF 3.3, 3.6, 3.7, 3.2.6) ----------------------------------------------------------

RELATED = """
SELECT o.guid
FROM related_topics r
JOIN topics t ON t.guid = r.topic_guid
JOIN memberships m ON m.project_id = t.project_id AND m.user_id = $1
JOIN topics o ON o.guid = r.related_guid
WHERE t.project_id = $2 AND r.topic_guid = $3
ORDER BY o.creation_date, o.guid COLLATE "C"
"""
TOPICS_OF_PROJECT = "SELECT o.guid FROM topics o WHERE o.project_id = $1 AND o.guid = ANY($2::text[])"
RELATED_UNSET = """
DELETE FROM related_topics r USING topics t
WHERE t.guid = r.topic_guid AND t.project_id = $1 AND r.topic_guid = $2
"""
RELATED_SET = """
INSERT INTO related_topics (topic_guid, related_guid)
SELECT t.guid, o.guid FROM topics t JOIN topics o ON o.guid = ANY($3::text[])
WHERE t.project_id = $1 AND t.guid = $2
"""
REFERENCES = """
SELECT r.guid, r.document_guid, r.url, r.description
FROM document_references r
JOIN topics t ON t.guid = r.topic_guid
JOIN memberships m ON m.project_id = t.project_id AND m.user_id = $1
WHERE t.project_id = $2 AND r.topic_guid = $3
ORDER BY r.created_at, r.guid COLLATE "C"
"""
DOCUMENT_OF_PROJECT = """
SELECT EXISTS (SELECT 1 FROM bcf_documents d WHERE d.project_id = $1 AND d.guid = $2)
       OR EXISTS (SELECT 1 FROM documents d WHERE d.project_id = $1 AND d.document_id = $2) AS found
"""
REFERENCE_INSERT = """
INSERT INTO document_references AS r (guid, topic_guid, document_guid, url, description, created_at)
SELECT $1, t.guid, $4, $5, $6, $7 FROM topics t WHERE t.project_id = $2 AND t.guid = $3
RETURNING r.guid, r.document_guid, r.url, r.description
"""
REFERENCE_UPDATE = """
UPDATE document_references r SET document_guid = $4, url = $5, description = $6
FROM topics t
WHERE t.guid = r.topic_guid AND t.project_id = $1 AND r.topic_guid = $2 AND r.guid = $3
RETURNING r.guid, r.document_guid, r.url, r.description
"""
HEADER_FILES = """
SELECT f.ifc_project, f.ifc_spatial_structure_element, f.filename, f.date, f.reference
FROM header_files f
JOIN topics t ON t.guid = f.topic_guid
JOIN memberships m ON m.project_id = t.project_id AND m.user_id = $1
WHERE t.project_id = $2 AND f.topic_guid = $3
ORDER BY f.position
"""
HEADER_FILES_UNSET = """
DELETE FROM header_files f USING topics t
WHERE t.guid = f.topic_guid AND t.project_id = $1 AND f.topic_guid = $2
"""
HEADER_FILES_SET = """
INSERT INTO header_files (
    id, topic_guid, position, ifc_project, ifc_spatial_structure_element, filename, date, reference
)
SELECT r.id, t.guid, r.position, r.ifc_project, r.ifc_spatial_structure_element, r.filename, r.date, r.reference
FROM topics t,
     unnest($3::text[], $4::integer[], $5::text[], $6::text[], $7::text[], $8::text[], $9::text[])
     AS r (id, position, ifc_project, ifc_spatial_structure_element, filename, date, reference)
WHERE t.project_id = $1 AND t.guid = $2
"""
SNIPPET = """
SELECT t.snippet_storage_key AS storage_key,
       coalesce(t.snippet_filename, t.snippet_reference, 'snippet') AS filename
FROM topics t JOIN memberships m ON m.project_id = t.project_id AND m.user_id = $1
WHERE t.project_id = $2 AND t.guid = $3
  AND t.snippet_storage_key IS NOT NULL AND t.snippet_type IS NOT NULL AND t.snippet_is_external = false
"""
SNIPPET_SET = """
UPDATE topics t
SET snippet_storage_key = $3, snippet_is_external = false,
    snippet_reference = coalesce($4::text, t.snippet_reference), snippet_filename = $4::text, snippet_size = $5,
    modified_date = $6, modified_author = $7
WHERE t.project_id = $1 AND t.guid = $2
"""
_HEADER_FILE_COLUMNS = (
    "id",
    "position",
    "ifc_project",
    "ifc_spatial_structure_element",
    "filename",
    "date",
    "reference",
)


class PostgresTopicLinkRepository:
    def __init__(self, postgres: Postgres) -> None:
        self.postgres = postgres

    async def related(self, *, user_id: str, project_id: str, topic_guid: str) -> list[str]:
        return [row["guid"] for row in await self.postgres.run(RELATED, user_id, project_id, topic_guid)]

    async def set_related(self, *, project_id: str, topic_guid: str, author: str, guids: list[str]) -> list[str]:
        wanted: list[str] = []
        for value in guids:
            if not is_uuid(value):
                raise HTTPException(400, "related_topic_guid must be a UUID")
            normalized = normalize_guid(value)
            if normalized == topic_guid:
                raise HTTPException(400, "a topic cannot be related to itself")
            if normalized not in wanted:
                wanted.append(normalized)

        async def work(tx: Tx) -> list[str]:
            found = await tx.run(TOPICS_OF_PROJECT, project_id, wanted)
            missing = set(wanted) - {row["guid"] for row in found}
            if missing:
                raise HTTPException(400, f"not topics of this project: {', '.join(sorted(missing))}")
            await tx.execute(RELATED_UNSET, project_id, topic_guid)
            await tx.execute(RELATED_SET, project_id, topic_guid, wanted)
            await _touch(tx, topic_guid, author)
            return wanted

        return await self.postgres.write(work)

    async def references(self, *, user_id: str, project_id: str, topic_guid: str) -> list[DocumentReferenceGET]:
        rows = await self.postgres.run(REFERENCES, user_id, project_id, topic_guid)
        return [_reference(row) for row in rows]

    @staticmethod
    async def _check_document(tx: Tx, project_id: str, fields: DocumentReferenceFields) -> str | None:
        if fields.document_guid is None:
            return None
        if not is_uuid(fields.document_guid):
            raise HTTPException(400, "document_guid must be a UUID")
        guid = normalize_guid(fields.document_guid)
        row = await tx.one(DOCUMENT_OF_PROJECT, project_id, guid)
        if row is None or not row["found"]:
            raise HTTPException(400, "document_guid does not match a document of this project")  # BCF 3.7.2
        return guid

    async def add_reference(
        self, *, project_id: str, topic_guid: str, author: str, body: DocumentReferencePOST
    ) -> DocumentReferenceGET:
        if body.guid and not is_uuid(body.guid):
            raise HTTPException(400, "guid must be a UUID")
        guid = normalize_guid(body.guid) if body.guid else new_id()

        async def work(tx: Tx) -> dict[str, Any]:
            if await tx.one("SELECT 1 AS n FROM document_references WHERE guid = $1", guid):
                raise HTTPException(409, "A document reference with this guid already exists")
            document_guid = await self._check_document(tx, project_id, body)
            row = await tx.one(
                REFERENCE_INSERT, guid, project_id, topic_guid, document_guid, body.url, body.description, now_iso()
            )
            if row is None:
                raise HTTPException(404, "Topic not found")
            await _touch(tx, topic_guid, author)
            return row

        return _reference(await self.postgres.write(work))

    async def update_reference(
        self, *, project_id: str, topic_guid: str, guid: str, author: str, body: DocumentReferencePUT
    ) -> DocumentReferenceGET | None:
        async def work(tx: Tx) -> dict[str, Any] | None:
            document_guid = await self._check_document(tx, project_id, body)
            row = await tx.one(
                REFERENCE_UPDATE, project_id, topic_guid, guid, document_guid, body.url, body.description
            )
            if row is None:
                return None
            await _touch(tx, topic_guid, author)
            return row

        result = await self.postgres.write(work)
        return _reference(result) if result else None

    async def files(self, *, user_id: str, project_id: str, topic_guid: str) -> list[FileRef]:
        return [_file(row) for row in await self.postgres.run(HEADER_FILES, user_id, project_id, topic_guid)]

    async def set_files(self, *, project_id: str, topic_guid: str, author: str, files: list[FileRef]) -> list[FileRef]:
        rows = [{"id": new_id(), "position": position, **item.model_dump()} for position, item in enumerate(files)]

        async def work(tx: Tx) -> None:
            await tx.execute(HEADER_FILES_UNSET, project_id, topic_guid)
            await tx.execute(HEADER_FILES_SET, project_id, topic_guid, *_columns(rows, _HEADER_FILE_COLUMNS))
            await _touch(tx, topic_guid, author)

        await self.postgres.write(work)
        return files

    async def snippet(self, *, user_id: str, project_id: str, topic_guid: str) -> dict[str, Any] | None:
        """Storage key and file name of the stored snippet, or None when the topic has none."""
        return await self.postgres.one(SNIPPET, user_id, project_id, topic_guid)

    async def set_snippet(
        self, *, project_id: str, topic_guid: str, author: str, storage_key: str, filename: str | None, size: int
    ) -> None:
        """Record an uploaded snippet file: the snippet becomes internal and its reference the file name (3.2.7)."""
        await self.postgres.execute(SNIPPET_SET, project_id, topic_guid, storage_key, filename, size, now_iso(), author)


# -- project documents (BCF 3.8) and the files information (3.3.1) ----------------------------------------------

BCF_DOCUMENTS = """
SELECT d.guid, d.filename, d.storage_key, d.size, d.created_at, d.author
FROM bcf_documents d JOIN memberships m ON m.project_id = d.project_id AND m.user_id = $1
WHERE d.project_id = $2
ORDER BY d.created_at, d.guid COLLATE "C"
"""
BCF_DOCUMENT = """
SELECT d.guid, d.filename, d.storage_key, d.size, d.created_at, d.author
FROM bcf_documents d JOIN memberships m ON m.project_id = d.project_id AND m.user_id = $1
WHERE d.project_id = $2 AND d.guid = $3
"""
BCF_DOCUMENT_INSERT = """
INSERT INTO bcf_documents AS d (guid, project_id, filename, storage_key, size, created_at, author)
SELECT $1, p.project_id, $3, $4, $5, $6, $7 FROM projects p JOIN users u ON u.username = $7 WHERE p.project_id = $2
RETURNING d.guid, d.filename
"""
#: The latest version of each of the project's Documents API documents, with the IFC project of its finished
#: conversion (the jobs area's view).
LATEST_VERSIONS = """
SELECT d.document_id, v.version_index, v.file_name, v.creation_date, v.author, c.ifc_project_guid AS ifc_project
FROM documents d
JOIN memberships m ON m.project_id = d.project_id AND m.user_id = $1
JOIN document_heads h ON h.document_id = d.document_id
JOIN document_versions v ON v.document_id = h.document_id AND v.version_index = h.version_index
LEFT JOIN conversion_ifc_projects c ON c.document_id = d.document_id AND c.version_index = v.version_index
WHERE d.project_id = $2
ORDER BY v.creation_date, d.document_id COLLATE "C"
"""


class PostgresBcfDocumentRepository:
    def __init__(self, postgres: Postgres) -> None:
        self.postgres = postgres

    async def search(self, *, user_id: str, project_id: str) -> list[DocumentGET]:
        rows = await self.postgres.run(BCF_DOCUMENTS, user_id, project_id)
        return [DocumentGET(guid=row["guid"], filename=row["filename"]) for row in rows]

    async def get(self, *, user_id: str, project_id: str, guid: str) -> dict[str, Any] | None:
        row = await self.postgres.one(BCF_DOCUMENT, user_id, project_id, guid)
        return _properties(row) if row else None

    async def exists(self, guid: str) -> bool:
        return await self.postgres.one("SELECT 1 AS n FROM bcf_documents WHERE guid = $1", guid) is not None

    async def create(
        self, *, project_id: str, guid: str, filename: str, author: str, storage_key: str, size: int
    ) -> DocumentGET:
        async def work(tx: Tx) -> dict[str, Any]:
            if await tx.one("SELECT 1 AS n FROM bcf_documents WHERE guid = $1", guid):
                raise HTTPException(409, "A document with this guid already exists")  # Foundation API 1.5.1
            row = await tx.one(BCF_DOCUMENT_INSERT, guid, project_id, filename, storage_key, size, now_iso(), author)
            if row is None:
                raise HTTPException(404, "Project not found")
            return row

        row = await self.postgres.write(work)
        return DocumentGET(guid=row["guid"], filename=row["filename"])

    async def files_information(self, *, user_id: str, project_id: str, base_url: str) -> list[ProjectFileInformation]:
        """One entry per file in the project (BCF documents and Documents API versions), with the same display
        fields for every entry (BCF 3.3.1)."""
        entries = [
            _entry(
                filename=row["filename"],
                date=row["created_at"],
                author=row["author"],
                source="BCF API document",
                reference=f"{base_url}/bcf/3.0/projects/{project_id}/documents/{row['guid']}",
                document_id=row["guid"],
            )
            for row in await self.postgres.run(BCF_DOCUMENTS, user_id, project_id)
        ]
        entries.extend(
            _entry(
                filename=row["file_name"],
                date=row["creation_date"],
                author=row["author"],
                source="Documents API",
                reference=(
                    f"{base_url}/documents/1.0/documents/{row['document_id']}/versions/{row['version_index']}/download"
                ),
                ifc_project=row["ifc_project"],
                document_id=row["document_id"],
                version_index=row["version_index"],
            )
            for row in await self.postgres.run(LATEST_VERSIONS, user_id, project_id)
        )
        return entries


# -- where the BCF area is ---------------------------------------------------------------------------------------


def topic_store(graph: Graph, postgres: Postgres | None, *, id_prefix: str) -> TopicStore:
    if postgres is not None:
        return PostgresTopicRepository(postgres, id_prefix=id_prefix)
    return TopicRepository(graph, id_prefix=id_prefix)


def comment_store(graph: Graph, postgres: Postgres | None, topics: TopicStore) -> CommentStore:
    return (
        PostgresCommentRepository(postgres) if postgres is not None else graph_comments.CommentRepository(graph, topics)
    )


def viewpoint_store(
    graph: Graph, postgres: Postgres | None, storage: LocalStorage, topics: TopicStore, *, max_image_bytes: int
) -> ViewpointStore:
    if postgres is not None:
        return PostgresViewpointRepository(postgres, storage, max_image_bytes=max_image_bytes)
    return ViewpointRepository(graph, storage, topics, max_image_bytes=max_image_bytes)


def link_store(graph: Graph, postgres: Postgres | None, topics: TopicStore) -> TopicLinkStore:
    return PostgresTopicLinkRepository(postgres) if postgres is not None else TopicLinkRepository(graph, topics)


def bcf_document_store(graph: Graph, postgres: Postgres | None) -> BcfDocumentStore:
    return PostgresBcfDocumentRepository(postgres) if postgres is not None else BcfDocumentRepository(graph)


def event_store(graph: Graph, postgres: Postgres | None) -> BcfEventStore:
    return PostgresBcfEventRepository(postgres) if postgres is not None else BcfEventRepository(graph)
