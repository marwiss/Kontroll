# This file was generated with the assistance of an AI coding tool.
"""Housekeeping of imported models for the ``opencde ifcgraph`` commands.

Every upload of an IFC file adds a ``Conversion`` and a model with its entities, so a project
that receives new versions (or a test suite that uploads the same file again
and again) accumulates graphs nobody queries. ``prune_models`` removes the
models that failed and the finished models superseded by a newer finished one
of the same document; queued and running models are never touched, and the
documents and their files stay. ``everything`` empties a whole project.
``delete_project`` deletes a project's models in the IFC graph, and then the
project with what it owns in the store (ADR 0027).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ifc_lpg.importer import delete_model

from opencde.graph.graph import Graph
from opencde.storage import LocalStorage
from opencde.store.jobs.conversions import ConversionRepository

if TYPE_CHECKING:
    from opencde.store.protocols import ProjectStore


def delete_geometry(storage: LocalStorage, model_id: str) -> int:
    """Delete a model's geometry records and the glTF files built from them. Returns how many files went."""
    gone = 0
    for key in list(storage.iter_keys("geometry")):
        if key.startswith(f"geometry/{model_id}."):
            storage.delete(key)
            gone += 1
    return gone


async def list_models(graph: Graph, *, project_id: str | None = None) -> list[dict[str, Any]]:
    return await ConversionRepository(graph).all(project_id=project_id)


async def superseded_or_failed(graph: Graph, *, project_id: str | None = None) -> list[str]:
    """Ids of the models to drop: every failed one, and every finished one that a newer finished conversion of the
    same document (Documents API ``document_id`` or BCF ``bcf_document_guid``) has replaced."""
    return await ConversionRepository(graph).superseded_or_failed(project_id=project_id)


async def prune_models(
    graph: Graph,
    *,
    store: Graph | None = None,
    project_id: str | None = None,
    everything: bool = False,
    storage: LocalStorage | None = None,
) -> dict[str, int]:
    """Delete models from the IFC graph ``graph``, their conversions from the ``store`` (the IFC graph itself when
    none is given) and their geometry files; returns ``{"models": n, "entities": n}``."""
    store = store or graph
    if everything:
        if project_id is None:
            raise ValueError("deleting every model needs a project")
        ids = [model["id"] for model in await list_models(store, project_id=project_id)]
    else:
        ids = await superseded_or_failed(store, project_id=project_id)
    conversions = ConversionRepository(store)
    entities = 0
    for model_id in ids:
        entities += await delete_model(graph, model_id)
        await conversions.delete(model_id)
        if storage is not None:
            delete_geometry(storage, model_id)
    return {"models": len(ids), "entities": entities}


async def delete_project(projects: ProjectStore, graph: Graph, project_id: str, storage: LocalStorage) -> bool:
    """A project's models in the IFC graph ``graph``, in batches of their own (the entities of a model reach far beyond
    what the store's deletion follows, and they live in the other graph), and then the project, what it owns and its
    stored files in the store behind ``projects``. Returns whether the project was there."""
    for model_id in await projects.model_ids(project_id):
        await delete_model(graph, model_id)
    return await projects.delete_with_files(project_id, storage)
