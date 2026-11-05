# This file was generated with the assistance of an AI coding tool.
"""Password hashing and policy.

Argon2id through ``pwdlib`` with the library's recommended parameters. The
policy rejects short and guessable passwords (``zxcvbn`` score below 3) and
passwords that contain the user name.
"""

from __future__ import annotations

from pwdlib import PasswordHash
from zxcvbn import zxcvbn

from opencde.settings import MIN_PASSWORD_LENGTH

_hasher = PasswordHash.recommended()

# Verifying against this hash when the user does not exist keeps the response
# time of a failed sign-in the same whether or not the user name is valid.
DUMMY_HASH = _hasher.hash("not-a-real-password-just-for-timing")

MIN_SCORE = 3


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    try:
        return _hasher.verify(password, password_hash or DUMMY_HASH)
    except Exception:  # malformed hash: treat as mismatch, never as an error the caller can observe
        return False


def password_problems(password: str, username: str = "", extra_inputs: list[str] | None = None) -> list[str]:
    """Why a password is not acceptable; an empty list means it is fine."""
    problems: list[str] = []
    if len(password) < MIN_PASSWORD_LENGTH:
        problems.append(f"use at least {MIN_PASSWORD_LENGTH} characters")
    if len(password) > 256:
        problems.append("use at most 256 characters")
    if username and username.lower() in password.lower():
        problems.append("do not include the user name")
    if not problems:
        result = zxcvbn(password, user_inputs=[username, *(extra_inputs or [])])
        if result["score"] < MIN_SCORE:
            hint = result["feedback"].get("warning") or "it is too easy to guess"
            problems.append(f"too weak: {hint}")
    return problems
