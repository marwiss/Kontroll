# This file was generated with the assistance of an AI coding tool.
"""The server's records of the merges (IFC-DB F21 a and F22 a, ADR 0025): a ``Merge`` under the project merged into.

``ifcgraph/merging.py`` runs the job; this repository keeps its kind (``merge``, or ``prepare`` for a copy of B made
ready for A), the request as the server wrote it (JSON), the lifecycle (``queued``, ``running``, then ``done``,
``failed`` or ``conflict``, and ``expired`` for a preparation whose day is over), the model the job makes, and the
result: the packed report, the error, the version a merge became, and when a preparation's model stops standing in
for B (``expires_at``; the job's round takes the model out and keeps the record).
"""

from __future__ import annotations

from typing import Any

from opencde.graph.graph import Graph
from opencde.timeutil import now_iso

STATE_QUEUED = "queued"
STATE_RUNNING = "running"
STATE_DONE = "done"
KIND_MERGE = "merge"
KIND_PREPARE = "prepare"  # B made ready for A: migrated to its schema, with its lengths in its unit


class MergeRepository:
    """The merges and preparations of the projects, by the job's id."""

    def __init__(self, graph: Graph) -> None:
        self.graph = graph

    async def create(self, *, merge_id: str, project_id: str, kind: str, author: str, request: str) -> None:
        await self.graph.run(
            """
            MATCH (p:Project {project_id: $project_id})
            CREATE (p)-[:HAS_MERGE]->(:Merge {
                id: $id, project_id: $project_id, kind: $kind, state: $state, request: $request, author: $author,
                created_at: $now
            })
            """,
            project_id=project_id,
            id=merge_id,
            kind=kind,
            state=STATE_QUEUED,
            request=request,
            author=author,
            now=now_iso(),
        )

    async def claim(self, merge_id: str, *, model_id: str) -> dict[str, Any] | None:
        """The queued job's project, request, author and kind, now this process's to run with the model
        ``model_id``; None when it is not queued."""
        return await self.graph.one(
            """
            MATCH (j:Merge {id: $id, state: $queued})
            SET j.state = $running, j.running_at = $now, j.model_id = $model_id
            RETURN j.project_id AS project_id, j.request AS request, j.author AS author, j.kind AS kind
            """,
            id=merge_id,
            queued=STATE_QUEUED,
            running=STATE_RUNNING,
            now=now_iso(),
            model_id=model_id,
        )

    async def set_state(self, merge_id: str, state: str, **fields: Any) -> None:
        """The job's new state, with ``finished_at`` and the fields of its result."""
        await self.graph.run(
            "MATCH (j:Merge {id: $id}) SET j.state = $state, j += $fields",
            id=merge_id,
            state=state,
            fields={"finished_at": now_iso(), **fields},
        )

    async def prepared(self, *, user_id: str, project_id: str, prepare_id: str) -> dict[str, Any] | None:
        """A preparation of a project the user is a member of that is done and has not expired: its model's id and
        its request (JSON)."""
        return await self.graph.one(
            """
            MATCH (:User {id: $user_id})-[:MEMBER_OF]->(:Project {project_id: $project_id})
                  -[:HAS_MERGE]->(j:Merge {id: $id, kind: $kind, state: $done})
            WHERE j.expires_at > $now
            RETURN j.model_id AS model_id, j.request AS request
            """,
            user_id=user_id,
            project_id=project_id,
            id=prepare_id,
            kind=KIND_PREPARE,
            done=STATE_DONE,
            now=now_iso(),
        )

    async def get(self, *, user_id: str, project_id: str, merge_id: str) -> dict[str, Any] | None:
        """One job, as it is kept, when the user is a member of its project."""
        row = await self.graph.one(
            """
            MATCH (:User {id: $user_id})-[:MEMBER_OF]->(:Project {project_id: $project_id})-[:HAS_MERGE]->(j:Merge {id: $id})
            RETURN properties(j) AS merge
            """,
            user_id=user_id,
            project_id=project_id,
            id=merge_id,
        )
        return dict(row["merge"]) if row else None

    async def expired_preparations(self) -> list[dict[str, Any]]:
        """The preparations whose day is over and whose model is still to be taken out: ``id`` and ``model_id``."""
        return await self.graph.run(
            "MATCH (j:Merge {kind: $kind, state: $done}) WHERE j.expires_at <= $now RETURN j.id AS id, j.model_id AS model_id",
            kind=KIND_PREPARE,
            done=STATE_DONE,
            now=now_iso(),
        )

    async def interrupted(self, *, given_up: str) -> list[dict[str, Any]]:
        """The jobs a stopped server left behind: queued, or running since before ``given_up``."""
        return await self.graph.run(
            """
            MATCH (j:Merge)
            WHERE j.state = $queued OR (j.state = $running AND j.running_at < $given_up)
            RETURN j.id AS id, j.state AS state, j.model_id AS model_id
            """,
            queued=STATE_QUEUED,
            running=STATE_RUNNING,
            given_up=given_up,
        )
