# This file was generated with the assistance of an AI coding tool.
"""Sign in for MCP's conformance suite and stand between it and the endpoint, adding the token (the nightly job).

The official suite (``@modelcontextprotocol/conformance``) sends no token, and the endpoint takes none but one bound
to it (ADR 0028). So this signs a demo user in through the server's own OAuth2 flow, with ``resource=<server>/mcp``
and the scope ``mcp``, and then serves on ``127.0.0.1:<port>`` what the server answers, adding
``Authorization: Bearer <token>`` to every request that carries none. The token is never printed. For a throwaway
server with the demo data only:

    uv run python -m tests.conformance.mcp_proxy <server> <public client id> <demo password> <port>
"""

from __future__ import annotations

import sys

import httpx
import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

from tests.integration.helpers import authorize, exchange

REDIRECT = "http://127.0.0.1/callback"
USER = "officer"  # a manager of the demo projects
HOP_BY_HOP = {"host", "content-length", "connection", "keep-alive", "transfer-encoding", "content-encoding"}


def sign_in(server: str, client_id: str, password: str) -> str:
    resource = f"{server}/mcp"
    with httpx.Client(base_url=server, timeout=30.0) as browser:
        code, query, verifier = authorize(
            browser,  # type: ignore[arg-type]  (the helpers take any client with the test client's methods)
            client_id=client_id,
            redirect_uri=REDIRECT,
            username=USER,
            password=password,
            scope="mcp",
            resource=resource,
        )
        if not code:
            raise SystemExit(f"the sign-in was refused: {query.get('error')}")
        session = exchange(
            browser,  # type: ignore[arg-type]
            code=code,
            verifier=verifier,
            client_id=client_id,
            redirect_uri=REDIRECT,
            resource=resource,
        )
    return session.access_token


def proxy(server: str, token: str) -> Starlette:
    upstream = httpx.AsyncClient(base_url=server, timeout=60.0)

    async def forward(request: Request) -> Response:
        headers = {name: value for name, value in request.headers.items() if name not in HOP_BY_HOP}
        headers.setdefault("authorization", f"Bearer {token}")
        answer = await upstream.request(
            request.method, request.url.path, params=request.query_params, headers=headers, content=await request.body()
        )
        kept = {name: value for name, value in answer.headers.items() if name.lower() not in HOP_BY_HOP}
        return Response(answer.content, status_code=answer.status_code, headers=kept)

    methods = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
    return Starlette(routes=[Route("/{path:path}", forward, methods=methods)])


def main(server: str, client_id: str, password: str, port: str) -> None:
    server = server.rstrip("/")
    uvicorn.run(
        proxy(server, sign_in(server, client_id, password)), host="127.0.0.1", port=int(port), log_level="warning"
    )


if __name__ == "__main__":
    main(*sys.argv[1:5])
