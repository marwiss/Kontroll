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


@router.get("/readyz", summary="Readiness: the graph databases answer", include_in_schema=False)
async def readyz(request: Request) -> JSONResponse:
    settings = request.app.state.settings
    graph = request.app.state.graph
    reachable = await ping_within(graph.driver, graph.database, settings.graph_connect_timeout_seconds)
    store = getattr(request.app.state, "store", graph)
    store_state = "shared"  # the server's own data in the IFC graph's connection, unless it has its own (ADR 0027)
    if store is not graph:
        answers = await ping_within(store.driver, store.database, settings.graph_connect_timeout_seconds)
        store_state = "ok" if answers else "unavailable"
    workcopy = getattr(request.app.state, "workcopy", None)
    copy_state = "none"
    if workcopy is not None:  # the working copy's state is reported, never a reason not to be ready (ADR 0024)
        copy_state = (
            "ok"
            if await ping_within(workcopy.driver, workcopy.database, settings.graph_connect_timeout_seconds)
            else "unavailable"
        )
    if reachable and store_state != "unavailable":
        return JSONResponse(
            {
                "status": "ready",
                "graph": "ok",
                "store": store_state,
                "dialect": graph.dialect.name.value,
                "workcopy": copy_state,
            }
        )
    return JSONResponse(
        {"status": "not_ready", "graph": "ok" if reachable else "unavailable", "store": store_state}, status_code=503
    )
