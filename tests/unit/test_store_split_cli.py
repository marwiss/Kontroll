# This file was generated with the assistance of an AI coding tool.
"""The command line, the backup, the doctor and the readiness check with the server's own data in a graph of its
own (ADR 0027): two stand-in graphs, and which of them each command opens and asks."""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from opencde import backup as backups
from opencde import bootstrap, health
from opencde import seed as seeding
from opencde.admin import doctor
from opencde.cli import app
from opencde.graph.dialect import GraphDialect
from opencde.ifcgraph import service as service_module
from opencde.storage import LocalStorage
from tests.conftest import test_settings as make_settings
from tests.unit.test_store_split import Recording, assert_apart


class Graph(Recording):
    """A recording graph with what a connection has besides its statements."""

    def __init__(self, name: str, answers: list[tuple[str, list[dict[str, Any]]]] | None = None) -> None:
        super().__init__(name, answers)
        self.driver = name
        self.database = name
        self.dialect = SimpleNamespace(name=GraphDialect.NEO4J, list_constraints="SHOW CONSTRAINTS")
        self.closed = False

    async def close(self) -> None:
        self.closed = True

    async def schema_rows(self, statement: str) -> list[dict[str, Any]]:
        return [{}] * 100


@pytest.fixture
def two_graphs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Graph, Graph, list[str]]:
    """The IFC graph and a store of its own, as the command line's sessions open them; ``opened`` says which."""
    ifc = Graph("ifc", [("RETURN count(n) AS n", [{"n": 0}])])
    store = Graph(
        "store",
        [
            ("RETURN count(n) AS n", [{"n": 0}]),
            ("RETURN properties(c) AS c", [{"c": {"id": "model-1", "project_id": "p1", "state": "done"}}]),
        ],
    )
    opened: list[str] = []

    def make_graph(settings: Any) -> Graph:
        opened.append("ifc")
        return ifc

    def make_store(settings: Any) -> Graph:
        opened.append("store")
        return store

    async def nothing(*args: Any, **kwargs: Any) -> None:
        return None

    settings = make_settings(tmp_path, ifcgraph_enabled=True)
    monkeypatch.setattr("opencde.cli._settings", lambda: settings)
    monkeypatch.setattr(bootstrap, "make_graph", make_graph)
    monkeypatch.setattr(bootstrap, "make_store", make_store)
    monkeypatch.setattr(bootstrap, "wait_for_graph", nothing)
    monkeypatch.setattr(bootstrap, "apply_schema", nothing)
    return ifc, store, opened


@pytest.mark.parametrize(
    "command",
    [
        ["user", "list"],
        ["project", "list"],
        ["client", "list"],
        ["cleanup"],
        ["revoke", "--all"],
        ["ifc-db", "list"],
    ],
    ids=" ".join,
)
def test_a_command_over_the_servers_own_data_opens_the_store_alone(
    two_graphs: tuple[Graph, Graph, list[str]], command: list[str]
) -> None:
    ifc, store, opened = two_graphs
    done = CliRunner().invoke(app, command)
    assert done.exit_code == 0, done.output
    assert opened == ["store"], "the IFC graph is not even opened"
    assert store.statements and store.closed
    assert not ifc.statements


def test_pruning_opens_both_and_deletes_the_model_on_the_ifc_graph(two_graphs: tuple[Graph, Graph, list[str]]) -> None:
    ifc, store, opened = two_graphs
    done = CliRunner().invoke(app, ["ifc-db", "prune", "--project", "p1", "--all"])
    assert done.exit_code == 0, done.output
    assert "deleted 1 model(s)" in done.output
    assert opened == ["ifc", "store"] and ifc.closed and store.closed
    assert any(s.startswith("MATCH (m:Model") for s in ifc.statements)
    assert_apart(ifc, store)


def test_the_export_builds_the_service_with_both(
    two_graphs: tuple[Graph, Graph, list[str]], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ifc, store, _opened = two_graphs
    built: list[tuple[Any, Any]] = []

    class Service:
        def __init__(self, graph: Any, storage: Any, settings: Any, *, store: Any = None) -> None:
            built.append((graph, store))

        async def export(self, model_id: str, target: Path) -> int:
            return 3

    monkeypatch.setattr(service_module, "IfcGraphService", Service)
    done = CliRunner().invoke(app, ["ifc-db", "export", "model-1", str(tmp_path / "w.ifc"), "--no-validate"])
    assert done.exit_code == 0, done.output
    assert built == [(ifc, store)]


def test_the_seed_goes_to_the_store_and_its_model_to_the_ifc_graph(
    two_graphs: tuple[Graph, Graph, list[str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    ifc, store, _opened = two_graphs
    given: list[tuple[str, Any, Any]] = []

    async def seed(graph: Any, **kwargs: Any) -> seeding.SeedResult:
        given.append(("seed", graph, None))
        return seeding.SeedResult()

    async def build_sample_graph(graph: Any, storage: Any, settings: Any, result: Any, *, store: Any = None) -> dict:
        given.append(("model", graph, store))
        return {"state": "done", "entities": 1}

    monkeypatch.setattr(seeding, "seed", seed)
    monkeypatch.setattr(seeding, "build_sample_graph", build_sample_graph)
    done = CliRunner().invoke(app, ["seed", "--reset", "--yes"])
    assert done.exit_code == 0, done.output
    assert given == [("seed", store, None), ("model", ifc, store)]
    wiped = [graph.name for graph in (ifc, store) if any("DETACH DELETE n" in s for s in graph.statements)]
    assert wiped == ["ifc", "store"], "a reset empties both"


def test_the_doctor_checks_both(two_graphs: tuple[Graph, Graph, list[str]], monkeypatch: pytest.MonkeyPatch) -> None:
    ifc, store, opened = two_graphs
    given: list[tuple[Any, Any]] = []

    async def run_checks(settings: Any, graph: Any, storage: Any, *, store: Any = None) -> list[doctor.Check]:
        given.append((graph, store))
        return [doctor.Check("version", True, value="x")]

    monkeypatch.setattr(doctor, "run_checks", run_checks)
    done = CliRunner().invoke(app, ["doctor"])
    assert done.exit_code == 0, done.output
    assert given == [(ifc, store)] and opened == ["ifc", "store"] and ifc.closed and store.closed


def test_backup_and_restore_take_both(two_graphs: tuple[Graph, Graph, list[str]], tmp_path: Path) -> None:
    ifc, store, _opened = two_graphs
    done = CliRunner().invoke(app, ["backup", str(tmp_path / "backups")])
    assert done.exit_code == 0, done.output
    (folder,) = (tmp_path / "backups").iterdir()
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["store_dialect"] == "neo4j", "the manifest says the store was a graph of its own"
    assert ifc.statements and store.statements

    asked = len(ifc.statements), len(store.statements)
    done = CliRunner().invoke(app, ["restore", str(folder)])
    assert done.exit_code == 0, done.output
    assert len(ifc.statements) > asked[0] and len(store.statements) > asked[1], "both are asked whether empty"


# -- the backup itself --------------------------------------------------------------------------------------------


def server_nodes() -> list[tuple[str, list[dict[str, Any]]]]:
    return [
        ("UNWIND labels(n) AS label", [{"label": "User"}, {"label": "Project"}]),
        ("MATCH (n:User)", [{"labels": ["User"], "props": {"id": "u1", "username": "anna"}}]),
        ("MATCH (n:Project)", [{"labels": ["Project"], "props": {"project_id": "p1"}}]),
        (
            "MATCH (a:User)-[r]->(b)",
            [
                {
                    "a_key": "u1",
                    "type": "MEMBER_OF",
                    "props": {"role": "editor"},
                    "b_labels": ["Project"],
                    "b_keys": {"project_id": "p1"},
                }
            ],
        ),
    ]


def model_nodes() -> list[tuple[str, list[dict[str, Any]]]]:
    return [
        ("UNWIND labels(n) AS label", [{"label": "Model"}, {"label": "Entity"}, {"label": "IfcWall"}]),
        ("MATCH (n:Model)", [{"labels": ["Model"], "props": {"id": "m1"}}]),
        ("MATCH (n:Entity)", [{"labels": ["Entity", "IfcWall"], "props": {"id": "m1:9", "model_id": "m1"}}]),
        ("RETURN count(n) AS n", [{"n": 0}]),
    ]


def created(graph: Graph) -> list[str]:
    return [s.split("CREATE ")[1].split(" ")[0] for s in graph.statements if "CREATE (" in s]


async def test_a_backup_holds_both_graphs_and_restores_each_node_where_it_belongs(tmp_path: Path) -> None:
    ifc, store = Graph("ifc", model_nodes()), Graph("store", server_nodes())
    manifest = await backups.export(ifc, LocalStorage(tmp_path / "storage"), tmp_path / "b", store=store)  # type: ignore[arg-type]
    assert (manifest.nodes, manifest.relationships, manifest.store_dialect) == (4, 1, "neo4j"), (
        "a user's relationship once, though a user has two keys"
    )
    assert_apart(ifc, store)

    into_ifc, into_store = Graph("ifc"), Graph("store")
    await backups.restore(into_ifc, LocalStorage(tmp_path / "again"), tmp_path / "b", store=into_store)  # type: ignore[arg-type]
    assert sorted(created(into_ifc)) == ["(n:Entity:IfcWall)", "(n:Model)"]
    assert sorted(created(into_store)) == ["(a)-[r:MEMBER_OF]->(b)", "(n:Project)", "(n:User)"]

    into_one = Graph("one")
    await backups.restore(into_one, LocalStorage(tmp_path / "once"), tmp_path / "b")  # type: ignore[arg-type]
    assert len(created(into_one)) == 5, "into one graph, everything goes there"


async def test_a_backup_of_one_database_restores_into_two(tmp_path: Path) -> None:
    """What earlier releases kept in one graph, a project's HAS_MODEL to its model among it, is split on the way in;
    a relationship across the two is left out, since no database can hold it."""
    both = [*server_nodes()[1:], *model_nodes()[1:3]]
    both.insert(
        0, ("UNWIND labels(n) AS label", [{"label": label} for label in ("User", "Project", "Model", "Entity")])
    )
    both.append(
        (
            "MATCH (a:Project)-[r]->(b)",
            [{"a_key": "p1", "type": "HAS_MODEL", "props": {}, "b_labels": ["Model"], "b_keys": {"id": "m1"}}],
        )
    )
    one = Graph("one", both)
    manifest = await backups.export(one, LocalStorage(tmp_path / "storage"), tmp_path / "b")  # type: ignore[arg-type]
    assert manifest.store_dialect is None and manifest.relationships == 2
    assert "store_dialect" not in json.loads((tmp_path / "b" / "manifest.json").read_text(encoding="utf-8"))
    with gzip.open(tmp_path / "b" / "nodes.jsonl.gz", "rt", encoding="utf-8") as handle:
        assert len(handle.readlines()) == 4

    into_ifc, into_store = Graph("ifc"), Graph("store")
    await backups.restore(into_ifc, LocalStorage(tmp_path / "again"), tmp_path / "b", store=into_store)  # type: ignore[arg-type]
    assert sorted(created(into_ifc)) == ["(n:Entity:IfcWall)", "(n:Model)"]
    assert sorted(created(into_store)) == ["(a)-[r:MEMBER_OF]->(b)", "(n:Project)", "(n:User)"]


# -- the doctor and the readiness check -----------------------------------------------------------------------------


async def test_the_doctor_reports_the_store_apart_or_shared(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ifc, store = Graph("ifc"), Graph("store")

    async def answers(driver: str, database: str, seconds: float) -> bool:
        return driver != "down"

    monkeypatch.setattr(doctor, "ping_within", answers)
    settings = make_settings(tmp_path)
    shared = await doctor.store_checks(settings, ifc, ifc)  # type: ignore[arg-type]
    assert [(c.key, c.ok, c.detail_key) for c in shared] == [("store", True, "store_shared")]
    assert shared[0].name == "The server's own data" and "OPENCDE_STORE_GRAPH_URI" in shared[0].detail
    apart = await doctor.store_checks(settings, ifc, store)  # type: ignore[arg-type]
    assert [(c.key, c.ok, c.detail_key) for c in apart] == [
        ("store", True, "graph_ok"),
        ("store_schema", True, "schema_count"),
    ]
    store.driver = "down"
    silent = await doctor.store_checks(settings, ifc, store)  # type: ignore[arg-type]
    assert [(c.key, c.ok) for c in silent] == [("store", False), ("store_schema", False)]


@pytest.mark.parametrize(
    ("down", "status", "body"),
    [
        (None, 200, {"status": "ready", "graph": "ok", "store": "ok", "dialect": "neo4j", "workcopy": "none"}),
        ("store", 503, {"status": "not_ready", "graph": "ok", "store": "unavailable"}),
        ("ifc", 503, {"status": "not_ready", "graph": "unavailable", "store": "ok"}),
    ],
)
def test_the_server_is_ready_when_both_graphs_answer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, down: str | None, status: int, body: dict[str, str]
) -> None:
    async def answers(driver: str, database: str, seconds: float) -> bool:
        return driver != down

    monkeypatch.setattr(health, "ping_within", answers)
    ready = FastAPI()
    ready.include_router(health.router)
    ready.state.settings = make_settings(tmp_path)
    ready.state.graph, ready.state.store, ready.state.workcopy = Graph("ifc"), Graph("store"), None
    response = TestClient(ready).get("/readyz")
    assert (response.status_code, response.json()) == (status, body)
