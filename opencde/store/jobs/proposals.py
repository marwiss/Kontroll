# This file was generated with the assistance of an AI coding tool.
"""The trials of change sets as a document's list of proposals (ADR 0021).

A ``Proposal`` hangs off the topic whose snippet is the change set (``HAS_PROPOSAL``); the IFC-DB service makes
and judges it (``ifcgraph/service.py``). This repository reads them the other way round, for the Documents API:
every proposal against a document, found from the user through ``MEMBER_OF`` to the project, its document and the
topics' proposals that name the document as their base. Rows are the columns a listing needs, never the report
or the keys of the files.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends

from opencde.deps import GraphDep
from opencde.graph.graph import Graph
from opencde.odata import Compiled, Field
from opencde.store.protocols import ProposalStore

#: The listing is ordered newest first by the proposal's creation time, and by nothing else; no field is filtered
#: on, so ``$filter`` and ``$orderby`` are refused as unknown fields, and ``$top`` and ``$skip`` page through it.
FIELDS: dict[str, Field] = {}
ORDERABLE: tuple[str, ...] = ()
DEFAULT_ORDER = "r.created_at DESC"

MATCHING = """
MATCH (:User {id: $user_id})-[:MEMBER_OF]->(p:Project)-[:HAS_DOCUMENT]->(:Document {document_id: $document_id})
MATCH (p)-[:HAS_TOPIC]->(t:Topic)-[:HAS_PROPOSAL]->(r:Proposal {base_document_id: $document_id})
"""

LISTING = (
    MATCHING
    + """
RETURN p.project_id AS project_id, t.guid AS topic_guid, t.title AS title, t.description AS description,
       r.state AS state, r.base_version_index AS base_version_index, r.change_count AS change_count,
       r.author AS author, r.checked_at AS checked_at, r.version_index AS version_index
ORDER BY r.created_at DESC
SKIP $skip LIMIT $limit
"""
)


class ProposalRepository:
    """The proposals against a document, for a member of its project."""

    def __init__(self, graph: Graph) -> None:
        self.graph = graph

    async def count(self, *, user_id: str, document_id: str, compiled: Compiled) -> int:
        """How many proposals name the document as their base, before ``$top`` and ``$skip``."""
        row = await self.graph.one(MATCHING + "RETURN count(r) AS total", user_id=user_id, document_id=document_id)
        return int(row["total"]) if row else 0

    async def of_document(self, *, user_id: str, document_id: str, compiled: Compiled) -> list[dict[str, Any]]:
        """One row per proposal, newest first: the topic's guid, title and description, the trial's state, base
        version, number of changes, author and end, the version it became, and the project's id for the links."""
        rows = await self.graph.run(
            LISTING, user_id=user_id, document_id=document_id, skip=compiled.skip, limit=compiled.limit
        )
        return [dict(row) for row in rows]


def proposal_repository(graph: GraphDep) -> ProposalStore:
    return ProposalRepository(graph)


ProposalsDep = Annotated[ProposalStore, Depends(proposal_repository)]
