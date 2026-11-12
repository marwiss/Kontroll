# This file was generated with the assistance of an AI coding tool.
"""The accounts area in PostgreSQL (ADR 0029) against a real database: the same tests on the graph's repositories and
on PostgreSQL's, the migrations and the cleaner, and the app signing a user in with the accounts in PostgreSQL.

PostgreSQL runs in a container of its own (testcontainers' postgres module), one per test session; every test starts
from empty tables with the migrations applied. Each case runs once on the graph (on every graph the session has) and
once on PostgreSQL, which needs no graph: ``-k on_postgresql`` starts PostgreSQL alone."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from dataclasses import dataclass

import pytest
from asyncpg.exceptions import CheckViolationError
from fastapi.testclient import TestClient
from neo4j import GraphDatabase
from pydantic import SecretStr
from testcontainers.community.postgres import PostgresContainer

from opencde.accounts.roles import Role
from opencde.graph.graph import Graph
from opencde.main import create_app
from opencde.postgres.cleanup import delete_expired
from opencde.postgres.database import Postgres
from opencde.postgres.schema import MigrationError, migrate
from opencde.settings import Settings
from opencde.store.accounts.postgres import (
    PostgresProjectRepository,
    PostgresTeamRepository,
    PostgresUserRepository,
    PostgresWebSessionRepository,
)
from opencde.store.accounts.projects import ProjectRepository
from opencde.store.accounts.sessions import WebSessionRepository
from opencde.store.accounts.teams import TeamRepository
from opencde.store.accounts.users import AccountError, UserRepository
from opencde.store.protocols import ProjectStore, TeamStore, UserStore, WebSessionStore
from tests.integration.conftest import GraphTarget
from tests.integration.test_web_signin import form_token

pytestmark = pytest.mark.integration

POSTGRES_IMAGE = "postgres:17.6-alpine"
PASSWORD = "a-long-and-strong-passphrase"
EMPTY = "TRUNCATE users, projects, memberships, teams, team_members, web_sessions CASCADE"
PROJECT_ID = "6f3c2b5e-8d1a-4c2e-9f7b-1a2b3c4d5e6f"


@dataclass(frozen=True)
class PostgresTarget:
    url: str  # without the password, as OPENCDE_STORE_URL wants it
    password: str


@pytest.fixture(scope="session")
def postgres_target() -> Iterator[PostgresTarget]:
    with PostgresContainer(POSTGRES_IMAGE, driver=None) as container:
        host, port = container.get_container_host_ip(), container.get_exposed_port(5432)
        yield PostgresTarget(f"postgresql://{container.username}@{host}:{port}/{container.dbname}", container.password)


async def _emptied(target: PostgresTarget) -> Postgres:
    postgres = Postgres(target.url, target.password, connect_timeout_seconds=10.0)
    await migrate(postgres)
    await postgres.execute(EMPTY)
    return postgres


@pytest.fixture
async def pg(postgres_target: PostgresTarget) -> AsyncIterator[Postgres]:
    """A migrated PostgreSQL with empty tables, for async tests."""
    postgres = await _emptied(postgres_target)
    try:
        yield postgres
    finally:
        await postgres.close()


@dataclass(frozen=True)
class Accounts:
    users: UserStore
    projects: ProjectStore
    teams: TeamStore
    sessions: WebSessionStore


# -- the same on both ----------------------------------------------------------------------------------------------


async def users_are_made_found_changed_and_deleted(accounts: Accounts) -> None:
    users = accounts.users
    bertil = await users.create("bertil", PASSWORD, email="Bertil@Example.org", full_name="Bertil Ek")
    await users.create("Adam", PASSWORD)
    await users.create("anna", PASSWORD, must_change_password=True)
    with pytest.raises(AccountError, match="already taken"):
        await users.create("bertil", PASSWORD)
    assert await users.count() == 3
    assert [u.username for u in await users.search()] == ["Adam", "anna", "bertil"], "by code point"
    assert [u.username for u in await users.search(query="EXAMPLE")] == ["bertil"], "the e-mail too, any case"
    assert [u.username for u in await users.search(skip=1, limit=1)] == ["anna"]
    anna = await users.get_by_username("anna")
    assert anna is not None and anna.must_change_password

    changed = await users.update(bertil.id, full_name="Bertil Ekström", disabled=None)
    assert changed.full_name == "Bertil Ekström" and changed.email == "Bertil@Example.org", "None keeps a value"
    assert await users.authenticate(" bertil ", PASSWORD) is not None
    assert await users.authenticate("bertil", "wrong-" + PASSWORD) is None
    await users.update(bertil.id, disabled=True)
    assert await users.authenticate("bertil", PASSWORD) is None, "a disabled user does not sign in"
    await users.set_password(bertil.id, "another-long-passphrase-entirely", must_change=True)
    renewed = await users.get(bertil.id)
    assert renewed is not None and renewed.must_change_password and renewed.last_sign_in_at is None
    await users.touch_sign_in(bertil.id)
    touched = await users.get(bertil.id)
    assert touched is not None and touched.last_sign_in_at is not None
    assert await users.delete(bertil.id) and not await users.delete(bertil.id)
    assert await users.get(bertil.id) is None


async def projects_and_their_members(accounts: Accounts) -> None:
    users, projects = accounts.users, accounts.projects
    editor, viewer = await users.create("editor", PASSWORD), await users.create("viewer", PASSWORD)
    first = await projects.create(" Building permit ", project_id=PROJECT_ID.upper())
    assert first.project_id == PROJECT_ID and first.name == "Building permit" and first.ai_policy == "local"
    with pytest.raises(AccountError, match="already exists"):
        await projects.create("Again", project_id=PROJECT_ID)
    second = await projects.create("Archive")
    assert [p.name for p in await projects.all()] == ["Archive", "Building permit"]

    await projects.set_member(first.project_id, editor.id, Role.VIEWER)
    await projects.set_member(first.project_id, editor.id, Role.EDITOR)  # once, with the new role
    await projects.set_member(first.project_id, viewer.id, Role.VIEWER)
    await projects.set_member(second.project_id, editor.id, Role.MANAGER)
    with pytest.raises(AccountError, match="no such user or project"):
        await projects.set_member(first.project_id, "no-such-user", Role.VIEWER)
    assert [(u.username, r) for u, r in await projects.members(first.project_id)] == [
        ("editor", Role.EDITOR),
        ("viewer", Role.VIEWER),
    ]
    assert [(p.name, r) for p, r in await projects.list_for_user(editor.id)] == [
        ("Archive", Role.MANAGER),
        ("Building permit", Role.EDITOR),
    ]
    assert await users.project_role(viewer.id, second.project_id) is None
    assert await users.memberships(viewer.id) == [(first.project_id, "Building permit", Role.VIEWER)]

    assert (await projects.rename(first.project_id, "Permit")).name == "Permit"
    assert (await projects.set_ai_policy(first.project_id, "cloud")).ai_policy == "cloud"
    assert (await projects.set_block_on_validation_errors(first.project_id, True)).block_on_validation_errors
    extensions = await projects.set_extensions(first.project_id, {"topic_status": ["Open", " Closed ", "Open"]})
    assert extensions["topic_status"] == ["Open", "Closed"] and extensions["users"] == ["editor", "viewer"]
    assert extensions["priority"] == ["Low", "Medium", "High", "Critical"], "the other lists stay"
    with pytest.raises(AccountError, match="no such project"):
        await projects.rename("no-such-project", "x")

    assert await projects.remove_member(first.project_id, viewer.id)
    assert not await projects.remove_member(first.project_id, viewer.id)
    assert await projects.model_ids(first.project_id) == [] and await projects.storage_keys(first.project_id) == []
    assert await projects.delete(first.project_id) and await projects.get(first.project_id) is None
    assert await users.memberships(editor.id) == [(second.project_id, "Archive", Role.MANAGER)], "with its members"
    await users.delete(editor.id)
    assert await projects.members(second.project_id) == [], "a user goes from the projects too"


async def teams_of_a_project(accounts: Accounts) -> None:
    users, projects, teams = accounts.users, accounts.projects, accounts.teams
    lead, member, outsider = [await users.create(name, PASSWORD) for name in ("lead", "member", "outsider")]
    project = await projects.create("Building permit")
    for user in (lead, member):
        await projects.set_member(project.project_id, user.id, Role.EDITOR)
    team_id = await teams.save(
        project.project_id,
        team_id=None,
        name="Structure",
        responsible_user_id=lead.id,
        member_ids=[member.id, outsider.id, member.id],
        ids_document_id="d-1",
    )
    assert team_id is not None
    found = await teams.get(project.project_id, team_id)
    assert found is not None and found["responsible"] == "lead" and found["members"] == ["member"], (
        "a team's members are the project's members"
    )
    assert found["ids_document_id"] == "d-1" and found["created_at"] and found["updated_at"]
    other = await projects.create("Archive")
    assert (
        await teams.save(
            other.project_id, team_id=team_id, name="X", responsible_user_id=lead.id, member_ids=[], ids_document_id="d"
        )
        is None
    ), "another project's team is none of this one's"
    await teams.save(
        project.project_id,
        team_id=team_id,
        name="Bearing structure",
        responsible_user_id=member.id,
        member_ids=[lead.id],
        ids_document_id="d-2",
    )
    await teams.save(
        project.project_id,
        team_id=None,
        name="Acoustics",
        responsible_user_id=lead.id,
        member_ids=[],
        ids_document_id="d-3",
    )
    listed = await teams.of_project(project.project_id)
    assert [(t["name"], t["responsible"], t["members"]) for t in listed] == [
        ("Acoustics", "lead", []),
        ("Bearing structure", "member", ["lead"]),
    ]
    assert await teams.parts(project.project_id) == [], "no IDS document has a version"
    assert await teams.delete(project.project_id, team_id) and not await teams.delete(project.project_id, team_id)


async def browser_sessions(accounts: Accounts) -> None:
    users, sessions = accounts.users, accounts.sessions
    user = await users.create("editor", PASSWORD)
    token, other = await sessions.create(user.id, "127.0.0.1"), await sessions.create(user.id, None)
    found = await sessions.resolve(token)
    assert found is not None and found.user.username == "editor"
    await sessions.delete(token)
    assert await sessions.resolve(token) is None and await sessions.resolve("not-a-session") is None
    await users.update(user.id, disabled=True)
    assert await sessions.resolve(other) is None, "a disabled user's session is no session"
    assert await sessions.delete_for_user(user.id) == 1


CASES = (users_are_made_found_changed_and_deleted, projects_and_their_members, teams_of_a_project, browser_sessions)


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.__name__)
async def test_on_the_graph(case: Callable[[Accounts], Awaitable[None]], graph: Graph) -> None:
    await case(
        Accounts(
            UserRepository(graph),
            ProjectRepository(graph),
            TeamRepository(graph),
            WebSessionRepository(graph, ttl_seconds=3600, idle_seconds=600),
        )
    )


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.__name__)
async def test_on_postgresql(case: Callable[[Accounts], Awaitable[None]], pg: Postgres) -> None:
    await case(
        Accounts(
            PostgresUserRepository(pg),
            PostgresProjectRepository(pg),
            PostgresTeamRepository(pg),
            PostgresWebSessionRepository(pg, ttl_seconds=3600, idle_seconds=600),
        )
    )


# -- PostgreSQL's own ----------------------------------------------------------------------------------------------


async def test_on_postgresql_the_migrations_run_once_and_refuse_a_newer_database(pg: Postgres) -> None:
    assert await migrate(pg) == 0, "already applied"
    await pg.execute("INSERT INTO schema_migrations (version, name, applied_at) VALUES (99, '0099_later', 'x')")
    try:
        with pytest.raises(MigrationError, match="a newer release"):
            await migrate(pg)
    finally:
        await pg.execute("DELETE FROM schema_migrations WHERE version = 99")
    with pytest.raises(CheckViolationError, match="iso_utc"):  # the canonical form is checked
        await pg.execute(
            "INSERT INTO users (id, username, password_hash, created_at) VALUES ('u', 'u', 'h', '2026-11-12 10:00')"
        )


async def test_on_postgresql_expired_sessions_are_deleted_and_the_others_kept(pg: Postgres) -> None:
    user = await PostgresUserRepository(pg).create("editor", PASSWORD)
    await PostgresWebSessionRepository(pg, ttl_seconds=-60, idle_seconds=-60).create(user.id, None)
    kept = await PostgresWebSessionRepository(pg, ttl_seconds=3600, idle_seconds=600).create(user.id, None)
    assert await delete_expired(pg) == 1
    assert await pg.one("SELECT count(*) AS n FROM web_sessions") == {"n": 1}
    assert await PostgresWebSessionRepository(pg, ttl_seconds=3600, idle_seconds=600).resolve(kept) is not None


def test_the_app_signs_in_with_the_accounts_in_postgresql(
    settings: Settings, clean_database: None, graph_target: GraphTarget, postgres_target: PostgresTarget
) -> None:
    """The routes choose PostgreSQL's repositories when ``OPENCDE_STORE_URL`` names it: the user signs in from there,
    the session lives there, and the graph holds no user."""

    async def seed() -> None:
        postgres = await _emptied(postgres_target)
        try:
            await PostgresUserRepository(postgres).create("editor", PASSWORD)
        finally:
            await postgres.close()

    async def stored() -> tuple[int, str | None]:
        postgres = Postgres(postgres_target.url, postgres_target.password, connect_timeout_seconds=10.0)
        try:
            sessions = await postgres.one("SELECT count(*) AS n FROM web_sessions")
            user = await postgres.one("SELECT last_sign_in_at FROM users WHERE username = 'editor'")
            return (sessions or {}).get("n", 0), (user or {}).get("last_sign_in_at")
        finally:
            await postgres.close()

    asyncio.run(seed())
    apart = settings.model_copy(
        update={"store_url": postgres_target.url, "store_password": SecretStr(postgres_target.password)}
    )
    with TestClient(create_app(apart, startup_wait_seconds=30)) as client:
        ready = client.get("/readyz").json()
        assert ready["store"] == "ok" and ready["store_dialect"] == "postgres"
        page = client.get("/signin")
        answer = client.post(
            "/signin",
            data={"form_token": form_token(page.text), "username": "editor", "password": PASSWORD},
            follow_redirects=False,
        )
        assert answer.status_code == 302, answer.text
        account = client.get("/account")
        assert account.status_code == 200 and "editor" in account.text
    sessions, signed_in = asyncio.run(stored())
    assert sessions == 1 and signed_in is not None
    with GraphDatabase.driver(graph_target.uri, auth=(graph_target.user, graph_target.password)) as driver:
        records, _, _ = driver.execute_query("MATCH (u:User) RETURN count(u) AS n", database_=settings.database_name)
    assert records[0]["n"] == 0, "the graph holds no user"
