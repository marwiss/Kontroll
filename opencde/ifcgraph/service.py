# This file was generated with the assistance of an AI coding tool.
"""Scheduling conversions and linking BCF components to model elements.

``IfcGraphService.schedule`` records an ``IfcModel`` node (state ``queued``),
then converts in the background: the file is handed to the worker process
(``.ifczip`` is unpacked first, with a size cap), the worker's records are
imported, and the node ends in state ``done`` or ``failed`` with counts or an
error. One conversion runs at a time.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import sys
import tempfile
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, Request

from opencde.graph.graph import Graph
from opencde.ids import new_id
from opencde.ifcgraph.exporter import export_records
from opencde.ifcgraph.importer import delete_blocks, delete_model, import_records
from opencde.logging import get_logger
from opencde.settings import Settings
from opencde.storage import LocalStorage
from opencde.timeutil import later_iso, now_iso

log = get_logger(__name__)

STATE_QUEUED = "queued"
STATE_RUNNING = "running"
STATE_DONE = "done"
STATE_FAILED = "failed"
IFC_SUFFIXES = (".ifc", ".ifczip", ".ifcxml")


class IfcGraphService:
    def __init__(self, graph: Graph, storage: LocalStorage, settings: Settings) -> None:
        self.graph = graph
        self.storage = storage
        self.settings = settings
        self._tasks: set[asyncio.Task[None]] = set()
        self._lock = asyncio.Semaphore(1)

    # -- scheduling ------------------------------------------------------------------------------

    @staticmethod
    def wants(file_name: str) -> bool:
        return file_name.lower().endswith(IFC_SUFFIXES[:2])

    async def schedule(
        self,
        *,
        project_id: str,
        storage_key: str,
        file_name: str,
        document_id: str | None = None,
        version_index: int | None = None,
        bcf_document_guid: str | None = None,
    ) -> str | None:
        """Queue a conversion for an uploaded IFC file; returns the model id, or None for other files."""
        if not self.wants(file_name):
            return None
        model_id = new_id()
        await self.graph.run(
            """
            MATCH (p:Project {project_id: $project_id})
            CREATE (p)-[:HAS_MODEL]->(:IfcModel {
                id: $id, project_id: $project_id, document_id: $document_id, version_index: $version_index,
                bcf_document_guid: $bcf_document_guid, file_name: $file_name, storage_key: $storage_key,
                state: $state, created_at: $now
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
        self._start(model_id, storage_key, file_name)
        return model_id

    def _start(self, model_id: str, storage_key: str, file_name: str) -> None:
        task = asyncio.create_task(self._run(model_id, storage_key, file_name), name=f"ifcgraph-{model_id}")
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def resume_interrupted(self) -> None:
        """Start over the conversions a stopped server left behind.

        A queued model belongs to whichever server process takes it first (``_claim``). A running one may be
        running in another process, so it is given up only when twice the time limit has passed since it started.
        """
        rows = await self.graph.run(
            """
            MATCH (m:IfcModel)
            WHERE m.state = $queued OR (m.state = $running AND m.running_at < $given_up)
            RETURN m.id AS id, m.storage_key AS storage_key, m.file_name AS file_name, m.state AS state
            """,
            queued=STATE_QUEUED,
            running=STATE_RUNNING,
            given_up=later_iso(-2 * self.settings.ifcgraph_timeout_seconds),
        )
        waiting_here = {task.get_name() for task in self._tasks}
        for row in rows:
            if f"ifcgraph-{row['id']}" in waiting_here:
                continue
            if row["state"] == STATE_RUNNING:
                await delete_model_entities(self.graph, row["id"])
                await self._set_state(row["id"], STATE_QUEUED)
            log.info("ifcgraph_resumed", model_id=row["id"])
            self._start(row["id"], row["storage_key"], row["file_name"])

    async def shutdown(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        for task in list(self._tasks):
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task

    async def wait_idle(self) -> None:
        """For tests: wait until every scheduled conversion has finished."""
        while self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

    # -- the conversion ----------------------------------------------------------------------------

    async def _set_state(self, model_id: str, state: str, **fields: Any) -> None:
        await self.graph.run(
            "MATCH (m:IfcModel {id: $id}) SET m.state = $state, m += $fields",
            id=model_id,
            state=state,
            fields={**fields, f"{state}_at": now_iso()},
        )

    async def _claim(self, model_id: str) -> bool:
        rows = await self.graph.run(
            """
            MATCH (m:IfcModel {id: $id, state: $queued})
            SET m.state = $running, m.running_at = $now
            RETURN m.id AS id
            """,
            id=model_id,
            queued=STATE_QUEUED,
            running=STATE_RUNNING,
            now=now_iso(),
        )
        return bool(rows)

    async def _run(self, model_id: str, storage_key: str, file_name: str) -> None:
        async with self._lock:
            if not await self._claim(model_id):
                return
            with tempfile.TemporaryDirectory(prefix="ifcgraph-") as tmp:
                workdir = Path(tmp)
                try:
                    source = await asyncio.to_thread(self._prepare_input, storage_key, file_name, workdir)
                    records = workdir / "records.jsonl"
                    header = await self._convert(source, records)
                    counts = await import_records(self.graph, model_id, records)
                except Exception as exc:
                    log.warning("ifcgraph_failed", model_id=model_id, error=f"{type(exc).__name__}: {exc}"[:500])
                    with contextlib.suppress(Exception):
                        await delete_model_entities(self.graph, model_id)
                    await self._set_state(model_id, STATE_FAILED, error=f"{type(exc).__name__}: {exc}"[:500])
                    return
            await self._set_state(
                model_id,
                STATE_DONE,
                schema=header.get("schema"),
                ifc_project_guid=header.get("ifc_project_guid"),
                entities=counts["nodes"],
                relationships=counts["relationships"],
                skipped=header.get("skipped", 0),
                lossless=header.get("lossless", False),
                ifc_header=header.get("ifc_header"),
            )
            # Viewpoints created before the model finished (or before it was uploaded) get their links now.
            try:
                linked = await self._link_model(model_id)
            except Exception as exc:  # the import itself succeeded; linking can be repeated by a new viewpoint
                log.warning("ifcgraph_link_failed", model_id=model_id, error=f"{type(exc).__name__}: {exc}"[:200])
                linked = 0
            log.info("ifcgraph_imported", model_id=model_id, linked=linked, **counts)

    def _prepare_input(self, storage_key: str, file_name: str, workdir: Path) -> Path:
        """The IFC file to convert; an ``.ifczip`` is unpacked with a cap on the unpacked size."""
        path = self.storage.path(storage_key)
        if not file_name.lower().endswith(".ifczip"):
            return path
        limit = self.settings.max_upload_bytes
        with zipfile.ZipFile(path) as archive:
            members = [m for m in archive.infolist() if not m.is_dir() and m.filename.lower().endswith(".ifc")]
            if len(members) != 1:
                raise ValueError("an .ifczip must contain exactly one .ifc file")
            member = members[0]
            if member.file_size > limit:
                raise ValueError(f"the archived model exceeds {limit} bytes")
            target = workdir / "model.ifc"
            written = 0
            with archive.open(member) as source, target.open("wb") as out:
                while chunk := source.read(1024 * 1024):
                    written += len(chunk)
                    if written > limit:
                        raise ValueError(f"the archived model exceeds {limit} bytes")
                    out.write(chunk)
            return target

    async def _convert(self, source: Path, records: Path) -> dict[str, Any]:
        command = [
            sys.executable,
            "-m",
            "opencde.ifcgraph.worker",
            str(source),
            str(records),
            "--memory-mb",
            str(self.settings.ifcgraph_memory_mb),
            "--max-entities",
            str(self.settings.ifcgraph_max_entities),
        ]
        if self.settings.ifcgraph_include_geometry:
            command.append("--include-geometry")
        if self.settings.ifcgraph_lossless:
            command.append("--lossless")
        return json.loads((await self._in_a_process(command, "conversion")).strip().splitlines()[-1])

    async def _in_a_process(self, command: list[str], what: str, answers: tuple[int, ...] = (0,)) -> str:
        """Run a worker with the time limit. Returns what it wrote to stdout, for an exit code that is an answer."""
        process = await asyncio.create_subprocess_exec(
            *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=self.settings.ifcgraph_timeout_seconds
            )
        except TimeoutError:
            process.kill()
            await process.wait()
            raise RuntimeError(f"{what} exceeded {self.settings.ifcgraph_timeout_seconds} s") from None
        if process.returncode not in answers:
            message = stderr.decode("utf-8", "replace").strip().splitlines()
            detail = message[-1] if message else f"exit code {process.returncode}"
            with contextlib.suppress(ValueError):
                detail = json.loads(detail).get("error", detail)
            raise RuntimeError(detail)
        return stdout.decode("utf-8")

    # -- writing a model back ------------------------------------------------------------------------

    async def export(self, model_id: str, target: Path) -> int:
        """Write a model back as an IFC file from what the graph holds. Returns the number of instances."""
        with tempfile.TemporaryDirectory(prefix="ifcgraph-") as tmp:
            records = Path(tmp) / "records.jsonl"
            instances = await export_records(self.graph, model_id, records)
            await self._in_a_process(
                [
                    sys.executable,
                    "-m",
                    "opencde.ifcgraph.writer",
                    str(records),
                    str(target),
                    "--memory-mb",
                    str(self.settings.ifcgraph_memory_mb),
                ],
                "writing the file",
            )
        return instances

    async def compare_with_upload(self, model_id: str, written: Path, *, geometry: bool = False) -> dict[str, Any]:
        """Whether a file holds the same model as the one the model was converted from (``equivalence.py``)."""
        extra = ["--geometry"] if geometry else []
        return await self._with_upload(
            model_id,
            "the comparison",
            lambda source: ["opencde.ifcgraph.equivalence", str(source), str(written), *extra],
        )

    async def validate_against_upload(self, model_id: str, written: Path) -> dict[str, Any]:
        """What a file breaks of the IFC standard that the one the model was converted from does not (``validation.py``)."""
        return await self._with_upload(
            model_id,
            "the validation",
            lambda source: ["opencde.ifcgraph.validation", str(written), "--against", str(source)],
        )

    async def _with_upload(self, model_id: str, what: str, command: Callable[[Path], list[str]]) -> dict[str, Any]:
        """Run a module of this package on the uploaded file, unpacked. Exit codes 0 and 1 are both answers."""
        rows = await self.graph.run(
            "MATCH (m:IfcModel {id: $id}) RETURN m.storage_key AS storage_key, m.file_name AS file_name", id=model_id
        )
        if not rows:
            raise ValueError("there is no such model")
        with tempfile.TemporaryDirectory(prefix="ifcgraph-") as tmp:
            source = await asyncio.to_thread(
                self._prepare_input, rows[0]["storage_key"], rows[0]["file_name"], Path(tmp)
            )
            arguments = [sys.executable, "-m", *command(source), "--memory-mb", str(self.settings.ifcgraph_memory_mb)]
            return json.loads(await self._in_a_process(arguments, what, answers=(0, 1)))

    # -- linking BCF components ----------------------------------------------------------------------

    async def link_viewpoint(self, *, project_id: str, viewpoint_guid: str) -> int:
        """``SAME_AS`` from one viewpoint's components to the project's finished models, plus GTIN (at viewpoint POST)."""
        return await self._link(
            """
            MATCH (:Project {project_id: $project_id})-[:HAS_TOPIC]->(:Topic)-[:HAS_VIEWPOINT]->(v:Viewpoint {guid: $guid})
                  -[:HAS_COMPONENT]->(c:Component)
            WHERE c.ifc_guid IS NOT NULL
            MATCH (m:IfcModel {project_id: $project_id, state: 'done'})
            MATCH (e:IfcEntity {model_id: m.id, GlobalId: c.ifc_guid})
            """,
            project_id=project_id,
            guid=viewpoint_guid,
        )

    async def _link_model(self, model_id: str) -> int:
        """``SAME_AS`` from every component of the project to a model that has just finished importing."""
        return await self._link(
            """
            MATCH (m:IfcModel {id: $model_id})
            MATCH (:Project {project_id: m.project_id})-[:HAS_TOPIC]->(:Topic)-[:HAS_VIEWPOINT]->(:Viewpoint)
                  -[:HAS_COMPONENT]->(c:Component)
            WHERE c.ifc_guid IS NOT NULL
            MATCH (e:IfcEntity {model_id: m.id, GlobalId: c.ifc_guid})
            """,
            model_id=model_id,
        )

    async def _link(self, scope: str, **params: Any) -> int:
        """Merge the ``SAME_AS`` edges for the ``(c, e)`` pairs a scope matches and copy the GTIN property."""
        rows = await self.graph.run(
            scope + _LINK_TAIL,
            pset=self.settings.ifcgraph_gtin_property_set,
            prop=self.settings.ifcgraph_gtin_property,
            **params,
        )
        return int(rows[0]["linked"]) if rows else 0

    async def status(self, project_id: str) -> list[dict[str, Any]]:
        rows = await self.graph.run(
            "MATCH (m:IfcModel {project_id: $project_id}) RETURN properties(m) AS model ORDER BY m.created_at DESC",
            project_id=project_id,
        )
        return [row["model"] for row in rows]


# The shared tail of both linking queries: the edge, then the GTIN from the configured property set.
_LINK_TAIL = """
            MERGE (c)-[:SAME_AS]->(e)
            WITH c, e
            OPTIONAL MATCH (e)-[:IS_DEFINED_BY]->(:IfcRelDefinesByProperties)-[:RELATING_PROPERTY_DEFINITION]
                  ->(ps:IfcPropertySet {Name: $pset})-[:HAS_PROPERTIES]->(p:IfcPropertySingleValue {Name: $prop})
            WITH c, e, collect(p.NominalValue)[0] AS gtin
            SET c.gtin = CASE WHEN gtin IS NULL THEN c.gtin ELSE toString(gtin) END
            RETURN count(DISTINCT e) AS linked
            """


async def delete_model_entities(graph: Graph, model_id: str) -> None:
    """Remove a model's entities but keep the ``IfcModel`` node (so a failure stays visible)."""
    await delete_blocks(graph, model_id)
    while True:
        rows = await graph.run(
            "MATCH (n:IfcEntity {model_id: $model_id}) WITH n LIMIT 2000 DETACH DELETE n RETURN count(*) AS n",
            model_id=model_id,
        )
        if not rows or int(rows[0]["n"]) < 2000:
            break


def ifcgraph_service(request: Request) -> IfcGraphService | None:
    return getattr(request.app.state, "ifcgraph", None)


IfcGraphDep = Annotated[IfcGraphService | None, Depends(ifcgraph_service)]

__all__ = ["IfcGraphDep", "IfcGraphService", "delete_model", "ifcgraph_service"]
