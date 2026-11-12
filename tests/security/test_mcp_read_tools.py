# This file was generated with the assistance of an AI coding tool.
"""The guards of ``server_query``, ``get_publication`` and the clash tools (ADR 0028): the AI policy of a project on
every one of them, a text from a model or a project as data in its field, a value given only as a parameter, a refusal
that quotes nothing, and nothing a client sends in a log or in the audit log. The database and the IFC-DB service are
stood in for (``tests/mcp_read_support.py``); ``tests/integration/test_mcp_server_query.py`` and
``tests/integration/test_mcp_clash.py`` have their side.
"""

from __future__ import annotations

import io
import json
import logging
from pathlib import Path
from typing import Any

import pytest
import structlog

from opencde.ifcgraph.queries import QUERIES
from opencde.logging import configure_logging
from tests.mcp_read_support import (
    CLASH,
    PUBLISHED,
    DocumentsGraph,
    FakeService,
    IfcGraph,
    clash_row,
    pair,
    tools,
    version,
)
from tests.mcp_support import CLOUD, DOCUMENT, LOCAL, call, principal, project, rpc
from tests.security.test_prompt_injection import INJECTIONS, INSTRUCTION

pytestmark = pytest.mark.security

LOOPBACK = "http://127.0.0.1:8000"
SIDE = {"document_id": DOCUMENT, "version_index": 3, "types": None}
QUERY = {"version_index": None, "class": None, "pset": None, "property": None, "global_id": None, "since": None}
CALLS: dict[str, dict[str, Any]] = {
    "server_query": {"document_id": DOCUMENT, "name": None, **QUERY},
    "get_publication": {"document_id": DOCUMENT, "version_index": 3},
    "start_clash_check": {"a": SIDE, "b": SIDE, "mode": None, "tolerance": None, "clearance": None},
    "get_clash_check": {"clash_id": CLASH, "wait_seconds": None},
}


def arguments(name: str, project_id: str) -> dict[str, Any]:
    """A call of the tool that reaches the project: by its id, or by its document."""
    return CALLS[name] | ({"project_id": project_id} if "clash" in name else {})


def _local_world() -> tuple[DocumentsGraph, FakeService]:
    memberships = [
        (project(CLOUD, "Cloud project", "cloud"), "editor"),
        (project(LOCAL, "Local project", None), "viewer"),
    ]
    graph = DocumentsGraph(memberships, versions=[version(3, project_id=LOCAL)], publications={3: PUBLISHED})
    return graph, FakeService(reports=[clash_row(project_id=LOCAL)])


# -- the AI policy ----------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("name", list(CALLS))
def test_a_team_server_refuses_a_local_projects_data_into_the_audit_log(tmp_path: Path, name: str) -> None:
    graph, service = _local_world()
    with tools(tmp_path, graph, service) as client:
        result = call(client, name, arguments(name, LOCAL)).json()["result"]
    assert result["isError"] is True and "local only" in result["content"][0]["text"]
    (event,) = graph.events()
    assert event["type"] == "mcp.denied" and event["actor"] == "u-anna"
    assert event["details"] == {
        "reason": "policy",
        "project_id": LOCAL,
        "tool": name,
        "client_info": {"name": "test-client", "version": "1.0"},
    }
    assert not graph.conversion_lookups() and not service.graph.asked and not service.scheduled and not service.read
    assert not [query for query, _params in graph.calls if "HAS_PUBLICATION" in query]


@pytest.mark.parametrize("name", list(CALLS))
def test_the_local_engine_serves_a_local_project(tmp_path: Path, name: str) -> None:
    graph, service = _local_world()
    graph.conversions = {3: ("done", "model")}
    loopback = principal(resource=f"{LOOPBACK}/mcp")
    with tools(
        tmp_path,
        graph,
        service,
        found=loopback,
        base_url=LOOPBACK,
        environment="local",
        public_url=LOOPBACK,
        cors_origins=["null"],
    ) as client:
        result = call(client, name, arguments(name, LOCAL)).json()["result"]
    assert result["isError"] is False, result
    assert not [event for event in graph.events() if event["type"] == "mcp.denied"]


# -- data, never instructions ------------------------------------------------------------------------------------------


@pytest.mark.parametrize("text", INJECTIONS)
def test_a_text_from_a_model_or_a_project_comes_back_as_data_in_its_field(tmp_path: Path, text: str) -> None:
    rows = [{"global_id": "1Xezbq735AdBO_4DerG66G", "class": "IfcWall", "name": text, "container": text}]
    published = PUBLISHED | {"file_name": text, "published_by": text}
    named = pair(text, text)
    done = clash_row("done", count=1, set_a=1, set_b=1, missing=0, seconds=0.1, truncated=False, clashes=[named])
    graph = DocumentsGraph(publications={3: published})
    service = FakeService(IfcGraph({"elements": rows}), reports=[done])
    with tools(tmp_path, graph, service) as client:
        before = rpc(client, "tools/list").json()["result"]["tools"]
        queried = call(client, "server_query", CALLS["server_query"] | {"name": "elements", "class": "IfcWall"})
        publication = call(client, "get_publication", CALLS["get_publication"])
        report = call(client, "get_clash_check", arguments("get_clash_check", CLOUD))
        after = rpc(client, "tools/list").json()["result"]["tools"]
    results = [answer.json()["result"] for answer in (queried, publication, report)]
    assert all(result["isError"] is False for result in results)
    assert all(json.loads(result["content"][0]["text"]) == result["structuredContent"] for result in results)
    ((_id, _class, name, container),) = results[0]["structuredContent"]["rows"]
    assert name == container == text[:1000]
    assert results[1]["structuredContent"]["file_name"] == results[1]["structuredContent"]["published_by"] == text[:200]
    (found,) = results[2]["structuredContent"]["clashes"]
    assert found["a"]["name"] == found["a"]["storey"] == text[:200]
    assert before == after, "the tools are the same whatever the projects hold"
    assert text not in json.dumps(before)


def test_a_value_reaches_the_ifc_graph_as_a_parameter_only(tmp_path: Path) -> None:
    service = FakeService(IfcGraph({"property": []}))
    with tools(tmp_path, service=service) as client:
        given = CALLS["server_query"] | {"name": "property", "pset": INSTRUCTION, "property": "' OR 1=1 //"}
        assert call(client, "server_query", given).json()["result"]["isError"] is False
    ((name, params),) = service.graph.asked
    assert name == "property" and params["pset"] == INSTRUCTION and params["property"] == "' OR 1=1 //"
    assert INSTRUCTION not in QUERIES["property"].cypher, "the statement is the library's own"


@pytest.mark.parametrize(
    ("name", "given"),
    [
        ("server_query", {"document_id": INSTRUCTION[:60]}),
        ("server_query", {"name": "elements", "class": INSTRUCTION}),
        ("server_query", {"name": "entity", "global_id": INSTRUCTION}),
        ("server_query", {"name": "storeys", "pset": INSTRUCTION}),
        ("server_query", {"name": INSTRUCTION[:60]}),
        ("get_publication", {"document_id": INSTRUCTION[:60]}),
        ("start_clash_check", {"a": SIDE | {"document_id": INSTRUCTION[:60]}}),
        ("start_clash_check", {"a": SIDE | {"types": [INSTRUCTION[:60]]}}),
        ("start_clash_check", {"project_id": INSTRUCTION[:60]}),
        ("get_clash_check", {"clash_id": INSTRUCTION[:60]}),
    ],
)
def test_a_refusal_never_quotes_what_was_given(tmp_path: Path, name: str, given: dict[str, Any]) -> None:
    service = FakeService(reports=[clash_row()])
    with tools(tmp_path, service=service) as client:
        result = call(client, name, arguments(name, CLOUD) | given).json()["result"]
    assert result["isError"] is True
    assert INSTRUCTION[:30] not in result["content"][0]["text"] and "Ignore" not in result["content"][0]["text"]
    assert not service.scheduled and not service.graph.asked


def test_no_argument_reaches_the_log_or_the_audit_log(tmp_path: Path) -> None:
    configure_logging("INFO", json_output=True)
    root = logging.getLogger()
    buffer = io.StringIO()
    handler = logging.StreamHandler(buffer)
    handler.setFormatter(root.handlers[0].formatter)
    root.handlers[:] = [handler]
    graph, service = DocumentsGraph(), FakeService(IfcGraph({"property": []}))
    try:
        with tools(tmp_path, graph, service, log_level="INFO") as client:
            root.handlers[:] = [handler]  # the application configures the logging as it starts
            query = CALLS["server_query"] | {"name": "property", "pset": INSTRUCTION, "property": "x"}
            call(client, "server_query", query)
            call(client, "server_query", CALLS["server_query"] | {"document_id": INSTRUCTION[:60]})
            call(client, "start_clash_check", arguments("start_clash_check", CLOUD))
            call(client, "start_clash_check", arguments("start_clash_check", CLOUD) | {"mode": INSTRUCTION[:60]})
            call(client, "get_clash_check", arguments("get_clash_check", CLOUD) | {"clash_id": INSTRUCTION[:60]})
            structlog.get_logger("opencde.tests").info("marker")
    finally:
        configure_logging("WARNING", json_output=False)
    logged = buffer.getvalue()
    assert "marker" in logged and "POST http://testserver/mcp" in logged, "the log of the requests was captured"
    assert INSTRUCTION[:40] not in logged and "Ignore all previous" not in logged
    events = graph.events()
    assert [event["type"] for event in events] == ["mcp.clash.started"]
    assert all(INSTRUCTION[:40] not in json.dumps(event) for event in events)
