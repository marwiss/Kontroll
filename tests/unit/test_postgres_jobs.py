# This file was generated with the assistance of an AI coding tool.
"""The jobs area in PostgreSQL (ADR 0029), without a database: the member's reads join the membership, a claim is
one conditional update, a draft's change holds its row, what a job writes goes to its fields and the columns are
its own, the migration's tables and views, and the choice of store. ``test_postgres_store.py`` reads the module's
syntax tree for statements built from strings."""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Any

import pytest

from opencde.odata import Compiled
from opencde.postgres import schema
from opencde.postgres.database import Postgres
from opencde.store.jobs import postgres as jobs
from opencde.store.jobs.clashes import ClashRepository
from opencde.store.jobs.conversions import ConversionRepository
from opencde.store.jobs.drafts import ChangeSetDraft, ChangeSetDraftRepository, DraftRefused
from opencde.store.jobs.merges import MergeRepository
from opencde.store.jobs.postgres import (
    PostgresChangeSetDraftRepository,
    PostgresClashRepository,
    PostgresConversionRepository,
    PostgresMergeRepository,
    PostgresProposalRepository,
    PostgresValidationRepository,
    change_set_draft_store,
    clash_store,
    conversion_store,
    merge_store,
    proposal_store,
    validation_store,
)
from opencde.store.jobs.proposals import ProposalRepository
from opencde.store.jobs.validations import ValidationRepository
from tests.unit.test_postgres_store import URL, WEAK, FakePostgres

NOW = "2026-11-12T10:00:00.000Z"
MEMBER = re.compile(r"JOIN memberships m ON m\.project_id = [a-z]\.project_id AND m\.user_id = \$1")


def _migration() -> str:
    return (schema.MIGRATIONS_DIR / "0005_jobs.sql").read_text(encoding="utf-8")


# -- the statements ------------------------------------------------------------------------------------------------


def test_a_members_read_joins_the_membership_on_the_users_id() -> None:
    """``MEMBER_OF`` in PostgreSQL: every read for a member reaches the job through ``memberships`` on the user's id."""
    for statement in (
        jobs.CONVERSION_FOR_MEMBER,
        jobs.PRECHECK_FOR_MEMBER,
        jobs.PROPOSALS_OF_DOCUMENT,
        jobs.PROPOSALS_OF_DOCUMENT_COUNT,
        jobs.PROPOSAL_OF_TOPIC,
        jobs.DRAFT_GET,
        jobs.DRAFT_TAKE,
        jobs.CLASHES_OF_PROJECT,
        jobs.CLASH_FOR_MEMBER,
        jobs.CLASHES_OPEN,
        jobs.MERGE_PREPARED,
        jobs.MERGE_FOR_MEMBER,
    ):
        assert MEMBER.search(statement), statement
    assert "FROM memberships m JOIN documents d ON d.project_id = m.project_id" in jobs.DRAFT_OPEN
    assert "WHERE m.user_id = $1 AND m.project_id = $2" in jobs.DRAFT_OPEN, "a draft only in the user's project"
    assert "d.user_id = $1" in jobs.DRAFT_GET and "d.user_id = $1" in jobs.DRAFT_TAKE, "a draft is its user's alone"
    assert "JOIN documents d ON d.document_id = r.base_document_id AND d.project_id = r.project_id" in (
        jobs.PROPOSALS_OF_DOCUMENT
    ), "the base document is the project's"


def test_a_job_is_claimed_by_one_conditional_update() -> None:
    """Two processes never run one job: the claim changes the state only where it is still queued."""
    for statement in (
        jobs.CONVERSION_CLAIM,
        jobs.VALIDATION_CLAIM,
        jobs.PROPOSAL_CLAIM,
        jobs.CLASH_CLAIM,
        jobs.MERGE_CLAIM,
    ):
        assert statement.strip().startswith("UPDATE") and "WHERE id = $1 AND state = $2" in statement
        assert "SET state = $3, running_at = $4" in statement and "RETURNING" in statement


async def test_the_claims_name_queued_and_running() -> None:
    fake = FakePostgres(lambda query, args: {"id": args[0], "project_id": "p", "request": "{}"})
    assert await PostgresConversionRepository(fake).claim("m-1")  # ty: ignore[invalid-argument-type]
    assert await PostgresValidationRepository(fake).claim("v-1")  # ty: ignore[invalid-argument-type]
    assert await PostgresClashRepository(fake).claim("c-1") is not None  # ty: ignore[invalid-argument-type]
    assert await PostgresMergeRepository(fake).claim("j-1", model_id="m-2") is not None  # ty: ignore[invalid-argument-type]
    for _, args in fake.statements:
        assert args[1:3] == ("queued", "running")
    assert fake.statements[-1][1][4] == "m-2", "the merge's model with its claim"


async def test_a_value_is_only_ever_an_argument() -> None:
    fake = FakePostgres()
    await PostgresConversionRepository(fake).for_member(user_id=WEAK, document_id=WEAK, version_index=1)  # ty: ignore[invalid-argument-type]
    await PostgresValidationRepository(fake).precheck(user_id=WEAK, project_id=WEAK, precheck_id=WEAK)  # ty: ignore[invalid-argument-type]
    await PostgresProposalRepository(fake).of_topic(user_id=WEAK, project_id=WEAK, topic_guid=WEAK)  # ty: ignore[invalid-argument-type]
    await PostgresChangeSetDraftRepository(fake).get(user_id=WEAK, changeset_id=WEAK)  # ty: ignore[invalid-argument-type]
    await PostgresClashRepository(fake).open_count(user_id=WEAK, author=WEAK)  # ty: ignore[invalid-argument-type]
    await PostgresMergeRepository(fake).get(user_id=WEAK, project_id=WEAK, merge_id=WEAK)  # ty: ignore[invalid-argument-type]
    for statement, args in fake.statements:
        assert WEAK not in statement and WEAK in args


# -- what a job writes ---------------------------------------------------------------------------------------------


async def test_a_conversion_keeps_its_times_as_columns_and_the_rest_as_fields() -> None:
    fake = FakePostgres()
    conversions = PostgresConversionRepository(fake)  # ty: ignore[invalid-argument-type]
    await conversions.set_state("m-1", "done", schema="IFC4", entities=3, spatial_pending=True)
    await conversions.set_state("m-1", "failed", error="RuntimeError: broke")
    await conversions.set_state("m-1", "queued")
    done, failed, queued = (args for _, args in fake.statements)
    assert done[:2] == ("m-1", "done") and done[3] == {"schema": "IFC4", "entities": 3, "spatial_pending": True}
    assert set(failed[3]) == {"error", "failed_at"} and failed[3]["failed_at"] == failed[2]
    assert set(queued[3]) == {"queued_at"}, "running_at and done_at are columns; the others are fields"
    with pytest.raises(ValueError, match="set by the record itself"):
        await conversions.set_fields("m-1", project_id="another")
    with pytest.raises(ValueError, match="not a field that is removed"):
        await conversions.remove_field("m-1", "schema")
    assert len(fake.statements) == 3, "nothing refused reaches the database"


async def test_a_row_comes_back_as_the_graph_gives_the_node() -> None:
    row = {
        "id": "m-1",
        "model_id": "m-1",
        "project_id": "p-1",
        "document_id": None,
        "bcf_document_guid": "b-1",
        "state": "done",
        "done_at": NOW,
        "fields": {"schema": "IFC4", "entities": 3},
    }
    found = await PostgresConversionRepository(FakePostgres(lambda query, args: row)).get("m-1")  # ty: ignore[invalid-argument-type]
    assert found == {
        "id": "m-1",
        "model_id": "m-1",
        "project_id": "p-1",
        "bcf_document_guid": "b-1",
        "state": "done",
        "done_at": NOW,
        "schema": "IFC4",
        "entities": 3,
    }, "the fields beside the columns, and what is null left out"


async def test_a_trials_file_and_base_are_columns_and_its_state_has_its_time() -> None:
    fake = FakePostgres()
    proposals = PostgresProposalRepository(fake)  # ty: ignore[invalid-argument-type]
    await proposals.set_state(
        "r-1", "clean", storage_key="proposals/r.ifc", base_document_id="d-1", base_version_index=2, change_count=4
    )
    await proposals.set_state("r-1", "running")
    (_, clean), (_, running) = fake.statements
    assert clean[:2] == ("r-1", "clean") and clean[3:6] == ("proposals/r.ifc", "d-1", 2)
    assert clean[6] == {"change_count": 4, "clean_at": clean[2]}
    assert running[3:6] == (None, None, None) and running[6] == {}, "running_at is a column"
    with pytest.raises(ValueError, match="topic_guid"):
        await proposals.set_state("r-1", "issues", topic_guid="another")


async def test_a_trial_replaces_the_topics_earlier_one_in_one_transaction() -> None:
    def answer(query: str, args: tuple[Any, ...]) -> Any:
        if query == jobs.PROPOSALS_OF_TOPIC_DELETE:
            return [{"storage_key": "proposals/old.ifc"}, {"storage_key": None}]
        return {"id": args[2]} if query == jobs.PROPOSAL_INSERT else None

    fake = FakePostgres(answer)
    made, gone = await PostgresProposalRepository(fake).create(  # ty: ignore[invalid-argument-type]
        proposal_id="r-2",
        project_id="p-1",
        topic_guid="t-1",
        snippet_key="snippets/s.json",
        author="anna",
        base_document_id="d-1",
        base_version_index=1,
    )
    assert made and gone == ["proposals/old.ifc"] and fake.transactions == 1
    assert [query for query, _ in fake.statements] == [jobs.PROPOSALS_OF_TOPIC_DELETE, jobs.PROPOSAL_INSERT]
    assert "FROM topics t WHERE t.guid = $2 AND t.project_id = $1" in jobs.PROPOSAL_INSERT, "the project's topic"


async def test_a_merges_day_is_a_column_and_the_rest_its_fields() -> None:
    fake = FakePostgres()
    merges = PostgresMergeRepository(fake)  # ty: ignore[invalid-argument-type]
    await merges.set_state("j-1", "done", expires_at=NOW, report="packed")
    await merges.set_state("j-1", "expired")
    (_, done), (_, expired) = fake.statements
    assert done[2] == NOW and set(done[3]) == {"finished_at", "report"}
    assert expired[2] is None and set(expired[3]) == {"finished_at"}, "None keeps the day it had"


async def test_a_check_made_already_is_recorded_with_its_state() -> None:
    fake = FakePostgres()
    checks = PostgresValidationRepository(fake)  # ty: ignore[invalid-argument-type]
    await checks.record(version_id="v-1", storage_key="documents/k", file_name="m.ifc", checked={"state": "done"})
    await checks.keep_precheck(
        precheck_id="q-1",
        project_id="p-1",
        storage_key="prechecks/k",
        file_name="m.ifc",
        author="anna",
        checked={"state": "failed", "error": "x"},
    )
    (_, recorded), (_, kept) = fake.statements
    assert recorded[4] == "done" and recorded[6] == {"done_at": recorded[5]}
    assert kept[5] == "failed" and kept[7] > kept[6] and kept[8] == {"error": "x", "failed_at": kept[6]}


async def test_a_clash_report_and_a_failure_are_fields() -> None:
    fake = FakePostgres()
    clashes = PostgresClashRepository(fake)  # ty: ignore[invalid-argument-type]
    await clashes.finish("c-1", count=2, set_a=3, set_b=4, missing=0, seconds=0.5, truncated=False, report="packed")
    await clashes.fail("c-1", error="ValueError: no file")
    (_, done), (_, failed) = fake.statements
    assert done[1] == "done" and done[2]["count"] == 2 and done[2]["report"] == "packed" and "done_at" in done[2]
    assert failed[1] == "failed" and set(failed[2]) == {"failed_at", "error"}


# -- the open change sets ------------------------------------------------------------------------------------------

DRAFT_ROW = {
    "changeset_id": "c-1",
    "user_id": "u-1",
    "project_id": "p-1",
    "document_id": "d-1",
    "version_index": 2,
    "steps": "[]",
    "refs": 0,
    "topic_guid": None,
    "created_at": NOW,
    "expires_at": NOW,
}


async def test_a_draft_is_opened_under_the_users_lock_and_changed_holding_its_row() -> None:
    assert "FOR UPDATE OF d" in jobs.DRAFT_TAKE and "FOR NO KEY UPDATE" in jobs.DRAFT_USER_LOCK
    fake = FakePostgres(lambda query, args: DRAFT_ROW if query in (jobs.DRAFT_OPEN, jobs.DRAFT_TAKE) else None)
    drafts = PostgresChangeSetDraftRepository(fake)  # ty: ignore[invalid-argument-type]
    opened = await drafts.open(user_id="u-1", project_id="p-1", document_id="d-1", version_index=2)
    assert opened is not None and opened.base == {"document_id": "d-1", "version_index": 2}
    assert [query for query, _ in fake.statements] == [jobs.DRAFT_USER_LOCK, jobs.DRAFT_OPEN]
    assert fake.statements[1][1][7] == 10, "at most MAX_OPEN"

    def add(draft: ChangeSetDraft) -> ChangeSetDraft:
        assert draft.expires_at > NOW, "the change sees the day it is given"
        return replace(draft, steps=[*draft.steps, {"op": "wall"}], refs=1, topic_guid="t-1")

    before = len(fake.statements)
    changed = await drafts.update(user_id="u-1", changeset_id="c-1", change=add)
    assert changed is not None and changed.steps == [{"op": "wall"}] and changed.refs == 1
    assert fake.transactions == 2
    (_, taken), (_, saved) = fake.statements[before:]
    assert taken[:2] == ("u-1", "c-1")
    assert saved[:4] == ("c-1", '[{"op":"wall"}]', 1, "t-1") and saved[4] == changed.expires_at


async def test_a_draft_refuses_too_much_before_it_is_saved() -> None:
    fake = FakePostgres(lambda query, args: DRAFT_ROW if query == jobs.DRAFT_TAKE else None)
    drafts = PostgresChangeSetDraftRepository(fake)  # ty: ignore[invalid-argument-type]
    with pytest.raises(DraftRefused, match="at most 200 steps"):
        await drafts.update(user_id="u-1", changeset_id="c-1", change=lambda d: replace(d, steps=[{"op": "x"}] * 201))
    assert [query for query, _ in fake.statements] == [jobs.DRAFT_TAKE], "nothing was saved"
    assert (
        await PostgresChangeSetDraftRepository(FakePostgres()).update(  # ty: ignore[invalid-argument-type]
            user_id="u-1", changeset_id="c-1", change=lambda d: d
        )
        is None
    ), "an unknown, foreign or expired draft"


async def test_the_listing_pages_by_top_and_skip() -> None:
    fake = FakePostgres()
    page = Compiled(where=None, params={}, order_by="r.created_at DESC", skip=5, limit=10)
    await PostgresProposalRepository(fake).of_document(user_id="u-1", document_id="d-1", compiled=page)  # ty: ignore[invalid-argument-type]
    assert fake.statements == [(jobs.PROPOSALS_OF_DOCUMENT, ("u-1", "d-1", 5, 10))]
    assert "JOIN topics t ON t.guid = r.topic_guid" in jobs.PROPOSALS_OF_DOCUMENT, "the topic's title"


# -- the migration -------------------------------------------------------------------------------------------------


def test_the_jobs_migration_owns_by_foreign_keys_and_keeps_time_canonical() -> None:
    text = _migration()
    assert text.startswith("-- This file was generated with the assistance of an AI coding tool.")
    assert "timestamptz" not in text and "CREATE DOMAIN" not in text, "the accounts' iso_utc"
    for table in ("conversions", "validations", "proposals", "clashes", "merges", "change_set_drafts"):
        assert f"CREATE TABLE {table} (" in text
    assert text.count("REFERENCES projects (project_id) ON DELETE CASCADE") == 6, "a project owns its jobs"
    for owner in ("document_versions (id)", "topics (guid)", "users (id)", "documents (document_id)"):
        assert f"REFERENCES {owner} ON DELETE CASCADE" in text
    assert "expires_at iso_utc NOT NULL" in text and "change_set_drafts_expires_at" in text
    assert "validations_expires_at" in text and "CHECK ((version_id IS NULL) = (expires_at IS NOT NULL))" in text


def test_the_jobs_migration_defines_the_views_the_other_areas_left_empty() -> None:
    text = _migration()
    for view in (
        "project_models",
        "project_files",
        "version_validations",
        "version_graph_checks",
        "conversion_ifc_projects",
        "proposal_files",
    ):
        assert f"CREATE OR REPLACE VIEW {view} (" in text, view
    files = text.split("CREATE OR REPLACE VIEW project_files")[1].split(";")[0]
    assert "FROM document_files" in files and "FROM bcf_files" in files
    assert "FROM proposals" not in files, "a trial's file reaches project_files through bcf_files"


def test_every_job_state_the_code_writes_is_one_the_table_allows() -> None:
    from opencde.ifcgraph import merging, service

    text = _migration()
    proposals = text.split("CREATE TABLE proposals")[1].split(");")[0]
    for state in ("queued", "running", service.STATE_CLEAN, service.STATE_ISSUES, "failed", service.STATE_APPROVED):
        assert f"'{state}'" in proposals
    merges = text.split("CREATE TABLE merges")[1].split(");")[0]
    for state in ("queued", "running", "done", merging.STATE_FAILED, merging.STATE_CONFLICT, merging.STATE_EXPIRED):
        assert f"'{state}'" in merges
    assert f"'{merging.KIND_MERGE}', '{merging.KIND_PREPARE}'" in merges


def test_the_steps_are_kept_as_the_text_that_was_measured() -> None:
    assert "steps text NOT NULL DEFAULT '[]'" in _migration(), "not jsonb, which would reorder what was measured"


# -- the choice of store -------------------------------------------------------------------------------------------


def test_the_graph_holds_the_jobs_unless_postgresql_is_named() -> None:
    graph = object()
    postgres = Postgres(URL, "", connect_timeout_seconds=1.0)
    for choose, on_graph, on_postgres in (
        (conversion_store, ConversionRepository, PostgresConversionRepository),
        (validation_store, ValidationRepository, PostgresValidationRepository),
        (proposal_store, ProposalRepository, PostgresProposalRepository),
        (change_set_draft_store, ChangeSetDraftRepository, PostgresChangeSetDraftRepository),
        (clash_store, ClashRepository, PostgresClashRepository),
        (merge_store, MergeRepository, PostgresMergeRepository),
    ):
        assert isinstance(choose(graph, None), on_graph)  # ty: ignore[invalid-argument-type]
        assert isinstance(choose(graph, postgres), on_postgres)  # ty: ignore[invalid-argument-type]
