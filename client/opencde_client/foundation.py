# This file was generated with the assistance of an AI coding tool.
"""Foundation API 1.0: discovery (``/foundation/versions``), authentication info and the current user.

A server that has only BCF API 2.1 has no Foundation API. It tells the same things in its own services, so
:func:`discover` and :func:`auth_info` can ask those too.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from opencde_client.errors import ApiError
from opencde_client.http import ApiSession


@dataclass(frozen=True)
class ApiVersion:
    api_id: str
    version_id: str
    detailed_version: str | None = None


@dataclass(frozen=True)
class AuthInfo:
    """``GET /foundation/1.0/auth``: where to sign in and what the server supports."""

    oauth2_auth_url: str | None
    oauth2_token_url: str | None
    oauth2_dynamic_client_reg_url: str | None
    http_basic_supported: bool
    supported_oauth2_flows: tuple[str, ...]
    extras: dict[str, Any]

    @property
    def oauth2_revocation_url(self) -> str | None:
        value = self.extras.get("oauth2_revocation_url")
        return str(value) if value else None

    @property
    def pkce_required(self) -> bool:
        return bool(self.extras.get("oauth2_pkce_required", True))


def _auth_info(body: dict[str, Any]) -> AuthInfo:
    known = {
        "oauth2_auth_url",
        "oauth2_token_url",
        "oauth2_dynamic_client_reg_url",
        "http_basic_supported",
        "supported_oauth2_flows",
    }
    return AuthInfo(
        oauth2_auth_url=body.get("oauth2_auth_url"),
        oauth2_token_url=body.get("oauth2_token_url"),
        oauth2_dynamic_client_reg_url=body.get("oauth2_dynamic_client_reg_url"),
        http_basic_supported=bool(body.get("http_basic_supported", False)),
        supported_oauth2_flows=tuple(body.get("supported_oauth2_flows") or ()),
        extras={key: value for key, value in body.items() if key not in known},
    )


def discover(base_url: str, *, transport: httpx.BaseTransport | None = None, timeout: float = 30.0) -> list[ApiVersion]:
    """The APIs a server offers, no authentication needed: ``GET /foundation/versions``, and on a server without the
    Foundation API what BCF API 2.1 has in its place, ``GET /bcf/versions``, whose items do not name the API."""
    with httpx.Client(base_url=base_url.rstrip("/"), transport=transport, timeout=timeout) as client:
        response = client.get("/foundation/versions")
        if response.status_code == 404:
            response = client.get("/bcf/versions")
        if response.is_error:
            raise ApiError(response)
        return [
            ApiVersion(item.get("api_id", "bcf"), item["version_id"], item.get("detailed_version"))
            for item in response.json().get("versions", [])
        ]


def auth_info(
    base_url: str,
    *,
    transport: httpx.BaseTransport | None = None,
    timeout: float = 30.0,
    path: str = "/foundation/1.0/auth",
) -> AuthInfo:
    """Where to sign in, no authentication needed. BCF API 2.1 has it under ``/bcf/2.1/auth``."""
    with httpx.Client(base_url=base_url.rstrip("/"), transport=transport, timeout=timeout) as client:
        response = client.get(path)
        if response.is_error:
            raise ApiError(response)
        return _auth_info(response.json())


class FoundationClient:
    def __init__(self, session: ApiSession) -> None:
        self.session = session

    def versions(self) -> list[ApiVersion]:
        body = self.session.json("GET", "/foundation/versions", include_authorization=False)
        return [
            ApiVersion(item["api_id"], item["version_id"], item.get("detailed_version")) for item in body["versions"]
        ]

    def auth(self) -> AuthInfo:
        return _auth_info(self.session.json("GET", "/foundation/1.0/auth", include_authorization=False))

    def current_user(self) -> dict[str, Any]:
        """``{"id": ..., "name": ...}`` of the signed-in user."""
        return self.session.json("GET", "/foundation/1.0/current-user")
