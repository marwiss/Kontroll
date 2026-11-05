# This file was generated with the assistance of an AI coding tool.
"""ASGI middleware shared by every route.

Written as plain ASGI callables rather than Starlette's ``BaseHTTPMiddleware``
so that streaming responses (document downloads) are not buffered.
"""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Iterable

import structlog
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_HEADER = b"x-request-id"
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")

# Defaults for API responses. HTML pages set their own Content-Security-Policy
# and static files their own Cache-Control; the middleware only fills gaps.
SECURITY_HEADERS: dict[bytes, bytes] = {
    b"content-security-policy": b"default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
    b"x-content-type-options": b"nosniff",
    b"x-frame-options": b"DENY",
    b"referrer-policy": b"no-referrer",
    b"permissions-policy": b"camera=(), microphone=(), geolocation=(), payment=()",
    b"cross-origin-opener-policy": b"same-origin",
    b"cross-origin-resource-policy": b"same-origin",
    b"cache-control": b"no-store",
}


def _header_names(headers: Iterable[tuple[bytes, bytes]]) -> set[bytes]:
    return {name.lower() for name, _ in headers}


class SecurityHeadersMiddleware:
    """Add the security headers above to every HTTP response that lacks them."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers: list[tuple[bytes, bytes]] = list(message.get("headers", []))
                present = _header_names(headers)
                headers.extend((name, value) for name, value in SECURITY_HEADERS.items() if name not in present)
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_headers)


class RequestIDMiddleware:
    """Accept a well-formed X-Request-ID or mint one; echo it and bind it to the logs."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = dict(scope.get("headers", [])).get(REQUEST_ID_HEADER, b"").decode("latin-1")
        request_id = incoming if _REQUEST_ID_RE.match(incoming) else uuid.uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        async def send_with_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((REQUEST_ID_HEADER, request_id.encode("ascii")))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            structlog.contextvars.clear_contextvars()


class BodySizeLimitMiddleware:
    """Reject request bodies whose declared size exceeds the limit with 413.

    Routes that accept large binary uploads stream and count bytes themselves
    and are listed in ``exempt_prefixes``; everything else is JSON or a small
    form and fits comfortably under the default limit.
    """

    def __init__(self, app: ASGIApp, max_bytes: int, exempt_prefixes: Iterable[str] = ()) -> None:
        self.app = app
        self.max_bytes = max_bytes
        self.exempt_prefixes = tuple(exempt_prefixes)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"].startswith(self.exempt_prefixes):
            await self.app(scope, receive, send)
            return

        declared = dict(scope.get("headers", [])).get(b"content-length")
        if declared is not None:
            try:
                size = int(declared)
            except ValueError:
                size = self.max_bytes + 1
            if size > self.max_bytes:
                await _send_json(send, 413, {"message": f"Request body exceeds {self.max_bytes} bytes"})
                return

        await self.app(scope, receive, send)


async def _send_json(send: Send, status: int, body: dict[str, str]) -> None:
    payload = json.dumps(body).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(payload)).encode("ascii")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": payload})
