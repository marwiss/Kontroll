# This file was generated with the assistance of an AI coding tool.
"""Load converted records into the graph in batches (``UNWIND … CREATE``, no APOC)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from opencde.graph.graph import Graph

BATCH = 2_000
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")


def _safe(name: str) -> str:
    if not _IDENTIFIER.match(name):
        raise ValueError(f"unsafe identifier from converter: {name!r}")
    return name


def relationship_type(attribute: str) -> str:
    """The relationship type for an IFC attribute: upper case with underscores, as every relationship in the
    graph is written (``IsDefinedBy`` becomes ``IS_DEFINED_BY``, ``HasProperties`` ``HAS_PROPERTIES``)."""
    return _safe(_CAMEL_BOUNDARY.sub("_", _safe(attribute)).upper())


async def import_records(graph: Graph, model_id: str, records_path: Path) -> dict[str, int]:
    """Create the ``IfcEntity`` nodes and their relationships for one model. Returns counts."""
    nodes = relationships = 0
    node_groups: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    edge_groups: dict[str, list[dict[str, Any]]] = {}

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

    async def flush_edges() -> None:
        nonlocal relationships
        for rel_type, rows in edge_groups.items():
            await graph.run(
                f"UNWIND $rows AS row MATCH (a:IfcEntity {{id: row.a}}), (b:IfcEntity {{id: row.b}}) "
                f"CREATE (a)-[:{rel_type}]->(b)",
                rows=rows,
            )
            relationships += len(rows)
        edge_groups.clear()

    pending = 0
    with records_path.open(encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            kind = record["t"]
            if kind == "n":
                labels = tuple(_safe(label) for label in record["labels"])
                node_groups.setdefault(labels, []).append(
                    {"id": f"{model_id}:{record['step']}", "step": record["step"], "props": record["props"]}
                )
            elif kind == "e":
                edge_groups.setdefault(relationship_type(record["type"]), []).append(
                    {"a": f"{model_id}:{record['a']}", "b": f"{model_id}:{record['b']}"}
                )
            else:
                await flush_nodes()  # the header separates nodes from edges
                continue
            pending += 1
            if pending >= BATCH:
                await flush_nodes()
                await flush_edges()
                pending = 0
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


async def delete_model(graph: Graph, model_id: str) -> int:
    """Remove a model's entities in batches (a re-import or a deleted document)."""
    deleted = 0
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
