# This file was generated with the assistance of an AI coding tool.
"""Foundation API 1.0 (https://github.com/buildingSMART/foundation-API/tree/v1.0).

* ``GET /foundation/versions``          2.1 Versions service: which OpenCDE APIs this server offers and where.
* ``GET /foundation/1.0/auth``          2.2.1 Authentication information: the OAuth2 endpoints and flows.
* ``GET /foundation/1.0/current-user``  2.3.1 The signed-in user.

The versions service is always served from ``/foundation/versions``; the other
APIs may be relocated through ``api_base_url``. It lists both versions of the BCF
API, the newest first. Clients still call ``/bcf/{version}/auth`` and
``/bcf/{version}/current-user`` for 3.0 too, so those are served as aliases. In
2.1 they are real services, in :mod:`opencde.bcf.routes_v21`.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from opencde.auth.dependencies import PrincipalDep
from opencde.deps import SettingsDep
from opencde.settings import Settings

router = APIRouter(tags=["Foundation API"])

BCF_VERSION = "3.0"
BCF_OLDER_VERSION = "2.1"
DOCUMENTS_VERSION = "1.0"
FOUNDATION_VERSION = "1.0"


class CurrentUser(BaseModel):
    """``user_GET.json``: ``id`` is the user id used throughout the APIs, ``name`` is for display."""

    id: str
    name: str | None = None


def versions_payload(settings: Settings) -> dict[str, Any]:
    return {
        "versions": [
            {
                "api_id": "foundation",
                "version_id": FOUNDATION_VERSION,
                "detailed_version": "https://github.com/buildingSMART/foundation-API/tree/v1.0",
                "api_base_url": settings.url(f"/foundation/{FOUNDATION_VERSION}"),
            },
            {
                "api_id": "bcf",
                "version_id": BCF_VERSION,
                "detailed_version": "https://github.com/buildingSMART/BCF-API/tree/release_3_0",
                "api_base_url": settings.url(f"/bcf/{BCF_VERSION}"),
            },
            {
                "api_id": "bcf",
                "version_id": BCF_OLDER_VERSION,
                "detailed_version": "https://github.com/buildingSMART/BCF-API/tree/release_2_1",
                "api_base_url": settings.url(f"/bcf/{BCF_OLDER_VERSION}"),
            },
            {
                "api_id": "documents",
                "version_id": DOCUMENTS_VERSION,
                "detailed_version": "https://github.com/buildingSMART/documents-API/tree/release_1_0",
                "api_base_url": settings.url(f"/documents/{DOCUMENTS_VERSION}"),
            },
        ]
    }


def auth_payload(settings: Settings) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "oauth2_auth_url": settings.url("/foundation/oauth2/auth"),
        "oauth2_token_url": settings.url("/foundation/oauth2/token"),
        "http_basic_supported": False,
        "supported_oauth2_flows": ["authorization_code_grant"],
        # Additional properties (Foundation API 1.8) that help clients do the right thing.
        "oauth2_revocation_url": settings.url("/foundation/oauth2/revoke"),
        "oauth2_pkce_methods": ["S256"],
        "oauth2_pkce_required": True,
    }
    if settings.dynamic_client_registration:
        payload["oauth2_dynamic_client_reg_url"] = settings.url("/foundation/oauth2/reg")
    return payload


def auth_payload_v21(settings: Settings) -> dict[str, Any]:
    """What 2.1's authentication service says. A client registered through this URL need not use PKCE, so it does not
    say that PKCE is required, only that it is on offer."""
    payload = auth_payload(settings)
    del payload["oauth2_pkce_required"]
    if settings.dynamic_client_registration:
        payload["oauth2_dynamic_client_reg_url"] = settings.url(f"/bcf/{BCF_OLDER_VERSION}/oauth2/reg")
    return payload


@router.get("/foundation/versions", summary="2.1 Versions service")
async def versions(settings: SettingsDep) -> dict[str, Any]:
    return versions_payload(settings)


@router.get(f"/foundation/{FOUNDATION_VERSION}/auth", summary="2.2.1 Authentication information")
async def auth_info(settings: SettingsDep) -> dict[str, Any]:
    return auth_payload(settings)


@router.get(f"/foundation/{FOUNDATION_VERSION}/current-user", summary="2.3.1 Current user", response_model=CurrentUser)
async def current_user(principal: PrincipalDep) -> CurrentUser:
    return CurrentUser(id=principal.username, name=principal.display_name)


# -- what BCF API 2.1 calls these under its own address, for clients that do so on 3.0 too ---

alias_router = APIRouter(tags=["BCF API"], include_in_schema=False)


@alias_router.get(f"/bcf/{BCF_VERSION}/auth")
async def bcf_auth(settings: SettingsDep) -> dict[str, Any]:
    return auth_payload(settings)


@alias_router.get(f"/bcf/{BCF_VERSION}/current-user", response_model=CurrentUser)
async def bcf_current_user(principal: PrincipalDep) -> CurrentUser:
    return CurrentUser(id=principal.username, name=principal.display_name)
