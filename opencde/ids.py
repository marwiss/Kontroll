# This file was generated with the assistance of an AI coding tool.
"""Identifiers and secrets.

Every node has a server-generated UUID. Client-facing BCF guids are UUIDs
too (BCF API 3.2.9). Secrets (codes, tokens, client secrets) are 256-bit
random strings that are stored only as SHA-256 hashes.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid

SECRET_BYTES = 32


def new_id() -> str:
    return str(uuid.uuid4())


def is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        return False
    return True


def normalize_guid(value: str) -> str:
    """Lower-case canonical form, so 'B724AAC3-...' and 'b724aac3-...' are the same topic."""
    return str(uuid.UUID(value))


def new_secret() -> str:
    """A URL-safe random secret with 256 bits of entropy."""
    return secrets.token_urlsafe(SECRET_BYTES)


def hash_secret(value: str) -> str:
    """Hash for storage and lookup. High-entropy inputs need no salt or slow hash."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def secrets_equal(left: str, right: str) -> bool:
    """Constant-time comparison for secrets and their hashes."""
    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))
