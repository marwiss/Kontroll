# This file was generated with the assistance of an AI coding tool.
"""The BCF area in PostgreSQL (ADR 0029) against a real database: the same cases on the graph's repositories and on
PostgreSQL's, the OData filters giving the same rows in both, and PostgreSQL's own rules.

PostgreSQL runs in a container of its own (``postgres_target`` and ``pg`` in the conftest), one per test session;
every test starts from empty tables with the migrations applied. Each case runs once on the graph (on every graph the
session has) and once on PostgreSQL, which needs no graph: ``-k on_postgresql`` starts PostgreSQL alone. The cases
assert what the graph answers, so that both answering them is the proof that they answer alike."""

from __future__ import annotations

import asyncio
import base64
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

import pytest
from asyncpg.exceptions import ForeignKeyViolationError
from fastapi import HTTPException

from opencde.accounts.roles import Role
from opencde.bcf import events
from opencde.bcf.schemas import (
    BimSnippet,
    CommentPOST,
    CommentPUT,
    DocumentReferencePOST,
    DocumentReferencePUT,
    FileRef,
    TopicPOST,
    TopicPUT,
    ViewpointPOST,
)
from opencde.graph.graph import Graph
from opencde.odata import Compiled, compile_odata
from opencde.postgres.database import Postgres
from opencde.storage import LocalStorage
from opencde.store.accounts.postgres import PostgresProjectRepository, PostgresUserRepository
from opencde.store.accounts.projects import ProjectRepository
from opencde.store.accounts.users import UserRepository
from opencde.store.bcf.comments import COMMENT_DEFAULT_ORDER, COMMENT_FIELDS, COMMENT_ORDERABLE, CommentRepository
from opencde.store.bcf.documents import BcfDocumentRepository
from opencde.store.bcf.events import BcfEventRepository
from opencde.store.bcf.postgres import (
    PostgresBcfDocumentRepository,
    PostgresBcfEventRepository,
    PostgresCommentRepository,
    PostgresTopicLinkRepository,
    PostgresTopicRepository,
    PostgresViewpointRepository,
)
from opencde.store.bcf.topic_links import TopicLinkRepository
from opencde.store.bcf.topics import TOPIC_DEFAULT_ORDER, TOPIC_FIELDS, TOPIC_ORDERABLE, TopicRepository
from opencde.store.bcf.viewpoints import ViewpointRepository
from opencde.store.documents.postgres import PostgresDocumentRepository
from opencde.store.protocols import (
    BcfDocumentStore,
    BcfEventStore,
    CommentStore,
    ProjectStore,
    TopicLinkStore,
    TopicStore,
    UserStore,
    ViewpointStore,
)
from tests.integration.test_postgres_accounts import PASSWORD

pytestmark = pytest.mark.integration

PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c63f8ffff3f0005fe02fea7358184"
    "0000000049454e44ae426082"
)
GUIDS = [f"00000000-0000-4000-8000-{n:012d}" for n in range(1, 21)]
MAX_IMAGE_BYTES = 1_000_000
ORTHOGONAL = {
    "orthogonal_camera": {
        "camera_view_point": {"x": 1.0, "y": 2.0, "z": 3.0},
        "camera_direction": {"x": 0.0, "y": -1.0, "z": 0.0},
        "camera_up_vector": {"x": 0.0, "y": 0.0, "z": 1.0},
        "view_to_world_scale": 2.0,
        "aspect_ratio": 1.0,
    }
}


@dataclass(frozen=True)
class Bcf:
    users: UserStore
    projects: ProjectStore
    topics: TopicStore
    comments: CommentStore
    viewpoints: ViewpointStore
    links: TopicLinkStore
    documents: BcfDocumentStore
    events: BcfEventStore
    storage: LocalStorage


@dataclass(frozen=True)
class World:
    project_id: str
    other_project_id: str
    editor: str  # user ids
    viewer: str
    outsider: str


async def _world(bcf: Bcf) -> World:
    editor, viewer, outsider = [await bcf.users.create(name, PASSWORD) for name in ("editor", "viewer", "outsider")]
    project, other = await bcf.projects.create("Building permit"), await bcf.projects.create("Archive")
    await bcf.projects.set_member(project.project_id, editor.id, Role.EDITOR)
    await bcf.projects.set_member(project.project_id, viewer.id, Role.VIEWER)
    await bcf.projects.set_member(other.project_id, editor.id, Role.EDITOR)
    return World(project.project_id, other.project_id, editor.id, viewer.id, outsider.id)


def _topics(filter_: str | None = None, orderby: str | None = None, top: int | None = None, skip: int | None = None):
    return compile_odata(
        filter_=filter_,
        orderby=orderby,
        top=top,
        skip=skip,
        fields=TOPIC_FIELDS,
        orderable=TOPIC_ORDERABLE,
        default_order=TOPIC_DEFAULT_ORDER,
    )


def _events(filter_: str | None = None, orderby: str | None = None) -> Compiled:
    return compile_odata(
        filter_=filter_,
        orderby=orderby,
        top=None,
        skip=None,
        fields=events.EVENT_FIELDS,
        orderable=events.EVENT_ORDERABLE,
        default_order=events.EVENT_DEFAULT_ORDER,
    )


def _comments(filter_: str | None = None, orderby: str | None = None) -> Compiled:
    return compile_odata(
        filter_=filter_,
        orderby=orderby,
        top=None,
        skip=None,
        fields=COMMENT_FIELDS,
        orderable=COMMENT_ORDERABLE,
        default_order=COMMENT_DEFAULT_ORDER,
    )


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


async def _tick() -> None:
    """A millisecond apart, so that times order what was made one after another."""
    await asyncio.sleep(0.003)


# -- the same on both ----------------------------------------------------------------------------------------------


async def topics_and_their_events(bcf: Bcf) -> None:
    w = await _world(bcf)
    first = await bcf.topics.create(
        project_id=w.project_id,
        author="editor",
        body=TopicPOST(
            guid=GUIDS[0].upper(), title="Wall", topic_status="Open", labels=["Reuse", "Architecture"], description="d"
        ),
    )
    assert first.guid == GUIDS[0] and first.server_assigned_id == "ISSUE-0001" and first.creation_author == "editor"
    assert first.labels == ["Reuse", "Architecture"] and first.modified_date == first.creation_date
    with pytest.raises(HTTPException) as taken:
        await bcf.topics.create(project_id=w.project_id, author="editor", body=TopicPOST(guid=GUIDS[0], title="x"))
    assert taken.value.status_code == 409
    with pytest.raises(HTTPException) as nowhere:
        await bcf.topics.create(project_id="no-such-project", author="editor", body=TopicPOST(title="x"))
    assert nowhere.value.status_code == 404
    await _tick()
    second = await bcf.topics.create(
        project_id=w.project_id,
        author="editor",
        body=TopicPOST(
            guid=GUIDS[1],
            title="Slab",
            stage="Design",
            labels=[],
            bim_snippet=BimSnippet(
                snippet_type=".ifc", is_external=True, reference="https://x.org/a.ifc", reference_schema="s"
            ),
        ),
    )
    assert second.server_assigned_id == "ISSUE-0002" and second.labels == [] and second.bim_snippet is not None
    other = await bcf.topics.create(project_id=w.other_project_id, author="editor", body=TopicPOST(title="Elsewhere"))
    assert other.server_assigned_id == "ISSUE-0001", "each project counts its own"

    seen = await bcf.topics.get(user_id=w.viewer, project_id=w.project_id, guid=first.guid)
    assert seen == first
    assert await bcf.topics.get(user_id=w.outsider, project_id=w.project_id, guid=first.guid) is None
    assert await bcf.topics.get(user_id=w.viewer, project_id=w.other_project_id, guid=other.guid) is None
    assert await bcf.topics.exists(first.guid) and not await bcf.topics.exists(GUIDS[19])
    assert [
        t.title for t in await bcf.topics.search(user_id=w.viewer, project_id=w.project_id, compiled=_topics())
    ] == [
        "Wall",
        "Slab",
    ]
    assert await bcf.topics.search(user_id=w.outsider, project_id=w.project_id, compiled=_topics()) == []
    assert await bcf.topics.count(user_id=w.viewer, project_id=w.project_id, compiled=_topics()) == 2

    await _tick()
    changed = await bcf.topics.update(
        project_id=w.project_id,
        guid=first.guid,
        author="viewer",
        body=TopicPUT(title="Wall 2", topic_status="Closed", labels=["Architecture", "Structural"], priority="High"),
    )
    assert changed is not None and changed.modified_author == "viewer" and changed.description is None
    assert changed.server_assigned_id == "ISSUE-0001" and changed.creation_date == first.creation_date
    assert (
        await bcf.topics.update(project_id=w.project_id, guid=GUIDS[19], author="x", body=TopicPUT(title="x")) is None
    )
    await _tick()
    await bcf.topics.update(
        project_id=w.project_id,
        guid=second.guid,
        author="editor",
        body=TopicPUT(title="Slab", stage="Completion", labels=[]),
    )

    found = await bcf.events.query(
        user_id=w.viewer, project_id=w.project_id, kind="topic", compiled=_events(), topic_guid=first.guid
    )
    assert [[(a["type"], a["value"]) for a in e["actions"]] for e in found] == [
        [
            ("topic_created", None),
            ("title_updated", "Wall"),
            ("description_updated", "d"),
            ("status_updated", "Open"),
            ("label_added", "Architecture"),
            ("label_added", "Reuse"),
        ],
        [
            ("title_updated", "Wall 2"),
            ("description_removed", None),
            ("status_updated", "Closed"),
            ("priority_updated", "High"),
            ("label_added", "Structural"),
            ("label_removed", "Reuse"),
        ],
    ]
    assert [e["author"] for e in found] == ["editor", "viewer"] and "comment_guid" not in found[0]
    assert found[0]["topic_guid"] == first.guid and found[0]["date"] == first.creation_date

    # BCF 2.1 knows no stages: the event that only moved the stage is left out, and so is the action of the first.
    whole = await bcf.events.query(user_id=w.viewer, project_id=w.project_id, kind="topic", compiled=_events())
    assert len(whole) == 4
    older = await bcf.events.query(
        user_id=w.viewer, project_id=w.project_id, kind="topic", compiled=_events(), left_out=events.NOT_IN_21
    )
    assert len(older) == 3 and [a["type"] for a in older[1]["actions"]] == ["topic_created", "title_updated"]
    assert (
        await bcf.events.count(
            user_id=w.viewer, project_id=w.project_id, kind="topic", compiled=_events(), left_out=events.NOT_IN_21
        )
        == 3
    )
    for filter_, orderby, wanted in (
        ("type eq 'label_removed'", None, [first.guid]),
        ("type eq 'stage_updated' or type eq 'label_added'", "date desc", [second.guid, first.guid, first.guid]),
        ("author eq 'viewer'", None, [first.guid]),
        (f"topic_guid eq '{second.guid}' and date ge {first.creation_date}", None, [second.guid, second.guid]),
        ("comment_guid ne null", None, []),
    ):
        listed = await bcf.events.query(
            user_id=w.viewer, project_id=w.project_id, kind="topic", compiled=_events(filter_, orderby)
        )
        assert [e["topic_guid"] for e in listed] == wanted, filter_
    assert await bcf.events.query(user_id=w.outsider, project_id=w.project_id, kind="topic", compiled=_events()) == []

    assert await bcf.topics.delete(project_id=w.project_id, guid=first.guid) == []
    assert await bcf.topics.get(user_id=w.viewer, project_id=w.project_id, guid=first.guid) is None
    with pytest.raises(HTTPException) as gone:
        await bcf.topics.delete(project_id=w.project_id, guid=first.guid)
    assert gone.value.status_code == 404
    with pytest.raises(HTTPException):
        await bcf.topics.delete(project_id=w.other_project_id, guid=second.guid)  # another project's: not found
    after = await bcf.events.query(
        user_id=w.viewer, project_id=w.project_id, kind="topic", compiled=_events(), topic_guid=first.guid
    )
    assert len(after) == 2, "a topic's events outlive it"


# The topics of the filter cases: title, status, type, priority, labels, assigned_to, index, due_date.
SET = (
    ("Wall reuse", "Open", "Issue", "High", ["Architecture", "Reuse"], "anna@example.org", 1, "2026-12-01T00:00:00Z"),
    ("Åtgärd slab", "Closed", "Request", None, ["Structural"], None, 2, None),
    ("beam", "Open", "Question", "Low", None, None, None, None),
    ("Door", "In progress", "Issue", "High", [], None, 10, None),
    ("zeta", "Resolved", None, "Medium", ["Safety", "Architecture"], None, 3, "2026-11-01T00:00:00Z"),
)
W, A, B, D, Z = (row[0] for row in SET)
#: (``$filter``, ``$orderby``, ``$top``, ``$skip``) and the titles both stores answer with.
FILTERS: tuple[tuple[str | None, str | None, int | None, int | None, list[str]], ...] = (
    (None, None, None, None, [W, A, B, D, Z]),
    ("topic_status eq 'Open'", None, None, None, [W, B]),
    ("topic_status ne 'Open'", None, None, None, [A, D, Z]),
    ("priority eq null", None, None, None, [A]),
    ("priority ne null and priority ne 'High'", None, None, None, [B, Z]),
    ("topic_type in ('Issue', 'Question')", None, None, None, [W, B, D]),
    ("labels/any(l: l eq 'Architecture')", None, None, None, [W, Z]),
    ("labels/any(l: l eq 'Architecture') or labels/any(l: l eq 'Structural')", None, None, None, [W, A, Z]),
    ("labels/any()", None, None, None, [W, A, Z]),
    ("not labels/any()", None, None, None, [D]),
    ("labels/all(l: l ne 'Safety')", None, None, None, [W, A, B, D]),
    ("labels eq 'Reuse'", None, None, None, [W]),
    ("labels ne 'Reuse'", None, None, None, [A, B, D, Z]),
    ("contains(labels, 'Safety')", None, None, None, [Z]),
    ("labels/any(l: startswith(l, 'Str'))", None, None, None, [A]),
    ("labels/any(l: priority eq 'High')", None, None, None, [W]),
    ("not labels/any(l: priority eq 'High')", None, None, None, [B, D, Z]),
    ("not labels/all(l: priority eq 'Medium')", None, None, None, [W]),
    ("labels in ('Architecture', 'Safety')", None, None, None, []),
    ("not (labels in ('Architecture', 'Safety'))", None, None, None, [W, A, D, Z]),
    ("contains(title, 'a')", None, None, None, [W, A, B, Z]),
    ("startswith(title, 'W')", None, None, None, [W]),
    ("endswith(title, 'm')", None, None, None, [B]),
    ("contains(title, '')", None, None, None, [W, A, B, D, Z]),
    ("tolower(title) eq 'door'", None, None, None, [D]),
    ("toupper(topic_status) eq 'OPEN'", None, None, None, [W, B]),
    ("contains(tolower(title), 'BEAM')", None, None, None, []),
    ("title gt 'Wall'", None, None, None, [W, A, B, Z]),
    ("title lt 'a'", None, None, None, [W, D]),
    ("tolower(title) lt 'c'", None, None, None, [B]),
    ("index ge 3", None, None, None, [D, Z]),
    ("index in (1, 10)", None, None, None, [W, D]),
    ("not (index eq 1)", None, None, None, [A, D, Z]),
    ("(topic_status eq 'Open' or priority eq 'High') and not (index eq 1)", None, None, None, [D]),
    ("assigned_to eq 'anna@example.org'", None, None, None, [W]),
    ("due_date lt 2026-11-15", None, None, None, [Z]),
    ("due_date ge 2026-11-15T00:00:00Z", None, None, None, [W]),
    ("due_date in (2026-11-01T01:00:00+01:00, 1999-01-01)", None, None, None, [Z]),
    ("creation_date gt 2000-01-01 and modified_date le 2999-01-01T00:00:00Z", None, None, None, [W, A, B, D, Z]),
    ("server_assigned_id eq 'ISSUE-0003'", None, None, None, [B]),
    (None, "index desc", None, None, [B, D, Z, A, W]),
    (None, "index", None, None, [W, A, Z, D, B]),
    (None, "server_assigned_id desc", None, None, [Z, D, B, A, W]),
    (None, "modified_date desc", None, None, [Z, D, B, A, W]),
    ("priority eq 'High'", "creation_date desc", None, None, [D, W]),
    (None, None, 2, 1, [A, B]),
    (None, "index desc", 2, 3, [A, W]),
    (None, None, 0, None, []),
    (None, None, None, 9, []),
)


async def filters_give_the_same_rows(bcf: Bcf) -> None:
    w = await _world(bcf)
    for title, status, kind, priority, labels, assigned, index, due in SET:
        await bcf.topics.create(
            project_id=w.project_id,
            author="editor",
            body=TopicPOST(
                title=title,
                topic_status=status,
                topic_type=kind,
                priority=priority,
                labels=labels,
                assigned_to=assigned,
                index=index,
                due_date=due,
            ),
        )
        await _tick()
    for filter_, orderby, top, skip, wanted in FILTERS:
        compiled = _topics(filter_, orderby, top, skip)
        found = await bcf.topics.search(user_id=w.viewer, project_id=w.project_id, compiled=compiled)
        assert [t.title for t in found] == wanted, (filter_, orderby, top, skip)
        if top is None and skip is None:
            count = await bcf.topics.count(user_id=w.viewer, project_id=w.project_id, compiled=compiled)
            assert count == len(wanted), filter_
        assert await bcf.topics.count(user_id=w.outsider, project_id=w.project_id, compiled=compiled) == 0


async def comments_and_their_events(bcf: Bcf) -> None:
    w = await _world(bcf)
    topic = await bcf.topics.create(project_id=w.project_id, author="editor", body=TopicPOST(title="Wall"))
    elsewhere = await bcf.topics.create(project_id=w.project_id, author="editor", body=TopicPOST(title="Slab"))
    camera = ViewpointPOST.model_validate({"perspective_camera": VIEWPOINT["perspective_camera"]})
    viewpoint = await bcf.viewpoints.create(
        project_id=w.project_id, topic_guid=topic.guid, author="editor", body=camera
    )
    foreign = await bcf.viewpoints.create(
        project_id=w.project_id, topic_guid=elsewhere.guid, author="editor", body=camera
    )
    scope = {"user_id": w.viewer, "project_id": w.project_id, "topic_guid": topic.guid}
    await _tick()
    first = await bcf.comments.create(
        project_id=w.project_id,
        topic_guid=topic.guid,
        author="editor",
        body=CommentPOST(guid=GUIDS[2], comment=" First "),
    )
    assert first.guid == GUIDS[2] and first.comment == "First" and first.topic_guid == topic.guid
    touched = await bcf.topics.get(user_id=w.viewer, project_id=w.project_id, guid=topic.guid)
    assert touched is not None and touched.modified_date == first.date, "a comment moves its topic"
    await _tick()
    second = await bcf.comments.create(
        project_id=w.project_id,
        topic_guid=topic.guid,
        author="viewer",
        body=CommentPOST(comment="Second", viewpoint_guid=viewpoint.model.guid.upper()),
        reply_to=first.guid,
    )
    assert second.viewpoint_guid == viewpoint.model.guid and second.reply_to_comment_guid == first.guid
    for body, reply_to, status in (
        (CommentPOST(guid=GUIDS[2], comment="again"), None, 409),
        (CommentPOST(comment="x", viewpoint_guid=foreign.model.guid), None, 400),
        (CommentPOST(comment="x"), GUIDS[19], 400),
        (CommentPOST(guid=GUIDS[3], comment="x"), GUIDS[3], 400),
        (CommentPOST(comment="x", viewpoint_guid="not-a-guid"), None, 400),
    ):
        with pytest.raises(HTTPException) as refused:
            await bcf.comments.create(
                project_id=w.project_id, topic_guid=topic.guid, author="editor", body=body, reply_to=reply_to
            )
        assert refused.value.status_code == status, body
    with pytest.raises(HTTPException) as nowhere:
        await bcf.comments.create(
            project_id=w.project_id, topic_guid=GUIDS[19], author="editor", body=CommentPOST(comment="x")
        )
    assert nowhere.value.status_code == 404

    assert [c.guid for c in await bcf.comments.search(**scope, compiled=_comments())] == [first.guid, second.guid]
    assert [c.guid for c in await bcf.comments.search(**scope, compiled=_comments("author eq 'viewer'"))] == [
        second.guid
    ]
    assert [c.guid for c in await bcf.comments.search(**scope, compiled=_comments(None, "date desc"))] == [
        second.guid,
        first.guid,
    ]
    assert await bcf.comments.count(**scope, compiled=_comments(f"date gt {first.date}")) == 1
    assert await bcf.comments.get(**scope, guid=second.guid) == second
    assert await bcf.comments.get(**(scope | {"user_id": w.outsider}), guid=second.guid) is None

    with pytest.raises(HTTPException) as referred:
        await bcf.viewpoints.delete(topic_guid=topic.guid, guid=viewpoint.model.guid)
    assert referred.value.status_code == 409, "a comment refers to it"

    await _tick()
    kept = await bcf.comments.update(
        project_id=w.project_id,
        topic_guid=topic.guid,
        guid=second.guid,
        author="editor",
        body=CommentPUT(comment="Second!"),
    )
    assert kept is not None and kept.reply_to_comment_guid == first.guid and kept.viewpoint_guid is None
    assert kept.modified_author == "editor"
    await _tick()
    undone = await bcf.comments.update(
        project_id=w.project_id,
        topic_guid=topic.guid,
        guid=second.guid,
        author="editor",
        body=CommentPUT(comment="Second!", viewpoint_guid=viewpoint.model.guid),
        change_reply=True,
        reply_to=None,
    )
    assert undone is not None and undone.reply_to_comment_guid is None and undone.viewpoint_guid == viewpoint.model.guid
    assert (
        await bcf.comments.update(
            project_id=w.project_id, topic_guid=topic.guid, guid=GUIDS[19], author="x", body=CommentPUT(comment="x")
        )
        is None
    )
    await _tick()
    await bcf.comments.update(
        project_id=w.project_id,
        topic_guid=topic.guid,
        guid=second.guid,
        author="editor",
        body=CommentPUT(comment="Second!", viewpoint_guid=viewpoint.model.guid),
        change_reply=True,
        reply_to=first.guid,
    )
    await _tick()
    assert await bcf.comments.delete(project_id=w.project_id, topic_guid=topic.guid, guid=first.guid, author="viewer")
    assert not await bcf.comments.delete(project_id=w.project_id, topic_guid=topic.guid, guid=first.guid, author="x")
    after = await bcf.comments.get(**scope, guid=second.guid)
    assert after is not None and after.reply_to_comment_guid is None, "a reply to a deleted comment is none"

    listed = await bcf.events.query(
        user_id=w.viewer, project_id=w.project_id, kind="comment", compiled=_events(), comment_guid=second.guid
    )
    assert [[(a["type"], a["value"]) for a in e["actions"]] for e in listed] == [
        [
            ("comment_created", None),
            ("comment_text_updated", "Second"),
            ("viewpoint_updated", viewpoint.model.guid),
            ("reply_to_comment_updated", first.guid),
        ],
        [("comment_text_updated", "Second!"), ("viewpoint_removed", None)],
        [("viewpoint_updated", viewpoint.model.guid), ("reply_to_comment_removed", None)],
        [("reply_to_comment_updated", first.guid)],
        [("reply_to_comment_removed", None)],
    ]
    assert listed[-1]["author"] == "viewer" and listed[0]["comment_guid"] == second.guid
    newer = await bcf.events.query(
        user_id=w.viewer,
        project_id=w.project_id,
        kind="comment",
        compiled=_events(),
        topic_guid=topic.guid,
        left_out=events.NOT_IN_30,
    )
    assert [e["comment_guid"] for e in newer] == [first.guid, second.guid, second.guid, second.guid], (
        "3.0 knows no replies: the events of replies alone are left out"
    )


VIEWPOINT = {
    "guid": GUIDS[4],
    "index": 7,
    "perspective_camera": {
        "camera_view_point": {"x": 1.25, "y": -2.5, "z": 3.0},
        "camera_direction": {"x": 0.0, "y": 1.0, "z": 0.0},
        "camera_up_vector": {"x": 0.0, "y": 0.0, "z": 1.0},
        "field_of_view": 60.0,
        "aspect_ratio": 1.5,
    },
    "lines": [{"start_point": {"x": 0.0, "y": 0.0, "z": 0.0}, "end_point": {"x": 1.0, "y": 1.0, "z": 0.1}}],
    "clipping_planes": [{"location": {"x": 0.0, "y": 0.0, "z": 2.0}, "direction": {"x": 0.0, "y": 0.0, "z": -1.0}}],
    "bitmaps": [
        {
            "bitmap_type": "png",
            "bitmap_data": _b64(PNG),
            "location": {"x": float(n), "y": 0.0, "z": 0.0},
            "normal": {"x": 0.0, "y": 0.0, "z": 1.0},
            "up": {"x": 0.0, "y": 1.0, "z": 0.0},
            "height": 0.5 + n,
        }
        for n in range(2)
    ],
    "snapshot": {"snapshot_type": "png", "snapshot_data": _b64(PNG)},
    "components": {
        "selection": [{"ifc_guid": "1Xezbq735AdBO_4DerG66G"}, {"authoring_tool_id": "42", "originating_system": "X"}],
        "coloring": [
            {"color": "ff0000", "components": [{"ifc_guid": "2Xezbq735AdBO_4DerG66G"}]},
            {"color": "AA00FF00", "components": [{"ifc_guid": "3Xezbq735AdBO_4DerG66G"}, {"authoring_tool_id": "7"}]},
        ],
        "visibility": {
            "default_visibility": False,
            "exceptions": [{"ifc_guid": "4Xezbq735AdBO_4DerG66G"}],
            "view_setup_hints": {"spaces_visible": True},
        },
    },
}


async def viewpoints_with_their_parts(bcf: Bcf) -> None:
    w = await _world(bcf)
    topic = await bcf.topics.create(project_id=w.project_id, author="editor", body=TopicPOST(title="Wall"))
    await _tick()
    made = await bcf.viewpoints.create(
        project_id=w.project_id, topic_guid=topic.guid, author="editor", body=ViewpointPOST.model_validate(VIEWPOINT)
    )
    model = made.model
    assert model.guid == GUIDS[4] and model.index == 7 and made.author == "editor" and made.snapshot_type == "png"
    assert model.perspective_camera is not None and model.perspective_camera.camera_view_point.y == -2.5
    assert model.orthogonal_camera is None and model.lines and model.lines[0].end_point.z == 0.1
    assert model.clipping_planes and model.clipping_planes[0].direction.z == -1.0
    assert model.bitmaps and [b.height for b in model.bitmaps] == [0.5, 1.5]
    assert made.snapshot_key and bcf.storage.path(made.snapshot_key).read_bytes() == PNG
    touched = await bcf.topics.get(user_id=w.viewer, project_id=w.project_id, guid=topic.guid)
    assert touched is not None and touched.modified_date != topic.modified_date, "a floating viewpoint moves it"

    scope = {"user_id": w.viewer, "project_id": w.project_id, "topic_guid": topic.guid}
    assert [r.model for r in await bcf.viewpoints.search(**scope)] == [model]
    found = await bcf.viewpoints.get(**scope, guid=model.guid)
    assert found == made
    assert await bcf.viewpoints.get(**(scope | {"user_id": w.outsider}), guid=model.guid) is None
    bitmap = await bcf.viewpoints.bitmap(**scope, guid=model.guid, bitmap_guid=model.bitmaps[1].guid)
    assert bitmap is not None and bitmap["bitmap_type"] == "png" and bitmap["loc_x"] == 1.0 and bitmap["position"] == 1
    assert bcf.storage.path(bitmap["storage_key"]).read_bytes() == PNG
    assert await bcf.viewpoints.bitmap(**scope, guid=model.guid, bitmap_guid=GUIDS[19]) is None
    selection = await bcf.viewpoints.selection(**scope, guid=model.guid)
    assert [(c.ifc_guid, c.authoring_tool_id, c.originating_system) for c in selection] == [
        ("1Xezbq735AdBO_4DerG66G", None, None),
        (None, "42", "X"),
    ]
    coloring = await bcf.viewpoints.coloring(**scope, guid=model.guid)
    assert [(group.color, [c.ifc_guid for c in group.components]) for group in coloring] == [
        ("FF0000", ["2Xezbq735AdBO_4DerG66G"]),
        ("AA00FF00", ["3Xezbq735AdBO_4DerG66G", None]),
    ]
    node = await bcf.viewpoints.node(**scope, guid=model.guid)
    assert node is not None and node["has_components"] and node["has_hints"] and "openings_visible" in node
    assert "topic_guid" not in node and None not in node.values(), "the node's properties, without nulls"
    visibility = await bcf.viewpoints.visibility(node, **scope, guid=model.guid)
    assert not visibility.default_visibility and visibility.view_setup_hints is not None
    assert visibility.view_setup_hints.spaces_visible and not visibility.view_setup_hints.openings_visible
    assert [c.ifc_guid for c in visibility.exceptions or []] == ["4Xezbq735AdBO_4DerG66G"]
    rows = await bcf.viewpoints.components(**scope, guid=model.guid, role="coloring")
    assert [(row["group_index"], row["position"]) for row in rows] == [(0, 0), (1, 0), (1, 1)]
    assert "color" in rows[0] and "ifc_guid" not in rows[2], "the node's properties, without nulls"
    assert await bcf.viewpoints.node(**(scope | {"user_id": w.outsider}), guid=model.guid) is None

    with pytest.raises(HTTPException) as taken:
        await bcf.viewpoints.create(
            project_id=w.project_id,
            topic_guid=topic.guid,
            author="editor",
            body=ViewpointPOST.model_validate(ORTHOGONAL | {"guid": GUIDS[4]}),
        )
    assert taken.value.status_code == 409
    files = sorted(path.name for path in bcf.storage.root.rglob("*") if path.is_file())
    with pytest.raises(HTTPException) as nowhere:
        await bcf.viewpoints.create(
            project_id=w.project_id,
            topic_guid=GUIDS[19],
            author="editor",
            body=ViewpointPOST(snapshot={"snapshot_type": "png", "snapshot_data": _b64(PNG)}),
        )
    assert nowhere.value.status_code == 404
    assert sorted(path.name for path in bcf.storage.root.rglob("*") if path.is_file()) == files, "nothing left"

    await _tick()
    plain = await bcf.viewpoints.create(
        project_id=w.project_id, topic_guid=topic.guid, author="viewer", body=ViewpointPOST.model_validate(ORTHOGONAL)
    )
    assert plain.model.orthogonal_camera is not None and plain.model.bitmaps is None and plain.snapshot_key is None
    bare = await bcf.viewpoints.node(**scope, guid=plain.model.guid)
    assert bare is not None and not bare["has_components"] and bare["default_visibility"]
    assert (await bcf.viewpoints.visibility(bare, **scope, guid=plain.model.guid)).exceptions == []
    assert [r.model.guid for r in await bcf.viewpoints.search(**scope)] == [model.guid, plain.model.guid]

    keys = await bcf.viewpoints.delete(topic_guid=topic.guid, guid=model.guid)
    assert len(keys) == 3 and made.snapshot_key in keys and bitmap["storage_key"] in keys
    assert len([key for key in keys if key.startswith("bitmaps/")]) == 2, "its snapshot and its two bitmaps"
    assert await bcf.viewpoints.get(**scope, guid=model.guid) is None
    assert await bcf.viewpoints.components(**scope, guid=model.guid, role="selection") == []
    with pytest.raises(HTTPException) as gone:
        await bcf.viewpoints.delete(topic_guid=topic.guid, guid=model.guid)
    assert gone.value.status_code == 404
    again = await bcf.viewpoints.create(
        project_id=w.project_id, topic_guid=topic.guid, author="editor", body=ViewpointPOST.model_validate(VIEWPOINT)
    )
    assert again.model.guid == GUIDS[4], "the guid is free again"
    keys = await bcf.topics.delete(project_id=w.project_id, guid=topic.guid)
    assert len(keys) == 3 and again.snapshot_key in keys, "the topic's files: a snapshot and two bitmaps"


async def what_a_topic_points_at(bcf: Bcf) -> None:
    w = await _world(bcf)
    topics = []
    for title in ("One", "Two", "Three"):
        topics.append(await bcf.topics.create(project_id=w.project_id, author="editor", body=TopicPOST(title=title)))
        await _tick()
    one, two, three = topics
    outside = await bcf.topics.create(project_id=w.other_project_id, author="editor", body=TopicPOST(title="Out"))
    scope = {"user_id": w.viewer, "project_id": w.project_id, "topic_guid": one.guid}

    assert await bcf.links.set_related(
        project_id=w.project_id, topic_guid=one.guid, author="viewer", guids=[three.guid.upper(), two.guid, three.guid]
    ) == [three.guid, two.guid]
    assert await bcf.links.related(**scope) == [two.guid, three.guid], "in the order they were made"
    assert await bcf.links.related(**(scope | {"user_id": w.outsider})) == []
    for guids, words in (([one.guid], "itself"), (["x"], "UUID"), ([outside.guid], "not topics of this project")):
        with pytest.raises(HTTPException, match=words):
            await bcf.links.set_related(project_id=w.project_id, topic_guid=one.guid, author="viewer", guids=guids)
    touched = await bcf.topics.get(user_id=w.viewer, project_id=w.project_id, guid=one.guid)
    assert touched is not None and touched.modified_author == "viewer"
    await bcf.topics.delete(project_id=w.project_id, guid=three.guid)
    assert await bcf.links.related(**scope) == [two.guid], "a deleted topic is related to none"
    assert await bcf.links.set_related(project_id=w.project_id, topic_guid=one.guid, author="viewer", guids=[]) == []
    assert await bcf.links.related(**scope) == []

    document = await bcf.documents.create(
        project_id=w.project_id,
        guid=GUIDS[5],
        filename="plan.pdf",
        author="editor",
        storage_key="bcf-documents/x",
        size=3,
    )
    elsewhere = await bcf.documents.create(
        project_id=w.other_project_id,
        guid=GUIDS[6],
        filename="o.pdf",
        author="editor",
        storage_key="bcf-documents/y",
        size=1,
    )
    first = await bcf.links.add_reference(
        project_id=w.project_id,
        topic_guid=one.guid,
        author="editor",
        body=DocumentReferencePOST(guid=GUIDS[7], url="https://example.org/a", description="A"),
    )
    assert first.guid == GUIDS[7] and first.url == "https://example.org/a" and first.document_guid is None
    await _tick()
    second = await bcf.links.add_reference(
        project_id=w.project_id,
        topic_guid=one.guid,
        author="editor",
        body=DocumentReferencePOST(document_guid=document.guid.upper()),
    )
    assert second.document_guid == document.guid
    for body, status in (
        (DocumentReferencePOST(guid=GUIDS[7], url="https://example.org/b"), 409),
        (DocumentReferencePOST(document_guid=elsewhere.guid), 400),
        (DocumentReferencePOST(document_guid="not-a-guid"), 400),
    ):
        with pytest.raises(HTTPException) as refused:
            await bcf.links.add_reference(project_id=w.project_id, topic_guid=one.guid, author="editor", body=body)
        assert refused.value.status_code == status
    with pytest.raises(HTTPException) as nowhere:
        await bcf.links.add_reference(
            project_id=w.project_id,
            topic_guid=GUIDS[19],
            author="editor",
            body=DocumentReferencePOST(url="https://example.org/c"),
        )
    assert nowhere.value.status_code == 404
    changed = await bcf.links.update_reference(
        project_id=w.project_id,
        topic_guid=one.guid,
        guid=first.guid,
        author="editor",
        body=DocumentReferencePUT(document_guid=document.guid, description="now internal"),
    )
    assert changed is not None and changed.url is None and changed.document_guid == document.guid
    assert (
        await bcf.links.update_reference(
            project_id=w.project_id,
            topic_guid=two.guid,
            guid=first.guid,
            author="editor",
            body=DocumentReferencePUT(url="https://example.org/d"),
        )
        is None
    ), "another topic's reference"
    assert await bcf.links.references(**scope) == [changed, second]
    assert await bcf.links.references(**(scope | {"user_id": w.outsider})) == []

    files = [
        FileRef(ifc_project="0J$yPqHBD12v72y4qF6XcD", filename="a.ifc", date="2026-11-12T10:00:00Z", reference="r"),
        FileRef(filename="b.ifc"),
    ]
    assert (
        await bcf.links.set_files(project_id=w.project_id, topic_guid=one.guid, author="editor", files=files) == files
    )
    assert await bcf.links.files(**scope) == files
    assert (await bcf.links.files(**scope))[0].date == "2026-11-12T10:00:00.000Z"
    await bcf.links.set_files(project_id=w.project_id, topic_guid=one.guid, author="editor", files=files[1:])
    assert await bcf.links.files(**scope) == files[1:]
    assert await bcf.links.files(**(scope | {"user_id": w.outsider})) == []

    external = await bcf.topics.create(
        project_id=w.project_id,
        author="editor",
        body=TopicPOST(
            title="Change",
            bim_snippet=BimSnippet(
                snippet_type=".json", is_external=True, reference="https://x.org/c", reference_schema="s"
            ),
        ),
    )
    snippet_scope = scope | {"topic_guid": external.guid}
    assert await bcf.links.snippet(**snippet_scope) is None, "an external snippet has no file here"
    await bcf.links.set_snippet(
        project_id=w.project_id,
        topic_guid=external.guid,
        author="viewer",
        storage_key="snippets/k",
        filename=None,
        size=4,
    )
    assert await bcf.links.snippet(**snippet_scope) == {"storage_key": "snippets/k", "filename": "https://x.org/c"}
    await bcf.links.set_snippet(
        project_id=w.project_id,
        topic_guid=external.guid,
        author="viewer",
        storage_key="snippets/k",
        filename="change.json",
        size=4,
    )
    assert await bcf.links.snippet(**snippet_scope) == {"storage_key": "snippets/k", "filename": "change.json"}
    assert await bcf.links.snippet(**(snippet_scope | {"user_id": w.outsider})) is None
    internal = await bcf.topics.get(user_id=w.viewer, project_id=w.project_id, guid=external.guid)
    assert internal is not None and internal.bim_snippet is not None and not internal.bim_snippet.is_external
    assert internal.bim_snippet.reference == "change.json" and internal.modified_author == "viewer"
    assert await bcf.topics.delete(project_id=w.project_id, guid=external.guid) == ["snippets/k"]


async def project_documents(bcf: Bcf) -> None:
    w = await _world(bcf)
    first = await bcf.documents.create(
        project_id=w.project_id,
        guid=GUIDS[8],
        filename="plan.pdf",
        author="editor",
        storage_key="bcf-documents/a",
        size=3,
    )
    assert (first.guid, first.filename) == (GUIDS[8], "plan.pdf")
    await _tick()
    await bcf.documents.create(
        project_id=w.project_id, guid=GUIDS[9], filename="b.ifc", author="viewer", storage_key="bcf-documents/b", size=9
    )
    with pytest.raises(HTTPException) as taken:
        await bcf.documents.create(
            project_id=w.other_project_id, guid=GUIDS[8], filename="x", author="editor", storage_key="k", size=1
        )
    assert taken.value.status_code == 409, "a guid is the server's, not the project's"
    with pytest.raises(HTTPException) as nowhere:
        await bcf.documents.create(
            project_id="none", guid=GUIDS[10], filename="x", author="editor", storage_key="k", size=1
        )
    assert nowhere.value.status_code == 404
    assert await bcf.documents.exists(GUIDS[8]) and not await bcf.documents.exists(GUIDS[10])
    assert [(d.guid, d.filename) for d in await bcf.documents.search(user_id=w.viewer, project_id=w.project_id)] == [
        (GUIDS[8], "plan.pdf"),
        (GUIDS[9], "b.ifc"),
    ]
    assert await bcf.documents.search(user_id=w.outsider, project_id=w.project_id) == []
    stored = await bcf.documents.get(user_id=w.viewer, project_id=w.project_id, guid=GUIDS[9])
    assert stored is not None and set(stored) == {"guid", "filename", "storage_key", "size", "created_at", "author"}
    assert (stored["storage_key"], stored["size"], stored["author"]) == ("bcf-documents/b", 9, "viewer")
    assert await bcf.documents.get(user_id=w.outsider, project_id=w.project_id, guid=GUIDS[9]) is None
    entries = await bcf.documents.files_information(user_id=w.viewer, project_id=w.project_id, base_url="https://cde")
    assert [entry.file.reference for entry in entries] == [
        f"https://cde/bcf/3.0/projects/{w.project_id}/documents/{GUIDS[8]}",
        f"https://cde/bcf/3.0/projects/{w.project_id}/documents/{GUIDS[9]}",
    ]
    assert [d.field_value for d in entries[1].display_information] == [
        "b.ifc",
        stored["created_at"],
        "viewer",
        "BCF API document",
        GUIDS[9],
        "",
    ]
    assert await bcf.documents.files_information(user_id=w.outsider, project_id=w.project_id, base_url="x") == []


async def a_project_owns_its_bcf_files(bcf: Bcf) -> None:
    w = await _world(bcf)
    topic = await bcf.topics.create(project_id=w.project_id, author="editor", body=TopicPOST(title="Wall"))
    made = await bcf.viewpoints.create(
        project_id=w.project_id, topic_guid=topic.guid, author="editor", body=ViewpointPOST.model_validate(VIEWPOINT)
    )
    await bcf.links.set_snippet(
        project_id=w.project_id, topic_guid=topic.guid, author="editor", storage_key="snippets/s", filename="s", size=1
    )
    await bcf.documents.create(
        project_id=w.project_id, guid=GUIDS[11], filename="d", author="editor", storage_key="bcf-documents/d", size=1
    )
    await bcf.comments.create(
        project_id=w.project_id, topic_guid=topic.guid, author="editor", body=CommentPOST(comment="c")
    )
    keys = await bcf.projects.storage_keys(w.project_id)
    bitmaps = [key for key in keys if key.startswith("bitmaps/")]
    assert sorted(keys) == sorted([made.snapshot_key, "snippets/s", "bcf-documents/d", *bitmaps]) and len(bitmaps) == 2
    assert await bcf.projects.storage_keys(w.other_project_id) == []
    assert await bcf.projects.delete(w.project_id)
    assert not await bcf.topics.exists(topic.guid) and not await bcf.documents.exists(GUIDS[11])
    assert await bcf.projects.storage_keys(w.project_id) == []


CASES = (
    topics_and_their_events,
    filters_give_the_same_rows,
    comments_and_their_events,
    viewpoints_with_their_parts,
    what_a_topic_points_at,
    project_documents,
    a_project_owns_its_bcf_files,
)


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.__name__)
async def test_on_the_graph(case: Callable[[Bcf], Awaitable[None]], graph: Graph, tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path / "data")
    topics = TopicRepository(graph)
    await case(
        Bcf(
            UserRepository(graph),
            ProjectRepository(graph),
            topics,
            CommentRepository(graph, topics),
            ViewpointRepository(graph, storage, topics, max_image_bytes=MAX_IMAGE_BYTES),
            TopicLinkRepository(graph, topics),
            BcfDocumentRepository(graph),
            BcfEventRepository(graph),
            storage,
        )
    )


def _on_postgresql(pg: Postgres, storage: LocalStorage) -> Bcf:
    return Bcf(
        PostgresUserRepository(pg),
        PostgresProjectRepository(pg),
        PostgresTopicRepository(pg),
        PostgresCommentRepository(pg),
        PostgresViewpointRepository(pg, storage, max_image_bytes=MAX_IMAGE_BYTES),
        PostgresTopicLinkRepository(pg),
        PostgresBcfDocumentRepository(pg),
        PostgresBcfEventRepository(pg),
        storage,
    )


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.__name__)
async def test_on_postgresql(case: Callable[[Bcf], Awaitable[None]], pg: Postgres, tmp_path: Path) -> None:
    await case(_on_postgresql(pg, LocalStorage(tmp_path / "data")))


# -- PostgreSQL's own ----------------------------------------------------------------------------------------------


async def test_on_postgresql_lower_maps_every_letter_and_text_is_ordered_by_code_point(
    pg: Postgres, tmp_path: Path
) -> None:
    bcf = _on_postgresql(pg, LocalStorage(tmp_path))
    w = await _world(bcf)
    for title in ("Åtgärd", "beam", "Wall"):
        await bcf.topics.create(project_id=w.project_id, author="editor", body=TopicPOST(title=title))
    found = await bcf.topics.search(
        user_id=w.viewer, project_id=w.project_id, compiled=_topics("tolower(title) eq 'åtgärd'")
    )
    assert [t.title for t in found] == ["Åtgärd"], "as Neo4j's toLower, not ASCII's alone"
    ordered = await bcf.topics.search(user_id=w.viewer, project_id=w.project_id, compiled=_topics("title gt 'A'"))
    assert sorted(t.title for t in ordered) == ["Wall", "beam", "Åtgärd"]


async def test_on_postgresql_the_files_information_holds_the_latest_versions(pg: Postgres, tmp_path: Path) -> None:
    """The Documents area's versions (0003), written by its own repository."""
    bcf = _on_postgresql(pg, LocalStorage(tmp_path))
    w = await _world(bcf)
    documents = PostgresDocumentRepository(pg)
    for index, name in ((1, "old.ifc"), (2, "new.ifc")):
        await documents.create_version(
            project_id=w.project_id,
            document_id=GUIDS[12] if index > 1 else None,
            requested_document_id=GUIDS[12] if index == 1 else None,
            title="Model",
            version_number="",
            file_name=name,
            size_in_bytes=1,
            sha256="0" * 64,
            storage_key=f"documents/{index}",
            author="editor",
            metadata=[],
        )
    entries = await bcf.documents.files_information(user_id=w.viewer, project_id=w.project_id, base_url="https://cde")
    assert [(e.file.filename, e.file.reference) for e in entries] == [
        ("new.ifc", f"https://cde/documents/1.0/documents/{GUIDS[12]}/versions/2/download")
    ]
    assert [d.field_value for d in entries[0].display_information][-2:] == [GUIDS[12], "2"]
    reference = await bcf.links.add_reference(
        project_id=w.project_id,
        topic_guid=(await bcf.topics.create(project_id=w.project_id, author="editor", body=TopicPOST(title="T"))).guid,
        author="editor",
        body=DocumentReferencePOST(document_guid=GUIDS[12]),
    )
    assert reference.document_guid == GUIDS[12], "a Documents API document is one of the project's"


async def test_on_postgresql_a_topic_needs_its_project_and_goes_with_it(pg: Postgres, tmp_path: Path) -> None:
    bcf = _on_postgresql(pg, LocalStorage(tmp_path))
    w = await _world(bcf)
    with pytest.raises(ForeignKeyViolationError):
        await pg.execute(
            """
            INSERT INTO topics (guid, project_id, title, server_assigned_id, creation_date, creation_author)
            VALUES ('t', 'no-such-project', 'x', 'ISSUE-0001', '2026-11-12T10:00:00.000Z', 'editor')
            """
        )
    topic = await bcf.topics.create(project_id=w.project_id, author="editor", body=TopicPOST(title="Wall"))
    await bcf.comments.create(
        project_id=w.project_id, topic_guid=topic.guid, author="editor", body=CommentPOST(comment="c")
    )
    await bcf.projects.delete(w.project_id)
    for statement in (
        "SELECT count(*) AS n FROM topics",
        "SELECT count(*) AS n FROM comments",
        "SELECT count(*) AS n FROM bcf_events",
    ):
        assert await pg.one(statement) == {"n": 0}, statement
