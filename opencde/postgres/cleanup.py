# This file was generated with the assistance of an AI coding tool.
"""Deletion of expired rows in PostgreSQL, as :mod:`opencde.graph.cleanup` deletes expired nodes (ADR 0029).

Readers always check ``expires_at``, so an expired row is harmless; this only keeps the tables small. It runs in the
cleaner's round, in batches. Each expiring table has its statement here, as its area moves.
"""

from __future__ import annotations

from opencde.logging import get_logger
from opencde.postgres.database import Postgres
from opencde.timeutil import now_iso

log = get_logger(__name__)

BATCH = 500

EXPIRED_WEB_SESSIONS = """
DELETE FROM web_sessions WHERE id IN (SELECT id FROM web_sessions WHERE expires_at < $1 LIMIT $2)
"""


async def delete_expired(postgres: Postgres, at: str | None = None) -> int:
    """Delete every expired row of the expiring tables. Returns the number deleted."""
    moment = at or now_iso()
    deleted = 0
    while True:
        done = await postgres.execute(EXPIRED_WEB_SESSIONS, moment, BATCH)
        deleted += done
        if done < BATCH:
            break
    if deleted:
        log.info("expired_rows_deleted", count=deleted)
    return deleted
