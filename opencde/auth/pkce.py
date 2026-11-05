# This file was generated with the assistance of an AI coding tool.
"""Proof Key for Code Exchange (RFC 7636).

Every authorization code request must carry a ``code_challenge`` computed as
``BASE64URL(SHA256(code_verifier))``; the token request proves possession of
the verifier. Only the ``S256`` method is accepted, as OAuth 2.1 requires;
``plain`` offers no protection against a stolen code.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import re

# RFC 7636 §4.1: 43-128 characters from the unreserved set.
_VERIFIER = re.compile(r"^[A-Za-z0-9\-._~]{43,128}$")
# A base64url SHA-256 digest without padding is exactly 43 characters.
_CHALLENGE = re.compile(r"^[A-Za-z0-9\-_]{43}$")

METHOD = "S256"


def is_valid_challenge(challenge: str | None) -> bool:
    return bool(challenge) and _CHALLENGE.match(challenge or "") is not None


def is_valid_verifier(verifier: str | None) -> bool:
    return bool(verifier) and _VERIFIER.match(verifier or "") is not None


def challenge_for(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def verify(verifier: str | None, challenge: str | None) -> bool:
    """True when ``verifier`` hashes to ``challenge`` (constant-time comparison)."""
    if not is_valid_verifier(verifier) or not is_valid_challenge(challenge):
        return False
    return hmac.compare_digest(challenge_for(verifier or ""), challenge or "")
