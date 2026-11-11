# This file was generated with the assistance of an AI coding tool.
"""Housekeeping: unused self-registered clients expire, and imported models can be pruned."""

from __future__ import annotations

import pytest

from opencde.graph.cleanup import delete_expired
from opencde.graph.graph import Graph
from opencde.ifcgraph.maintenance import list_models, prune_models
from opencde.store.oauth2.clients import ClientRepository
from opencde.timeutil import later_iso

pytestmark = pytest.mark.integration


async def test_unused_self_registered_clients_expire_and_can_be_pruned(graph: Graph) -> None:
    clients = ClientRepository(graph)
    stale, _ = await clients.create(
        "Old app", ["https://a.test/cb"], public=True, dynamic=True, expires_at=later_iso(-60)
    )
    fresh, _ = await clients.create(
        "Fresh app", ["https://b.test/cb"], public=True, dynamic=True, expires_at=later_iso(3600)
    )
    manual, _ = await clients.create("Manual", ["https://c.test/cb"], public=False, expires_at=later_iso(-60))
    assert manual.expires_at is None, "only self-registered clients expire"
    await graph.run(
        "MATCH (c:Client {client_id: $id}) CREATE (:RefreshToken {token_hash: 'fresh-token', expires_at: $future})-[:ISSUED_TO]->(c)",
        id=fresh.client_id,
        future=later_iso(3600),
    )

    assert await delete_expired(graph) == 1, "the cleaner removes the stale registration"
    assert await clients.get(stale.client_id) is None
    assert await clients.get(fresh.client_id) is not None and await clients.get(manual.client_id) is not None

    # Using the client moves its expiry forward; a manual client is never touched.
    await clients.touch(fresh.client_id, expires_at=later_iso(7200))
    await clients.touch(manual.client_id, expires_at=later_iso(7200))
    refreshed = await clients.get(fresh.client_id)
    assert refreshed is not None and refreshed.expires_at is not None and refreshed.expires_at > fresh.expires_at  # type: ignore[operator]
    assert (await clients.get(manual.client_id)).expires_at is None  # type: ignore[union-attr]

    assert await clients.prune_dynamic() == 0, "nothing expired any more"
    assert await clients.prune_dynamic(all_dynamic=True) == 1, "but every self-registered client can be dropped"
    assert await clients.get(fresh.client_id) is None and await clients.get(manual.client_id) is not None
    rows = await graph.run("MATCH (t:RefreshToken {token_hash: 'fresh-token'}) RETURN count(t) AS n")
    assert rows[0]["n"] == 0, "its tokens go with it"


async def test_prune_keeps_the_latest_finished_model_per_document(graph: Graph) -> None:
    await graph.run(
        """
        CREATE (p:Project {project_id: 'p', name: 'P', created_at: '2026-01-01T00:00:00.000Z'})
        CREATE (p)-[:HAS_CONVERSION]->(:Conversion {id: 'a1', model_id: 'a1', project_id: 'p', document_id: 'A', version_index: 1,
                 state: 'done', created_at: '2026-01-01T00:00:00.000Z', done_at: '2026-01-01T00:00:01.000Z'})
        CREATE (p)-[:HAS_CONVERSION]->(:Conversion {id: 'a2', model_id: 'a2', project_id: 'p', document_id: 'A', version_index: 2,
                 state: 'done', created_at: '2026-01-02T00:00:00.000Z', done_at: '2026-01-02T00:00:01.000Z'})
        CREATE (p)-[:HAS_CONVERSION]->(:Conversion {id: 'a3', model_id: 'a3', project_id: 'p', document_id: 'A', version_index: 3,
                 state: 'failed', created_at: '2026-01-03T00:00:00.000Z', failed_at: '2026-01-03T00:00:01.000Z'})
        CREATE (p)-[:HAS_CONVERSION]->(:Conversion {id: 'b1', model_id: 'b1', project_id: 'p', bcf_document_guid: 'B',
                 state: 'done', created_at: '2026-01-04T00:00:00.000Z', done_at: '2026-01-04T00:00:01.000Z'})
        CREATE (p)-[:HAS_CONVERSION]->(:Conversion {id: 'q1', model_id: 'q1', project_id: 'p', document_id: 'Q', version_index: 1,
                 state: 'queued', created_at: '2026-01-05T00:00:00.000Z'})
        CREATE (:Entity:IfcWall {id: 'a1:1', model_id: 'a1', GlobalId: 'g1'})
        CREATE (:Entity:IfcWall {id: 'a2:1', model_id: 'a2', GlobalId: 'g1'})
        CREATE (:Entity:IfcWall {id: 'b1:1', model_id: 'b1', GlobalId: 'g2'})
        """
    )
    assert await prune_models(graph, project_id="p") == {"models": 2, "entities": 1}, "a1 superseded, a3 failed"
    assert {m["id"] for m in await list_models(graph, project_id="p")} == {"a2", "b1", "q1"}
    assert await prune_models(graph, project_id="other") == {"models": 0, "entities": 0}

    with pytest.raises(ValueError):
        await prune_models(graph, everything=True)
    assert await prune_models(graph, project_id="p", everything=True) == {"models": 3, "entities": 2}
    assert await list_models(graph) == []
    rows = await graph.run("MATCH (e:Entity) RETURN count(e) AS n")
    assert rows[0]["n"] == 0
