# This file was generated with the assistance of an AI coding tool.
"""Error responses in the OpenCDE format.

Foundation API 1.6 prescribes one error body for all OpenCDE APIs
(``spec/foundation-api/schemas/error.json``): ``{"message": "..."}``. Nothing
else is ever returned on failure: no stack traces, no echoed input, no
internal identifiers. Unexpected exceptions are logged with the request id
so an operator can find them.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette import status
from starlette.exceptions import HTTPException as StarletteHTTPException

from opencde.logging import get_logger

log = get_logger(__name__)


def error_response(status_code: int, message: str, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse({"message": message}, status_code=status_code, headers=headers)


def _summarize_validation(exc: RequestValidationError) -> str:
    """Name the offending fields without reflecting the submitted values."""
    parts = []
    for error in exc.errors()[:5]:
        location = ".".join(str(piece) for piece in error.get("loc", ()) if piece not in ("body", "query", "path"))
        parts.append(f"{location or 'request'}: {error.get('msg', 'invalid')}")
    return "Invalid request. " + "; ".join(parts)


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def _http_exception(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, str) else "Request failed"
        headers = dict(exc.headers) if isinstance(exc, HTTPException) and exc.headers else None
        return error_response(exc.status_code, detail, headers)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
        return error_response(status.HTTP_400_BAD_REQUEST, _summarize_validation(exc))

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled_error", path=request.url.path, error_type=type(exc).__name__)
        return error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "Internal server error")
