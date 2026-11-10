# This file was generated with the assistance of an AI coding tool.
"""A thin, typed layer over the Bolt driver.

Repositories receive a :class:`Graph` and run parameterised Cypher through
it. Three ways to run queries, from simplest to most controlled:

* ``await graph.run(query, **params)`` for a single auto-committed statement
  (reads and simple writes),
* ``await graph.write(work)`` / ``await graph.read(work)`` for a retried
  transaction function that runs several statements atomically,
* the ``Tx`` object inside such a function, whose ``run`` returns plain dicts.

Records come back as dictionaries; nodes are returned as property maps because
queries project them with ``properties(n)`` or map projections, never as raw
node objects. Never build Cypher from user input: parameters only.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, LiteralString, TypeVar, cast

from neo4j import AsyncDriver, AsyncManagedTransaction
from neo4j.exceptions import ClientError, TransientError

from opencde.graph.dialect import Dialect
from opencde.logging import get_logger

log = get_logger(__name__)

T = TypeVar("T")

DDL_ATTEMPTS = 30  # schema statements that meet a transient error: about two minutes in all, at growing intervals
DDL_RETRY_SECONDS = 0.5
DDL_RETRY_MAX_SECONDS = 5.0


class Tx:
    """Statements inside one transaction. Created by :meth:`Graph.write` and :meth:`Graph.read`."""

    def __init__(self, tx: AsyncManagedTransaction) -> None:
        self._tx = tx

    async def run(self, query: str, /, **params: Any) -> list[dict[str, Any]]:
        result = await self._tx.run(cast("LiteralString", query), params)
        return [record.data() async for record in result]

    async def one(self, query: str, /, **params: Any) -> dict[str, Any] | None:
        rows = await self.run(query, **params)
        return rows[0] if rows else None

    async def counters(self, query: str, /, **params: Any) -> Any:
        """Run a write statement and return the summary counters (nodes_created, ...)."""
        result = await self._tx.run(cast("LiteralString", query), params)
        summary = await result.consume()
        return summary.counters


class Graph:
    """Entry point for all database access; one instance per application."""

    def __init__(self, driver: AsyncDriver, database: str, dialect: Dialect) -> None:
        self.driver = driver
        self.database = database
        self.dialect = dialect

    async def run(self, query: str, /, **params: Any) -> list[dict[str, Any]]:
        records, _summary, _keys = await self.driver.execute_query(
            cast("LiteralString", query), parameters_=params, database_=self.database
        )
        return [record.data() for record in records]

    async def one(self, query: str, /, **params: Any) -> dict[str, Any] | None:
        rows = await self.run(query, **params)
        return rows[0] if rows else None

    async def write(self, work: Callable[[Tx], Awaitable[T]]) -> T:
        async with self.driver.session(database=self.database) as session:
            return await session.execute_write(lambda tx: work(Tx(tx)))

    async def read(self, work: Callable[[Tx], Awaitable[T]]) -> T:
        async with self.driver.session(database=self.database) as session:
            return await session.execute_read(lambda tx: work(Tx(tx)))

    async def ddl(self, statement: str) -> bool:
        """Run a schema statement outside any transaction; True if it changed something.

        Memgraph refuses schema changes inside explicit transactions (which
        ``execute_query`` uses), so the statement runs as an auto-commit
        ``session.run``, which the driver does not retry. The server and a command
        such as ``opencde seed`` can apply the schema at the same moment, and the
        database then answers one of them with a transient error (a deadlock in
        Neo4j), so that is retried here. Memgraph answers with a transient error too
        while it cannot get unique access to its storage, which a periodic snapshot or
        a long write holds for seconds, so the retries last about two minutes.
        Memgraph also raises when a constraint or index already exists; that is
        treated as "nothing to do".
        """
        attempt = 0
        while True:
            attempt += 1
            try:
                async with self.driver.session(database=self.database) as session:
                    result = await session.run(cast("LiteralString", statement))
                    summary = await result.consume()
            except ClientError as exc:
                message = f"{exc.code} {exc.message}"
                if any(marker in message for marker in self.dialect.already_exists_markers):
                    return False
                raise
            except TransientError:
                if attempt >= DDL_ATTEMPTS:
                    raise
                log.debug("schema_statement_retried", attempt=attempt)
                await asyncio.sleep(min(DDL_RETRY_SECONDS * attempt, DDL_RETRY_MAX_SECONDS))
                continue
            counters = summary.counters
            added = getattr(counters, "constraints_added", 0) + getattr(counters, "indexes_added", 0)
            return added > 0 if counters.contains_updates or added else False

    async def schema_rows(self, statement: str) -> list[dict[str, Any]]:
        """The rows of a schema listing, which Memgraph too only answers outside explicit transactions."""
        async with self.driver.session(database=self.database) as session:
            result = await session.run(cast("LiteralString", statement))
            return [record.data() async for record in result]

    async def close(self) -> None:
        await self.driver.close()
