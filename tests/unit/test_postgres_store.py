# This file was generated with the assistance of an AI coding tool.
"""The server's own data in PostgreSQL (ADR 0029), without a database: every statement a literal with numbered
parameters, the migrations in order, every expiring table in the cleaner's round, the areas' repositories over a fake,
and the choice of store in the app."""

from __future__ import annotations

import ast
import re
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from ifc_db.validation import pack_report

from opencde.accounts.roles import Role
from opencde.auth import pkce
from opencde.auth.dependencies import get_tokens
from opencde.bcf.schemas import CommentPOST, TopicPOST
from opencde.deps import get_clients, get_projects, get_users
from opencde.ids import hash_secret
from opencde.main import create_app
from opencde.odata import compile_odata
from opencde.postgres import cleanup, database, schema
from opencde.postgres.database import Postgres, _count
from opencde.storage import LocalStorage
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
from opencde.store.bcf import postgres as bcf
from opencde.store.bcf.comments import CommentRepository
from opencde.store.bcf.documents import BcfDocumentRepository
from opencde.store.bcf.events import BcfEventRepository
from opencde.store.bcf.postgres import (
    PostgresBcfDocumentRepository,
    PostgresBcfEventRepository,
    PostgresCommentRepository,
    PostgresTopicLinkRepository,
    PostgresTopicRepository,
    PostgresViewpointRepository,
)
from opencde.store.bcf.topic_links import TopicLinkRepository
from opencde.store.bcf.topics import TOPIC_DEFAULT_ORDER, TOPIC_FIELDS, TOPIC_ORDERABLE, TopicRepository
from opencde.store.bcf.viewpoints import ViewpointRepository
from opencde.store.documents import postgres as documents
from opencde.store.documents.postgres import (
    PostgresDocumentRepository,
    PostgresSelectionSessionRepository,
    PostgresUploadSessionRepository,
    document_store,
    selection_session_store,
    upload_session_store,
)
from opencde.store.documents.sessions import (
    SelectionSessionRepository,
    UploadSessionRepository,
    selection_sessions,
    upload_sessions,
)
from opencde.store.documents.versions import DocumentRepository, default_metadata, document_repository
from opencde.store.oauth2 import postgres as oauth2
from opencde.store.oauth2.clients import ClientError, ClientRepository
from opencde.store.oauth2.postgres import PostgresClientRepository, PostgresTokenRepository, client_store, token_store
from opencde.store.oauth2.tokens import GrantError, TokenPair, TokenRepository
from opencde.timeutil import later_iso, now_iso
from tests.conftest import REPO_ROOT
from tests.conftest import test_settings as make_settings

MODULES = sorted(
    [*(REPO_ROOT / "opencde" / "postgres").glob("*.py"), *(REPO_ROOT / "opencde" / "store").rglob("postgres.py")]
)
RUNNERS = {"run", "one", "execute", "fetch", "fetchrow", "fetchval", "executemany"}
SQL = re.compile(r"\b(SELECT|INSERT|UPDATE|DELETE|FROM|WHERE|JOIN|VALUES|CREATE|DROP|ALTER|TRUNCATE)\b")
#: The layer that runs the repositories' statements hands on the statement its caller gave, and the cleaner each of
#: its module's statements in turn.
PASSED_ON = {"database.py": {"query", "text"}, "cleanup.py": {"statement"}}
URL = "postgresql://cde@127.0.0.1:9/cde"  # the discard port: refused at once
WEAK = "x' OR '1'='1"
LONG_ENOUGH = "a-long-and-strong-passphrase"
GUID = "00000000-0000-4000-8000-000000000001"


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
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "sql":
        # A list's statement with the OData compiler's filter and order in it (``Compiled.sql``), made of its
        # whitelist alone; the statement itself is a literal still.
        return len(node.args) == 1 and not node.keywords and _literal(node.args[0], constants, passed_on)
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


def test_a_token_answers_for_its_user_and_client_and_a_secret_stays_inside() -> None:
    """``FOR`` and ``ISSUED_TO`` in PostgreSQL: a code or a token is read with its user and its client, and only the
    client's sign-in reads its secret's hash."""
    for statement in (oauth2.PRINCIPAL, oauth2.CODE_TO_REDEEM, oauth2.REFRESH_TO_USE):
        assert "JOIN users u ON u.id = " in statement and "JOIN oauth_clients c ON c.client_id = " in statement
    assert "NOT u.disabled AND NOT c.disabled" in oauth2.PRINCIPAL and "a.expires_at > $2" in oauth2.PRINCIPAL
    for statement in (oauth2.CODE_TO_REDEEM, oauth2.REFRESH_TO_USE):
        assert statement.rstrip().endswith("FOR UPDATE OF ac") or statement.rstrip().endswith("FOR UPDATE OF r")
    for statement in (oauth2.CLIENT_INSERT, oauth2.CLIENT_BY_ID, oauth2.CLIENT_ALL, oauth2.CLIENT_UPDATE):
        assert "secret_hash" not in statement.split("RETURNING")[-1].split("SELECT")[-1].split("FROM")[0]
    assert "c.secret_hash" in oauth2.CLIENT_SIGN_IN


# -- the migrations ------------------------------------------------------------------------------------------------


def test_the_migrations_are_numbered_from_one_without_gaps(tmp_path: Path) -> None:
    shipped = [(m.version, m.name) for m in schema.migrations()]
    assert shipped == [(1, "0001_accounts"), (2, "0002_oauth2"), (3, "0003_documents"), (4, "0004_bcf")]
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


def test_the_oauth2_migration_keeps_hashes_alone_and_goes_with_the_user_and_the_client() -> None:
    text = (schema.MIGRATIONS_DIR / "0002_oauth2.sql").read_text(encoding="utf-8")
    assert text.startswith("-- This file was generated with the assistance of an AI coding tool.")
    assert "timestamptz" not in text and "CREATE DOMAIN" not in text, "the accounts' domain serves"
    for table in ("authorization_codes", "access_tokens", "refresh_tokens"):
        body = text.split(f"CREATE TABLE {table} (")[1].split(");")[0]
        assert "user_id text NOT NULL REFERENCES users (id) ON DELETE CASCADE" in body, table
        assert "client_id text NOT NULL REFERENCES oauth_clients (client_id) ON DELETE CASCADE" in body, table
        assert "expires_at iso_utc NOT NULL" in body and f"{table}_expires_at" in text, table
        assert re.search(r"\b(code|token)_hash text PRIMARY KEY", body) and " code text" not in body, table
    assert "secret_hash text," in text and "secret text" not in text


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
    shipped = [{"version": m.version, "name": m.name} for m in schema.migrations()]
    fresh = FakePostgres(_ledger([]))
    assert await schema.migrate(fresh) == len(shipped)  # ty: ignore[invalid-argument-type]
    assert fresh.transactions == 1 and fresh.statements[0] == (schema.LOCK, (schema.LOCK_KEY,))
    assert len(fresh.scripts) == len(shipped) and "CREATE TABLE users" in fresh.scripts[0]
    records = [args[:2] for query, args in fresh.statements if query == schema.RECORD]
    assert records == [(row["version"], row["name"]) for row in shipped], "in order"

    behind = FakePostgres(_ledger(shipped[:1]))
    assert await schema.migrate(behind) == len(shipped) - 1, "only what is missing"  # ty: ignore[invalid-argument-type]
    done = FakePostgres(_ledger(shipped))
    assert await schema.migrate(done) == 0 and done.scripts == []  # ty: ignore[invalid-argument-type]
    later = {"version": len(shipped) + 1, "name": f"{len(shipped) + 1:04d}_later"}
    for rows, words in (
        ([*shipped, later], "a newer release"),
        ([{"version": 1, "name": "0001_other"}], "not the ones this server ships"),
    ):
        with pytest.raises(schema.MigrationError, match=words):
            await schema.migrate(FakePostgres(_ledger(rows)))  # ty: ignore[invalid-argument-type]


async def test_expired_rows_go_in_batches() -> None:
    counts = iter([cleanup.BATCH, cleanup.BATCH, 3])
    first = cleanup.EXPIRING[0]
    fake = FakePostgres(
        lambda query, args: next(counts) if query == first else 1 if query in cleanup.EXPIRING else None
    )
    expected = 2 * cleanup.BATCH + 3 + len(cleanup.EXPIRING) - 1
    assert await cleanup.delete_expired(fake, at="2026-11-12T00:00:00.000Z") == expected  # ty: ignore[invalid-argument-type]
    queries = [query for query, _ in fake.statements]
    assert queries == [*cleanup.EXPIRING_WITH_FILES, first, first, first, *cleanup.EXPIRING[1:]], (
        "the rows with files first, each until a batch is short"
    )
    assert {args for _, args in fake.statements} == {("2026-11-12T00:00:00.000Z", cleanup.BATCH)}


def test_every_expiring_table_is_in_the_cleaners_round() -> None:
    """A table with ``expires_at`` in any migration has its statement, which deletes by it in batches; a row that
    owns a file gives back its key."""
    text = "\n".join(m.path.read_text(encoding="utf-8") for m in schema.migrations())
    expiring = {
        table for table, body in re.findall(r"CREATE TABLE (\w+) \((.*?)\n\);", text, re.DOTALL) if "expires_at" in body
    }
    assert {
        "web_sessions",
        "authorization_codes",
        "access_tokens",
        "refresh_tokens",
        "oauth_clients",
        "selection_sessions",
        "upload_sessions",
        "upload_parts",
    } <= expiring
    statements = (*cleanup.EXPIRING_WITH_FILES, *cleanup.EXPIRING)
    cleaned = {}
    for statement in statements:
        deletes = re.match(r"\s*DELETE FROM (\w+)\s", statement)
        reads = re.search(r"\(\s*SELECT [\w.]+ FROM (\w+)\b[^()]*?\bexpires_at < \$1[^()]*?LIMIT \$2\s*\)", statement)
        assert deletes and reads and deletes[1] == reads[1], statement
        assert statement.rstrip().endswith("RETURNING storage_key") == (statement in cleanup.EXPIRING_WITH_FILES)
        cleaned[deletes[1]] = statement
    assert set(cleaned) == expiring and len(cleaned) == len(statements), "each table once"


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


# -- OAuth2 over a fake --------------------------------------------------------------------------------------------

REDIRECT = "http://127.0.0.1/callback"
VERIFIER = "v" * 50
NOW = "2026-11-12T00:00:00.000Z"
TTLS = {"code_ttl": 60, "access_ttl": 3600, "refresh_ttl": 86400, "refresh_idle": 3600}
CLIENT_ROW = {
    "client_id": "c-1",
    "name": "Server app",
    "redirect_uris": [REDIRECT],
    "is_public": False,
    "disabled": False,
    "created_at": NOW,
}


class Committing(FakePostgres):
    """A fake that notes where each transaction commits."""

    async def write(self, work: Callable[[Any], Awaitable[Any]]) -> Any:
        done = await super().write(work)
        self.statements.append(("COMMIT", ()))
        return done


def _code_row(**changes: Any) -> dict[str, Any]:
    return {
        "redirect_uri": REDIRECT,
        "redirect_required": False,
        "scope": "bcf",
        "code_challenge": pkce.challenge_for(VERIFIER),
        "resource": None,
        "created_at": NOW,
        "auth_time": NOW,
        "expires_at": later_iso(60),
        "spent": False,
        "user_id": "u-1",
        "user_disabled": False,
        "client_id": "c-1",
        "client_disabled": False,
        "pkce_optional": False,
    } | changes


def _refresh_row(**changes: Any) -> dict[str, Any]:
    return {
        "family_id": "f-1",
        "code_hash": "code-hash",
        "scope": "mcp",
        "resource": "http://testserver/mcp",
        "created_at": now_iso(),
        "auth_time": NOW,
        "expires_at": later_iso(3600),
        "spent": False,
        "user_id": "u-1",
        "user_disabled": False,
        "client_id": "c-1",
        "client_disabled": False,
    } | changes


def _tokens(fake: FakePostgres) -> PostgresTokenRepository:
    return PostgresTokenRepository(fake, **TTLS)  # ty: ignore[invalid-argument-type]


async def test_oauth2_takes_a_value_only_as_an_argument() -> None:
    fake = FakePostgres()
    clients, tokens = PostgresClientRepository(fake), _tokens(fake)  # ty: ignore[invalid-argument-type]
    await clients.get(WEAK)
    await clients.authenticate(WEAK, WEAK)
    await tokens.principal(WEAK)
    await tokens.revoke_family(WEAK, user_id=WEAK)
    await tokens.sessions_for_user(WEAK)
    for statement, _ in fake.statements:
        assert WEAK not in statement
    assert fake.statements[0] == (oauth2.CLIENT_BY_ID, (WEAK,))
    assert fake.statements[3] == (oauth2.REVOKE_FAMILY_OF_USER, (WEAK, WEAK))


async def test_a_client_is_made_by_the_rules_with_its_secrets_hash_alone() -> None:
    fake = FakePostgres()
    clients = PostgresClientRepository(fake)  # ty: ignore[invalid-argument-type]
    for words, kwargs in (
        ("client name", {"name": "  "}),
        ("cannot do without PKCE", {"public": True, "pkce_optional": True}),
        ("cannot upload headless", {"public": True, "headless_uploads": True}),
        ("must be a UUID", {"client_id": "client-1"}),
        ("loopback", {"redirect_uris": ["http://example.test/cb"]}),
        ("at most 10", {"redirect_uris": [f"https://a.test/{n}" for n in range(11)]}),
    ):
        with pytest.raises(ClientError, match=words):
            await clients.create(**({"name": "App", "redirect_uris": [REDIRECT], "public": False} | kwargs))
    assert fake.statements == [], "nothing that is refused reaches the database"
    with pytest.raises(ClientError, match="not created"):  # ON CONFLICT DO NOTHING: the id is taken
        await clients.create("App", [REDIRECT], public=False)

    def answer(query: str, args: tuple[Any, ...]) -> Any:
        if query == oauth2.CLIENT_INSERT:
            return {"client_id": args[0], "name": args[1], "redirect_uris": args[4], "created_at": args[8]}
        return None

    made = FakePostgres(answer)
    client, secret = await PostgresClientRepository(made).create(" App ", [REDIRECT, REDIRECT], public=False)  # ty: ignore[invalid-argument-type]
    (_, args) = made.statements[0]
    assert secret and secret not in args and args[6] == hash_secret(secret), "the secret is stored as its hash"
    assert client.name == "App" and client.redirect_uris == [REDIRECT] and args[7] is False
    public = FakePostgres(answer)
    _, none = await PostgresClientRepository(public).create("App", [REDIRECT], public=True, dynamic=True)  # ty: ignore[invalid-argument-type]
    assert none is None and public.statements[0][1][6] is None, "a public client has no secret"


async def test_a_client_authenticates_by_its_secrets_hash() -> None:
    rows = {
        "c-1": CLIENT_ROW | {"secret_hash": hash_secret("s3cret")},
        "c-2": CLIENT_ROW | {"client_id": "c-2", "is_public": True, "secret_hash": None},
        "c-3": CLIENT_ROW | {"client_id": "c-3", "disabled": True, "secret_hash": hash_secret("s3cret")},
    }
    clients = PostgresClientRepository(FakePostgres(lambda query, args: rows.get(args[0])))  # ty: ignore[invalid-argument-type]
    assert await clients.authenticate("c-1", "s3cret") is not None
    assert await clients.authenticate("c-1", "wrong") is None and await clients.authenticate("c-1", None) is None
    assert await clients.authenticate("c-2", None) is not None and await clients.authenticate("c-2", "x") is None
    assert await clients.authenticate("c-3", "s3cret") is None, "a disabled client does not sign in"
    assert await clients.authenticate("c-9", "s3cret") is None


async def test_a_code_is_stored_as_its_hash_and_redeemed_in_one_transaction() -> None:
    fake = Committing(lambda query, args: _code_row() if query == oauth2.CODE_TO_REDEEM else None)
    tokens = _tokens(fake)
    code = await tokens.issue_code(
        user_id="u-1", client_id="c-1", redirect_uri=REDIRECT, scope="bcf", code_challenge=pkce.challenge_for(VERIFIER)
    )
    (query, issued) = fake.statements[0]
    assert query == oauth2.CODE_INSERT and issued[0] == hash_secret(code) and code not in issued
    pair = await tokens.redeem_code(code=code, client_id="c-1", redirect_uri=REDIRECT, code_verifier=VERIFIER)
    assert isinstance(pair, TokenPair) and pair.scope == "bcf" and fake.transactions == 1
    assert [query for query, _ in fake.statements[1:]] == [
        oauth2.CODE_TO_REDEEM,
        "UPDATE authorization_codes SET spent = true WHERE code_hash = $1",
        oauth2.ACCESS_INSERT,
        oauth2.REFRESH_INSERT,
        "COMMIT",
    ]
    access, refresh = fake.statements[3][1], fake.statements[4][1]
    assert access[0] == hash_secret(pair.access_token) and refresh[0] == hash_secret(pair.refresh_token)
    assert access[3] == refresh[3] and access[4] == refresh[4] == hash_secret(code), "one family, from its code"
    assert access[8] == NOW, "the authentication of the code"
    assert pair.access_token not in access + refresh and pair.refresh_token not in access + refresh


async def test_a_refusal_commits_its_revocation_before_it_is_raised() -> None:
    replayed = Committing(lambda query, args: _code_row(spent=True) if query == oauth2.CODE_TO_REDEEM else None)
    with pytest.raises(GrantError, match="already used"):
        await _tokens(replayed).redeem_code(code="c", client_id="c-1", redirect_uri=None, code_verifier=VERIFIER)
    assert replayed.statements[1:] == [
        ("COMMIT", ()),
        (oauth2.REVOKE_CODE_TOKENS, (hash_secret("c"),)),
        ("DELETE FROM authorization_codes WHERE code_hash = $1", (hash_secret("c"),)),
    ], "what the first redemption produced goes, outside the transaction that found the replay"

    reused = Committing(lambda query, args: _refresh_row(spent=True) if query == oauth2.REFRESH_TO_USE else None)
    with pytest.raises(GrantError, match="reuse detected"):
        await _tokens(reused).refresh(refresh_token="r", client_id="c-1")
    assert reused.statements[1:] == [("COMMIT", ()), (oauth2.REVOKE_FAMILY, ("f-1",))]

    elsewhere = Committing(lambda query, args: _refresh_row() if query == oauth2.REFRESH_TO_USE else None)
    with pytest.raises(GrantError, match="another client") as refused:
        await _tokens(elsewhere).refresh(refresh_token="r", client_id="c-2")
    assert refused.value.error == "invalid_grant" and elsewhere.statements[1:] == [("COMMIT", ())], "nothing goes"
    with pytest.raises(GrantError, match="resource does not match") as refused:
        await _tokens(elsewhere).refresh(refresh_token="r", client_id="c-1", resource="https://evil.test/mcp")
    assert refused.value.error == "invalid_target"


async def test_a_refresh_rotates_within_its_family_and_keeps_its_lifetime() -> None:
    row = _refresh_row()
    fake = Committing(lambda query, args: row if query == oauth2.REFRESH_TO_USE else None)
    pair = await _tokens(fake).refresh(refresh_token="r", client_id="c-1")
    assert [query for query, _ in fake.statements] == [
        oauth2.REFRESH_TO_USE,
        "UPDATE refresh_tokens SET spent = true WHERE token_hash = $1",
        "DELETE FROM access_tokens WHERE family_id = $1",
        oauth2.ACCESS_INSERT,
        oauth2.REFRESH_INSERT,
        oauth2.FAMILY_LIFETIME,
        "COMMIT",
    ]
    assert fake.statements[1][1] == (hash_secret("r"),) and fake.statements[2][1] == ("f-1",)
    refresh = fake.statements[4][1]
    assert refresh[0] == hash_secret(pair.refresh_token)
    assert refresh[3:7] == ("f-1", "code-hash", "mcp", "http://testserver/mcp"), "its family, code, scope, binding"
    assert refresh[8] == NOW, "a refresh is no new authentication"
    assert fake.statements[5][1] == ("f-1", row["expires_at"]), "no longer than the token it replaces"


async def test_a_principal_is_found_by_the_tokens_hash() -> None:
    row = {"scope": "bcf documents", "user_id": "u-1", "username": "editor", "full_name": None, "is_admin": True}
    row |= {"client_id": "c-1", "auth_time": NOW, "resource": None}
    fake = FakePostgres(lambda query, args: row if args[0] == hash_secret("a") else None)
    tokens = _tokens(fake)
    caller = await tokens.principal("a")
    assert caller is not None and caller.display_name == "editor" and caller.scopes == ("bcf", "documents")
    assert caller.is_admin and caller.token_hash == hash_secret("a") and caller.auth_time == NOW
    assert await tokens.principal("b") is None
    assert fake.statements[0][0] == oauth2.PRINCIPAL and fake.statements[0][1][0] == hash_secret("a")


async def test_a_revocation_takes_an_access_token_alone_and_a_refresh_token_with_its_family() -> None:
    kinds = {hash_secret("r"): {"kind": "refresh", "family_id": "f-1"}, hash_secret("a"): {"kind": "access"}}
    fake = FakePostgres(lambda query, args: kinds.get(args[0]) if query == oauth2.ISSUED_TO_CLIENT else None)
    tokens = _tokens(fake)
    assert await tokens.revoke("r", client_id="c-1") and fake.statements[-1] == (oauth2.REVOKE_FAMILY, ("f-1",))
    assert await tokens.revoke("a", client_id="c-1")
    assert fake.statements[-1] == ("DELETE FROM access_tokens WHERE token_hash = $1", (hash_secret("a"),))
    assert not await tokens.revoke("x", client_id="c-1") and fake.statements[-1][0] == oauth2.ISSUED_TO_CLIENT
    assert fake.transactions == 3 and fake.statements[0][1] == (hash_secret("r"), "c-1"), "by its own client"
    counted = _tokens(FakePostgres(lambda query, args: {"n": 4}))
    assert await counted.revoke_all_for_user("u-1") == 4 and await counted.revoke_all_for_client("c-1") == 4


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


def test_the_graph_holds_oauth2_unless_postgresql_is_named(tmp_path: Path) -> None:
    graph, settings = object(), make_settings(tmp_path, allow_localhost_redirects=True)
    assert isinstance(client_store(graph, None, settings), ClientRepository)  # ty: ignore[invalid-argument-type]
    assert isinstance(token_store(graph, None, settings), TokenRepository)  # ty: ignore[invalid-argument-type]
    postgres = Postgres(URL, "", connect_timeout_seconds=1.0)
    clients = get_clients(graph, postgres, settings)  # ty: ignore[invalid-argument-type]
    assert isinstance(clients, PostgresClientRepository) and clients.allow_localhost
    tokens = get_tokens(graph, postgres, settings)  # ty: ignore[invalid-argument-type]
    assert isinstance(tokens, PostgresTokenRepository) and tokens.code_ttl == settings.authorization_code_ttl_seconds
    assert tokens.refresh_idle == settings.refresh_token_idle_seconds


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


# -- the documents -------------------------------------------------------------------------------------------------

MEMBER_READS = (
    "LATEST",
    "VERSION",
    "VERSIONS",
    "LATEST_MANY",
    "LATEST_IN_PROJECTS",
    "VALIDATION",
    "VERSIONS_SINCE",
    "CHANGE_SET",
    "PUBLICATION",
    "PUBLISH",
)
VERSION_ROW = {
    "document_id": "d-1",
    "project_id": "p-1",
    "project_name": "Building permit",
    "id": "v-1",
    "version_index": 1,
    "version_number": "1",
    "creation_date": "2026-11-12T00:00:00.000Z",
    "title": "Plan",
    "file_name": "plan.ifc",
    "size_in_bytes": 3,
    "sha256": "0" * 64,
    "storage_key": "documents/v-1",
    "author": "editor",
    "metadata": [{"name": "file_name", "value": ["plan.ifc"], "data_type": "string"}],
}
PUBLISHED = {
    "id": "pub-1",
    "storage_key": "published/pub-1.ifczip",
    "file_name": "plan.ifczip",
    "size_in_bytes": 7,
    "sha256": "1" * 64,
    "published_at": "2026-11-12T00:00:00.000Z",
    "published_by": "manager",
}
VERSION_FIELDS: dict[str, Any] = {
    "project_id": "p-1",
    "title": "Plan",
    "version_number": "",
    "file_name": "plan.ifc",
    "size_in_bytes": 3,
    "sha256": "0" * 64,
    "storage_key": "documents/x",
    "author": "editor",
    "metadata": [],
}


def test_a_members_read_of_a_document_joins_the_membership_on_the_users_id() -> None:
    """Every read of a document for a user, and the publication a member makes, reach the document through
    ``memberships``; a new version is held to the project it was given. The sessions are the caller's by their user,
    which the routes hold to the principal."""
    for name in MEMBER_READS:
        assert "JOIN memberships m ON m.project_id = d.project_id AND m.user_id = $1" in getattr(documents, name), name
    assert "FROM projects p WHERE p.project_id = $2" in documents.DOCUMENT_INSERT
    for statement in (documents.DOCUMENT_NEXT, documents.VERSION_INSERT):
        assert "WHERE d.project_id = $1 AND d.document_id = $2" in statement


def test_the_documents_migration_owns_by_foreign_keys_and_fills_the_seams() -> None:
    text = (schema.MIGRATIONS_DIR / "0003_documents.sql").read_text(encoding="utf-8")
    assert text.startswith("-- This file was generated with the assistance of an AI coding tool.")
    assert "timestamptz" not in text and "creation_date iso_utc NOT NULL" in text
    for owned in (
        "project_id text NOT NULL REFERENCES projects (project_id) ON DELETE CASCADE",
        "document_id text NOT NULL REFERENCES documents (document_id) ON DELETE CASCADE",
        "version_id text NOT NULL UNIQUE REFERENCES document_versions (id) ON DELETE CASCADE",
        "session_id text NOT NULL REFERENCES upload_sessions (id) ON DELETE CASCADE",
    ):
        assert owned in text, owned
    for table in ("upload_sessions", "upload_parts", "selection_sessions"):
        assert f"CREATE INDEX {table}_expires_at ON {table} (expires_at)" in text, "the cleaner's round"
    for view in ("document_heads", "project_files"):
        assert f"CREATE OR REPLACE VIEW {view}" in text, "the seams of 0001 that are this area's"
    for view in ("document_files", "version_validations", "version_graph_checks"):
        assert f"CREATE VIEW {view}" in text


async def test_a_documents_value_is_only_ever_an_argument() -> None:
    fake = FakePostgres()
    repository = PostgresDocumentRepository(fake)  # ty: ignore[invalid-argument-type]
    assert await repository.latest(user_id=WEAK, document_id=WEAK) is None
    assert await repository.version(user_id=WEAK, document_id=WEAK, version_index=2) is None
    assert await repository.latest_many(user_id=WEAK, document_ids=[WEAK]) == []
    assert await repository.validation(user_id=WEAK, document_id=WEAK, version_index=2, with_issues=True) is None
    assert await repository.change_set(user_id=WEAK, document_id=WEAK, version_index=2) is None
    assert await repository.publication(user_id=WEAK, document_id=WEAK, version_index=2) is None
    for statement, args in fake.statements:
        assert WEAK not in statement and args[0] == WEAK
    assert fake.statements[2] == (documents.LATEST_MANY, (WEAK, [WEAK]))
    assert fake.statements[3] == (documents.VALIDATION, (WEAK, WEAK, 2, True))


def _created(query: str, args: tuple[Any, ...]) -> Any:
    if query in (documents.DOCUMENT_INSERT, documents.DOCUMENT_NEXT):
        return {"index": 4 if query == documents.DOCUMENT_NEXT else 1}
    if query == documents.VERSION_INSERT:
        return {**VERSION_ROW, "document_id": args[1], "id": args[2], "version_index": args[4], "metadata": args[12]}
    return None


async def test_a_version_is_made_in_one_transaction_with_the_next_index_and_its_lineage() -> None:
    fake = FakePostgres(_created)
    repository = PostgresDocumentRepository(fake)  # ty: ignore[invalid-argument-type]
    metadata = default_metadata(
        file_name="plan.ifc", size_in_bytes=3, sha256="0" * 64, author="editor", project_name="Building permit"
    )
    fields = {**VERSION_FIELDS, "metadata": metadata}
    record = await repository.create_version(
        document_id=None, requested_document_id="d-9", approved_by="manager", **fields
    )
    assert fake.transactions == 1 and [query for query, _ in fake.statements] == [
        documents.DOCUMENT_INSERT,
        documents.VERSION_INSERT,
    ]
    assert record.document_id == "d-9" and record.version_index == 1 and record.metadata[0]["name"] == "file_name"
    made = fake.statements[1][1]
    assert made[3] == "editor" and made[5] == "1", "the author joins users by name; the number is the index"
    assert made[13:] == (None, None, None, None), "no lineage without a version it was built on"

    fake.statements.clear()
    record = await repository.create_version(
        document_id="d-9", parent_version_index=3, approved_by="manager", change_set_id="t-1", change_set="x", **fields
    )
    assert [query for query, _ in fake.statements] == [documents.DOCUMENT_NEXT, documents.VERSION_INSERT]
    assert fake.statements[0][1] == ("p-1", "d-9", "Plan") and record.version_index == 4
    assert fake.statements[1][1][13:] == (3, "manager", "t-1", "x")


async def test_a_version_is_refused_as_the_graph_refuses_it() -> None:
    with pytest.raises(HTTPException, match="Document not found"):  # another project's document, or none
        await PostgresDocumentRepository(FakePostgres()).create_version(document_id="d-1", **VERSION_FIELDS)  # ty: ignore[invalid-argument-type]
    no_author = FakePostgres(lambda query, args: {"index": 1} if query == documents.DOCUMENT_INSERT else None)
    with pytest.raises(HTTPException, match="Project not found"):  # the author is no user
        await PostgresDocumentRepository(no_author).create_version(document_id=None, **VERSION_FIELDS)  # ty: ignore[invalid-argument-type]


class FakeAuditGraph:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def run(self, query: str, **parameters: Any) -> list[dict[str, Any]]:
        self.events.append(parameters)
        return []


async def test_a_version_is_published_once_and_audited_when_it_is() -> None:
    event = {"type": "documents.publish", "actor": "u-1", "client_id": "c-1", "ip": None, "details": {"x": 1}}
    graph = FakeAuditGraph()
    taken = PostgresDocumentRepository(FakePostgres(), audit_graph=graph)  # ty: ignore[invalid-argument-type]
    assert not await taken.publish(
        user_id="u-1", document_id="d-1", version_index=1, publication=PUBLISHED, audit_event=event
    ), "ON CONFLICT DO NOTHING: published already, or by another meanwhile"
    assert graph.events == []
    fake = FakePostgres(lambda query, args: {"version_id": "v-1"} if query == documents.PUBLISH else None)
    published = PostgresDocumentRepository(fake, audit_graph=graph)  # ty: ignore[invalid-argument-type]
    assert await published.publish(
        user_id="u-1", document_id="d-1", version_index=1, publication=PUBLISHED, audit_event=event
    )
    assert fake.statements == [(documents.PUBLISH, ("u-1", "d-1", 1, *PUBLISHED.values()))]
    assert [(e["type"], e["actor"]) for e in graph.events] == [("documents.publish", "u-1")]


async def test_a_versions_change_set_and_check_are_read_as_the_graph_reads_them() -> None:
    changes = [{"op": "set", "guid": "g"}]

    def answer(query: str, args: tuple[Any, ...]) -> Any:
        if query == documents.CHANGE_SET:
            return {
                "change_set": pack_report(changes),
                "change_set_id": "t-1",
                "parent": 2,
                "approved_by": "m",
                "author": "a",
            }
        if query == documents.VERSIONS_SINCE:
            return [{"version_index": 3, "author": "a", "approved_by": None, "change_set_id": None, "change_set": None}]
        if query == documents.VALIDATION:
            return {
                "state": "done",
                "issue_count": 1,
                "error_count": 0,
                "truncated": False,
                "checked_at": "2026-11-12T00:00:00.000Z",
                "ruleset": "IFC4",
                "checks": None,
                "report": pack_report([{"message": "m"}]),
                "rooms": None,
                "graph_issue_count": None,
                "graph_error_count": None,
                "graph_ruleset": None,
                "graph_report": None,
            }
        return None

    repository = PostgresDocumentRepository(FakePostgres(answer))  # ty: ignore[invalid-argument-type]
    found = await repository.change_set(user_id="u", document_id="d-1", version_index=3)
    assert found == {
        "change_set_id": "t-1",
        "base": {"document_id": "d-1", "version_index": 2},
        "proposed_by": "a",
        "approved_by": "m",
        "changes": changes,
    }
    assert await repository.versions_since(user_id="u", document_id="d-1", since=2, until=3) == [
        {"version_index": 3, "author": "a", "approved_by": None, "change_set_id": None, "changes": None}
    ], "a whole file has no changes"
    validation = await repository.validation(user_id="u", document_id="d-1", version_index=3, with_issues=True)
    assert validation is not None and validation.issue_count == 1 and validation.issues == [{"message": "m"}]


async def test_an_upload_session_keeps_the_tokens_hash_and_its_parts_in_order() -> None:
    def answer(query: str, args: tuple[Any, ...]) -> Any:
        if query == documents.PARTS_DELETE:
            return [{"storage_key": "parts/a"}, {"storage_key": None}]
        return None

    fake = FakePostgres(answer)
    sessions = PostgresUploadSessionRepository(fake, ui_ttl_seconds=600, upload_ttl_seconds=3600)  # ty: ignore[invalid-argument-type]
    files = [{"session_file_id": "f", "file_name": "plan.ifc"}]
    session_id, token = await sessions.create(
        user_id="u-1",
        username="editor",
        callback_url="http://localhost/cb",
        callback_expires_in=60,
        server_context=None,
        files=files,
    )
    (_, made) = fake.statements[0]
    assert token not in made and made[0] == session_id and made[-1] == files, "the token is stored as its hash"
    assert await sessions.by_token("x" * 200) is None and await sessions.by_token("") is None
    assert len(fake.statements) == 1, "too long or empty to be one: nothing is asked"
    assert await sessions.by_token(token) is None
    assert fake.statements[-1][0] == documents.UPLOAD_BY_HASH and token not in fake.statements[-1][1]

    ids = await sessions.create_parts(session_id, 2, [(0, 9), (10, 14)])
    (_, parts) = fake.statements[-1]
    assert parts[0:2] == (session_id, 2) and parts[3:] == (ids, [0, 1], [0, 10], [9, 14])
    assert await sessions.delete_parts(session_id, 2) == ["parts/a"], "only the parts that were received"
    await sessions.update(session_id, state="uploading", files=files, extend=True)
    (_, changed) = fake.statements[-1]
    assert changed[:5] == (session_id, "uploading", None, files, True)


async def test_a_selection_session_is_finished_with_what_was_selected() -> None:
    fake = FakePostgres()
    sessions = PostgresSelectionSessionRepository(fake, ui_ttl_seconds=600)  # ty: ignore[invalid-argument-type]
    session_id, token = await sessions.create(
        user_id="u-1",
        callback_url="http://localhost/cb",
        callback_expires_in=60,
        server_context="s",
        extensions=[".ifc"],
    )
    (_, made) = fake.statements[0]
    assert token not in made and made[8] == [".ifc"] and made[9] == "new"
    await sessions.finish(session_id, state="selected", selected=["d-1:2"])
    assert fake.statements[-1] == (documents.SELECTION_FINISH, (session_id, "selected", ["d-1:2"]))
    assert await sessions.by_token("x" * 129) is None and len(fake.statements) == 2


class FakeStorage:
    def __init__(self) -> None:
        self.deleted: list[str] = []

    def delete(self, key: str) -> None:
        if key.startswith(".."):
            raise ValueError("outside the storage")
        self.deleted.append(key)


async def test_expired_upload_parts_go_with_their_files_before_their_sessions() -> None:
    def answer(query: str, args: tuple[Any, ...]) -> Any:
        if query == cleanup.EXPIRED_UPLOAD_PARTS:
            return [{"storage_key": "parts/a"}, {"storage_key": None}, {"storage_key": "../x"}]
        return 1 if query == cleanup.EXPIRED_UPLOAD_SESSIONS else 0

    fake, storage = FakePostgres(answer), FakeStorage()
    assert await cleanup.delete_expired(fake, storage=storage) == 4  # ty: ignore[invalid-argument-type]
    assert storage.deleted == ["parts/a"], "a key the storage refuses is no file of its own"
    order = [query for query, _ in fake.statements]
    assert order.index(cleanup.EXPIRED_UPLOAD_PARTS) < order.index(cleanup.EXPIRED_UPLOAD_SESSIONS)


def test_the_graph_holds_the_documents_unless_postgresql_is_named(tmp_path: Path) -> None:
    graph, settings = object(), make_settings(tmp_path)
    assert isinstance(document_store(graph, None), DocumentRepository)  # ty: ignore[invalid-argument-type]
    assert isinstance(upload_session_store(graph, None, settings), UploadSessionRepository)  # ty: ignore[invalid-argument-type]
    assert isinstance(selection_session_store(graph, None, settings), SelectionSessionRepository)  # ty: ignore[invalid-argument-type]
    assert isinstance(document_repository(graph, None), DocumentRepository)  # ty: ignore[invalid-argument-type]
    postgres = Postgres(URL, "", connect_timeout_seconds=1.0)
    chosen = document_repository(graph, postgres)  # ty: ignore[invalid-argument-type]
    assert isinstance(chosen, PostgresDocumentRepository) and chosen.audit_graph is graph, "the audit log stays"
    uploads = upload_sessions(graph, postgres, settings)  # ty: ignore[invalid-argument-type]
    assert isinstance(uploads, PostgresUploadSessionRepository)
    assert uploads.upload_ttl_seconds == settings.upload_session_ttl_seconds
    selections = selection_sessions(graph, postgres, settings)  # ty: ignore[invalid-argument-type]
    assert isinstance(selections, PostgresSelectionSessionRepository)
    assert selections.ui_ttl_seconds == settings.documents_session_ttl_seconds


# -- the BCF area --------------------------------------------------------------------------------------------------

BCF_READS = (
    bcf.TOPICS,
    bcf.TOPICS_COUNT,
    bcf.TOPIC,
    bcf.COMMENTS,
    bcf.COMMENTS_COUNT,
    bcf.COMMENT,
    bcf.VIEWPOINTS,
    bcf.VIEWPOINT,
    bcf.VIEWPOINT_NODE,
    bcf.BITMAP,
    bcf.COMPONENTS,
    bcf.RELATED,
    bcf.REFERENCES,
    bcf.HEADER_FILES,
    bcf.SNIPPET,
    bcf.BCF_DOCUMENTS,
    bcf.BCF_DOCUMENT,
    bcf.LATEST_VERSIONS,
    bcf.EVENTS,
    bcf.EVENTS_COUNT,
)


def test_the_bcf_migration_owns_by_foreign_keys_and_adds_its_files_to_the_projects() -> None:
    text = (schema.MIGRATIONS_DIR / "0004_bcf.sql").read_text(encoding="utf-8")
    assert text.startswith("-- This file was generated with the assistance of an AI coding tool.")
    assert "timestamptz" not in text and "iso_utc" in text
    assert (
        "guid text PRIMARY KEY,\n    project_id text NOT NULL REFERENCES projects (project_id) ON DELETE CASCADE,"
        in text
    )
    assert text.count("ON DELETE CASCADE") >= 11, "what a project, a topic or a viewpoint owns goes with it"
    assert "labels text[]" in text and 'title text COLLATE "C" NOT NULL' in text
    assert "CREATE OR REPLACE VIEW project_files" in text and "FROM document_files" in text and "FROM bcf_files" in text
    for view in ("proposal_files", "conversion_ifc_projects"):
        assert f"CREATE VIEW {view}" in text, "the seams to the jobs area, which follows"


@pytest.mark.parametrize("statement", BCF_READS, ids=range(len(BCF_READS)))
def test_a_bcf_read_joins_the_membership_on_the_users_id(statement: str) -> None:
    assert "JOIN memberships m ON m.project_id = " in statement and "AND m.user_id = $1" in statement


def _topic_row(**fields: Any) -> dict[str, Any]:
    return {
        "guid": GUID,
        "server_assigned_id": "ISSUE-0007",
        "title": "Wall",
        "creation_date": "2026-11-12T00:00:00.000Z",
        "creation_author": "editor",
        **fields,
    }


async def test_a_list_takes_the_filter_and_its_values_after_its_own_arguments() -> None:
    fake = FakePostgres(lambda query, args: {"total": 0} if "AS total" in query else [_topic_row()])
    topics = PostgresTopicRepository(fake)  # ty: ignore[invalid-argument-type]
    quoted = WEAK.replace("'", "''")
    compiled = compile_odata(
        filter_=f"title eq '{quoted}' and labels/any(l: l eq 'A')",
        orderby="index desc",
        top=5,
        skip=10,
        fields=TOPIC_FIELDS,
        orderable=TOPIC_ORDERABLE,
        default_order=TOPIC_DEFAULT_ORDER,
    )
    (found,) = await topics.search(user_id="u-1", project_id="p-1", compiled=compiled)
    assert found.server_assigned_id == "ISSUE-0007"
    await topics.count(user_id="u-1", project_id="p-1", compiled=compiled)
    (listing, listed), (counting, counted) = fake.statements
    assert listed == ("u-1", "p-1", 10, 5, WEAK, "A") and counted == ("u-1", "p-1", WEAK, "A")
    assert WEAK not in listing and "t.title = $5::text" in listing and "ORDER BY t.index DESC" in listing
    assert "t.title = $3::text" in counting and "$filter" not in counting


async def test_the_bcf_rules_come_before_the_database() -> None:
    fake = FakePostgres()
    topics, comments = PostgresTopicRepository(fake), PostgresCommentRepository(fake)  # ty: ignore[invalid-argument-type]
    links = PostgresTopicLinkRepository(fake)  # ty: ignore[invalid-argument-type]
    for attempt, words in (
        (topics.create(project_id="p", author="a", body=TopicPOST(guid="x", title="t")), "UUID"),
        (
            comments.create(
                project_id="p", topic_guid="t", author="a", body=CommentPOST(comment="c", viewpoint_guid="x")
            ),
            "viewpoint_guid must be a UUID",
        ),
        (
            comments.create(project_id="p", topic_guid="t", author="a", body=CommentPOST(comment="c"), reply_to="x"),
            "UUID",
        ),
        (links.set_related(project_id="p", topic_guid=GUID, author="a", guids=[GUID.upper()]), "itself"),
        (links.set_related(project_id="p", topic_guid=GUID, author="a", guids=["x"]), "UUID"),
    ):
        with pytest.raises(HTTPException, match=words):
            await attempt
    assert fake.statements == [] and fake.transactions == 0, "nothing that is refused reaches the database"


async def test_a_topic_is_counted_made_and_recorded_in_one_transaction() -> None:
    def answer(query: str, args: tuple[Any, ...]) -> Any:
        if query == bcf.TOPIC_COUNTER:
            return {"n": 7}
        if query == bcf.TOPIC_INSERT:
            return _topic_row(guid=args[0], server_assigned_id=args[2], labels=["B", "A"], topic_status="Open")
        return None

    fake = FakePostgres(answer)
    topics = PostgresTopicRepository(fake, id_prefix="T-")  # ty: ignore[invalid-argument-type]
    topic = await topics.create(
        project_id="p-1", author="editor", body=TopicPOST(guid=GUID.upper(), title="Wall", labels=["B", "A"])
    )
    assert topic.guid == GUID and fake.transactions == 1
    assert [query for query, _ in fake.statements] == [
        "SELECT 1 AS n FROM topics WHERE guid = $1",
        bcf.TOPIC_COUNTER,
        bcf.TOPIC_INSERT,
        bcf.EVENT_INSERT,
    ]
    inserted, recorded = fake.statements[2][1], fake.statements[3][1]
    assert inserted[:5] == (GUID, "p-1", "T-0007", inserted[3], "editor") and inserted[11] == ["B", "A"]
    assert recorded[1:6] == ("p-1", "topic", GUID, None, "editor")
    assert recorded[7] == ["topic_created", "title_updated", "status_updated", "label_added", "label_added"]
    assert recorded[8] == ["", "Wall", "Open", "A", "B"], "a value-less action keeps its place"


async def test_a_viewpoint_that_a_comment_refers_to_stays(tmp_path: Path) -> None:
    def answer(query: str, args: tuple[Any, ...]) -> Any:
        return {"comments": 1, "snapshot_key": None, "bitmap_keys": []} if query == bcf.VIEWPOINT_GOING else None

    fake = FakePostgres(answer)
    viewpoints = PostgresViewpointRepository(fake, LocalStorage(tmp_path), max_image_bytes=1)  # ty: ignore[invalid-argument-type]
    with pytest.raises(HTTPException) as refused:
        await viewpoints.delete(topic_guid="t", guid="v")
    assert refused.value.status_code == 409 and [query for query, _ in fake.statements] == [bcf.VIEWPOINT_GOING]


def test_the_graph_holds_the_bcf_area_unless_postgresql_is_named(tmp_path: Path) -> None:
    graph: Any = object()
    storage, postgres = LocalStorage(tmp_path), Postgres(URL, "", connect_timeout_seconds=1.0)
    topics = bcf.topic_store(graph, None, id_prefix="ISSUE-")
    assert isinstance(topics, TopicRepository)
    assert isinstance(bcf.comment_store(graph, None, topics), CommentRepository)
    assert isinstance(bcf.viewpoint_store(graph, None, storage, topics, max_image_bytes=1), ViewpointRepository)
    assert isinstance(bcf.link_store(graph, None, topics), TopicLinkRepository)
    assert isinstance(bcf.bcf_document_store(graph, None), BcfDocumentRepository)
    assert isinstance(bcf.event_store(graph, None), BcfEventRepository)
    topics = bcf.topic_store(graph, postgres, id_prefix="T-")
    assert isinstance(topics, PostgresTopicRepository) and topics.id_prefix == "T-"
    assert isinstance(bcf.comment_store(graph, postgres, topics), PostgresCommentRepository)
    assert isinstance(
        bcf.viewpoint_store(graph, postgres, storage, topics, max_image_bytes=1), PostgresViewpointRepository
    )
    assert isinstance(bcf.link_store(graph, postgres, topics), PostgresTopicLinkRepository)
    assert isinstance(bcf.bcf_document_store(graph, postgres), PostgresBcfDocumentRepository)
    assert isinstance(bcf.event_store(graph, postgres), PostgresBcfEventRepository)
