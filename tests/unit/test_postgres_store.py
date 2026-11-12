# This file was generated with the assistance of an AI coding tool.
"""The server's own data in PostgreSQL (ADR 0029), without a database: every statement a literal with numbered
parameters, the migrations in order, the accounts' repositories over a fake, and the choice of store in the app."""

from __future__ import annotations

import ast
import re
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from opencde.accounts.roles import Role
from opencde.deps import get_projects, get_users
from opencde.main import create_app
from opencde.postgres import cleanup, database, schema
from opencde.postgres.database import Postgres, _count
from opencde.store.accounts import postgres as accounts
from opencde.store.accounts.postgres import (
    PostgresProjectRepository,
    PostgresTeamRepository,
    PostgresUserRepository,
    PostgresWebSessionRepository,
    project_store,
    team_store,
    user_store,
    web_session_store,
)
from opencde.store.accounts.projects import ProjectRepository
from opencde.store.accounts.sessions import WebSessionRepository
from opencde.store.accounts.teams import TeamRepository
from opencde.store.accounts.users import AccountError, UserRepository
from tests.conftest import REPO_ROOT
from tests.conftest import test_settings as make_settings

MODULES = sorted(
    [*(REPO_ROOT / "opencde" / "postgres").glob("*.py"), *(REPO_ROOT / "opencde" / "store").rglob("postgres.py")]
)
RUNNERS = {"run", "one", "execute", "fetch", "fetchrow", "fetchval", "executemany"}
SQL = re.compile(r"\b(SELECT|INSERT|UPDATE|DELETE|FROM|WHERE|JOIN|VALUES|CREATE|DROP|ALTER|TRUNCATE)\b")
#: The layer that runs the repositories' statements hands on the statement its caller gave.
PASSED_ON = {"database.py": {"query", "text"}}
URL = "postgresql://cde@127.0.0.1:9/cde"  # the discard port: refused at once
WEAK = "x' OR '1'='1"
LONG_ENOUGH = "a-long-and-strong-passphrase"


def _statements(tree: ast.Module) -> dict[str, str]:
    """The module's constants that hold a statement."""
    found = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            for target in node.targets:
                if isinstance(target, ast.Name) and SQL.search(node.value.value):
                    found[target.id] = node.value.value
    return found


def _literal(node: ast.expr, constants: dict[str, str], passed_on: set[str]) -> bool:
    if isinstance(node, ast.Constant):
        return isinstance(node.value, str)
    if isinstance(node, ast.Name):
        return node.id in constants or node.id in passed_on
    if isinstance(node, ast.IfExp):
        return _literal(node.body, constants, passed_on) and _literal(node.orelse, constants, passed_on)
    return False


def _sql_text(node: ast.AST) -> bool:
    return any(
        isinstance(part, ast.Constant) and isinstance(part.value, str) and SQL.search(part.value)
        for part in ast.walk(node)
    )


@pytest.mark.parametrize("path", MODULES, ids=lambda path: str(path.relative_to(REPO_ROOT)))
def test_every_statement_is_one_literal_with_numbered_parameters(path: Path) -> None:
    """No f-string, ``%``, ``.format``, ``+`` or ``join`` near SQL, and every call that runs a statement is given a
    literal: a value can only ever be an argument, which asyncpg binds on the server."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    constants = _statements(tree)
    passed_on = PASSED_ON.get(path.name, set())
    offences = []
    for node in ast.walk(tree):
        line = getattr(node, "lineno", 0)
        if isinstance(node, ast.JoinedStr) and _sql_text(node):
            offences.append(f"{line}: an f-string with SQL")
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod | ast.Add) and _sql_text(node):
            offences.append(f"{line}: SQL built with % or +")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in ("format", "join") and _sql_text(node.func.value):
                offences.append(f"{line}: SQL built with .{node.func.attr}")
            if node.func.attr in RUNNERS and node.args and not _literal(node.args[0], constants, passed_on):
                offences.append(f"{line}: .{node.func.attr} is given something other than a literal")
            if node.func.attr == "script" and path.name != "schema.py":
                offences.append(f"{line}: only the migrations run a script")
    for name, statement in constants.items():
        if "%" in statement or "{" in statement:
            offences.append(f"{name}: a placeholder other than $n")
        numbers = sorted({int(n) for n in re.findall(r"\$(\d+)", statement)})
        if numbers != list(range(1, len(numbers) + 1)):
            offences.append(f"{name}: the parameters are not $1 to ${len(numbers)}")
    assert offences == []


def test_a_members_read_joins_the_membership_on_the_users_id() -> None:
    """``MEMBER_OF`` in PostgreSQL: what a user reads of the projects is reached through ``memberships``."""
    for statement in (accounts.MEMBERSHIPS, accounts.PROJECTS_OF_USER):
        assert "FROM memberships m JOIN projects p ON p.project_id = m.project_id" in statement
        assert "WHERE m.user_id = $1" in statement
    assert "JOIN memberships m ON m.user_id = tm.user_id AND m.project_id = t.project_id" in accounts.TEAMS, (
        "a team's members are the project's members"
    )
    for statement in (accounts.USER_INSERT, accounts.USER_UPDATE, accounts.MEMBERS, accounts.SESSION_RESOLVE):
        assert "password_hash" not in statement.split("RETURNING")[-1].split("FROM")[0], "the hash stays inside"


# -- the migrations ------------------------------------------------------------------------------------------------


def test_the_migrations_are_numbered_from_one_without_gaps(tmp_path: Path) -> None:
    assert [(m.version, m.name) for m in schema.migrations()] == [(1, "0001_accounts")]
    for names, words in ((["0001_a.sql", "0003_c.sql"], "without gaps"), (["1_a.sql"], "NNNN_name.sql")):
        folder = tmp_path / names[0]
        folder.mkdir()
        for name in names:
            (folder / name).write_text("SELECT 1;", encoding="utf-8")
        with pytest.raises(schema.MigrationError, match=words):
            schema.migrations(folder)


def test_the_first_migration_keeps_time_canonical_and_owns_by_foreign_keys() -> None:
    text = (schema.MIGRATIONS_DIR / "0001_accounts.sql").read_text(encoding="utf-8")
    assert text.startswith("-- This file was generated with the assistance of an AI coding tool.")
    assert "CREATE DOMAIN iso_utc" in text and "timestamptz" not in text
    assert re.search(r"expires_at iso_utc NOT NULL", text) and "web_sessions_expires_at" in text
    assert text.count("ON DELETE CASCADE") >= 6
    for view in ("project_files", "project_models", "document_heads"):
        assert f"CREATE VIEW {view}" in text, "the seams to the areas that have not followed"


class FakePostgres:
    """Records each statement with its arguments and answers through ``answer``; ``write`` runs the work on itself."""

    def __init__(self, answer: Callable[[str, tuple[Any, ...]], Any] | None = None) -> None:
        self.answer = answer or (lambda query, args: None)
        self.statements: list[tuple[str, tuple[Any, ...]]] = []
        self.scripts: list[str] = []
        self.transactions = 0

    async def run(self, query: str, /, *args: Any) -> list[dict[str, Any]]:
        self.statements.append((query, args))
        return self.answer(query, args) or []

    async def one(self, query: str, /, *args: Any) -> dict[str, Any] | None:
        self.statements.append((query, args))
        return self.answer(query, args)

    async def execute(self, query: str, /, *args: Any) -> int:
        self.statements.append((query, args))
        return self.answer(query, args) or 0

    async def script(self, text: str) -> None:
        self.scripts.append(text)

    async def write(self, work: Callable[[Any], Awaitable[Any]]) -> Any:
        self.transactions += 1
        return await work(self)


def _ledger(rows: list[dict[str, Any]]) -> Callable[[str, tuple[Any, ...]], Any]:
    return lambda query, args: rows if query == schema.APPLIED else None


async def test_migrate_runs_what_is_missing_under_the_lock_and_refuses_a_newer_database() -> None:
    fresh = FakePostgres(_ledger([]))
    assert await schema.migrate(fresh) == 1  # ty: ignore[invalid-argument-type]
    assert fresh.transactions == 1 and fresh.statements[0] == (schema.LOCK, (schema.LOCK_KEY,))
    assert len(fresh.scripts) == 1 and "CREATE TABLE users" in fresh.scripts[0]
    (record,) = [args for query, args in fresh.statements if query == schema.RECORD]
    assert record[:2] == (1, "0001_accounts")

    done = FakePostgres(_ledger([{"version": 1, "name": "0001_accounts"}]))
    assert await schema.migrate(done) == 0 and done.scripts == []  # ty: ignore[invalid-argument-type]
    for rows, words in (
        ([{"version": 1, "name": "0001_accounts"}, {"version": 2, "name": "0002_later"}], "a newer release"),
        ([{"version": 1, "name": "0001_other"}], "not the ones this server ships"),
    ):
        with pytest.raises(schema.MigrationError, match=words):
            await schema.migrate(FakePostgres(_ledger(rows)))  # ty: ignore[invalid-argument-type]


async def test_expired_rows_go_in_batches() -> None:
    counts = iter([cleanup.BATCH, cleanup.BATCH, 3])
    fake = FakePostgres(lambda query, args: next(counts))
    assert await cleanup.delete_expired(fake, at="2026-11-12T00:00:00.000Z") == 2 * cleanup.BATCH + 3  # ty: ignore[invalid-argument-type]
    assert [args for _, args in fake.statements] == [("2026-11-12T00:00:00.000Z", cleanup.BATCH)] * 3


def test_a_status_says_how_many_rows() -> None:
    assert _count("DELETE 3") == 3 and _count("INSERT 0 1") == 1 and _count("UPDATE 0") == 0
    assert _count("CREATE TABLE") == 0


# -- the accounts over a fake --------------------------------------------------------------------------------------

USER_ROW = {
    "id": "u-1",
    "username": "editor",
    "email": None,
    "full_name": None,
    "is_admin": False,
    "disabled": False,
    "created_at": "2026-11-12T00:00:00.000Z",
    "must_change_password": False,
    "last_sign_in_at": None,
}


async def test_a_value_is_only_ever_an_argument() -> None:
    fake = FakePostgres()
    users, projects = PostgresUserRepository(fake), PostgresProjectRepository(fake)  # ty: ignore[invalid-argument-type]
    await users.search(query=WEAK, skip=5, limit=10)
    await users.get_by_username(WEAK)
    await users.project_role(WEAK, WEAK)
    await projects.list_for_user(WEAK)
    for statement, args in fake.statements:
        assert WEAK not in statement and WEAK in args
    assert fake.statements[0] == (accounts.USER_SEARCH, (WEAK, 5, 10))


async def test_the_rules_come_before_the_database() -> None:
    fake = FakePostgres()
    users, projects = PostgresUserRepository(fake), PostgresProjectRepository(fake)  # ty: ignore[invalid-argument-type]
    with pytest.raises(AccountError, match="password rejected"):
        await users.create("editor", "short")
    with pytest.raises(AccountError, match="user name"):
        await users.create("x", LONG_ENOUGH)
    with pytest.raises(AccountError, match="local or cloud"):
        await projects.set_ai_policy("p-1", "anywhere")
    with pytest.raises(AccountError, match="unknown extension lists"):
        await projects.set_extensions("p-1", {"topic_type": ["A"], "colour": ["red"]})
    assert fake.statements == [], "nothing that is refused reaches the database"


async def test_a_taken_user_name_is_told_also_when_two_ask_at_once() -> None:
    users = PostgresUserRepository(FakePostgres())  # ty: ignore[invalid-argument-type]
    with pytest.raises(AccountError, match="already taken"):  # ON CONFLICT DO NOTHING returned no row
        await users.create("editor", LONG_ENOUGH)
    made = PostgresUserRepository(FakePostgres(lambda query, args: USER_ROW))  # ty: ignore[invalid-argument-type]
    assert (await made.create(" editor ", LONG_ENOUGH)).username == "editor"


async def test_a_project_is_made_with_its_lists_and_extended_by_merging() -> None:
    def answer(query: str, args: tuple[Any, ...]) -> Any:
        if query == accounts.PROJECT_INSERT:
            return {"project_id": args[0], "name": args[1], "created_at": args[2], "ai_policy": "local"}
        if query == accounts.EXTENSIONS_SET:
            return {"project_id": args[0]}
        if query == accounts.EXTENSIONS:
            return {"extensions": {"topic_type": ["A"]}, "users": ["viewer", "editor"]}
        return None

    fake = FakePostgres(answer)
    projects = PostgresProjectRepository(fake)  # ty: ignore[invalid-argument-type]
    project = await projects.create(" Building permit ", extensions={"topic_type": ["A", "A", " B "]})
    assert project.name == "Building permit" and project.ai_policy == "local"
    (_, args) = fake.statements[0]
    assert args[3]["topic_type"] == ["A", "B"] and args[3]["priority"] == ["Low", "Medium", "High", "Critical"]
    assert await projects.set_extensions(project.project_id, {"topic_type": ["A"]}) == {
        "topic_type": ["A"],
        "users": ["editor", "viewer"],
    }
    assert fake.statements[1] == (accounts.EXTENSIONS_SET, (project.project_id, {"topic_type": ["A"]}))


async def test_a_team_is_saved_in_one_transaction_and_only_in_its_project() -> None:
    fake = FakePostgres(lambda query, args: {"id": args[0]} if query == accounts.TEAM_INSERT else None)
    teams = PostgresTeamRepository(fake)  # ty: ignore[invalid-argument-type]
    team_id = await teams.save(
        "p-1",
        team_id=None,
        name="Structure",
        responsible_user_id="u-1",
        member_ids=["u-3", "u-2", "u-3"],
        ids_document_id="d-1",
    )
    assert team_id is not None and fake.transactions == 1
    assert [query for query, _ in fake.statements] == [
        accounts.TEAM_INSERT,
        "DELETE FROM team_members WHERE team_id = $1",
        accounts.TEAM_MEMBERS_SET,
    ]
    assert fake.statements[2][1] == (team_id, ["u-2", "u-3"])
    before = len(fake.statements)
    assert (
        await teams.save(
            "p-2", team_id=team_id, name="Structure", responsible_user_id="u-1", member_ids=[], ids_document_id="d-1"
        )
        is None
    ), "another project's team is none of this one's"
    assert [query for query, _ in fake.statements[before:]] == [accounts.TEAM_UPDATE]


async def test_a_session_is_resolved_by_its_hash_and_only_while_it_lasts() -> None:
    fake = FakePostgres(lambda query, args: USER_ROW if query == accounts.SESSION_RESOLVE else None)
    sessions = PostgresWebSessionRepository(fake, ttl_seconds=3600, idle_seconds=600)  # ty: ignore[invalid-argument-type]
    token = await sessions.create("u-1", "127.0.0.1")
    (_, made) = fake.statements[0]
    assert token not in made and made[1] == "u-1", "the cookie is stored as its hash alone"
    found = await sessions.resolve(token)
    assert found is not None and found.user.username == "editor" and found.session_hash == made[0]
    assert await sessions.resolve("x" * 200) is None and len(fake.statements) == 2, "too long to be one"


async def test_a_member_is_set_once_and_told_when_the_user_or_project_is_missing() -> None:
    projects = PostgresProjectRepository(FakePostgres())  # ty: ignore[invalid-argument-type]
    with pytest.raises(AccountError, match="no such user or project"):
        await projects.set_member("p-1", "u-1", Role.EDITOR)


# -- the choice of store -------------------------------------------------------------------------------------------


def test_the_graph_holds_the_accounts_unless_postgresql_is_named(tmp_path: Path) -> None:
    graph, settings = object(), make_settings(tmp_path)
    assert isinstance(user_store(graph, None), UserRepository)  # ty: ignore[invalid-argument-type]
    assert isinstance(project_store(graph, None), ProjectRepository)  # ty: ignore[invalid-argument-type]
    assert isinstance(team_store(graph, None), TeamRepository)  # ty: ignore[invalid-argument-type]
    assert isinstance(web_session_store(graph, None, settings), WebSessionRepository)  # ty: ignore[invalid-argument-type]
    postgres = Postgres(URL, "", connect_timeout_seconds=1.0)
    assert isinstance(user_store(graph, postgres), PostgresUserRepository)  # ty: ignore[invalid-argument-type]
    assert isinstance(project_store(graph, postgres), PostgresProjectRepository)  # ty: ignore[invalid-argument-type]
    assert isinstance(team_store(graph, postgres), PostgresTeamRepository)  # ty: ignore[invalid-argument-type]
    sessions = web_session_store(graph, postgres, settings)  # ty: ignore[invalid-argument-type]
    assert (
        isinstance(sessions, PostgresWebSessionRepository) and sessions.ttl_seconds == settings.web_session_ttl_seconds
    )


def test_the_app_opens_postgresql_when_it_is_named_and_reports_it(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, store_url=URL)
    with TestClient(create_app(settings, startup_wait_seconds=0)) as client:
        postgres = client.app.state.postgres  # ty: ignore[unresolved-attribute]
        assert isinstance(postgres, Postgres) and postgres.url == URL
        assert isinstance(get_users(client.app.state.store, postgres), PostgresUserRepository)  # ty: ignore[unresolved-attribute]
        assert isinstance(get_projects(client.app.state.store, postgres), PostgresProjectRepository)  # ty: ignore[unresolved-attribute]
        answer = client.get("/readyz")
        assert answer.status_code == 503 and answer.json()["store"] == "unavailable"
    with TestClient(create_app(make_settings(tmp_path), startup_wait_seconds=0)) as client:
        assert client.app.state.postgres is None  # ty: ignore[unresolved-attribute]


def test_postgresql_wants_its_extra(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(database.importlib.util, "find_spec", lambda name: None)
    with pytest.raises(RuntimeError, match=r"opencde-server\[postgres\]"):
        Postgres(URL, "", connect_timeout_seconds=1.0)
