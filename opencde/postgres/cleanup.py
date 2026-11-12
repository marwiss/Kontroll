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
EXPIRED_AUTHORIZATION_CODES = """
DELETE FROM authorization_codes
WHERE code_hash IN (SELECT code_hash FROM authorization_codes WHERE expires_at < $1 LIMIT $2)
"""
EXPIRED_ACCESS_TOKENS = """
DELETE FROM access_tokens WHERE token_hash IN (SELECT token_hash FROM access_tokens WHERE expires_at < $1 LIMIT $2)
"""
EXPIRED_REFRESH_TOKENS = """
DELETE FROM refresh_tokens WHERE token_hash IN (SELECT token_hash FROM refresh_tokens WHERE expires_at < $1 LIMIT $2)
"""
#: Only a self-registered client expires, once unused; what was issued to it goes with it.
EXPIRED_CLIENTS = """
DELETE FROM oauth_clients WHERE client_id IN (SELECT client_id FROM oauth_clients WHERE expires_at < $1 LIMIT $2)
"""
#: One statement per expiring table, each run with the moment and the batch size.
EXPIRING = (
    EXPIRED_WEB_SESSIONS,
    EXPIRED_AUTHORIZATION_CODES,
    EXPIRED_ACCESS_TOKENS,
    EXPIRED_REFRESH_TOKENS,
    EXPIRED_CLIENTS,
)


async def delete_expired(postgres: Postgres, at: str | None = None) -> int:
    """Delete every expired row of the expiring tables. Returns the number deleted."""
    moment = at or now_iso()
    deleted = 0
    for statement in EXPIRING:
        while True:
            done = await postgres.execute(statement, moment, BATCH)
            deleted += done
            if done < BATCH:
                break
    if deleted:
        log.info("expired_rows_deleted", count=deleted)
    return deleted
