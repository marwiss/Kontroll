# This file was generated with the assistance of an AI coding tool.
"""The MCP endpoint's guards (ADR 0028): the token on every request, the scope of a tool with its step-up, the
origin against DNS rebinding, no CORS and no session, the limit per token, the AI policy of a project, and nothing a
client or a project writes in a log or taken as an instruction. The database is stood in for
(``tests/mcp_support.py``); ``tests/integration/test_mcp_list_models.py`` has its side.
"""

from __future__ import annotations

import io
import json
import logging
from pathlib import Path
from typing import Any

import pytest
import structlog

from opencde.auth.scopes import MCP_PROPOSE
from opencde.logging import configure_logging
from opencde.mcp import routes
from opencde.mcp.registry import Arguments, Tool
from tests.mcp_support import (
    BEARER,
    CLOUD,
    LOCAL,
    MODERN,
    FakeGraph,
    call,
    endpoint,
    headers,
    legacy,
    model_row,
    principal,
    project,
    rpc,
)
from tests.security.test_prompt_injection import INJECTIONS, INSTRUCTION

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


async def _proposed(context: Any, arguments: Arguments) -> dict[str, Any]:
    return {"proposed": True}


PROPOSER = Tool(
    name="probe_propose",
    title="Probe",
    description="A tool that proposes, for the test.",
    arguments=Arguments,
    run=_proposed,
    scope=MCP_PROPOSE,
    read_only=False,
)


def test_a_tool_that_proposes_needs_mcp_propose_and_names_both_scopes_for_the_step_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    names = [tool.name for tool in routes.TOOLS if not tool.needs_ifcgraph]
    monkeypatch.setattr(routes, "TOOLS", (*routes.TOOLS, PROPOSER))
    monkeypatch.setitem(routes._BY_NAME, PROPOSER.name, PROPOSER)
    graph = FakeGraph()
    with endpoint(tmp_path, graph) as reader:
        listed = [tool["name"] for tool in rpc(reader, "tools/list").json()["result"]["tools"]]
        refused = call(reader, "probe_propose", {})
    assert listed == [*names, "probe_propose"], "every tool is listed, whatever the token holds"
    assert refused.status_code == 403 and refused.json()["code"] == "insufficient_scope"
    expected = f'Bearer error="insufficient_scope", resource_metadata="{METADATA}", scope="mcp mcp:propose"'
    assert refused.headers["www-authenticate"] == expected
    (event,) = graph.events()
    assert event["type"] == "mcp.denied" and event["actor"] == "u-anna" and event["client_id"] == "ai-client"
    assert event["details"] == {
        "reason": "scope",
        "scope": "mcp:propose",
        "tool": "probe_propose",
        "client_info": {"name": "test-client", "version": "1.0"},
    }
    with endpoint(tmp_path, found=principal(scopes=("mcp", "mcp:propose"))) as proposer:
        answer = call(proposer, "probe_propose", {})
    assert answer.json()["result"]["structuredContent"] == {"proposed": True}


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


# -- the limit --------------------------------------------------------------------------------------------------------


def test_a_token_makes_at_most_120_tool_calls_a_minute(tmp_path: Path) -> None:
    with endpoint(tmp_path, FakeGraph(models=[]), rate_limits_enabled=True) as client:
        answers = [call(client, "list_models", {"project_id": None}).json()["result"] for _ in range(121)]
        listed = rpc(client, "tools/list")
    assert all(answer["isError"] is False for answer in answers[:120])
    limited = answers[120]
    assert limited["isError"] is True and limited["content"][0]["text"].startswith(
        "Too many tool calls: at most 120 a minute for each token. Try again in "
    )
    assert listed.status_code == 200, "listing is no tool call"
    with endpoint(tmp_path, FakeGraph(models=[]), principal(hashed="another"), rate_limits_enabled=True) as other:
        assert call(other, "list_models", {"project_id": None}).json()["result"]["isError"] is False


# -- the AI policy ----------------------------------------------------------------------------------------------------


def _memberships() -> list[tuple[dict[str, Any], str]]:
    return [(project(CLOUD, "Cloud project", "cloud"), "editor"), (project(LOCAL, "Local project", None), "viewer")]


def test_a_team_server_lists_only_cloud_projects_and_refuses_a_local_one_by_its_id(tmp_path: Path) -> None:
    graph = FakeGraph(_memberships())
    with endpoint(tmp_path, graph) as client:
        everything = call(client, "list_models", {"project_id": None}).json()["result"]
        refused = call(client, "list_models", {"project_id": LOCAL.upper()}).json()["result"]
        served = call(client, "list_models", {"project_id": CLOUD}).json()["result"]
    assert everything["isError"] is False and served["isError"] is False
    assert [query["every_policy"] for query in graph.model_queries()] == [False, False]
    assert [query["project_id"] for query in graph.model_queries()] == [None, CLOUD], "the local one is never queried"
    assert refused["isError"] is True and "local only" in refused["content"][0]["text"]
    (event,) = graph.events()
    assert event["type"] == "mcp.denied" and event["actor"] == "u-anna"
    assert event["details"] == {
        "reason": "policy",
        "project_id": LOCAL,
        "tool": "list_models",
        "client_info": {"name": "test-client", "version": "1.0"},
    }


def test_the_local_engine_serves_every_project(tmp_path: Path) -> None:
    graph = FakeGraph(_memberships(), models=[model_row(LOCAL, ai_policy=None)])
    with endpoint(
        tmp_path,
        graph,
        ON_THE_LOOPBACK,
        base_url=LOOPBACK,
        environment="local",
        public_url=LOOPBACK,
        cors_origins=["null"],
    ) as client:
        everything = call(client, "list_models", {"project_id": None}).json()["result"]
        local = call(client, "list_models", {"project_id": LOCAL}).json()["result"]
    assert [query["every_policy"] for query in graph.model_queries()] == [True, True]
    assert local["isError"] is False and local["structuredContent"]["models"][0]["ai_policy"] == "local"
    assert everything["isError"] is False and not graph.events()


def test_a_project_that_is_not_the_users_is_not_there_whatever_its_policy(tmp_path: Path) -> None:
    graph = FakeGraph(memberships=[])
    with endpoint(tmp_path, graph) as client:
        for project_id in (CLOUD, LOCAL, "../../etc/passwd", "MATCH (n) DETACH DELETE n"):
            result = call(client, "list_models", {"project_id": project_id}).json()["result"]
            assert result["content"][0]["text"] == "There is no project with this id among your projects"
    assert not graph.events() and not graph.model_queries()


# -- data, never instructions; nothing in the log ---------------------------------------------------------------------


@pytest.mark.parametrize("text", INJECTIONS)
def test_a_text_from_a_project_comes_back_as_data_in_its_field(tmp_path: Path, text: str) -> None:
    graph = FakeGraph(models=[model_row(title=text, project_name=text, file_name=text, schema=text)])
    with endpoint(tmp_path, graph) as client:
        before = rpc(client, "tools/list").json()["result"]["tools"]
        result = call(client, "list_models", {"project_id": None}).json()["result"]
        after = rpc(client, "tools/list").json()["result"]["tools"]
    (row,) = result["structuredContent"]["models"]
    assert row["title"] == row["project_name"] == row["file_name"] == text[:200]
    assert json.loads(result["content"][0]["text"]) == result["structuredContent"], "the text is the same JSON"
    assert before == after, "the tools are the same whatever the projects hold"
    assert text not in json.dumps(before) and "instruction" not in before[0]["inputSchema"]


def test_no_argument_and_no_text_reaches_the_log(tmp_path: Path) -> None:
    configure_logging("INFO", json_output=True)
    root = logging.getLogger()
    buffer = io.StringIO()
    handler = logging.StreamHandler(buffer)
    handler.setFormatter(root.handlers[0].formatter)
    root.handlers[:] = [handler]
    graph = FakeGraph(_memberships(), models=[model_row(title=INSTRUCTION)])
    try:
        with endpoint(tmp_path, graph, log_level="INFO", rate_limits_enabled=True) as client:
            root.handlers[:] = [handler]  # the application configures the logging as it starts
            call(client, "list_models", {"project_id": None, "extra": INSTRUCTION})
            call(client, "list_models", {"project_id": INSTRUCTION[:60]})
            call(client, "list_models", {"project_id": LOCAL})
            call(client, "list_models", {"project_id": None})
            rpc(client, "tools/call", {"name": INSTRUCTION[:60]}, sent=headers("tools/call", INSTRUCTION[:60]))
            structlog.get_logger("opencde.tests").info("marker")
    finally:
        configure_logging("WARNING", json_output=False)
    logged = buffer.getvalue()
    assert "marker" in logged and "POST http://testserver/mcp" in logged, "the log of the requests was captured"
    assert INSTRUCTION[:40] not in logged and "Ignore all previous" not in logged
    details = [event["details"] for event in graph.events()]
    assert all(INSTRUCTION[:40] not in json.dumps(found) for found in details)


def test_a_bearer_token_is_never_answered_back(tmp_path: Path) -> None:
    with endpoint(tmp_path) as client:
        answers = [rpc(client, "server/discover"), call(client, "list_models", {"project_id": None})]
        answers.append(client.get("/mcp", headers=BEARER))
    token = BEARER["Authorization"].split()[1]
    assert all(token not in answer.text for answer in answers)
