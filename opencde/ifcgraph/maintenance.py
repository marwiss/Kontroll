# This file was generated with the assistance of an AI coding tool.
"""Housekeeping of imported models for the ``opencde ifcgraph`` commands.

Every upload of an IFC file adds an ``IfcModel`` with its entities, so a project
that receives new versions (or a test suite that uploads the same file again
and again) accumulates graphs nobody queries. ``prune_models`` removes the
models that failed and the finished models superseded by a newer finished one
of the same document; queued and running models are never touched, and the
documents and their files stay. ``everything`` empties a whole project.
"""

from __future__ import annotations

from typing import Any

from opencde.graph.graph import Graph
from opencde.ifcgraph.importer import delete_model


async def list_models(graph: Graph, *, project_id: str | None = None) -> list[dict[str, Any]]:
    rows = await graph.run(
        """
        MATCH (m:IfcModel) WHERE $project IS NULL OR m.project_id = $project
        RETURN properties(m) AS model ORDER BY m.project_id, m.created_at
        """,
        project=project_id,
    )
    return [row["model"] for row in rows]


async def superseded_or_failed(graph: Graph, *, project_id: str | None = None) -> list[str]:
    """Ids of the models to drop: every failed one, and every finished one that a newer finished model of the
    same document (Documents API ``document_id`` or BCF ``bcf_document_guid``) has replaced."""
    rows = await graph.run(
        """
        MATCH (m:IfcModel)
        WHERE ($project IS NULL OR m.project_id = $project) AND m.state IN ['done', 'failed']
        WITH coalesce(m.document_id, m.bcf_document_guid, m.id) AS doc, m
        ORDER BY CASE WHEN m.state = 'done' THEN 0 ELSE 1 END, coalesce(m.version_index, 0) DESC,
                 coalesce(m.done_at, m.created_at) DESC
        WITH doc, collect(m) AS models
        WITH [x IN models[1..] | x.id] AS older, CASE WHEN models[0].state = 'done' THEN [] ELSE [models[0].id] END AS failed
        UNWIND older + failed AS id
        RETURN DISTINCT id
        """,
        project=project_id,
    )
    return [row["id"] for row in rows]


async def prune_models(graph: Graph, *, project_id: str | None = None, everything: bool = False) -> dict[str, int]:
    """Delete models and their entities; returns ``{"models": n, "entities": n}``."""
    if everything:
        if project_id is None:
            raise ValueError("deleting every model needs a project")
        ids = [model["id"] for model in await list_models(graph, project_id=project_id)]
    else:
        ids = await superseded_or_failed(graph, project_id=project_id)
    entities = 0
    for model_id in ids:
        entities += await delete_model(graph, model_id)
    return {"models": len(ids), "entities": entities}
