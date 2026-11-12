# This file was generated with the assistance of an AI coding tool.
"""A thin layer over asyncpg's pool, in the shape of :class:`opencde.graph.graph.Graph` (ADR 0029).

Repositories receive a :class:`Postgres` and run statements through it, in three ways:

* ``await postgres.run(query, *args)`` and ``one`` for the rows of a single auto-committed statement,
  ``execute`` for the number of rows a write touched,
* ``await postgres.write(work)`` for several statements in one transaction, retried when PostgreSQL rolls it back
  for a deadlock or a serialization failure,
* the ``Tx`` inside such a function, with the same three methods.

A statement is a literal with numbered parameters (``$1``), which asyncpg binds on the server in a prepared
statement; rows come back as dictionaries, ``jsonb`` as Python values. The pool is made on first use, so that
nothing connects until a statement runs, as the graph's driver does. asyncpg comes with the ``postgres`` extra.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from opencde.logging import get_logger

log = get_logger(__name__)

T = TypeVar("T")

APPLICATION_NAME = "dataregium-opencde"
MAX_CONNECTIONS = 10
WRITE_ATTEMPTS = 5  # a transaction PostgreSQL rolled back (SQLSTATE class 40) is run again, at growing intervals
WRITE_RETRY_SECONDS = 0.05


class PostgresUnavailable(RuntimeError):
    pass


def _count(status: str) -> int:
    """The rows a command touched, from its status: ``DELETE 3``, ``INSERT 0 1``, ``UPDATE 0``."""
    last = status.rsplit(" ", 1)[-1]
    return int(last) if last.isdigit() else 0


class Tx:
    """Statements on one connection, inside a transaction when made by :meth:`Postgres.write`."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    async def run(self, query: str, /, *args: Any) -> list[dict[str, Any]]:
        return [dict(record) for record in await self._connection.fetch(query, *args)]

    async def one(self, query: str, /, *args: Any) -> dict[str, Any] | None:
        record = await self._connection.fetchrow(query, *args)
        return dict(record) if record is not None else None

    async def execute(self, query: str, /, *args: Any) -> int:
        return _count(await self._connection.execute(query, *args))

    async def script(self, text: str) -> None:
        """Several statements without parameters: a migration of the package's own (``opencde.postgres.schema``)."""
        await self._connection.execute(text)


async def _init_connection(connection: Any) -> None:
    """``json`` and ``jsonb`` as Python values rather than their text."""
    for name in ("json", "jsonb"):
        await connection.set_type_codec(
            name,
            encoder=lambda value: json.dumps(value, separators=(",", ":")),
            decoder=json.loads,
            schema="pg_catalog",
        )


class Postgres:
    """Entry point for the store's statements in PostgreSQL; one instance per application."""

    def __init__(self, url: str, password: str, *, connect_timeout_seconds: float) -> None:
        if importlib.util.find_spec("asyncpg") is None:
            raise RuntimeError("OPENCDE_STORE_URL needs the postgres extra: opencde-server[postgres]")
        self.url = url  # never holds the password (the settings refuse one), so it can be logged and shown
        self._password = password
        self._timeout = connect_timeout_seconds
        self._pool: Any = None
        self._lock = asyncio.Lock()

    async def _connections(self) -> Any:
        if self._pool is None:
            async with self._lock:
                if self._pool is None:
                    import asyncpg

                    self._pool = await asyncpg.create_pool(
                        self.url,
                        password=self._password or None,
                        min_size=0,
                        max_size=MAX_CONNECTIONS,
                        timeout=self._timeout,
                        init=_init_connection,
                        server_settings={"application_name": APPLICATION_NAME},
                    )
        return self._pool

    async def run(self, query: str, /, *args: Any) -> list[dict[str, Any]]:
        async with (await self._connections()).acquire() as connection:
            return await Tx(connection).run(query, *args)

    async def one(self, query: str, /, *args: Any) -> dict[str, Any] | None:
        async with (await self._connections()).acquire() as connection:
            return await Tx(connection).one(query, *args)

    async def execute(self, query: str, /, *args: Any) -> int:
        async with (await self._connections()).acquire() as connection:
            return await Tx(connection).execute(query, *args)

    async def write(self, work: Callable[[Tx], Awaitable[T]]) -> T:
        from asyncpg.exceptions import TransactionRollbackError

        attempt = 0
        while True:
            attempt += 1
            try:
                async with (await self._connections()).acquire() as connection, connection.transaction():
                    return await work(Tx(connection))
            except TransactionRollbackError:
                if attempt >= WRITE_ATTEMPTS:
                    raise
                log.debug("postgres_transaction_retried", attempt=attempt)
                await asyncio.sleep(WRITE_RETRY_SECONDS * attempt)

    async def ping(self, seconds: float) -> bool:
        """True when the database answers a trivial statement within ``seconds``."""
        try:
            async with asyncio.timeout(seconds):
                return await self.one("SELECT 1 AS ok") == {"ok": 1}
        except Exception as exc:  # refused, unknown host, wrong password, a timeout: all of them mean "unreachable"
            log.warning("postgres_ping_failed", error_type=type(exc).__name__)
            return False

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None


async def wait_for_postgres(postgres: Postgres, timeout_seconds: float, step_seconds: float = 1.0) -> None:
    """Wait until the database answers, or raise. Containers start in any order."""
    waited = 0.0
    while not await postgres.ping(min(step_seconds, 2.0) + 2.0):
        if waited >= timeout_seconds:
            raise PostgresUnavailable(f"PostgreSQL at {postgres.url} did not answer within {timeout_seconds}s")
        await asyncio.sleep(step_seconds)
        waited += step_seconds
        step_seconds = min(step_seconds * 1.5, 5.0)
