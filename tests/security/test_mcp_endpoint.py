# This file was generated with the assistance of an AI coding tool.
"""The MCP endpoint's guards (ADR 0028): the token on every request, the origin against DNS rebinding, no CORS and
no session, and no token answered back. The database is stood in for (``tests/mcp_support.py``).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.mcp_support import (
    BEARER,
    MODERN,
    call,
    endpoint,
    headers,
    legacy,
    principal,
    rpc,
)

pytestmark = pytest.mark.security

METADATA = "http://testserver/.well-known/oauth-protected-resource/mcp"
LOOPBACK = "http://127.0.0.1:8000"
ON_THE_LOOPBACK = principal(resource=f"{LOOPBACK}/mcp")  # the local engine's own resource


# -- the token --------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("method", ["server/discover", "tools/list", "tools/call"])
def test_every_request_needs_a_token_bound_to_the_endpoint(tmp_path: Path, method: str) -> None:
    with endpoint(tmp_path) as client:
        message = {"jsonrpc": "2.0", "id": 1, "method": method, "params": {"name": "list_models"}}
        missing = client.post("/mcp", json=message, headers={"MCP-Protocol-Version": MODERN, "Mcp-Method": method})
    assert missing.status_code == 401 and missing.json()["code"] == "unauthenticated"
    assert missing.headers["www-authenticate"] == f'Bearer resource_metadata="{METADATA}", scope="mcp"'
    for found in (None, principal(resource=None, scopes=("profile", "bcf", "documents")), principal(resource="x")):
        with endpoint(tmp_path, found=found) as client:
            refused = rpc(client, method)
        assert refused.status_code == 401 and refused.json()["code"] == "invalid_token", found
        assert refused.headers["www-authenticate"].startswith('Bearer error="invalid_token", resource_metadata=')


def test_the_handshake_needs_the_token_too(tmp_path: Path) -> None:
    with endpoint(tmp_path, found=None) as client:
        params = {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "old", "version": "1"}}
        assert legacy(client, "initialize", params, version=None).status_code == 401


# -- the origin, CORS and sessions ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("origin", "status"),
    [
        (None, 200),
        ("http://testserver", 200),  # the server's own pages
        ("https://dataspatium.example", 200),  # named in OPENCDE_CORS_ORIGINS
        ("HTTPS://DATASPATIUM.EXAMPLE", 200),
        ("null", 403),  # a file or a sandbox, even when named
        ("https://evil.example", 403),
        ("http://testserver.evil.example", 403),
        ("http://localhost", 403),
    ],
)
def test_a_browser_origin_must_be_the_servers_own_or_named(tmp_path: Path, origin: str | None, status: int) -> None:
    with endpoint(tmp_path, cors_origins=["null", "https://dataspatium.example"]) as client:
        sent = headers("tools/list") | ({"Origin": origin} if origin else {})
        answer = rpc(client, "tools/list", sent=sent)
    assert answer.status_code == status, origin
    if status == 403:
        assert answer.json()["code"] == "forbidden"


def test_a_wildcard_opens_the_api_to_every_origin_but_not_the_endpoint(tmp_path: Path) -> None:
    with endpoint(tmp_path, cors_origins=["*"]) as client:
        assert (
            rpc(client, "tools/list", sent=headers("tools/list") | {"Origin": "https://evil.example"}).status_code
            == 403
        )
        assert client.get("/foundation/versions", headers={"Origin": "https://evil.example"}).status_code == 200


def test_a_bad_origin_is_refused_before_the_token_is_looked_at(tmp_path: Path) -> None:
    with endpoint(tmp_path, found=None) as client:
        answer = client.post("/mcp", json={}, headers={"Origin": "https://evil.example"})
    assert answer.status_code == 403


def test_the_endpoint_shares_nothing_cross_origin_and_never_makes_a_session(tmp_path: Path) -> None:
    with endpoint(tmp_path, cors_origins=["https://dataspatium.example"]) as client:
        allowed = rpc(client, "tools/list", sent=headers("tools/list") | {"Origin": "https://dataspatium.example"})
        preflight = client.options(
            "/mcp",
            headers={"Origin": "https://dataspatium.example", "Access-Control-Request-Method": "POST"},
        )
        initialized = legacy(
            client, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {}}, version=None
        )
    assert allowed.status_code == 200
    for answer in (allowed, preflight, initialized):
        assert not any(name.startswith("access-control-") for name in answer.headers), answer.headers
        assert "mcp-session-id" not in answer.headers
    assert preflight.status_code == 405


def test_the_local_engine_answers_only_on_the_loopback_here_too(tmp_path: Path) -> None:
    with endpoint(
        tmp_path,
        found=ON_THE_LOOPBACK,
        base_url=LOOPBACK,
        environment="local",
        public_url=LOOPBACK,
        cors_origins=["null", "https://marwiss.github.io"],
    ) as client:
        assert rpc(client, "tools/list").status_code == 200
        rebinding = rpc(client, "tools/list", sent=headers("tools/list") | {"Host": "evil.example"})
        own_page = rpc(client, "tools/list", sent=headers("tools/list") | {"Origin": LOOPBACK})
    assert rebinding.status_code == 421 and own_page.status_code == 200


# -- no token answered back -------------------------------------------------------------------------------------------


def test_a_bearer_token_is_never_answered_back(tmp_path: Path) -> None:
    with endpoint(tmp_path) as client:
        answers = [rpc(client, "server/discover"), call(client, "list_models", {"project_id": None})]
        answers.append(client.get("/mcp", headers=BEARER))
    token = BEARER["Authorization"].split()[1]
    assert all(token not in answer.text for answer in answers)
