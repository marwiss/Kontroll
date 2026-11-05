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

from opencde.auth.tokens import Principal, TokenRepository
from opencde.deps import GraphDep, SettingsDep
from opencde.graph.graph import Graph
from opencde.settings import Settings

BEARER_CHALLENGE = {"WWW-Authenticate": 'Bearer realm="opencde"'}


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


async def current_principal(request: Request, tokens: TokensDep) -> Principal:
    token = _bearer(request)
    if token is None:
        raise HTTPException(401, "Authentication required", headers=BEARER_CHALLENGE)
    principal = await tokens.principal(token)
    if principal is None:
        raise HTTPException(
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
            raise HTTPException(
                403,
                f"This operation needs the '{scope}' scope",
                headers={"WWW-Authenticate": f'Bearer realm="opencde", error="insufficient_scope", scope="{scope}"'},
            )
        return principal

    return check


BcfPrincipal = Annotated[Principal, Depends(require_scope("bcf"))]
DocumentsPrincipal = Annotated[Principal, Depends(require_scope("documents"))]
