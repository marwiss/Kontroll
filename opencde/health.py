# This file was generated with the assistance of an AI coding tool.
"""Liveness and readiness endpoints for containers, load balancers and ``opencde doctor``."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from opencde import __version__
from opencde.graph.driver import ping_within

router = APIRouter(tags=["operations"])


@router.get("/healthz", summary="Liveness: the process is up", include_in_schema=False)
async def healthz() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@router.get("/readyz", summary="Readiness: the graph database answers", include_in_schema=False)
async def readyz(request: Request) -> JSONResponse:
    settings = request.app.state.settings
    reachable = await ping_within(
        request.app.state.driver, settings.database_name, settings.graph_connect_timeout_seconds
    )
    if reachable:
        return JSONResponse({"status": "ready", "graph": "ok"})
    return JSONResponse({"status": "not_ready", "graph": "unavailable"}, status_code=503)
