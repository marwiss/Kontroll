# This file was generated with the assistance of an AI coding tool.
"""Integration fixtures: a real graph database in a container, and PostgreSQL in one when a test asks for it.

Neo4j always; Memgraph too when ``OPENCDE_TEST_MEMGRAPH=1`` (nightly CI),
which is how the dialect-neutral Cypher of ADR 0003 is proven. One container
per test session; every test starts from an empty graph. PostgreSQL (ADR 0029)
starts with the first test that asks for ``postgres_target`` or ``pg``, once
for the session; every such test starts from empty tables with the migrations
applied.

Two ways to reach the database from a test:

* ``graph``: an async :class:`Graph` for repository tests (``async def test_...``).
  All awaits run in the test's own event loop, which the async driver needs.
* ``client``: the application in a ``TestClient`` for API tests (sync). The
  app owns its own driver; the database is wiped with the sync driver first.
"""

from __future__ import annotations

import os
import re
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from neo4j import GraphDatabase
from testcontainers.community.postgres import PostgresContainer
from testcontainers.core.container import DockerContainer
from testcontainers.core.wait_strategies import LogMessageWaitStrategy

from opencde.bootstrap import make_graph
from opencde.graph.graph import Graph
from opencde.graph.schema import apply_schema
from opencde.main import create_app
from opencde.postgres.database import Postgres
from opencde.postgres.schema import migrate
from opencde.seed import wipe
from opencde.settings import GraphDialect, Settings
from tests.conftest import test_settings

NEO4J_IMAGE = "neo4j:5.26.32-community"
MEMGRAPH_IMAGE = "memgraph/memgraph:3.14.0"
NEO4J_PASSWORD = "integration-test-password"
POSTGRES_IMAGE = "postgres:17.6-alpine"
#: Every table of the store but the ledger of the migrations, whichever areas have theirs, emptied at once.
EMPTY_POSTGRES = """
DO $$
DECLARE tables text;
BEGIN
    SELECT string_agg(format('%I', tablename), ', ') INTO tables
    FROM pg_tables WHERE schemaname = current_schema() AND tablename <> 'schema_migrations';
    IF tables IS NOT NULL THEN
        EXECUTE 'TRUNCATE ' || tables || ' CASCADE';
    END IF;
END
$$
"""

pytestmark = pytest.mark.integration


@dataclass(frozen=True)
class GraphTarget:
    dialect: GraphDialect
    uri: str
    user: str
    password: str


def _targets() -> list[str]:
    targets = ["neo4j"]
    if os.environ.get("OPENCDE_TEST_MEMGRAPH") == "1":
        targets.append("memgraph")
    return targets


@pytest.fixture(scope="session", params=_targets())
def graph_target(request: pytest.FixtureRequest) -> Iterator[GraphTarget]:
    if request.param == "neo4j":
        container = (
            DockerContainer(NEO4J_IMAGE)
            .with_env("NEO4J_AUTH", f"neo4j/{NEO4J_PASSWORD}")
            .with_env("NEO4J_server_memory_heap_max__size", "512m")
            .with_env("NEO4J_server_memory_pagecache_size", "128m")
            .with_exposed_ports(7687)
            .waiting_for(LogMessageWaitStrategy(re.compile(r"Started\.")).with_startup_timeout(120))
        )
        with container:
            port = container.get_exposed_port(7687)
            yield GraphTarget(
                GraphDialect.NEO4J, f"bolt://{container.get_container_host_ip()}:{port}", "neo4j", NEO4J_PASSWORD
            )
    else:
        container = (
            DockerContainer(MEMGRAPH_IMAGE)
            .with_exposed_ports(7687)
            .waiting_for(LogMessageWaitStrategy(re.compile(r"You are running Memgraph")).with_startup_timeout(120))
        )
        with container:
            port = container.get_exposed_port(7687)
            yield GraphTarget(GraphDialect.MEMGRAPH, f"bolt://{container.get_container_host_ip()}:{port}", "", "")


@pytest.fixture
def settings(graph_target: GraphTarget, tmp_path: Path) -> Settings:
    return test_settings(
        tmp_path,
        graph_dialect=graph_target.dialect,
        graph_uri=graph_target.uri,
        graph_user=graph_target.user,
        graph_password=graph_target.password,
        graph_connect_timeout_seconds=10.0,
        cleanup_interval_seconds=3600,
        upload_part_bytes=1024,  # small parts so multi-part uploads are exercised with small files
    )


@pytest.fixture
def clean_database(graph_target: GraphTarget, settings: Settings) -> None:
    """Empty the database with the sync driver (safe from any event loop)."""
    with GraphDatabase.driver(graph_target.uri, auth=(graph_target.user, graph_target.password)) as driver:
        while True:
            records, _, _ = driver.execute_query(
                "MATCH (n) WITH n LIMIT 2000 DETACH DELETE n RETURN count(*) AS n", database_=settings.database_name
            )
            if not records or records[0]["n"] == 0:
                break


@pytest.fixture
async def graph(settings: Settings, clean_database: None) -> AsyncIterator[Graph]:
    """A connected Graph with an empty database and the schema applied, for async tests."""
    graph = make_graph(settings)
    await apply_schema(graph)
    await wipe(graph)
    try:
        yield graph
    finally:
        await graph.close()


@pytest.fixture
def client(settings: Settings, clean_database: None) -> Iterator[TestClient]:
    """The application connected to the test database, for sync API tests."""
    with TestClient(create_app(settings, startup_wait_seconds=30)) as test_client:
        yield test_client


@dataclass(frozen=True)
class PostgresTarget:
    url: str  # without the password, as OPENCDE_STORE_URL wants it
    password: str


@pytest.fixture(scope="session")
def postgres_target() -> Iterator[PostgresTarget]:
    with PostgresContainer(POSTGRES_IMAGE, driver=None) as container:
        host, port = container.get_container_host_ip(), container.get_exposed_port(5432)
        yield PostgresTarget(f"postgresql://{container.username}@{host}:{port}/{container.dbname}", container.password)


async def emptied_postgres(target: PostgresTarget) -> Postgres:
    """A connection to the migrated database with every table emptied; the caller closes it."""
    postgres = Postgres(target.url, target.password, connect_timeout_seconds=10.0)
    await migrate(postgres)
    await postgres.execute(EMPTY_POSTGRES)
    return postgres


@pytest.fixture
async def pg(postgres_target: PostgresTarget) -> AsyncIterator[Postgres]:
    """A migrated PostgreSQL with empty tables, for async tests."""
    postgres = await emptied_postgres(postgres_target)
    try:
        yield postgres
    finally:
        await postgres.close()
