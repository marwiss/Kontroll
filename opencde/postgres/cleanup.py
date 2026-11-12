# This file was generated with the assistance of an AI coding tool.
"""Deletion of expired rows in PostgreSQL, as :mod:`opencde.graph.cleanup` deletes expired nodes (ADR 0029).

Readers always check ``expires_at``, so an expired row is harmless; this only keeps the tables small. It runs in the
cleaner's round, in batches. Each expiring table has its statement here, as its area moves. The rows that own a file
in storage (an upload's parts, a precheck) return its key, and the file goes with the row.
"""

from __future__ import annotations

import contextlib
from collections.abc import Awaitable, Callable

from opencde.logging import get_logger
from opencde.postgres.database import Postgres
from opencde.storage import LocalStorage
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
EXPIRED_SELECTION_SESSIONS = """
DELETE FROM selection_sessions WHERE id IN (SELECT id FROM selection_sessions WHERE expires_at < $1 LIMIT $2)
"""
#: The parts of an expired upload go before it, also those that would outlast it, so that none leaves its file.
EXPIRED_UPLOAD_PARTS = """
DELETE FROM upload_parts WHERE id IN (
    SELECT p.id FROM upload_parts p JOIN upload_sessions s ON s.id = p.session_id
    WHERE p.expires_at < $1 OR s.expires_at < $1
    LIMIT $2
)
RETURNING storage_key
"""
EXPIRED_UPLOAD_SESSIONS = """
DELETE FROM upload_sessions WHERE id IN (SELECT id FROM upload_sessions WHERE expires_at < $1 LIMIT $2)
"""
#: Of the checks only a precheck expires; a version's check lasts as long as the version.
EXPIRED_PRECHECKS = """
DELETE FROM validations WHERE id IN (SELECT id FROM validations WHERE expires_at < $1 LIMIT $2)
RETURNING storage_key
"""
EXPIRED_CHANGE_SET_DRAFTS = """
DELETE FROM change_set_drafts
WHERE changeset_id IN (SELECT changeset_id FROM change_set_drafts WHERE expires_at < $1 LIMIT $2)
"""
#: The statements of the rows that own a file, each returning its key; they run first, so that a row goes before
#: what owns it (an upload's parts before their session).
EXPIRING_WITH_FILES = (EXPIRED_UPLOAD_PARTS, EXPIRED_PRECHECKS)
#: One statement per expiring table that owns no file, each run with the moment and the batch size.
EXPIRING = (
    EXPIRED_WEB_SESSIONS,
    EXPIRED_AUTHORIZATION_CODES,
    EXPIRED_ACCESS_TOKENS,
    EXPIRED_REFRESH_TOKENS,
    EXPIRED_CLIENTS,
    EXPIRED_SELECTION_SESSIONS,
    EXPIRED_UPLOAD_SESSIONS,
    EXPIRED_CHANGE_SET_DRAFTS,
)


async def _in_batches(delete: Callable[[str], Awaitable[int]], statement: str) -> int:
    deleted = 0
    while True:
        done = await delete(statement)
        deleted += done
        if done < BATCH:
            return deleted


async def delete_expired(postgres: Postgres, at: str | None = None, storage: LocalStorage | None = None) -> int:
    """Delete every expired row of the expiring tables, and the files of those that own one. Returns the number
    deleted."""
    moment = at or now_iso()

    async def rows(statement: str) -> int:
        return await postgres.execute(statement, moment, BATCH)

    async def rows_with_files(statement: str) -> int:
        gone = await postgres.run(statement, moment, BATCH)
        for row in gone:
            if storage is not None and row["storage_key"]:
                with contextlib.suppress(ValueError, OSError):  # a key the storage refuses was never one it wrote
                    storage.delete(row["storage_key"])
        return len(gone)

    deleted = 0
    for statement in EXPIRING_WITH_FILES:
        deleted += await _in_batches(rows_with_files, statement)
    for statement in EXPIRING:
        deleted += await _in_batches(rows, statement)
    if deleted:
        log.info("expired_rows_deleted", count=deleted)
    return deleted
