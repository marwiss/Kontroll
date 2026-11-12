# This file was generated with the assistance of an AI coding tool.
"""A building of one model brought into another model's project, as the next version of its document (IFC-LPG F21 a
and F22 a, ADR 0025).

IFC-LPG's ``merge_report`` says what bringing the building of model B into the project of model A would do: what
comes along, which objects both have with a GlobalId, whether their content is the same, and the choice that holds
for each (``a``, ``b`` or ``new``). ``merge_building`` makes the merged model C in the graph and checks it against A
and B. Here a ``manager`` of A's project runs it as a job: C is written out as a file, the file becomes the next
version of A's document, with A's version as its parent, and is converted and checked as an upload is; C itself is
then taken out of the graph again, and A and B do not change.

Where B's schema or length unit is not A's, ``prepare_other`` first makes a copy of B migrated to A's schema and
with its lengths in A's unit (IFC-LPG F25 a), as a job of its own whose model stands in for B in the report and the
merge for a day, and is then taken out by the cleanup. What A's schema has no equivalent of ends the job in
``conflict`` with the problems and the options for each, until the caller chooses with ``resolutions`` (IFC-LPG
F32, ``RESOLUTIONS``); a copy with issues that B did not have is not made, and the job fails with them (F33 a).
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ifc_lpg.files import Limits
from ifc_lpg.importer import delete_model
from ifc_lpg.merge import (
    RESOLUTIONS,
    MergeConflict,
    MergeError,
    PrepareConflict,
    PrepareError,
    merge_building,
    merge_report,
    prepare_other,
)
from ifc_lpg.validation import pack_report, unpack_report

from opencde.documents.schemas import DocumentMetadataEntry
from opencde.ids import new_id
from opencde.logging import get_logger
from opencde.storage import make_key
from opencde.store.documents.versions import DocumentRepository, default_metadata
from opencde.timeutil import later_iso, now_iso

if TYPE_CHECKING:
    from opencde.ifcgraph.service import IfcGraphService

log = get_logger(__name__)

STATE_QUEUED = "queued"
STATE_RUNNING = "running"
STATE_DONE = "done"
STATE_FAILED = "failed"
STATE_CONFLICT = "conflict"  # objects of both models differ, and no choice was made for them
STATE_EXPIRED = "expired"  # a prepared model taken out again
KIND_MERGE = "merge"
KIND_PREPARE = "prepare"  # B made ready for A: migrated to its schema, with its lengths in its unit
PREPARED_SECONDS = 24 * 3600  # how long a prepared model stands in for B
__all__ = ["RESOLUTIONS"]  # the choices a preparation takes, as IFC-LPG names them


def limits_of(service: IfcGraphService) -> Limits:
    settings = service.settings
    return Limits(
        timeout_seconds=float(settings.ifcgraph_timeout_seconds),
        memory_mb=int(settings.ifcgraph_memory_mb),
        max_entities=int(settings.ifcgraph_max_entities),
    )


async def report(service: IfcGraphService, request: dict[str, Any]) -> dict[str, Any]:
    """What the merge would do, without making anything; :class:`MergeError` when it cannot be made at all."""
    return await merge_report(
        service.graph,
        request["base"]["model_id"],
        request["other"]["model_id"],
        request["building"],
        site=request.get("site"),
        choices=request.get("choices") or {},
        default=request.get("default"),
    )


async def schedule(
    service: IfcGraphService, *, project_id: str, author: str, request: dict[str, Any], kind: str = KIND_MERGE
) -> str:
    """Queue a merge into a project, or the preparation of B for one (``kind``); returns the job's id."""
    merge_id = new_id()
    await service.store.run(
        """
        MATCH (p:Project {project_id: $project_id})
        CREATE (p)-[:HAS_MERGE]->(:Merge {
            id: $id, project_id: $project_id, kind: $kind, state: $state, request: $request, author: $author,
            created_at: $now
        })
        """,
        project_id=project_id,
        id=merge_id,
        kind=kind,
        state=STATE_QUEUED,
        request=json.dumps(request, separators=(",", ":")),
        author=author,
        now=now_iso(),
    )
    _start(service, merge_id)
    return merge_id


def _start(service: IfcGraphService, merge_id: str) -> None:
    task = asyncio.create_task(run(service, merge_id), name=f"ifcmerge-{merge_id}")
    service._tasks.add(task)
    task.add_done_callback(service._tasks.discard)


async def _set(service: IfcGraphService, merge_id: str, state: str, **fields: Any) -> None:
    await service.store.run(
        "MATCH (j:Merge {id: $id}) SET j.state = $state, j += $fields",
        id=merge_id,
        state=state,
        fields={"finished_at": now_iso(), **fields},
    )


async def run(service: IfcGraphService, merge_id: str) -> None:
    """Run one queued merge: make C, write it out, make it the next version of A's document, and take C out again."""
    async with service._lock:
        model_id = new_id()  # C, in the graph until it is written out
        rows = await service.store.run(
            """
            MATCH (j:Merge {id: $id, state: $queued})
            SET j.state = $running, j.running_at = $now, j.model_id = $model_id
            RETURN j.project_id AS project_id, j.request AS request, j.author AS author, j.kind AS kind
            """,
            id=merge_id,
            queued=STATE_QUEUED,
            running=STATE_RUNNING,
            now=now_iso(),
            model_id=model_id,
        )
        if not rows:
            return
        project_id, author = str(rows[0]["project_id"]), str(rows[0]["author"])
        request = json.loads(rows[0]["request"])
        if rows[0]["kind"] == KIND_PREPARE:
            await _prepare(service, merge_id, request, model_id)
            return
        try:
            merged = await merge_building(
                service.graph,
                request["base"]["model_id"],
                request["other"]["model_id"],
                request["building"],
                model_id,
                site=request.get("site"),
                choices=request.get("choices") or {},
                default=request.get("default"),
                limits=limits_of(service),
            )
        except MergeConflict as exc:
            await _set(service, merge_id, STATE_CONFLICT, report=pack_report([exc.report]))
            log.info("ifc_merge_conflict", merge_id=merge_id)
            await _drop(service, model_id)
            return
        except Exception as exc:
            await _set(service, merge_id, STATE_FAILED, error=f"{type(exc).__name__}: {exc}"[:500])
            log.warning("ifc_merge_failed", merge_id=merge_id, error=type(exc).__name__)
            await _drop(service, model_id)
            return
        try:
            version_index = await _as_version(service, project_id, author, request, model_id, merged)
        except Exception as exc:
            await _set(service, merge_id, STATE_FAILED, error=f"{type(exc).__name__}: {exc}"[:500])
            log.warning("ifc_merge_version_failed", merge_id=merge_id, error=type(exc).__name__)
            return
        finally:
            await _drop(service, model_id)
        merged.pop("model", None)
        await _set(service, merge_id, STATE_DONE, version_index=version_index, report=pack_report([merged]))
        log.info("ifc_merge_done", merge_id=merge_id, version_index=version_index)


async def _prepare(service: IfcGraphService, merge_id: str, request: dict[str, Any], model_id: str) -> None:
    """B migrated to A's schema and with its lengths in A's unit, as the model ``model_id``, for a day; ``conflict``
    with the problems and their options when a choice is needed, ``failed`` with the new issues when the copy has
    issues B did not have."""
    try:
        prepared = await prepare_other(
            service.graph,
            request["other"]["model_id"],
            model_id,
            base_id=request["base"]["model_id"],
            resolutions=request.get("resolutions") or None,
            limits=limits_of(service),
        )
    except PrepareConflict as exc:
        await _set(service, merge_id, STATE_CONFLICT, report=pack_report([exc.report]))
        log.info("ifc_merge_prepare_conflict", merge_id=merge_id, problems=len(exc.report.get("problems") or []))
        await _drop(service, model_id)
        return
    except PrepareError as exc:
        await _set(service, merge_id, STATE_FAILED, error=str(exc)[:500], report=pack_report([exc.report]))
        log.info("ifc_merge_prepare_refused", merge_id=merge_id, new=int(exc.report.get("new_count") or 0))
        await _drop(service, model_id)
        return
    except Exception as exc:
        await _set(service, merge_id, STATE_FAILED, error=f"{type(exc).__name__}: {exc}"[:500])
        log.warning("ifc_merge_prepare_failed", merge_id=merge_id, error=type(exc).__name__)
        await _drop(service, model_id)
        return
    prepared.pop("model", None)
    await _set(service, merge_id, STATE_DONE, expires_at=later_iso(PREPARED_SECONDS), report=pack_report([prepared]))
    log.info("ifc_merge_prepared", merge_id=merge_id)


async def prepared(
    service: IfcGraphService, *, user_id: str, project_id: str, prepare_id: str
) -> dict[str, Any] | None:
    """A preparation of this project that is done and has not expired: its model's id and what it was asked for."""
    row = await service.store.one(
        """
        MATCH (:User {id: $user_id})-[:MEMBER_OF]->(:Project {project_id: $project_id})
              -[:HAS_MERGE]->(j:Merge {id: $id, kind: $kind, state: $done})
        WHERE j.expires_at > $now
        RETURN j.model_id AS model_id, j.request AS request
        """,
        user_id=user_id,
        project_id=project_id,
        id=prepare_id,
        kind=KIND_PREPARE,
        done=STATE_DONE,
        now=now_iso(),
    )
    return {"model_id": row["model_id"], "request": json.loads(row["request"])} if row else None


async def _drop(service: IfcGraphService, model_id: str) -> None:
    """C out of the graph: its file is the version now, and the version gets a model of its own when converted."""
    with contextlib.suppress(Exception):
        await delete_model(service.graph, model_id)


async def _as_version(
    service: IfcGraphService,
    project_id: str,
    author: str,
    request: dict[str, Any],
    model_id: str,
    merged: dict[str, Any],
) -> int:
    """C written out as the next version of A's document, when the document has not moved on since A's version."""
    base = request["base"]
    documents = DocumentRepository(service.store)
    latest = await service.store.one(
        """
        MATCH (:Project {project_id: $project_id})-[:HAS_DOCUMENT]->(:Document {document_id: $document_id})
              -[:HAS_VERSION]->(v:DocumentVersion)
        RETURN v.version_index AS version_index, v.title AS title, v.file_name AS file_name
        ORDER BY v.version_index DESC LIMIT 1
        """,
        project_id=project_id,
        document_id=base["document_id"],
    )
    if latest is None:
        raise MergeError("the base document is gone")
    if int(latest["version_index"]) != int(base["version_index"]):
        raise MergeError(
            f"the document's latest version is {latest['version_index']}, not version {base['version_index']} that "
            "the merge builds on; merge into the latest"
        )
    key = make_key("documents", new_id())
    with tempfile.TemporaryDirectory(prefix="ifcmerge-") as tmp:
        written = Path(tmp) / "merged.ifc"
        await service.export(model_id, written)
        size, sha256 = await asyncio.to_thread(_copy_hashed, service, written, key)
    project_name = await service.store.one(
        "MATCH (p:Project {project_id: $project_id}) RETURN p.name AS name", project_id=project_id
    )
    metadata = default_metadata(
        file_name=str(latest["file_name"]),
        size_in_bytes=size,
        sha256=sha256,
        author=author,
        project_name=str((project_name or {}).get("name") or ""),
    )
    other = request["other"]
    metadata += [
        DocumentMetadataEntry(name="base_version_index", value=[str(base["version_index"])], data_type="integer32"),
        DocumentMetadataEntry(name="merged_from_document", value=[str(other["document_id"])], data_type="string"),
        DocumentMetadataEntry(name="merged_from_version", value=[str(other["version_index"])], data_type="integer32"),
        DocumentMetadataEntry(name="merged_building", value=[str(request["building"])], data_type="string"),
        DocumentMetadataEntry(name="approved_by", value=[author], data_type="string"),
    ]
    try:
        record = await documents.create_version(
            project_id=project_id,
            document_id=str(base["document_id"]),
            title=str(latest["title"]),
            version_number=str(int(base["version_index"]) + 1),
            file_name=str(latest["file_name"]),
            size_in_bytes=size,
            sha256=sha256,
            storage_key=key,
            author=author,
            metadata=metadata,
            parent_version_index=int(base["version_index"]),
            approved_by=author,
        )
    except BaseException:
        service.storage.delete(key)
        raise
    await service.schedule(
        project_id=project_id,
        storage_key=record.storage_key,
        file_name=record.file_name,
        document_id=record.document_id,
        version_index=record.version_index,
        version_id=record.version_id,
    )
    return record.version_index


def _copy_hashed(service: IfcGraphService, source: Path, key: str) -> tuple[int, str]:
    digest = hashlib.sha256()
    with source.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return service.storage.copy_in(source, key), digest.hexdigest()


async def job(service: IfcGraphService, *, user_id: str, project_id: str, merge_id: str) -> dict[str, Any] | None:
    """One merge, when the user is a member of its project."""
    row = await service.store.one(
        """
        MATCH (:User {id: $user_id})-[:MEMBER_OF]->(:Project {project_id: $project_id})-[:HAS_MERGE]->(j:Merge {id: $id})
        RETURN properties(j) AS merge
        """,
        user_id=user_id,
        project_id=project_id,
        id=merge_id,
    )
    if row is None:
        return None
    node = dict(row["merge"])
    request = json.loads(node.get("request") or "{}")
    found = unpack_report(node.get("report"))
    return {
        "merge_id": node["id"],
        "kind": node.get("kind") or KIND_MERGE,
        "state": node["state"],
        "expires_at": node.get("expires_at"),
        "author": node.get("author"),
        "created_at": node.get("created_at"),
        "finished_at": node.get("finished_at"),
        "base": {key: request["base"][key] for key in ("document_id", "version_index")} if request else None,
        "other": {key: request["other"][key] for key in ("project_id", "document_id", "version_index")}
        if request
        else None,
        "building": request.get("building"),
        "resolutions": request.get("resolutions") if node.get("kind") == KIND_PREPARE else None,
        "version_index": node.get("version_index"),
        "error": node.get("error"),
        "report": found[0] if found else None,
    }


async def resume(service: IfcGraphService) -> None:
    """After a stop: a job that was running is failed and its model taken out, and a queued one starts. Each round,
    a prepared model whose day is over is taken out too."""
    given_up = later_iso(-2 * float(service.settings.ifcgraph_timeout_seconds))
    expired = await service.store.run(
        "MATCH (j:Merge {kind: $kind, state: $done}) WHERE j.expires_at <= $now RETURN j.id AS id, j.model_id AS model_id",
        kind=KIND_PREPARE,
        done=STATE_DONE,
        now=now_iso(),
    )
    for row in expired:
        await _drop(service, str(row["model_id"]))
        await _set(service, str(row["id"]), STATE_EXPIRED)
    rows = await service.store.run(
        """
        MATCH (j:Merge)
        WHERE j.state = $queued OR (j.state = $running AND j.running_at < $given_up)
        RETURN j.id AS id, j.state AS state, j.model_id AS model_id
        """,
        queued=STATE_QUEUED,
        running=STATE_RUNNING,
        given_up=given_up,
    )
    waiting_here = {task.get_name() for task in service._tasks}
    for row in rows:
        if f"ifcmerge-{row['id']}" in waiting_here:
            continue
        if row["state"] == STATE_RUNNING:
            if row["model_id"]:
                await _drop(service, str(row["model_id"]))
            await _set(service, str(row["id"]), STATE_FAILED, error="the server stopped while the merge was running")
            continue
        _start(service, str(row["id"]))
