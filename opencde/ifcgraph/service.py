# This file was generated with the assistance of an AI coding tool.
"""Scheduling conversions and checks of uploads, and linking BCF components to model elements.

``IfcGraphService.schedule`` records an ``IfcModel`` node (state ``queued``),
then converts in the background: the file is handed to the worker process
(``.ifczip`` is unpacked first, with a size cap), the worker's records are
imported, and the node ends in state ``done`` or ``failed`` with counts or an
error. A file uploaded as a document version is also checked against the IFC
schema (``validation.py``), with the result on an ``IfcValidation`` node below
the version, which the Documents API shows (ADR 0011), against buildingSMART's
rules where they are installed (ADR 0012), and against the IDS documents of its
project (ADR 0015). Two versions are compared for clashes on request, in the
same worker pattern (ADR 0019, ``clash.py``). One job runs at a time, the check
of a file before its conversion.
"""

from __future__ import annotations

import asyncio
import contextlib
import importlib.metadata
import json
import sys
import tempfile
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, Request
from ifc_lpg.exporter import NotExportable, export_records
from ifc_lpg.gherkin_install import MANIFEST
from ifc_lpg.importer import delete_blocks, delete_model, import_records
from ifc_lpg.validation import MAX_REPORTED, pack_report, unpack_report

from opencde.graph.graph import Graph
from opencde.ids import new_id
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
IDS_SUFFIX = ".ids"
# The IDS documents of one project an upload is checked against, and the specifications its report keeps (ADR 0015).
MAX_IDS_DOCUMENTS = 50
PRECHECK_SECONDS = 24 * 3600  # a file checked without becoming a version is kept this long (ADR 0021)
MAX_SPECIFICATIONS = 1_000


def _failure(exc: Exception) -> dict[str, Any]:
    """The fields of a check that could not run; the message is cut, as it may quote the file."""
    return {"checked_at": now_iso(), "error": f"{type(exc).__name__}: {exc}"[:300]}


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
        version_id: str | None = None,
        checked: dict[str, Any] | None = None,
    ) -> str | None:
        """Queue a conversion for an uploaded IFC file; returns the model id, or None for other files.

        A document version (``version_id``) is checked against the IFC schema too, before it is converted, unless
        ``checked`` brings the result of a check made before the version existed (``check_now``).
        """
        if not self.wants(file_name):
            return None
        if version_id is not None and self.settings.ifcgraph_validate_uploads:
            if checked is None:
                await self._queue_validation(version_id, storage_key, file_name)
            else:
                await self._record_validation(version_id, storage_key, file_name, checked)
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
        if not self.settings.ifcgraph_validate_uploads:
            return
        rows = await self.graph.run(
            """
            MATCH (r:IfcValidation)
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
                geometry=header.get("geometry"),  # skeleton, blocks or nodes (IFC-LPG 1.0.0 of 2026-11-10)
                ifc_header=header.get("ifc_header"),
            )
            # Viewpoints created before the model finished (or before it was uploaded) get their links now.
            try:
                linked = await self._link_model(model_id)
            except Exception as exc:  # the import itself succeeded; linking can be repeated by a new viewpoint
                log.warning("ifcgraph_link_failed", model_id=model_id, error=f"{type(exc).__name__}: {exc}"[:200])
                linked = 0
            log.info("ifcgraph_imported", model_id=model_id, linked=linked, **counts)

    # -- checking an upload against the IFC schema ------------------------------------------------

    async def _queue_validation(self, version_id: str, storage_key: str, file_name: str) -> None:
        validation_id = new_id()
        rows = await self.graph.run(
            """
            MATCH (v:DocumentVersion {id: $version_id})
            CREATE (v)-[:HAS_VALIDATION]->(r:IfcValidation {
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
            "MATCH (r:IfcValidation {id: $id}) SET r.state = $state, r += $fields",
            id=validation_id,
            state=state,
            fields={**fields, f"{state}_at": now_iso()},
        )

    async def _validate(self, validation_id: str, storage_key: str, file_name: str) -> None:
        """Check one upload; the issues may quote the file, so only their number is logged."""
        async with self._lock:
            rows = await self.graph.run(
                """
                MATCH (r:IfcValidation {id: $id, state: $queued})
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
            MATCH (r:IfcValidation {id: $id})
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
        """The IFC schema, buildingSMART's rules and the project's IDS documents on one file.

        The fields of an ``IfcValidation`` node in state ``done``; an exception when the file could not be checked.
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
        for other in (gherkin, ids):
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

        The fields of an ``IfcValidation`` node with its ``state``, ``done`` or ``failed``; None for a file that is
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
        """A check made before the version existed (``check_now``) becomes the version's ``IfcValidation`` node."""
        now = now_iso()
        await self.graph.run(
            """
            MATCH (v:DocumentVersion {id: $version_id})
            CREATE (v)-[:HAS_VALIDATION]->(r:IfcValidation {id: $id, storage_key: $storage_key, file_name: $file_name})
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
            CREATE (p)-[:HAS_PRECHECK]->(r:IfcValidation:IfcPrecheck {
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
            CREATE (p)-[:HAS_PRECHECK]->(r:IfcValidation:IfcPrecheck {
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
                  -[:HAS_PRECHECK]->(r:IfcPrecheck {id: $id})
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
                rows = await self.graph.run(
                    "MATCH (m:IfcModel {id: $id}) RETURN m.state AS state, m.lossless AS lossless", id=model_id
                )
                if rows and rows[0]["state"] == STATE_DONE and not rows[0]["lossless"]:
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

    # -- clash checks (ADR 0019) ---------------------------------------------------------------------

    async def schedule_clash(self, *, project_id: str, author: str, request: dict[str, Any]) -> str:
        """Queue a clash check between two document versions of a project; returns the check's id."""
        clash_id = new_id()
        await self.graph.run(
            """
            MATCH (p:Project {project_id: $project_id})
            CREATE (p)-[:HAS_CLASH]->(:IfcClash {
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
                MATCH (c:IfcClash {id: $id, state: $queued})
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
                    "MATCH (c:IfcClash {id: $id}) SET c.state = $state, c.failed_at = $now, c.error = $error",
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
                MATCH (c:IfcClash {id: $id})
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
            MATCH (:User {id: $user_id})-[:MEMBER_OF]->(:Project {project_id: $project_id})-[:HAS_CLASH]->(c:IfcClash)
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
                  -[:HAS_CLASH]->(c:IfcClash {id: $clash_id})
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
