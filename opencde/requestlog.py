# This file was generated with the assistance of an AI coding tool.
"""Request log: one ``RequestLog`` node per HTTP request, for debugging clients and learning the APIs.

An extension outside the OpenCDE specifications, off by default
(``OPENCDE_REQUEST_LOG_ENABLED``). Each entry holds when, method, path (never
the query string, which may carry filters with personal data), the operation
as the OpenAPI summary names it, status, duration, the ``X-Request-ID`` the
client sent or the server minted, bytes in and out, and who called (user and
client from the bearer principal, or the browser user of a page) from which
address. Never bodies, headers or tokens. Entries expire after
``OPENCDE_REQUEST_LOG_RETENTION_HOURS`` and are swept by the cleaner; the
administration shows them at ``/admin/requests`` and serves them as JSON at
``/admin/api/requests`` for administrators holding the ``admin`` scope.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from opencde.graph.graph import Graph
from opencde.ids import new_id
from opencde.logging import get_logger
from opencde.timeutil import later_iso, now_iso

log = get_logger(__name__)

SKIPPED_PREFIXES = ("/static/", "/healthz", "/readyz")
MAX_LIMIT = 1000
DEFAULT_LIMIT = 200

CREATE = """
CREATE (:RequestLog {
    id: $id, at: $at, method: $method, path: $path, operation: $operation, status: $status,
    duration_ms: $duration_ms, request_id: $request_id, bytes_in: $bytes_in, bytes_out: $bytes_out,
    username: $username, client_id: $client_id, ip: $ip, expires_at: $expires_at
})
"""


class RequestLogWriter:
    """Stores entries in the background so a response never waits for the log."""

    def __init__(self, graph: Graph, retention_hours: int) -> None:
        self.graph = graph
        self.retention_seconds = retention_hours * 3600
        self._tasks: set[asyncio.Task[None]] = set()

    def record(self, entry: dict[str, Any]) -> None:
        entry["id"] = new_id()
        entry["expires_at"] = later_iso(self.retention_seconds)
        task = asyncio.create_task(self._write(entry), name="request-log")
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _write(self, entry: dict[str, Any]) -> None:
        try:
            await self.graph.run(CREATE, **entry)
        except Exception as exc:  # the log is a convenience; the request itself has already been answered
            log.warning("request_log_write_failed", error=f"{type(exc).__name__}: {exc}"[:200])

    async def wait_idle(self) -> None:
        """For tests: wait until every pending entry is stored."""
        while self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

    async def close(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        for task in list(self._tasks):
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task


def _operation(scope: Scope) -> str | None:
    """The matched route's OpenAPI summary (the specification's operation name), else its name."""
    route = scope.get("route")
    if route is None:
        endpoint = scope.get("endpoint")
        app = scope.get("app")
        if endpoint is not None and app is not None:
            route = next((r for r in app.routes if getattr(r, "endpoint", None) is endpoint), None)
    if route is None:
        return None
    return getattr(route, "summary", None) or getattr(route, "name", None)


def _caller(scope: Scope) -> tuple[str | None, str | None]:
    """(username, client_id) of a bearer principal, or the browser user of a page."""
    state = scope.get("state") or {}
    principal = state.get("principal")
    if principal is not None:
        return getattr(principal, "username", None), getattr(principal, "client_id", None)
    web_user = state.get("web_user")
    if web_user is not None:
        return getattr(getattr(web_user, "user", None), "username", None), None
    # The token and revocation endpoints authenticate the client by form, not bearer; they leave its id here.
    return None, state.get("log_client_id")


def _client_address(scope: Scope) -> str | None:
    client = scope.get("client")
    return client[0] if client else None


class RequestLogMiddleware:
    """Measure every request and hand the entry to the writer kept in ``app.state.requestlog``."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"].startswith(SKIPPED_PREFIXES):
            await self.app(scope, receive, send)
            return
        writer: RequestLogWriter | None = getattr(scope["app"].state, "requestlog", None)
        if writer is None:
            await self.app(scope, receive, send)
            return

        started = time.perf_counter()
        counters = {"status": 0, "in": 0, "out": 0}

        async def counting_receive() -> Message:
            message = await receive()
            if message["type"] == "http.request":
                counters["in"] += len(message.get("body", b""))
            return message

        async def counting_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                counters["status"] = int(message["status"])
            elif message["type"] == "http.response.body":
                counters["out"] += len(message.get("body", b""))
            await send(message)

        try:
            await self.app(scope, counting_receive, counting_send)
        finally:
            username, client_id = _caller(scope)
            request_id = (scope.get("state") or {}).get("request_id")
            writer.record(
                {
                    "at": now_iso(),
                    "method": scope["method"],
                    "path": scope["path"],
                    "operation": _operation(scope),
                    "status": counters["status"] or 500,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                    "request_id": request_id,
                    "bytes_in": counters["in"],
                    "bytes_out": counters["out"],
                    "username": username,
                    "client_id": client_id,
                    "ip": _client_address(scope),
                }
            )


async def query(
    graph: Graph,
    *,
    client_id: str | None = None,
    username: str | None = None,
    path_prefix: str | None = None,
    status: int | None = None,
    since: str | None = None,
    request_id: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> list[dict[str, Any]]:
    """The newest matching entries, newest first; every filter is optional."""
    rows = await graph.run(
        """
        MATCH (r:RequestLog)
        WHERE ($client_id IS NULL OR r.client_id = $client_id)
          AND ($username IS NULL OR r.username = $username)
          AND ($path IS NULL OR r.path STARTS WITH $path)
          AND ($status IS NULL OR r.status = $status)
          AND ($since IS NULL OR r.at >= $since)
          AND ($request_id IS NULL OR r.request_id = $request_id)
        RETURN properties(r) AS entry
        ORDER BY r.at DESC
        LIMIT $limit
        """,
        client_id=client_id or None,
        username=username or None,
        path=path_prefix or None,
        status=status,
        since=since or None,
        request_id=request_id or None,
        limit=max(1, min(int(limit), MAX_LIMIT)),
    )
    return [dict(row["entry"]) for row in rows]
