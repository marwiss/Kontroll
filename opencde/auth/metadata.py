# This file was generated with the assistance of an AI coding tool.
"""The authorization server metadata (RFC 8414): ``GET /.well-known/oauth-authorization-server``.

What ``GET /foundation/1.0/auth`` tells an OpenCDE client, in the form OAuth clients outside OpenCDE look for, MCP
clients first among them (ADR 0028). It describes the authorization server the Foundation API already has, so it is
served whether or not the MCP endpoint is on. Public and cacheable, as the capabilities document is; nothing in it is
secret. ``issuer`` is the ``iss`` the authorization responses carry (RFC 9207). A server whose public URL has a path
needs its proxy to pass ``/.well-known/oauth-authorization-server/<path>`` on to this address.
"""

from __future__ import annotations

from fastapi import APIRouter, Response
from pydantic import BaseModel, Field

from opencde.auth import pkce
from opencde.auth.routes import AUTH_METHOD_BASIC, AUTH_METHOD_NONE, SUPPORTED_GRANT_TYPES
from opencde.auth.scopes import offered_scopes
from opencde.deps import SettingsDep

TAG = "OAuth2 metadata (extension)"
CACHEABLE = "public, max-age=300"
AUTH_METHODS = [AUTH_METHOD_BASIC, "client_secret_post", AUTH_METHOD_NONE]

router = APIRouter(tags=[TAG])


class AuthorizationServerMetadata(BaseModel):
    """RFC 8414 §2, for this server's OAuth2 endpoints (Foundation API 2.2)."""

    issuer: str = Field(description="The server's public URL, equal to `iss` in every authorization response.")
    authorization_endpoint: str
    token_endpoint: str
    revocation_endpoint: str
    registration_endpoint: str | None = Field(None, description="Only while dynamic client registration is on.")
    scopes_supported: list[str] = Field(description="The scopes on offer; `mcp` ones only with the MCP endpoint.")
    response_types_supported: list[str]
    response_modes_supported: list[str]
    grant_types_supported: list[str]
    token_endpoint_auth_methods_supported: list[str]
    revocation_endpoint_auth_methods_supported: list[str]
    code_challenge_methods_supported: list[str]
    authorization_response_iss_parameter_supported: bool = Field(description="RFC 9207: `iss` is always sent.")


@router.get(
    "/.well-known/oauth-authorization-server",
    summary="Authorization server metadata (RFC 8414)",
    response_model=AuthorizationServerMetadata,
    response_model_exclude_none=True,
)
async def authorization_server_metadata(response: Response, settings: SettingsDep) -> AuthorizationServerMetadata:
    """Where to sign in and how: the endpoints, PKCE with `S256`, the grants and the scopes. No authentication."""
    response.headers["Cache-Control"] = CACHEABLE
    return AuthorizationServerMetadata(
        issuer=settings.public_url,
        authorization_endpoint=settings.url("/foundation/oauth2/auth"),
        token_endpoint=settings.url("/foundation/oauth2/token"),
        revocation_endpoint=settings.url("/foundation/oauth2/revoke"),
        registration_endpoint=settings.url("/foundation/oauth2/reg") if settings.dynamic_client_registration else None,
        scopes_supported=offered_scopes(settings),
        response_types_supported=["code"],
        response_modes_supported=["query"],
        grant_types_supported=list(SUPPORTED_GRANT_TYPES),
        token_endpoint_auth_methods_supported=AUTH_METHODS,
        revocation_endpoint_auth_methods_supported=AUTH_METHODS,
        code_challenge_methods_supported=[pkce.METHOD],
        authorization_response_iss_parameter_supported=True,
    )
