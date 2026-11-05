# This file was generated with the assistance of an AI coding tool.
"""Timestamps as the server stores and sends them.

All timestamps are ISO 8601 strings in UTC with millisecond precision and a
``Z`` suffix, for example ``2026-11-05T12:34:56.789Z``. Storing strings instead
of the databases' temporal types keeps Neo4j and Memgraph interchangeable and
makes string comparison equal to chronological comparison (Foundation API 1.7
requires ISO 8601; a value without a time zone is UTC).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

ISO_FORMAT = "%Y-%m-%dT%H:%M:%S.%f"


def to_iso(moment: datetime) -> str:
    """Canonical string for an aware or naive (= UTC) datetime."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    moment = moment.astimezone(UTC)
    return moment.strftime(ISO_FORMAT)[:-3] + "Z"


def now() -> datetime:
    return datetime.now(UTC)


def now_iso() -> str:
    return to_iso(now())


def later_iso(seconds: float) -> str:
    """Canonical string for ``seconds`` from now; used for ``expires_at``."""
    return to_iso(now() + timedelta(seconds=seconds))


def parse_iso(text: str) -> datetime:
    """Parse any ISO 8601 datetime the specifications allow, returning an aware UTC datetime."""
    cleaned = text.strip()
    if cleaned.endswith(("Z", "z")):
        cleaned = cleaned[:-1] + "+00:00"
    moment = datetime.fromisoformat(cleaned)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


def canonical_iso(text: str) -> str:
    """Re-format a client-supplied timestamp into the stored form, so comparisons stay valid."""
    return to_iso(parse_iso(text))


def is_expired(expires_at: str | None, at: str | None = None) -> bool:
    """True when ``expires_at`` lies in the past (or is missing)."""
    if not expires_at:
        return True
    return expires_at <= (at or now_iso())
