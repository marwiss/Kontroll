# This file was generated with the assistance of an AI coding tool.
"""Upload and selection sessions of the Documents API, and the parts of an upload.

A session is created by an API call and continued in the browser: the client
receives a UI URL that carries a 256-bit token. The graph stores only the
token's hash; the API-side URLs (instructions, completion, cancellation) use
the session's public id instead, so the secret appears in as few places as
possible. Sessions and parts carry ``expires_at`` and are swept by the
cleanup job, which also removes the part files.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends

from opencde.deps import GraphDep, SettingsDep
from opencde.graph.graph import Graph
from opencde.ids import hash_secret, new_id, new_secret
from opencde.timeutil import later_iso, now_iso

STATE_NEW = "new"  # waiting for the user to fill in metadata or select
STATE_METADATA = "metadata"  # metadata saved; waiting for upload instructions
STATE_UPLOADING = "uploading"
STATE_SELECTED = "selected"
STATE_CANCELLED = "cancelled"

FILE_PENDING = "pending"
FILE_PARTS = "parts"
FILE_DONE = "done"
FILE_CANCELLED = "cancelled"


@dataclass(frozen=True)
class UploadSession:
    id: str
    user_id: str
    username: str
    callback_url: str
    callback_expires_at: str
    expires_at: str
    server_context: str | None
    project_id: str | None
    state: str
    files: list[dict[str, Any]]

    @property
    def callback_expired(self) -> bool:
        return self.callback_expires_at <= now_iso()


@dataclass(frozen=True)
class SelectionSession:
    id: str
    user_id: str
    callback_url: str
    callback_expires_at: str
    expires_at: str
    server_context: str | None
    extensions: list[str]
    state: str
    selected: list[str]  # "document_id:version_index"

    @property
    def callback_expired(self) -> bool:
        return self.callback_expires_at <= now_iso()


def _upload(node: dict[str, Any]) -> UploadSession:
    return UploadSession(
        id=node["id"],
        user_id=node["user_id"],
        username=node["username"],
        callback_url=node["callback_url"],
        callback_expires_at=node["callback_expires_at"],
        expires_at=node["expires_at"],
        server_context=node.get("server_context"),
        project_id=node.get("project_id"),
        state=node["state"],
        files=json.loads(node.get("files_json") or "[]"),
    )


def _selection(node: dict[str, Any]) -> SelectionSession:
    return SelectionSession(
        id=node["id"],
        user_id=node["user_id"],
        callback_url=node["callback_url"],
        callback_expires_at=node["callback_expires_at"],
        expires_at=node["expires_at"],
        server_context=node.get("server_context"),
        extensions=list(node.get("extensions") or []),
        state=node["state"],
        selected=list(node.get("selected") or []),
    )


class UploadSessionRepository:
    def __init__(self, graph: Graph, *, ui_ttl_seconds: int, upload_ttl_seconds: int) -> None:
        self.graph = graph
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
        """Returns ``(session id, UI token)``."""
        token = new_secret()
        session_id = new_id()
        await self.graph.run(
            """
            CREATE (:UploadSession {
                id: $id, token_hash: $token_hash, user_id: $user_id, username: $username,
                callback_url: $callback_url, callback_expires_at: $callback_expires_at,
                created_at: $now, expires_at: $expires_at, server_context: $server_context,
                project_id: null, state: $state, files_json: $files_json
            })
            """,
            id=session_id,
            token_hash=hash_secret(token),
            user_id=user_id,
            username=username,
            callback_url=callback_url,
            callback_expires_at=later_iso(callback_expires_in),
            now=now_iso(),
            expires_at=later_iso(self.ui_ttl_seconds),
            server_context=server_context,
            state=STATE_NEW,
            files_json=json.dumps(files),
        )
        return session_id, token

    async def by_token(self, token: str) -> UploadSession | None:
        if not token or len(token) > 128:
            return None
        row = await self.graph.one(
            "MATCH (s:UploadSession {token_hash: $hash}) WHERE s.expires_at > $now RETURN properties(s) AS s",
            hash=hash_secret(token),
            now=now_iso(),
        )
        return _upload(row["s"]) if row else None

    async def by_id(self, session_id: str) -> UploadSession | None:
        row = await self.graph.one(
            "MATCH (s:UploadSession {id: $id}) WHERE s.expires_at > $now RETURN properties(s) AS s",
            id=session_id,
            now=now_iso(),
        )
        return _upload(row["s"]) if row else None

    async def update(
        self,
        session_id: str,
        *,
        state: str | None = None,
        project_id: str | None = None,
        files: list[dict[str, Any]] | None = None,
        extend: bool = False,
    ) -> None:
        await self.graph.run(
            """
            MATCH (s:UploadSession {id: $id})
            SET s.state = coalesce($state, s.state),
                s.project_id = coalesce($project_id, s.project_id),
                s.files_json = coalesce($files_json, s.files_json),
                s.expires_at = CASE WHEN $extend THEN $extended ELSE s.expires_at END
            """,
            id=session_id,
            state=state,
            project_id=project_id,
            files_json=json.dumps(files) if files is not None else None,
            extend=extend,
            extended=later_iso(self.upload_ttl_seconds),
        )

    # -- parts ---------------------------------------------------------------------------------

    async def create_parts(self, session_id: str, file_index: int, ranges: list[tuple[int, int]]) -> list[str]:
        """Create one ``UploadPart`` per range for the file. Returns the part ids in range order."""
        rows: list[dict[str, Any]] = [
            {"id": new_id(), "index": index, "start": start, "end": end} for index, (start, end) in enumerate(ranges)
        ]
        await self.graph.run(
            """
            MATCH (s:UploadSession {id: $session_id})
            UNWIND $rows AS row
            CREATE (s)-[:HAS_PART]->(:UploadPart {
                id: row.id, file_index: $file_index, part_index: row.index, range_start: row.start,
                range_end: row.end, received: false, storage_key: null, expires_at: $expires_at
            })
            """,
            session_id=session_id,
            file_index=file_index,
            rows=rows,
            expires_at=later_iso(self.upload_ttl_seconds),
        )
        return [row["id"] for row in rows]

    async def part(self, part_id: str) -> dict[str, Any] | None:
        """The part with its session's user and id, or None when unknown or expired."""
        row = await self.graph.one(
            """
            MATCH (s:UploadSession)-[:HAS_PART]->(p:UploadPart {id: $id})
            WHERE p.expires_at > $now
            RETURN properties(p) AS part, s.user_id AS user_id, s.id AS session_id
            """,
            id=part_id,
            now=now_iso(),
        )
        if row is None:
            return None
        return {**row["part"], "user_id": row["user_id"], "session_id": row["session_id"]}

    async def mark_received(self, part_id: str, storage_key: str, size: int) -> None:
        await self.graph.run(
            "MATCH (p:UploadPart {id: $id}) SET p.received = true, p.storage_key = $key, p.size = $size",
            id=part_id,
            key=storage_key,
            size=size,
        )

    async def parts(self, session_id: str, file_index: int) -> list[dict[str, Any]]:
        rows = await self.graph.run(
            """
            MATCH (:UploadSession {id: $session_id})-[:HAS_PART]->(p:UploadPart {file_index: $file_index})
            RETURN properties(p) AS part ORDER BY p.part_index
            """,
            session_id=session_id,
            file_index=file_index,
        )
        return [row["part"] for row in rows]

    async def delete_parts(self, session_id: str, file_index: int) -> list[str]:
        """Delete the file's part nodes; returns the storage keys of parts that were received."""
        rows = await self.graph.run(
            """
            MATCH (:UploadSession {id: $session_id})-[:HAS_PART]->(p:UploadPart {file_index: $file_index})
            WITH p, p.storage_key AS key
            DETACH DELETE p
            RETURN key
            """,
            session_id=session_id,
            file_index=file_index,
        )
        return [row["key"] for row in rows if row["key"]]


class SelectionSessionRepository:
    def __init__(self, graph: Graph, *, ui_ttl_seconds: int) -> None:
        self.graph = graph
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
        await self.graph.run(
            """
            CREATE (:SelectionSession {
                id: $id, token_hash: $token_hash, user_id: $user_id, callback_url: $callback_url,
                callback_expires_at: $callback_expires_at, created_at: $now, expires_at: $expires_at,
                server_context: $server_context, extensions: $extensions, state: $state, selected: []
            })
            """,
            id=session_id,
            token_hash=hash_secret(token),
            user_id=user_id,
            callback_url=callback_url,
            callback_expires_at=later_iso(callback_expires_in),
            now=now_iso(),
            expires_at=later_iso(self.ui_ttl_seconds),
            server_context=server_context,
            extensions=extensions,
            state=STATE_NEW,
        )
        return session_id, token

    async def by_token(self, token: str) -> SelectionSession | None:
        if not token or len(token) > 128:
            return None
        row = await self.graph.one(
            "MATCH (s:SelectionSession {token_hash: $hash}) WHERE s.expires_at > $now RETURN properties(s) AS s",
            hash=hash_secret(token),
            now=now_iso(),
        )
        return _selection(row["s"]) if row else None

    async def by_id(self, session_id: str) -> SelectionSession | None:
        row = await self.graph.one(
            "MATCH (s:SelectionSession {id: $id}) WHERE s.expires_at > $now RETURN properties(s) AS s",
            id=session_id,
            now=now_iso(),
        )
        return _selection(row["s"]) if row else None

    async def finish(self, session_id: str, *, state: str, selected: list[str]) -> None:
        await self.graph.run(
            "MATCH (s:SelectionSession {id: $id}) SET s.state = $state, s.selected = $selected",
            id=session_id,
            state=state,
            selected=selected,
        )


def upload_sessions(graph: GraphDep, settings: SettingsDep) -> UploadSessionRepository:
    return UploadSessionRepository(
        graph,
        ui_ttl_seconds=settings.documents_session_ttl_seconds,
        upload_ttl_seconds=settings.upload_session_ttl_seconds,
    )


def selection_sessions(graph: GraphDep, settings: SettingsDep) -> SelectionSessionRepository:
    return SelectionSessionRepository(graph, ui_ttl_seconds=settings.documents_session_ttl_seconds)


UploadSessionsDep = Annotated[UploadSessionRepository, Depends(upload_sessions)]
SelectionSessionsDep = Annotated[SelectionSessionRepository, Depends(selection_sessions)]
