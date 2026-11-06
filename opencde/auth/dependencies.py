# This file was generated with the assistance of an AI coding tool.
"""Bearer-token authentication for API routes.

``Authorization: Bearer <token>`` is the only way to call the BCF and
Documents APIs (Foundation API 2.2; cookies are never accepted there). A
missing or bad token yields ``401`` with a ``WWW-Authenticate`` header;
a token without the scope a route needs yields ``403``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from opencde.auth.tokens import Principal, TokenRepository
from opencde.deps import GraphDep, SettingsDep
from opencde.errors import CODE_INSUFFICIENT_SCOPE, CODE_REAUTHENTICATION_REQUIRED, CODE_UNAUTHENTICATED, ApiError
from opencde.graph.graph import Graph
from opencde.settings import Settings
from opencde.timeutil import later_iso

BEARER_CHALLENGE = {"WWW-Authenticate": 'Bearer realm="opencde"'}

# Declares the scheme in the OpenAPI document, so that every operation behind ``current_principal`` says it
# needs a token and the interactive documentation offers to enter one. Refusals stay in ``current_principal``.
BEARER_SCHEME = HTTPBearer(
    auto_error=False,
    scheme_name="bearer",
    description="An access token from the OAuth2 flow of the Foundation API.",
)


def token_repository(graph: Graph, settings: Settings) -> TokenRepository:
    return TokenRepository(
        graph,
        code_ttl=settings.authorization_code_ttl_seconds,
        access_ttl=settings.access_token_ttl_seconds,
        refresh_ttl=settings.refresh_token_ttl_seconds,
    )


def get_tokens(graph: GraphDep, settings: SettingsDep) -> TokenRepository:
    return token_repository(graph, settings)


TokensDep = Annotated[TokenRepository, Depends(get_tokens)]


def _bearer(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    scheme, _, value = header.partition(" ")
    if scheme.lower() != "bearer" or not value.strip():
        return None
    return value.strip()


async def current_principal(
    request: Request,
    tokens: TokensDep,
    _declared: Annotated[HTTPAuthorizationCredentials | None, Depends(BEARER_SCHEME)],
) -> Principal:
    token = _bearer(request)
    if token is None:
        raise ApiError(401, "Authentication required", code=CODE_UNAUTHENTICATED, headers=BEARER_CHALLENGE)
    principal = await tokens.principal(token)
    if principal is None:
        raise HTTPException(  # code "invalid_token" follows from the status
            401,
            "Invalid or expired access token",
            headers={"WWW-Authenticate": 'Bearer realm="opencde", error="invalid_token"'},
        )
    request.state.principal = principal
    return principal


PrincipalDep = Annotated[Principal, Depends(current_principal)]


def require_scope(scope: str) -> Callable[[Principal], Principal]:
    """Dependency factory: the principal must hold ``scope``."""

    def check(principal: PrincipalDep) -> Principal:
        if not principal.has_scope(scope):
            raise ApiError(
                403,
                f"This operation needs the '{scope}' scope",
                code=CODE_INSUFFICIENT_SCOPE,
                headers={"WWW-Authenticate": f'Bearer realm="opencde", error="insufficient_scope", scope="{scope}"'},
            )
        return principal

    return check


BcfPrincipal = Annotated[Principal, Depends(require_scope("bcf"))]
DocumentsPrincipal = Annotated[Principal, Depends(require_scope("documents"))]


def admin_principal(principal: Annotated[Principal, Depends(require_scope("admin"))]) -> Principal:
    """The administration API: the ``admin`` scope and the administrator role, both."""
    if not principal.is_admin:
        raise HTTPException(403, "This operation needs an administrator account")
    return principal


AdminPrincipal = Annotated[Principal, Depends(admin_principal)]

# Dangerous administration calls need an authentication this recent: a refresh never renews it, only a new
# authorization (the app opens the sign-in page again), which is what "fresh" means to the client.
REAUTHENTICATION_WINDOW_SECONDS = 600


def fresh_admin_principal(principal: AdminPrincipal) -> Principal:
    if principal.auth_time is None or principal.auth_time < later_iso(-REAUTHENTICATION_WINDOW_SECONDS):
        raise ApiError(
            403,
            "This operation needs a sign-in from the last ten minutes; authorize again and retry",
            code=CODE_REAUTHENTICATION_REQUIRED,
        )
    return principal


FreshAdminPrincipal = Annotated[Principal, Depends(fresh_admin_principal)]
