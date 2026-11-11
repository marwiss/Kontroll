# This file was generated with the assistance of an AI coding tool.
"""Who may call the MCP endpoint (ADR 0028, F31 a), and the document that says how to become one.

``/mcp`` takes only an access token issued for its own resource, ``<public_url>/mcp`` (RFC 8707,
:mod:`opencde.auth.resources`), and the REST APIs refuse such tokens, so an AI's token never reaches the approval or
the publication. ``mcp`` opens the read tools, and ``mcp:propose`` the change sets too. A refusal follows the
authorization section of the MCP specification: ``401`` names the protected resource metadata (RFC 9728) and the
scope to ask for, and ``403 insufficient_scope`` names the scopes a step-up asks for.

``GET /.well-known/oauth-protected-resource/mcp`` is that metadata, served only while the endpoint is on
(``OPENCDE_MCP_ENABLED``); public and cacheable, as the capabilities document is.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel

from opencde.auth.dependencies import BEARER_SCHEME, TokensDep, bearer_token
from opencde.auth.metadata import CACHEABLE, TAG
from opencde.auth.resources import mcp_resource
from opencde.auth.scopes import MCP_PROPOSE, MCP_READ, MCP_SCOPES
from opencde.deps import SettingsDep
from opencde.errors import CODE_INSUFFICIENT_SCOPE, CODE_INVALID_TOKEN, CODE_UNAUTHENTICATED, ApiError
from opencde.settings import Settings
from opencde.store.oauth2.tokens import Principal

METADATA_PATH = "/.well-known/oauth-protected-resource/mcp"

router = APIRouter(tags=[TAG])


def challenge(settings: Settings, *, error: str | None = None, scope: str = MCP_READ) -> dict[str, str]:
    """``WWW-Authenticate`` of a refusal: where the metadata is and which scope to ask for (RFC 9728 §5.1)."""
    params = [f'error="{error}"'] if error else []
    params += [f'resource_metadata="{settings.url(METADATA_PATH)}"', f'scope="{scope}"']
    return {"WWW-Authenticate": "Bearer " + ", ".join(params)}


async def mcp_principal(
    request: Request,
    tokens: TokensDep,
    settings: SettingsDep,
    _declared: Annotated[HTTPAuthorizationCredentials | None, Depends(BEARER_SCHEME)],
) -> Principal:
    """The caller of ``/mcp``: a token bound to the endpoint that holds ``mcp``. Every other token is ``401``, the
    REST APIs' among them, so the client signs in again for this resource."""
    token = bearer_token(request)
    if token is None:
        raise ApiError(401, "Authentication required", code=CODE_UNAUTHENTICATED, headers=challenge(settings))
    principal = await tokens.principal(token)
    if principal is None or principal.resource != mcp_resource(settings):
        raise ApiError(
            401,
            "Invalid or expired access token for the MCP endpoint",
            code=CODE_INVALID_TOKEN,
            headers=challenge(settings, error="invalid_token"),
        )
    require_mcp_scope(principal, MCP_READ, settings)
    request.state.principal = principal
    return principal


McpPrincipal = Annotated[Principal, Depends(mcp_principal)]


def require_mcp_scope(principal: Principal, scope: str, settings: Settings) -> None:
    """``403 insufficient_scope`` unless the principal holds ``scope``: ``mcp`` for the read tools, ``mcp:propose``
    for the change sets. The challenge names every scope the tool needs, so the client can ask for them at once."""
    if principal.has_scope(scope):
        return
    needed = " ".join(MCP_SCOPES) if scope == MCP_PROPOSE else MCP_READ
    raise ApiError(
        403,
        f"This tool needs the '{scope}' scope",
        code=CODE_INSUFFICIENT_SCOPE,
        headers=challenge(settings, error="insufficient_scope", scope=needed),
    )


class ProtectedResourceMetadata(BaseModel):
    """RFC 9728 §2, for the MCP endpoint."""

    resource: str
    authorization_servers: list[str]
    scopes_supported: list[str]
    bearer_methods_supported: list[str]


@router.get(METADATA_PATH, summary="Protected resource metadata of the MCP endpoint (RFC 9728)")
async def protected_resource_metadata(response: Response, settings: SettingsDep) -> ProtectedResourceMetadata:
    """The resource a token for the MCP endpoint is bound to, who issues it and with which scopes. No
    authentication."""
    response.headers["Cache-Control"] = CACHEABLE
    return ProtectedResourceMetadata(
        resource=mcp_resource(settings),
        authorization_servers=[settings.public_url],
        scopes_supported=list(MCP_SCOPES),
        bearer_methods_supported=["header"],
    )
