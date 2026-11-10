# This file was generated with the assistance of an AI coding tool.
"""Error responses in the OpenCDE format.

Foundation API 1.6 prescribes one error body for all OpenCDE APIs
(``spec/foundation-api/schemas/error.json``): ``{"message": "..."}``. Nothing
else is ever returned on failure: no stack traces, no echoed input, no
internal identifiers. Unexpected exceptions are logged with the request id
so an operator can find them.

As an extension outside the specifications, every error the server shapes
itself also carries a stable ``code`` (``{"message": "...", "code":
"not_found"}``) that a client can act on or translate, while ``message``
stays the English text for people. The list is closed and documented in
``docs/en/client-guide.md``; a client treats an unknown code like a missing one
and shows the message. The code follows from the status unless the raising
code names one (``ApiError``), as the few places where one status covers two
different client reactions do (no token versus a stale token, a request body
over the limit versus a chosen file over the limit).
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from neo4j.exceptions import ServiceUnavailable
from starlette import status
from starlette.exceptions import HTTPException as StarletteHTTPException

from opencde.logging import get_logger

log = get_logger(__name__)

# Codes a client may act on, by status. Statuses outside this table (405, 415 from the framework) carry no code.
CODE_VALIDATION = "validation_error"  # 400: body, query, OData or extension value not accepted
CODE_LOCALHOST_REDIRECT = "localhost_redirect"  # 400: a client asked to come back to http://localhost
CODE_UNAUTHENTICATED = "unauthenticated"  # 401: no bearer token at all
CODE_INVALID_TOKEN = "invalid_token"  # 401: a label for a stale token, not a secret  # noqa: S105  # nosec B105
CODE_INSUFFICIENT_SCOPE = "insufficient_scope"  # 403: token lacks the scope the route needs
CODE_FORBIDDEN = "forbidden"  # 403: the role does not allow the action
CODE_REAUTHENTICATION_REQUIRED = "reauthentication_required"  # 403: a fresh sign-in is needed (administration)
CODE_NOT_FOUND = "not_found"  # 404: absent, outside the user's projects, or a feature that is off
CODE_CONFLICT = "conflict"  # 409: a guid that already exists
CODE_VERSION_CONFLICT = "version_conflict"  # 412: the upload builds on a version that is no longer the latest
CODE_IFC_VALIDATION_FAILED = "ifc_validation_failed"  # 422: the project refuses a file with validation errors
CODE_PAYLOAD_TOO_LARGE = "payload_too_large"  # 413: the request body is over the server's limit
CODE_UPLOAD_TOO_LARGE = "upload_too_large"  # 413: a chosen file or part is over the upload limit
CODE_RATE_LIMITED = "rate_limited"  # 429
CODE_INTERNAL_ERROR = "internal_error"  # 500
CODE_UNAVAILABLE = "unavailable"  # 503: the graph database cannot be reached

CODES_BY_STATUS = {
    400: CODE_VALIDATION,
    401: CODE_INVALID_TOKEN,
    403: CODE_FORBIDDEN,
    404: CODE_NOT_FOUND,
    409: CODE_CONFLICT,
    412: CODE_VERSION_CONFLICT,
    413: CODE_PAYLOAD_TOO_LARGE,
    429: CODE_RATE_LIMITED,
    500: CODE_INTERNAL_ERROR,
    503: CODE_UNAVAILABLE,
}


class ApiError(HTTPException):
    """An error whose code differs from the one the status implies; ``details`` are fields the body carries besides."""

    def __init__(
        self,
        status_code: int,
        message: str,
        *,
        code: str,
        headers: dict[str, str] | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(status_code, message, headers)
        self.code = code
        self.details = details


class UserFacingError(ValueError):
    """A request that cannot be fulfilled, with a message that is safe to show.

    ``str(exc)`` is the English message, for the CLI and the API. ``key`` names the same text in
    the UI catalogues (``error.*``) and ``params`` fills its placeholders, so that a page shows it
    in the user's language (``opencde.ui.i18n.tr_error``). A parameter may itself carry ``key``
    and ``params`` (a password problem, for instance), or be a list of such values.
    """

    def __init__(self, message: str, *, key: str | None = None, **params: Any) -> None:
        super().__init__(message)
        self.key = key
        self.params = params


def error_body(
    status_code: int, message: str, code: str | None = None, details: dict[str, Any] | None = None
) -> dict[str, Any]:
    body: dict[str, Any] = {"message": message}
    code = code or CODES_BY_STATUS.get(status_code)
    if code:
        body["code"] = code
    if details:
        body.update(details)
    return body


def error_response(
    status_code: int,
    message: str,
    headers: dict[str, str] | None = None,
    code: str | None = None,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    return JSONResponse(error_body(status_code, message, code, details), status_code=status_code, headers=headers)


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
        headers = dict(exc.headers) if exc.headers else None  # the Allow of a 405 comes from Starlette itself
        return error_response(
            exc.status_code, detail, headers, code=getattr(exc, "code", None), details=getattr(exc, "details", None)
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
        return error_response(status.HTTP_400_BAD_REQUEST, _summarize_validation(exc))

    @app.exception_handler(ServiceUnavailable)
    async def _database_unavailable(request: Request, exc: ServiceUnavailable) -> JSONResponse:
        # The driver could not reach the database (down, restarting, network). Nothing about it is the client's
        # fault, and the message never repeats the driver's text, which names hosts and ports.
        log.error("database_unavailable", path=request.url.path, error_type=type(exc).__name__)
        return error_response(status.HTTP_503_SERVICE_UNAVAILABLE, "The database is not available right now")

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled_error", path=request.url.path, error_type=type(exc).__name__)
        return error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "Internal server error")
