# This file was generated with the assistance of an AI coding tool.
"""Resource indicators (RFC 8707): which resource a token is for.

A token is for the REST APIs unless the client names a ``resource``. The only resource a client may name is the MCP
endpoint, ``<public_url>/mcp`` (ADR 0028, F31 a), and only while it is on; anything else is ``invalid_target``. A
token for it holds ``mcp`` and, when asked for, ``mcp:propose``, and nothing else, and those two scopes come only with
it. The authorization code and the token family keep the resource, so a refreshed token is bound as the first was.
The REST APIs refuse a bound token (``current_principal``), and the MCP endpoint takes nothing else
(:mod:`opencde.mcp.auth`), so that an AI's token never reaches the approval or the publication.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING
from urllib.parse import urlsplit, urlunsplit

from opencde.auth.scopes import MCP_READ, MCP_SCOPES, ScopeError

if TYPE_CHECKING:
    from opencde.settings import Settings

MCP_PATH = "/mcp"


class TargetError(ValueError):
    """``invalid_target`` (RFC 8707 §2): the resource is invalid, missing, unknown or malformed."""


def canonical(uri: str) -> str:
    """The form resources are compared in: scheme and host in lower case and no trailing slash, as the MCP
    specification writes a server's canonical URI."""
    parts = urlsplit(uri)
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), parts.query, parts.fragment))


def mcp_resource(settings: Settings) -> str:
    """The MCP endpoint as a resource: the one value ``resource`` may take."""
    return canonical(settings.url(MCP_PATH))


def requested(values: Iterable[str] | None, settings: Settings) -> str | None:
    """The resource a request names, in canonical form, or None when it names none; blank values name none.

    Raises :class:`TargetError` for anything but the MCP endpoint while it is on, and for more than one resource.
    The client's value is never repeated in the error."""
    try:
        named = {canonical(value) for value in values or () if value.strip()}
    except ValueError:  # urlsplit refuses some malformed addresses outright
        raise TargetError("malformed resource") from None
    if not named:
        return None
    if len(named) > 1:
        raise TargetError("a token is bound to one resource only")
    (resource,) = named
    if not settings.mcp_enabled:
        raise TargetError("unknown resource")
    if resource != mcp_resource(settings):
        raise TargetError(f"unknown resource; the only one is {mcp_resource(settings)}")
    return resource


def binding(scopes: list[str], values: Iterable[str] | None, settings: Settings) -> str | None:
    """The resource an authorization request binds its token to, or None for the REST APIs.

    Refuses what does not go together: :class:`~opencde.auth.scopes.ScopeError` for the scopes (``invalid_scope``),
    :class:`TargetError` for the resource (``invalid_target``). While the endpoint is off, any resource is unknown and
    so are its scopes."""
    resource = requested(values, settings)
    mcp = [scope for scope in scopes if scope in MCP_SCOPES]
    if mcp and not settings.mcp_enabled:
        raise ScopeError(f"unknown scope '{mcp[0]}'")
    if resource is None:
        if mcp:
            raise TargetError(f"the scope '{mcp[0]}' needs resource={mcp_resource(settings)}")
        return None
    if MCP_READ not in scopes or len(mcp) != len(scopes):
        raise ScopeError("a token for the MCP endpoint holds mcp, mcp:propose when asked for, and no other scope")
    return resource
