# This file was generated with the assistance of an AI coding tool.
"""Create the shared application objects from settings.

Used by the ASGI application and by the command line, so both see exactly the
same database, schema and storage.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import NamedTuple

from opencde.graph.dialect import get_dialect
from opencde.graph.driver import create_driver, create_store_driver, create_workcopy_driver, ping_within
from opencde.graph.graph import Graph
from opencde.graph.schema import apply_schema
from opencde.logging import get_logger
from opencde.postgres.database import Postgres
from opencde.settings import Settings
from opencde.storage import LocalStorage

log = get_logger(__name__)


class GraphUnavailable(RuntimeError):
    pass


async def wait_for_graph(graph: Graph, timeout_seconds: float, step_seconds: float = 1.0) -> None:
    """Wait until the database answers, or raise. Containers start in any order."""
    waited = 0.0
    while True:
        if await ping_within(graph.driver, graph.database, min(step_seconds, 2.0) + 2.0):
            return
        if waited >= timeout_seconds:
            raise GraphUnavailable(f"graph database at {graph.driver} did not answer within {timeout_seconds}s")
        await asyncio.sleep(step_seconds)
        waited += step_seconds
        step_seconds = min(step_seconds * 1.5, 5.0)


def make_graph(settings: Settings) -> Graph:
    return Graph(create_driver(settings), settings.database_name, get_dialect(settings.graph_dialect))


def make_workcopy(settings: Settings) -> Graph | None:
    """The working copy beside the archive (ADR 0024), when one is configured."""
    if not settings.has_workcopy:
        return None
    return Graph(
        create_workcopy_driver(settings), settings.workcopy_database_name, get_dialect(settings.workcopy_graph_dialect)
    )


def make_store(settings: Settings) -> Graph | None:
    """The graph of the server's own data apart from the IFC graph (F24 a), when one is configured."""
    if not settings.has_store:
        return None
    return Graph(create_store_driver(settings), settings.store_database_name, get_dialect(settings.store_graph_dialect))


def make_postgres(settings: Settings) -> Postgres | None:
    """The server's own data in PostgreSQL (ADR 0029), when ``OPENCDE_STORE_URL`` names it; nothing connects yet."""
    if settings.store_url is None:
        return None
    return Postgres(
        settings.store_url,
        settings.store_password.get_secret_value(),
        connect_timeout_seconds=settings.graph_connect_timeout_seconds,
    )


def make_storage(settings: Settings) -> LocalStorage:
    return LocalStorage(settings.data_dir)


class Graphs(NamedTuple):
    """The two graphs of a command: IFC-DB's models, and the server's own data, which is the same graph unless
    ``OPENCDE_STORE_GRAPH_URI`` names another (F24 a, ADR 0027)."""

    graph: Graph
    store: Graph

    def distinct(self) -> tuple[Graph, ...]:
        """Each graph once: one when the store shares the IFC graph's connection."""
        return (self.graph,) if self.store is self.graph else (self.graph, self.store)


@asynccontextmanager
async def _connected(graph: Graph, wait_seconds: float, schema: bool) -> AsyncGenerator[Graph, None]:
    try:
        await wait_for_graph(graph, wait_seconds)
        if schema:
            await apply_schema(graph)
        yield graph
    finally:
        await graph.close()


@asynccontextmanager
async def store_session(
    settings: Settings, *, wait_seconds: float = 30.0, schema: bool = True
) -> AsyncGenerator[Graph, None]:
    """The server's own graph for command-line use: the store when one is configured, else the IFC graph's
    connection; waits for the database and applies the schema."""
    async with _connected(make_store(settings) or make_graph(settings), wait_seconds, schema) as store:
        yield store


@asynccontextmanager
async def graph_session(
    settings: Settings, *, wait_seconds: float = 30.0, schema: bool = True
) -> AsyncGenerator[Graphs, None]:
    """Both graphs for command-line use, for what touches the models: each connected and with the schema applied."""
    async with _connected(make_graph(settings), wait_seconds, schema) as graph:
        store = make_store(settings)
        if store is None:
            yield Graphs(graph, graph)
            return
        async with _connected(store, wait_seconds, schema) as own:
            yield Graphs(graph, own)
