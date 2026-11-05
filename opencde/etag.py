# This file was generated with the assistance of an AI coding tool.
"""ETag support (Foundation API 1.2).

Every JSON ``GET`` response gets an ``ETag`` derived from its body. A client
that sends the same value in ``If-None-Match`` receives ``304 Not Modified``
without a body. Implemented as ASGI middleware so no route has to think about
it; binary downloads (not JSON) pass through untouched.
"""

from __future__ import annotations

import hashlib

from starlette.types import ASGIApp, Message, Receive, Scope, Send

MAX_BUFFERED = 8 * 1024 * 1024  # larger JSON bodies are streamed without an ETag


def etag_for(body: bytes) -> str:
    return '"' + hashlib.sha256(body).hexdigest()[:32] + '"'


def matches(if_none_match: str | None, etag: str) -> bool:
    if not if_none_match:
        return False
    candidates = [value.strip() for value in if_none_match.split(",")]
    return (
        "*" in candidates
        or etag in candidates
        or etag.replace('"', "") in [c.replace('"', "").removeprefix("W/") for c in candidates]
    )


class ETagMiddleware:
    def __init__(self, app: ASGIApp, prefixes: tuple[str, ...] = ("/foundation/", "/bcf/", "/documents/")) -> None:
        self.app = app
        self.prefixes = prefixes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] != "GET" or not scope["path"].startswith(self.prefixes):
            await self.app(scope, receive, send)
            return

        request_headers = dict(scope.get("headers", []))
        if_none_match = request_headers.get(b"if-none-match", b"").decode("latin-1") or None

        start: Message | None = None
        chunks: list[bytes] = []
        buffering = False
        passthrough = False

        async def flush_buffered() -> None:
            nonlocal start
            if start is None:
                return
            body = b"".join(chunks)
            etag = etag_for(body)
            headers = [(k, v) for k, v in start.get("headers", []) if k.lower() != b"etag"]
            headers.append((b"etag", etag.encode("ascii")))
            if matches(if_none_match, etag):
                headers = [(k, v) for k, v in headers if k.lower() not in (b"content-length", b"content-type")]
                await send({"type": "http.response.start", "status": 304, "headers": headers})
                await send({"type": "http.response.body", "body": b""})
                return
            await send({"type": "http.response.start", "status": start["status"], "headers": headers})
            await send({"type": "http.response.body", "body": body})

        async def send_wrapper(message: Message) -> None:
            nonlocal start, buffering, passthrough
            if message["type"] == "http.response.start":
                headers = dict(message.get("headers", []))
                content_type = headers.get(b"content-type", b"").decode("latin-1")
                declared = int(headers.get(b"content-length", b"0") or 0)
                if (
                    message["status"] == 200
                    and content_type.startswith("application/json")
                    and declared <= MAX_BUFFERED
                ):
                    start = message
                    buffering = True
                    return
                passthrough = True
                await send(message)
                return
            if message["type"] == "http.response.body" and buffering and not passthrough:
                chunks.append(message.get("body", b""))
                if not message.get("more_body", False):
                    await flush_buffered()
                return
            await send(message)

        await self.app(scope, receive, send_wrapper)
