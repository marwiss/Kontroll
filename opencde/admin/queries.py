# This file was generated with the assistance of an AI coding tool.
"""Read-only aggregates for the admin pages.

These queries are the one place that does not start at a user node: they
run only for administrators, who see the whole server.
"""

from __future__ import annotations

from typing import Any

from opencde.graph.graph import Graph
from opencde.timeutil import now_iso


async def counts(graph: Graph) -> dict[str, int]:
    row = await graph.one(
        """
        OPTIONAL MATCH (u:User) WITH count(u) AS users
        OPTIONAL MATCH (p:Project) WITH users, count(p) AS projects
        OPTIONAL MATCH (c:Client) WITH users, projects, count(c) AS clients
        OPTIONAL MATCH (t:Topic) WITH users, projects, clients, count(t) AS topics
        OPTIONAL MATCH (d:Document) WITH users, projects, clients, topics, count(d) AS documents
        OPTIONAL MATCH (b:BcfDocument) WITH users, projects, clients, topics, documents, count(b) AS bcf_documents
        OPTIONAL MATCH (rt:RefreshToken {spent: false}) WHERE rt.expires_at > $now
        RETURN users, projects, clients, topics, documents, bcf_documents, count(rt) AS sessions
        """,
        now=now_iso(),
    )
    return {key: int(value or 0) for key, value in (row or {}).items()}


async def active_families(graph: Graph, limit: int = 500) -> list[dict[str, Any]]:
    """Live refresh-token families: who authorised which application, until when."""
    return await graph.run(
        """
        MATCH (rt:RefreshToken {spent: false})-[:FOR]->(u:User), (rt)-[:ISSUED_TO]->(c:Client)
        WHERE rt.expires_at > $now
        RETURN rt.family_id AS family_id, u.id AS user_id, u.username AS username, c.client_id AS client_id,
               c.name AS client_name, rt.scope AS scope, rt.created_at AS created_at, rt.expires_at AS expires_at
        ORDER BY rt.created_at DESC
        LIMIT $limit
        """,
        now=now_iso(),
        limit=limit,
    )


async def web_sessions(graph: Graph, user_id: str | None = None, limit: int = 500) -> list[dict[str, Any]]:
    """Live browser sessions, optionally for one user."""
    return await graph.run(
        """
        MATCH (s:WebSession)-[:FOR]->(u:User)
        WHERE s.expires_at > $now AND s.idle_expires_at > $now AND ($user_id IS NULL OR u.id = $user_id)
        RETURN s.id AS id, u.id AS user_id, u.username AS username, s.created_at AS created_at,
               s.expires_at AS expires_at, s.idle_expires_at AS idle_expires_at, s.ip AS ip
        ORDER BY s.created_at DESC
        LIMIT $limit
        """,
        now=now_iso(),
        user_id=user_id,
        limit=limit,
    )


async def delete_web_session(graph: Graph, session_id: str) -> bool:
    counters = await graph.write(
        lambda tx: tx.counters("MATCH (s:WebSession {id: $id}) DETACH DELETE s", id=session_id)
    )
    return counters.nodes_deleted > 0


async def project_stats(graph: Graph) -> dict[str, dict[str, int]]:
    rows = await graph.run(
        """
        MATCH (p:Project)
        OPTIONAL MATCH (:User)-[m:MEMBER_OF]->(p) WITH p, count(m) AS members
        OPTIONAL MATCH (p)-[:HAS_TOPIC]->(t:Topic) WITH p, members, count(t) AS topics
        OPTIONAL MATCH (p)-[:HAS_DOCUMENT]->(d) WITH p, members, topics, count(d) AS documents
        RETURN p.project_id AS project_id, members, topics, documents
        """
    )
    return {
        row["project_id"]: {
            "members": int(row["members"]),
            "topics": int(row["topics"]),
            "documents": int(row["documents"]),
        }
        for row in rows
    }


async def membership_counts(graph: Graph) -> dict[str, int]:
    rows = await graph.run(
        "MATCH (u:User) OPTIONAL MATCH (u)-[m:MEMBER_OF]->(:Project) RETURN u.id AS id, count(m) AS n"
    )
    return {row["id"]: int(row["n"]) for row in rows}


async def memberships_by_user(graph: Graph) -> dict[str, list[dict[str, str]]]:
    """``{user_id: [{"project_id", "role"}]}`` for every membership on the server."""
    rows = await graph.run(
        """
        MATCH (u:User)-[m:MEMBER_OF]->(p:Project)
        RETURN u.id AS user_id, p.project_id AS project_id, m.role AS role
        ORDER BY p.name
        """
    )
    result: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        result.setdefault(row["user_id"], []).append({"project_id": row["project_id"], "role": row["role"]})
    return result


async def members_by_project(graph: Graph) -> dict[str, list[dict[str, str]]]:
    """``{project_id: [{"user_id", "username", "role"}]}`` for every membership on the server."""
    rows = await graph.run(
        """
        MATCH (u:User)-[m:MEMBER_OF]->(p:Project)
        RETURN p.project_id AS project_id, u.id AS user_id, u.username AS username, m.role AS role
        ORDER BY u.username
        """
    )
    result: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        result.setdefault(row["project_id"], []).append(
            {"user_id": row["user_id"], "username": row["username"], "role": row["role"]}
        )
    return result


async def model_counts(graph: Graph) -> dict[str, int]:
    """Imported IFC models per project id (every state), plus the total under ``""``."""
    rows = await graph.run("MATCH (m:IfcModel) RETURN m.project_id AS project_id, count(m) AS n")
    counts = {str(row["project_id"] or ""): int(row["n"]) for row in rows}
    counts[""] = sum(counts.values())
    return counts


async def request_log_rows(graph: Graph) -> int:
    row = await graph.one("MATCH (r:RequestLog) RETURN count(r) AS n")
    return int(row["n"]) if row else 0


async def family_user(graph: Graph, family_id: str) -> str | None:
    """The user of a refresh-token family, or None when no live token of it exists."""
    row = await graph.one(
        "MATCH (rt:RefreshToken {family_id: $family_id})-[:FOR]->(u:User) RETURN u.id AS user_id LIMIT 1",
        family_id=family_id,
    )
    return row["user_id"] if row else None
