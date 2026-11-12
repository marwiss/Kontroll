# This file was generated with the assistance of an AI coding tool.
"""The server's own records on the store and IFC-LPG's models on the IFC graph (ADR 0027): the IFC-LPG service and
the merge with two stand-in graphs, each of which keeps every statement, so that a statement that lands on the wrong
one shows by the labels it names."""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from ifc_db.graph import UNIQUE as LIBRARY_UNIQUE
from ifc_db.validation import pack_report

from opencde.graph.schema import EXPIRING_LABELS, UNIQUE
from opencde.ids import new_id
from opencde.ifcgraph import merging
from opencde.ifcgraph import service as service_module
from opencde.ifcgraph.maintenance import delete_project, prune_models
from opencde.ifcgraph.service import IfcGraphService
from opencde.storage import LocalStorage, make_key
from opencde.store.accounts.projects import ProjectRepository
from tests.conftest import test_settings as make_settings

LIBRARY_LABELS = {label for label, _ in LIBRARY_UNIQUE}  # Model, Entity, StepBlock, Object
SERVER_LABELS = {label for label, _ in UNIQUE} | {"Precheck", "Proposal", "Clash", "Merge", "Team", "Component"}
_LABEL = re.compile(r":([A-Z][a-z][A-Za-z]*)\b")  # a node label; a relationship type is upper case throughout
GUID = "0KhR8hr7H8eewFRKm6V1bJ"


class Recording:
    """A graph that keeps every statement and answers with the rows of the first fragment the statement contains."""

    def __init__(self, name: str, answers: list[tuple[str, list[dict[str, Any]]]] | None = None) -> None:
        self.name = name
        self.answers = answers or []
        self.statements: list[str] = []

    async def run(self, query: str, /, **params: Any) -> list[dict[str, Any]]:
        self.statements.append(query)
        for fragment, rows in self.answers:
            if fragment in query:
                return [dict(row) for row in rows]
        return []

    async def one(self, query: str, /, **params: Any) -> dict[str, Any] | None:
        rows = await self.run(query, **params)
        return rows[0] if rows else None

    async def write(self, work: Any) -> Any:
        return await work(self)  # the transaction is the graph itself

    async def counters(self, query: str, /, **params: Any) -> SimpleNamespace:
        self.statements.append(query)
        return SimpleNamespace(nodes_deleted=1)

    def labels(self) -> set[str]:
        return {label for statement in self.statements for label in _LABEL.findall(statement)}


def assert_apart(ifc: Recording, store: Recording) -> None:
    """Every statement over the server's own nodes ran on the store, and the IFC graph had only the library's."""
    assert store.statements, "the store was asked"
    assert not store.labels() & LIBRARY_LABELS, f"the store was asked about the models: {store.labels()}"
    foreign = {label for label in ifc.labels() if label not in LIBRARY_LABELS and not label.startswith("Ifc")}
    assert not foreign, f"the IFC graph was asked about the server's own nodes: {foreign}"
    assert not ifc.labels() & SERVER_LABELS


async def answer(command: list[str], what: str, answers: tuple[int, ...] = (0,)) -> str:
    """The workers, without IfcOpenShell: a clean check, a conversion's header, an applied change set and a clash
    check that finds nothing."""
    module = command[2]
    if module == "ifc_db.worker":
        return json.dumps({"schema": "IFC4", "entities": 1})
    if module == "opencde.ifcgraph.apply":
        await asyncio.to_thread(Path(command[5]).write_bytes, b"ISO-10303-21;")  # the changed file
        return json.dumps({"count": 1, "applied": 1, "problems": []})
    if module == "opencde.ifcgraph.clash":
        report = {"clashes": [], "count": 0, "set_a": 1, "set_b": 1, "missing": 0, "seconds": 0.1, "truncated": False}
        return json.dumps(report)
    return json.dumps({"ruleset": "IfcOpenShell x", "issue_count": 0, "truncated": False, "issues": []})


def service_with(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    store_answers: list[tuple[str, list[dict[str, Any]]]],
    **settings: Any,
) -> tuple[IfcGraphService, Recording, Recording]:
    ifc, store = Recording("ifc"), Recording("store", store_answers)
    service = IfcGraphService(
        ifc,  # type: ignore[arg-type]
        LocalStorage(tmp_path / "storage"),
        make_settings(tmp_path, ifcgraph_enabled=True, ifcgraph_spatial=False, **settings),
        store=store,  # type: ignore[arg-type]
    )
    monkeypatch.setattr(service, "_in_a_process", answer)
    monkeypatch.setattr(service, "_prepare_input", lambda key, name, workdir: tmp_path / "model.ifc")
    monkeypatch.setattr(service, "_prepare_clash_input", lambda key, name, workdir: tmp_path / "model.ifc")
    return service, ifc, store


async def test_a_conversion_imports_into_the_ifc_graph_and_records_on_the_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, ifc, store = service_with(
        tmp_path,
        monkeypatch,
        [
            ("CREATE (v)-[:HAS_VALIDATION]", [{"id": "check-1"}]),
            ("SET r.state = $running", [{"id": "check-1"}]),
            ("RETURN p.project_id AS of_version", [{"of_version": "project-1", "of_precheck": None}]),
            ("SET c.state = $running", [{"id": "claimed"}]),
            ("RETURN properties(c) AS c", [{"c": {"project_id": "project-1", "document_id": "doc-1"}}]),
            ("RETURN DISTINCT c.ifc_guid AS guid", [{"guid": GUID}]),
        ],
    )
    given: list[tuple[str, Any]] = []

    async def importing(graph: Any, model_id: str, records: Path) -> dict[str, int]:
        given.append(("import_records", graph))
        return {"nodes": 1, "relationships": 0}

    async def values(reading: Any, model_id: str, **_: Any) -> list[dict[str, Any]]:
        given.append(("property_values", reading.graph))
        return [{"global_id": GUID, "value": "7310000000000"}]

    monkeypatch.setattr(service_module, "import_records", importing)
    monkeypatch.setattr(service_module, "property_values", values)
    model_id = await service.schedule(
        project_id="project-1",
        storage_key="documents/model.ifc",
        file_name="model.ifc",
        document_id="doc-1",
        version_index=1,
        version_id="version-1",
    )
    await service.wait_idle()

    assert model_id is not None
    assert given == [("import_records", ifc), ("property_values", ifc)], "the library's calls go to the IFC graph"
    assert any("unreachable" in s or ":Entity" in s for s in ifc.statements), "the graph check reads the model"
    written = "\n".join(store.statements)
    for made in ("HAS_CONVERSION", "HAS_VALIDATION", "SET c.state = $state", "SET c.gtin = gtin.gtin"):
        assert made in written, made
    assert_apart(ifc, store)


async def test_a_failed_conversion_tidies_the_ifc_graph_and_says_so_on_the_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, ifc, store = service_with(
        tmp_path, monkeypatch, [("SET c.state = $running", [{"id": "claimed"}])], ifcgraph_validate_uploads=False
    )

    async def broken(graph: Any, model_id: str, records: Path) -> dict[str, int]:
        raise RuntimeError("the import broke off")

    monkeypatch.setattr(service_module, "import_records", broken)
    await service.schedule(project_id="project-1", storage_key="documents/model.ifc", file_name="model.ifc")
    await service.wait_idle()

    assert any(":Entity" in s for s in ifc.statements), "what came in is taken out of the IFC graph"
    assert any("SET c.state = $state" in s for s in store.statements), "the record says failed"
    assert_apart(ifc, store)


async def test_a_precheck_and_its_report_live_on_the_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service, ifc, store = service_with(
        tmp_path,
        monkeypatch,
        [
            ("CREATE (p)-[:HAS_PRECHECK]", [{"id": "precheck-1"}]),
            ("SET r.state = $running", [{"id": "precheck-1"}]),
            ("RETURN p.project_id AS of_version", [{"of_version": None, "of_precheck": "project-1"}]),
            ("RETURN properties(r) AS node", [{"node": {"id": "precheck-1", "state": "done"}}]),
        ],
    )
    await service.schedule_precheck(
        precheck_id="precheck-1", project_id="project-1", storage_key="prechecks/x", file_name="x.ifc", author="anna"
    )
    await service.wait_idle()
    kept = await service.keep_as_precheck(
        project_id="project-1", storage_key="prechecks/y", file_name="y.ifc", author="anna", checked={"state": "done"}
    )
    found = await service.precheck(user_id="user-1", project_id="project-1", precheck_id="precheck-1")

    assert kept and found is not None and found["issues"] == []
    assert ifc.statements == [], "a check of a file never touches the IFC graph"
    assert_apart(ifc, store)


async def test_a_trial_and_its_approval_run_on_the_store_and_the_keys_on_the_ifc_graph(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    snippet = make_key("snippets", new_id(), "json")
    service, ifc, store = service_with(
        tmp_path,
        monkeypatch,
        [
            ("CREATE (t)-[:HAS_PROPOSAL]", [{"id": "proposal-1"}]),
            ("p.snippet_key AS snippet_key, p.author", [{"project_id": "p1", "snippet_key": snippet, "author": "a"}]),
            (
                "r.report AS base_report",
                [{"storage_key": "k", "file_name": "base.ifc", "base_report": pack_report([]), "base_checks": None}],
            ),
            ("RETURN p.snippet_key AS snippet_key", [{"snippet_key": snippet}]),
            ("RETURN properties(p) AS node", [{"node": {"id": "proposal-1", "state": "clean"}}]),
            ("RETURN properties(c) AS c", [{"c": {"id": "model-1"}}]),
        ],
    )
    change_set = {"base": {"document_id": "doc-1", "version_index": 1}, "changes": []}
    service.storage.write_bytes(snippet, json.dumps(change_set).encode("utf-8"))

    await service.schedule_proposal(project_id="p1", topic_guid="topic-1", snippet_key=snippet, author="anna")
    await service.wait_idle()
    proposal_id = new_id()  # it names the applied file in the storage
    assert await service.retry_proposal(proposal_id=proposal_id, base_version_index=1) == "clean"
    await service.approve(proposal_id=proposal_id, approved_by="manager", version_index=2)
    assert await service.proposal(user_id="u", project_id="p1", topic_guid="topic-1") is not None
    assert await service.change_set_of(project_id="p1", topic_guid="topic-1") == change_set
    assert await service.values_in(document_id="doc-1", version_index=1, changes=[]) is None
    assert not ifc.statements, "a trial reads files and the server's own nodes alone"
    change = {"guid": GUID, "path": "", "attribute": "Name"}
    keys = await service.canonical_keys(document_id="doc-1", version_index=1, changes=[change])

    assert keys == [f"{GUID}/.Name"], "a path that leads nowhere keeps the key its client wrote"
    assert ifc.statements, "the canonical path is looked up in the model"
    written = "\n".join(store.statements)
    for made in ("HAS_PROPOSAL", "HAS_TEAM", "SET p.state = $state", "DETACH DELETE p"):
        assert made in written, made
    assert_apart(ifc, store)


async def test_a_clash_check_runs_on_the_store_alone(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    request = {
        "a": {"document_id": "doc-a", "version_index": 1},
        "b": {"document_id": "doc-b", "version_index": 1},
        "mode": "intersection",
        "tolerance": 0.0,
        "clearance": 0.0,
    }
    service, ifc, store = service_with(
        tmp_path,
        monkeypatch,
        [
            ("MATCH (c:Clash {id: $id, state: $queued})", [{"project_id": "p1", "request": json.dumps(request)}]),
            ("RETURN v.storage_key AS storage_key", [{"storage_key": "documents/a.ifc", "file_name": "a.ifc"}]),
            ("RETURN properties(c) AS clash", [{"clash": {"id": "clash-1", "request": json.dumps(request)}}]),
        ],
    )
    await service.schedule_clash(project_id="p1", author="anna", request=request)
    await service.wait_idle()
    listed = await service.clash_reports(user_id="u", project_id="p1")
    one = await service.clash_report(user_id="u", project_id="p1", clash_id="clash-1", with_clashes=False)

    assert len(listed) == 1 and one is not None
    assert any("c.done_at = $now" in s for s in store.statements), "the report is kept on the store"
    assert ifc.statements == []
    assert_apart(ifc, store)


async def test_a_merge_runs_its_job_on_the_store_and_its_model_on_the_ifc_graph(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = {
        "base": {"model_id": "model-a", "document_id": "doc-a", "version_index": 1},
        "other": {"model_id": "model-b", "project_id": "p2", "document_id": "doc-b", "version_index": 1},
        "building": GUID,
    }
    service, ifc, store = service_with(
        tmp_path,
        monkeypatch,
        [
            (
                "MATCH (j:Merge {id: $id, state: $queued})",
                [{"project_id": "p1", "request": json.dumps(request), "author": "anna", "kind": "merge"}],
            ),
            ("ORDER BY v.version_index DESC LIMIT 1", [{"version_index": 1, "title": "A", "file_name": "a.ifc"}]),
            ("RETURN p.name AS name", [{"name": "Building permit"}]),
            ("WHERE j.expires_at <= $now", [{"id": "prepare-1", "model_id": "prepared-1"}]),
            ("RETURN properties(j) AS merge", [{"merge": {"id": "merge-1", "state": "done"}}]),
        ],
    )
    given: list[tuple[str, Any]] = []

    async def merge_building(graph: Any, *args: Any, **kwargs: Any) -> dict[str, Any]:
        given.append(("merge_building", graph))
        return {"model": args[3], "summary": {}}

    async def merge_report(graph: Any, *args: Any, **kwargs: Any) -> dict[str, Any]:
        given.append(("merge_report", graph))
        return {}

    async def export(model_id: str, target: Path) -> int:
        await asyncio.to_thread(target.write_bytes, b"ISO-10303-21;")
        return 1

    class Documents:
        def __init__(self, graph: Any) -> None:
            given.append(("DocumentRepository", graph))

        async def create_version(self, **fields: Any) -> SimpleNamespace:
            return SimpleNamespace(
                storage_key=fields["storage_key"],
                file_name=fields["file_name"],
                document_id=fields["document_id"],
                version_index=2,
                version_id="version-2",
            )

    async def schedule(**fields: Any) -> str:
        given.append(("schedule", fields["version_index"]))
        return "model-c"

    monkeypatch.setattr(merging, "merge_building", merge_building)
    monkeypatch.setattr(merging, "merge_report", merge_report)
    monkeypatch.setattr(merging, "DocumentRepository", Documents)
    monkeypatch.setattr(service, "export", export)
    monkeypatch.setattr(service, "schedule", schedule)

    await merging.report(service, request)
    await merging.schedule(service, project_id="p1", author="anna", request=request)
    await service.wait_idle()
    await merging.resume(service)
    assert await merging.job(service, user_id="u", project_id="p1", merge_id="merge-1") is not None

    assert given == [
        ("merge_report", ifc),
        ("merge_building", ifc),
        ("DocumentRepository", store),
        ("schedule", 2),
    ], "the library merges on the IFC graph; the version is the store's"
    dropped = [s for s in ifc.statements if s.startswith("MATCH (m:Model") and "DETACH DELETE m" in s]
    assert len(dropped) == 2, "the merged model and the expired preparation leave the IFC graph"
    written = "\n".join(store.statements)
    for made in ("HAS_MERGE", "SET j.state = $state", "WHERE j.expires_at <= $now"):
        assert made in written, made
    assert_apart(ifc, store)


async def test_the_resumption_after_a_stop_reads_the_store_and_tidies_the_ifc_graph(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, ifc, store = service_with(
        tmp_path,
        monkeypatch,
        [
            (
                "RETURN properties(c) AS c",
                [{"c": {"id": "model-9", "state": "running", "storage_key": "k", "file_name": "m.ifc"}}],
            ),
            ("RETURN p.id AS id, p.state AS state", [{"id": "proposal-9", "state": "running"}]),
            (
                "RETURN r.id AS id, r.storage_key",
                [{"id": "check-9", "state": "running", "storage_key": "k", "file_name": "m.ifc"}],
            ),
        ],
    )
    monkeypatch.setattr(service, "_start", lambda *args: None)
    monkeypatch.setattr(service, "_start_proposal", lambda *args: None)
    monkeypatch.setattr(service, "_start_validation", lambda *args: None)
    await service.resume_interrupted()

    assert any(":Entity" in s for s in ifc.statements), "the half-imported model leaves the IFC graph"
    written = "\n".join(store.statements)
    for asked in ("MATCH (p:Proposal)", "MATCH (r:Validation)", "MATCH (j:Merge)", "MATCH (c:Conversion)"):
        assert asked in written, asked
    assert_apart(ifc, store)


async def test_a_project_goes_with_its_models_from_the_ifc_graph_and_the_rest_from_the_store(tmp_path: Path) -> None:
    ifc = Recording("ifc")
    store = Recording("store", [("RETURN c.model_id AS id", [{"id": "model-1"}, {"id": "model-2"}])])
    projects = ProjectRepository(store)  # type: ignore[arg-type]

    assert await delete_project(projects, ifc, "project-1", LocalStorage(tmp_path))  # type: ignore[arg-type]

    removed = [s for s in ifc.statements if s.startswith("MATCH (m:Model") and "DETACH DELETE m" in s]
    assert len(removed) == 2, "both models leave the IFC graph"
    assert any("DETACH DELETE p" in s for s in store.statements), "the project leaves the store"
    assert_apart(ifc, store)


async def test_the_project_repository_never_asks_the_ifc_graph(tmp_path: Path) -> None:
    store = Recording("store", [("RETURN c.model_id AS id", [{"id": "model-1"}])])
    projects = ProjectRepository(store)  # type: ignore[arg-type]
    assert await projects.model_ids("project-1") == ["model-1"]
    assert await projects.delete_with_files("project-1", LocalStorage(tmp_path))
    assert not store.labels() & LIBRARY_LABELS, "the models are the caller's, in the other graph"


async def test_pruning_deletes_the_models_on_the_ifc_graph_and_their_records_on_the_store() -> None:
    ifc = Recording("ifc")
    store = Recording("store", [("RETURN properties(c) AS c", [{"c": {"id": "model-1", "project_id": "p1"}}])])

    done = await prune_models(ifc, store=store, project_id="p1", everything=True)  # type: ignore[arg-type]

    assert done == {"models": 1, "entities": 0}
    assert any(s.startswith("MATCH (m:Model") for s in ifc.statements)
    assert any("Conversion" in s and "DELETE" in s for s in store.statements), "the record goes from the store"
    assert_apart(ifc, store)


def test_nothing_that_expires_lives_on_the_ifc_graph() -> None:
    """The expiry cleaner runs on the store alone; the library's nodes carry no ``expires_at``, and a prepared model
    leaves the IFC graph through its ``Merge`` job, which is the store's (``merging.resume``)."""
    assert not set(EXPIRING_LABELS) & LIBRARY_LABELS
