# This file was generated with the assistance of an AI coding tool.
"""Create and probe the Bolt connection to the graph database."""

from __future__ import annotations

import asyncio

from neo4j import AsyncDriver, AsyncGraphDatabase

from opencde.logging import get_logger
from opencde.settings import Settings

log = get_logger(__name__)


def create_driver(settings: Settings) -> AsyncDriver:
    """Build the driver. No network traffic happens until the first query."""
    return AsyncGraphDatabase.driver(
        settings.graph_uri,
        auth=(settings.graph_user, settings.graph_password.get_secret_value()),
        connection_timeout=settings.graph_connect_timeout_seconds,
        max_connection_lifetime=30 * 60,
        user_agent="kontroll-opencde",
    )


async def ping(driver: AsyncDriver, database: str) -> bool:
    """True when the database answers a trivial query.

    Callers bound the wait with ``asyncio.timeout(...)``; a timeout counts as
    "not reachable" like any other failure.
    """
    try:
        records, _summary, _keys = await driver.execute_query("RETURN 1 AS ok", database_=database)
        return bool(records) and records[0]["ok"] == 1
    except Exception as exc:  # the driver raises several unrelated types; all of them mean "unreachable"
        log.warning("graph_ping_failed", error_type=type(exc).__name__)
        return False


async def ping_within(driver: AsyncDriver, database: str, seconds: float) -> bool:
    """``ping`` with an upper bound on the wait."""
    try:
        async with asyncio.timeout(seconds):
            return await ping(driver, database)
    except TimeoutError:
        log.warning("graph_ping_timeout", seconds=seconds)
        return False
