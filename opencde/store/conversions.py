# This file was generated with the assistance of an AI coding tool.
"""The server's record of a conversion: one per IFC document version, or BCF project document, turned into a model
of the graph, kept apart from the model itself (IFC-LPG's F38 a, step two).

The library keeps the ``Model`` node and what it knows of it; the server keeps ``Conversion`` under the project:
the file it came from, the lifecycle (``queued``, ``running``, ``done``, ``failed``) with its timestamps, the key of
the geometry records, the findings of the graph check, and a copy of the import's facts once it is done, so that a
listing needs no look into the model. ``model_id`` names the model, which bears the same id, and nothing else
joins the two, so that they can live in different databases (F24 a). No statement here touches the model.
"""

from __future__ import annotations

from typing import Any

from opencde.graph.graph import Graph
from opencde.logging import get_logger
from opencde.timeutil import now_iso

log = get_logger(__name__)

STATE_QUEUED = "queued"
STATE_RUNNING = "running"
STATE_DONE = "done"
STATE_FAILED = "failed"

#: The import's facts a finished conversion copies from the library's answer, for listings without the model.
FACTS = (
    "schema",
    "ifc_project_guid",
    "entities",
    "relationships",
    "skipped",
    "lossless",
    "geometry",
    "ifc_header",
    "form_version",
    "format",
)
#: What the geometry pass put on the model, copied the same way once the pass is over.
SPATIAL_FACTS = ("spatial_at", "spatial_products", "spatial_failed")
#: What the server kept on ``Model`` before 2026-11-11, moved to ``Conversion`` at startup (:func:`migrate_models`).
#: ``state`` stays on those models: IFC-LPG 1.x counts a model whole by it when ``imported_at`` is missing.
MOVED = (
    "project_id",
    "document_id",
    "version_index",
    "bcf_document_guid",
    "file_name",
    "storage_key",
    "created_at",
    "running_at",
    "done_at",
    "failed_at",
    "error",
    "geometry_key",
    "spatial_pending",
    "spatial_error",
    "graph_report",
    "graph_issue_count",
    "graph_error_count",
    "graph_ruleset",
    "graph_checked_at",
    "merge_of",
)
_REMOVABLE = frozenset({"spatial_pending"})
BATCH = 500


class ConversionRepository:
    """The conversions of the projects, by the model's id."""

    def __init__(self, graph: Graph) -> None:
        self.graph = graph

    async def create(
        self,
        *,
        project_id: str,
        model_id: str,
        file_name: str,
        storage_key: str,
        document_id: str | None = None,
        version_index: int | None = None,
        bcf_document_guid: str | None = None,
    ) -> None:
        await self.graph.run(
            """
            MATCH (p:Project {project_id: $project_id})
            CREATE (p)-[:HAS_CONVERSION]->(:Conversion {
                id: $id, model_id: $id, project_id: $project_id, document_id: $document_id,
                version_index: $version_index, bcf_document_guid: $bcf_document_guid, file_name: $file_name,
                storage_key: $storage_key, state: $state, created_at: $now
            })
            """,
            project_id=project_id,
            id=model_id,
            document_id=document_id,
            version_index=version_index,
            bcf_document_guid=bcf_document_guid,
            file_name=file_name,
            storage_key=storage_key,
            state=STATE_QUEUED,
            now=now_iso(),
        )

    async def claim(self, model_id: str) -> bool:
        rows = await self.graph.run(
            """
            MATCH (c:Conversion {id: $id, state: $queued})
            SET c.state = $running, c.running_at = $now
            RETURN c.id AS id
            """,
            id=model_id,
            queued=STATE_QUEUED,
            running=STATE_RUNNING,
            now=now_iso(),
        )
        return bool(rows)

    async def set_state(self, model_id: str, state: str, **fields: Any) -> None:
        await self.graph.run(
            "MATCH (c:Conversion {id: $id}) SET c.state = $state, c += $fields",
            id=model_id,
            state=state,
            fields={**fields, f"{state}_at": now_iso()},
        )

    async def set_fields(self, model_id: str, **fields: Any) -> None:
        await self.graph.run("MATCH (c:Conversion {id: $id}) SET c += $fields", id=model_id, fields=fields)

    async def remove_field(self, model_id: str, name: str) -> None:
        if name not in _REMOVABLE:
            raise ValueError(f"not a field that is removed: {name}")
        await self.graph.run(f"MATCH (c:Conversion {{id: $id}}) REMOVE c.{name}", id=model_id)

    async def get(self, model_id: str) -> dict[str, Any] | None:
        row = await self.graph.one("MATCH (c:Conversion {id: $id}) RETURN properties(c) AS c", id=model_id)
        return dict(row["c"]) if row else None

    async def of_project(self, project_id: str) -> list[dict[str, Any]]:
        rows = await self.graph.run(
            "MATCH (c:Conversion {project_id: $project_id}) RETURN properties(c) AS c ORDER BY c.created_at DESC",
            project_id=project_id,
        )
        return [dict(row["c"]) for row in rows]

    async def done_model_ids(self, project_id: str) -> list[str]:
        rows = await self.graph.run(
            "MATCH (c:Conversion {project_id: $project_id, state: $done}) RETURN c.model_id AS id",
            project_id=project_id,
            done=STATE_DONE,
        )
        return [str(row["id"]) for row in rows]

    async def latest_of_version(
        self, *, document_id: str, version_index: int, done_only: bool = True
    ) -> dict[str, Any] | None:
        """The newest conversion of a document version, finished when ``done_only``."""
        row = await self.graph.one(
            "MATCH (c:Conversion {document_id: $document_id, version_index: $version_index})\n"
            + ("WHERE c.state = $done\n" if done_only else "")
            + "RETURN properties(c) AS c ORDER BY c.created_at DESC LIMIT 1",
            document_id=document_id,
            version_index=version_index,
            done=STATE_DONE,
        )
        return dict(row["c"]) if row else None

    async def for_member(
        self,
        *,
        user_id: str,
        document_id: str,
        version_index: int,
        project_id: str | None = None,
        done_only: bool = False,
    ) -> dict[str, Any] | None:
        """The newest conversion of a document version in a project the user is a member of."""
        conditions = ["TRUE"]
        if project_id is not None:
            conditions.append("p.project_id = $project_id")
        if done_only:
            conditions.append("c.state = $done")
        row = await self.graph.one(
            "MATCH (:User {id: $user_id})-[:MEMBER_OF]->(p:Project)\n"
            "      -[:HAS_CONVERSION]->(c:Conversion {document_id: $document_id, version_index: $version_index})\n"
            "WHERE " + " AND ".join(conditions) + "\n"
            "RETURN properties(c) AS c ORDER BY c.created_at DESC LIMIT 1",
            user_id=user_id,
            document_id=document_id,
            version_index=version_index,
            project_id=project_id,
            done=STATE_DONE,
        )
        return dict(row["c"]) if row else None

    async def interrupted(self, *, given_up: str) -> list[dict[str, Any]]:
        """The conversions a stopped server left behind: queued, or running since before ``given_up``."""
        rows = await self.graph.run(
            """
            MATCH (c:Conversion)
            WHERE (c.state = $queued OR (c.state = $running AND c.running_at < $given_up)) AND c.merge_of IS NULL
            RETURN properties(c) AS c
            """,
            queued=STATE_QUEUED,
            running=STATE_RUNNING,
            given_up=given_up,
        )
        return [dict(row["c"]) for row in rows]

    async def spatial_interrupted(self, *, given_up: str) -> None:
        """A geometry pass a stopped server left pending is given up."""
        await self.graph.run(
            """
            MATCH (c:Conversion {state: $done}) WHERE c.spatial_pending IS NOT NULL AND c.done_at < $given_up
            REMOVE c.spatial_pending SET c.spatial_error = 'the geometry pass was interrupted'
            """,
            done=STATE_DONE,
            given_up=given_up,
        )

    async def model_ids_of_document(self, document_id: str) -> list[str]:
        rows = await self.graph.run(
            "MATCH (c:Conversion {document_id: $document_id}) RETURN c.model_id AS id", document_id=document_id
        )
        return [str(row["id"]) for row in rows]

    async def all(self, *, project_id: str | None = None) -> list[dict[str, Any]]:
        rows = await self.graph.run(
            """
            MATCH (c:Conversion) WHERE $project IS NULL OR c.project_id = $project
            RETURN properties(c) AS c ORDER BY c.project_id, c.created_at
            """,
            project=project_id,
        )
        return [dict(row["c"]) for row in rows]

    async def superseded_or_failed(self, *, project_id: str | None = None) -> list[str]:
        """Ids of the models to drop: every failed one, and every finished one that a newer finished conversion of
        the same document (Documents API ``document_id`` or BCF ``bcf_document_guid``) has replaced."""
        rows = await self.graph.run(
            """
            MATCH (c:Conversion)
            WHERE ($project IS NULL OR c.project_id = $project) AND c.state IN ['done', 'failed']
            WITH coalesce(c.document_id, c.bcf_document_guid, c.id) AS doc, c
            ORDER BY CASE WHEN c.state = 'done' THEN 0 ELSE 1 END, coalesce(c.version_index, 0) DESC,
                     coalesce(c.done_at, c.created_at) DESC
            WITH doc, collect(c) AS conversions
            WITH [x IN conversions[1..] | x.id] AS older,
                 CASE WHEN conversions[0].state = 'done' THEN [] ELSE [conversions[0].id] END AS failed
            UNWIND older + failed AS id
            RETURN DISTINCT id
            """,
            project=project_id,
        )
        return [str(row["id"]) for row in rows]

    async def delete(self, model_id: str) -> None:
        await self.graph.run("MATCH (c:Conversion {id: $id}) DETACH DELETE c", id=model_id)

    async def counts_per_project(self) -> dict[str, int]:
        rows = await self.graph.run("MATCH (c:Conversion) RETURN c.project_id AS project_id, count(c) AS n")
        return {str(row["project_id"] or ""): int(row["n"]) for row in rows}


_MOVE = ", ".join(f"{name}: m.{name}" for name in MOVED)
_FACTS = ", ".join(f"{name}: m.{name}" for name in FACTS)
_STRIP = ", ".join(f"m.{name}" for name in MOVED)


async def migrate_models(graph: Graph) -> int:
    """Give the models earlier releases kept the server's record: a ``Conversion`` under the project with what the
    server had put on the ``Model``, and the model left with the library's own and its
    ``state``. A model without a project (the working copy's) only loses the server's properties. In batches,
    idempotent and cheap once done. Returns how many models changed."""
    changed = 0
    for statement in (
        "MATCH (p:Project)-[r:HAS_MODEL]->(m:Model) WITH p, r, m LIMIT $batch "
        f"CREATE (p)-[:HAS_CONVERSION]->(c:Conversion {{id: m.id, model_id: m.id, state: m.state, {_MOVE}, {_FACTS}}}) "
        f"DELETE r REMOVE {_STRIP} RETURN count(*) AS n",
        f"MATCH (m:Model) WHERE m.project_id IS NOT NULL WITH m LIMIT $batch REMOVE {_STRIP} RETURN count(*) AS n",
    ):
        while True:
            rows = await graph.run(statement, batch=BATCH)
            done = int(rows[0]["n"]) if rows else 0
            changed += done
            if done < BATCH:
                break
    if changed:
        log.info("models_given_conversions", models=changed)
    return changed
