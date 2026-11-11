# This file was generated with the assistance of an AI coding tool.
"""Deletion of expired nodes.

Codes, tokens and sessions carry ``expires_at``. Readers always check it, so
an expired node is harmless; this job only keeps the graph small. It runs in
the server process on a timer, in small batches, and needs no database plugin
(the prototype relied on APOC's TTL, which Memgraph does not have). Upload
parts also own a file in storage, which is removed with the node.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable

from opencde.graph.graph import Graph
from opencde.graph.schema import EXPIRING_LABELS
from opencde.logging import get_logger
from opencde.storage import LocalStorage
from opencde.timeutil import now_iso

log = get_logger(__name__)

BATCH = 500
LABELS_WITH_FILES = ("UploadPart", "Precheck")


async def delete_expired(graph: Graph, at: str | None = None, storage: LocalStorage | None = None) -> int:
    """Delete every expired node of the expiring labels (and their files). Returns the number deleted."""
    moment = at or now_iso()
    deleted = 0
    for label in EXPIRING_LABELS:
        while True:
            rows = await graph.run(
                f"""
                MATCH (n:{label}) WHERE n.expires_at < $now
                WITH n LIMIT $batch
                WITH n, n.storage_key AS key
                DETACH DELETE n
                RETURN key
                """,
                now=moment,
                batch=BATCH,
            )
            if storage is not None and label in LABELS_WITH_FILES:
                for row in rows:
                    if row["key"]:
                        with contextlib.suppress(ValueError, OSError):
                            storage.delete(row["key"])
            deleted += len(rows)
            if len(rows) < BATCH:
                break
    if deleted:
        log.info("expired_nodes_deleted", count=deleted)
    return deleted


class ExpiryCleaner:
    """Background task that calls :func:`delete_expired` every ``interval`` seconds, and ``each_round`` after it."""

    def __init__(
        self,
        graph: Graph,
        interval: float,
        storage: LocalStorage | None = None,
        each_round: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self._graph = graph
        self._interval = interval
        self._storage = storage
        self._each_round = each_round
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
                await delete_expired(self._graph, storage=self._storage)
                if self._each_round is not None:
                    await self._each_round()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("expiry_cleanup_failed")
            await asyncio.sleep(self._interval)
