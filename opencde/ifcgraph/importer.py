# This file was generated with the assistance of an AI coding tool.
"""Load converted records into the graph in batches (``UNWIND … CREATE``, no APOC)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from opencde.graph.graph import Graph
from opencde.ifcgraph.schema import relationship_type
from opencde.ifcgraph.schema import safe_identifier as _safe

BATCH = 2_000
MAX_BATCH_BYTES = 16 * 1024 * 1024  # a coordinate list can be megabytes, and a transaction's memory has a limit
BLOCK_BATCH = 100


async def import_records(graph: Graph, model_id: str, records_path: Path) -> dict[str, int]:
    """Create the ``IfcEntity`` nodes and their relationships for one model. Returns counts."""
    nodes = relationships = 0
    block_rows: list[dict[str, Any]] = []
    node_groups: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    edge_groups: dict[tuple[str, bool], list[dict[str, Any]]] = {}

    async def flush_nodes() -> None:
        nonlocal nodes
        for labels, rows in node_groups.items():
            label_clause = ":".join(["IfcEntity", *labels])
            await graph.run(
                f"UNWIND $rows AS row CREATE (n:{label_clause}) SET n = row.props, n.id = row.id, "
                f"n.step_id = row.step, n.model_id = $model_id",
                rows=rows,
                model_id=model_id,
            )
            nodes += len(rows)
        node_groups.clear()
        if block_rows:
            await graph.run(
                """
                MATCH (m:IfcModel {id: $model_id})
                UNWIND $rows AS row
                CREATE (m)-[:HAS_STEP_BLOCK]->(:StepBlock {
                    id: $model_id + ':' + toString(row.first), first_step: row.first, instances: row.instances,
                    text: row.text
                })
                """,
                model_id=model_id,
                rows=block_rows,
            )
            block_rows.clear()

    async def flush_edges() -> None:
        nonlocal relationships
        for (rel_type, positioned), rows in edge_groups.items():
            relationship = f"{rel_type} {{position: row.position}}" if positioned else rel_type
            await graph.run(
                f"UNWIND $rows AS row MATCH (a:IfcEntity {{id: row.a}}), (b:IfcEntity {{id: row.b}}) "
                f"CREATE (a)-[:{relationship}]->(b)",
                rows=rows,
            )
            relationships += len(rows)
        edge_groups.clear()

    pending = pending_bytes = 0
    with records_path.open(encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            kind = record["t"]
            if kind == "n":
                labels = tuple(_safe(label) for label in record["labels"])
                node_groups.setdefault(labels, []).append(
                    {"id": f"{model_id}:{record['step']}", "step": record["step"], "props": record["props"]}
                )
            elif kind == "g":
                block_rows.append({key: record[key] for key in ("first", "instances", "text")})
            elif kind == "e":
                position = record.get("position")
                row = {"a": f"{model_id}:{record['a']}", "b": f"{model_id}:{record['b']}"}
                if position is not None:
                    row["position"] = position
                edge_groups.setdefault((relationship_type(record["type"]), position is not None), []).append(row)
            else:
                await flush_nodes()  # the header separates nodes from edges
                continue
            pending += 1
            pending_bytes += len(line)
            if pending >= BATCH or pending_bytes >= MAX_BATCH_BYTES:
                await flush_nodes()
                await flush_edges()
                pending = pending_bytes = 0
    await flush_nodes()
    await flush_edges()
    await graph.run(
        """
        MATCH (m:IfcModel {id: $model_id}), (p:IfcEntity:IfcProject {model_id: $model_id})
        MERGE (m)-[:HAS_PROJECT]->(p)
        """,
        model_id=model_id,
    )
    return {"nodes": nodes, "relationships": relationships}


async def delete_blocks(graph: Graph, model_id: str) -> None:
    """Remove a model's blocks, a few at a time, for each holds a lot of text."""
    while True:
        rows = await graph.run(
            """
            MATCH (:IfcModel {id: $model_id})-[:HAS_STEP_BLOCK]->(b:StepBlock)
            WITH b LIMIT $batch DETACH DELETE b RETURN count(*) AS n
            """,
            model_id=model_id,
            batch=BLOCK_BATCH,
        )
        if not rows or int(rows[0]["n"]) < BLOCK_BATCH:
            return


async def delete_model(graph: Graph, model_id: str) -> int:
    """Remove a model's entities in batches (a re-import or a deleted document)."""
    deleted = 0
    await delete_blocks(graph, model_id)
    while True:
        rows = await graph.run(
            "MATCH (n:IfcEntity {model_id: $model_id}) WITH n LIMIT $batch DETACH DELETE n RETURN count(*) AS n",
            model_id=model_id,
            batch=BATCH,
        )
        count = int(rows[0]["n"]) if rows else 0
        deleted += count
        if count < BATCH:
            break
    await graph.run("MATCH (m:IfcModel {id: $model_id}) DETACH DELETE m", model_id=model_id)
    return deleted
