# This file was generated with the assistance of an AI coding tool.
"""The jobs area in PostgreSQL (ADR 0029): conversions, checks and prechecks, trials of change sets, clash checks,
merges, and the MCP endpoint's open change sets.

The same protocols as the graph's repositories (``opencde.store.protocols``), over the tables of
``opencde/postgres/migrations/0005_jobs.sql``, with the same rules and answers. A job's identity, owner, state and the
times its queries ask for are columns; what the job writes as it goes (the facts of a conversion, the report of a
check, the result of a trial) is the row's ``fields``, a ``jsonb`` document of values, as the node's properties are in
the graph: a key is a value there, never a column named from input, and a field set to null is removed, as the
graph removes a property set to null. A row comes back as the node does, its fields beside its columns and without
what is null. Claiming a queued job is one ``UPDATE … WHERE state = 'queued' RETURNING``, so that two processes never
both run it; a draft's change takes its row with ``SELECT … FOR UPDATE`` inside the transaction. A member's read joins
``memberships`` on the user's id; every statement is one string literal with numbered parameters; text is ordered by
code point (``COLLATE "C"``), as the graphs order it.

``conversion_store``, ``proposal_store``, ``change_set_draft_store``, ``validation_store``, ``clash_store`` and
``merge_store`` choose between the two: PostgreSQL when ``OPENCDE_STORE_URL`` names it, the graph otherwise.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from opencde.ids import new_id
from opencde.store.jobs.clashes import MAX_LISTED as MAX_CLASHES
from opencde.store.jobs.clashes import ClashRepository
from opencde.store.jobs.conversions import _REMOVABLE as REMOVABLE_FIELDS
from opencde.store.jobs.conversions import (
    STATE_DONE,
    STATE_FAILED,
    STATE_QUEUED,
    STATE_RUNNING,
    ConversionRepository,
)
from opencde.store.jobs.drafts import (
    LIFETIME_SECONDS,
    MAX_OPEN,
    ChangeSetDraft,
    ChangeSetDraftRepository,
    _draft,
    _steps,
)
from opencde.store.jobs.merges import KIND_PREPARE, MergeRepository
from opencde.store.jobs.proposals import ProposalRepository
from opencde.store.jobs.validations import PRECHECK_SECONDS, ValidationRepository
from opencde.timeutil import later_iso, now_iso

if TYPE_CHECKING:
    from opencde.graph.graph import Graph
    from opencde.odata import Compiled
    from opencde.postgres.database import Postgres, Tx
    from opencde.store.protocols import (
        ChangeSetDraftStore,
        ClashStore,
        ConversionStore,
        MergeStore,
        ProposalStore,
        ValidationStore,
    )


def _nodes(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rows as the graph gives the nodes: the fields beside the columns, and nothing that is null."""
    found = []
    for row in rows:
        columns = {name: value for name, value in row.items() if name != "fields" and value is not None}
        found.append({**(row.get("fields") or {}), **columns})
    return found


def _node(row: dict[str, Any] | None) -> dict[str, Any] | None:
    return _nodes([row])[0] if row is not None else None


def _fields(fields: dict[str, Any], own: frozenset[str]) -> dict[str, Any]:
    """The fields as the row keeps them; one that names a column is refused, since the record sets those itself."""
    named = own & fields.keys()
    if named:
        raise ValueError(f"set by the record itself, not as a field: {', '.join(sorted(named))}")
    return fields


# -- conversions -------------------------------------------------------------------------------------------------

#: The columns of ``conversions``; ``running_at`` and ``done_at`` are the times of those states, which the queries ask.
CONVERSION_COLUMNS = frozenset(
    {
        "id",
        "model_id",
        "project_id",
        "document_id",
        "version_index",
        "bcf_document_guid",
        "file_name",
        "storage_key",
        "state",
        "created_at",
        "running_at",
        "done_at",
    }
)

CONVERSION_INSERT = """
INSERT INTO conversions (id, project_id, document_id, version_index, bcf_document_guid, file_name, storage_key, state,
                         created_at)
SELECT $1, p.project_id, $3, $4, $5, $6, $7, $8, $9 FROM projects p WHERE p.project_id = $2
"""
CONVERSION_CLAIM = "UPDATE conversions SET state = $3, running_at = $4 WHERE id = $1 AND state = $2 RETURNING id"
CONVERSION_STATE = """
UPDATE conversions
SET state = $2,
    running_at = CASE WHEN $2 = 'running' THEN $3 ELSE running_at END,
    done_at = CASE WHEN $2 = 'done' THEN $3 ELSE done_at END,
    fields = jsonb_strip_nulls(fields || $4::jsonb)
WHERE id = $1
"""
CONVERSION_FIELDS = "UPDATE conversions SET fields = jsonb_strip_nulls(fields || $2::jsonb) WHERE id = $1"
CONVERSION_REMOVE_FIELD = "UPDATE conversions SET fields = fields - $2::text WHERE id = $1"
CONVERSION_BY_ID = "SELECT c.*, c.id AS model_id FROM conversions c WHERE c.id = $1"
CONVERSIONS_OF_PROJECT = """
SELECT c.*, c.id AS model_id FROM conversions c WHERE c.project_id = $1 ORDER BY c.created_at COLLATE "C" DESC
"""
CONVERSIONS_DONE = "SELECT c.id FROM conversions c WHERE c.project_id = $1 AND c.state = $2"
CONVERSION_LATEST_OF_VERSION = """
SELECT c.*, c.id AS model_id
FROM conversions c
WHERE c.document_id = $1 AND c.version_index = $2 AND (NOT $3::boolean OR c.state = $4)
ORDER BY c.created_at COLLATE "C" DESC
LIMIT 1
"""
CONVERSION_FOR_MEMBER = """
SELECT c.*, c.id AS model_id
FROM conversions c JOIN memberships m ON m.project_id = c.project_id AND m.user_id = $1
WHERE c.document_id = $2 AND c.version_index = $3 AND ($4::text IS NULL OR c.project_id = $4)
  AND (NOT $5::boolean OR c.state = $6)
ORDER BY c.created_at COLLATE "C" DESC
LIMIT 1
"""
CONVERSIONS_INTERRUPTED = """
SELECT c.*, c.id AS model_id FROM conversions c WHERE c.state = $1 OR (c.state = $2 AND c.running_at < $3)
"""
CONVERSIONS_SPATIAL_INTERRUPTED = """
UPDATE conversions
SET fields = (fields - 'spatial_pending') || jsonb_build_object('spatial_error', 'the geometry pass was interrupted')
WHERE state = $1 AND fields -> 'spatial_pending' IS NOT NULL AND done_at < $2
"""
CONVERSIONS_OF_DOCUMENT = "SELECT c.id FROM conversions c WHERE c.document_id = $1"
CONVERSIONS_ALL = """
SELECT c.*, c.id AS model_id FROM conversions c WHERE $1::text IS NULL OR c.project_id = $1
ORDER BY c.project_id COLLATE "C", c.created_at COLLATE "C"
"""
# Per document (Documents API ``document_id``, BCF ``bcf_document_guid``, or the conversion alone), the finished one
# of the highest version first: every one after it, and the first too when it failed.
CONVERSIONS_SUPERSEDED_OR_FAILED = """
SELECT ranked.id
FROM (
    SELECT c.id, c.state,
           row_number() OVER (
               PARTITION BY coalesce(c.document_id, c.bcf_document_guid, c.id)
               ORDER BY CASE WHEN c.state = 'done' THEN 0 ELSE 1 END, coalesce(c.version_index, 0) DESC,
                        coalesce(c.done_at, c.created_at) COLLATE "C" DESC
           ) AS place
    FROM conversions c
    WHERE ($1::text IS NULL OR c.project_id = $1) AND c.state IN ('done', 'failed')
) ranked
WHERE ranked.place > 1 OR ranked.state = 'failed'
"""
CONVERSION_DELETE = "DELETE FROM conversions WHERE id = $1"
CONVERSION_COUNTS = "SELECT project_id, count(*) AS n FROM conversions GROUP BY project_id"


class PostgresConversionRepository:
    def __init__(self, postgres: Postgres) -> None:
        self.postgres = postgres

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
        await self.postgres.execute(
            CONVERSION_INSERT,
            model_id,
            project_id,
            document_id,
            version_index,
            bcf_document_guid,
            file_name,
            storage_key,
            STATE_QUEUED,
            now_iso(),
        )

    async def claim(self, model_id: str) -> bool:
        return await self.postgres.one(CONVERSION_CLAIM, model_id, STATE_QUEUED, STATE_RUNNING, now_iso()) is not None

    async def set_state(self, model_id: str, state: str, **fields: Any) -> None:
        now = now_iso()
        stamp = {} if state in (STATE_RUNNING, STATE_DONE) else {f"{state}_at": now}  # those two are columns
        await self.postgres.execute(
            CONVERSION_STATE, model_id, state, now, {**_fields(fields, CONVERSION_COLUMNS), **stamp}
        )

    async def set_fields(self, model_id: str, **fields: Any) -> None:
        await self.postgres.execute(CONVERSION_FIELDS, model_id, _fields(fields, CONVERSION_COLUMNS))

    async def remove_field(self, model_id: str, name: str) -> None:
        if name not in REMOVABLE_FIELDS:
            raise ValueError(f"not a field that is removed: {name}")
        await self.postgres.execute(CONVERSION_REMOVE_FIELD, model_id, name)

    async def get(self, model_id: str) -> dict[str, Any] | None:
        return _node(await self.postgres.one(CONVERSION_BY_ID, model_id))

    async def of_project(self, project_id: str) -> list[dict[str, Any]]:
        return _nodes(await self.postgres.run(CONVERSIONS_OF_PROJECT, project_id))

    async def done_model_ids(self, project_id: str) -> list[str]:
        return [str(row["id"]) for row in await self.postgres.run(CONVERSIONS_DONE, project_id, STATE_DONE)]

    async def latest_of_version(
        self, *, document_id: str, version_index: int, done_only: bool = True
    ) -> dict[str, Any] | None:
        """The newest conversion of a document version, finished when ``done_only``."""
        return _node(
            await self.postgres.one(CONVERSION_LATEST_OF_VERSION, document_id, version_index, done_only, STATE_DONE)
        )

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
        row = await self.postgres.one(
            CONVERSION_FOR_MEMBER, user_id, document_id, version_index, project_id, done_only, STATE_DONE
        )
        return _node(row)

    async def interrupted(self, *, given_up: str) -> list[dict[str, Any]]:
        """The conversions a stopped server left behind: queued, or running since before ``given_up``."""
        rows = await self.postgres.run(CONVERSIONS_INTERRUPTED, STATE_QUEUED, STATE_RUNNING, given_up)
        return _nodes(rows)

    async def spatial_interrupted(self, *, given_up: str) -> None:
        """A geometry pass a stopped server left pending is given up."""
        await self.postgres.execute(CONVERSIONS_SPATIAL_INTERRUPTED, STATE_DONE, given_up)

    async def model_ids_of_document(self, document_id: str) -> list[str]:
        return [str(row["id"]) for row in await self.postgres.run(CONVERSIONS_OF_DOCUMENT, document_id)]

    async def all(self, *, project_id: str | None = None) -> list[dict[str, Any]]:
        return _nodes(await self.postgres.run(CONVERSIONS_ALL, project_id))

    async def superseded_or_failed(self, *, project_id: str | None = None) -> list[str]:
        """Ids of the models to drop: every failed one, and every finished one that a newer finished conversion of
        the same document (Documents API ``document_id`` or BCF ``bcf_document_guid``) has replaced."""
        return [str(row["id"]) for row in await self.postgres.run(CONVERSIONS_SUPERSEDED_OR_FAILED, project_id)]

    async def delete(self, model_id: str) -> None:
        await self.postgres.execute(CONVERSION_DELETE, model_id)

    async def counts_per_project(self) -> dict[str, int]:
        return {str(row["project_id"] or ""): int(row["n"]) for row in await self.postgres.run(CONVERSION_COUNTS)}


# -- checks and prechecks ----------------------------------------------------------------------------------------

VALIDATION_COLUMNS = frozenset(
    {
        "id",
        "project_id",
        "version_id",
        "storage_key",
        "file_name",
        "author",
        "state",
        "created_at",
        "running_at",
        "expires_at",
    }
)

# A version's check takes its project from the version's document, so that it goes with either.
VALIDATION_QUEUE = """
INSERT INTO validations (id, project_id, version_id, storage_key, file_name, state, created_at)
SELECT $2, d.project_id, v.id, $3, $4, $5, $6
FROM document_versions v JOIN documents d ON d.document_id = v.document_id
WHERE v.id = $1
RETURNING id
"""
VALIDATION_RECORD = """
INSERT INTO validations (id, project_id, version_id, storage_key, file_name, state, created_at, fields)
SELECT $2, d.project_id, v.id, $3, $4, $5, $6, $7::jsonb
FROM document_versions v JOIN documents d ON d.document_id = v.document_id
WHERE v.id = $1
"""
VALIDATION_CLAIM = "UPDATE validations SET state = $3, running_at = $4 WHERE id = $1 AND state = $2 RETURNING id"
VALIDATION_STATE = """
UPDATE validations
SET state = $2, running_at = CASE WHEN $2 = 'running' THEN $3 ELSE running_at END,
    fields = jsonb_strip_nulls(fields || $4::jsonb)
WHERE id = $1
"""
VALIDATION_PROJECT = "SELECT project_id FROM validations WHERE id = $1"
VALIDATIONS_INTERRUPTED = """
SELECT id, storage_key, file_name, state FROM validations WHERE state = $1 OR (state = $2 AND running_at < $3)
"""
PRECHECK_OPEN = """
INSERT INTO validations (id, project_id, storage_key, file_name, author, state, created_at, expires_at)
SELECT $1, p.project_id, $3, $4, $5, $6, $7, $8 FROM projects p WHERE p.project_id = $2
RETURNING id
"""
PRECHECK_KEEP = """
INSERT INTO validations (id, project_id, storage_key, file_name, author, state, created_at, expires_at, fields)
SELECT $1, p.project_id, $3, $4, $5, $6, $7, $8, $9::jsonb FROM projects p WHERE p.project_id = $2
"""
PRECHECK_FOR_MEMBER = """
SELECT r.* FROM validations r JOIN memberships m ON m.project_id = r.project_id AND m.user_id = $1
WHERE r.project_id = $2 AND r.id = $3 AND r.version_id IS NULL
"""


def _checked(checked: dict[str, Any], now: str) -> tuple[str, dict[str, Any]]:
    """A check made already: its state, and its fields with the time of that state."""
    fields = dict(checked)
    state = str(fields.pop("state"))
    return state, {**_fields(fields, VALIDATION_COLUMNS), f"{state}_at": now}


class PostgresValidationRepository:
    def __init__(self, postgres: Postgres) -> None:
        self.postgres = postgres

    async def queue(self, *, validation_id: str, version_id: str, storage_key: str, file_name: str) -> bool:
        row = await self.postgres.one(
            VALIDATION_QUEUE, version_id, validation_id, storage_key, file_name, STATE_QUEUED, now_iso()
        )
        return row is not None

    async def record(self, *, version_id: str, storage_key: str, file_name: str, checked: dict[str, Any]) -> None:
        now = now_iso()
        state, fields = _checked(checked, now)
        await self.postgres.execute(VALIDATION_RECORD, version_id, new_id(), storage_key, file_name, state, now, fields)

    async def claim(self, validation_id: str) -> bool:
        row = await self.postgres.one(VALIDATION_CLAIM, validation_id, STATE_QUEUED, STATE_RUNNING, now_iso())
        return row is not None

    async def set_state(self, validation_id: str, state: str, **fields: Any) -> None:
        now = now_iso()
        stamp = {} if state == STATE_RUNNING else {f"{state}_at": now}
        await self.postgres.execute(
            VALIDATION_STATE, validation_id, state, now, {**_fields(fields, VALIDATION_COLUMNS), **stamp}
        )

    async def project_of(self, validation_id: str) -> str | None:
        row = await self.postgres.one(VALIDATION_PROJECT, validation_id)
        return str(row["project_id"]) if row else None

    async def interrupted(self, *, given_up: str) -> list[dict[str, Any]]:
        return await self.postgres.run(VALIDATIONS_INTERRUPTED, STATE_QUEUED, STATE_RUNNING, given_up)

    async def open_precheck(
        self, *, precheck_id: str, project_id: str, storage_key: str, file_name: str, author: str
    ) -> bool:
        row = await self.postgres.one(
            PRECHECK_OPEN,
            precheck_id,
            project_id,
            storage_key,
            file_name,
            author,
            STATE_QUEUED,
            now_iso(),
            later_iso(PRECHECK_SECONDS),
        )
        return row is not None

    async def keep_precheck(
        self,
        *,
        precheck_id: str,
        project_id: str,
        storage_key: str,
        file_name: str,
        author: str,
        checked: dict[str, Any],
    ) -> None:
        now = now_iso()
        state, fields = _checked(checked, now)
        await self.postgres.execute(
            PRECHECK_KEEP,
            precheck_id,
            project_id,
            storage_key,
            file_name,
            author,
            state,
            now,
            later_iso(PRECHECK_SECONDS),
            fields,
        )

    async def precheck(self, *, user_id: str, project_id: str, precheck_id: str) -> dict[str, Any] | None:
        return _node(await self.postgres.one(PRECHECK_FOR_MEMBER, user_id, project_id, precheck_id))


# -- trials of change sets ---------------------------------------------------------------------------------------

#: The columns of ``proposals`` that no field sets; the trial's result sets its file and its base as columns.
PROPOSAL_COLUMNS = frozenset(
    {"id", "project_id", "topic_guid", "snippet_key", "author", "state", "created_at", "running_at"}
)

# The listing: the proposals of the user's projects that name the document, a document of the same project, as their
# base, each with its topic's title and description; newest first.
PROPOSALS_OF_DOCUMENT = """
SELECT r.project_id, r.topic_guid, t.title, t.description, r.state, r.base_version_index,
       (r.fields ->> 'change_count')::integer AS change_count, r.author, r.fields ->> 'checked_at' AS checked_at,
       (r.fields ->> 'version_index')::integer AS version_index
FROM proposals r
JOIN memberships m ON m.project_id = r.project_id AND m.user_id = $1
JOIN documents d ON d.document_id = r.base_document_id AND d.project_id = r.project_id
JOIN topics t ON t.guid = r.topic_guid AND t.project_id = r.project_id
WHERE r.base_document_id = $2
ORDER BY r.created_at COLLATE "C" DESC, r.id COLLATE "C"
OFFSET $3 LIMIT $4
"""
PROPOSALS_OF_DOCUMENT_COUNT = """
SELECT count(*) AS total
FROM proposals r
JOIN memberships m ON m.project_id = r.project_id AND m.user_id = $1
JOIN documents d ON d.document_id = r.base_document_id AND d.project_id = r.project_id
JOIN topics t ON t.guid = r.topic_guid AND t.project_id = r.project_id
WHERE r.base_document_id = $2
"""
PROPOSALS_OF_TOPIC_DELETE = "DELETE FROM proposals WHERE project_id = $1 AND topic_guid = $2 RETURNING storage_key"
# The topic must be the project's: the trial takes both from the topic's row.
PROPOSAL_INSERT = """
INSERT INTO proposals (id, project_id, topic_guid, snippet_key, author, state, created_at, base_document_id,
                       base_version_index)
SELECT $3, t.project_id, t.guid, $4, $5, $6, $7, $8, $9 FROM topics t WHERE t.guid = $2 AND t.project_id = $1
RETURNING id
"""
PROPOSAL_CLAIM = """
UPDATE proposals SET state = $3, running_at = $4 WHERE id = $1 AND state = $2
RETURNING project_id, snippet_key, author
"""
PROPOSAL_STATE = """
UPDATE proposals
SET state = $2, running_at = CASE WHEN $2 = 'running' THEN $3 ELSE running_at END,
    storage_key = coalesce($4, storage_key), base_document_id = coalesce($5, base_document_id),
    base_version_index = coalesce($6, base_version_index), fields = jsonb_strip_nulls(fields || $7::jsonb)
WHERE id = $1
"""
PROPOSAL_BY_ID = "SELECT project_id, snippet_key, author FROM proposals WHERE id = $1"
PROPOSAL_SNIPPET = """
SELECT snippet_key FROM proposals WHERE project_id = $1 AND topic_guid = $2
ORDER BY created_at COLLATE "C" DESC LIMIT 1
"""
PROPOSAL_OF_TOPIC = """
SELECT r.* FROM proposals r JOIN memberships m ON m.project_id = r.project_id AND m.user_id = $1
WHERE r.project_id = $2 AND r.topic_guid = $3
ORDER BY r.created_at COLLATE "C" DESC LIMIT 1
"""
PROPOSALS_INTERRUPTED = "SELECT id, state FROM proposals WHERE state = $1 OR (state = $2 AND running_at < $3)"


class PostgresProposalRepository:
    def __init__(self, postgres: Postgres) -> None:
        self.postgres = postgres

    async def count(self, *, user_id: str, document_id: str, compiled: Compiled) -> int:
        """How many proposals name the document as their base, before ``$top`` and ``$skip``."""
        row = await self.postgres.one(PROPOSALS_OF_DOCUMENT_COUNT, user_id, document_id)
        return int(row["total"]) if row else 0

    async def of_document(self, *, user_id: str, document_id: str, compiled: Compiled) -> list[dict[str, Any]]:
        """One row per proposal, newest first; the listing filters on no field, so ``compiled`` gives the page."""
        return await self.postgres.run(PROPOSALS_OF_DOCUMENT, user_id, document_id, compiled.skip, compiled.limit)

    async def create(
        self,
        *,
        proposal_id: str,
        project_id: str,
        topic_guid: str,
        snippet_key: str,
        author: str,
        base_document_id: str | None,
        base_version_index: int | None,
    ) -> tuple[bool, list[str]]:
        async def work(tx: Tx) -> tuple[bool, list[str]]:
            gone = await tx.run(PROPOSALS_OF_TOPIC_DELETE, project_id, topic_guid)
            made = await tx.one(
                PROPOSAL_INSERT,
                project_id,
                topic_guid,
                proposal_id,
                snippet_key,
                author,
                STATE_QUEUED,
                now_iso(),
                base_document_id,
                base_version_index,
            )
            return made is not None, [str(row["storage_key"]) for row in gone if row["storage_key"]]

        return await self.postgres.write(work)

    async def claim(self, proposal_id: str) -> dict[str, Any] | None:
        return await self.postgres.one(PROPOSAL_CLAIM, proposal_id, STATE_QUEUED, STATE_RUNNING, now_iso())

    async def set_state(self, proposal_id: str, state: str, **fields: Any) -> None:
        now = now_iso()
        rest = dict(fields)
        storage_key, base_document_id, base_version_index = (
            rest.pop("storage_key", None),
            rest.pop("base_document_id", None),
            rest.pop("base_version_index", None),
        )
        stamp = {} if state == STATE_RUNNING else {f"{state}_at": now}
        await self.postgres.execute(
            PROPOSAL_STATE,
            proposal_id,
            state,
            now,
            storage_key,
            base_document_id,
            base_version_index,
            {**_fields(rest, PROPOSAL_COLUMNS), **stamp},
        )

    async def get(self, proposal_id: str) -> dict[str, Any] | None:
        return await self.postgres.one(PROPOSAL_BY_ID, proposal_id)

    async def snippet_key(self, *, project_id: str, topic_guid: str) -> str | None:
        row = await self.postgres.one(PROPOSAL_SNIPPET, project_id, topic_guid)
        return str(row["snippet_key"]) if row and row["snippet_key"] else None

    async def of_topic(self, *, user_id: str, project_id: str, topic_guid: str) -> dict[str, Any] | None:
        return _node(await self.postgres.one(PROPOSAL_OF_TOPIC, user_id, project_id, topic_guid))

    async def interrupted(self, *, given_up: str) -> list[dict[str, Any]]:
        return await self.postgres.run(PROPOSALS_INTERRUPTED, STATE_QUEUED, STATE_RUNNING, given_up)


# -- the open change sets of the MCP endpoint --------------------------------------------------------------------

#: A user's drafts are opened one after the other, so that two calls at once do not both find room for one more.
DRAFT_USER_LOCK = "SELECT id FROM users WHERE id = $1 FOR NO KEY UPDATE"
# The document must be the project's, and the user one of its members with fewer than MAX_OPEN open drafts.
DRAFT_OPEN = """
INSERT INTO change_set_drafts (changeset_id, user_id, project_id, document_id, version_index, created_at, expires_at)
SELECT $5, m.user_id, m.project_id, d.document_id, $4, $6::text, $7
FROM memberships m JOIN documents d ON d.project_id = m.project_id AND d.document_id = $3
WHERE m.user_id = $1 AND m.project_id = $2
  AND (SELECT count(*)
       FROM change_set_drafts o JOIN memberships om ON om.project_id = o.project_id AND om.user_id = $1
       WHERE o.user_id = $1 AND o.expires_at > $6::text) < $8
RETURNING changeset_id, user_id, project_id, document_id, version_index, steps, refs, topic_guid, created_at,
          expires_at
"""
DRAFT_GET = """
SELECT d.changeset_id, d.user_id, d.project_id, d.document_id, d.version_index, d.steps, d.refs, d.topic_guid,
       d.created_at, d.expires_at
FROM change_set_drafts d JOIN memberships m ON m.project_id = d.project_id AND m.user_id = $1
WHERE d.changeset_id = $2 AND d.user_id = $1 AND d.expires_at > $3
"""
# Writing first takes the draft's row, so that two calls at once add their steps one after the other; the read
# that follows the lock sees what the other call wrote.
DRAFT_TAKE = """
SELECT d.changeset_id, d.user_id, d.project_id, d.document_id, d.version_index, d.steps, d.refs, d.topic_guid,
       d.created_at, d.expires_at
FROM change_set_drafts d JOIN memberships m ON m.project_id = d.project_id AND m.user_id = $1
WHERE d.changeset_id = $2 AND d.user_id = $1 AND d.expires_at > $3
FOR UPDATE OF d
"""
DRAFT_SAVE = """
UPDATE change_set_drafts SET steps = $2, refs = $3, topic_guid = $4, expires_at = $5 WHERE changeset_id = $1
"""


class PostgresChangeSetDraftRepository:
    def __init__(self, postgres: Postgres) -> None:
        self.postgres = postgres

    async def open(
        self, *, user_id: str, project_id: str, document_id: str, version_index: int
    ) -> ChangeSetDraft | None:
        """A new, empty draft on a version of a document of one of the user's projects; None when the user has
        ``MAX_OPEN`` open already (or the document is not the project's)."""
        now = now_iso()

        async def work(tx: Tx) -> dict[str, Any] | None:
            await tx.one(DRAFT_USER_LOCK, user_id)
            return await tx.one(
                DRAFT_OPEN,
                user_id,
                project_id,
                document_id,
                version_index,
                new_id(),
                now,
                later_iso(LIFETIME_SECONDS),
                MAX_OPEN,
            )

        row = await self.postgres.write(work)
        return _draft(row) if row else None

    async def get(self, *, user_id: str, changeset_id: str) -> ChangeSetDraft | None:
        row = await self.postgres.one(DRAFT_GET, user_id, changeset_id, now_iso())
        return _draft(row) if row else None

    async def update(
        self, *, user_id: str, changeset_id: str, change: Callable[[ChangeSetDraft], ChangeSetDraft]
    ) -> ChangeSetDraft | None:
        """As the graph's: ``change`` gets the draft as it is, in the transaction that holds its row, and may be
        called again when PostgreSQL rolls the transaction back and it is retried."""

        async def work(tx: Tx) -> ChangeSetDraft | None:
            row = await tx.one(DRAFT_TAKE, user_id, changeset_id, now_iso())
            if row is None:
                return None
            expires_at = later_iso(LIFETIME_SECONDS)
            found = replace(_draft(row), expires_at=expires_at)
            changed = change(found)
            saved = replace(found, steps=changed.steps, refs=changed.refs, topic_guid=changed.topic_guid)
            await tx.execute(DRAFT_SAVE, changeset_id, _steps(saved), saved.refs, saved.topic_guid, expires_at)
            return saved

        return await self.postgres.write(work)


# -- clash checks ------------------------------------------------------------------------------------------------

CLASH_INSERT = """
INSERT INTO clashes (id, project_id, state, request, author, created_at)
SELECT $1, p.project_id, $3, $4, $5, $6 FROM projects p WHERE p.project_id = $2
"""
CLASH_CLAIM = (
    "UPDATE clashes SET state = $3, running_at = $4 WHERE id = $1 AND state = $2 RETURNING project_id, request"
)
CLASH_STATE = "UPDATE clashes SET state = $2, fields = jsonb_strip_nulls(fields || $3::jsonb) WHERE id = $1"
CLASHES_OF_PROJECT = """
SELECT c.* FROM clashes c JOIN memberships m ON m.project_id = c.project_id AND m.user_id = $1
WHERE c.project_id = $2
ORDER BY c.created_at COLLATE "C" DESC, c.id COLLATE "C"
LIMIT $3
"""
CLASH_FOR_MEMBER = """
SELECT c.* FROM clashes c JOIN memberships m ON m.project_id = c.project_id AND m.user_id = $1
WHERE c.project_id = $2 AND c.id = $3
"""
CLASHES_OPEN = """
SELECT count(*) AS n FROM clashes c JOIN memberships m ON m.project_id = c.project_id AND m.user_id = $1
WHERE c.author = $2 AND c.state IN ('queued', 'running')
"""


class PostgresClashRepository:
    def __init__(self, postgres: Postgres) -> None:
        self.postgres = postgres

    async def create(self, *, clash_id: str, project_id: str, author: str, request: str) -> None:
        await self.postgres.execute(CLASH_INSERT, clash_id, project_id, STATE_QUEUED, request, author, now_iso())

    async def claim(self, clash_id: str) -> dict[str, Any] | None:
        return await self.postgres.one(CLASH_CLAIM, clash_id, STATE_QUEUED, STATE_RUNNING, now_iso())

    async def fail(self, clash_id: str, *, error: str) -> None:
        await self.postgres.execute(CLASH_STATE, clash_id, STATE_FAILED, {"failed_at": now_iso(), "error": error})

    async def finish(
        self,
        clash_id: str,
        *,
        count: int,
        set_a: int,
        set_b: int,
        missing: int,
        seconds: float,
        truncated: bool,
        report: str,
    ) -> None:
        result = {"count": count, "set_a": set_a, "set_b": set_b, "missing": missing, "seconds": seconds}
        fields = {"done_at": now_iso(), **result, "truncated": truncated, "report": report}
        await self.postgres.execute(CLASH_STATE, clash_id, STATE_DONE, fields)

    async def of_project(self, *, user_id: str, project_id: str) -> list[dict[str, Any]]:
        rows = await self.postgres.run(CLASHES_OF_PROJECT, user_id, project_id, MAX_CLASHES)
        return _nodes(rows)

    async def get(self, *, user_id: str, project_id: str, clash_id: str) -> dict[str, Any] | None:
        return _node(await self.postgres.one(CLASH_FOR_MEMBER, user_id, project_id, clash_id))

    async def open_count(self, *, user_id: str, author: str) -> int:
        row = await self.postgres.one(CLASHES_OPEN, user_id, author)
        return int(row["n"]) if row else 0


# -- merges ------------------------------------------------------------------------------------------------------

MERGE_COLUMNS = frozenset(
    {"id", "project_id", "kind", "state", "request", "author", "created_at", "running_at", "model_id"}
)

MERGE_INSERT = """
INSERT INTO merges (id, project_id, kind, state, request, author, created_at)
SELECT $1, p.project_id, $3, $4, $5, $6, $7 FROM projects p WHERE p.project_id = $2
"""
MERGE_CLAIM = """
UPDATE merges SET state = $3, running_at = $4, model_id = $5 WHERE id = $1 AND state = $2
RETURNING project_id, request, author, kind
"""
MERGE_STATE = """
UPDATE merges
SET state = $2, expires_at = coalesce($3, expires_at), fields = jsonb_strip_nulls(fields || $4::jsonb)
WHERE id = $1
"""
MERGE_PREPARED = """
SELECT j.model_id, j.request FROM merges j JOIN memberships m ON m.project_id = j.project_id AND m.user_id = $1
WHERE j.project_id = $2 AND j.id = $3 AND j.kind = $4 AND j.state = $5 AND j.expires_at > $6
"""
MERGE_FOR_MEMBER = """
SELECT j.* FROM merges j JOIN memberships m ON m.project_id = j.project_id AND m.user_id = $1
WHERE j.project_id = $2 AND j.id = $3
"""
MERGES_EXPIRED = "SELECT id, model_id FROM merges WHERE kind = $1 AND state = $2 AND expires_at <= $3"
MERGES_INTERRUPTED = """
SELECT id, state, model_id FROM merges WHERE state = $1 OR (state = $2 AND running_at < $3)
"""


class PostgresMergeRepository:
    def __init__(self, postgres: Postgres) -> None:
        self.postgres = postgres

    async def create(self, *, merge_id: str, project_id: str, kind: str, author: str, request: str) -> None:
        await self.postgres.execute(MERGE_INSERT, merge_id, project_id, kind, STATE_QUEUED, request, author, now_iso())

    async def claim(self, merge_id: str, *, model_id: str) -> dict[str, Any] | None:
        return await self.postgres.one(MERGE_CLAIM, merge_id, STATE_QUEUED, STATE_RUNNING, now_iso(), model_id)

    async def set_state(self, merge_id: str, state: str, **fields: Any) -> None:
        rest = {"finished_at": now_iso(), **fields}
        expires_at = rest.pop("expires_at", None)  # a preparation's day, which the job's round asks for
        await self.postgres.execute(MERGE_STATE, merge_id, state, expires_at, _fields(rest, MERGE_COLUMNS))

    async def prepared(self, *, user_id: str, project_id: str, prepare_id: str) -> dict[str, Any] | None:
        return await self.postgres.one(
            MERGE_PREPARED, user_id, project_id, prepare_id, KIND_PREPARE, STATE_DONE, now_iso()
        )

    async def get(self, *, user_id: str, project_id: str, merge_id: str) -> dict[str, Any] | None:
        return _node(await self.postgres.one(MERGE_FOR_MEMBER, user_id, project_id, merge_id))

    async def expired_preparations(self) -> list[dict[str, Any]]:
        return await self.postgres.run(MERGES_EXPIRED, KIND_PREPARE, STATE_DONE, now_iso())

    async def interrupted(self, *, given_up: str) -> list[dict[str, Any]]:
        return await self.postgres.run(MERGES_INTERRUPTED, STATE_QUEUED, STATE_RUNNING, given_up)


# -- where the jobs are ------------------------------------------------------------------------------------------


def conversion_store(graph: Graph, postgres: Postgres | None) -> ConversionStore:
    return PostgresConversionRepository(postgres) if postgres is not None else ConversionRepository(graph)


def validation_store(graph: Graph, postgres: Postgres | None) -> ValidationStore:
    return PostgresValidationRepository(postgres) if postgres is not None else ValidationRepository(graph)


def proposal_store(graph: Graph, postgres: Postgres | None) -> ProposalStore:
    return PostgresProposalRepository(postgres) if postgres is not None else ProposalRepository(graph)


def change_set_draft_store(graph: Graph, postgres: Postgres | None) -> ChangeSetDraftStore:
    return PostgresChangeSetDraftRepository(postgres) if postgres is not None else ChangeSetDraftRepository(graph)


def clash_store(graph: Graph, postgres: Postgres | None) -> ClashStore:
    return PostgresClashRepository(postgres) if postgres is not None else ClashRepository(graph)


def merge_store(graph: Graph, postgres: Postgres | None) -> MergeStore:
    return PostgresMergeRepository(postgres) if postgres is not None else MergeRepository(graph)
