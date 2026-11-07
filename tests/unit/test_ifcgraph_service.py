# This file was generated with the assistance of an AI coding tool.
"""The check of an upload, without a database or IfcOpenShell: what it stores, and what it logs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from opencde.ifcgraph import service as service_module
from opencde.ifcgraph.service import IfcGraphService
from opencde.ifcgraph.validation import unpack_report
from opencde.storage import LocalStorage
from tests.conftest import test_settings as make_settings  # aliased so pytest does not collect it as a test

# What an issue may carry: a line of the uploaded file, which the log is not to have.
LINE = "#9=IFCWALL('0KhR8hr7H8eewFRKm6V1bJ',#5,'what an owner history may hold',$,$,$,$,$,.NOSUCHWALL.);"


class Graph:
    """Answers the claim of a queued check and keeps every write."""

    def __init__(self) -> None:
        self.writes: list[tuple[str, dict[str, Any]]] = []

    async def run(self, query: str, **params: Any) -> list[dict[str, Any]]:
        self.writes.append((query, params))
        return [{"id": params["id"]}] if "SET r.state = $running" in query else []


class Log:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    def info(self, event: str, **fields: Any) -> None:
        self.events.append((event, fields))

    warning = info


@pytest.fixture
def checking(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[IfcGraphService, Graph, Log]:
    graph = Graph()
    log = Log()
    service = IfcGraphService(graph, LocalStorage(tmp_path), make_settings(tmp_path, ifcgraph_enabled=True))
    monkeypatch.setattr(service_module, "log", log)
    monkeypatch.setattr(service, "_prepare_input", lambda key, name, workdir: tmp_path / "model.ifc")
    return service, graph, log


async def test_the_log_gets_the_number_of_issues_and_the_report_their_words(
    checking: tuple[IfcGraphService, Graph, Log], monkeypatch: pytest.MonkeyPatch
) -> None:
    service, graph, log = checking
    issue = {"kind": "schema", "severity": "error", "message": LINE, "step_id": 9, "global_id": None, "attribute": None}

    async def answer(command: list[str], what: str, answers: tuple[int, ...] = (0,)) -> str:
        assert command[-3:-1] == ["--report", "--memory-mb"] and answers == (0, 1), (
            "issues are an answer, not a failure"
        )
        return json.dumps({"ruleset": "IfcOpenShell x", "issue_count": 1, "truncated": False, "issues": [issue]})

    monkeypatch.setattr(service, "_in_a_process", answer)
    await service._validate("check-1", "documents/x", "model.ifc")

    assert log.events == [("ifc_validation_done", {"validation_id": "check-1", "issues": 1})]
    stored = graph.writes[-1][1]
    assert stored["state"] == "done" and stored["fields"]["issue_count"] == 1
    assert unpack_report(stored["fields"]["report"]) == [issue]


async def test_a_check_that_fails_logs_what_failed_and_nothing_of_the_file(
    checking: tuple[IfcGraphService, Graph, Log], monkeypatch: pytest.MonkeyPatch
) -> None:
    service, graph, log = checking

    async def fails(command: list[str], what: str, answers: tuple[int, ...] = (0,)) -> str:
        raise RuntimeError(f"could not read {LINE}")

    monkeypatch.setattr(service, "_in_a_process", fails)
    await service._validate("check-2", "documents/x", "model.ifc")

    assert log.events == [("ifc_validation_failed", {"validation_id": "check-2", "error": "RuntimeError"})]
    assert graph.writes[-1][1]["state"] == "failed", "the version says it could not be checked"


async def test_a_check_another_process_has_taken_is_left_alone(
    checking: tuple[IfcGraphService, Graph, Log], monkeypatch: pytest.MonkeyPatch
) -> None:
    service, graph, log = checking

    async def taken(query: str, **params: Any) -> list[dict[str, Any]]:
        graph.writes.append((query, params))
        return []

    monkeypatch.setattr(graph, "run", taken)
    await service._validate("check-3", "documents/x", "model.ifc")
    assert log.events == [] and len(graph.writes) == 1
