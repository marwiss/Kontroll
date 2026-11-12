# This file was generated with the assistance of an AI coding tool.
"""The Documents area in PostgreSQL (ADR 0029): documents with their versions, publications, and the upload and
selection sessions.

The same protocols as the graph's repositories (``opencde.store.protocols``), over the tables of
``opencde/postgres/migrations/0003_documents.sql``, with the same rules and answers. Every read for a member joins
``memberships`` on the user's id, as the graph's statements start at the user and follow ``MEMBER_OF``; a document
in a project the caller is not a member of does not exist. Every statement is one string literal with numbered
parameters; text is ordered by code point (``COLLATE "C"``), as the graphs order it.

A version's checks are the jobs area's: ``validation`` reads them through the views ``version_validations`` and
``version_graph_checks``, empty until that area's migration defines them. The audit log is still the graph's, so
``publish`` records its event there once the publication is stored, rather than in the same transaction.

``document_store``, ``upload_session_store`` and ``selection_session_store`` choose between the two: PostgreSQL when
``OPENCDE_STORE_URL`` names it, the graph otherwise.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import HTTPException

from opencde import audit
from opencde.ids import hash_secret, new_id, new_secret
from opencde.store.documents.sessions import (
    STATE_NEW,
    SelectionSession,
    SelectionSessionRepository,
    UploadSession,
    UploadSessionRepository,
)
from opencde.store.documents.versions import (
    DocumentRepository,
    VersionRecord,
    _change,
    _change_set,
    _validation,
)
from opencde.timeutil import later_iso, now_iso

if TYPE_CHECKING:
    from opencde.documents.schemas import DocumentMetadataEntry
    from opencde.documents.validation import Validation
    from opencde.graph.graph import Graph
    from opencde.postgres.database import Postgres, Tx
    from opencde.settings import Settings
    from opencde.store.protocols import DocumentStore, SelectionSessionStore, UploadSessionStore

MAX_TOKEN_LENGTH = 128  # longer is no token the server gave


def _record(row: dict[str, Any]) -> VersionRecord:
    return VersionRecord(
        document_id=row["document_id"],
        project_id=row["project_id"],
        project_name=row["project_name"],
        version_id=row["id"],
        version_index=int(row["version_index"]),
        version_number=row["version_number"],
        creation_date=row["creation_date"],
        title=row["title"],
        file_name=row["file_name"],
        size_in_bytes=int(row["size_in_bytes"]),
        sha256=row["sha256"],
        storage_key=row["storage_key"],
        author=row["author"],
        metadata=list(row["metadata"] or []),
    )


# -- documents and their versions --------------------------------------------------------------------------------

LATEST = """
SELECT d.document_id, p.project_id, p.name AS project_name, v.id, v.version_index, v.version_number,
       v.creation_date, v.title, v.file_name, v.size_in_bytes, v.sha256, v.storage_key, v.author, v.metadata
FROM documents d
JOIN memberships m ON m.project_id = d.project_id AND m.user_id = $1
JOIN projects p ON p.project_id = d.project_id
JOIN document_versions v ON v.document_id = d.document_id
WHERE d.document_id = $2
ORDER BY v.version_index DESC
LIMIT 1
"""
VERSION = """
SELECT d.document_id, p.project_id, p.name AS project_name, v.id, v.version_index, v.version_number,
       v.creation_date, v.title, v.file_name, v.size_in_bytes, v.sha256, v.storage_key, v.author, v.metadata
FROM documents d
JOIN memberships m ON m.project_id = d.project_id AND m.user_id = $1
JOIN projects p ON p.project_id = d.project_id
JOIN document_versions v ON v.document_id = d.document_id AND v.version_index = $3
WHERE d.document_id = $2
"""
VERSIONS = """
SELECT d.document_id, p.project_id, p.name AS project_name, v.id, v.version_index, v.version_number,
       v.creation_date, v.title, v.file_name, v.size_in_bytes, v.sha256, v.storage_key, v.author, v.metadata
FROM documents d
JOIN memberships m ON m.project_id = d.project_id AND m.user_id = $1
JOIN projects p ON p.project_id = d.project_id
JOIN document_versions v ON v.document_id = d.document_id
WHERE d.document_id = $2
ORDER BY v.version_index
"""
LATEST_MANY = """
SELECT h.* FROM (
    SELECT DISTINCT ON (d.document_id)
           d.document_id, p.project_id, p.name AS project_name, v.id, v.version_index, v.version_number,
           v.creation_date, v.title, v.file_name, v.size_in_bytes, v.sha256, v.storage_key, v.author, v.metadata
    FROM documents d
    JOIN memberships m ON m.project_id = d.project_id AND m.user_id = $1
    JOIN projects p ON p.project_id = d.project_id
    JOIN document_versions v ON v.document_id = d.document_id
    WHERE d.document_id = ANY($2::text[])
    ORDER BY d.document_id, v.version_index DESC
) h
ORDER BY h.document_id COLLATE "C"
"""
LATEST_IN_PROJECTS = """
SELECT h.* FROM (
    SELECT DISTINCT ON (d.document_id)
           d.document_id, p.project_id, p.name AS project_name, v.id, v.version_index, v.version_number,
           v.creation_date, v.title, v.file_name, v.size_in_bytes, v.sha256, v.storage_key, v.author, v.metadata
    FROM documents d
    JOIN memberships m ON m.project_id = d.project_id AND m.user_id = $1
    JOIN projects p ON p.project_id = d.project_id
    JOIN document_versions v ON v.document_id = d.document_id
    ORDER BY d.document_id, v.version_index DESC
) h
ORDER BY h.project_name COLLATE "C", h.project_id COLLATE "C", h.title COLLATE "C", h.document_id COLLATE "C"
"""
VALIDATION = """
SELECT r.state, r.issue_count, r.error_count, r.truncated, r.checked_at, r.ruleset, r.checks,
       CASE WHEN $4::boolean THEN r.report END AS report, CASE WHEN $4::boolean THEN r.rooms END AS rooms,
       g.graph_issue_count, g.graph_error_count, g.graph_ruleset,
       CASE WHEN $4::boolean THEN g.graph_report END AS graph_report
FROM documents d
JOIN memberships m ON m.project_id = d.project_id AND m.user_id = $1
JOIN document_versions v ON v.document_id = d.document_id AND v.version_index = $3
JOIN LATERAL (
    SELECT c.state, c.issue_count, c.error_count, c.truncated, c.checked_at, c.ruleset, c.checks, c.report, c.rooms
    FROM version_validations c WHERE c.version_id = v.id
    ORDER BY c.created_at DESC LIMIT 1
) r ON true
LEFT JOIN LATERAL (
    SELECT c.graph_issue_count, c.graph_error_count, c.graph_ruleset, c.graph_report
    FROM version_graph_checks c
    WHERE c.project_id = d.project_id AND c.document_id = d.document_id AND c.version_index = v.version_index
      AND c.graph_checked_at IS NOT NULL
    ORDER BY c.created_at DESC LIMIT 1
) g ON true
WHERE d.document_id = $2
"""
DOCUMENT_INSERT = """
INSERT INTO documents (document_id, project_id, title, created_at, latest_index)
SELECT $1, p.project_id, $3, $4, 1 FROM projects p WHERE p.project_id = $2
RETURNING latest_index AS index
"""
DOCUMENT_NEXT = """
UPDATE documents d SET latest_index = d.latest_index + 1, title = $3
WHERE d.project_id = $1 AND d.document_id = $2
RETURNING d.latest_index AS index
"""
VERSION_INSERT = """
WITH made AS (
    INSERT INTO document_versions AS v (
        id, document_id, version_index, version_number, creation_date, title, file_name, size_in_bytes, sha256,
        storage_key, author, uploaded_by, metadata, parent_version_index, approved_by, change_set_id, change_set
    )
    SELECT $3, d.document_id, $5::integer, $6, $7, $8, $9, $10::bigint, $11, $12, u.username, u.id, $13::jsonb,
           $14::integer, $15, $16, $17
    FROM documents d JOIN users u ON u.username = $4
    WHERE d.project_id = $1 AND d.document_id = $2
    RETURNING v.*
)
SELECT made.document_id, p.project_id, p.name AS project_name, made.id, made.version_index, made.version_number,
       made.creation_date, made.title, made.file_name, made.size_in_bytes, made.sha256, made.storage_key,
       made.author, made.metadata
FROM made JOIN projects p ON p.project_id = $1
"""
VERSIONS_SINCE = """
SELECT v.version_index, v.author, v.approved_by, v.change_set_id, v.change_set
FROM documents d
JOIN memberships m ON m.project_id = d.project_id AND m.user_id = $1
JOIN document_versions v ON v.document_id = d.document_id
WHERE d.document_id = $2 AND v.version_index > $3 AND v.version_index <= $4
ORDER BY v.version_index
"""
CHANGE_SET = """
SELECT v.change_set, v.change_set_id, v.parent_version_index AS parent, v.approved_by, v.author
FROM documents d
JOIN memberships m ON m.project_id = d.project_id AND m.user_id = $1
JOIN document_versions v ON v.document_id = d.document_id AND v.version_index = $3
WHERE d.document_id = $2
"""
PUBLICATION = """
SELECT pub.id, pub.storage_key, pub.file_name, pub.size_in_bytes, pub.sha256, pub.published_at, pub.published_by
FROM documents d
JOIN memberships m ON m.project_id = d.project_id AND m.user_id = $1
JOIN document_versions v ON v.document_id = d.document_id AND v.version_index = $3
JOIN publications pub ON pub.version_id = v.id
WHERE d.document_id = $2
"""
PUBLISH = """
INSERT INTO publications (id, version_id, storage_key, file_name, size_in_bytes, sha256, published_at, published_by)
SELECT $4, v.id, $5, $6, $7::bigint, $8, $9, $10
FROM documents d
JOIN memberships m ON m.project_id = d.project_id AND m.user_id = $1
JOIN document_versions v ON v.document_id = d.document_id AND v.version_index = $3
WHERE d.document_id = $2
ON CONFLICT (version_id) DO NOTHING
RETURNING version_id
"""


class PostgresDocumentRepository:
    def __init__(self, postgres: Postgres, *, audit_graph: Graph | None = None) -> None:
        self.postgres = postgres
        self.audit_graph = audit_graph  # where the audit log is until it follows (ADR 0029)

    async def latest(self, *, user_id: str, document_id: str) -> VersionRecord | None:
        row = await self.postgres.one(LATEST, user_id, document_id)
        return _record(row) if row else None

    async def version(self, *, user_id: str, document_id: str, version_index: int) -> VersionRecord | None:
        row = await self.postgres.one(VERSION, user_id, document_id, version_index)
        return _record(row) if row else None

    async def versions(self, *, user_id: str, document_id: str) -> list[VersionRecord]:
        return [_record(row) for row in await self.postgres.run(VERSIONS, user_id, document_id)]

    async def latest_many(self, *, user_id: str, document_ids: list[str]) -> list[VersionRecord]:
        """The latest version of each listed document the user may see, in document id order."""
        return [_record(row) for row in await self.postgres.run(LATEST_MANY, user_id, list(document_ids))]

    async def latest_in_projects(self, *, user_id: str) -> list[VersionRecord]:
        """The latest version of every document in the user's projects (the selection page)."""
        return [_record(row) for row in await self.postgres.run(LATEST_IN_PROJECTS, user_id)]

    async def validation(
        self, *, user_id: str, document_id: str, version_index: int, with_issues: bool = False
    ) -> Validation | None:
        """The latest check of a version, with what the graph of its converted model showed (the jobs area's views
        ``version_validations`` and ``version_graph_checks``)."""
        row = await self.postgres.one(VALIDATION, user_id, document_id, version_index, with_issues)
        return _validation(row) if row else None

    async def create_version(
        self,
        *,
        project_id: str,
        document_id: str | None,
        title: str,
        version_number: str,
        file_name: str,
        size_in_bytes: int,
        sha256: str,
        storage_key: str,
        author: str,
        metadata: list[DocumentMetadataEntry],
        requested_document_id: str | None = None,
        parent_version_index: int | None = None,
        approved_by: str | None = None,
        change_set_id: str | None = None,
        change_set: str | None = None,
    ) -> VersionRecord:
        """A new document (``document_id`` None) or a new version of an existing one, in one transaction: the
        document's row is locked while its next index is taken. The rest as the graph's ``create_version``."""
        now = now_iso()
        version_id = new_id()
        new_document_id = document_id or requested_document_id or new_id()
        entries = [entry.model_dump() for entry in metadata]
        derived = parent_version_index is not None  # the lineage is kept for a version built on another only

        async def work(tx: Tx) -> dict[str, Any]:
            if document_id is None:
                head = await tx.one(DOCUMENT_INSERT, new_document_id, project_id, title, now)
            else:
                head = await tx.one(DOCUMENT_NEXT, project_id, document_id, title)
            if head is None:
                raise HTTPException(404, "Document not found")
            index = int(head["index"])
            row = await tx.one(
                VERSION_INSERT,
                project_id,
                new_document_id,
                version_id,
                author,
                index,
                version_number or str(index),
                now,
                title,
                file_name,
                size_in_bytes,
                sha256,
                storage_key,
                entries,
                parent_version_index,
                approved_by if derived else None,
                change_set_id if derived else None,
                change_set if derived else None,
            )
            if row is None:
                raise HTTPException(404, "Project not found")
            return row

        return _record(await self.postgres.write(work))

    async def versions_since(self, *, user_id: str, document_id: str, since: int, until: int) -> list[dict[str, Any]]:
        """The versions after `since` up to `until`, each with its change set unpacked, or none for a whole file."""
        return [_change(row) for row in await self.postgres.run(VERSIONS_SINCE, user_id, document_id, since, until)]

    async def change_set(self, *, user_id: str, document_id: str, version_index: int) -> dict[str, Any] | None:
        """The change set a version was approved from (ADR 0021), unpacked; None when it has none."""
        row = await self.postgres.one(CHANGE_SET, user_id, document_id, version_index)
        return _change_set(row, document_id) if row else None

    async def publication(self, *, user_id: str, document_id: str, version_index: int) -> dict[str, Any] | None:
        """The publication of a version (F9 a), or None while it is not published."""
        return await self.postgres.one(PUBLICATION, user_id, document_id, version_index)

    async def publish(
        self,
        *,
        user_id: str,
        document_id: str,
        version_index: int,
        publication: dict[str, Any],
        audit_event: dict[str, Any],
    ) -> bool:
        """Mark a version published with its stored archive, as the graph's ``publish``; False when it already was,
        also when two publish at once. The audit event follows the publication into the graph's audit log."""
        row = await self.postgres.one(
            PUBLISH,
            user_id,
            document_id,
            version_index,
            publication["id"],
            publication["storage_key"],
            publication["file_name"],
            publication["size_in_bytes"],
            publication["sha256"],
            publication["published_at"],
            publication["published_by"],
        )
        if row is None:
            return False
        if self.audit_graph is not None:
            await audit.record(self.audit_graph, **audit_event)
        return True


# -- the upload and selection sessions ---------------------------------------------------------------------------

UPLOAD_INSERT = """
INSERT INTO upload_sessions (
    id, token_hash, user_id, username, callback_url, callback_expires_at, created_at, expires_at, server_context,
    project_id, state, files
)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NULL, $10, $11::jsonb)
"""
UPLOAD_BY_HASH = """
SELECT s.id, s.user_id, s.username, s.callback_url, s.callback_expires_at, s.expires_at, s.server_context,
       s.project_id, s.state, s.files
FROM upload_sessions s WHERE s.token_hash = $1 AND s.expires_at > $2
"""
UPLOAD_BY_ID = """
SELECT s.id, s.user_id, s.username, s.callback_url, s.callback_expires_at, s.expires_at, s.server_context,
       s.project_id, s.state, s.files
FROM upload_sessions s WHERE s.id = $1 AND s.expires_at > $2
"""
UPLOAD_UPDATE = """
UPDATE upload_sessions s
SET state = coalesce($2::text, s.state), project_id = coalesce($3::text, s.project_id),
    files = coalesce($4::jsonb, s.files), expires_at = CASE WHEN $5::boolean THEN $6::text ELSE s.expires_at END
WHERE s.id = $1
"""
PARTS_INSERT = """
INSERT INTO upload_parts (id, session_id, file_index, part_index, range_start, range_end, received, expires_at)
SELECT r.id, s.id, $2::integer, r.part_index, r.range_start, r.range_end, false, $3
FROM upload_sessions s,
     unnest($4::text[], $5::integer[], $6::bigint[], $7::bigint[]) AS r (id, part_index, range_start, range_end)
WHERE s.id = $1
"""
PART = """
SELECT p.id, p.file_index, p.part_index, p.range_start, p.range_end, p.received, p.storage_key, p.size, p.expires_at,
       s.user_id, s.id AS session_id
FROM upload_parts p JOIN upload_sessions s ON s.id = p.session_id
WHERE p.id = $1 AND p.expires_at > $2
"""
PART_RECEIVED = "UPDATE upload_parts SET received = true, storage_key = $2, size = $3 WHERE id = $1"
PARTS = """
SELECT p.id, p.file_index, p.part_index, p.range_start, p.range_end, p.received, p.storage_key, p.size, p.expires_at
FROM upload_parts p WHERE p.session_id = $1 AND p.file_index = $2
ORDER BY p.part_index
"""
PARTS_DELETE = "DELETE FROM upload_parts WHERE session_id = $1 AND file_index = $2 RETURNING storage_key"


def _upload(row: dict[str, Any]) -> UploadSession:
    return UploadSession(
        id=row["id"],
        user_id=row["user_id"],
        username=row["username"],
        callback_url=row["callback_url"],
        callback_expires_at=row["callback_expires_at"],
        expires_at=row["expires_at"],
        server_context=row["server_context"],
        project_id=row["project_id"],
        state=row["state"],
        files=list(row["files"] or []),
    )


class PostgresUploadSessionRepository:
    def __init__(self, postgres: Postgres, *, ui_ttl_seconds: int, upload_ttl_seconds: int) -> None:
        self.postgres = postgres
        self.ui_ttl_seconds = ui_ttl_seconds
        self.upload_ttl_seconds = upload_ttl_seconds

    async def create(
        self,
        *,
        user_id: str,
        username: str,
        callback_url: str,
        callback_expires_in: int,
        server_context: str | None,
        files: list[dict[str, Any]],
    ) -> tuple[str, str]:
        """Returns ``(session id, UI token)``; only the token's hash is stored."""
        token = new_secret()
        session_id = new_id()
        await self.postgres.execute(
            UPLOAD_INSERT,
            session_id,
            hash_secret(token),
            user_id,
            username,
            callback_url,
            later_iso(callback_expires_in),
            now_iso(),
            later_iso(self.ui_ttl_seconds),
            server_context,
            STATE_NEW,
            files,
        )
        return session_id, token

    async def by_token(self, token: str) -> UploadSession | None:
        if not token or len(token) > MAX_TOKEN_LENGTH:
            return None
        row = await self.postgres.one(UPLOAD_BY_HASH, hash_secret(token), now_iso())
        return _upload(row) if row else None

    async def by_id(self, session_id: str) -> UploadSession | None:
        row = await self.postgres.one(UPLOAD_BY_ID, session_id, now_iso())
        return _upload(row) if row else None

    async def update(
        self,
        session_id: str,
        *,
        state: str | None = None,
        project_id: str | None = None,
        files: list[dict[str, Any]] | None = None,
        extend: bool = False,
    ) -> None:
        await self.postgres.execute(
            UPLOAD_UPDATE, session_id, state, project_id, files, extend, later_iso(self.upload_ttl_seconds)
        )

    # -- parts ---------------------------------------------------------------------------------

    async def create_parts(self, session_id: str, file_index: int, ranges: list[tuple[int, int]]) -> list[str]:
        """One part per range for the file, as the graph's ``create_parts``. Returns the part ids in range order."""
        ids = [new_id() for _ in ranges]
        await self.postgres.execute(
            PARTS_INSERT,
            session_id,
            file_index,
            later_iso(self.upload_ttl_seconds),
            ids,
            list(range(len(ranges))),
            [start for start, _ in ranges],
            [end for _, end in ranges],
        )
        return ids

    async def part(self, part_id: str) -> dict[str, Any] | None:
        """The part with its session's user and id, or None when unknown or expired."""
        return await self.postgres.one(PART, part_id, now_iso())

    async def mark_received(self, part_id: str, storage_key: str, size: int) -> None:
        await self.postgres.execute(PART_RECEIVED, part_id, storage_key, size)

    async def parts(self, session_id: str, file_index: int) -> list[dict[str, Any]]:
        return await self.postgres.run(PARTS, session_id, file_index)

    async def delete_parts(self, session_id: str, file_index: int) -> list[str]:
        """Delete the file's parts; returns the storage keys of parts that were received."""
        rows = await self.postgres.run(PARTS_DELETE, session_id, file_index)
        return [row["storage_key"] for row in rows if row["storage_key"]]


SELECTION_INSERT = """
INSERT INTO selection_sessions (
    id, token_hash, user_id, callback_url, callback_expires_at, created_at, expires_at, server_context, extensions,
    state
)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::text[], $10)
"""
SELECTION_BY_HASH = """
SELECT s.id, s.user_id, s.callback_url, s.callback_expires_at, s.expires_at, s.server_context, s.extensions, s.state,
       s.selected
FROM selection_sessions s WHERE s.token_hash = $1 AND s.expires_at > $2
"""
SELECTION_BY_ID = """
SELECT s.id, s.user_id, s.callback_url, s.callback_expires_at, s.expires_at, s.server_context, s.extensions, s.state,
       s.selected
FROM selection_sessions s WHERE s.id = $1 AND s.expires_at > $2
"""
SELECTION_FINISH = "UPDATE selection_sessions SET state = $2, selected = $3::text[] WHERE id = $1"


def _selection(row: dict[str, Any]) -> SelectionSession:
    return SelectionSession(
        id=row["id"],
        user_id=row["user_id"],
        callback_url=row["callback_url"],
        callback_expires_at=row["callback_expires_at"],
        expires_at=row["expires_at"],
        server_context=row["server_context"],
        extensions=list(row["extensions"] or []),
        state=row["state"],
        selected=list(row["selected"] or []),
    )


class PostgresSelectionSessionRepository:
    def __init__(self, postgres: Postgres, *, ui_ttl_seconds: int) -> None:
        self.postgres = postgres
        self.ui_ttl_seconds = ui_ttl_seconds

    async def create(
        self,
        *,
        user_id: str,
        callback_url: str,
        callback_expires_in: int,
        server_context: str | None,
        extensions: list[str],
    ) -> tuple[str, str]:
        token = new_secret()
        session_id = new_id()
        await self.postgres.execute(
            SELECTION_INSERT,
            session_id,
            hash_secret(token),
            user_id,
            callback_url,
            later_iso(callback_expires_in),
            now_iso(),
            later_iso(self.ui_ttl_seconds),
            server_context,
            list(extensions),
            STATE_NEW,
        )
        return session_id, token

    async def by_token(self, token: str) -> SelectionSession | None:
        if not token or len(token) > MAX_TOKEN_LENGTH:
            return None
        row = await self.postgres.one(SELECTION_BY_HASH, hash_secret(token), now_iso())
        return _selection(row) if row else None

    async def by_id(self, session_id: str) -> SelectionSession | None:
        row = await self.postgres.one(SELECTION_BY_ID, session_id, now_iso())
        return _selection(row) if row else None

    async def finish(self, session_id: str, *, state: str, selected: list[str]) -> None:
        await self.postgres.execute(SELECTION_FINISH, session_id, state, list(selected))


# -- where the documents are -------------------------------------------------------------------------------------


def document_store(graph: Graph, postgres: Postgres | None) -> DocumentStore:
    if postgres is not None:
        return PostgresDocumentRepository(postgres, audit_graph=graph)
    return DocumentRepository(graph)


def upload_session_store(graph: Graph, postgres: Postgres | None, settings: Settings) -> UploadSessionStore:
    ui, upload = settings.documents_session_ttl_seconds, settings.upload_session_ttl_seconds
    if postgres is not None:
        return PostgresUploadSessionRepository(postgres, ui_ttl_seconds=ui, upload_ttl_seconds=upload)
    return UploadSessionRepository(graph, ui_ttl_seconds=ui, upload_ttl_seconds=upload)


def selection_session_store(graph: Graph, postgres: Postgres | None, settings: Settings) -> SelectionSessionStore:
    if postgres is not None:
        return PostgresSelectionSessionRepository(postgres, ui_ttl_seconds=settings.documents_session_ttl_seconds)
    return SelectionSessionRepository(graph, ui_ttl_seconds=settings.documents_session_ttl_seconds)
