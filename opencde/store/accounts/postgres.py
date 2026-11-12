# This file was generated with the assistance of an AI coding tool.
"""The accounts area in PostgreSQL (ADR 0029): users, projects and their members, teams, and browser sessions.

The same protocols as the graph's repositories (``opencde.store.protocols``), over the tables of
``opencde/postgres/migrations/0001_accounts.sql``, with the same rules and answers. Membership is the ``memberships``
table, which a member's read joins on the user's id, as the graph's statements start at the user and follow
``MEMBER_OF``. Foreign keys delete what a project or a user owns. Every statement is one string literal with
numbered parameters; text is ordered by code point (``COLLATE "C"``), as the graphs order it.

``user_store``, ``project_store``, ``team_store`` and ``web_session_store`` choose between the two: PostgreSQL when
``OPENCDE_STORE_URL`` names it, the graph otherwise.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any

from opencde.accounts.roles import Role
from opencde.auth.passwords import hash_password, verify_password
from opencde.ids import hash_secret, is_uuid, new_id, new_secret, normalize_guid
from opencde.ifcgraph.maintenance import delete_geometry
from opencde.storage import LocalStorage
from opencde.store.accounts.projects import (
    AI_POLICIES,
    DEFAULT_EXTENSIONS,
    EXTENSION_LISTS,
    MAX_NAME,
    Project,
    ProjectRepository,
    _clean_list,
    _project,
)
from opencde.store.accounts.sessions import MAX_COOKIE_LENGTH, WebSessionRepository, WebUser
from opencde.store.accounts.teams import MAX_TEAMS, TeamRepository, _team
from opencde.store.accounts.users import (
    AccountError,
    User,
    UserRepository,
    _user,
    check_password,
    checked_new_user,
)
from opencde.timeutil import later_iso, now_iso

if TYPE_CHECKING:
    from opencde.graph.graph import Graph
    from opencde.postgres.database import Postgres, Tx
    from opencde.settings import Settings
    from opencde.store.protocols import ProjectStore, TeamStore, UserStore, WebSessionStore


def _project_name(name: str) -> str:
    name = name.strip()
    if not name or len(name) > MAX_NAME:
        raise AccountError(f"project name: 1-{MAX_NAME} characters", key="error.project.name_length", max=MAX_NAME)
    return name


def _no_project() -> AccountError:
    return AccountError("no such project", key="error.project.not_found")


# -- users -------------------------------------------------------------------------------------------------------

USER_INSERT = """
INSERT INTO users AS u (id, username, email, full_name, password_hash, is_admin, created_at, must_change_password)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
ON CONFLICT (username) DO NOTHING
RETURNING u.id, u.username, u.email, u.full_name, u.is_admin, u.disabled, u.created_at, u.must_change_password,
       u.last_sign_in_at
"""
USER_BY_NAME = """
SELECT u.id, u.username, u.email, u.full_name, u.is_admin, u.disabled, u.created_at, u.must_change_password,
       u.last_sign_in_at
FROM users u WHERE u.username = $1
"""
USER_BY_ID = """
SELECT u.id, u.username, u.email, u.full_name, u.is_admin, u.disabled, u.created_at, u.must_change_password,
       u.last_sign_in_at
FROM users u WHERE u.id = $1
"""
USER_SEARCH = """
SELECT u.id, u.username, u.email, u.full_name, u.is_admin, u.disabled, u.created_at, u.must_change_password,
       u.last_sign_in_at
FROM users u
WHERE $1::text IS NULL OR strpos(lower(u.username), lower($1)) > 0
   OR strpos(lower(coalesce(u.full_name, '')), lower($1)) > 0 OR strpos(lower(coalesce(u.email, '')), lower($1)) > 0
ORDER BY u.username COLLATE "C"
OFFSET $2 LIMIT $3
"""
USER_SIGN_IN = """
SELECT u.id, u.username, u.email, u.full_name, u.is_admin, u.disabled, u.created_at, u.must_change_password,
       u.last_sign_in_at, u.password_hash
FROM users u WHERE u.username = $1
"""
USER_UPDATE = """
UPDATE users u
SET email = coalesce($2::text, u.email), full_name = coalesce($3::text, u.full_name),
    is_admin = coalesce($4::boolean, u.is_admin), disabled = coalesce($5::boolean, u.disabled)
WHERE u.id = $1
RETURNING u.id, u.username, u.email, u.full_name, u.is_admin, u.disabled, u.created_at, u.must_change_password,
       u.last_sign_in_at
"""
MEMBERSHIPS = """
SELECT p.project_id, p.name, m.role
FROM memberships m JOIN projects p ON p.project_id = m.project_id
WHERE m.user_id = $1
ORDER BY p.name COLLATE "C"
"""


class PostgresUserRepository:
    def __init__(self, postgres: Postgres) -> None:
        self.postgres = postgres

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
        username = checked_new_user(username, password, email, full_name)
        row = await self.postgres.one(
            USER_INSERT,
            new_id(),
            username,
            email or None,
            full_name or None,
            hash_password(password),
            is_admin,
            now_iso(),
            must_change_password,
        )
        if row is None:  # the unique user name, also when two ask for it at once
            raise AccountError("user name already taken", key="error.user.name_taken")
        return _user(row)

    async def get_by_username(self, username: str) -> User | None:
        row = await self.postgres.one(USER_BY_NAME, username)
        return _user(row) if row else None

    async def get(self, user_id: str) -> User | None:
        row = await self.postgres.one(USER_BY_ID, user_id)
        return _user(row) if row else None

    async def search(self, *, query: str | None = None, limit: int = 200, skip: int = 0) -> list[User]:
        return [_user(row) for row in await self.postgres.run(USER_SEARCH, query or None, skip, limit)]

    async def count(self) -> int:
        row = await self.postgres.one("SELECT count(*) AS n FROM users")
        return int(row["n"]) if row else 0

    async def touch_sign_in(self, user_id: str) -> None:
        """Remember when the user last authenticated (browser sign-in or OAuth2 authorization)."""
        await self.postgres.execute("UPDATE users SET last_sign_in_at = $2 WHERE id = $1", user_id, now_iso())

    async def authenticate(self, username: str, password: str) -> User | None:
        """The user if the password matches and the account is enabled; None otherwise, in constant-ish time."""
        row = await self.postgres.one(USER_SIGN_IN, username.strip())
        password_hash = row["password_hash"] if row else None
        if not verify_password(password, password_hash) or row is None:
            return None
        user = _user(row)
        return None if user.disabled else user

    async def set_password(self, user_id: str, password: str, *, must_change: bool = False) -> None:
        user = await self.get(user_id)
        if user is None:
            raise AccountError("no such user", key="error.user.not_found")
        check_password(password, user.username, [user.email or "", user.full_name or ""])
        await self.postgres.execute(
            "UPDATE users SET password_hash = $2, must_change_password = $3 WHERE id = $1",
            user_id,
            hash_password(password),
            must_change,
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
        row = await self.postgres.one(USER_UPDATE, user_id, email, full_name, is_admin, disabled)
        if row is None:
            raise AccountError("no such user", key="error.user.not_found")
        return _user(row)

    async def delete(self, user_id: str) -> bool:
        """The user and what is theirs alone: memberships, team memberships, browser sessions."""
        return await self.postgres.execute("DELETE FROM users WHERE id = $1", user_id) > 0

    # -- memberships ------------------------------------------------------------

    async def project_role(self, user_id: str, project_id: str) -> Role | None:
        row = await self.postgres.one(
            "SELECT role FROM memberships WHERE user_id = $1 AND project_id = $2", user_id, project_id
        )
        return Role(row["role"]) if row else None

    async def memberships(self, user_id: str) -> list[tuple[str, str, Role]]:
        """(project_id, project name, role) for every project the user belongs to."""
        rows = await self.postgres.run(MEMBERSHIPS, user_id)
        return [(row["project_id"], row["name"], Role(row["role"])) for row in rows]


# -- projects ----------------------------------------------------------------------------------------------------

PROJECT_INSERT = """
INSERT INTO projects AS p (project_id, name, created_at, extensions) VALUES ($1, $2, $3, $4::jsonb)
RETURNING p.project_id, p.name, p.created_at, p.block_on_validation_errors, p.ai_policy
"""
PROJECT_BY_ID = "SELECT p.project_id, p.name, p.created_at, p.block_on_validation_errors, p.ai_policy FROM projects p WHERE p.project_id = $1"
PROJECT_ALL = 'SELECT p.project_id, p.name, p.created_at, p.block_on_validation_errors, p.ai_policy FROM projects p ORDER BY p.name COLLATE "C"'
PROJECTS_OF_USER = """
SELECT p.project_id, p.name, p.created_at, p.block_on_validation_errors, p.ai_policy, m.role
FROM memberships m JOIN projects p ON p.project_id = m.project_id
WHERE m.user_id = $1
ORDER BY p.name COLLATE "C"
"""
PROJECT_RENAME = """
UPDATE projects p SET name = $2 WHERE p.project_id = $1
RETURNING p.project_id, p.name, p.created_at, p.block_on_validation_errors, p.ai_policy
"""
PROJECT_BLOCK = """
UPDATE projects p SET block_on_validation_errors = $2 WHERE p.project_id = $1
RETURNING p.project_id, p.name, p.created_at, p.block_on_validation_errors, p.ai_policy
"""
PROJECT_AI_POLICY = """
UPDATE projects p SET ai_policy = $2 WHERE p.project_id = $1
RETURNING p.project_id, p.name, p.created_at, p.block_on_validation_errors, p.ai_policy
"""
MEMBER_SET = """
INSERT INTO memberships (user_id, project_id, role, since)
SELECT u.id, p.project_id, $3, $4 FROM users u, projects p WHERE u.id = $1 AND p.project_id = $2
ON CONFLICT (user_id, project_id) DO UPDATE SET role = EXCLUDED.role
RETURNING role
"""
MEMBERS = """
SELECT u.id, u.username, u.email, u.full_name, u.is_admin, u.disabled, u.created_at, u.must_change_password,
       u.last_sign_in_at, m.role
FROM memberships m JOIN users u ON u.id = m.user_id
WHERE m.project_id = $1
ORDER BY u.username COLLATE "C"
"""
EXTENSIONS = """
SELECT p.extensions,
       ARRAY(SELECT u.username FROM memberships m JOIN users u ON u.id = m.user_id
             WHERE m.project_id = p.project_id) AS users
FROM projects p
WHERE p.project_id = $1
"""
EXTENSIONS_SET = "UPDATE projects SET extensions = extensions || $2::jsonb WHERE project_id = $1 RETURNING project_id"


class PostgresProjectRepository:
    def __init__(self, postgres: Postgres) -> None:
        self.postgres = postgres

    async def create(
        self, name: str, *, project_id: str | None = None, extensions: dict[str, list[str]] | None = None
    ) -> Project:
        name = _project_name(name)
        if project_id is not None:
            if not is_uuid(project_id):
                raise AccountError("project_id must be a UUID", key="error.project.id_uuid")
            project_id = normalize_guid(project_id)
            if await self.get(project_id):
                raise AccountError("project_id already exists", key="error.project.id_exists")
        values = {
            key: _clean_list(key, (extensions or {}).get(key, DEFAULT_EXTENSIONS[key])) for key in EXTENSION_LISTS
        }
        row = await self.postgres.one(PROJECT_INSERT, project_id or new_id(), name, now_iso(), values)
        if row is None:  # INSERT ... RETURNING always returns a row; this guards the type checker
            raise AccountError("project was not created", key="error.project.not_created")
        return _project(row)

    async def get(self, project_id: str) -> Project | None:
        row = await self.postgres.one(PROJECT_BY_ID, project_id)
        return _project(row) if row else None

    async def all(self) -> list[Project]:
        return [_project(row) for row in await self.postgres.run(PROJECT_ALL)]

    async def list_for_user(self, user_id: str) -> list[tuple[Project, Role]]:
        rows = await self.postgres.run(PROJECTS_OF_USER, user_id)
        return [(_project(row), Role(row["role"])) for row in rows]

    async def rename(self, project_id: str, name: str) -> Project:
        row = await self.postgres.one(PROJECT_RENAME, project_id, _project_name(name))
        if row is None:
            raise _no_project()
        return _project(row)

    async def set_block_on_validation_errors(self, project_id: str, value: bool) -> Project:
        row = await self.postgres.one(PROJECT_BLOCK, project_id, bool(value))
        if row is None:
            raise _no_project()
        return _project(row)

    async def set_ai_policy(self, project_id: str, value: str) -> Project:
        if value not in AI_POLICIES:
            raise AccountError("ai_policy: local or cloud", key="error.project.ai_policy")
        row = await self.postgres.one(PROJECT_AI_POLICY, project_id, value)
        if row is None:
            raise _no_project()
        return _project(row)

    async def model_ids(self, project_id: str) -> list[str]:
        """The ids of the project's IFC models, by its conversions (the view ``project_models``). The models live in
        the IFC graph, so the caller that has both deletes them first (``ifcgraph.maintenance.delete_project``)."""
        rows = await self.postgres.run("SELECT model_id FROM project_models WHERE project_id = $1", project_id)
        return [str(row["model_id"]) for row in rows if row["model_id"]]

    async def delete(self, project_id: str) -> bool:
        """Delete the project and, by its foreign keys, what it owns. Its IFC models go before it (``model_ids``)."""
        return await self.postgres.execute("DELETE FROM projects WHERE project_id = $1", project_id) > 0

    async def delete_with_files(self, project_id: str, storage: LocalStorage) -> bool:
        """``delete``, and the stored files the project owned, so that deleting it frees the disk too."""
        keys = await self.storage_keys(project_id)
        models = await self.model_ids(project_id)
        deleted = await self.delete(project_id)
        for model_id in models:
            with contextlib.suppress(OSError):
                delete_geometry(storage, model_id)
        for key in keys:
            with contextlib.suppress(ValueError):  # a key the storage refuses was never one it wrote
                storage.delete(key)
        return deleted

    async def storage_keys(self, project_id: str) -> list[str]:
        """Every stored file the project owns (the view ``project_files``)."""
        rows = await self.postgres.run(
            "SELECT DISTINCT storage_key FROM project_files WHERE project_id = $1 AND storage_key IS NOT NULL",
            project_id,
        )
        return [row["storage_key"] for row in rows]

    # -- members ----------------------------------------------------------------

    async def set_member(self, project_id: str, user_id: str, role: Role) -> None:
        if await self.postgres.one(MEMBER_SET, user_id, project_id, role.value, now_iso()) is None:
            raise AccountError("no such user or project", key="error.project.member_not_found")

    async def remove_member(self, project_id: str, user_id: str) -> bool:
        deleted = await self.postgres.execute(
            "DELETE FROM memberships WHERE user_id = $1 AND project_id = $2", user_id, project_id
        )
        return deleted > 0

    async def members(self, project_id: str) -> list[tuple[User, Role]]:
        return [(_user(row), Role(row["role"])) for row in await self.postgres.run(MEMBERS, project_id)]

    # -- extensions ---------------------------------------------------------------

    async def extensions(self, project_id: str) -> dict[str, list[str]] | None:
        row = await self.postgres.one(EXTENSIONS, project_id)
        if row is None:
            return None
        ext = dict(row["extensions"])
        ext["users"] = sorted(row["users"])
        return ext

    async def set_extensions(self, project_id: str, values: dict[str, list[str]]) -> dict[str, list[str]]:
        unknown = set(values) - set(EXTENSION_LISTS)
        if unknown:
            names = ", ".join(sorted(unknown))
            raise AccountError(f"unknown extension lists: {names}", key="error.project.unknown_extensions", names=names)
        cleaned = {key: _clean_list(key, value) for key, value in values.items()}
        if await self.postgres.one(EXTENSIONS_SET, project_id, cleaned) is None:
            raise _no_project()
        result = await self.extensions(project_id)
        if result is None:
            raise _no_project()
        return result


# -- teams -------------------------------------------------------------------------------------------------------

TEAMS = """
SELECT t.id AS team_id, t.name, t.ids_document_id, r.id AS responsible_user_id, r.username AS responsible,
       ARRAY(SELECT u.username
             FROM team_members tm
             JOIN memberships m ON m.user_id = tm.user_id AND m.project_id = t.project_id
             JOIN users u ON u.id = tm.user_id
             WHERE tm.team_id = t.id) AS members,
       t.created_at, t.updated_at
FROM teams t LEFT JOIN users r ON r.id = t.responsible_user_id
WHERE t.project_id = $1 AND ($2::text IS NULL OR t.id = $2)
ORDER BY t.name COLLATE "C", t.id COLLATE "C"
LIMIT $3
"""
TEAM_INSERT = """
INSERT INTO teams (id, project_id, name, ids_document_id, responsible_user_id, created_at, updated_at)
SELECT $1, p.project_id, $3, $4, (SELECT id FROM users WHERE id = $5), $6, $6 FROM projects p WHERE p.project_id = $2
RETURNING id
"""
TEAM_UPDATE = """
UPDATE teams SET name = $3, ids_document_id = $4, responsible_user_id = (SELECT id FROM users WHERE id = $5),
       updated_at = $6
WHERE id = $1 AND project_id = $2
RETURNING id
"""
TEAM_MEMBERS_SET = """
INSERT INTO team_members (team_id, user_id) SELECT $1, u.id FROM users u WHERE u.id = ANY($2::text[])
"""
TEAM_PARTS = """
SELECT t.id AS team_id, t.name, r.id AS responsible_user_id, r.username AS responsible,
       h.storage_key, h.version_index AS ids_version_index
FROM teams t
JOIN document_heads h ON h.project_id = t.project_id AND h.document_id = t.ids_document_id
LEFT JOIN users r ON r.id = t.responsible_user_id
WHERE t.project_id = $1
ORDER BY t.name COLLATE "C", t.id COLLATE "C"
LIMIT $2
"""


class PostgresTeamRepository:
    def __init__(self, postgres: Postgres) -> None:
        self.postgres = postgres

    async def of_project(self, project_id: str) -> list[dict[str, Any]]:
        return [_team(row) for row in await self.postgres.run(TEAMS, project_id, None, MAX_TEAMS)]

    async def get(self, project_id: str, team_id: str) -> dict[str, Any] | None:
        row = await self.postgres.one(TEAMS, project_id, team_id, 1)
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
        fields = (wanted, project_id, name, ids_document_id, responsible_user_id, now_iso())

        async def work(tx: Tx) -> str | None:
            if await tx.one(TEAM_INSERT if team_id is None else TEAM_UPDATE, *fields) is None:
                return None
            await tx.execute("DELETE FROM team_members WHERE team_id = $1", wanted)
            await tx.execute(TEAM_MEMBERS_SET, wanted, sorted(set(member_ids)))
            return wanted

        return await self.postgres.write(work)

    async def delete(self, project_id: str, team_id: str) -> bool:
        deleted = await self.postgres.execute(
            "DELETE FROM teams WHERE project_id = $1 AND id = $2", project_id, team_id
        )
        return deleted > 0

    async def parts(self, project_id: str) -> list[dict[str, Any]]:
        """Each team with the file of the latest version of its IDS document, for the trial of a change set."""
        return await self.postgres.run(TEAM_PARTS, project_id, MAX_TEAMS)


# -- browser sessions --------------------------------------------------------------------------------------------

SESSION_INSERT = """
INSERT INTO web_sessions (id, user_id, created_at, expires_at, idle_expires_at, ip)
SELECT $1, u.id, $3, $4, $5, $6 FROM users u WHERE u.id = $2
"""
SESSION_RESOLVE = """
UPDATE web_sessions s SET idle_expires_at = $3
FROM users u
WHERE s.id = $1 AND u.id = s.user_id AND s.expires_at > $2 AND s.idle_expires_at > $2 AND NOT u.disabled
RETURNING u.id, u.username, u.email, u.full_name, u.is_admin, u.disabled, u.created_at, u.must_change_password,
       u.last_sign_in_at
"""


class PostgresWebSessionRepository:
    def __init__(self, postgres: Postgres, *, ttl_seconds: int, idle_seconds: int) -> None:
        self.postgres = postgres
        self.ttl_seconds = ttl_seconds
        self.idle_seconds = idle_seconds

    async def create(self, user_id: str, ip: str | None) -> str:
        """Start a session for the user; returns the cookie value (shown to the browser only)."""
        token = new_secret()
        await self.postgres.execute(
            SESSION_INSERT,
            hash_secret(token),
            user_id,
            now_iso(),
            later_iso(self.ttl_seconds),
            later_iso(self.idle_seconds),
            ip,
        )
        return token

    async def resolve(self, token: str) -> WebUser | None:
        """The signed-in user for a cookie value, extending the idle timeout; None when it is not valid."""
        if not token or len(token) > MAX_COOKIE_LENGTH:
            return None
        session_hash = hash_secret(token)
        row = await self.postgres.one(SESSION_RESOLVE, session_hash, now_iso(), later_iso(self.idle_seconds))
        return WebUser(user=_user(row), session_hash=session_hash) if row else None

    async def delete(self, token: str) -> None:
        await self.postgres.execute("DELETE FROM web_sessions WHERE id = $1", hash_secret(token))

    async def delete_for_user(self, user_id: str) -> int:
        return await self.postgres.execute("DELETE FROM web_sessions WHERE user_id = $1", user_id)


# -- where the accounts are --------------------------------------------------------------------------------------


def user_store(graph: Graph, postgres: Postgres | None) -> UserStore:
    return PostgresUserRepository(postgres) if postgres is not None else UserRepository(graph)


def project_store(graph: Graph, postgres: Postgres | None) -> ProjectStore:
    return PostgresProjectRepository(postgres) if postgres is not None else ProjectRepository(graph)


def team_store(graph: Graph, postgres: Postgres | None) -> TeamStore:
    return PostgresTeamRepository(postgres) if postgres is not None else TeamRepository(graph)


def web_session_store(graph: Graph, postgres: Postgres | None, settings: Settings) -> WebSessionStore:
    ttl, idle = settings.web_session_ttl_seconds, settings.web_session_idle_seconds
    if postgres is not None:
        return PostgresWebSessionRepository(postgres, ttl_seconds=ttl, idle_seconds=idle)
    return WebSessionRepository(graph, ttl_seconds=ttl, idle_seconds=idle)
