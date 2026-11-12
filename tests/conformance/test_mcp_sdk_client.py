# This file was generated with the assistance of an AI coding tool.
"""The official MCP SDK's client drives the endpoint over the application, in both eras (ADR 0028, F32 c).

``mcp`` is a development dependency only: the server speaks the protocol with its own small part, and the SDK's
client, which checks every answer against its own models, shows when the two drift apart. ``auto`` discovers the
server at 2026-07-28; ``legacy`` takes the handshake of 2025-11-25, which the endpoint answers without a session.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from opencde.auth.dependencies import get_tokens
from opencde.deps import get_graph
from opencde.main import create_app
from opencde.mcp import routes
from tests.conftest import test_settings as make_settings
from tests.mcp_support import BEARER, BOUND, CLOUD, FakeGraph, OneToken

mcp = pytest.importorskip("mcp")
httpx2 = pytest.importorskip("httpx2")

pytestmark = pytest.mark.conformance


@pytest.mark.parametrize(("mode", "version"), [("auto", "2026-07-28"), ("legacy", "2025-11-25")])
async def test_the_sdks_client_discovers_lists_and_calls(tmp_path: Path, mode: str, version: str) -> None:
    from mcp.client.streamable_http import streamable_http_client

    app = create_app(make_settings(tmp_path, mcp_enabled=True), startup_wait_seconds=0)
    app.dependency_overrides[get_tokens] = lambda: OneToken(BOUND)
    app.dependency_overrides[get_graph] = FakeGraph
    async with (
        app.router.lifespan_context(app),
        httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app), base_url="http://testserver", headers=BEARER
        ) as http,
        mcp.Client(streamable_http_client("http://testserver/mcp", http_client=http), mode=mode) as client,
    ):
        assert client.protocol_version == version
        assert client.server_info is not None and client.server_info.name == "Dataregium OpenCDE server"
        assert client.server_capabilities.tools is not None
        listed = await client.list_tools()
        assert [tool.name for tool in listed.tools] == [tool.name for tool in routes.TOOLS]
        answer = await client.call_tool("list_models", {"project_id": None})
        assert answer.is_error is False
        assert answer.structured_content is not None and answer.structured_content["models"][0]["project_id"] == CLOUD
        refused = await client.call_tool("list_models", {"project_id": "not one of them"})
        assert refused.is_error is True
