# This file was generated with the assistance of an AI coding tool.
"""OAuth2 scopes.

The OpenCDE specifications do not define scopes, so this server keeps a small
fixed set. A client that asks for nothing gets everything a user may do with
the standard APIs; a client that asks for an unknown scope is refused
(``invalid_scope``). Routes of the BCF API require ``bcf``, routes of the
Documents API ``documents``. The ``admin`` scope opens the administration API
(an extension outside the specifications) and must be asked for explicitly;
it works only for users who are administrators. The ``project`` scope opens the
administration of the projects a user manages (an extension too), asked for
explicitly as well; the role in each project decides.
"""

from __future__ import annotations

SCOPES: dict[str, str] = {
    "profile": "Who you are (Foundation API current-user).",
    "bcf": "Issue management through the BCF API.",
    "documents": "Document exchange through the Documents API.",
    "project": "Administration of the projects you manage (members and roles).",
    "admin": "Server administration (users, projects, clients, logs) for administrators.",
}

DEFAULT_SCOPES = ("profile", "bcf", "documents")


class ScopeError(ValueError):
    pass


def parse_scope(requested: str | None) -> list[str]:
    """Split a space-separated scope string; unknown or duplicate values are errors."""
    if requested is None or not requested.strip():
        return list(DEFAULT_SCOPES)
    scopes: list[str] = []
    for value in requested.split():
        if value not in SCOPES:
            raise ScopeError(f"unknown scope '{value}'")
        if value not in scopes:
            scopes.append(value)
    return scopes


def scope_string(scopes: list[str]) -> str:
    return " ".join(scopes)
