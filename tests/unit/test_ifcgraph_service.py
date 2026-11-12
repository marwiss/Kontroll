# This file was generated with the assistance of an AI coding tool.
"""The check of an upload, without a database or IfcOpenShell: what it stores, and what it logs."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from ifc_lpg.validation import pack_report, unpack_report

from opencde.ids import new_id
from opencde.ifcgraph import service as service_module
from opencde.ifcgraph.service import IfcGraphService
from opencde.storage import LocalStorage, make_key
from tests.conftest import test_settings as make_settings  # aliased so pytest does not collect it as a test

# An environment made with `python -m ifc_lpg.gherkin_install`, for the test with buildingSMART's rules.
GHERKIN_ENV = os.environ.get("OPENCDE_TEST_GHERKIN_ENV", "")
# What an issue may carry: a line of the uploaded file, which the log is not to have.
LINE = "#9=IFCWALL('0KhR8hr7H8eewFRKm6V1bJ',#5,'what an owner history may hold',$,$,$,$,$,.NOSUCHWALL.);"


class Graph:
    """Answers the claim of a queued check and keeps every write."""

    def __init__(self) -> None:
        self.writes: list[tuple[str, dict[str, Any]]] = []

    async def run(self, query: str, **params: Any) -> list[dict[str, Any]]:
        self.writes.append((query, params))
        return [{"id": params["id"]}] if "SET r.state = $running" in query else []

    async def one(self, query: str, **params: Any) -> dict[str, Any] | None:
        """The project of the check (``_project_of``), as an upload has one."""
        return {"of_version": "project-1", "of_precheck": None}


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
        if command[2] == "opencde.ifcgraph.elements":
            asked = await asyncio.to_thread(Path(command[4]).read_text, encoding="utf-8")
            assert json.loads(asked) == [99], "only the rules' instances"
            return json.dumps({"elements": {"99": {"ifc_class": "IfcCartesianPoint", "root_global_id": None}}})
        return json.dumps(SCHEMA_ANSWER)

    monkeypatch.setattr(service, "_in_a_process", answer)
    await service._validate("check-4", "documents/x", "model.ifc")

    fields = graph.writes[-1][1]["fields"]
    assert fields["issue_count"] == 2 and fields["error_count"] == 1 and fields["truncated"] is False
    assert fields["ruleset"] == "IfcOpenShell 0.9.0 (IFC4); ifc-gherkin-rules 893f827 with IfcOpenShell 0.8.6"
    assert [check["name"] for check in json.loads(fields["checks"])] == ["schema", "gherkin"]
    assert json.loads(fields["checks"])[1]["rules_not_run"] == not_run
    assert unpack_report(fields["report"]) == [SCHEMA_ANSWER["issues"][0], {**found, "ifc_class": "IfcCartesianPoint"}]
    assert log.events == [("ifc_validation_done", {"validation_id": "check-4", "issues": 2})]


# What `python -m ifc_lpg.gherkin` answered on the file of `test_ifcgraph_elements.broken`, recorded on 2026-11-12 with
# ifc-gherkin-rules 893f827 and IfcOpenShell 0.8.6, as `gherkin_install` makes them: GEM111 names the polyline, which has
# no GlobalId, and GEM004 could not run (its tables are looked for where this environment does not keep them).
GEM111_ANSWER = {
    "ruleset": "ifc-gherkin-rules 893f827 with IfcOpenShell 0.8.6",
    "issue_count": 1,
    "error_count": 1,
    "truncated": False,
    "issues": [
        {
            "kind": "gherkin",
            "rule": "GEM111",
            "severity": "error",
            "message": "GEM111 - No duplicated points within a polyloop or polyline. Agreement on no duplicated points "
            'within a polyline. It must have no duplicate points excluding first and last point. Expected: "It must '
            'have no duplicate points excluding first and last point". Observed: {"value": [[8599.33565217, -300.0], '
            "[8599.33565217, -300.0]]}",
            "step_id": 202,
            "global_id": None,
            "attribute": None,
        }
    ],
    "rules_not_run": [{"rule": "GEM004", "error": "FileNotFoundError"}],
}


def gem111(tmp_path: Path, service: IfcGraphService, monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("ifcopenshell", reason="the ifc-lpg extra is not installed")
    from tests.unit.test_ifcgraph_elements import broken

    path = broken(tmp_path)
    monkeypatch.setattr(service, "_prepare_input", lambda key, name, workdir: path)


async def test_a_rules_finding_names_the_element_its_instance_is_in(
    tmp_path: Path, checking: tuple[IfcGraphService, Graph, Log], monkeypatch: pytest.MonkeyPatch
) -> None:
    service, graph, log = checking
    with_rules(tmp_path, service)
    gem111(tmp_path, service, monkeypatch)
    workers: list[str] = []

    async def answer(command: list[str], what: str, answers: tuple[int, ...] = (0,)) -> str:
        workers.append(command[2])
        if command[2] == "ifc_lpg.gherkin":
            return json.dumps(GEM111_ANSWER)
        if command[2] == "opencde.ifcgraph.elements":  # the real worker, on the file
            done = await asyncio.to_thread(subprocess.run, command, capture_output=True, text=True, check=False)
            assert done.returncode == 0, done.stderr
            return done.stdout
        return json.dumps({**SCHEMA_ANSWER, "issue_count": 0, "error_count": 0, "issues": []})

    monkeypatch.setattr(service, "_in_a_process", answer)
    await service._validate("check-9", "documents/x", "gem111.ifc")

    assert workers == ["ifc_lpg.validation", "ifc_lpg.gherkin", "opencde.ifcgraph.elements"]
    [finding] = unpack_report(graph.writes[-1][1]["fields"]["report"])
    assert finding == {
        **GEM111_ANSWER["issues"][0],
        "ifc_class": "IfcPolyline",
        "root_global_id": "1Xezbq735AdBO_4DerG66G",  # the wall whose body's outline it is
    }
    assert finding["global_id"] is None, "global_id stays the instance's own, so that a trial's base still matches"
    assert log.events == [("ifc_validation_done", {"validation_id": "check-9", "issues": 1})]


async def test_when_the_elements_cannot_be_read_the_findings_stay_as_the_rules_gave_them(
    tmp_path: Path, checking: tuple[IfcGraphService, Graph, Log], monkeypatch: pytest.MonkeyPatch
) -> None:
    service, graph, log = checking
    with_rules(tmp_path, service)

    async def answer(command: list[str], what: str, answers: tuple[int, ...] = (0,)) -> str:
        if command[2] == "ifc_lpg.gherkin":
            return json.dumps(GEM111_ANSWER)
        if command[2] == "opencde.ifcgraph.elements":
            raise RuntimeError(f"could not read {LINE}")
        return json.dumps(SCHEMA_ANSWER)

    monkeypatch.setattr(service, "_in_a_process", answer)
    await service._validate("check-10", "documents/x", "model.ifc")

    assert unpack_report(graph.writes[-1][1]["fields"]["report"])[1] == GEM111_ANSWER["issues"][0]
    assert log.events == [
        ("ifc_elements_failed", {"error": "RuntimeError"}),
        ("ifc_validation_done", {"validation_id": "check-10", "issues": 2}),
    ]


@pytest.mark.skipif(not GHERKIN_ENV, reason="OPENCDE_TEST_GHERKIN_ENV names no environment for ifc-gherkin-rules")
async def test_the_installed_rules_give_the_recorded_answer(tmp_path: Path) -> None:
    pytest.importorskip("ifcopenshell", reason="the ifc-lpg extra is not installed")
    from tests.unit.test_ifcgraph_elements import broken

    command = [sys.executable, "-m", "ifc_lpg.gherkin", str(broken(tmp_path)), "--env", GHERKIN_ENV]
    done = await asyncio.to_thread(subprocess.run, command, capture_output=True, text=True, check=False)
    assert done.returncode == 1, done.stderr
    assert json.loads(done.stdout.strip().splitlines()[-1]) == GEM111_ANSWER


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


IDS_DOCUMENTS = [
    {"document_id": "ids-a", "version_index": 2, "title": "Walls for reuse", "storage_key": "documents/ids-a-2"},
    {"document_id": "ids-b", "version_index": 1, "title": "Broken", "storage_key": "documents/ids-b-1"},
]
IDS_FOUND = {
    "kind": "ids",
    "rule": "Walls have a fire rating",
    "severity": "error",
    "message": f"Walls have a fire rating: {LINE}",
    "step_id": 9,
    "global_id": "0KhR8hr7H8eewFRKm6V1bJ",
    "attribute": None,
    "ids": 0,
}
IDS_SPECIFICATION = {
    "ids": 0,
    "title": "the IDS's own title",
    "name": "Walls have a fire rating",
    "identifier": None,
    "usage": "optional",
    "ifc_versions": ["IFC4"],
    "for_this_schema": True,
    "status": "failed",
    "applicable": 3,
    "issues": 1,
}


def with_ids_documents(service: IfcGraphService, monkeypatch: pytest.MonkeyPatch) -> None:
    async def documents(validation_id: str) -> list[dict[str, Any]]:
        return IDS_DOCUMENTS

    monkeypatch.setattr(service, "_ids_documents", documents)


async def test_the_projects_ids_documents_join_the_report(
    tmp_path: Path, checking: tuple[IfcGraphService, Graph, Log], monkeypatch: pytest.MonkeyPatch
) -> None:
    service, graph, log = checking
    with_ids_documents(service, monkeypatch)
    commands: list[list[str]] = []

    async def answer(command: list[str], what: str, answers: tuple[int, ...] = (0,)) -> str:
        commands.append(command)
        if command[2] == "ifc_lpg.ids":
            assert answers == (0, 1), "a specification that fails is an answer, not a failure"
            return json.dumps(
                {
                    "ruleset": "IfcTester 0.9.0: IDS 1.0",
                    "issue_count": 1,
                    "error_count": 1,
                    "truncated": False,
                    "issues": [IDS_FOUND],
                    "rules_not_run": [{"rule": "IDS 2", "ids": 1, "error": "it has a DTD or an entity"}],
                    "specifications": [IDS_SPECIFICATION],
                }
            )
        return json.dumps(SCHEMA_ANSWER)

    monkeypatch.setattr(service, "_in_a_process", answer)
    await service._validate("check-7", "documents/x", "model.ifc")

    (ids_command,) = [command for command in commands if command[2] == "ifc_lpg.ids"]
    stored_files = [str(service.storage.path(document["storage_key"])) for document in IDS_DOCUMENTS]
    assert ids_command[ids_command.index("--") + 1 :] == [str(tmp_path / "model.ifc"), *stored_files], (
        "the worker gets the paths the server made, and nothing of a document's name"
    )
    fields = graph.writes[-1][1]["fields"]
    assert fields["issue_count"] == 2 and fields["error_count"] == 2
    assert fields["ruleset"] == "IfcOpenShell 0.9.0 (IFC4); IfcTester 0.9.0: IDS 1.0"
    ids = json.loads(fields["checks"])[1]
    assert (ids["name"], ids["state"], ids["issue_count"]) == ("ids", "done", 1)
    assert ids["documents"] == [
        {"document_id": "ids-a", "version_index": 2, "title": "Walls for reuse"},
        {"document_id": "ids-b", "version_index": 1, "title": "Broken"},
    ]
    assert ids["rules_not_run"] == [{"rule": "Broken", "error": "it has a DTD or an entity", "document_id": "ids-b"}]
    expected = {key: value for key, value in IDS_SPECIFICATION.items() if key not in ("ids", "title")}
    assert ids["specifications"] == [{**expected, "document_id": "ids-a"}]
    stored = unpack_report(fields["report"])[1]
    assert stored["document_id"] == "ids-a" and "ids" not in stored and stored["kind"] == "ids"
    assert log.events == [("ifc_validation_done", {"validation_id": "check-7", "issues": 2})]


async def test_when_the_ids_check_cannot_run_the_others_stand(
    checking: tuple[IfcGraphService, Graph, Log], monkeypatch: pytest.MonkeyPatch
) -> None:
    service, graph, log = checking
    with_ids_documents(service, monkeypatch)

    async def answer(command: list[str], what: str, answers: tuple[int, ...] = (0,)) -> str:
        if command[2] == "ifc_lpg.ids":
            raise RuntimeError(f"IfcTester stopped at {LINE}")
        return json.dumps(SCHEMA_ANSWER)

    monkeypatch.setattr(service, "_in_a_process", answer)
    await service._validate("check-8", "documents/x", "model.ifc")

    fields = graph.writes[-1][1]["fields"]
    assert graph.writes[-1][1]["state"] == "done" and fields["issue_count"] == 1
    assert fields["ruleset"] == "IfcOpenShell 0.9.0 (IFC4)", "only the checks that ran"
    ids = json.loads(fields["checks"])[1]
    assert (ids["name"], ids["state"], ids["issue_count"]) == ("ids", "failed", 0)
    assert ids["ruleset"].startswith("IfcTester") and [d["document_id"] for d in ids["documents"]] == ["ids-a", "ids-b"]
    assert log.events == [
        ("ifc_ids_failed", {"error": "RuntimeError"}),
        ("ifc_validation_done", {"validation_id": "check-8", "issues": 1}),
    ]


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


# -- the trial of a change set with Dataspatium's write tools (``ops``) ------------------------------------------

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "three_walls_gtin.ifc"
NEW_WALL = {"tool": "create_wall", "start": [0, 0], "end": [4, 0], "name": "New"}


class Versions:
    """The versions of one document as the trial asks for them: the base by its index, and the latest."""

    def __init__(self, keys: dict[int, str]) -> None:
        self.keys = keys
        self.asked: list[int] = []

    async def run(self, query: str, **params: Any) -> list[dict[str, Any]]:
        return []  # no teams, no IDS documents

    async def one(self, query: str, **params: Any) -> dict[str, Any] | None:
        if "max(v.version_index)" in query:
            return {"latest": max(self.keys)}
        self.asked.append(int(params["version_index"]))
        key = self.keys.get(int(params["version_index"]))
        row = {"storage_key": key, "file_name": "walls.ifc", "base_report": pack_report([]), "base_checks": None}
        return row if key else None


@pytest.fixture
def trying(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[IfcGraphService, Versions, LocalStorage]:
    """A service whose apply worker is the real one, in a process of its own, and whose checks find nothing."""
    pytest.importorskip("ifcopenshell", reason="the ifc-lpg extra is not installed")
    storage = LocalStorage(tmp_path / "storage")
    keys = {index: make_key("documents", new_id(), "ifc") for index in (1, 2)}
    for key in keys.values():
        storage.write_bytes(key, FIXTURE.read_bytes())
    versions = Versions(keys)
    service = IfcGraphService(versions, storage, make_settings(tmp_path, ifcgraph_enabled=True))

    async def in_a_process(command: list[str], what: str, answers: tuple[int, ...] = (0,)) -> str:
        if "opencde.ifcgraph.apply" not in command:
            return json.dumps({"ruleset": "IfcOpenShell x", "issue_count": 0, "truncated": False, "issues": []})
        done = await asyncio.to_thread(subprocess.run, command, capture_output=True, text=True, check=False)
        assert done.returncode == 0, done.stderr
        return done.stdout

    monkeypatch.setattr(service, "_in_a_process", in_a_process)
    return service, versions, storage


def snippet(storage: LocalStorage, **fields: Any) -> str:
    change_set = {"base": {"document_id": "d" * 36, "version_index": 1}, "provenance": {"user": "anna"}, **fields}
    key = make_key("snippets", new_id(), "bin")
    storage.write_bytes(key, json.dumps(change_set).encode("utf-8"))
    return key


async def test_a_trial_applies_the_operations_and_says_what_they_created(
    trying: tuple[IfcGraphService, Versions, LocalStorage], monkeypatch: pytest.MonkeyPatch
) -> None:
    service, versions, storage = trying
    touching: list[dict[str, Any]] = []

    async def parts(project_id: str, base: Path, changed: Path, changes: Path) -> tuple[list[Any], None]:
        touching.extend(json.loads(await asyncio.to_thread(changes.read_text, encoding="utf-8"))["changes"])
        return [], None

    monkeypatch.setattr(service, "_parts_touched", parts)
    rename = {"guid": "3eT96F_cnDsOufCEsotwtp", "attribute": "Name", "op": "set", "new": "YVT-B2"}
    key = snippet(storage, ops_form="dataspatium-tools/1", ops=[NEW_WALL, NEW_WALL], changes=[rename])
    fields = await service._try_proposal(new_id(), "project-1", key, author="anna")
    assert fields["state"] == "clean" and unpack_report(fields["report"]) == []
    assert (fields["change_count"], fields["applied"]) == (3, 3), "two operations and one change"
    created = json.loads(fields["created"])
    assert list(created) == ["new-1", "new-2"] and json.loads(fields["notes"]) == [
        "IsExternal was left out on the walls of storey 1. etasje that the change set made or changed, and on their "
        "doors and windows: 8 wall ends stand open, so the app cannot tell outside from inside"
    ], "the new walls stand alone, so the topology tells no outside"
    assert set(created.values()) <= set(json.loads(fields["ops_objects"]))
    assert {"guid": created["new-1"]} in touching and rename in touching, "a team's part is touched by either"
    assert versions.asked == [1], "tried on the base it names"


async def test_an_operation_that_fails_is_an_issue_of_kind_op(
    trying: tuple[IfcGraphService, Versions, LocalStorage],
) -> None:
    service, _versions, storage = trying
    nowhere = {**NEW_WALL, "storey": "Level 9"}
    key = snippet(storage, ops_form="dataspatium-tools/1", ops=[NEW_WALL, nowhere], changes=[])
    fields = await service._try_proposal(new_id(), "project-1", key, author="anna")
    assert fields["state"] == "issues" and (fields["change_count"], fields["applied"]) == (2, 1)
    assert unpack_report(fields["report"]) == [
        {
            "kind": "op",
            "severity": "error",
            "message": "op 1 (create_wall): no storey named 'Level 9'; the storeys are 1. etasje",
            "op": 1,
            "tool": "create_wall",
        }
    ]


async def test_a_change_set_that_keeps_theirs_is_tried_on_the_latest_version(
    trying: tuple[IfcGraphService, Versions, LocalStorage],
) -> None:
    service, versions, storage = trying
    keep = ["1Xezbq735AdBO_4DerG66G/.Name", "#999999.Name"]
    key = snippet(storage, ops_form="dataspatium-tools/1", ops=[NEW_WALL], changes=[], keep_theirs=keep)
    proposal_id = new_id()
    fields = await service._try_proposal(proposal_id, "project-1", key, author="anna")
    assert versions.asked == [2] and fields["base_version_index"] == 2, "the latest, not the base it names"
    assert [issue["message"] for issue in unpack_report(fields["report"])] == ["keep_theirs 1: no instance #999999"], (
        "a key that names nothing in the latest version"
    )
    retried = await service._try_proposal(proposal_id, "project-1", key, base_version_index=1, author="anna")
    assert versions.asked == [2, 1] and retried["base_version_index"] == 1, "the approval's merge names its own"
