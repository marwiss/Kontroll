# This file was generated with the assistance of an AI coding tool.
"""What the tests of ``server_query``, ``get_publication`` and the clash tools share: a graph that also answers the
documents' versions, publications, conversions and change sets for the projects the user is a member of, and stand-ins
for the IFC-LPG module's service and its IFC graph, which the endpoint is given in place of its own.

The database's own side is in ``tests/integration/test_mcp_server_query.py`` and ``tests/integration/test_mcp_clash.py``.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from ifc_lpg.validation import pack_report

from opencde.ifcgraph import queries as server_queries
from opencde.ifcgraph.queries import QUERIES
from tests.mcp_support import CLOUD, DOCUMENT, FakeGraph, endpoint

MODEL = "model-of-version-3"
CLASH = "44444444-4444-4444-8444-444444444444"
GUID = "1Xezbq735AdBO_4DerG66G"
#: A publication as the server keeps it (``DocumentRepository.publish``).
PUBLISHED = {
    "id": "publication-1",
    "storage_key": "published/publication-1.ifczip",
    "file_name": "walls.ifczip",
    "size_in_bytes": 1234,
    "sha256": "a" * 64,
    "published_at": "2026-11-12T09:30:00.000Z",
    "published_by": "bo",
}


def version(index: int = 3, project_id: str = CLOUD, document_id: str = DOCUMENT, **values: Any) -> dict[str, Any]:
    """A version as the documents' statements return it."""
    return {
        "document_id": document_id,
        "project_id": project_id,
        "project_name": "Cloud project",
        "version": {
            "id": f"version-{index}",
            "version_index": index,
            "version_number": str(index),
            "creation_date": "2026-11-01T00:00:00.000Z",
            "title": "Walls",
            "file_name": "walls.ifc",
            "size_in_bytes": 1,
            "sha256": "0" * 64,
            "storage_key": f"documents/version-{index}",
            "author": "anna",
        }
        | values,
    }


class DocumentsGraph(FakeGraph):
    """The server's own graph with the versions of the member's projects, their conversions (by version index, the
    state and the model's id), their publications (by version index) and the versions' change sets (``since``, as
    ``DocumentRepository.versions_since`` gives them)."""

    def __init__(
        self,
        memberships: list[tuple[dict[str, Any], str]] | None = None,
        versions: list[dict[str, Any]] | None = None,
        conversions: dict[int, tuple[str, str]] | None = None,
        publications: dict[int, dict[str, Any]] | None = None,
        since: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(memberships, models=[])
        self.versions = versions if versions is not None else [version()]
        self.conversions = conversions if conversions is not None else {3: ("done", MODEL)}
        self.publications = publications or {}
        self.since = since or []

    def _reached(self, document_id: Any) -> list[dict[str, Any]]:
        """The versions of the document in a project the user is a member of, oldest first."""
        mine = {found["project_id"] for found, _role in self.memberships}
        rows = [row for row in self.versions if row["document_id"] == document_id and row["project_id"] in mine]
        return sorted(rows, key=lambda row: row["version"]["version_index"])

    async def one(self, query: str, **params: Any) -> dict[str, Any] | None:
        self.calls.append((query, params))
        rows = self._reached(params.get("document_id"))
        if "version_index" in params:
            rows = [row for row in rows if row["version"]["version_index"] == params["version_index"]]
        if not rows:
            return None
        if "HAS_PUBLICATION" in query:
            found = self.publications.get(params["version_index"])
            return {"publication": found} if found else None
        return rows[-1]

    async def run(self, query: str, **params: Any) -> list[dict[str, Any]]:
        if "(m:Conversion)" in query:
            self.calls.append((query, params))
            known = self._reached(params["document_id"])
            state = self.conversions.get(params["version_index"]) if known else None
            return [{"state": state[0], "id": state[1]}] if state else []
        if "v.version_index > $since" in query:
            self.calls.append((query, params))
            return [
                {key: row[key] for key in ("version_index", "author", "approved_by", "change_set_id")}
                | {"change_set": pack_report(row["changes"]) if row["changes"] is not None else None}
                for row in self.since
                if params["since"] < row["version_index"] <= params["until"]
            ]
        return await super().run(query, **params)

    def conversion_lookups(self) -> list[dict[str, Any]]:
        return [params for query, params in self.calls if "(m:Conversion)" in query]


class IfcGraph:
    """The IFC graph as IFC-LPG's named queries read it: the rows of each query, by its columns."""

    def __init__(self, rows: dict[str, list[dict[str, Any]]] | None = None) -> None:
        self.rows = rows or {}
        self.asked: list[tuple[str, dict[str, Any]]] = []

    async def run(self, statement: str, **params: Any) -> list[dict[str, Any]]:
        name = next(name for name, query in QUERIES.items() if query.cypher == statement)
        self.asked.append((name, params))
        return self.rows.get(name, [])[: params["row_limit"]]


def clash_row(state: str = "queued", **values: Any) -> dict[str, Any]:
    """A clash check as the service reads it back (``IfcGraphService.clash_report``)."""
    side = {"document_id": DOCUMENT, "version_index": 3, "types": None}
    return {
        "id": CLASH,
        "project_id": CLOUD,
        "state": state,
        "author": "anna",
        "created_at": "2026-11-12T09:30:00.000Z",
        "request": {"a": side, "b": side, "mode": "intersection", "tolerance": 0.001, "clearance": 0.05},
        "clashes": None,
    } | values


def pair(name: str | None = "Wall 1", storey: str | None = "Level 1") -> dict[str, Any]:
    """One clash of a report, as the worker writes it."""
    element = {"document_id": DOCUMENT, "version_index": 3, "id": 242, "guid": GUID, "type": "IfcWall"}
    return {
        "a": element | {"name": name, "storey": storey},
        "b": element | {"id": 243, "guid": "3eT96F_cnDsOufCEsotwtp", "name": None, "storey": None},
        "kind": "intersection",
        "depth": 0.182,
        "distance": 0.0,
        "point": [12.431, 7.902, 6.35],
        "extent": None,
    }


class FakeService:
    """The IFC-LPG module's service as far as the tools ask it: its IFC graph, the working copy, and the clash checks,
    whose reports come back in the order given and the last one ever after."""

    def __init__(
        self,
        ifc: IfcGraph | None = None,
        workcopy: IfcGraph | None = None,
        held: bool = False,
        reports: list[dict[str, Any]] | None = None,
    ) -> None:
        self.graph = ifc or IfcGraph()
        self.workcopy = workcopy
        self.held = held
        self.reports = list(reports or [])
        self.scheduled: list[dict[str, Any]] = []
        self.read: list[dict[str, Any]] = []

    async def in_workcopy(self, model_id: str) -> bool:
        return self.held

    async def shutdown(self) -> None:
        """The application stops its service as it stops."""

    async def schedule_clash(self, *, project_id: str, author: str, request: dict[str, Any]) -> str:
        self.scheduled.append({"project_id": project_id, "author": author, "request": request})
        self.reports = [clash_row(request=request)]
        return CLASH

    async def clash_report(
        self, *, user_id: str, project_id: str, clash_id: str, with_clashes: bool
    ) -> dict[str, Any] | None:
        self.read.append({"user_id": user_id, "project_id": project_id, "clash_id": clash_id})
        if clash_id != CLASH or not self.reports:
            return None
        return self.reports.pop(0) if len(self.reports) > 1 else self.reports[0]


@contextmanager
def tools(
    tmp_path: Path,
    graph: DocumentsGraph | None = None,
    service: FakeService | None = None,
    **overrides: Any,
) -> Iterator[TestClient]:
    """The endpoint with the IFC-LPG module and the clash check on, the graph and the service standing in; the
    module's settings can be turned off through ``overrides``. The stand-in IFC graph is asked as the library asks
    any graph, without the driver's read transaction."""
    settings = {"ifcgraph_enabled": True, "ifcgraph_clash_enabled": True, **overrides}
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(server_queries, "ReadingGraph", lambda graph: graph)
        with endpoint(tmp_path, graph if graph is not None else DocumentsGraph(), **settings) as client:
            client.app.state.ifcgraph = service if service is not None else FakeService()  # type: ignore[attr-defined]
            yield client
