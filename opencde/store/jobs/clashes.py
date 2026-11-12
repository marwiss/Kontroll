# This file was generated with the assistance of an AI coding tool.
"""The server's records of the clash checks between two document versions (ADR 0019): a ``Clash`` under its project.

The IFC-DB service runs a check in its worker (``ifcgraph/service.py``); this repository keeps the request as the
server wrote it (JSON), the lifecycle (``queued``, ``running``, ``done``, ``failed``) with its times, and the report:
the counts, the time it took and the clashes, packed. A member of the project reads them, newest first.
"""

from __future__ import annotations

from typing import Any

from opencde.graph.graph import Graph
from opencde.timeutil import now_iso

STATE_QUEUED = "queued"
STATE_RUNNING = "running"
STATE_DONE = "done"
STATE_FAILED = "failed"
MAX_LISTED = 100  # the checks of a project a listing shows, newest first

#: The user's queued or running clash checks in all their projects, from the user's node through MEMBER_OF.
OPEN_CHECKS = """
MATCH (:User {id: $user_id})-[:MEMBER_OF]->(:Project)-[:HAS_CLASH]->(c:Clash)
WHERE c.author = $author AND c.state IN ['queued', 'running']
RETURN count(c) AS n
"""


class ClashRepository:
    """The clash checks of the projects, by the check's id."""

    def __init__(self, graph: Graph) -> None:
        self.graph = graph

    async def create(self, *, clash_id: str, project_id: str, author: str, request: str) -> None:
        await self.graph.run(
            """
            MATCH (p:Project {project_id: $project_id})
            CREATE (p)-[:HAS_CLASH]->(:Clash {
                id: $id, project_id: $project_id, state: $state, request: $request, author: $author, created_at: $now
            })
            """,
            project_id=project_id,
            id=clash_id,
            state=STATE_QUEUED,
            request=request,
            author=author,
            now=now_iso(),
        )

    async def claim(self, clash_id: str) -> dict[str, Any] | None:
        """The queued check's project and request, now this process's to run; None when it is not queued."""
        return await self.graph.one(
            """
            MATCH (c:Clash {id: $id, state: $queued})
            SET c.state = $running, c.running_at = $now
            RETURN c.project_id AS project_id, c.request AS request
            """,
            id=clash_id,
            queued=STATE_QUEUED,
            running=STATE_RUNNING,
            now=now_iso(),
        )

    async def fail(self, clash_id: str, *, error: str) -> None:
        await self.graph.run(
            "MATCH (c:Clash {id: $id}) SET c.state = $state, c.failed_at = $now, c.error = $error",
            id=clash_id,
            state=STATE_FAILED,
            now=now_iso(),
            error=error,
        )

    async def finish(
        self,
        clash_id: str,
        *,
        count: int,
        set_a: int,
        set_b: int,
        missing: int,
        seconds: float,
        truncated: bool,
        report: str,
    ) -> None:
        await self.graph.run(
            """
            MATCH (c:Clash {id: $id})
            SET c.state = $state, c.done_at = $now, c.count = $count, c.set_a = $set_a, c.set_b = $set_b,
                c.missing = $missing, c.seconds = $seconds, c.truncated = $truncated, c.report = $report
            """,
            id=clash_id,
            state=STATE_DONE,
            now=now_iso(),
            count=count,
            set_a=set_a,
            set_b=set_b,
            missing=missing,
            seconds=seconds,
            truncated=truncated,
            report=report,
        )

    async def of_project(self, *, user_id: str, project_id: str) -> list[dict[str, Any]]:
        """The checks of a project the user is a member of, newest first, as they are kept."""
        rows = await self.graph.run(
            """
            MATCH (:User {id: $user_id})-[:MEMBER_OF]->(:Project {project_id: $project_id})-[:HAS_CLASH]->(c:Clash)
            RETURN properties(c) AS clash ORDER BY c.created_at DESC LIMIT $limit
            """,
            user_id=user_id,
            project_id=project_id,
            limit=MAX_LISTED,
        )
        return [dict(row["clash"]) for row in rows]

    async def get(self, *, user_id: str, project_id: str, clash_id: str) -> dict[str, Any] | None:
        """One check, when the user is a member of its project."""
        rows = await self.graph.run(
            """
            MATCH (:User {id: $user_id})-[:MEMBER_OF]->(:Project {project_id: $project_id})
                  -[:HAS_CLASH]->(c:Clash {id: $clash_id})
            RETURN properties(c) AS clash
            """,
            user_id=user_id,
            project_id=project_id,
            clash_id=clash_id,
        )
        return dict(rows[0]["clash"]) if rows else None

    async def open_count(self, *, user_id: str, author: str) -> int:
        """How many checks the user has started that are queued or running, in all the user's projects."""
        rows = await self.graph.run(OPEN_CHECKS, user_id=user_id, author=author)
        return int(rows[0]["n"]) if rows else 0
