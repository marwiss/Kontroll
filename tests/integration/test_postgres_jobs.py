# This file was generated with the assistance of an AI coding tool.
"""The jobs area in PostgreSQL (ADR 0029) against a real database: the same tests on the graph's repositories and on
PostgreSQL's (conversions, checks and prechecks, trials, open change sets, clash checks and merges), and PostgreSQL's
own: the views the other areas read, the cleaner, and what goes with what it belongs to.

PostgreSQL runs in a container of its own (``postgres_target`` and ``pg`` in the conftest), one per test session;
every test starts from empty tables with the migrations applied. Each case runs once on the graph and once on
PostgreSQL, which needs no graph: ``-k on_postgresql`` starts PostgreSQL alone. What a job belongs to in another area,
a document version or a topic, is made by ``World``: nodes in the graph, rows of the documents' and the BCF tables in
PostgreSQL, with the columns those areas' migrations require.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Protocol

import pytest
from ifc_db.validation import pack_report

from opencde.accounts.roles import Role
from opencde.graph.graph import Graph
from opencde.ids import new_id
from opencde.odata import Compiled
from opencde.postgres.cleanup import delete_expired
from opencde.postgres.database import Postgres
from opencde.postgres.schema import migrate, migrations
from opencde.storage import LocalStorage
from opencde.store.accounts.postgres import PostgresProjectRepository, PostgresUserRepository
from opencde.store.accounts.projects import Project, ProjectRepository
from opencde.store.accounts.users import User, UserRepository
from opencde.store.jobs import postgres as jobs_postgres
from opencde.store.jobs.clashes import ClashRepository
from opencde.store.jobs.conversions import ConversionRepository
from opencde.store.jobs.drafts import MAX_OPEN, ChangeSetDraft, ChangeSetDraftRepository, DraftRefused
from opencde.store.jobs.merges import MergeRepository
from opencde.store.jobs.postgres import (
    PostgresChangeSetDraftRepository,
    PostgresClashRepository,
    PostgresConversionRepository,
    PostgresMergeRepository,
    PostgresProposalRepository,
    PostgresValidationRepository,
)
from opencde.store.jobs.proposals import DEFAULT_ORDER, ProposalRepository
from opencde.store.jobs.validations import ValidationRepository
from opencde.store.protocols import (
    ChangeSetDraftStore,
    ClashStore,
    ConversionStore,
    MergeStore,
    ProjectStore,
    ProposalStore,
    UserStore,
    ValidationStore,
)
from opencde.timeutil import later_iso, now_iso

pytestmark = pytest.mark.integration

PASSWORD = "a-long-and-strong-passphrase"
PAGE = Compiled(where=None, params={}, order_by=DEFAULT_ORDER, skip=0, limit=50)


class World(Protocol):
    """What a job belongs to in the other areas."""

    async def version(self, project_id: str, document_id: str, version_index: int) -> str: ...
    async def topic(self, project_id: str, guid: str, title: str, description: str | None = None) -> None: ...


class GraphWorld:
    def __init__(self, graph: Graph) -> None:
        self.graph = graph

    async def version(self, project_id: str, document_id: str, version_index: int) -> str:
        version_id = new_id()
        await self.graph.run(
            """
            MATCH (p:Project {project_id: $project_id})
            MERGE (p)-[:HAS_DOCUMENT]->(d:Document {document_id: $document_id})
            CREATE (d)-[:HAS_VERSION]->(:DocumentVersion {
                id: $id, version_index: $index, file_name: 'model.ifc', storage_key: 'documents/model'
            })
            """,
            project_id=project_id,
            document_id=document_id,
            id=version_id,
            index=version_index,
        )
        return version_id

    async def topic(self, project_id: str, guid: str, title: str, description: str | None = None) -> None:
        await self.graph.run(
            """
            MATCH (p:Project {project_id: $project_id})
            CREATE (p)-[:HAS_TOPIC]->(:Topic {guid: $guid, title: $title, description: $description})
            """,
            project_id=project_id,
            guid=guid,
            title=title,
            description=description,
        )


class PostgresWorld:
    """Rows of the documents' and the BCF tables (0003 and 0004), with what their columns require."""

    def __init__(self, postgres: Postgres) -> None:
        self.postgres = postgres

    async def version(self, project_id: str, document_id: str, version_index: int) -> str:
        version_id = new_id()
        await self.postgres.execute(
            """
            INSERT INTO documents (document_id, project_id, title, created_at, latest_index)
            VALUES ($1, $2, 'Model', $3, $4)
            ON CONFLICT (document_id) DO UPDATE SET latest_index = EXCLUDED.latest_index
            """,
            document_id,
            project_id,
            now_iso(),
            version_index,
        )
        await self.postgres.execute(
            """
            INSERT INTO document_versions (
                id, document_id, version_index, version_number, creation_date, title, file_name, size_in_bytes,
                sha256, storage_key, author
            )
            VALUES ($1, $2, $3, $4, $5, 'Model', 'model.ifc', 3, $6, 'documents/model', 'editor')
            """,
            version_id,
            document_id,
            version_index,
            str(version_index),
            now_iso(),
            "0" * 64,
        )
        return version_id

    async def topic(self, project_id: str, guid: str, title: str, description: str | None = None) -> None:
        await self.postgres.execute(
            """
            INSERT INTO topics (guid, project_id, title, description, server_assigned_id, creation_date, creation_author)
            VALUES ($1, $2, $3, $4, $5, $6, 'editor')
            """,
            guid,
            project_id,
            title,
            description,
            "ISSUE-" + guid[:8],
            now_iso(),
        )


@dataclass(frozen=True)
class Jobs:
    users: UserStore
    projects: ProjectStore
    conversions: ConversionStore
    validations: ValidationStore
    proposals: ProposalStore
    drafts: ChangeSetDraftStore
    clashes: ClashStore
    merges: MergeStore
    world: World


async def _tick() -> None:
    """Past the millisecond of the server's timestamps, so that newest first has one answer."""
    await asyncio.sleep(0.003)


async def _project(jobs: Jobs, name: str = "Building permit") -> tuple[User, User, Project]:
    """A project with a member, and a user who is none of its members."""
    member = await jobs.users.create(f"member-{name[:3].lower()}", PASSWORD)
    outsider = await jobs.users.create(f"outsider-{name[:3].lower()}", PASSWORD)
    project = await jobs.projects.create(name)
    await jobs.projects.set_member(project.project_id, member.id, Role.EDITOR)
    return member, outsider, project


# -- the same on both ----------------------------------------------------------------------------------------------


async def conversions_from_queued_to_pruned(jobs: Jobs) -> None:
    conversions = jobs.conversions
    member, outsider, project = await _project(jobs)
    pid, document = project.project_id, new_id()
    first, second, failed, running, bcf = (new_id() for _ in range(5))
    for model_id, index in ((first, 1), (second, 2), (failed, 3), (running, 4)):
        await conversions.create(
            project_id=pid,
            model_id=model_id,
            file_name="model.ifc",
            storage_key="documents/model",
            document_id=document,
            version_index=index,
        )
        await _tick()
    await conversions.create(
        project_id=pid, model_id=bcf, file_name="b.ifc", storage_key="bcf-documents/b", bcf_document_guid=new_id()
    )
    await conversions.create(project_id=new_id(), model_id=new_id(), file_name="x.ifc", storage_key="documents/x")

    assert await conversions.claim(first) and not await conversions.claim(first), "one process runs it"
    await conversions.set_state(first, "done", schema="IFC4", entities=3, lossless=True, spatial_pending=True)
    await conversions.set_fields(first, geometry_key="geometry/first.jsonl", spatial_error=None)
    await conversions.remove_field(first, "spatial_pending")
    found = await conversions.get(first)
    assert found is not None
    assert (found["id"], found["model_id"], found["state"], found["document_id"], found["version_index"]) == (
        first,
        first,
        "done",
        document,
        1,
    )
    assert found["schema"] == "IFC4" and found["entities"] == 3 and found["lossless"] is True
    assert found["geometry_key"] == "geometry/first.jsonl"
    assert found["running_at"] and found["done_at"] and found["file_name"] == "model.ifc"
    for gone in ("spatial_pending", "spatial_error", "bcf_document_guid"):
        assert gone not in found, f"{gone}: what is null or removed is no property"

    assert await conversions.claim(second)
    await conversions.set_state(second, "done", schema="IFC4", spatial_pending=True)
    assert await conversions.claim(failed)
    await conversions.set_state(failed, "failed", error="RuntimeError: the import broke off")
    assert await conversions.claim(running)

    assert [c["id"] for c in await conversions.of_project(pid)] == [bcf, running, failed, second, first]
    assert sorted(await conversions.done_model_ids(pid)) == sorted([first, second])
    newest = await conversions.latest_of_version(document_id=document, version_index=3)
    assert newest is None, "a failed one is no finished model"
    newest = await conversions.latest_of_version(document_id=document, version_index=3, done_only=False)
    assert newest is not None and newest["id"] == failed and newest["error"].startswith("RuntimeError")
    assert newest["failed_at"]

    mine = await conversions.for_member(user_id=member.id, document_id=document, version_index=1)
    assert mine is not None and mine["id"] == first
    assert await conversions.for_member(user_id=outsider.id, document_id=document, version_index=1) is None
    assert (
        await conversions.for_member(user_id=member.id, document_id=document, version_index=1, project_id=new_id())
        is None
    )
    assert (
        await conversions.for_member(user_id=member.id, document_id=document, version_index=4, done_only=True) is None
    )

    left = {c["id"]: c for c in await conversions.interrupted(given_up=later_iso(60))}
    assert set(left) == {running, bcf} and left[running]["storage_key"] == "documents/model"
    assert {c["id"] for c in await conversions.interrupted(given_up=later_iso(-60))} == {bcf}, "running for now"
    await conversions.spatial_interrupted(given_up=later_iso(60))
    given_up = await conversions.get(second)
    assert given_up is not None and "spatial_pending" not in given_up
    assert given_up["spatial_error"] == "the geometry pass was interrupted"

    assert sorted(await conversions.model_ids_of_document(document)) == sorted([first, second, failed, running])
    assert [c["id"] for c in await conversions.all(project_id=pid)] == [first, second, failed, running, bcf]
    assert sorted(await conversions.superseded_or_failed(project_id=pid)) == sorted([first, failed])
    assert (await conversions.counts_per_project())[pid] == 5

    assert sorted(await jobs.projects.model_ids(pid)) == sorted([first, second, failed, running, bcf])
    assert {"documents/model", "bcf-documents/b"} <= set(await jobs.projects.storage_keys(pid))
    await conversions.delete(first)
    assert await conversions.get(first) is None
    assert await jobs.projects.delete(pid)
    assert await conversions.all(project_id=pid) == [], "the project's conversions go with it"


async def checks_of_versions_and_prechecks(jobs: Jobs) -> None:
    checks = jobs.validations
    member, outsider, project = await _project(jobs)
    pid = project.project_id
    version_id = await jobs.world.version(pid, new_id(), 1)
    check = new_id()
    assert await checks.queue(validation_id=check, version_id=version_id, storage_key="documents/m", file_name="m.ifc")
    assert not await checks.queue(
        validation_id=new_id(), version_id=new_id(), storage_key="documents/m", file_name="m.ifc"
    ), "no such version"
    assert await checks.claim(check) and not await checks.claim(check)
    assert [r["id"] for r in await checks.interrupted(given_up=later_iso(60))] == [check]
    assert await checks.interrupted(given_up=later_iso(-60)) == []
    report = pack_report([{"kind": "schema", "severity": "error", "message": "x"}])
    await checks.set_state(
        check, "done", checked_at=now_iso(), issue_count=1, error_count=1, truncated=False, report=report, rooms=None
    )
    assert await checks.project_of(check) == pid
    await checks.record(
        version_id=version_id, storage_key="documents/m", file_name="m.ifc", checked={"state": "failed", "error": "x"}
    )

    queued, kept = new_id(), new_id()
    assert await checks.open_precheck(
        precheck_id=queued, project_id=pid, storage_key="prechecks/a.ifc", file_name="a.ifc", author="member"
    )
    assert not await checks.open_precheck(
        precheck_id=new_id(), project_id=new_id(), storage_key="prechecks/b.ifc", file_name="b.ifc", author="member"
    ), "no such project"
    assert await checks.project_of(queued) == pid
    await checks.keep_precheck(
        precheck_id=kept,
        project_id=pid,
        storage_key="prechecks/c.ifc",
        file_name="c.ifc",
        author="member",
        checked={"state": "done", "issue_count": 0, "report": pack_report([])},
    )
    node = await checks.precheck(user_id=member.id, project_id=pid, precheck_id=kept)
    assert node is not None and (node["id"], node["state"], node["author"], node["issue_count"]) == (
        kept,
        "done",
        "member",
        0,
    )
    assert node["expires_at"] > node["created_at"] and node["done_at"] and node["storage_key"] == "prechecks/c.ifc"
    assert await checks.precheck(user_id=outsider.id, project_id=pid, precheck_id=kept) is None
    assert await checks.precheck(user_id=member.id, project_id=pid, precheck_id=check) is None, "a version's check"
    assert {r["id"] for r in await checks.interrupted(given_up=later_iso(60))} == {queued}
    assert {"prechecks/a.ifc", "prechecks/c.ifc"} <= set(await jobs.projects.storage_keys(pid))


async def trials_of_change_sets(jobs: Jobs) -> None:
    proposals = jobs.proposals
    member, outsider, project = await _project(jobs)
    pid, document, topic, other_topic = project.project_id, new_id(), new_id(), new_id()
    await jobs.world.version(pid, document, 1)
    await jobs.world.topic(pid, topic, "Move the wall", "A longer description")
    await jobs.world.topic(pid, other_topic, "Open a door")
    trial = {"project_id": pid, "author": "member", "base_document_id": document, "base_version_index": 1}

    first = new_id()
    assert await proposals.create(proposal_id=first, topic_guid=topic, snippet_key="snippets/a.json", **trial) == (
        True,
        [],
    )
    assert await proposals.claim(first) == {"project_id": pid, "snippet_key": "snippets/a.json", "author": "member"}
    assert await proposals.claim(first) is None
    checked_at = now_iso()
    await proposals.set_state(
        first,
        "clean",
        checked_at=checked_at,
        storage_key="proposals/a.ifc",
        base_document_id=document,
        base_version_index=1,
        change_count=3,
        issue_count=0,
        report=pack_report([]),
        teams_error=None,
    )
    node = await proposals.of_topic(user_id=member.id, project_id=pid, topic_guid=topic)
    assert node is not None and (node["id"], node["state"], node["storage_key"], node["change_count"]) == (
        first,
        "clean",
        "proposals/a.ifc",
        3,
    )
    assert node["clean_at"] and node["running_at"] and "teams_error" not in node
    assert await proposals.of_topic(user_id=outsider.id, project_id=pid, topic_guid=topic) is None
    row = {
        "project_id": pid,
        "topic_guid": topic,
        "title": "Move the wall",
        "description": "A longer description",
        "state": "clean",
        "base_version_index": 1,
        "change_count": 3,
        "author": "member",
        "checked_at": checked_at,
        "version_index": None,
    }
    assert await proposals.of_document(user_id=member.id, document_id=document, compiled=PAGE) == [row]
    assert await proposals.count(user_id=member.id, document_id=document, compiled=PAGE) == 1
    assert await proposals.of_document(user_id=outsider.id, document_id=document, compiled=PAGE) == []
    assert await proposals.count(user_id=outsider.id, document_id=document, compiled=PAGE) == 0

    await proposals.set_state(first, "approved", approved_by="manager", version_index=2)
    (approved,) = await proposals.of_document(user_id=member.id, document_id=document, compiled=PAGE)
    assert approved["state"] == "approved" and approved["version_index"] == 2
    assert await proposals.get(first) == {"project_id": pid, "snippet_key": "snippets/a.json", "author": "member"}
    assert await proposals.snippet_key(project_id=pid, topic_guid=topic) == "snippets/a.json"
    assert await proposals.snippet_key(project_id=pid, topic_guid=other_topic) is None

    await _tick()
    second, door = new_id(), new_id()
    assert await proposals.create(proposal_id=second, topic_guid=topic, snippet_key="snippets/b.json", **trial) == (
        True,
        ["proposals/a.ifc"],
    ), "a new trial replaces the topic's earlier one, whose file the caller deletes"
    assert await proposals.get(first) is None
    await _tick()
    assert await proposals.create(proposal_id=door, topic_guid=other_topic, snippet_key="snippets/c.json", **trial) == (
        True,
        [],
    )
    listed = await proposals.of_document(user_id=member.id, document_id=document, compiled=PAGE)
    assert [r["topic_guid"] for r in listed] == [other_topic, topic], "newest first"
    page = Compiled(where=None, params={}, order_by=DEFAULT_ORDER, skip=1, limit=1)
    assert [
        r["topic_guid"] for r in await proposals.of_document(user_id=member.id, document_id=document, compiled=page)
    ] == [topic]
    assert {r["id"] for r in await proposals.interrupted(given_up=later_iso(60))} == {second, door}

    _, _, elsewhere = await _project(jobs, "Archive")
    foreign = new_id()
    await jobs.world.topic(elsewhere.project_id, foreign, "Not this project's")
    unknown = {**trial, "snippet_key": "snippets/x.json"}
    assert await proposals.create(proposal_id=new_id(), topic_guid=new_id(), **unknown) == (False, [])
    assert await proposals.create(proposal_id=new_id(), topic_guid=foreign, **unknown) == (False, []), (
        "a topic of another project"
    )


async def open_change_sets(jobs: Jobs) -> None:
    drafts = jobs.drafts
    member, outsider, project = await _project(jobs)
    pid, document = project.project_id, new_id()
    await jobs.world.version(pid, document, 1)
    draft = await drafts.open(user_id=member.id, project_id=pid, document_id=document, version_index=1)
    assert draft is not None and draft.steps == [] and draft.refs == 0 and draft.topic_guid is None
    assert draft.base == {"document_id": document, "version_index": 1} and draft.expires_at > draft.created_at
    assert await drafts.open(user_id=outsider.id, project_id=pid, document_id=document, version_index=1) is None
    assert await drafts.open(user_id=member.id, project_id=pid, document_id=new_id(), version_index=1) is None, (
        "not a document of the project"
    )
    handle = draft.changeset_id
    assert await drafts.get(user_id=member.id, changeset_id=handle) == draft
    await jobs.projects.set_member(pid, outsider.id, Role.EDITOR)
    assert await drafts.get(user_id=outsider.id, changeset_id=handle) is None, "a draft is its user's alone"

    def adding(op: str) -> Callable[[ChangeSetDraft], ChangeSetDraft]:
        return lambda found: replace(found, steps=[*found.steps, {"op": op}], refs=found.refs + 1, topic_guid="t")

    await asyncio.gather(
        drafts.update(user_id=member.id, changeset_id=handle, change=adding("wall")),
        drafts.update(user_id=member.id, changeset_id=handle, change=adding("slab")),
    )
    found = await drafts.get(user_id=member.id, changeset_id=handle)
    assert found is not None and sorted(step["op"] for step in found.steps) == ["slab", "wall"], "one after the other"
    assert found.refs == 2 and found.topic_guid == "t" and found.expires_at >= draft.expires_at
    with pytest.raises(DraftRefused, match="at most 200 steps"):
        await drafts.update(
            user_id=member.id, changeset_id=handle, change=lambda d: replace(d, steps=[{"op": "x"}] * 201)
        )
    after = await drafts.get(user_id=member.id, changeset_id=handle)
    assert after is not None and after.refs == 2, "what was refused changed nothing"
    assert await drafts.update(user_id=outsider.id, changeset_id=handle, change=adding("door")) is None

    for _ in range(MAX_OPEN - 1):
        assert await drafts.open(user_id=member.id, project_id=pid, document_id=document, version_index=1)
    assert await drafts.open(user_id=member.id, project_id=pid, document_id=document, version_index=1) is None
    assert await drafts.open(user_id=outsider.id, project_id=pid, document_id=document, version_index=1), (
        "the limit is each user's"
    )
    assert await jobs.projects.delete(pid)
    assert await drafts.get(user_id=member.id, changeset_id=handle) is None


async def clash_checks(jobs: Jobs) -> None:
    clashes = jobs.clashes
    member, outsider, project = await _project(jobs)
    pid = project.project_id
    request = json.dumps({"a": {"document_id": "a", "version_index": 1}, "b": {"document_id": "b", "version_index": 1}})
    done, failed = new_id(), new_id()
    await clashes.create(clash_id=done, project_id=pid, author="member", request=request)
    await _tick()
    await clashes.create(clash_id=failed, project_id=pid, author="member", request=request)
    await clashes.create(clash_id=new_id(), project_id=new_id(), author="member", request=request)
    assert await clashes.open_count(user_id=member.id, author="member") == 2
    assert await clashes.open_count(user_id=outsider.id, author="member") == 0, "reached from the user alone"

    assert await clashes.claim(done) == {"project_id": pid, "request": request}
    assert await clashes.claim(done) is None
    await clashes.finish(done, count=2, set_a=3, set_b=4, missing=0, seconds=0.5, truncated=False, report="packed")
    assert await clashes.claim(failed) is not None
    await clashes.fail(failed, error="ValueError: no such version")
    assert await clashes.open_count(user_id=member.id, author="member") == 0

    listed = await clashes.of_project(user_id=member.id, project_id=pid)
    assert [c["id"] for c in listed] == [failed, done], "newest first"
    assert listed[0]["state"] == "failed" and listed[0]["error"] == "ValueError: no such version"
    assert listed[0]["failed_at"] and listed[0]["author"] == "member"
    finished = listed[1]
    assert (finished["state"], finished["count"], finished["set_a"], finished["seconds"], finished["truncated"]) == (
        "done",
        2,
        3,
        0.5,
        False,
    )
    assert finished["done_at"] and finished["running_at"] and finished["report"] == "packed"
    one = await clashes.get(user_id=member.id, project_id=pid, clash_id=done)
    assert one is not None and one["request"] == request
    assert await clashes.get(user_id=outsider.id, project_id=pid, clash_id=done) is None
    assert await clashes.of_project(user_id=outsider.id, project_id=pid) == []


async def merges_and_preparations(jobs: Jobs) -> None:
    merges = jobs.merges
    member, outsider, project = await _project(jobs)
    pid = project.project_id
    request = json.dumps({"base": {"model_id": "a"}, "other": {"model_id": "b"}, "building": "x"})
    merge, prepare, made, prepared = new_id(), new_id(), new_id(), new_id()
    await merges.create(merge_id=merge, project_id=pid, kind="merge", author="member", request=request)
    await merges.create(merge_id=prepare, project_id=pid, kind="prepare", author="member", request=request)
    assert {j["id"] for j in await merges.interrupted(given_up=later_iso(60))} == {merge, prepare}

    claimed = await merges.claim(merge, model_id=made)
    assert claimed == {"project_id": pid, "request": request, "author": "member", "kind": "merge"}
    assert await merges.claim(merge, model_id=new_id()) is None
    running = {j["id"]: j for j in await merges.interrupted(given_up=later_iso(60))}
    assert running[merge]["state"] == "running" and running[merge]["model_id"] == made
    await merges.set_state(merge, "done", version_index=2, report="packed")
    assert await merges.claim(prepare, model_id=prepared) is not None
    await merges.set_state(prepare, "done", expires_at=later_iso(3600), report="packed")

    assert await merges.prepared(user_id=member.id, project_id=pid, prepare_id=prepare) == {
        "model_id": prepared,
        "request": request,
    }
    assert await merges.prepared(user_id=outsider.id, project_id=pid, prepare_id=prepare) is None
    assert await merges.prepared(user_id=member.id, project_id=pid, prepare_id=merge) is None, (
        "a merge is no preparation"
    )
    assert await merges.expired_preparations() == []
    node = await merges.get(user_id=member.id, project_id=pid, merge_id=merge)
    assert node is not None and (node["kind"], node["state"], node["version_index"], node["model_id"]) == (
        "merge",
        "done",
        2,
        made,
    )
    assert node["finished_at"] and node["report"] == "packed" and node["author"] == "member"
    assert await merges.get(user_id=outsider.id, project_id=pid, merge_id=merge) is None

    await merges.set_state(prepare, "done", expires_at=later_iso(-60))
    assert await merges.prepared(user_id=member.id, project_id=pid, prepare_id=prepare) is None, "its day is over"
    assert await merges.expired_preparations() == [{"id": prepare, "model_id": prepared}]
    await merges.set_state(prepare, "expired")
    assert await merges.expired_preparations() == []
    expired = await merges.get(user_id=member.id, project_id=pid, merge_id=prepare)
    assert expired is not None and expired["state"] == "expired" and expired["expires_at"], "the record stays"


CASES = (
    conversions_from_queued_to_pruned,
    checks_of_versions_and_prechecks,
    trials_of_change_sets,
    open_change_sets,
    clash_checks,
    merges_and_preparations,
)


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.__name__)
async def test_on_the_graph(case: Callable[[Jobs], Awaitable[None]], graph: Graph) -> None:
    await case(
        Jobs(
            UserRepository(graph),
            ProjectRepository(graph),
            ConversionRepository(graph),
            ValidationRepository(graph),
            ProposalRepository(graph),
            ChangeSetDraftRepository(graph),
            ClashRepository(graph),
            MergeRepository(graph),
            GraphWorld(graph),
        )
    )


def _on_postgresql(pg: Postgres) -> Jobs:
    return Jobs(
        PostgresUserRepository(pg),
        PostgresProjectRepository(pg),
        PostgresConversionRepository(pg),
        PostgresValidationRepository(pg),
        PostgresProposalRepository(pg),
        PostgresChangeSetDraftRepository(pg),
        PostgresClashRepository(pg),
        PostgresMergeRepository(pg),
        PostgresWorld(pg),
    )


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.__name__)
async def test_on_postgresql(case: Callable[[Jobs], Awaitable[None]], pg: Postgres) -> None:
    await case(_on_postgresql(pg))


# -- PostgreSQL's own ----------------------------------------------------------------------------------------------


async def test_on_postgresql_the_jobs_migration_is_applied_once(pg: Postgres) -> None:
    assert await migrate(pg) == 0
    row = await pg.one("SELECT max(version) AS version FROM schema_migrations")
    assert row == {"version": len(migrations())}


async def test_on_postgresql_the_other_areas_read_the_jobs_through_their_views(pg: Postgres) -> None:
    jobs = _on_postgresql(pg)
    _, _, project = await _project(jobs)
    pid, document, topic = project.project_id, new_id(), new_id()
    version_id = await jobs.world.version(pid, document, 1)
    await jobs.world.topic(pid, topic, "Move the wall")
    check, model, trial = new_id(), new_id(), new_id()
    await jobs.validations.queue(validation_id=check, version_id=version_id, storage_key="documents/m", file_name="m")
    await jobs.validations.set_state(check, "done", issue_count=2, error_count=1, truncated=True, checks="[]")
    await jobs.conversions.create(
        project_id=pid,
        model_id=model,
        file_name="m.ifc",
        storage_key="documents/m",
        document_id=document,
        version_index=1,
    )
    await jobs.conversions.set_state(model, "done", ifc_project_guid="0KhR8hr7H8eewFRKm6V1bJ")
    await jobs.conversions.set_fields(model, graph_checked_at=now_iso(), graph_issue_count=4, graph_error_count=0)
    await jobs.proposals.create(
        proposal_id=trial,
        project_id=pid,
        topic_guid=topic,
        snippet_key="snippets/s.json",
        author="member",
        base_document_id=document,
        base_version_index=1,
    )
    await jobs.proposals.set_state(trial, "clean", storage_key="proposals/t.ifc")

    validation = await pg.one("SELECT * FROM version_validations WHERE version_id = $1", version_id)
    assert validation is not None
    assert (validation["state"], validation["issue_count"], validation["error_count"], validation["truncated"]) == (
        "done",
        2,
        1,
        True,
    )
    assert validation["checks"] == "[]" and validation["report"] is None and validation["created_at"]
    graph_check = await pg.one("SELECT * FROM version_graph_checks WHERE document_id = $1", document)
    assert graph_check is not None and graph_check["graph_issue_count"] == 4 and graph_check["version_index"] == 1
    assert await pg.one("SELECT ifc_project_guid FROM conversion_ifc_projects WHERE document_id = $1", document) == {
        "ifc_project_guid": "0KhR8hr7H8eewFRKm6V1bJ"
    }
    assert await pg.run("SELECT * FROM proposal_files") == [{"topic_guid": topic, "storage_key": "proposals/t.ifc"}]
    keys = await pg.run("SELECT storage_key FROM project_files WHERE project_id = $1", pid)
    assert sorted(row["storage_key"] for row in keys) == sorted(
        ["documents/model", "documents/m", "documents/m", "proposals/t.ifc"]
    ), "the version's file, the conversion's and the check's (the same), and the trial's through bcf_files"
    assert await jobs.projects.model_ids(pid) == [model]


async def test_on_postgresql_what_a_job_belongs_to_takes_it_along(pg: Postgres) -> None:
    jobs = _on_postgresql(pg)
    member, _, project = await _project(jobs)
    pid, document, topic = project.project_id, new_id(), new_id()
    version_id = await jobs.world.version(pid, document, 1)
    await jobs.world.topic(pid, topic, "Move the wall")
    trial, check = new_id(), new_id()
    await jobs.validations.queue(validation_id=check, version_id=version_id, storage_key="documents/m", file_name="m")
    await jobs.proposals.create(
        proposal_id=trial,
        project_id=pid,
        topic_guid=topic,
        snippet_key="snippets/s.json",
        author="member",
        base_document_id=document,
        base_version_index=1,
    )
    draft = await jobs.drafts.open(user_id=member.id, project_id=pid, document_id=document, version_index=1)
    assert draft is not None
    await pg.execute("DELETE FROM topics WHERE guid = $1", topic)
    assert await jobs.proposals.get(trial) is None, "a topic's trial goes with the topic"
    await pg.execute("DELETE FROM document_versions WHERE id = $1", version_id)
    assert await jobs.validations.project_of(check) is None, "a version's check goes with the version"
    await jobs.users.delete(member.id)
    assert await pg.one("SELECT count(*) AS n FROM change_set_drafts") == {"n": 0}, "a user's drafts go with the user"


async def test_on_postgresql_the_cleaner_deletes_expired_prechecks_with_their_files_and_drafts(
    pg: Postgres, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    jobs = _on_postgresql(pg)
    member, _, project = await _project(jobs)
    pid, document = project.project_id, new_id()
    await jobs.world.version(pid, document, 1)
    storage = LocalStorage(tmp_path)
    for key in ("prechecks/old.ifc", "prechecks/new.ifc"):
        storage.write_bytes(key, b"ISO-10303-21;")
    kept = new_id()
    await jobs.validations.open_precheck(
        precheck_id=kept, project_id=pid, storage_key="prechecks/new.ifc", file_name="n.ifc", author="member"
    )
    kept_draft = await jobs.drafts.open(user_id=member.id, project_id=pid, document_id=document, version_index=1)
    monkeypatch.setattr(jobs_postgres, "PRECHECK_SECONDS", -60)
    monkeypatch.setattr(jobs_postgres, "LIFETIME_SECONDS", -60)
    await jobs.validations.open_precheck(
        precheck_id=new_id(), project_id=pid, storage_key="prechecks/old.ifc", file_name="o.ifc", author="member"
    )
    await jobs.drafts.open(user_id=member.id, project_id=pid, document_id=document, version_index=1)

    assert await delete_expired(pg, storage=storage) == 2
    assert not storage.exists("prechecks/old.ifc") and storage.exists("prechecks/new.ifc")
    assert await jobs.validations.precheck(user_id=member.id, project_id=pid, precheck_id=kept) is not None
    assert kept_draft is not None
    assert await jobs.drafts.get(user_id=member.id, changeset_id=kept_draft.changeset_id) is not None
    assert await pg.one("SELECT count(*) AS n FROM change_set_drafts") == {"n": 1}
