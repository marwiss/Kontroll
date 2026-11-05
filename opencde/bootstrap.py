# This file was generated with the assistance of an AI coding tool.
"""Create the shared application objects from settings.

Used by the ASGI application and by the command line, so both see exactly the
same database, schema and storage.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from opencde.graph.dialect import get_dialect
from opencde.graph.driver import create_driver, ping_within
from opencde.graph.graph import Graph
from opencde.graph.schema import apply_schema
from opencde.logging import get_logger
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


def make_storage(settings: Settings) -> LocalStorage:
    return LocalStorage(settings.data_dir)


@asynccontextmanager
async def graph_session(
    settings: Settings, *, wait_seconds: float = 30.0, schema: bool = True
) -> AsyncGenerator[Graph, None]:
    """Connected graph for command-line use: waits for the database and applies the schema."""
    graph = make_graph(settings)
    try:
        await wait_for_graph(graph, wait_seconds)
        if schema:
            await apply_schema(graph)
        yield graph
    finally:
        await graph.close()
