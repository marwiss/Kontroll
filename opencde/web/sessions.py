# This file was generated with the assistance of an AI coding tool.
"""Browser sessions.

The APIs never use cookies (Foundation API 2.2) and the pages never accept
bearer tokens; this module is the pages' side. A session is a 256-bit random
cookie value that the graph stores only as a SHA-256 hash, bound to one user,
with an absolute lifetime and an idle timeout. Signing out deletes it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Response

from opencde.accounts.users import PUBLIC_FIELDS, User, _user
from opencde.deps import GraphDep, SettingsDep
from opencde.graph.graph import Graph
from opencde.ids import hash_secret, new_secret
from opencde.settings import Settings
from opencde.timeutil import later_iso, now_iso

COOKIE_NAME = "opencde_session"
MAX_COOKIE_LENGTH = 128


@dataclass(frozen=True)
class WebUser:
    user: User
    session_hash: str


class WebSessionRepository:
    def __init__(self, graph: Graph, *, ttl_seconds: int, idle_seconds: int) -> None:
        self.graph = graph
        self.ttl_seconds = ttl_seconds
        self.idle_seconds = idle_seconds

    async def create(self, user_id: str, ip: str | None) -> str:
        """Start a session for the user; returns the cookie value (shown to the browser only)."""
        token = new_secret()
        await self.graph.run(
            """
            MATCH (u:User {id: $user_id})
            CREATE (s:WebSession {id: $id, created_at: $now, expires_at: $expires_at, idle_expires_at: $idle, ip: $ip})
            CREATE (s)-[:FOR]->(u)
            """,
            user_id=user_id,
            id=hash_secret(token),
            now=now_iso(),
            expires_at=later_iso(self.ttl_seconds),
            idle=later_iso(self.idle_seconds),
            ip=ip,
        )
        return token

    async def resolve(self, token: str) -> WebUser | None:
        """The signed-in user for a cookie value, extending the idle timeout; None when it is not valid."""
        if not token or len(token) > MAX_COOKIE_LENGTH:
            return None
        session_hash = hash_secret(token)
        row = await self.graph.one(
            f"""
            MATCH (s:WebSession {{id: $id}})-[:FOR]->(u:User)
            WHERE s.expires_at > $now AND s.idle_expires_at > $now AND NOT coalesce(u.disabled, false)
            SET s.idle_expires_at = $idle
            RETURN {PUBLIC_FIELDS} AS user
            """,
            id=session_hash,
            now=now_iso(),
            idle=later_iso(self.idle_seconds),
        )
        return WebUser(user=_user(row["user"]), session_hash=session_hash) if row else None

    async def delete(self, token: str) -> None:
        await self.graph.run("MATCH (s:WebSession {id: $id}) DETACH DELETE s", id=hash_secret(token))

    async def delete_for_user(self, user_id: str) -> int:
        counters = await self.graph.write(
            lambda tx: tx.counters(
                "MATCH (s:WebSession)-[:FOR]->(:User {id: $user_id}) DETACH DELETE s", user_id=user_id
            )
        )
        return counters.nodes_deleted


def set_session_cookie(response: Response, token: str, settings: Settings) -> None:
    """HttpOnly, SameSite=Strict, Secure on https, limited to the absolute session lifetime."""
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=settings.web_session_ttl_seconds,
        httponly=True,
        secure=settings.public_url.startswith("https://"),
        samesite="strict",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")


def web_sessions(graph: GraphDep, settings: SettingsDep) -> WebSessionRepository:
    return WebSessionRepository(
        graph, ttl_seconds=settings.web_session_ttl_seconds, idle_seconds=settings.web_session_idle_seconds
    )


WebSessionsDep = Annotated[WebSessionRepository, Depends(web_sessions)]
