# This file was generated with the assistance of an AI coding tool.
"""Scheduling conversions and checks of uploads, and linking BCF components to model elements.

``IfcGraphService.schedule`` records a ``Conversion`` (state ``queued``),
then converts in the background: the file is handed to the worker process
(``.ifczip`` is unpacked first, with a size cap), the worker's records are
imported, and the record ends in state ``done`` or ``failed`` with counts or an
error. A file uploaded as a document version is also checked against the IFC
schema (``validation.py``), with the result on a ``Validation`` node below
the version, which the Documents API shows (ADR 0011), against buildingSMART's
rules where they are installed (ADR 0012), against the IDS documents of its
project (ADR 0015), and against buildingSMART's Data Dictionary when enabled
(OB-42, ``bsdd.py``). Two versions are compared for clashes on request, in the
same worker pattern (ADR 0019, ``clash.py``). One job runs at a time, the check
of a file before its conversion.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import importlib.metadata
import json
import re
import sys
import tempfile
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, Request
from ifc_lpg.exporter import NotExportable, export_records
from ifc_lpg.gherkin_install import MANIFEST
from ifc_lpg.graph import rebuild_point_indexes
from ifc_lpg.importer import delete_model, import_records, model_facts, models
from ifc_lpg.paths import PathError, canonical_path, resolve, unreachable
from ifc_lpg.queries import MAX_GLOBAL_IDS, property_values
from ifc_lpg.spatial import geometry_issues, import_spatial
from ifc_lpg.validation import MAX_REPORTED, pack_report, unpack_report

from opencde.admin.graph_query import ReadingGraph
from opencde.graph.graph import Graph
from opencde.graph.schema import SchemaGraph, library_dialect
from opencde.ids import new_id
from opencde.ifcgraph import merging
from opencde.ifcgraph.bsdd import BsddClient, BsddUnavailable
from opencde.ifcgraph.bsdd import check as check_bsdd
from opencde.ifcgraph.bsdd import ruleset as bsdd_ruleset
from opencde.ifcgraph.gltf import LODS, build_glb
from opencde.logging import get_logger
from opencde.settings import Settings
from opencde.storage import LocalStorage, make_key
from opencde.store.accounts.teams import TeamRepository
from opencde.store.jobs.conversions import (
    FACTS,
    SPATIAL_FACTS,
    STATE_DONE,
    STATE_FAILED,
    STATE_QUEUED,
    STATE_RUNNING,
    ConversionRepository,
)
from opencde.store.protocols import ConversionStore
from opencde.timeutil import later_iso, now_iso

log = get_logger(__name__)

STATE_CLEAN = "clean"  # a proposal whose every change applied, with no finding the base lacks
STATE_ISSUES = "issues"
STATE_APPROVED = "approved"  # a clean proposal that became a version
IFC_SUFFIXES = (".ifc", ".ifczip", ".ifcxml")
IDS_SUFFIX = ".ids"
# The IDS documents of one project an upload is checked against, and the specifications its report keeps (ADR 0015).
MAX_IDS_DOCUMENTS = 50
MAX_RECHECKS = 500  # the IFC documents of a project checked again at once when its IDS changes (OB-43.1)
PRECHECK_SECONDS = 24 * 3600  # a file checked without becoming a version is kept this long (ADR 0021)
MAX_SPECIFICATIONS = 1_000


def _failure(exc: Exception) -> dict[str, Any]:
    """The fields of a check that could not run; the message is cut, as it may quote the file."""
    return {"checked_at": now_iso(), "error": f"{type(exc).__name__}: {exc}"[:300]}


def _issue_key(issue: dict[str, Any]) -> tuple[Any, ...]:
    """What makes a finding the same one in the base and in the proposal: the GlobalId where there is one, and the
    attribute, which tells apart the properties of one set that bSDD does not list (OB-42)."""
    return (
        issue.get("kind"),
        issue.get("rule"),
        issue.get("attribute"),
        issue.get("global_id") or str(issue.get("message", ""))[:200],
    )


def _made(checks: Any, name: str) -> bool:
    """Whether the stored checks of a report include the check ``name``, made."""
    try:
        made = json.loads(checks) if isinstance(checks, str) else []
        return any(check.get("name") == name and check.get("state") == STATE_DONE for check in made)
    except (ValueError, AttributeError):
        return False


def _ids_ruleset() -> str:
    """What checks against IDS, also when the check could not be run."""
    try:
        return f"IfcTester {importlib.metadata.version('ifctester')}: IDS 1.0"
    except importlib.metadata.PackageNotFoundError:
        return "IfcTester: IDS 1.0"


def _ruleset_of(env: Path) -> str:
    """The name the installer gave the rules in ``env``, also when the rules could not be run there."""
    try:
        return str(json.loads((env / MANIFEST).read_text(encoding="utf-8"))["ruleset"])
    except (OSError, ValueError, KeyError, TypeError):
        return "ifc-gherkin-rules"


GRAPH_RULESET = "IFC-LPG: the instances no GlobalId reaches, and the shapes of the geometry pass"


def _unreached_issue(node: dict[str, Any]) -> dict[str, Any]:
    """An instance that no GlobalId reaches, as a warning of the report: only its STEP id names it, so that a change
    set can address it by that number alone, and removing it changes nothing that a GlobalId names."""
    return {
        "kind": "reachability",
        "severity": "warning",
        "message": f"No GlobalId reaches this {node.get('ifc_class') or 'instance'}, forward or backward; only its "
        "STEP id names it.",
        "step_id": int(node["step"]),
    }


class IfcGraphService:
    def __init__(
        self,
        graph: Graph,
        storage: LocalStorage,
        settings: Settings,
        *,
        workcopy: Graph | None = None,
        store: Graph | None = None,
    ) -> None:
        self.workcopy = workcopy  # the second graph that holds the head model of every document (ADR 0024)
        self.graph = graph
        self.store = store or graph  # the server's own records, apart from the IFC graph (F24 a)
        self.conversions: ConversionStore = ConversionRepository(self.store)
        self.storage = storage
        self.settings = settings
        self.bsdd: BsddClient | None = None  # made on the first check against bSDD; its cache lives on (OB-42)
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
        version_id: str | None = None,
        checked: dict[str, Any] | None = None,
    ) -> str | None:
        """Queue a conversion for an uploaded IFC file; returns the model id, or None for other files.

        A document version (``version_id``) is checked against the IFC schema too, before it is converted, unless
        ``checked`` brings the result of a check made before the version existed (``check_now``).
        """
        if not self.wants(file_name):
            if version_id is not None and file_name.lower().endswith(IDS_SUFFIX):
                await self.recheck_after_ids(project_id)
            return None
        if version_id is not None and self.settings.ifcgraph_validate_uploads:
            if checked is None:
                await self._queue_validation(version_id, storage_key, file_name)
            else:
                await self._record_validation(version_id, storage_key, file_name, checked)
        model_id = new_id()
        await self.conversions.create(
            project_id=project_id,
            model_id=model_id,
            file_name=file_name,
            storage_key=storage_key,
            document_id=document_id,
            version_index=version_index,
            bcf_document_guid=bcf_document_guid,
        )
        self._start(model_id, storage_key, file_name)
        return model_id

    def _start(self, model_id: str, storage_key: str, file_name: str) -> None:
        task = asyncio.create_task(self._run(model_id, storage_key, file_name), name=f"ifcgraph-{model_id}")
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def resume_interrupted(self) -> None:
        """Start over the conversions a stopped server left behind, and tidy the working copy (ADR 0024).

        A queued model belongs to whichever server process takes it first (``_claim``). A running one may be
        running in another process, so it is given up only when twice the time limit has passed since it started.
        """
        await self.tidy_workcopy()
        await merging.resume(self)
        given_up = later_iso(-2 * self.settings.ifcgraph_timeout_seconds)
        await self.conversions.spatial_interrupted(given_up=given_up)
        rows = await self.conversions.interrupted(given_up=given_up)
        waiting_here = {task.get_name() for task in self._tasks}
        for row in rows:
            if f"ifcgraph-{row['id']}" in waiting_here:
                continue
            if row["state"] == STATE_RUNNING:
                await delete_model(self.graph, row["id"], keep_model=True)
                await self._set_state(row["id"], STATE_QUEUED)
            log.info("ifcgraph_resumed", model_id=row["id"])
            self._start(row["id"], row["storage_key"], row["file_name"])
        rows = await self.graph.run(
            """
            MATCH (p:Proposal)
            WHERE p.state = $queued OR (p.state = $running AND p.running_at < $given_up)
            RETURN p.id AS id, p.state AS state
            """,
            queued=STATE_QUEUED,
            running=STATE_RUNNING,
            given_up=later_iso(-2 * self.settings.ifcgraph_timeout_seconds),
        )
        for row in rows:
            if f"ifcproposal-{row['id']}" in waiting_here:
                continue
            if row["state"] == STATE_RUNNING:
                await self._set_proposal(row["id"], STATE_QUEUED)
            log.info("ifc_proposal_resumed", proposal_id=row["id"])
            self._start_proposal(row["id"])
        if not self.settings.ifcgraph_validate_uploads:
            return
        rows = await self.graph.run(
            """
            MATCH (r:Validation)
            WHERE r.state = $queued OR (r.state = $running AND r.running_at < $given_up)
            RETURN r.id AS id, r.storage_key AS storage_key, r.file_name AS file_name, r.state AS state
            """,
            queued=STATE_QUEUED,
            running=STATE_RUNNING,
            given_up=later_iso(-2 * self.settings.ifcgraph_timeout_seconds),
        )
        for row in rows:
            if f"ifcvalidation-{row['id']}" in waiting_here:
                continue
            if row["state"] == STATE_RUNNING:
                await self._set_validation(row["id"], STATE_QUEUED)
            log.info("ifc_validation_resumed", validation_id=row["id"])
            self._start_validation(row["id"], row["storage_key"], row["file_name"])

    async def shutdown(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        for task in list(self._tasks):
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        if self.bsdd is not None:
            await self.bsdd.aclose()

    async def wait_idle(self) -> None:
        """For tests: wait until every scheduled conversion has finished."""
        while self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

    # -- the conversion ----------------------------------------------------------------------------

    async def _set_state(self, model_id: str, state: str, **fields: Any) -> None:
        await self.conversions.set_state(model_id, state, **fields)

    async def _claim(self, model_id: str) -> bool:
        return await self.conversions.claim(model_id)

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
                    if self.workcopy is not None:
                        await self._copy_to_workcopy(model_id, header, records)
                except Exception as exc:
                    log.warning("ifcgraph_failed", model_id=model_id, error=f"{type(exc).__name__}: {exc}"[:500])
                    with contextlib.suppress(Exception):
                        await delete_model(self.graph, model_id, keep_model=True)
                    await self._set_state(model_id, STATE_FAILED, error=f"{type(exc).__name__}: {exc}"[:500])
                    return
                facts = {name: counts.get(name, header.get(name)) for name in FACTS}
                await self._set_state(
                    model_id,
                    STATE_DONE,
                    **facts,
                    **({"spatial_pending": True} if self.settings.ifcgraph_spatial else {}),
                )
                geometry = await self._add_spatial(model_id, source, workdir)
                await self._graph_findings(model_id, geometry)
            # Viewpoints created before the model finished (or before it was uploaded) get their links now.
            try:
                linked = await self._link_model(model_id)
            except Exception as exc:  # the import itself succeeded; linking can be repeated by a new viewpoint
                log.warning("ifcgraph_link_failed", model_id=model_id, error=f"{type(exc).__name__}: {exc}"[:200])
                linked = 0
            log.info("ifcgraph_imported", model_id=model_id, linked=linked, **counts)

    # -- where the products are, and the geometry (OB-37) ---------------------------------------------

    async def _add_spatial(self, model_id: str, source: Path, workdir: Path) -> list[dict[str, Any]]:
        """Run IFC-LPG's geometry worker once: a box per product into the archive (and the working copy), and the
        records kept in the storage for the glTF. A failure here is logged on the model and never fails the
        conversion: the graph is complete without the boxes. Returns the products whose shape could not be built, as
        issues of a report (IFC-LPG F24 a)."""
        if not self.settings.ifcgraph_spatial:
            return []
        failed: list[dict[str, Any]] = []
        records = workdir / "geometry.jsonl"
        command = [
            sys.executable,
            "-m",
            "ifc_lpg.spatial",
            str(source),
            str(records),
            "--memory-mb",
            str(self.settings.ifcgraph_memory_mb),
            "--threads",
            str(self.settings.ifcgraph_geometry_threads),
            "--max-entities",
            str(self.settings.ifcgraph_max_entities),
        ]
        try:
            await self._in_a_process(command, "the geometry")
            counts = await import_spatial(self.graph, model_id, records)
            failed = await asyncio.to_thread(geometry_issues, records)
            passed = await model_facts(self.graph, model_id) or {}
            await self.conversions.set_fields(model_id, **{name: passed.get(name) for name in SPATIAL_FACTS})
            await rebuild_point_indexes(SchemaGraph(self.graph), library_dialect(self.graph))
            key = make_key("geometry", model_id, "jsonl")
            await asyncio.to_thread(self.storage.copy_in, records, key)
            await self.conversions.set_fields(model_id, geometry_key=key)
            if self.workcopy is not None and await self.in_workcopy(model_id):
                try:
                    await import_spatial(self.workcopy, model_id, records)
                    await rebuild_point_indexes(SchemaGraph(self.workcopy), library_dialect(self.workcopy))
                except Exception as exc:  # the archive has the boxes; the copy can be made again
                    log.warning("ifcgraph_workcopy_spatial_failed", model_id=model_id, error=type(exc).__name__)
            log.info("ifcgraph_spatial", model_id=model_id, **counts)
        except Exception as exc:
            log.warning("ifcgraph_spatial_failed", model_id=model_id, error=f"{type(exc).__name__}: {exc}"[:300])
            with contextlib.suppress(Exception):
                await self.conversions.set_fields(model_id, spatial_error=f"{type(exc).__name__}: {exc}"[:300])
        finally:
            with contextlib.suppress(Exception):
                await self.conversions.remove_field(model_id, "spatial_pending")
        return failed

    async def _graph_findings(self, model_id: str, geometry: list[dict[str, Any]]) -> None:
        """What the graph shows of a converted model, for the report of its version: the instances that no GlobalId
        reaches, forward or backward, as warnings (IFC-LPG F13 a and OB-10.1: a check warns of them and refuses
        nothing), and the products whose shape could not be built. A failure here is logged and leaves the report as
        the checks of the file made it."""
        try:
            unreached = await unreachable(self.graph, model_id)
            issues = [_unreached_issue(node) for node in unreached] + list(geometry)
            await self.conversions.set_fields(
                model_id,
                graph_report=pack_report(issues[:MAX_REPORTED]),
                graph_issue_count=len(issues),
                graph_error_count=sum(1 for issue in issues if issue.get("severity") == "error"),
                graph_ruleset=GRAPH_RULESET,
                graph_checked_at=now_iso(),
            )
            log.info("ifcgraph_findings", model_id=model_id, unreached=len(unreached), geometry=len(geometry))
        except Exception as exc:
            log.warning("ifcgraph_findings_failed", model_id=model_id, error=type(exc).__name__)

    async def model_of_version(
        self, *, user_id: str, project_id: str, document_id: str, version_index: int
    ) -> dict[str, Any] | None:
        """The converted model of a document version in a project the user is a member of, the latest when there are
        several; its ``id`` and ``file_name``, or None."""
        found = await self.conversions.for_member(
            user_id=user_id, project_id=project_id, document_id=document_id, version_index=version_index, done_only=True
        )
        return {"id": found["id"], "file_name": found.get("file_name")} if found else None

    async def unreached(self, model_id: str) -> list[dict[str, Any]]:
        """The instances of a converted model that no GlobalId reaches, forward or backward, as ``{"step",
        "ifc_class"}`` (IFC-LPG F13 a)."""
        return await unreachable(self.graph, model_id)

    async def geometry(
        self, *, model_id: str, lod: str = "full", classes: tuple[str, ...] = (), storey: str | None = None
    ) -> tuple[Path, str] | None:
        """The ``.glb`` of a model for the filters, built from its geometry records the first time and kept in the
        storage under a key that names the model and a tag of the filters. Returns the file and the tag, or None
        when the model has no geometry records."""
        conversion = await self.conversions.get(model_id)
        records_key = str(conversion.get("geometry_key") or "") if conversion else ""
        if not records_key or not self.storage.exists(records_key):
            return None
        if lod not in LODS:
            raise ValueError(f"lod is one of {', '.join(LODS)}")
        chosen = ",".join(sorted(set(classes)))
        tag = "g" + hashlib.sha256(f"{lod}|{chosen}|{storey or ''}".encode()).hexdigest()[:7]
        key = make_key("geometry", model_id, tag)
        if not self.storage.exists(key):
            glb, summary = await asyncio.to_thread(
                build_glb, self.storage.path(records_key), lod=lod, classes=set(classes) or None, storey=storey
            )
            await asyncio.to_thread(self.storage.write_bytes, key, glb)
            log.info("ifcgraph_geometry_built", model_id=model_id, lod=lod, bytes=len(glb), **summary)
        return self.storage.path(key), tag

    # -- the working copy (ADR 0024) ------------------------------------------------------------------

    async def _copy_to_workcopy(self, model_id: str, header: dict[str, Any], records: Path) -> None:
        """Import the same records into the working copy, as the head model of its document, replacing the model
        of the version before. A failure here is logged and never fails the conversion: the archive is the truth."""
        workcopy = self.workcopy
        if workcopy is None:
            return
        try:
            conversion = await self.conversions.get(model_id)
            if conversion is None or not conversion.get("document_id"):
                return  # a BCF project document has no head to keep
            for old in await self.conversions.model_ids_of_document(str(conversion["document_id"])):
                if old != model_id:
                    await delete_model(workcopy, old)
            await delete_model(workcopy, model_id)
            counts = await import_records(workcopy, model_id, records)
            log.info(
                "ifcgraph_workcopy_updated",
                model_id=model_id,
                nodes=counts["nodes"],
                relationships=counts["relationships"],
            )
        except Exception as exc:
            log.warning("ifcgraph_workcopy_failed", model_id=model_id, error=f"{type(exc).__name__}: {exc}"[:300])
            with contextlib.suppress(Exception):  # the archive is untouched; the copy can be made again
                await delete_model(workcopy, model_id)

    async def in_workcopy(self, model_id: str) -> bool:
        """Whether a version's model is in the working copy, so that a query can run there."""
        if self.workcopy is None:
            return False
        try:
            facts = await model_facts(self.workcopy, model_id)
        except Exception as exc:
            log.warning("ifcgraph_workcopy_unavailable", error=type(exc).__name__)
            return False
        return bool(facts and facts.get("whole"))

    async def tidy_workcopy(self) -> int:
        """Drop models the archive no longer has (a deleted project, a pruned model). Returns how many went."""
        if self.workcopy is None:
            return 0
        try:
            gone = 0
            for model in await models(self.workcopy):
                kept = await self.conversions.get(str(model["id"]))
                if kept is None:
                    await delete_model(self.workcopy, model["id"])
                    gone += 1
            return gone
        except Exception as exc:
            log.warning("ifcgraph_workcopy_unavailable", error=type(exc).__name__)
            return 0

    # -- checking an upload against the IFC schema ------------------------------------------------

    async def _queue_validation(self, version_id: str, storage_key: str, file_name: str) -> None:
        validation_id = new_id()
        rows = await self.graph.run(
            """
            MATCH (v:DocumentVersion {id: $version_id})
            CREATE (v)-[:HAS_VALIDATION]->(r:Validation {
                id: $id, storage_key: $storage_key, file_name: $file_name, state: $state, created_at: $now
            })
            RETURN r.id AS id
            """,
            version_id=version_id,
            id=validation_id,
            storage_key=storage_key,
            file_name=file_name,
            state=STATE_QUEUED,
            now=now_iso(),
        )
        if rows:
            self._start_validation(validation_id, storage_key, file_name)

    def _start_validation(self, validation_id: str, storage_key: str, file_name: str) -> None:
        task = asyncio.create_task(
            self._validate(validation_id, storage_key, file_name), name=f"ifcvalidation-{validation_id}"
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _set_validation(self, validation_id: str, state: str, **fields: Any) -> None:
        await self.graph.run(
            "MATCH (r:Validation {id: $id}) SET r.state = $state, r += $fields",
            id=validation_id,
            state=state,
            fields={**fields, f"{state}_at": now_iso()},
        )

    async def _validate(self, validation_id: str, storage_key: str, file_name: str) -> None:
        """Check one upload; the issues may quote the file, so only their number is logged."""
        async with self._lock:
            rows = await self.graph.run(
                """
                MATCH (r:Validation {id: $id, state: $queued})
                SET r.state = $running, r.running_at = $now
                RETURN r.id AS id
                """,
                id=validation_id,
                queued=STATE_QUEUED,
                running=STATE_RUNNING,
                now=now_iso(),
            )
            if not rows:
                return
            try:
                fields = await self._run_checks(storage_key, file_name, await self._project_of(validation_id))
            except Exception as exc:
                log.warning("ifc_validation_failed", validation_id=validation_id, error=type(exc).__name__)
                await self._set_validation(validation_id, STATE_FAILED, **_failure(exc))
                return
            await self._set_validation(validation_id, STATE_DONE, **fields)
            log.info("ifc_validation_done", validation_id=validation_id, issues=fields["issue_count"])

    async def _project_of(self, validation_id: str) -> str | None:
        """The project of a check: through the version for an upload, straight from the project for a precheck."""
        row = await self.graph.one(
            """
            MATCH (r:Validation {id: $id})
            OPTIONAL MATCH (r)<-[:HAS_VALIDATION]-(:DocumentVersion)<-[:HAS_VERSION]-(:Document)
                           <-[:HAS_DOCUMENT]-(p:Project)
            OPTIONAL MATCH (r)<-[:HAS_PRECHECK]-(q:Project)
            RETURN p.project_id AS of_version, q.project_id AS of_precheck
            """,
            id=validation_id,
        )
        if row is None:
            return None
        return row["of_version"] or row["of_precheck"]

    async def _run_checks(self, storage_key: str, file_name: str, project_id: str | None) -> dict[str, Any]:
        """The IFC schema, buildingSMART's rules, the project's IDS documents and bSDD on one file.

        The fields of an ``Validation`` node in state ``done``; an exception when the file could not be checked.
        """
        with tempfile.TemporaryDirectory(prefix="ifcvalidation-") as tmp:
            source = await asyncio.to_thread(self._prepare_input, storage_key, file_name, Path(tmp))
            command = [
                sys.executable,
                "-m",
                "ifc_lpg.validation",
                str(source),
                "--report",
                "--memory-mb",
                str(self.settings.ifcgraph_memory_mb),
            ]
            report = json.loads(await self._in_a_process(command, "the validation", answers=(0, 1)))
            gherkin = await self._gherkin(source)
            ids = await self._ids(source, await self._ids_documents(project_id) if project_id else [])
            dictionary = await self._bsdd(source)
        checks: list[dict[str, Any]] = [
            {
                "name": "schema",
                "state": STATE_DONE,
                "ruleset": str(report["ruleset"]),
                "issue_count": int(report["issue_count"]),
            }
        ]
        issues = list(report["issues"])
        total = int(report["issue_count"])
        errors = int(report.get("error_count", total))
        truncated = bool(report["truncated"])
        for other in (gherkin, ids, dictionary):
            if other is None:
                continue
            checks.append(other["check"])
            issues += other["issues"]
            total += int(other["check"]["issue_count"])
            errors += int(other["error_count"])
            truncated = truncated or bool(other["truncated"])
        if len(issues) > MAX_REPORTED:
            issues, truncated = issues[:MAX_REPORTED], True
        return {
            "checked_at": now_iso(),
            "issue_count": total,
            "error_count": errors,
            "truncated": truncated,
            "ruleset": "; ".join(check["ruleset"] for check in checks if check["state"] == STATE_DONE),
            "checks": json.dumps(checks),
            "report": pack_report(issues),
        }

    async def check_now(self, *, project_id: str, storage_key: str, file_name: str) -> dict[str, Any] | None:
        """Check a file before it becomes a version, for a project that refuses uploads with errors (ADR 0021).

        The fields of an ``Validation`` node with its ``state``, ``done`` or ``failed``; None for a file that is
        not IFC, or when checking is off. A check that cannot run refuses nothing: the file is as unknown as any
        other, and ``schedule`` records that with the version.
        """
        if not self.wants(file_name) or not self.settings.ifcgraph_validate_uploads:
            return None
        async with self._lock:
            try:
                return {"state": STATE_DONE, **await self._run_checks(storage_key, file_name, project_id)}
            except Exception as exc:
                log.warning("ifc_validation_failed", project_id=project_id, error=type(exc).__name__)
                return {"state": STATE_FAILED, **_failure(exc)}

    async def _record_validation(
        self, version_id: str, storage_key: str, file_name: str, checked: dict[str, Any]
    ) -> None:
        """A check made before the version existed (``check_now``) becomes the version's ``Validation`` node."""
        now = now_iso()
        await self.graph.run(
            """
            MATCH (v:DocumentVersion {id: $version_id})
            CREATE (v)-[:HAS_VALIDATION]->(r:Validation {id: $id, storage_key: $storage_key, file_name: $file_name})
            SET r += $fields
            """,
            version_id=version_id,
            id=new_id(),
            storage_key=storage_key,
            file_name=file_name,
            fields={**checked, "created_at": now, f"{checked['state']}_at": now},
        )

    # -- a file checked without becoming a version (ADR 0021) -----------------------------------------

    async def schedule_precheck(
        self, *, precheck_id: str, project_id: str, storage_key: str, file_name: str, author: str
    ) -> None:
        """Queue the checks on a file a member sent to try; the node and the file live ``PRECHECK_SECONDS``."""
        rows = await self.graph.run(
            """
            MATCH (p:Project {project_id: $project_id})
            CREATE (p)-[:HAS_PRECHECK]->(r:Validation:Precheck {
                id: $id, project_id: $project_id, storage_key: $storage_key, file_name: $file_name,
                author: $author, state: $state, created_at: $now, expires_at: $expires_at
            })
            RETURN r.id AS id
            """,
            project_id=project_id,
            id=precheck_id,
            storage_key=storage_key,
            file_name=file_name,
            author=author,
            state=STATE_QUEUED,
            now=now_iso(),
            expires_at=later_iso(PRECHECK_SECONDS),
        )
        if not rows:
            raise ValueError("no such project")
        self._start_validation(precheck_id, storage_key, file_name)

    async def keep_as_precheck(
        self, *, project_id: str, storage_key: str, file_name: str, author: str, checked: dict[str, Any]
    ) -> str:
        """A refused upload stays as a precheck, so that its report can be read; returns the precheck's id."""
        precheck_id = new_id()
        now = now_iso()
        await self.graph.run(
            """
            MATCH (p:Project {project_id: $project_id})
            CREATE (p)-[:HAS_PRECHECK]->(r:Validation:Precheck {
                id: $id, project_id: $project_id, storage_key: $storage_key, file_name: $file_name,
                author: $author, created_at: $now, expires_at: $expires_at
            })
            SET r += $fields
            """,
            project_id=project_id,
            id=precheck_id,
            storage_key=storage_key,
            file_name=file_name,
            author=author,
            now=now,
            expires_at=later_iso(PRECHECK_SECONDS),
            fields={**checked, f"{checked['state']}_at": now},
        )
        return precheck_id

    async def precheck(self, *, user_id: str, project_id: str, precheck_id: str) -> dict[str, Any] | None:
        """A precheck of a project the user is a member of, its issues unpacked; None when there is none."""
        row = await self.graph.one(
            """
            MATCH (:User {id: $user_id})-[:MEMBER_OF]->(:Project {project_id: $project_id})
                  -[:HAS_PRECHECK]->(r:Precheck {id: $id})
            RETURN properties(r) AS node
            """,
            user_id=user_id,
            project_id=project_id,
            id=precheck_id,
        )
        if row is None:
            return None
        node = dict(row["node"])
        node["issues"] = unpack_report(node.pop("report", None))
        node["checks"] = json.loads(node["checks"]) if node.get("checks") else []
        return node

    # -- a change set tried on its base version (ADR 0021) --------------------------------------------

    async def schedule_proposal(self, *, project_id: str, topic_guid: str, snippet_key: str, author: str) -> str:
        """Queue the trial of a topic's change set; an earlier trial of the topic goes, with its file."""
        gone = await self.graph.run(
            """
            MATCH (:Project {project_id: $project_id})-[:HAS_TOPIC]->(:Topic {guid: $guid})-[:HAS_PROPOSAL]->(p:Proposal)
            WITH p, p.storage_key AS key
            DETACH DELETE p
            RETURN key
            """,
            project_id=project_id,
            guid=topic_guid,
        )
        for row in gone:
            if row["key"]:
                with contextlib.suppress(ValueError, OSError):
                    self.storage.delete(row["key"])
        proposal_id = new_id()
        base = await asyncio.to_thread(self._base_of, snippet_key)
        rows = await self.graph.run(
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
            base_document_id=base.get("document_id"),
            base_version_index=base.get("version_index"),
        )
        if not rows:
            raise ValueError("no such topic")
        self._start_proposal(proposal_id)
        return proposal_id

    def _base_of(self, snippet_key: str) -> dict[str, Any]:
        """The base version a stored change set names, put on the proposal when it is queued, so that the Documents
        API lists the proposal against its document before the trial and when the trial failed; empty when the
        snippet cannot be read, which the trial then says."""
        try:
            with self.storage.open_read(snippet_key) as handle:
                base = json.loads(handle.read().decode("utf-8"))["base"]
            return {"document_id": str(base["document_id"]), "version_index": int(base["version_index"])}
        except (OSError, ValueError, KeyError, TypeError):
            return {}

    def _start_proposal(self, proposal_id: str) -> None:
        task = asyncio.create_task(self._run_proposal(proposal_id), name=f"ifcproposal-{proposal_id}")
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _set_proposal(self, proposal_id: str, state: str, **fields: Any) -> None:
        await self.graph.run(
            "MATCH (p:Proposal {id: $id}) SET p.state = $state, p += $fields",
            id=proposal_id,
            state=state,
            fields={**fields, f"{state}_at": now_iso()},
        )

    async def _run_proposal(self, proposal_id: str) -> None:
        """Try one change set; the findings may quote the file, so only their number is logged."""
        async with self._lock:
            row = await self.graph.one(
                """
                MATCH (p:Proposal {id: $id, state: $queued})
                SET p.state = $running, p.running_at = $now
                RETURN p.project_id AS project_id, p.snippet_key AS snippet_key
                """,
                id=proposal_id,
                queued=STATE_QUEUED,
                running=STATE_RUNNING,
                now=now_iso(),
            )
            if row is None:
                return
            try:
                fields = await self._try_proposal(proposal_id, str(row["project_id"]), str(row["snippet_key"]))
            except Exception as exc:
                log.warning("ifc_proposal_failed", proposal_id=proposal_id, error=type(exc).__name__)
                await self._set_proposal(proposal_id, STATE_FAILED, **_failure(exc))
                return
            state = fields.pop("state")
            await self._set_proposal(proposal_id, state, **fields)
            log.info("ifc_proposal_done", proposal_id=proposal_id, state=state, issues=fields["issue_count"])

    async def _try_proposal(
        self, proposal_id: str, project_id: str, snippet_key: str, base_version_index: int | None = None
    ) -> dict[str, Any]:
        """Apply the changes to the base version's file, check the result, and keep what the base lacks.

        ``base_version_index`` tries the change set on another version of its document than the one it names:
        the latest, when the server merges at the approval (ADR 0021).
        """
        with self.storage.open_read(snippet_key) as handle:
            change_set = json.loads(handle.read().decode("utf-8"))
        base = dict(change_set["base"])
        if base_version_index is not None:
            base["version_index"] = base_version_index
        version = await self.graph.one(
            """
            MATCH (:Project {project_id: $project_id})-[:HAS_DOCUMENT]->(:Document {document_id: $document_id})
                  -[:HAS_VERSION]->(v:DocumentVersion {version_index: $version_index})
            OPTIONAL MATCH (v)-[:HAS_VALIDATION]->(r:Validation {state: $done})
            WITH v, r ORDER BY r.created_at DESC
            RETURN v.storage_key AS storage_key, v.file_name AS file_name, r.report AS base_report,
                   r.checks AS base_checks
            LIMIT 1
            """,
            project_id=project_id,
            document_id=str(base["document_id"]),
            version_index=int(base["version_index"]),
            done=STATE_DONE,
        )
        if version is None:
            raise RuntimeError("the base version is not in this project")
        if not self.wants(str(version["file_name"])):
            raise RuntimeError("the base version is not an IFC file")
        key = make_key("proposals", proposal_id, "ifc")
        with tempfile.TemporaryDirectory(prefix="ifcproposal-") as tmp:
            workdir = Path(tmp)
            source = await asyncio.to_thread(
                self._prepare_input, str(version["storage_key"]), str(version["file_name"]), workdir
            )
            changes = workdir / "changes.json"
            changes.write_text(json.dumps(change_set), encoding="utf-8")
            out = workdir / "proposal.ifc"
            command = [
                sys.executable,
                "-m",
                "opencde.ifcgraph.apply",
                str(source),
                str(changes),
                str(out),
                "--memory-mb",
                str(self.settings.ifcgraph_memory_mb),
            ]
            answer = await self._in_a_process(command, "applying the change set")
            summary = json.loads(answer.strip().splitlines()[-1])
            await asyncio.to_thread(self.storage.copy_in, out, key)
            teams, teams_error = await self._parts_touched(project_id, source, out, changes)
            # A base checked before bSDD was asked, or while it was out of reach, is asked about now, so that the
            # trial keeps only the findings the change set brings (OB-42).
            base_bsdd = None
            if version["base_report"] is not None and not _made(version["base_checks"], "bsdd"):
                base_bsdd = await self._bsdd(source)
        checked = await self._run_checks(key, "proposal.ifc", project_id)
        if version["base_report"] is None:
            base_issues = unpack_report(
                (await self._run_checks(str(version["storage_key"]), str(version["file_name"]), project_id))["report"]
            )
        else:
            base_issues = unpack_report(version["base_report"]) + (base_bsdd["issues"] if base_bsdd else [])
        known = {_issue_key(issue) for issue in base_issues}
        new = [issue for issue in unpack_report(checked["report"]) if _issue_key(issue) not in known]
        problems = [
            {
                "kind": "proposal",
                "severity": "error",
                "message": f"change {problem['change']}: {problem['error']}",
            }
            for problem in summary["problems"]
        ]
        issues = problems + new
        return {
            "state": STATE_CLEAN if not issues else STATE_ISSUES,
            "checked_at": now_iso(),
            "storage_key": key,
            "file_name": "proposal.ifc",
            "base_document_id": str(base["document_id"]),
            "base_version_index": int(base["version_index"]),
            "change_count": int(summary["count"]),
            "applied": int(summary["applied"]),
            "issue_count": len(issues),
            "error_count": sum(1 for issue in issues if issue.get("severity") == "error"),
            "truncated": bool(checked["truncated"]),
            "ruleset": checked["ruleset"],
            "checks": checked["checks"],
            "report": pack_report(issues),
            "teams": json.dumps(teams, separators=(",", ":")),
            "teams_error": teams_error,
        }

    async def _parts_touched(
        self, project_id: str, base: Path, changed: Path, changes: Path
    ) -> tuple[list[dict[str, Any]], str | None]:
        """The teams whose part of the model the change set touches (F11 b, F19 a), and why that is unknown when it
        is: then a ``manager`` approves."""
        parts = [part for part in await TeamRepository(self.graph).parts(project_id) if part["storage_key"]]
        if not parts:
            return [], None
        command = [sys.executable, "-m", "opencde.ifcgraph.parts", "--memory-mb", str(self.settings.ifcgraph_memory_mb)]
        command += ["--", str(base), str(changed), str(changes)]
        command += [str(self.storage.path(str(part["storage_key"]))) for part in parts]
        try:
            answer = json.loads(
                (await self._in_a_process(command, "finding the teams' parts")).strip().splitlines()[-1]
            )
        except Exception as exc:
            log.warning("ifc_proposal_parts_failed", error=type(exc).__name__)
            return [], f"the teams' parts could not be found: {type(exc).__name__}"
        touched = [
            {"team_id": parts[index]["team_id"], "name": parts[index]["name"]} for index in sorted(set(answer["teams"]))
        ]
        unread = [str(parts[int(error["ids"])]["name"]) for error in answer.get("errors") or []]
        return touched, (f"the IDS of these teams could not be read: {', '.join(unread)}" if unread else None)

    async def approve(self, *, proposal_id: str, approved_by: str, version_index: int) -> None:
        """The trial became a version (ADR 0021): who approved it and which version it is."""
        await self._set_proposal(proposal_id, STATE_APPROVED, approved_by=approved_by, version_index=version_index)

    async def retry_proposal(self, *, proposal_id: str, base_version_index: int) -> str:
        """Try the change set again, at once, on another version of its document; returns the new state.

        The approval does this on the latest version when the change set collides with nothing that came
        between its base and the latest (ADR 0021). The request waits for the trial.
        """
        row = await self.graph.one(
            "MATCH (p:Proposal {id: $id}) RETURN p.project_id AS project_id, p.snippet_key AS snippet_key",
            id=proposal_id,
        )
        if row is None:
            raise ValueError("no such proposal")
        async with self._lock:
            await self._set_proposal(proposal_id, STATE_RUNNING)
            try:
                fields = await self._try_proposal(
                    proposal_id, str(row["project_id"]), str(row["snippet_key"]), base_version_index=base_version_index
                )
            except Exception as exc:
                log.warning("ifc_proposal_failed", proposal_id=proposal_id, error=type(exc).__name__)
                await self._set_proposal(proposal_id, STATE_FAILED, **_failure(exc))
                return STATE_FAILED
            state = str(fields.pop("state"))
            await self._set_proposal(proposal_id, state, **fields)
            return state

    async def values_in(
        self, *, document_id: str, version_index: int, changes: list[dict[str, Any]]
    ) -> list[dict[str, Any]] | None:
        """What each change's attribute holds in a stored version of a document, read by the apply worker; each entry
        ``{"value"}`` or ``{"error"}``. None when the version's file is not there."""
        row = await self.graph.one(
            """
            MATCH (:Document {document_id: $document_id})-[:HAS_VERSION]->(v:DocumentVersion {version_index: $index})
            RETURN v.storage_key AS storage_key, v.file_name AS file_name
            """,
            document_id=document_id,
            index=version_index,
        )
        if row is None or not changes:
            return None
        async with self._lock:
            with tempfile.TemporaryDirectory(prefix="ifcvalues-") as tmp:
                workdir = Path(tmp)
                source = await asyncio.to_thread(
                    self._prepare_input, str(row["storage_key"]), str(row["file_name"]), workdir
                )
                listed = workdir / "changes.json"
                listed.write_text(json.dumps({"changes": changes}), encoding="utf-8")
                command = [
                    sys.executable,
                    "-m",
                    "opencde.ifcgraph.apply",
                    str(source),
                    str(listed),
                    "--read",
                    "--memory-mb",
                    str(self.settings.ifcgraph_memory_mb),
                ]
                answer = await self._in_a_process(command, "reading the values")
        return list(json.loads(answer.strip().splitlines()[-1])["values"])

    async def canonical_keys(
        self, *, document_id: str, version_index: int, changes: list[dict[str, Any]]
    ) -> list[str] | None:
        """Each change's attribute as one string, the instance named by its canonical path in the model of the version
        the change was made on: `<guid>/<path>.<attribute>`, or `#<step>.<attribute>` for an instance no GlobalId
        reaches. A change whose path does not lead to a node there keeps the key its client wrote. None when that
        version has no finished model in the graph (pruned, or never converted)."""
        found = await self.conversions.latest_of_version(document_id=document_id, version_index=version_index)
        if found is None:
            return None
        model_id = str(found["id"])
        named: dict[int, str] = {}  # STEP id: its canonical name, since many changes touch one instance
        keys: list[str] = []
        for change in changes:
            attribute = change.get("attribute")
            written = (
                f"#{change['step_id']}.{attribute}"
                if change.get("step_id") is not None
                else f"{change.get('guid')}/{change.get('path') or ''}.{attribute}"
            )
            try:
                if change.get("step_id") is not None:
                    step = int(change["step_id"])
                else:
                    found = await resolve(self.graph, model_id, str(change.get("guid")), str(change.get("path") or ""))
                    step = int(found["step"])
                if step not in named:
                    try:
                        canonical = await canonical_path(self.graph, model_id, step)
                        named[step] = f"{canonical['global_id']}/{canonical['path']}"
                    except PathError:
                        named[step] = f"#{step}"  # in a block, or reached by no GlobalId: its STEP id names it
                keys.append(f"{named[step]}.{attribute}")
            except (PathError, ValueError, TypeError):
                keys.append(written)
        return keys

    async def change_set_of(self, *, project_id: str, topic_guid: str) -> dict[str, Any] | None:
        """The change set a topic carries, as uploaded; None when the topic has no trial any more."""
        row = await self.graph.one(
            """
            MATCH (:Project {project_id: $project_id})-[:HAS_TOPIC]->(:Topic {guid: $guid})
                  -[:HAS_PROPOSAL]->(p:Proposal)
            RETURN p.snippet_key AS snippet_key
            """,
            project_id=project_id,
            guid=topic_guid,
        )
        if row is None:
            return None
        try:
            with self.storage.open_read(str(row["snippet_key"])) as handle:
                return dict(json.loads(handle.read().decode("utf-8")))
        except (OSError, ValueError):
            return None

    async def diff(self, *, a: tuple[str, str], b: tuple[str, str]) -> dict[str, Any]:
        """The difference between two stored IFC files, element by element (``diff.py``), computed now.

        Each side is a storage key and a file name. The worker runs behind the conversion queue's lock, as the
        checks do, and the answer is never stored (ADR 0021).
        """
        async with self._lock:
            with tempfile.TemporaryDirectory(prefix="ifcdiff-") as tmp:
                workdir = Path(tmp)
                (workdir / "a").mkdir()
                (workdir / "b").mkdir()
                source_a = await asyncio.to_thread(self._prepare_input, a[0], a[1], workdir / "a")
                source_b = await asyncio.to_thread(self._prepare_input, b[0], b[1], workdir / "b")
                command = [
                    sys.executable,
                    "-m",
                    "opencde.ifcgraph.diff",
                    str(source_a),
                    str(source_b),
                    "--memory-mb",
                    str(self.settings.ifcgraph_memory_mb),
                ]
                answer = await self._in_a_process(command, "the comparison")
            return dict(json.loads(answer.strip().splitlines()[-1]))

    async def proposal(self, *, user_id: str, project_id: str, topic_guid: str) -> dict[str, Any] | None:
        """The trial of a topic's change set, for a member of the project, its issues unpacked; None without one."""
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
        if row is None:
            return None
        node = dict(row["node"])
        node["issues"] = unpack_report(node.pop("report", None))
        node["checks"] = json.loads(node["checks"]) if node.get("checks") else []
        node["teams"] = json.loads(node["teams"]) if node.get("teams") else []
        return node

    def _gherkin_env(self) -> Path | None:
        """The environment ifc-gherkin-rules run in, if one is configured and installed (ADR 0012)."""
        configured = self.settings.ifcgraph_gherkin_env
        if not configured:
            return None
        env = Path(configured)
        return env if (env / MANIFEST).is_file() else None

    async def _gherkin(self, source: Path) -> dict[str, Any] | None:
        """buildingSMART's ifc-gherkin-rules on the file. If they cannot be run, the schema's check stands alone."""
        env = self._gherkin_env()
        if env is None:
            return None
        timeout = self.settings.ifcgraph_timeout_seconds
        command = [
            sys.executable,
            "-m",
            "ifc_lpg.gherkin",
            str(source),
            "--env",
            str(env),
            "--memory-mb",
            str(self.settings.ifcgraph_memory_mb),
            "--timeout-seconds",
            str(max(timeout - 30, timeout // 2)),  # the rules' own limit comes first, so behave is stopped too
        ]
        try:
            report = json.loads(await self._in_a_process(command, "the gherkin rules", answers=(0, 1)))
        except Exception as exc:
            log.warning("ifc_gherkin_failed", error=type(exc).__name__)
            return {
                "check": {"name": "gherkin", "state": STATE_FAILED, "ruleset": _ruleset_of(env), "issue_count": 0},
                "issues": [],
                "error_count": 0,
                "truncated": False,
            }
        return {
            "check": {
                "name": "gherkin",
                "state": STATE_DONE,
                "ruleset": str(report["ruleset"]),
                "issue_count": int(report["issue_count"]),
                "rules_not_run": report["rules_not_run"],
            },
            "issues": report["issues"],
            "error_count": int(report["error_count"]),
            "truncated": bool(report["truncated"]),
        }

    async def recheck_after_ids(self, project_id: str) -> int:
        """A new version of an IDS document: the latest version of every IFC document in the project is checked again,
        so that its report follows the project's requirements as they are now (OB-43.1). Returns how many were queued;
        the reports show the newest check, and the checks run one at a time behind the others."""
        if not self.settings.ifcgraph_validate_uploads:
            return 0
        rows = await self.graph.run(
            """
            MATCH (:Project {project_id: $id})-[:HAS_DOCUMENT]->(d:Document)-[:HAS_VERSION]->(v:DocumentVersion)
            WITH d, v ORDER BY v.version_index DESC
            WITH d, collect(v)[0] AS v
            WHERE any(suffix IN $suffixes WHERE toLower(v.file_name) ENDS WITH suffix)
            RETURN v.id AS id, v.storage_key AS storage_key, v.file_name AS file_name
            ORDER BY d.document_id
            LIMIT $limit
            """,
            id=project_id,
            suffixes=list(IFC_SUFFIXES[:2]),
            limit=MAX_RECHECKS,
        )
        for row in rows:
            await self._queue_validation(str(row["id"]), str(row["storage_key"]), str(row["file_name"]))
        log.info("ifc_recheck_after_ids", project_id=project_id, versions=len(rows))
        return len(rows)

    async def _ids_documents(self, project_id: str) -> list[dict[str, Any]]:
        """The latest version of every IDS document in the project of the file being checked (ADR 0015)."""
        return await self.graph.run(
            """
            MATCH (:Project {project_id: $id})-[:HAS_DOCUMENT]->(d:Document)-[:HAS_VERSION]->(v:DocumentVersion)
            WITH d, v ORDER BY v.version_index DESC
            WITH d, collect(v)[0] AS v
            WHERE toLower(v.file_name) ENDS WITH $suffix
            RETURN d.document_id AS document_id, v.version_index AS version_index, d.title AS title,
                   v.storage_key AS storage_key
            ORDER BY document_id
            LIMIT $limit
            """,
            id=project_id,
            suffix=IDS_SUFFIX,
            limit=MAX_IDS_DOCUMENTS,
        )

    async def _ids(self, source: Path, documents: list[dict[str, Any]]) -> dict[str, Any] | None:
        """The file against the project's IDS documents, with IFC-LPG's check (ADR 0015). None when there are none.

        The worker gets the documents' files by their storage paths, which the server made; each finding is tied back
        to its document by the position the worker reports.
        """
        if not documents:
            return None
        listed = [
            {"document_id": d["document_id"], "version_index": int(d["version_index"]), "title": d["title"]}
            for d in documents
        ]
        paths = [str(self.storage.path(document["storage_key"])) for document in documents]
        memory = str(self.settings.ifcgraph_memory_mb)
        command = [sys.executable, "-m", "ifc_lpg.ids", "--memory-mb", memory, "--", str(source), *paths]
        try:
            report = json.loads(await self._in_a_process(command, "the IDS check", answers=(0, 1)))
        except Exception as exc:
            log.warning("ifc_ids_failed", error=type(exc).__name__)
            check = {"name": "ids", "state": STATE_FAILED, "ruleset": _ids_ruleset(), "issue_count": 0}
            return {"check": {**check, "documents": listed}, "issues": [], "error_count": 0, "truncated": False}

        def document_of(entry: dict[str, Any]) -> str:
            return str(listed[int(entry["ids"])]["document_id"])

        def without(entry: dict[str, Any], *keys: str) -> dict[str, Any]:
            return {key: value for key, value in entry.items() if key not in keys}

        not_run = [
            {
                "rule": str(listed[int(entry["ids"])]["title"] or document_of(entry)),
                "error": str(entry["error"]),
                "document_id": document_of(entry),
            }
            for entry in report["rules_not_run"]
        ]
        specifications = [
            {**without(spec, "ids", "title"), "document_id": document_of(spec)}
            for spec in report["specifications"][:MAX_SPECIFICATIONS]
        ]
        return {
            "check": {
                "name": "ids",
                "state": STATE_DONE,
                "ruleset": str(report["ruleset"]),
                "issue_count": int(report["issue_count"]),
                "rules_not_run": not_run,
                "documents": listed,
                "specifications": specifications,
            },
            "issues": [{**without(issue, "ids"), "document_id": document_of(issue)} for issue in report["issues"]],
            "error_count": int(report["error_count"]),
            "truncated": bool(report["truncated"]),
        }

    def _bsdd_client(self) -> BsddClient:
        """The client that asks buildingSMART's Data Dictionary, made once per server process for its cache."""
        if self.bsdd is None:
            self.bsdd = BsddClient(
                self.settings.bsdd_api_url,
                timeout_seconds=self.settings.bsdd_timeout_seconds,
                cache_seconds=self.settings.bsdd_cache_seconds,
            )
        return self.bsdd

    async def _bsdd(self, source: Path) -> dict[str, Any] | None:
        """The file's references to buildingSMART's Data Dictionary and its Pset_ and Qto_ sets against bSDD, when
        enabled (OB-42): a worker reads them out of the file, and the client asks bSDD about each URI. None when the
        check is off. bSDD out of reach, or the lookups outrunning the time limit, fails this check and nothing else;
        what the file says stays out of the log."""
        if not self.settings.bsdd_enabled:
            return None
        client = self._bsdd_client()
        timeout = self.settings.ifcgraph_timeout_seconds
        memory = str(self.settings.ifcgraph_memory_mb)
        command = [sys.executable, "-m", "opencde.ifcgraph.bsdd_refs", str(source), "--memory-mb", memory]
        try:
            answer = await self._in_a_process(command, "reading the bSDD references")
            found = json.loads(answer.strip().splitlines()[-1])
            async with asyncio.timeout(timeout):
                return await check_bsdd(found, client)
        except Exception as exc:
            if isinstance(exc, TimeoutError):
                error = f"the lookups at bSDD exceeded {timeout} s"
            else:
                error = str(exc) if isinstance(exc, BsddUnavailable) else f"{type(exc).__name__}: {exc}"
            log.warning("ifc_bsdd_failed", error=type(exc).__name__)
        check = {"name": "bsdd", "state": STATE_FAILED, "ruleset": bsdd_ruleset(client.host), "issue_count": 0}
        return {"check": {**check, "error": error[:300]}, "issues": [], "error_count": 0, "truncated": False}

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
            "ifc_lpg.worker",
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
        """Write a model back as an IFC file from what the graph holds. Returns the number of instances.

        A model converted without the lossless form cannot be written back, and the error then names the setting."""
        with tempfile.TemporaryDirectory(prefix="ifcgraph-") as tmp:
            records = Path(tmp) / "records.jsonl"
            try:
                instances = await export_records(self.graph, model_id, records)
            except NotExportable as exc:
                facts = await self.conversions.get(model_id) or await model_facts(self.graph, model_id) or {}
                if (facts.get("state") == STATE_DONE or facts.get("whole")) and not facts.get("lossless"):
                    raise NotExportable(
                        f"{exc}: it was converted with OPENCDE_IFC_LPG_LOSSLESS=false or before 3.0.0, and can be "
                        "written back once it is uploaded again"
                    ) from None
                raise
            await self._in_a_process(
                [
                    sys.executable,
                    "-m",
                    "ifc_lpg.writer",
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
            lambda source: ["ifc_lpg.equivalence", str(source), str(written), *extra],
        )

    async def validate_against_upload(self, model_id: str, written: Path) -> dict[str, Any]:
        """What a file breaks of the IFC standard that the one the model was converted from does not (``validation.py``)."""
        return await self._with_upload(
            model_id,
            "the validation",
            lambda source: ["ifc_lpg.validation", str(written), "--against", str(source)],
        )

    async def _with_upload(self, model_id: str, what: str, command: Callable[[Path], list[str]]) -> dict[str, Any]:
        """Run a module of this package on the uploaded file, unpacked. Exit codes 0 and 1 are both answers."""
        conversion = await self.conversions.get(model_id)
        if conversion is None:
            raise ValueError("there is no such model")
        with tempfile.TemporaryDirectory(prefix="ifcgraph-") as tmp:
            source = await asyncio.to_thread(
                self._prepare_input, str(conversion["storage_key"]), str(conversion["file_name"]), Path(tmp)
            )
            arguments = [sys.executable, "-m", *command(source), "--memory-mb", str(self.settings.ifcgraph_memory_mb)]
            return json.loads(await self._in_a_process(arguments, what, answers=(0, 1)))

    # -- the GTIN of BCF components -----------------------------------------------------------------

    async def link_viewpoint(self, *, project_id: str, viewpoint_guid: str) -> int:
        """The GTIN onto one viewpoint's components from the project's finished models (at viewpoint POST)."""
        found = 0
        for model_id in await self.conversions.done_model_ids(project_id):
            found += await self._copy_gtin(model_id, _VIEWPOINT_COMPONENTS, project_id=project_id, guid=viewpoint_guid)
        return found

    async def _link_model(self, model_id: str) -> int:
        """The GTIN onto every component of the project from a model that has just finished importing."""
        conversion = await self.conversions.get(model_id)
        if conversion is None or not conversion.get("project_id"):
            return 0
        return await self._copy_gtin(model_id, _PROJECT_COMPONENTS, project_id=str(conversion["project_id"]))

    async def _copy_gtin(self, model_id: str, scope: str, **params: Any) -> int:
        """Look the GlobalIds of the components a scope matches up in the model (IFC-LPG's ``property_values``)
        and copy the configured property, the GTIN, onto the components that name them; a component keeps its
        GTIN where the model lacks the property. No relationship into the model is made: the element is found by
        its ``GlobalId``. Returns how many of the GlobalIds the model has."""
        rows = await self.graph.run(scope + "WHERE c.ifc_guid IS NOT NULL RETURN DISTINCT c.ifc_guid AS guid", **params)
        guids = [str(row["guid"]) for row in rows if _GUID.match(str(row["guid"]))]
        found = 0
        for start in range(0, len(guids), MAX_GLOBAL_IDS):
            values = await property_values(
                ReadingGraph(self.graph),
                model_id,
                pset=self.settings.ifcgraph_gtin_property_set,
                property=self.settings.ifcgraph_gtin_property,
                global_ids=guids[start : start + MAX_GLOBAL_IDS],
            )
            found += len(values)
            gtins = [{"guid": v["global_id"], "gtin": str(v["value"])} for v in values if v["value"] is not None]
            if gtins:
                await self.graph.run(
                    "UNWIND $gtins AS gtin\n" + scope + "WHERE c.ifc_guid = gtin.guid SET c.gtin = gtin.gtin",
                    gtins=gtins,
                    **params,
                )
        return found

    async def status(self, project_id: str) -> list[dict[str, Any]]:
        """The project's conversions, newest first."""
        return await self.conversions.of_project(project_id)

    # -- clash checks (ADR 0019) ---------------------------------------------------------------------

    async def schedule_clash(self, *, project_id: str, author: str, request: dict[str, Any]) -> str:
        """Queue a clash check between two document versions of a project; returns the check's id."""
        clash_id = new_id()
        await self.graph.run(
            """
            MATCH (p:Project {project_id: $project_id})
            CREATE (p)-[:HAS_CLASH]->(:Clash {
                id: $id, project_id: $project_id, state: $state, request: $request, author: $author, created_at: $now
            })
            """,
            project_id=project_id,
            id=clash_id,
            state=STATE_QUEUED,
            request=json.dumps(request, separators=(",", ":")),
            author=author,
            now=now_iso(),
        )
        task = asyncio.create_task(self._run_clash(clash_id), name=f"ifcclash-{clash_id}")
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return clash_id

    async def _clash_input(self, project_id: str, side: dict[str, Any], workdir: Path) -> Path:
        """The file of one side of a check, from the project's own document versions."""
        rows = await self.graph.run(
            """
            MATCH (:Project {project_id: $project_id})-[:HAS_DOCUMENT]->(:Document {document_id: $document_id})
                  -[:HAS_VERSION]->(v:DocumentVersion {version_index: $version_index})
            RETURN v.storage_key AS storage_key, v.file_name AS file_name
            """,
            project_id=project_id,
            document_id=side["document_id"],
            version_index=side["version_index"],
        )
        if not rows:
            raise ValueError(f"document version {side['document_id']}/{side['version_index']} not found")
        if not self.wants(str(rows[0]["file_name"])):
            raise ValueError(f"document version {side['document_id']}/{side['version_index']} is not an IFC file")
        return await asyncio.to_thread(self._prepare_clash_input, rows[0]["storage_key"], rows[0]["file_name"], workdir)

    def _prepare_clash_input(self, storage_key: str, file_name: str, workdir: Path) -> Path:
        workdir.mkdir(exist_ok=True)
        return self._prepare_input(storage_key, file_name, workdir)

    async def _run_clash(self, clash_id: str) -> None:
        """Run one queued check in the worker process and store its report; the file names stay out of the log."""
        async with self._lock:
            rows = await self.graph.run(
                """
                MATCH (c:Clash {id: $id, state: $queued})
                SET c.state = $running, c.running_at = $now
                RETURN c.project_id AS project_id, c.request AS request
                """,
                id=clash_id,
                queued=STATE_QUEUED,
                running=STATE_RUNNING,
                now=now_iso(),
            )
            if not rows:
                return
            project_id, request = str(rows[0]["project_id"]), json.loads(rows[0]["request"])
            try:
                with tempfile.TemporaryDirectory(prefix="ifcclash-") as tmp:
                    a = await self._clash_input(project_id, request["a"], Path(tmp) / "a")
                    b = await self._clash_input(project_id, request["b"], Path(tmp) / "b")
                    command = [
                        sys.executable,
                        "-m",
                        "opencde.ifcgraph.clash",
                        str(a),
                        str(b),
                        "--mode",
                        str(request["mode"]),
                        "--tolerance",
                        str(request["tolerance"]),
                        "--clearance",
                        str(request["clearance"]),
                        "--max-clashes",
                        str(self.settings.ifcgraph_clash_max_clashes),
                        "--memory-mb",
                        str(self.settings.ifcgraph_memory_mb),
                    ]
                    for flag, side in (("--types-a", "a"), ("--types-b", "b")):
                        if request[side].get("types"):
                            command += [flag, ",".join(request[side]["types"])]
                    answer = await self._in_a_process(command, "the clash check")
                    report = json.loads(answer.strip().splitlines()[-1])
            except Exception as exc:
                log.warning("ifc_clash_failed", clash_id=clash_id, error=type(exc).__name__)
                await self.graph.run(
                    "MATCH (c:Clash {id: $id}) SET c.state = $state, c.failed_at = $now, c.error = $error",
                    id=clash_id,
                    state=STATE_FAILED,
                    now=now_iso(),
                    error=f"{type(exc).__name__}: {exc}"[:300],
                )
                return
            for clash in report["clashes"]:
                for key in ("a", "b"):
                    clash[key] = {
                        "document_id": request[key]["document_id"],
                        "version_index": request[key]["version_index"],
                        **clash[key],
                    }
            await self.graph.run(
                """
                MATCH (c:Clash {id: $id})
                SET c.state = $state, c.done_at = $now, c.count = $count, c.set_a = $set_a, c.set_b = $set_b,
                    c.missing = $missing, c.seconds = $seconds, c.truncated = $truncated, c.report = $report
                """,
                id=clash_id,
                state=STATE_DONE,
                now=now_iso(),
                count=int(report["count"]),
                set_a=int(report["set_a"]),
                set_b=int(report["set_b"]),
                missing=int(report["missing"]),
                seconds=float(report["seconds"]),
                truncated=bool(report["truncated"]),
                report=pack_report(report["clashes"]),
            )
            log.info("ifc_clash_done", clash_id=clash_id, count=report["count"], seconds=report["seconds"])

    async def clash_reports(self, *, user_id: str, project_id: str) -> list[dict[str, Any]]:
        """The checks of a project the user is a member of, newest first, without their clashes."""
        rows = await self.graph.run(
            """
            MATCH (:User {id: $user_id})-[:MEMBER_OF]->(:Project {project_id: $project_id})-[:HAS_CLASH]->(c:Clash)
            RETURN properties(c) AS clash ORDER BY c.created_at DESC LIMIT 100
            """,
            user_id=user_id,
            project_id=project_id,
        )
        return [self._clash_row(row["clash"], with_clashes=False) for row in rows]

    async def clash_report(
        self, *, user_id: str, project_id: str, clash_id: str, with_clashes: bool
    ) -> dict[str, Any] | None:
        """One check, when the user is a member of its project."""
        rows = await self.graph.run(
            """
            MATCH (:User {id: $user_id})-[:MEMBER_OF]->(:Project {project_id: $project_id})
                  -[:HAS_CLASH]->(c:Clash {id: $clash_id})
            RETURN properties(c) AS clash
            """,
            user_id=user_id,
            project_id=project_id,
            clash_id=clash_id,
        )
        return self._clash_row(rows[0]["clash"], with_clashes=with_clashes) if rows else None

    @staticmethod
    def _clash_row(node: dict[str, Any], *, with_clashes: bool) -> dict[str, Any]:
        keys = (
            "id",
            "project_id",
            "state",
            "author",
            "created_at",
            "running_at",
            "done_at",
            "failed_at",
            "error",
            "count",
            "set_a",
            "set_b",
            "missing",
            "seconds",
            "truncated",
        )
        row = {key: node.get(key) for key in keys}
        row["request"] = json.loads(str(node["request"]))
        row["clashes"] = unpack_report(node.get("report")) if with_clashes and node.get("report") else None
        return row


# The components a GTIN is copied onto, one viewpoint's or the project's; ``c`` is the component.
_VIEWPOINT_COMPONENTS = """
MATCH (:Project {project_id: $project_id})-[:HAS_TOPIC]->(:Topic)-[:HAS_VIEWPOINT]->(:Viewpoint {guid: $guid})
      -[:HAS_COMPONENT]->(c:Component)
"""
_PROJECT_COMPONENTS = """
MATCH (:Project {project_id: $project_id})-[:HAS_TOPIC]->(:Topic)-[:HAS_VIEWPOINT]->(:Viewpoint)
      -[:HAS_COMPONENT]->(c:Component)
"""
_GUID = re.compile(r"^[0-9A-Za-z_$]{22}$")  # a component's ifc_guid that is no GlobalId has nothing to look up


def ifcgraph_service(request: Request) -> IfcGraphService | None:
    return getattr(request.app.state, "ifcgraph", None)


IfcGraphDep = Annotated[IfcGraphService | None, Depends(ifcgraph_service)]

__all__ = ["IfcGraphDep", "IfcGraphService", "delete_model", "ifcgraph_service"]
