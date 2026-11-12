# This file was generated with the assistance of an AI coding tool.
"""The topic and comment events (BCF API 3.9, 3.10) as a repository, so that the routes ask the store (ADR 0029).

The graph's statements stay in ``opencde.bcf.events``, beside the event types and the diff that both stores use; a
repository records its events inside its own transactions.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends

from opencde.bcf import events
from opencde.deps import GraphDep, PostgresDep
from opencde.graph.graph import Graph
from opencde.odata import Compiled
from opencde.store.protocols import BcfEventStore


class BcfEventRepository:
    def __init__(self, graph: Graph) -> None:
        self.graph = graph

    async def count(
        self,
        *,
        user_id: str,
        project_id: str,
        kind: str,
        compiled: Compiled,
        topic_guid: str | None = None,
        comment_guid: str | None = None,
        left_out: frozenset[str] = frozenset(),
    ) -> int:
        """How many events the options match, before ``$top`` and ``$skip``."""
        return await events.count(
            self.graph,
            user_id=user_id,
            project_id=project_id,
            kind=kind,
            compiled=compiled,
            topic_guid=topic_guid,
            comment_guid=comment_guid,
            left_out=left_out,
        )

    async def query(
        self,
        *,
        user_id: str,
        project_id: str,
        kind: str,
        compiled: Compiled,
        topic_guid: str | None = None,
        comment_guid: str | None = None,
        left_out: frozenset[str] = frozenset(),
    ) -> list[dict[str, Any]]:
        """Events of a project (optionally one topic or comment) without the actions of ``left_out``, and without
        the events that then have none left."""
        return await events.query(
            self.graph,
            user_id=user_id,
            project_id=project_id,
            kind=kind,
            compiled=compiled,
            topic_guid=topic_guid,
            comment_guid=comment_guid,
            left_out=left_out,
        )


def event_repository(graph: GraphDep, postgres: PostgresDep) -> BcfEventStore:
    from opencde.store.bcf.postgres import event_store  # it imports this module

    return event_store(graph, postgres)


EventsDep = Annotated[BcfEventStore, Depends(event_repository)]
