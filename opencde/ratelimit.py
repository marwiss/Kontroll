# This file was generated with the assistance of an AI coding tool.
"""Rate limiting.

Limits are per client address (the address uvicorn derived from trusted
``X-Forwarded-For`` headers, or the socket peer). Sign-in and token endpoints
get tight limits against credential guessing, through decorators. Every request
also falls under :class:`PathRateLimitMiddleware`: a generous limit against
accidental floods, and a tighter one on the administration.
``OPENCDE_RATE_LIMITS_ENABLED=false`` turns the whole thing off for load tests.

The counts live in the server process unless ``OPENCDE_RATE_LIMIT_STORAGE``
points at a shared store, which several server processes need so that the
limit is not multiplied by their number.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from limits import RateLimitItem, parse
from limits.errors import ConfigurationError
from limits.storage import storage_from_string
from limits.strategies import FixedWindowRateLimiter
from limits.util import WindowStats
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.types import ASGIApp, Receive, Scope, Send

from opencde.errors import error_body
from opencde.logging import get_logger

log = get_logger(__name__)

# Requests per client address. Names describe the endpoint group they protect.
RATE_EXCHANGE = "60/minute"  # the OAuth2 code and refresh exchanges
RATE_UPLOAD = "120/minute"
RATE_ADMIN = "240/minute"
RATE_REGISTRATION = "5/hour"
RATE_REGISTRATION_DEVELOPMENT = "60/hour"  # someone trying a server out registers again and again
RATE_MCP_TOOL_CALLS = "120/minute"  # per token, on the MCP endpoint (ADR 0028): an AI's loop, not a person

STORE_TIMEOUT_SECONDS = 1.0  # a shared store that stops answering must not hold up the server

limiter = Limiter(key_func=get_remote_address, headers_enabled=True)

# The decorators hold the one limiter and read these two per request; they vary per application.
_registration_limit = RATE_REGISTRATION
_sign_in_limit = "10/minute"


def registration_limit() -> str:
    return _registration_limit


def sign_in_limit() -> str:
    return _sign_in_limit


class _FailOpen(FixedWindowRateLimiter):
    """A store that fails lets requests through: trouble in a limiter must not take the server down."""

    def hit(self, item: RateLimitItem, *identifiers: str, cost: int = 1) -> bool:
        try:
            return super().hit(item, *identifiers, cost=cost)
        except Exception as exc:
            log.warning("rate_limit_storage_failed", error=type(exc).__name__)
            return True

    def get_window_stats(self, item: RateLimitItem, *identifiers: str) -> WindowStats:
        try:
            return super().get_window_stats(item, *identifiers)
        except Exception:
            return WindowStats(datetime.now(UTC).timestamp() + item.get_expiry(), item.amount)


def wait_seconds(rule: str, *identifiers: str) -> int | None:
    """Count one request against ``rule`` for ``identifiers``, outside the decorators: None while it is within the
    limit (or the limits are off), else the seconds until the window frees."""
    if not limiter.enabled:
        return None
    item = parse(rule)
    if limiter.limiter.hit(item, *identifiers):
        return None
    reset, _remaining = limiter.limiter.get_window_stats(item, *identifiers)
    return max(1, math.ceil(reset - datetime.now(UTC).timestamp()))


class PathRateLimitMiddleware:
    """The limit on every request, tighter on the administration; answers before the request reaches a route."""

    EXEMPT = ("/healthz", "/readyz", "/static/")  # the orchestrator's checks, and files browsers cache anyway

    def __init__(self, app: ASGIApp, api_limit: str) -> None:
        self.app = app
        self.rules = (("/admin", parse(RATE_ADMIN)), ("", parse(api_limit)))

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        exceeded = self._exceeded(scope) if scope["type"] == "http" and limiter.enabled else None
        if exceeded is None:
            await self.app(scope, receive, send)
            return
        headers = {"Retry-After": str(exceeded.get_expiry())}
        answer = JSONResponse(error_body(429, "Too many requests"), status_code=429, headers=headers)
        await answer(scope, receive, send)

    def _exceeded(self, scope: Scope) -> RateLimitItem | None:
        path = scope["path"]
        if path.startswith(self.EXEMPT):
            return None
        prefix, rule = next(candidate for candidate in self.rules if path.startswith(candidate[0]))
        client = scope.get("client")
        allowed = limiter.limiter.hit(rule, "path", prefix, client[0] if client else "unknown")
        return None if allowed else rule


def install_rate_limiting(app: FastAPI, enabled: bool, *, production: bool, storage_uri: str, sign_in: str) -> None:
    global _registration_limit, _sign_in_limit
    _registration_limit = RATE_REGISTRATION if production else RATE_REGISTRATION_DEVELOPMENT
    _sign_in_limit = sign_in
    limiter.enabled = enabled
    try:
        limiter._storage = storage_from_string(
            storage_uri, socket_connect_timeout=STORE_TIMEOUT_SECONDS, socket_timeout=STORE_TIMEOUT_SECONDS
        )
    except ConfigurationError:  # its message would carry the address, which can hold a password
        raise RuntimeError("OPENCDE_RATE_LIMIT_STORAGE: a redis address needs the redis extra") from None
    limiter._limiter = _FailOpen(limiter._storage)
    app.state.limiter = limiter

    @app.exception_handler(RateLimitExceeded)
    async def _too_many(_request: Request, exc: RateLimitExceeded) -> Response:
        response = JSONResponse(error_body(429, "Too many requests"), status_code=429)
        return limiter._inject_headers(response, _request.state.view_rate_limit)
