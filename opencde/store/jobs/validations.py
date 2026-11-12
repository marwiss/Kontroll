# This file was generated with the assistance of an AI coding tool.
"""The server's records of the checks of IFC files (ADR 0011, 0021): one ``Validation`` below a document version, and
the ``Precheck``, a file a member checked without making it a version, which is a ``Validation`` below the project
that the cleaner deletes with its file after ``PRECHECK_SECONDS``.

The IFC-DB service runs the checks (``ifcgraph/service.py``); this repository keeps their lifecycle (``queued``,
``running``, ``done``, ``failed``, each with its time) and the fields of the result: the counts, the rulesets, the
checks, the packed report and the rooms. The Documents API reads a version's check through the documents' own
repository; a precheck is read here, for a member of its project.
"""

from __future__ import annotations

from typing import Any

from opencde.graph.graph import Graph
from opencde.ids import new_id
from opencde.timeutil import later_iso, now_iso

STATE_QUEUED = "queued"
STATE_RUNNING = "running"
PRECHECK_SECONDS = 24 * 3600  # a file checked without becoming a version is kept this long (ADR 0021)


class ValidationRepository:
    """The checks of the uploads and the prechecks, by the check's id."""

    def __init__(self, graph: Graph) -> None:
        self.graph = graph

    async def queue(self, *, validation_id: str, version_id: str, storage_key: str, file_name: str) -> bool:
        """A queued check of a document version's file; False when the version is not there."""
        rows = await self.graph.run(
            """
            MATCH (v:DocumentVersion {id: $version_id})
            CREATE (v)-[:HAS_VALIDATION]->(r:Validation {
                id: $id, storage_key: $storage_key, file_name: $file_name, state: $state, created_at: $now
            })
            RETURN r.id AS id
            """,
            version_id=version_id,
            id=validation_id,
            storage_key=storage_key,
            file_name=file_name,
            state=STATE_QUEUED,
            now=now_iso(),
        )
        return bool(rows)

    async def record(self, *, version_id: str, storage_key: str, file_name: str, checked: dict[str, Any]) -> None:
        """A check made before the version existed becomes the version's check, with its ``state``."""
        now = now_iso()
        await self.graph.run(
            """
            MATCH (v:DocumentVersion {id: $version_id})
            CREATE (v)-[:HAS_VALIDATION]->(r:Validation {id: $id, storage_key: $storage_key, file_name: $file_name})
            SET r += $fields
            """,
            version_id=version_id,
            id=new_id(),
            storage_key=storage_key,
            file_name=file_name,
            fields={**checked, "created_at": now, f"{checked['state']}_at": now},
        )

    async def claim(self, validation_id: str) -> bool:
        """The queued check is this process's to run; False when another took it, or it is not queued."""
        rows = await self.graph.run(
            """
            MATCH (r:Validation {id: $id, state: $queued})
            SET r.state = $running, r.running_at = $now
            RETURN r.id AS id
            """,
            id=validation_id,
            queued=STATE_QUEUED,
            running=STATE_RUNNING,
            now=now_iso(),
        )
        return bool(rows)

    async def set_state(self, validation_id: str, state: str, **fields: Any) -> None:
        await self.graph.run(
            "MATCH (r:Validation {id: $id}) SET r.state = $state, r += $fields",
            id=validation_id,
            state=state,
            fields={**fields, f"{state}_at": now_iso()},
        )

    async def project_of(self, validation_id: str) -> str | None:
        """The project of a check: through the version for an upload, straight from the project for a precheck."""
        row = await self.graph.one(
            """
            MATCH (r:Validation {id: $id})
            OPTIONAL MATCH (r)<-[:HAS_VALIDATION]-(:DocumentVersion)<-[:HAS_VERSION]-(:Document)
                           <-[:HAS_DOCUMENT]-(p:Project)
            OPTIONAL MATCH (r)<-[:HAS_PRECHECK]-(q:Project)
            RETURN p.project_id AS of_version, q.project_id AS of_precheck
            """,
            id=validation_id,
        )
        if row is None:
            return None
        return row["of_version"] or row["of_precheck"]

    async def interrupted(self, *, given_up: str) -> list[dict[str, Any]]:
        """The checks a stopped server left behind, prechecks too: queued, or running since before ``given_up``."""
        return await self.graph.run(
            """
            MATCH (r:Validation)
            WHERE r.state = $queued OR (r.state = $running AND r.running_at < $given_up)
            RETURN r.id AS id, r.storage_key AS storage_key, r.file_name AS file_name, r.state AS state
            """,
            queued=STATE_QUEUED,
            running=STATE_RUNNING,
            given_up=given_up,
        )

    async def open_precheck(
        self, *, precheck_id: str, project_id: str, storage_key: str, file_name: str, author: str
    ) -> bool:
        """A queued precheck of a file a member sent to try; False when the project is not there."""
        rows = await self.graph.run(
            """
            MATCH (p:Project {project_id: $project_id})
            CREATE (p)-[:HAS_PRECHECK]->(r:Validation:Precheck {
                id: $id, project_id: $project_id, storage_key: $storage_key, file_name: $file_name,
                author: $author, state: $state, created_at: $now, expires_at: $expires_at
            })
            RETURN r.id AS id
            """,
            project_id=project_id,
            id=precheck_id,
            storage_key=storage_key,
            file_name=file_name,
            author=author,
            state=STATE_QUEUED,
            now=now_iso(),
            expires_at=later_iso(PRECHECK_SECONDS),
        )
        return bool(rows)

    async def keep_precheck(
        self,
        *,
        precheck_id: str,
        project_id: str,
        storage_key: str,
        file_name: str,
        author: str,
        checked: dict[str, Any],
    ) -> None:
        """A refused upload stays as a precheck with the check that refused it, so that its report can be read."""
        now = now_iso()
        await self.graph.run(
            """
            MATCH (p:Project {project_id: $project_id})
            CREATE (p)-[:HAS_PRECHECK]->(r:Validation:Precheck {
                id: $id, project_id: $project_id, storage_key: $storage_key, file_name: $file_name,
                author: $author, created_at: $now, expires_at: $expires_at
            })
            SET r += $fields
            """,
            project_id=project_id,
            id=precheck_id,
            storage_key=storage_key,
            file_name=file_name,
            author=author,
            now=now,
            expires_at=later_iso(PRECHECK_SECONDS),
            fields={**checked, f"{checked['state']}_at": now},
        )

    async def precheck(self, *, user_id: str, project_id: str, precheck_id: str) -> dict[str, Any] | None:
        """A precheck of a project the user is a member of, as it is kept (its report packed); None without one."""
        row = await self.graph.one(
            """
            MATCH (:User {id: $user_id})-[:MEMBER_OF]->(:Project {project_id: $project_id})
                  -[:HAS_PRECHECK]->(r:Precheck {id: $id})
            RETURN properties(r) AS node
            """,
            user_id=user_id,
            project_id=project_id,
            id=precheck_id,
        )
        return dict(row["node"]) if row else None
