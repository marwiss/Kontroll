# This file was generated with the assistance of an AI coding tool.
"""The store's tables in PostgreSQL: plain SQL migrations, run at startup (ADR 0029).

``migrations/NNNN_<area>.sql`` are numbered from 1 without gaps and run in order. ``migrate`` applies those the
database lacks in one transaction, under an advisory lock so that several processes starting at once do not race, and
records each in ``schema_migrations``. PostgreSQL's DDL is transactional, so a migration that fails leaves nothing
behind. A database that holds a migration this server does not know was used by a newer release and is refused. A
released migration is never edited; a change is a new file.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from opencde.logging import get_logger
from opencde.postgres.database import Postgres, Tx
from opencde.timeutil import now_iso

log = get_logger(__name__)

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
_FILE_NAME = re.compile(r"^(\d{4})_[a-z0-9_]+\.sql$")
#: The advisory lock the migrations are applied under: any constant, the same in every process of the server.
LOCK_KEY = 0x0DA7A2E6

LOCK = "SELECT pg_advisory_xact_lock($1)"
LEDGER = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version integer PRIMARY KEY,
    name text NOT NULL,
    applied_at text NOT NULL
)
"""
APPLIED = "SELECT version, name FROM schema_migrations ORDER BY version"
RECORD = "INSERT INTO schema_migrations (version, name, applied_at) VALUES ($1, $2, $3)"


class MigrationError(RuntimeError):
    pass


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    path: Path


def migrations(folder: Path = MIGRATIONS_DIR) -> list[Migration]:
    """The migrations the server ships, in order."""
    found: list[Migration] = []
    for path in sorted(folder.glob("*.sql")):
        match = _FILE_NAME.match(path.name)
        if match is None:
            raise MigrationError(f"a migration is named NNNN_name.sql: {path.name}")
        found.append(Migration(int(match[1]), path.stem, path))
    if [migration.version for migration in found] != list(range(1, len(found) + 1)):
        raise MigrationError("the migrations are numbered from 1 without gaps")
    return found


async def migrate(postgres: Postgres, folder: Path = MIGRATIONS_DIR) -> int:
    """Apply the migrations the database lacks; returns how many ran."""
    shipped = migrations(folder)

    async def work(tx: Tx) -> int:
        await tx.execute(LOCK, LOCK_KEY)
        await tx.execute(LEDGER)
        recorded = {int(row["version"]): row["name"] for row in await tx.run(APPLIED)}
        known = {migration.version: migration.name for migration in shipped}
        unknown = sorted(set(recorded) - set(known))
        if unknown:
            raise MigrationError(f"the database has migrations this server does not know: {unknown}; a newer release")
        renamed = [version for version, name in recorded.items() if known[version] != name]
        if renamed:
            raise MigrationError(f"the database's migrations {renamed} are not the ones this server ships")
        ran = 0
        for migration in shipped:
            if migration.version in recorded:
                continue
            await tx.script(migration.path.read_text(encoding="utf-8"))
            await tx.execute(RECORD, migration.version, migration.name, now_iso())
            ran += 1
        return ran

    ran = await postgres.write(work)
    (log.info if ran else log.debug)("postgres_migrated", ran=ran, version=len(shipped))
    return ran
