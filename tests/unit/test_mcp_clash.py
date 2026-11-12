# This file was generated with the assistance of an AI coding tool.
"""``start_clash_check`` and ``get_clash_check`` through the MCP endpoint (ADR 0028, ADR 0019): a check started as the
REST route starts one, with its defaults, and recorded as ``mcp.clash.started``; its report waited for at most 20
seconds and held to 200 clashes and 256 kB; and the refusals. The database and the IFC-LPG service are stood in for
(``tests/mcp_read_support.py``)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from opencde.mcp import clash
from tests.mcp_read_support import CLASH, FakeService, clash_row, pair, tools
from tests.mcp_support import CLOUD, DOCUMENT, FakeGraph, call

SIDE = {"document_id": DOCUMENT.upper(), "version_index": 3, "types": None}
START = {"project_id": CLOUD, "a": SIDE, "b": SIDE, "mode": None, "tolerance": None, "clearance": None}


def result(client: Any, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    answer = call(client, name, arguments)
    assert answer.status_code == 200, answer.text
    return answer.json()["result"]


def report(client: Any, **arguments: Any) -> dict[str, Any]:
    return result(
        client, "get_clash_check", {"project_id": CLOUD, "clash_id": CLASH, "wait_seconds": None, **arguments}
    )


# -- starting ----------------------------------------------------------------------------------------------------------


def test_a_check_starts_as_the_route_starts_one_and_is_recorded(tmp_path: Path) -> None:
    service, graph = FakeService(), FakeGraph()
    with tools(tmp_path, graph, service) as client:
        started = result(client, "start_clash_check", START)
    assert started["isError"] is False and started["structuredContent"] == {"clash_id": CLASH, "state": "queued"}
    (scheduled,) = service.scheduled
    side = {"document_id": DOCUMENT, "version_index": 3, "types": None}
    assert scheduled == {
        "project_id": CLOUD,
        "author": "anna",
        "request": {"a": side, "b": side, "mode": "intersection", "tolerance": 0.001, "clearance": 0.05},
    }, "the ids as the server writes them, and the REST route's defaults for what is null"
    (event,) = graph.events()
    assert event["type"] == "mcp.clash.started" and event["actor"] == "u-anna" and event["client_id"] == "ai-client"
    assert event["details"] == {
        "project_id": CLOUD,
        "clash_id": CLASH,
        "a": {"document_id": DOCUMENT, "version_index": 3},
        "b": {"document_id": DOCUMENT, "version_index": 3},
        "tool": "start_clash_check",
        "client_info": {"name": "test-client", "version": "1.0"},
    }


class BusyGraph(FakeGraph):
    """A graph where the user already has two checks waiting or running in the project."""

    async def run(self, query: str, **params: Any) -> list[dict[str, Any]]:
        if "c.state IN ['queued', 'running']" in query:
            self.calls.append((query, params))
            return [{"n": clash.MAX_OPEN_CHECKS}]
        return await super().run(query, **params)


def test_a_user_with_two_checks_under_way_starts_no_third(tmp_path: Path) -> None:
    """The worker runs one job at a time: an AI in a loop must not hold up a project's conversions and trials."""
    service, graph = FakeService(), BusyGraph()
    with tools(tmp_path, graph, service) as client:
        refused = result(client, "start_clash_check", START)
    assert refused["isError"] is True and "2 clash checks waiting or running" in refused["content"][0]["text"]
    assert service.scheduled == [], "nothing is queued"
    (event,) = graph.events()
    assert event["type"] == "mcp.denied" and event["details"]["reason"] == "limit"


def test_a_check_takes_the_mode_its_distances_and_the_classes_of_each_side(tmp_path: Path) -> None:
    service = FakeService()
    walls = {**SIDE, "types": ["IfcWall", "IfcSlab"]}
    with tools(tmp_path, service=service) as client:
        result(
            client, "start_clash_check", {**START, "a": walls, "mode": "clearance", "tolerance": 0, "clearance": 0.2}
        )
    request = service.scheduled[0]["request"]
    assert request["mode"] == "clearance" and request["tolerance"] == 0 and request["clearance"] == 0.2
    assert request["a"]["types"] == ["IfcWall", "IfcSlab"] and request["b"]["types"] is None


@pytest.mark.parametrize(
    ("arguments", "expected"),
    [
        ({"a": {**SIDE, "types": ["Wall"]}}, "a.types.0: String should match pattern '^Ifc[A-Za-z0-9]{1,64}$'"),
        ({"a": {**SIDE, "types": ["IfcWall"] * 51}}, "a.types: List should have at most 50 items after validation"),
        ({"b": {**SIDE, "version_index": 0}}, "b.version_index: Input should be greater than or equal to 1"),
        ({"b": {**SIDE, "extra": 1}}, "an argument the tool does not take"),
        ({"b": None}, "b: Input should be a valid dictionary or instance of ClashSide"),
        ({"mode": "collision"}, "mode: Input should be 'intersection' or 'clearance'"),
        ({"tolerance": 2}, "tolerance: Input should be less than or equal to 1"),
        ({"clearance": 0}, "clearance: Input should be greater than 0"),
    ],
)
def test_arguments_the_schema_refuses_start_nothing(tmp_path: Path, arguments: dict[str, Any], expected: str) -> None:
    service = FakeService()
    with tools(tmp_path, service=service) as client:
        refused = result(client, "start_clash_check", {**START, **arguments})
    assert refused["isError"] is True and expected in refused["content"][0]["text"]
    assert not service.scheduled


def test_a_side_that_names_no_document_or_a_check_that_is_off_starts_nothing(tmp_path: Path) -> None:
    service = FakeService()
    with tools(tmp_path, service=service) as client:
        no_document = result(client, "start_clash_check", {**START, "b": {**SIDE, "document_id": "not one"}})
        no_project = result(
            client, "start_clash_check", {**START, "project_id": "55555555-5555-4555-8555-555555555555"}
        )
    with tools(tmp_path, service=service, ifcgraph_clash_enabled=False) as client:
        off = result(client, "start_clash_check", START)
        off_report = report(client)
    assert no_document["content"][0]["text"] == "Document version not found"
    assert no_project["content"][0]["text"] == "There is no project with this id among your projects"
    assert off["content"][0]["text"] == off_report["content"][0]["text"] == "The clash check is off on this server"
    assert not service.scheduled and not service.read


# -- the report --------------------------------------------------------------------------------------------------------


def test_a_report_gives_the_check_and_its_clashes_without_an_address(tmp_path: Path) -> None:
    done = clash_row(
        "done",
        done_at="2026-11-12T09:31:00.000Z",
        count=1,
        set_a=3,
        set_b=3,
        missing=0,
        seconds=1.5,
        truncated=False,
        clashes=[pair()],
    )
    with tools(tmp_path, service=FakeService(reports=[done])) as client:
        answer = report(client)["structuredContent"]
    side = {"document_id": DOCUMENT, "version_index": 3, "types": None}
    assert answer == {
        "clash_id": CLASH,
        "state": "done",
        "request": {"a": side, "b": side, "mode": "intersection", "tolerance": 0.001, "clearance": 0.05},
        "author": "anna",
        "created_at": "2026-11-12T09:30:00.000Z",
        "done_at": "2026-11-12T09:31:00.000Z",
        "error": None,
        "count": 1,
        "set_a": 3,
        "set_b": 3,
        "missing": 0,
        "seconds": 1.5,
        "clashes": [pair()],
        "truncated": False,
    }


def test_a_check_under_way_has_no_clashes_yet_and_a_failed_one_says_why(tmp_path: Path) -> None:
    failed = clash_row("failed", error="ValueError: document version x/1 is not an IFC file")
    with tools(tmp_path, service=FakeService(reports=[clash_row("running")])) as client:
        running = report(client)["structuredContent"]
    with tools(tmp_path, service=FakeService(reports=[failed])) as client:
        broken = report(client)["structuredContent"]
    assert running["state"] == "running" and running["clashes"] is None and running["count"] is None
    assert broken["state"] == "failed" and broken["error"] == "ValueError: document version x/1 is not an IFC file"


def test_a_report_holds_at_most_200_clashes_and_256_kb(tmp_path: Path) -> None:
    many = clash_row("done", count=250, truncated=False, clashes=[pair() for _ in range(250)])
    with tools(tmp_path, service=FakeService(reports=[many])) as client:
        answer = report(client)["structuredContent"]
    assert len(answer["clashes"]) == 200 and answer["truncated"] is True and answer["count"] == 250
    cut = clash_row("done", count=10, truncated=True, clashes=[pair() for _ in range(10)])
    with tools(tmp_path, service=FakeService(reports=[cut])) as client:
        assert report(client)["structuredContent"]["truncated"] is True, "the worker kept fewer than it found"
    long = "é" * 5000
    named = pair(long, long)
    named["b"] |= {"name": long, "storey": long}
    wide = clash_row("done", count=200, truncated=False, clashes=[named] * 200)
    with tools(tmp_path, service=FakeService(reports=[wide])) as client:
        whole = report(client)
    answer = whole["structuredContent"]
    assert answer["truncated"] is True and 0 < len(answer["clashes"]) < 200
    assert all(
        len(found[side][key]) == 200 for found in answer["clashes"] for side in "ab" for key in ("name", "storey")
    )
    assert len(whole["content"][0]["text"].encode("utf-8")) <= 256 * 1024


def test_a_wait_ends_when_the_check_does_or_after_the_seconds_asked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(clash, "POLL_SECONDS", 0.01)
    done = clash_row("done", count=0, set_a=3, set_b=3, missing=0, seconds=0.1, truncated=False, clashes=[])
    service = FakeService(reports=[clash_row("queued"), clash_row("running"), done])
    with tools(tmp_path, service=service) as client:
        answer = report(client, wait_seconds=20)["structuredContent"]
    assert answer["state"] == "done" and answer["clashes"] == [] and len(service.read) == 3
    service = FakeService(reports=[clash_row("queued")])
    with tools(tmp_path, service=service) as client:
        at_once = report(client, wait_seconds=None)["structuredContent"]
        zero = report(client, wait_seconds=0)["structuredContent"]
    assert at_once["state"] == zero["state"] == "queued" and len(service.read) == 2, "no wait without seconds"
    service = FakeService(reports=[clash_row("running")])
    with tools(tmp_path, service=service) as client:
        waited = report(client, wait_seconds=1)["structuredContent"]
    assert waited["state"] == "running" and 2 <= len(service.read) <= 150, "a second, then the answer as it is"


@pytest.mark.parametrize(
    ("arguments", "expected"),
    [
        ({"clash_id": "not a check"}, "Clash check not found"),
        ({"clash_id": "55555555-5555-4555-8555-555555555555"}, "Clash check not found"),
        ({"project_id": "not a project"}, "There is no project with this id among your projects"),
        ({"wait_seconds": 21}, "Invalid arguments: wait_seconds: Input should be less than or equal to 20"),
        ({"wait_seconds": -1}, "Invalid arguments: wait_seconds: Input should be greater than or equal to 0"),
    ],
)
def test_a_report_that_is_not_there_or_a_wait_past_the_limit_is_refused(
    tmp_path: Path, arguments: dict[str, Any], expected: str
) -> None:
    with tools(tmp_path, service=FakeService(reports=[clash_row()])) as client:
        refused = report(client, **arguments)
    assert refused["isError"] is True and refused["content"][0]["text"] == expected
