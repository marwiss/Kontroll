# This file was generated with the assistance of an AI coding tool.
import asyncio
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from neo4j.exceptions import TransientError

from opencde.accounts.roles import Role, comment_actions, project_actions, topic_actions, viewpoint_actions
from opencde.auth.clients import ClientError, redirect_uri_matches, validate_redirect_uri
from opencde.auth.passwords import hash_password, password_problems, verify_password
from opencde.graph import graph as graph_module
from opencde.graph.dialect import FORBIDDEN_CYPHER, MEMGRAPH, NEO4J
from opencde.graph.graph import Graph
from opencde.ids import hash_secret, is_uuid, new_id, new_secret, normalize_guid, secrets_equal
from opencde.storage import LocalStorage, TooLargeError, make_key
from opencde.timeutil import canonical_iso, is_expired, later_iso, now_iso, parse_iso, to_iso
from tests.conftest import REPO_ROOT

# --- time ---------------------------------------------------------------------


def test_timestamps_are_canonical_utc_strings() -> None:
    value = now_iso()
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z", value)
    assert to_iso(datetime(2026, 4, 28, 16, 31, 12, 270000, tzinfo=UTC)) == "2026-04-28T16:31:12.270Z"
    assert canonical_iso("2016-04-28T16:31:12.270+02:00") == "2016-04-28T14:31:12.270Z"
    assert canonical_iso("2016-04-28T16:31:12") == "2016-04-28T16:31:12.000Z", "no zone means UTC (Foundation 1.7)"
    assert canonical_iso("2016-04-28T16:31:12Z") == "2016-04-28T16:31:12.000Z"
    assert parse_iso("2016-04-28T16:31:12+0200").hour == 14
    assert later_iso(60) > now_iso()
    assert is_expired(later_iso(-1)) and not is_expired(later_iso(60)) and is_expired(None)
    assert to_iso(datetime(2026, 1, 1) + timedelta(hours=1)) == "2026-01-01T01:00:00.000Z"


# --- ids -----------------------------------------------------------------------


def test_ids_and_secrets() -> None:
    assert is_uuid(new_id()) and not is_uuid("nope") and not is_uuid("")
    assert normalize_guid("B724AAC3-5B2A-234A-D143-AE33CC184140") == "b724aac3-5b2a-234a-d143-ae33cc184140"
    secret = new_secret()
    assert len(secret) >= 40 and hash_secret(secret) != secret and len(hash_secret(secret)) == 64
    assert secrets_equal("a", "a") and not secrets_equal("a", "b")


# --- passwords -----------------------------------------------------------------


def test_password_policy_and_hashing() -> None:
    assert password_problems("short", "alice")
    assert any("user name" in str(p) for p in password_problems("alice-is-my-name-1234", "alice"))
    assert [p.key for p in password_problems("short", "alice")] == ["error.password.too_short"]
    assert password_problems("short", "alice")[0].params == {"min": 12}
    assert password_problems("password12345678")  # weak despite length
    assert password_problems("a-long-and-strong-passphrase", "alice") == []
    digest = hash_password("a-long-and-strong-passphrase")
    assert digest.startswith("$argon2id$")
    assert verify_password("a-long-and-strong-passphrase", digest)
    assert not verify_password("other", digest)
    assert not verify_password("anything", None)
    assert not verify_password("anything", "garbage")


# --- roles --------------------------------------------------------------------


def test_roles_map_to_spec_actions() -> None:
    assert project_actions(None) == [] and project_actions(Role.VIEWER) == []
    assert project_actions(Role.CONTRIBUTOR) == ["createTopic"]
    assert project_actions(Role.MANAGER) == ["update", "createTopic", "createDocument"]
    assert topic_actions(Role.CONTRIBUTOR, is_author=False) == ["createComment", "createViewpoint"]
    assert "delete" in topic_actions(Role.CONTRIBUTOR, is_author=True)
    assert "delete" not in topic_actions(Role.EDITOR, is_author=False)
    assert "delete" in topic_actions(Role.MANAGER, is_author=False)
    assert comment_actions(Role.CONTRIBUTOR, is_author=False) == []
    assert comment_actions(Role.CONTRIBUTOR, is_author=True) == ["update", "delete"]
    assert viewpoint_actions(Role.VIEWER, is_author=True) == []
    assert viewpoint_actions(Role.EDITOR, is_author=False) == ["delete"]


# --- redirect URIs ---------------------------------------------------------------


def test_redirect_uri_rules() -> None:
    assert validate_redirect_uri("https://app.example.test/cb") == "https://app.example.test/cb"
    assert validate_redirect_uri("http://127.0.0.1/cb") == "http://127.0.0.1/cb"
    assert validate_redirect_uri("http://[::1]:5000/cb") == "http://[::1]:5000/cb"
    assert validate_redirect_uri("myapp://callback") == "myapp://callback"
    assert validate_redirect_uri("http://localhost:8080/cb", allow_localhost=True)
    for bad in (
        "http://localhost:8080/cb",
        "http://example.test/cb",
        "https://x.test/cb#f",
        "javascript:alert(1)",
        "/relative",
        "",
    ):
        with pytest.raises(ClientError):
            validate_redirect_uri(bad)
    assert redirect_uri_matches("https://a.test/cb", "https://a.test/cb")
    assert not redirect_uri_matches("https://a.test/cb", "https://a.test/cb/")
    assert not redirect_uri_matches("https://a.test/cb", "https://a.test:8443/cb")
    assert redirect_uri_matches("http://127.0.0.1/cb", "http://127.0.0.1:53421/cb"), "loopback port may vary (RFC 8252)"
    assert not redirect_uri_matches("http://127.0.0.1/cb", "http://127.0.0.1:53421/other")
    assert not redirect_uri_matches("http://localhost/cb", "http://localhost:53421/cb"), (
        "localhost is not loopback-by-IP"
    )


# --- storage ------------------------------------------------------------------------


def test_storage_keys_cannot_escape(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path)
    key = make_key("snapshots", "6dbd4d52-14db-11ee-be56-0242ac120002", "png")
    assert key == "snapshots/6dbd4d52-14db-11ee-be56-0242ac120002.png"
    storage.write_bytes(key, b"\x89PNG")
    assert storage.exists(key) and storage.size(key) == 4
    assert list(storage.iter_keys("snapshots")) == [key]
    for bad in ("../x", "snapshots/../../etc/passwd", "unknown/abc", "snapshots/sub/dir", "snapshots/"):
        with pytest.raises(ValueError):
            storage.path(bad)
    with pytest.raises(ValueError):
        make_key("snapshots", "not-a-uuid")
    with pytest.raises(ValueError):
        make_key("snapshots", "6dbd4d52-14db-11ee-be56-0242ac120002", "p/ng")
    storage.delete(key)
    assert not storage.exists(key)


def test_storage_stream_counts_bytes(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path)
    key = make_key("parts", "6dbd4d52-14db-11ee-be56-0242ac120002")

    async def chunks(sizes: list[int]):
        for size in sizes:
            yield b"x" * size

    assert asyncio.run(storage.write_stream(key, chunks([10, 10]), max_bytes=20)) == 20
    with pytest.raises(TooLargeError):
        asyncio.run(storage.write_stream(key, chunks([10, 11]), max_bytes=20))
    assert storage.size(key) == 20, "a failed stream leaves the previous content untouched"
    assert not any(p.name.endswith(".tmp") for p in (tmp_path / "parts").iterdir())


# --- dialects -------------------------------------------------------------------------


def test_dialect_ddl_and_cypher_lint() -> None:
    assert NEO4J.unique_constraint("Topic", "guid") == (
        "CREATE CONSTRAINT Topic_guid_unique IF NOT EXISTS FOR (n:Topic) REQUIRE n.guid IS UNIQUE"
    )
    assert MEMGRAPH.unique_constraint("Topic", "guid") == "CREATE CONSTRAINT ON (n:Topic) ASSERT n.guid IS UNIQUE"
    assert MEMGRAPH.index("Topic", "guid") == "CREATE INDEX ON :Topic(guid)"
    with pytest.raises(ValueError):
        NEO4J.index("Topic", "guid) DROP DATABASE neo4j //")

    # Application Cypher must stay portable between Neo4j and Memgraph (ADR 0003).
    offenders: list[str] = []
    for path in (REPO_ROOT / "opencde").rglob("*.py"):
        if path.name == "dialect.py":
            continue
        text = path.read_text(encoding="utf-8")
        for pattern, reason in FORBIDDEN_CYPHER:
            for match in re.finditer(pattern, text):
                line = text.count("\n", 0, match.start()) + 1
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{line}: {reason}")
    assert offenders == []


# --- schema statements ----------------------------------------------------------


class _DdlDriver:
    """Answers each schema statement with the next outcome: an exception to raise, or nothing for a change."""

    def __init__(self, *outcomes: Exception | None) -> None:
        self.outcomes = list(outcomes)
        self.calls = 0

    def session(self, database: str) -> "_DdlDriver":
        return self

    async def __aenter__(self) -> "_DdlDriver":
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def run(self, statement: str) -> "_DdlDriver":
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if outcome is not None:
            raise outcome
        return self

    async def consume(self) -> SimpleNamespace:
        return SimpleNamespace(counters=SimpleNamespace(contains_updates=True, constraints_added=1, indexes_added=0))


async def test_a_schema_statement_survives_a_transient_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """The server and `opencde seed` can apply the schema together; Neo4j answers one with a deadlock."""
    monkeypatch.setattr(graph_module, "DDL_RETRY_SECONDS", 0)
    driver = _DdlDriver(TransientError("deadlock"), TransientError("deadlock"), None)
    assert await Graph(driver, "neo4j", NEO4J).ddl("CREATE CONSTRAINT") is True  # type: ignore[arg-type]
    assert driver.calls == 3


async def test_a_schema_statement_gives_up_when_the_error_stays(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(graph_module, "DDL_RETRY_SECONDS", 0)
    driver = _DdlDriver(*[TransientError("deadlock")] * graph_module.DDL_ATTEMPTS)
    with pytest.raises(TransientError):
        await Graph(driver, "neo4j", NEO4J).ddl("CREATE CONSTRAINT")  # type: ignore[arg-type]
    assert driver.calls == graph_module.DDL_ATTEMPTS
