# This file was generated with the assistance of an AI coding tool.
"""The rooms of each storey in the reports, with the worker stubbed (F36 a, the server makes the client's room check;
F38 a, the rooms only warn): the section beside the issues of an upload, a precheck and a trial, never one of them,
so that neither a status nor a trial's state depends on it; a worker that fails leaves it out with the reason logged,
never the file's words; off by default; the reports' models; and the version's page. The worker itself is tried in
``test_ifc_topology.py``, and the flow against a database in ``tests/integration/test_ifc_rooms.py``."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from ifc_lpg.validation import pack_report, unpack_report

from opencde.bcf.routes_proposals import proposal_report
from opencde.documents.routes_precheck import _report as precheck_report
from opencde.documents.validation import Validation, report
from opencde.ids import new_id
from opencde.ifcgraph import service as service_module
from opencde.ifcgraph.service import IfcGraphService
from opencde.storage import LocalStorage, make_key
from opencde.ui.templating import render
from tests.conftest import test_settings as make_settings  # aliased so pytest does not collect it as a test
from tests.security.test_prompt_injection import _contexts, _request
from tests.unit.test_ifcgraph_service import SCHEMA_ANSWER, Graph, Log

NOW = "2026-11-12T10:00:00.000Z"
WALLS = ["2O2Fr$t4X7Zf8NOew3FLOH", "1Xezbq735AdBO_4DerG66G", "3eT96F_cnDsOufCEsotwtp", "0KhR8hr7H8eewFRKm6V1bJ"]
STUB = "3k3LbXmTfDWODxdSuyCGYE"
# An open storey: one room of 10 by 6 m, and a wall that dangles into it.
ROOMS = {
    "storeys": [
        {
            "storey": "Level 1",
            "elevation": 0.0,
            "closed": False,
            "rooms": [{"index": 1, "area": 60.0, "perimeter": 32.0, "walls": sorted(WALLS), "neighbours": []}],
            "external": [{"global_id": WALLS[0], "name": "South", "facing": "S", "length": 10.0}],
            "dangles": [[5.0, 2.0]],
            "dangling_walls": [STUB],
            "walls": 5,
            "unread": 0,
            "unread_walls": [],
            "tolerance": 0.15,
            "north": "model",
        },
        {
            "storey": "Roof",
            "elevation": 3.5,
            "closed": False,
            "rooms": [],
            "external": [],
            "dangles": [],
            "dangling_walls": [],
            "walls": 0,
            "unread": 0,
            "unread_walls": [],
            "tolerance": 0.15,
            "north": "model",
        },
    ],
    "cut": False,
}


@pytest.fixture
def checking(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[IfcGraphService, Graph, Log]:
    graph = Graph()
    log = Log()
    service = IfcGraphService(
        graph, LocalStorage(tmp_path), make_settings(tmp_path, ifcgraph_enabled=True, rooms_enabled=True)
    )
    monkeypatch.setattr(service_module, "log", log)
    monkeypatch.setattr(service, "_prepare_input", lambda key, name, workdir: tmp_path / "model.ifc")
    return service, graph, log


def answering(rooms: Any, commands: list[list[str]]) -> Any:
    """The workers: the schema's check, and the topology answering ``rooms``, or raising it."""

    async def answer(command: list[str], what: str, answers: tuple[int, ...] = (0,)) -> str:
        commands.append(command)
        if command[2] == "opencde.ifcgraph.topology":
            assert answers == (0,) and command[-2:] == ["--memory-mb", "4096"], "the limits of every worker"
            if isinstance(rooms, Exception):
                raise rooms
            return json.dumps(rooms) + "\n"
        return json.dumps(SCHEMA_ANSWER)

    return answer


async def test_the_rooms_are_a_section_of_the_report_and_change_none_of_its_counts(
    tmp_path: Path, checking: tuple[IfcGraphService, Graph, Log], monkeypatch: pytest.MonkeyPatch
) -> None:
    service, graph, log = checking
    commands: list[list[str]] = []
    monkeypatch.setattr(service, "_in_a_process", answering(ROOMS, commands))
    await service._validate("check-1", "documents/x", "model.ifc")
    await service.shutdown()

    assert commands[-1][2:4] == ["opencde.ifcgraph.topology", str(tmp_path / "model.ifc")], "after the checks"
    assert graph.writes[-1][1]["state"] == "done"
    fields = graph.writes[-1][1]["fields"]
    assert json.loads(fields["rooms"]) == ROOMS
    assert (fields["issue_count"], fields["error_count"]) == (1, 1), "the schema's error alone: an open storey is none"
    assert [check["name"] for check in json.loads(fields["checks"])] == ["schema"], "nor a check of its own"
    assert [issue["kind"] for issue in unpack_report(fields["report"])] == ["schema"]
    assert log.events == [("ifc_validation_done", {"validation_id": "check-1", "issues": 1})]
    checked = await service.check_now(project_id="project-1", storage_key="documents/x", file_name="model.ifc")
    assert checked is not None and json.loads(checked["rooms"]) == ROOMS, "and before a version, for a refusal"


@pytest.mark.parametrize(
    ("failure", "logged"),
    [
        (RuntimeError(f"stopped at {SCHEMA_ANSWER['issues'][0]['message']}"), "RuntimeError"),
        ({"error": "the topology reads at most 2000 walls; there are 2400"}, None),
        ({"storeys": [{"storey": SCHEMA_ANSWER["issues"][0]["message"]}], "cut": False}, "ValidationError"),
    ],
    ids=["stopped", "refused", "malformed"],
)
async def test_rooms_that_cannot_be_found_are_left_out_with_the_reason_logged(
    checking: tuple[IfcGraphService, Graph, Log], monkeypatch: pytest.MonkeyPatch, failure: Any, logged: str | None
) -> None:
    service, graph, log = checking
    monkeypatch.setattr(service, "_in_a_process", answering(failure, []))
    await service._validate("check-2", "documents/x", "model.ifc")
    await service.shutdown()
    fields = graph.writes[-1][1]["fields"]
    assert graph.writes[-1][1]["state"] == "done" and fields["issue_count"] == 1, "the file is checked all the same"
    assert "rooms" in fields and fields["rooms"] is None, "none are kept"
    reason = logged or failure["error"]
    assert log.events == [
        ("ifc_rooms_failed", {"error": reason}),
        ("ifc_validation_done", {"validation_id": "check-2", "issues": 1}),
    ]
    assert "owner history" not in json.dumps(log.events), "what the file says stays out of the log"


async def test_off_by_default_no_worker_finds_the_rooms(
    tmp_path: Path, checking: tuple[IfcGraphService, Graph, Log], monkeypatch: pytest.MonkeyPatch
) -> None:
    service, graph, _ = checking
    service.settings = make_settings(tmp_path, ifcgraph_enabled=True)
    commands: list[list[str]] = []
    monkeypatch.setattr(service, "_in_a_process", answering(ROOMS, commands))
    await service._validate("check-3", "documents/x", "model.ifc")
    assert [command[2] for command in commands] == ["ifc_lpg.validation"]
    assert "rooms" not in graph.writes[-1][1]["fields"]


class TrialGraph:
    """The base version of a trial with or without a report of its own, and nothing else in the project."""

    def __init__(self, base_report: str | None) -> None:
        self.row = {
            "storage_key": "documents/base.ifc",
            "file_name": "base.ifc",
            "base_report": base_report,
            "base_checks": None,
        }

    async def one(self, query: str, **params: Any) -> dict[str, Any] | None:
        return self.row if "base_report" in query else None

    async def run(self, query: str, **params: Any) -> list[dict[str, Any]]:
        return []


@pytest.mark.parametrize("base_report", [pack_report([]), None], ids=["base checked", "base not checked"])
async def test_a_trial_keeps_the_rooms_of_the_applied_file_and_its_state_never_depends_on_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, base_report: str | None
) -> None:
    storage = LocalStorage(tmp_path / "storage")
    snippet = make_key("snippets", new_id(), "json")
    storage.write_bytes(snippet, json.dumps({"base": {"document_id": "doc-1", "version_index": 1}}).encode())
    settings = make_settings(tmp_path, ifcgraph_enabled=True, rooms_enabled=True)
    service = IfcGraphService(TrialGraph(base_report), storage, settings)  # type: ignore[arg-type]
    monkeypatch.setattr(service, "_prepare_input", lambda key, name, workdir: tmp_path / name)
    read: list[str] = []

    async def answer(command: list[str], what: str, answers: tuple[int, ...] = (0,)) -> str:
        if command[2] == "opencde.ifcgraph.apply":
            await asyncio.to_thread(Path(command[5]).write_bytes, b"ISO-10303-21;")  # the changed file
            return json.dumps({"count": 1, "applied": 1, "problems": []})
        if command[2] == "opencde.ifcgraph.topology":
            read.append(Path(command[3]).name)
            return json.dumps(ROOMS)
        return json.dumps({**SCHEMA_ANSWER, "issue_count": 0, "error_count": 0, "issues": []})

    monkeypatch.setattr(service, "_in_a_process", answer)
    fields = await service._try_proposal(new_id(), "project-1", snippet)
    await service.shutdown()
    assert fields["state"] == "clean" and fields["issue_count"] == 0, "an open storey stops nothing (F38 a)"
    assert json.loads(fields["rooms"]) == ROOMS
    assert read == ["proposal.ifc"], "the applied file's rooms, and never the base's"


def test_the_reports_give_the_rooms_beside_the_issues(tmp_path: Path) -> None:
    validation = Validation(state="done", issue_count=1, error_count=1, checked_at=NOW, rooms=ROOMS)
    body = report(validation).model_dump(exclude_none=True)
    assert body["rooms"] == ROOMS and body["status"] == "issues", "the status is the issues' alone"
    assert "rooms" not in report(Validation(state="done", issue_count=0)).model_dump(exclude_none=True)
    assert [storey["storey"] for storey in validation.room_storeys] == ["Level 1"], "the page lists storeys with walls"

    trial = proposal_report({"state": "clean", "created_at": NOW, "checks": [], "issues": [], "rooms": ROOMS})
    assert trial.state == "clean" and trial.rooms is not None and trial.rooms.storeys[0].dangling_walls == [STUB]
    assert proposal_report({"state": "clean", "created_at": NOW, "checks": [], "issues": []}).rooms is None

    node = {
        "id": new_id(),
        "project_id": new_id(),
        "file_name": "model.ifc",
        "created_at": NOW,
        "expires_at": NOW,
        "state": "done",
        "issue_count": 0,
        "issues": [],
        "checks": [],
        "rooms": ROOMS,
    }
    precheck = precheck_report(make_settings(tmp_path), node)
    assert precheck.rooms is not None and precheck.rooms.model_dump() == ROOMS


class NodeGraph:
    """A precheck or a trial as the graph keeps them: the section as JSON text."""

    async def one(self, query: str, **params: Any) -> dict[str, Any] | None:
        return {"node": {"state": "done", "report": pack_report([]), "checks": "[]", "rooms": json.dumps(ROOMS)}}


async def test_the_kept_section_is_read_back_for_the_precheck_and_the_trial(tmp_path: Path) -> None:
    service = IfcGraphService(NodeGraph(), LocalStorage(tmp_path), make_settings(tmp_path, ifcgraph_enabled=True))  # type: ignore[arg-type]
    precheck = await service.precheck(user_id="u", project_id="p", precheck_id="c")
    trial = await service.proposal(user_id="u", project_id="p", topic_guid="t")
    assert precheck is not None and trial is not None and precheck["rooms"] == trial["rooms"] == ROOMS


def test_the_versions_page_lists_the_storeys_with_walls_briefly(tmp_path: Path) -> None:
    """The page shows a row a storey with walls: its rooms, whether it is closed, its open ends and its walls."""
    validation = Validation(state="done", issue_count=0, rooms=ROOMS)
    context = {**_contexts("x")["documents/details.html"], "validation": validation, "validation_issues": []}
    html = render(_request(make_settings(tmp_path)), "documents/details.html", context).body.decode("utf-8")
    (card,) = [part for part in html.split('<section class="card">') if "<h2>Rooms</h2>" in part]
    assert "<td>Level 1</td>" in card and "<td>Open</td>" in card and "Open ends" in card
    assert "Roof" not in card, "a storey without walls is left out"
