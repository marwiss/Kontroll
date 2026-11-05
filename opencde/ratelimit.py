# This file was generated with the assistance of an AI coding tool.
"""Rate limiting.

Limits are per client address (the address uvicorn derived from trusted
``X-Forwarded-For`` headers, or the socket peer). Sign-in and token endpoints
get tight limits against credential guessing; the API gets a generous one
against accidental floods. ``OPENCDE_RATE_LIMITS_ENABLED=false`` turns the
whole thing off for load tests.
"""

from __future__ import annotations

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

# Requests per client address. Names describe the endpoint group they protect.
RATE_SIGN_IN = "10/minute"
RATE_EXCHANGE = "60/minute"  # the OAuth2 code and refresh exchanges
RATE_REGISTRATION = "5/hour"
API = "600/minute"
RATE_UPLOAD = "120/minute"

limiter = Limiter(key_func=get_remote_address, headers_enabled=True, default_limits=[API])


def install_rate_limiting(app: FastAPI, enabled: bool) -> None:
    limiter.enabled = enabled
    app.state.limiter = limiter

    @app.exception_handler(RateLimitExceeded)
    async def _too_many(_request: Request, exc: RateLimitExceeded) -> Response:
        response = JSONResponse({"message": "Too many requests"}, status_code=429)
        return limiter._inject_headers(response, _request.state.view_rate_limit)
