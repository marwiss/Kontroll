# This file was generated with the assistance of an AI coding tool.
"""Deletion of expired nodes.

Codes, tokens and sessions carry ``expires_at``. Readers always check it, so
an expired node is harmless; this job only keeps the graph small. It runs in
the server process on a timer, in small batches, and needs no database plugin
(the prototype relied on APOC's TTL, which Memgraph does not have).
"""

from __future__ import annotations

import asyncio
import contextlib

from opencde.graph.graph import Graph
from opencde.graph.schema import EXPIRING_LABELS
from opencde.logging import get_logger
from opencde.timeutil import now_iso

log = get_logger(__name__)

BATCH = 500


async def delete_expired(graph: Graph, at: str | None = None) -> int:
    """Delete every expired node of the expiring labels. Returns the number deleted."""
    moment = at or now_iso()
    deleted = 0
    for label in EXPIRING_LABELS:
        while True:
            rows = await graph.run(
                f"MATCH (n:{label}) WHERE n.expires_at < $now WITH n LIMIT $batch DETACH DELETE n RETURN count(*) AS n",
                now=moment,
                batch=BATCH,
            )
            count = int(rows[0]["n"]) if rows else 0
            deleted += count
            if count < BATCH:
                break
    if deleted:
        log.info("expired_nodes_deleted", count=deleted)
    return deleted


class ExpiryCleaner:
    """Background task that calls :func:`delete_expired` every ``interval`` seconds."""

    def __init__(self, graph: Graph, interval: float) -> None:
        self._graph = graph
        self._interval = interval
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._loop(), name="expiry-cleaner")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def _loop(self) -> None:
        while True:
            try:
                await delete_expired(self._graph)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("expiry_cleanup_failed")
            await asyncio.sleep(self._interval)
