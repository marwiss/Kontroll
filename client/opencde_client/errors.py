# This file was generated with the assistance of an AI coding tool.
"""Exceptions raised by the client."""

from __future__ import annotations

import httpx


class OpenCdeError(Exception):
    """Base class of everything this library raises on purpose."""


class AuthError(OpenCdeError):
    """The OAuth2 flow failed (refused, mismatched state, no code)."""


class NotInThisVersion(OpenCdeError):
    """The version of the API this client speaks has no such service, or the server none of the versions it speaks."""


class ApiError(OpenCdeError):
    """The server answered with an error status; ``message`` is the OpenCDE error body's text."""

    def __init__(self, response: httpx.Response) -> None:
        self.status_code = response.status_code
        self.response = response
        self.message = _message_of(response)
        super().__init__(f"{response.request.method} {response.request.url} -> {self.status_code}: {self.message}")


def _message_of(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text[:200] or response.reason_phrase
    if isinstance(body, dict):
        return str(body.get("message") or body.get("error_description") or body.get("error") or body)
    return str(body)[:200]
