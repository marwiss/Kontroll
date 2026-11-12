# This file was generated with the assistance of an AI coding tool.
"""The trials of change sets (ADR 0021): the job, and a document's list of proposals.

A ``Proposal`` hangs off the topic whose snippet is the change set (``HAS_PROPOSAL``), one per topic: a new trial
replaces the earlier one, whose applied file the caller deletes. The IFC-DB service runs and judges it
(``ifcgraph/service.py``) through this repository: the lifecycle (``queued``, ``running``, then ``clean``, ``issues``
or ``failed``, and ``approved`` once a clean one became a version), each with its time, and the fields of the result.

The listing reads them the other way round, for the Documents API: every proposal against a document, found from
the user through ``MEMBER_OF`` to the project, its document and the topics' proposals that name the document as
their base. Its rows are the columns a listing needs, never the report or the keys of the files.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends

from opencde.deps import GraphDep
from opencde.graph.graph import Graph, Tx
from opencde.odata import Compiled, Field
from opencde.store.protocols import ProposalStore
from opencde.timeutil import now_iso

STATE_QUEUED = "queued"
STATE_RUNNING = "running"

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

    # -- the job ----------------------------------------------------------------

    async def create(
        self,
        *,
        proposal_id: str,
        project_id: str,
        topic_guid: str,
        snippet_key: str,
        author: str,
        base_document_id: str | None,
        base_version_index: int | None,
    ) -> tuple[bool, list[str]]:
        """A queued trial of the topic's change set, in place of the topic's earlier one, in one transaction: whether
        it was made (False when the project has no such topic), and the storage keys of the files the earlier trials
        leave behind."""

        async def work(tx: Tx) -> tuple[bool, list[str]]:
            gone = await tx.run(
                """
                MATCH (:Project {project_id: $project_id})-[:HAS_TOPIC]->(:Topic {guid: $guid})-[:HAS_PROPOSAL]->(p:Proposal)
                WITH p, p.storage_key AS key
                DETACH DELETE p
                RETURN key
                """,
                project_id=project_id,
                guid=topic_guid,
            )
            rows = await tx.run(
                """
                MATCH (:Project {project_id: $project_id})-[:HAS_TOPIC]->(t:Topic {guid: $guid})
                CREATE (t)-[:HAS_PROPOSAL]->(p:Proposal {
                    id: $id, project_id: $project_id, topic_guid: $guid, snippet_key: $snippet_key, author: $author,
                    state: $state, created_at: $now,
                    base_document_id: $base_document_id, base_version_index: $base_version_index
                })
                RETURN p.id AS id
                """,
                project_id=project_id,
                guid=topic_guid,
                id=proposal_id,
                snippet_key=snippet_key,
                author=author,
                state=STATE_QUEUED,
                now=now_iso(),
                base_document_id=base_document_id,
                base_version_index=base_version_index,
            )
            return bool(rows), [str(row["key"]) for row in gone if row["key"]]

        return await self.graph.write(work)

    async def claim(self, proposal_id: str) -> dict[str, Any] | None:
        """The queued trial's project, snippet and author, now this process's to run; None when it is not queued."""
        return await self.graph.one(
            """
            MATCH (p:Proposal {id: $id, state: $queued})
            SET p.state = $running, p.running_at = $now
            RETURN p.project_id AS project_id, p.snippet_key AS snippet_key, p.author AS author
            """,
            id=proposal_id,
            queued=STATE_QUEUED,
            running=STATE_RUNNING,
            now=now_iso(),
        )

    async def set_state(self, proposal_id: str, state: str, **fields: Any) -> None:
        await self.graph.run(
            "MATCH (p:Proposal {id: $id}) SET p.state = $state, p += $fields",
            id=proposal_id,
            state=state,
            fields={**fields, f"{state}_at": now_iso()},
        )

    async def get(self, proposal_id: str) -> dict[str, Any] | None:
        """The trial's project, snippet and author, whatever its state; None without it."""
        return await self.graph.one(
            """
            MATCH (p:Proposal {id: $id})
            RETURN p.project_id AS project_id, p.snippet_key AS snippet_key, p.author AS author
            """,
            id=proposal_id,
        )

    async def snippet_key(self, *, project_id: str, topic_guid: str) -> str | None:
        """The storage key of the change set a topic's trial tries; None when the topic has no trial."""
        row = await self.graph.one(
            """
            MATCH (:Project {project_id: $project_id})-[:HAS_TOPIC]->(:Topic {guid: $guid})
                  -[:HAS_PROPOSAL]->(p:Proposal)
            RETURN p.snippet_key AS snippet_key
            """,
            project_id=project_id,
            guid=topic_guid,
        )
        return str(row["snippet_key"]) if row and row["snippet_key"] else None

    async def of_topic(self, *, user_id: str, project_id: str, topic_guid: str) -> dict[str, Any] | None:
        """The trial of a topic, as it is kept (its report packed), for a member of the project; None without one."""
        row = await self.graph.one(
            """
            MATCH (:User {id: $user_id})-[:MEMBER_OF]->(:Project {project_id: $project_id})
                  -[:HAS_TOPIC]->(:Topic {guid: $guid})-[:HAS_PROPOSAL]->(p:Proposal)
            RETURN properties(p) AS node
            """,
            user_id=user_id,
            project_id=project_id,
            guid=topic_guid,
        )
        return dict(row["node"]) if row else None

    async def interrupted(self, *, given_up: str) -> list[dict[str, Any]]:
        """The trials a stopped server left behind: queued, or running since before ``given_up``."""
        return await self.graph.run(
            """
            MATCH (p:Proposal)
            WHERE p.state = $queued OR (p.state = $running AND p.running_at < $given_up)
            RETURN p.id AS id, p.state AS state
            """,
            queued=STATE_QUEUED,
            running=STATE_RUNNING,
            given_up=given_up,
        )


def proposal_repository(graph: GraphDep) -> ProposalStore:
    return ProposalRepository(graph)


ProposalsDep = Annotated[ProposalStore, Depends(proposal_repository)]
