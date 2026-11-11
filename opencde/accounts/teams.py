# This file was generated with the assistance of an AI coding tool.
"""The teams of a project and the part of the model each answers for (F11 b, F19 a, F20 a, F21 b).

A ``manager`` of the project sets a team up: a name, a responsible member with at least the role ``editor``, the
members, and an IDS document of the project whose specifications point out the team's part of the model, the building
elements they apply to. A change set that touches the part of one team is approved by that team's responsible alone;
one that touches the parts of several teams, or of none, by a ``manager``. The nodes are
``(:Project)-[:HAS_TEAM]->(:Team)``, with ``RESPONSIBLE`` and ``HAS_MEMBER`` to the users.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends

from opencde.deps import GraphDep
from opencde.graph.graph import Graph, Tx
from opencde.ids import new_id
from opencde.timeutil import now_iso

MAX_TEAMS = 100  # teams of one project
MAX_MEMBERS = 500  # members of one team

_LIST = """
MATCH (p:Project {project_id: $project_id})-[:HAS_TEAM]->(t:Team)
WHERE $team_id IS NULL OR t.id = $team_id
OPTIONAL MATCH (t)-[:RESPONSIBLE]->(r:User)
OPTIONAL MATCH (t)-[:HAS_MEMBER]->(m:User)-[:MEMBER_OF]->(p)
WITH t, r, collect(DISTINCT m.username) AS members
RETURN t.id AS team_id, t.name AS name, t.ids_document_id AS ids_document_id, r.id AS responsible_user_id,
       r.username AS responsible, members, t.created_at AS created_at, t.updated_at AS updated_at
ORDER BY t.name, t.id
LIMIT $limit
"""


def _team(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "team_id": row["team_id"],
        "name": row["name"],
        "responsible": row["responsible"],
        "responsible_user_id": row["responsible_user_id"],
        "members": sorted(row["members"] or []),
        "ids_document_id": row["ids_document_id"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


class TeamRepository:
    def __init__(self, graph: Graph) -> None:
        self.graph = graph

    async def of_project(self, project_id: str) -> list[dict[str, Any]]:
        rows = await self.graph.run(_LIST, project_id=project_id, team_id=None, limit=MAX_TEAMS)
        return [_team(row) for row in rows]

    async def get(self, project_id: str, team_id: str) -> dict[str, Any] | None:
        row = await self.graph.one(_LIST, project_id=project_id, team_id=team_id, limit=1)
        return _team(row) if row else None

    async def save(
        self,
        project_id: str,
        *,
        team_id: str | None,
        name: str,
        responsible_user_id: str,
        member_ids: list[str],
        ids_document_id: str,
    ) -> str | None:
        """Make a team, or set every field of one (``team_id``); its id, or None for a team the project lacks."""
        wanted = team_id or new_id()

        async def work(tx: Tx) -> str | None:
            if team_id is None:
                rows = await tx.run(
                    """
                    MATCH (p:Project {project_id: $project_id})
                    CREATE (p)-[:HAS_TEAM]->(t:Team {id: $id, created_at: $now})
                    RETURN t.id AS id
                    """,
                    project_id=project_id,
                    id=wanted,
                    now=now_iso(),
                )
            else:
                rows = await tx.run(
                    "MATCH (:Project {project_id: $project_id})-[:HAS_TEAM]->(t:Team {id: $id}) RETURN t.id AS id",
                    project_id=project_id,
                    id=wanted,
                )
            if not rows:
                return None
            await tx.run("MATCH (:Team {id: $id})-[old:RESPONSIBLE|HAS_MEMBER]->(:User) DELETE old", id=wanted)
            await tx.run(
                """
                MATCH (t:Team {id: $id}), (r:User {id: $responsible})
                SET t.name = $name, t.ids_document_id = $ids_document_id, t.updated_at = $now
                CREATE (t)-[:RESPONSIBLE]->(r)
                WITH t
                UNWIND $members AS member_id
                MATCH (u:User {id: member_id})
                CREATE (t)-[:HAS_MEMBER]->(u)
                """,
                id=wanted,
                responsible=responsible_user_id,
                name=name,
                ids_document_id=ids_document_id,
                now=now_iso(),
                members=sorted(set(member_ids)),
            )
            return wanted

        return await self.graph.write(work)

    async def delete(self, project_id: str, team_id: str) -> bool:
        rows = await self.graph.run(
            """
            MATCH (:Project {project_id: $project_id})-[:HAS_TEAM]->(t:Team {id: $id})
            WITH t, t.id AS id
            DETACH DELETE t
            RETURN id
            """,
            project_id=project_id,
            id=team_id,
        )
        return bool(rows)

    async def parts(self, project_id: str) -> list[dict[str, Any]]:
        """Each team with the file of the latest version of its IDS document, for the trial of a change set."""
        return await self.graph.run(
            """
            MATCH (p:Project {project_id: $project_id})-[:HAS_TEAM]->(t:Team)
            OPTIONAL MATCH (t)-[:RESPONSIBLE]->(r:User)
            MATCH (p)-[:HAS_DOCUMENT]->(d:Document)-[:HAS_VERSION]->(v:DocumentVersion)
            WHERE d.document_id = t.ids_document_id
            WITH t, r, v ORDER BY v.version_index DESC
            WITH t, r, collect(v)[0] AS v
            RETURN t.id AS team_id, t.name AS name, r.id AS responsible_user_id, r.username AS responsible,
                   v.storage_key AS storage_key, v.version_index AS ids_version_index
            ORDER BY t.name, t.id
            LIMIT $limit
            """,
            project_id=project_id,
            limit=MAX_TEAMS,
        )


def team_repository(graph: GraphDep) -> TeamRepository:
    return TeamRepository(graph)


TeamsDep = Annotated[TeamRepository, Depends(team_repository)]
