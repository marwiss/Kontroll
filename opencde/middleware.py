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
from typing import Any

import structlog
from starlette.exceptions import HTTPException
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from opencde.errors import error_body

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

# The interactive API documentation is FastAPI's Swagger UI page: it loads its
# script and style sheet from jsdelivr and starts with an inline script, which
# our own pages never do. It gets this policy instead, and is served only
# outside production unless the operator asks for it (settings.api_docs_enabled).
DOCS_PATHS = ("/docs", "/docs/oauth2-redirect")

# A client opens the server's pages in a popup (the OAuth2 authorization page, the Documents API
# selection and upload pages, the sign-in they may need) and its callback page reports back to the
# window that opened it; a Cross-Origin-Opener-Policy of "same-origin" on those pages would cut
# that opener and strand the user on the callback page. They keep the browser's default, and only
# the administration and account pages, which no other site opens, isolate themselves. An account
# page on its way somewhere (a new password in the middle of a sign-in) is a step in that popup too.
ISOLATED_PREFIXES = ("/admin", "/account")
COOP_DEFAULT = b"unsafe-none"
DOCS_CSP = (
    b"default-src 'none'; script-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
    b"style-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
    b"img-src 'self' data: https://cdn.jsdelivr.net https://fastapi.tiangolo.com; font-src 'self' https://cdn.jsdelivr.net; "
    b"connect-src 'self'; form-action 'none'; frame-ancestors 'none'; base-uri 'none'"
)


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

        is_static = scope["path"].startswith("/static/")

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers: list[tuple[bytes, bytes]] = list(message.get("headers", []))
                present = _header_names(headers)
                defaults = dict(SECURITY_HEADERS)
                if is_static:  # versioned by release; safe to cache, and public anyway
                    defaults[b"cache-control"] = b"public, max-age=86400"
                if scope["path"] in DOCS_PATHS:
                    defaults[b"content-security-policy"] = DOCS_CSP
                going_on = scope["path"] == "/account" and b"next=" in scope.get("query_string", b"")
                if going_on or not scope["path"].startswith(ISOLATED_PREFIXES):
                    defaults[b"cross-origin-opener-policy"] = COOP_DEFAULT
                headers.extend((name, value) for name, value in defaults.items() if name not in present)
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_headers)


class ApiCORSMiddleware:
    """CORS for the API paths only (Foundation API 1.4). The server's pages are never shared cross-origin.

    ``include_prefixes`` selects the API; ``exclude_patterns`` carves the HTML pages that live under the same
    prefixes (the Documents API's upload and selection pages) back out. Everything else passes through untouched.
    """

    def __init__(
        self, app: ASGIApp, *, include_prefixes: Iterable[str], exclude_patterns: Iterable[str], **cors_options: Any
    ) -> None:
        self.app = app
        self.cors = CORSMiddleware(app, **cors_options)
        self.include = tuple(include_prefixes)
        self.exclude = tuple(re.compile(pattern) for pattern in exclude_patterns)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            path = scope["path"]
            if path.startswith(self.include) and not any(pattern.match(path) for pattern in self.exclude):
                await self.cors(scope, receive, send)
                return
        await self.app(scope, receive, send)


class UnhandledErrorMiddleware:
    """Turn an unhandled exception into the spec error body (Foundation API 1.6) *inside* the other layers.

    Starlette answers unhandled exceptions in its outermost layer, beyond CORS and the security headers, so a
    browser client would see a network error instead of a 500. Here the response is built where those layers
    still apply. The error is logged with the request id bound by RequestIDMiddleware; nothing else leaves.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = False

        async def send_tracking(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, send_tracking)
        except Exception as exc:
            if started:  # the response is under way; nothing can be sent any more
                raise
            structlog.get_logger("opencde.errors").exception(
                "unhandled_error", path=scope["path"], error_type=type(exc).__name__
            )
            response = JSONResponse(error_body(500, "Internal server error"), status_code=500)
            await response(scope, receive, send)


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
    """Reject request bodies larger than the limit with 413.

    A declared ``Content-Length`` above the limit is refused before the route
    runs; a body that arrives in chunks is counted as it is read, so a client
    cannot bypass the limit by omitting the header. Routes that accept large
    binary uploads stream and count bytes themselves and are exempt by prefix
    or by regular expression; everything else is JSON or a small form.
    """

    def __init__(
        self,
        app: ASGIApp,
        max_bytes: int,
        exempt_prefixes: Iterable[str] = (),
        exempt_patterns: Iterable[str] = (),
    ) -> None:
        self.app = app
        self.max_bytes = max_bytes
        self.exempt_prefixes = tuple(exempt_prefixes)
        self.exempt_patterns = tuple(re.compile(pattern) for pattern in exempt_patterns)

    def is_exempt(self, path: str) -> bool:
        return path.startswith(self.exempt_prefixes) or any(pattern.match(path) for pattern in self.exempt_patterns)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or self.is_exempt(scope["path"]):
            await self.app(scope, receive, send)
            return

        message = f"Request body exceeds {self.max_bytes} bytes"
        declared = dict(scope.get("headers", [])).get(b"content-length")
        if declared is not None:
            try:
                size = int(declared)
            except ValueError:
                size = self.max_bytes + 1
            if size > self.max_bytes:
                await _send_json(send, 413, error_body(413, message))
                return

        received = 0

        async def counting_receive() -> Message:
            nonlocal received
            event = await receive()
            if event["type"] == "http.request":
                received += len(event.get("body", b""))
                if received > self.max_bytes:
                    # Raised inside the route's body read; the exception handlers turn it into a 413.
                    raise HTTPException(413, message)
            return event

        await self.app(scope, counting_receive, send)


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
