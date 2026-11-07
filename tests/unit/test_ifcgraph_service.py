# This file was generated with the assistance of an AI coding tool.
"""The check of an upload, without a database or IfcOpenShell: what it stores, and what it logs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from ifc_lpg.validation import unpack_report

from opencde.ifcgraph import service as service_module
from opencde.ifcgraph.service import IfcGraphService
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


SCHEMA_ANSWER = {
    "ruleset": "IfcOpenShell 0.9.0 (IFC4)",
    "issue_count": 1,
    "error_count": 1,
    "truncated": False,
    "issues": [{"kind": "schema", "severity": "error", "message": LINE, "step_id": 9}],
}


def with_rules(tmp_path: Path, service: IfcGraphService) -> None:
    """An installed environment for ifc-gherkin-rules, as far as the service looks (ADR 0012)."""
    env = tmp_path / "gherkin"
    env.mkdir()
    (env / "manifest.json").write_text(json.dumps({"ruleset": "ifc-gherkin-rules 893f827 with IfcOpenShell 0.8.6"}))
    service.settings = make_settings(tmp_path, ifcgraph_enabled=True, ifcgraph_gherkin_env=str(env))


async def test_the_rules_findings_join_the_schemas_in_one_report(
    tmp_path: Path, checking: tuple[IfcGraphService, Graph, Log], monkeypatch: pytest.MonkeyPatch
) -> None:
    service, graph, log = checking
    with_rules(tmp_path, service)
    found = {"kind": "gherkin", "rule": "IFC106", "severity": "warning", "message": LINE, "step_id": 99}
    not_run = [{"rule": "GEM004", "error": "FileNotFoundError"}]

    async def answer(command: list[str], what: str, answers: tuple[int, ...] = (0,)) -> str:
        if command[2] == "ifc_lpg.gherkin":
            assert command[command.index("--env") + 1] == str(tmp_path / "gherkin") and answers == (0, 1)
            ruleset = "ifc-gherkin-rules 893f827 with IfcOpenShell 0.8.6"
            reply = {"ruleset": ruleset, "issue_count": 1, "error_count": 0, "truncated": False, "issues": [found]}
            return json.dumps({**reply, "rules_not_run": not_run})
        return json.dumps(SCHEMA_ANSWER)

    monkeypatch.setattr(service, "_in_a_process", answer)
    await service._validate("check-4", "documents/x", "model.ifc")

    fields = graph.writes[-1][1]["fields"]
    assert fields["issue_count"] == 2 and fields["error_count"] == 1 and fields["truncated"] is False
    assert fields["ruleset"] == "IfcOpenShell 0.9.0 (IFC4); ifc-gherkin-rules 893f827 with IfcOpenShell 0.8.6"
    assert [check["name"] for check in json.loads(fields["checks"])] == ["schema", "gherkin"]
    assert json.loads(fields["checks"])[1]["rules_not_run"] == not_run
    assert unpack_report(fields["report"]) == [SCHEMA_ANSWER["issues"][0], found]
    assert log.events == [("ifc_validation_done", {"validation_id": "check-4", "issues": 2})]


async def test_when_the_rules_cannot_run_the_schemas_check_stands(
    tmp_path: Path, checking: tuple[IfcGraphService, Graph, Log], monkeypatch: pytest.MonkeyPatch
) -> None:
    service, graph, log = checking
    with_rules(tmp_path, service)

    async def answer(command: list[str], what: str, answers: tuple[int, ...] = (0,)) -> str:
        if command[2] == "ifc_lpg.gherkin":
            raise RuntimeError(f"behave stopped at {LINE}")
        return json.dumps(SCHEMA_ANSWER)

    monkeypatch.setattr(service, "_in_a_process", answer)
    await service._validate("check-5", "documents/x", "model.ifc")

    stored = graph.writes[-1][1]
    assert stored["state"] == "done" and stored["fields"]["issue_count"] == 1 and stored["fields"]["error_count"] == 1
    assert stored["fields"]["ruleset"] == "IfcOpenShell 0.9.0 (IFC4)", "only the rule sets that ran"
    gherkin = json.loads(stored["fields"]["checks"])[1]
    assert gherkin == {
        "name": "gherkin",
        "state": "failed",
        "ruleset": "ifc-gherkin-rules 893f827 with IfcOpenShell 0.8.6",
        "issue_count": 0,
    }
    assert log.events == [
        ("ifc_gherkin_failed", {"error": "RuntimeError"}),
        ("ifc_validation_done", {"validation_id": "check-5", "issues": 1}),
    ]


async def test_rules_that_are_configured_but_not_installed_are_left_out(
    tmp_path: Path, checking: tuple[IfcGraphService, Graph, Log], monkeypatch: pytest.MonkeyPatch
) -> None:
    service, graph, _ = checking
    service.settings = make_settings(tmp_path, ifcgraph_enabled=True, ifcgraph_gherkin_env=str(tmp_path / "none"))
    commands: list[list[str]] = []

    async def answer(command: list[str], what: str, answers: tuple[int, ...] = (0,)) -> str:
        commands.append(command)
        return json.dumps(SCHEMA_ANSWER)

    monkeypatch.setattr(service, "_in_a_process", answer)
    await service._validate("check-6", "documents/x", "model.ifc")
    assert [command[2] for command in commands] == ["ifc_lpg.validation"]
    assert [check["name"] for check in json.loads(graph.writes[-1][1]["fields"]["checks"])] == ["schema"]


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
