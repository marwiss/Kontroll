# This file was generated with the assistance of an AI coding tool.
"""What the tests of the MCP endpoint's change sets share: a graph that keeps the drafts as the database would, by
the repository's own statements, and stands in for the documents, the proposals and the IFC-LPG service.

The drafts are kept by ``changeset_id`` and answered only to their user while that user is a member of their
project, as the statements' path from the user through ``MEMBER_OF`` has it; a transaction that raises leaves them
as they were. The database's own side is in ``tests/integration/test_mcp_change_sets.py``.
"""

from __future__ import annotations

import copy
from typing import Any

from opencde.store.jobs import drafts, proposals
from tests.mcp_support import CLOUD, DOCUMENT, FakeGraph, project

USER = "u-anna"
OTHER_DOCUMENT = "44444444-4444-4444-8444-444444444444"


def version(index: int, file_name: str = "walls.ifc") -> dict[str, Any]:
    return {
        "id": f"v-{index}",
        "version_index": index,
        "version_number": str(index),
        "creation_date": "2026-11-01T00:00:00.000Z",
        "title": "Walls",
        "file_name": file_name,
        "size_in_bytes": 1,
        "sha256": "0" * 64,
        "storage_key": f"documents/v-{index}",
        "author": "anna",
        "metadata": "[]",
    }


class DraftGraph(FakeGraph):
    """The server's own graph with the drafts kept, the documents of ``documents`` and the rows of the proposals."""

    def __init__(
        self,
        role: str = "editor",
        *,
        ai_policy: str = "cloud",
        documents: dict[str, tuple[str, list[dict[str, Any]]]] | None = None,
        proposal_rows: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__([(project(CLOUD, "Cloud project", ai_policy), role)])
        self.documents = (
            documents if documents is not None else {DOCUMENT: (CLOUD, [version(1), version(2), version(3)])}
        )
        self.proposal_rows = proposal_rows or []
        self.drafts: dict[str, dict[str, Any]] = {}
        self.transactions = 0

    def member_of(self, user_id: str, project_id: str) -> bool:
        return user_id == USER and any(found["project_id"] == project_id for found, _role in self.memberships)

    def set_role(self, role: str) -> None:
        self.memberships = [(found, role) for found, _role in self.memberships]

    async def run(self, query: str, **params: Any) -> list[dict[str, Any]]:
        if query in (drafts.OPEN, drafts.GET, drafts.TAKE, drafts.SAVE):
            self.calls.append((query, params))
            return self._draft(query, params)
        if query == proposals.LISTING:
            self.calls.append((query, params))
            return [dict(row) for row in self.proposal_rows]
        if "-[:HAS_VERSION]->(v:DocumentVersion" in query and "AS project_name" in query:
            self.calls.append((query, params))
            return self._versions(query, params)
        return await super().run(query, **params)

    async def one(self, query: str, **params: Any) -> dict[str, Any] | None:
        rows = await self.run(query, **params)
        return rows[0] if rows else None

    async def write(self, work: Any) -> Any:
        self.transactions += 1
        before = copy.deepcopy(self.drafts)
        try:
            return await work(self)
        except BaseException:
            self.drafts = before  # the database rolls the transaction back
            raise

    def _versions(self, query: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        found = self.documents.get(params["document_id"])
        if found is None or not self.member_of(params["user_id"], found[0]):
            return []
        project_id, versions = found
        wanted = [v for v in versions if params.get("version_index") in (None, v["version_index"])]
        if "ORDER BY v.version_index DESC LIMIT 1" in query:
            wanted = sorted(wanted, key=lambda v: v["version_index"])[-1:]
        row = {"document_id": params["document_id"], "project_id": project_id, "project_name": "Cloud project"}
        return [row | {"version": v} for v in wanted]

    def _draft(self, query: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        user_id = params["user_id"]
        if query == drafts.OPEN:
            found = self.documents.get(params["document_id"])
            if found is None or found[0] != params["project_id"] or not self.member_of(user_id, params["project_id"]):
                return []
            open_ones = [d for d in self.drafts.values() if d["user_id"] == user_id and d["expires_at"] > params["now"]]
            if len(open_ones) >= params["max_open"]:
                return []
            node = {key: params[key] for key in ("changeset_id", "user_id", "project_id", "document_id")}
            node |= {"version_index": params["version_index"], "steps": "[]", "refs": 0, "created_at": params["now"]}
            node["expires_at"] = params["expires_at"]
            self.drafts[node["changeset_id"]] = node
            return [{"draft": dict(node)}]
        node = self.drafts.get(params["changeset_id"])
        if (
            node is None
            or node["user_id"] != user_id
            or node["expires_at"] <= params["now"]
            or not self.member_of(user_id, node["project_id"])
        ):
            return []
        if query == drafts.TAKE:
            node["expires_at"] = params["expires_at"]
        if query == drafts.SAVE:
            node |= {"steps": params["steps"], "refs": params["refs"], "topic_guid": params["topic_guid"]}
            if params["topic_guid"] is None:
                node.pop("topic_guid")
            return [{"changeset_id": node["changeset_id"]}]
        return [{"draft": dict(node)}]

    def draft_queries(self) -> list[tuple[str, dict[str, Any]]]:
        return [
            (query, params)
            for query, params in self.calls
            if query in (drafts.OPEN, drafts.GET, drafts.TAKE, drafts.SAVE)
        ]


class FakeTrials:
    """The IFC-LPG service as far as the tools reach it: the trials they read, in turn, and the ones they queue."""

    def __init__(self, *nodes: dict[str, Any] | None) -> None:
        self.nodes = list(nodes)
        self.asked: list[dict[str, Any]] = []
        self.scheduled: list[dict[str, Any]] = []

    async def proposal(self, **asked: Any) -> dict[str, Any] | None:
        self.asked.append(asked)
        return self.nodes.pop(0) if len(self.nodes) > 1 else self.nodes[0] if self.nodes else None

    async def schedule_proposal(self, **scheduled: Any) -> str:
        self.scheduled.append(scheduled)
        return "proposal-1"

    async def shutdown(self) -> None:
        return None


class FakeProposing:
    """``documents.proposing.Proposing`` as far as ``propose_changes`` uses it: what it was asked to propose."""

    made: list[dict[str, Any]] = []

    def __init__(self, **stores: Any) -> None:
        self.stores = stores

    async def topic(self, **asked: Any) -> Any:
        FakeProposing.made.append({"topic": True, **asked})
        return _Topic(TOPIC)

    async def snippet(self, **asked: Any) -> None:
        FakeProposing.made.append({"topic": False, **asked})


TOPIC = "55555555-5555-4555-8555-555555555555"


class _Snippet:
    snippet_type = "DataregiumIfcChangeSet"


class _Topic:
    def __init__(self, guid: str, snippet: Any = _Snippet) -> None:
        self.guid = guid
        self.bim_snippet = snippet


class FakeTopics:
    """The topics as ``propose_changes`` reads them: the one it made, while it is there."""

    there: dict[str, Any] = {}

    def __init__(self, graph: Any, **_options: Any) -> None:
        self.graph = graph

    async def get(self, *, user_id: str, project_id: str, guid: str) -> Any:
        return FakeTopics.there.get(guid)


def trial(state: str = "clean", **fields: Any) -> dict[str, Any]:
    """A trial as ``IfcGraphService.proposal`` gives it."""
    node: dict[str, Any] = {"state": state, "created_at": "2026-11-12T09:30:00.000Z", "checks": [], "issues": []}
    node["teams"] = []
    node |= {"base_document_id": DOCUMENT, "base_version_index": 3, "change_count": 2, "applied": 2}
    return node | fields
