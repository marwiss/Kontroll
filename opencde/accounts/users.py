# This file was generated with the assistance of an AI coding tool.
"""Users and their project memberships.

A user is a ``User`` node. Project access is a ``MEMBER_OF {role}``
relationship to a ``Project`` node (see :mod:`opencde.accounts.roles`). The
user name doubles as the user id the APIs expose (``current-user.id``,
``creation_author``, ``assigned_to``); an e-mail address is a good choice.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from opencde.accounts.roles import Role
from opencde.auth.passwords import hash_password, password_problems, verify_password
from opencde.graph.graph import Graph
from opencde.ids import new_id
from opencde.timeutil import now_iso

USERNAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._@+-]{2,127}$")


class AccountError(ValueError):
    """A request that cannot be fulfilled; the message is safe to show."""


@dataclass(frozen=True)
class User:
    id: str
    username: str
    email: str | None
    full_name: str | None
    is_admin: bool
    disabled: bool
    created_at: str
    must_change_password: bool = False

    @property
    def display_name(self) -> str:
        return self.full_name or self.username


def _user(row: dict[str, Any]) -> User:
    return User(
        id=row["id"],
        username=row["username"],
        email=row.get("email"),
        full_name=row.get("full_name"),
        is_admin=bool(row.get("is_admin", False)),
        disabled=bool(row.get("disabled", False)),
        created_at=row["created_at"],
        must_change_password=bool(row.get("must_change_password", False)),
    )


PUBLIC_FIELDS = "u {.id, .username, .email, .full_name, .is_admin, .disabled, .created_at, .must_change_password}"


class UserRepository:
    def __init__(self, graph: Graph) -> None:
        self.graph = graph

    async def create(
        self,
        username: str,
        password: str,
        *,
        email: str | None = None,
        full_name: str | None = None,
        is_admin: bool = False,
        must_change_password: bool = False,
    ) -> User:
        username = username.strip()
        if not USERNAME.match(username):
            raise AccountError("user name: 3-128 characters, letters, digits and . _ @ + -")
        problems = password_problems(password, username, [email or "", full_name or ""])
        if problems:
            raise AccountError("password rejected: " + "; ".join(problems))
        if await self.get_by_username(username):
            raise AccountError("user name already taken")
        row = await self.graph.one(
            f"""
            CREATE (u:User {{
                id: $id, username: $username, email: $email, full_name: $full_name,
                password_hash: $password_hash, is_admin: $is_admin, disabled: false,
                created_at: $now, must_change_password: $must_change
            }})
            RETURN {PUBLIC_FIELDS} AS user
            """,
            id=new_id(),
            username=username,
            email=email or None,
            full_name=full_name or None,
            password_hash=hash_password(password),
            is_admin=is_admin,
            now=now_iso(),
            must_change=must_change_password,
        )
        if row is None:  # CREATE always returns a row; this guards the type checker and a broken driver
            raise AccountError("user was not created")
        return _user(row["user"])

    async def get_by_username(self, username: str) -> User | None:
        row = await self.graph.one(
            f"MATCH (u:User {{username: $username}}) RETURN {PUBLIC_FIELDS} AS user", username=username
        )
        return _user(row["user"]) if row else None

    async def get(self, user_id: str) -> User | None:
        row = await self.graph.one(f"MATCH (u:User {{id: $id}}) RETURN {PUBLIC_FIELDS} AS user", id=user_id)
        return _user(row["user"]) if row else None

    async def search(self, *, query: str | None = None, limit: int = 200, skip: int = 0) -> list[User]:
        rows = await self.graph.run(
            f"""
            MATCH (u:User)
            WHERE $query IS NULL OR toLower(u.username) CONTAINS toLower($query)
               OR toLower(coalesce(u.full_name, '')) CONTAINS toLower($query)
               OR toLower(coalesce(u.email, '')) CONTAINS toLower($query)
            RETURN {PUBLIC_FIELDS} AS user
            ORDER BY u.username
            SKIP $skip LIMIT $limit
            """,
            query=query or None,
            skip=skip,
            limit=limit,
        )
        return [_user(row["user"]) for row in rows]

    async def count(self) -> int:
        row = await self.graph.one("MATCH (u:User) RETURN count(u) AS n")
        return int(row["n"]) if row else 0

    async def authenticate(self, username: str, password: str) -> User | None:
        """The user if the password matches and the account is enabled; None otherwise, in constant-ish time."""
        row = await self.graph.one(
            f"MATCH (u:User {{username: $username}}) RETURN {PUBLIC_FIELDS} AS user, u.password_hash AS password_hash",
            username=username.strip(),
        )
        password_hash = row["password_hash"] if row else None
        if not verify_password(password, password_hash) or row is None:
            return None
        user = _user(row["user"])
        return None if user.disabled else user

    async def set_password(self, user_id: str, password: str, *, must_change: bool = False) -> None:
        user = await self.get(user_id)
        if user is None:
            raise AccountError("no such user")
        problems = password_problems(password, user.username, [user.email or "", user.full_name or ""])
        if problems:
            raise AccountError("password rejected: " + "; ".join(problems))
        await self.graph.run(
            "MATCH (u:User {id: $id}) SET u.password_hash = $hash, u.must_change_password = $must_change",
            id=user_id,
            hash=hash_password(password),
            must_change=must_change,
        )

    async def update(
        self,
        user_id: str,
        *,
        email: str | None = None,
        full_name: str | None = None,
        is_admin: bool | None = None,
        disabled: bool | None = None,
    ) -> User:
        row = await self.graph.one(
            f"""
            MATCH (u:User {{id: $id}})
            SET u.email = coalesce($email, u.email),
                u.full_name = coalesce($full_name, u.full_name),
                u.is_admin = coalesce($is_admin, u.is_admin),
                u.disabled = coalesce($disabled, u.disabled)
            RETURN {PUBLIC_FIELDS} AS user
            """,
            id=user_id,
            email=email,
            full_name=full_name,
            is_admin=is_admin,
            disabled=disabled,
        )
        if row is None:
            raise AccountError("no such user")
        return _user(row["user"])

    async def delete(self, user_id: str) -> bool:
        counters = await self.graph.write(
            lambda tx: tx.counters("MATCH (u:User {id: $id}) DETACH DELETE u", id=user_id)
        )
        return counters.nodes_deleted > 0

    # -- memberships ------------------------------------------------------------

    async def project_role(self, user_id: str, project_id: str) -> Role | None:
        row = await self.graph.one(
            "MATCH (:User {id: $user_id})-[m:MEMBER_OF]->(:Project {project_id: $project_id}) RETURN m.role AS role",
            user_id=user_id,
            project_id=project_id,
        )
        return Role(row["role"]) if row else None

    async def memberships(self, user_id: str) -> list[tuple[str, str, Role]]:
        """(project_id, project name, role) for every project the user belongs to."""
        rows = await self.graph.run(
            """
            MATCH (:User {id: $user_id})-[m:MEMBER_OF]->(p:Project)
            RETURN p.project_id AS project_id, p.name AS name, m.role AS role
            ORDER BY p.name
            """,
            user_id=user_id,
        )
        return [(row["project_id"], row["name"], Role(row["role"])) for row in rows]
