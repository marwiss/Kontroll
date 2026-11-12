# This file was generated with the assistance of an AI coding tool.
"""The list of the proposals against a document (ADR 0021): its rows, its links and its Cypher. The list itself is
proved against a database in ``tests/integration/test_ifc_proposal.py``."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from opencde.admin.graph_query import check_statement
from opencde.bcf.odata_params import MAX_TOP
from opencde.documents.routes_proposals import MAX_DESCRIPTION, IfcProposalEntry, _entry
from opencde.odata import ODataError, compile_odata
from opencde.store.jobs.proposals import DEFAULT_ORDER, FIELDS, ORDERABLE, ProposalRepository

PROJECT = "11111111-2222-4333-8444-555555555555"
TOPIC = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
BASE = "http://cde.example"


def row(**fields: Any) -> dict[str, Any]:
    return {
        "project_id": PROJECT,
        "topic_guid": TOPIC,
        "title": "Rename the wall",
        "description": None,
        "state": "clean",
        "base_version_index": 1,
        "change_count": 1,
        "author": "editor",
        "checked_at": "2026-11-11T10:00:00Z",
        "version_index": None,
        **fields,
    }


def test_a_row_names_the_topic_the_trial_and_its_approval() -> None:
    entry = _entry(BASE, row())
    assert entry.model_dump() == {
        "topic_guid": TOPIC,
        "title": "Rename the wall",
        "description": None,
        "state": "clean",
        "base_version_index": 1,
        "change_count": 1,
        "author": "editor",
        "checked_at": "2026-11-11T10:00:00Z",
        "version_index": None,
        "proposal_url": f"{BASE}/bcf/3.0/projects/{PROJECT}/topics/{TOPIC}/ifc-proposal",
        "approve_url": f"{BASE}/bcf/3.0/projects/{PROJECT}/topics/{TOPIC}/ifc-proposal/approve",
    }
    assert all(field.description for field in IfcProposalEntry.model_fields.values()), "every field is described"


def test_the_trial_of_operations_names_their_refs_their_notes_and_the_one_that_failed() -> None:
    """``GET …/ifc-proposal`` for a change set with ``ops``: the client maps its refs to the GlobalIds the server gave,
    and an operation that failed says its index and tool; a trial without operations has neither key."""
    from opencde.bcf.routes_proposals import IfcProposalIssue, IfcProposalReport, proposal_report

    failed = {
        "kind": "op",
        "severity": "error",
        "message": "op 1 (create_wall): no storey named 'Level 9'; the storeys are Level 1",
        "op": 1,
        "tool": "create_wall",
    }
    node = {"state": "issues", "created_at": "2026-11-11T10:00:00Z", "checks": [], "issues": [failed]}
    node |= {"created": {"new-1": "1Xezbq735AdBO_4DerG66G"}, "notes": ["the map conversion to EPSG:3006 was skipped"]}
    shown = proposal_report(node).model_dump(exclude_none=True)
    assert shown["issues"] == [failed] and shown["created"] == {"new-1": "1Xezbq735AdBO_4DerG66G"}
    assert shown["notes"] == ["the map conversion to EPSG:3006 was skipped"]
    plain = proposal_report({**node, "created": None, "notes": None, "issues": []}).model_dump(exclude_none=True)
    assert "created" not in plain and "notes" not in plain
    assert all(field.description for name, field in IfcProposalIssue.model_fields.items() if name in ("op", "tool"))
    assert IfcProposalReport.model_fields["created"].description and IfcProposalReport.model_fields["notes"].description


def test_the_description_is_cut_and_the_trial_fills_the_row_as_it_goes() -> None:
    assert _entry(BASE, row(description="x" * (MAX_DESCRIPTION + 50))).description == "x" * MAX_DESCRIPTION
    assert _entry(BASE, row(description="short")).description == "short"
    assert _entry(BASE, row(description="")).description is None, "an empty description is none"
    queued = _entry(BASE, row(state="queued", change_count=None, checked_at=None))
    assert (queued.change_count, queued.checked_at, queued.version_index) == (None, None, None)
    approved = _entry(BASE, row(state="approved", version_index=2))
    assert approved.version_index == 2 and approved.state == "approved"


class RecordingGraph:
    """Keeps every statement it is given and answers nothing."""

    def __init__(self) -> None:
        self.statements: list[tuple[str, dict[str, Any]]] = []

    async def run(self, cypher: str, **params: Any) -> list[dict[str, Any]]:
        self.statements.append((cypher, params))
        return []

    async def one(self, cypher: str, **params: Any) -> dict[str, Any] | None:
        self.statements.append((cypher, params))
        return None


def compiled(**options: Any) -> Any:
    return compile_odata(
        filter_=options.get("filter"),
        orderby=options.get("orderby"),
        top=options.get("top"),
        skip=options.get("skip"),
        fields=FIELDS,
        orderable=ORDERABLE,
        default_order=DEFAULT_ORDER,
        max_top=MAX_TOP,
    )


def test_the_listing_starts_at_the_user_walks_member_of_and_only_reads() -> None:
    graph = RecordingGraph()
    repository = ProposalRepository(graph)  # type: ignore[arg-type]
    assert asyncio.run(repository.of_document(user_id="u", document_id="d", compiled=compiled(skip=5))) == []
    assert asyncio.run(repository.count(user_id="u", document_id="d", compiled=compiled())) == 0
    for cypher, params in graph.statements:
        assert cypher.lstrip().startswith("MATCH (:User {id: $user_id})-[:MEMBER_OF]->(p:Project)-[:HAS_DOCUMENT]->")
        assert "(:Document {document_id: $document_id})" in cypher
        assert "(r:Proposal {base_document_id: $document_id})" in cypher, "the proposals that name the document"
        assert params["user_id"] == "u" and params["document_id"] == "d"
        check_statement(cypher)  # the fence the administrators' free Cypher goes through
    listing, _count = (statement for statement, _ in graph.statements)
    assert "ORDER BY r.created_at DESC" in listing and "SKIP $skip LIMIT $limit" in listing
    assert graph.statements[0][1]["skip"] == 5 and graph.statements[0][1]["limit"] == MAX_TOP
    assert "report" not in listing and "key" not in listing, "the findings and the files' keys stay with the trial"


def test_the_list_is_cut_like_the_bcf_lists_and_has_nothing_to_filter_on() -> None:
    whole = compiled()
    assert whole.limit == MAX_TOP and whole.capped and whole.skip == 0 and whole.order_by == DEFAULT_ORDER
    assert compiled(top=10).limit == 10 and not compiled(top=10).capped
    assert compiled(top=MAX_TOP + 1).limit == MAX_TOP and compiled(top=MAX_TOP + 1).capped
    with pytest.raises(ODataError):
        compiled(filter="title eq 'x'")
    with pytest.raises(ODataError):
        compiled(orderby="created_at desc")
