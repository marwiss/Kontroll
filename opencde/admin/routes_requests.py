# This file was generated with the assistance of an AI coding tool.
"""The request log: a page for administrators and a JSON endpoint for administration clients.

Both are extensions outside the OpenCDE specifications. The page uses the
browser session like the rest of the administration; the JSON endpoint uses a
bearer token with the ``admin`` scope held by an administrator, so a client on
another origin can show the server side of its own calls (CORS applies to
``/admin/api/``).
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, Response

from opencde import requestlog
from opencde.admin.access import AdminDep, admin_context
from opencde.auth.dependencies import AdminPrincipal
from opencde.deps import GraphDep, SettingsDep
from opencde.ui.templating import render

router = APIRouter(prefix="/admin", include_in_schema=False)
api_router = APIRouter(prefix="/admin/api", tags=["Administration (extension)"])

ClientFilter = Annotated[str | None, Query(max_length=64, description="Exact client_id")]
UserFilter = Annotated[str | None, Query(max_length=128, description="Exact user name")]
PathFilter = Annotated[str | None, Query(max_length=256, description="Path prefix, e.g. /bcf/3.0")]
StatusFilter = Annotated[int | None, Query(ge=100, le=599)]
SinceFilter = Annotated[str | None, Query(max_length=40, description="ISO 8601 UTC; entries at or after it")]
RequestIdFilter = Annotated[str | None, Query(max_length=128)]
LimitQuery = Annotated[int, Query(ge=1, le=requestlog.MAX_LIMIT)]

FIELDS = (
    "at",
    "method",
    "path",
    "operation",
    "status",
    "duration_ms",
    "request_id",
    "bytes_in",
    "bytes_out",
    "username",
    "client_id",
    "ip",
)


def _rows(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{field: entry.get(field) for field in FIELDS} for entry in entries]


async def _entries(
    graph: GraphDep,
    *,
    client_id: str | None,
    user: str | None,
    path: str | None,
    status: int | None,
    since: str | None,
    request_id: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    return _rows(
        await requestlog.query(
            graph,
            client_id=(client_id or "").strip(),
            username=(user or "").strip(),
            path_prefix=(path or "").strip(),
            status=status,
            since=(since or "").strip(),
            request_id=(request_id or "").strip(),
            limit=limit,
        )
    )


@router.get("/requests")
async def requests_page(
    request: Request,
    admin: AdminDep,
    graph: GraphDep,
    settings: SettingsDep,
    client_id: ClientFilter = None,
    user: UserFilter = None,
    path: PathFilter = None,
    status: StatusFilter = None,
    since: SinceFilter = None,
    request_id: RequestIdFilter = None,
) -> Response:
    rows = await _entries(
        graph,
        client_id=client_id,
        user=user,
        path=path,
        status=status,
        since=since,
        request_id=request_id,
        limit=requestlog.DEFAULT_LIMIT,
    )
    return render(
        request,
        "admin/requests.html",
        admin_context(
            request,
            admin,
            "requests",
            rows=rows,
            enabled=settings.request_log_enabled,
            retention_hours=settings.request_log_retention_hours,
            limit=requestlog.DEFAULT_LIMIT,
            filters={
                "client_id": client_id or "",
                "user": user or "",
                "path": path or "",
                "status": status if status is not None else "",
                "since": since or "",
                "request_id": request_id or "",
            },
        ),
    )


@api_router.get("/requests", summary="Request log (extension): the server side of a client's calls")
async def requests_api(
    principal: AdminPrincipal,
    graph: GraphDep,
    settings: SettingsDep,
    client_id: ClientFilter = None,
    user: UserFilter = None,
    path: PathFilter = None,
    status: StatusFilter = None,
    since: SinceFilter = None,
    request_id: RequestIdFilter = None,
    limit: LimitQuery = requestlog.DEFAULT_LIMIT,
) -> Response:
    """Newest entries first. Needs the ``admin`` scope and an administrator account. Entries carry
    method, path, operation, status, timing, request id, byte counts and the caller; never bodies or tokens."""
    rows = await _entries(
        graph,
        client_id=client_id,
        user=user,
        path=path,
        status=status,
        since=since,
        request_id=request_id,
        limit=limit,
    )
    return JSONResponse(
        {
            "enabled": settings.request_log_enabled,
            "retention_hours": settings.request_log_retention_hours,
            "requests": rows,
        },
        headers={"Cache-Control": "no-store"},
    )
