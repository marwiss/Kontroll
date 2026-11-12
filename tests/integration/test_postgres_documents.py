# This file was generated with the assistance of an AI coding tool.
"""The Documents area in PostgreSQL (ADR 0029) against a real database: the same cases on the graph's repositories
and on PostgreSQL's, what PostgreSQL adds of its own (versions and publications made at once, the seams the other
areas read, the cleaner deleting expired sessions with their parts' files), and the browser's pages reading a
document and a selection from PostgreSQL.

PostgreSQL runs in a container of its own (``postgres_target`` and ``pg`` in the conftest), one per test session;
every test starts from empty tables with the migrations applied. Each case runs once on the graph and once on
PostgreSQL, which needs no graph: ``-k on_postgresql`` starts PostgreSQL alone."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from ifc_db.validation import pack_report
from neo4j import GraphDatabase
from pydantic import SecretStr

from opencde.accounts.roles import Role
from opencde.documents.schemas import DocumentMetadataEntry
from opencde.graph.graph import Graph
from opencde.ids import new_id
from opencde.main import create_app
from opencde.postgres.cleanup import delete_expired
from opencde.postgres.database import Postgres
from opencde.settings import Settings
from opencde.storage import LocalStorage, make_key
from opencde.store.accounts.postgres import PostgresProjectRepository, PostgresTeamRepository, PostgresUserRepository
from opencde.store.accounts.projects import ProjectRepository
from opencde.store.accounts.teams import TeamRepository
from opencde.store.accounts.users import UserRepository
from opencde.store.documents.postgres import (
    PostgresDocumentRepository,
    PostgresSelectionSessionRepository,
    PostgresUploadSessionRepository,
)
from opencde.store.documents.sessions import SelectionSessionRepository, UploadSessionRepository
from opencde.store.documents.versions import DocumentRepository, default_metadata
from opencde.store.protocols import (
    DocumentStore,
    ProjectStore,
    SelectionSessionStore,
    TeamStore,
    UploadSessionStore,
    UserStore,
)
from tests.integration.conftest import GraphTarget, PostgresTarget, emptied_postgres
from tests.integration.test_web_signin import form_token

pytestmark = pytest.mark.integration

PASSWORD = "a-long-and-strong-passphrase"
DOCUMENT_ID = "0b7a4e52-3c1d-4f6e-8a9b-2c3d4e5f6a7b"
CHANGES = [{"op": "set_property", "guid": "2O2Fr$t4X7Zf8NOew3FLOH", "name": "FireRating", "value": "EI 60"}]


@dataclass(frozen=True)
class Area:
    users: UserStore
    projects: ProjectStore
    teams: TeamStore
    documents: DocumentStore
    uploads: UploadSessionStore
    selections: SelectionSessionStore


def _version(**fields: Any) -> dict[str, Any]:
    name = str(fields.pop("file_name", "plan.ifc"))
    return {
        "title": "Plan",
        "version_number": "",
        "file_name": name,
        "size_in_bytes": 3,
        "sha256": "0" * 64,
        "storage_key": make_key("documents", new_id()),
        "author": "editor",
        "metadata": default_metadata(
            file_name=name, size_in_bytes=3, sha256="0" * 64, author="editor", project_name="Building permit"
        ),
        **fields,
    }


# -- the same on both ----------------------------------------------------------------------------------------------


async def documents_and_their_versions(area: Area) -> None:
    users, projects, documents = area.users, area.projects, area.documents
    editor, outsider = await users.create("editor", PASSWORD), await users.create("outsider", PASSWORD)
    project = await projects.create("beta")
    other = await projects.create("Alpha")
    for pid in (project.project_id, other.project_id):
        await projects.set_member(pid, editor.id, Role.EDITOR)
    await projects.set_member(other.project_id, outsider.id, Role.VIEWER)
    pid = project.project_id

    first = await documents.create_version(
        project_id=pid, document_id=None, requested_document_id=DOCUMENT_ID, **_version()
    )
    assert (first.document_id, first.version_index, first.version_number) == (DOCUMENT_ID, 1, "1")
    assert first.project_name == "beta" and first.metadata[0] == {
        "name": "file_name",
        "value": ["plan.ifc"],
        "data_type": "string",
    }
    second = await documents.create_version(
        project_id=pid,
        document_id=DOCUMENT_ID,
        parent_version_index=1,
        approved_by="editor",
        change_set_id="topic-1",
        change_set=pack_report(CHANGES),
        **_version(title="Plan, revised", version_number="B", metadata=[]),
    )
    assert (second.version_index, second.version_number, second.title) == (2, "B", "Plan, revised")
    ids = await documents.create_version(project_id=pid, document_id=None, **_version(file_name="rules.ids"))
    elsewhere = await documents.create_version(
        project_id=other.project_id,
        document_id=None,
        **_version(title="Archive", metadata=[DocumentMetadataEntry(name="n", value=["v"], data_type="string")]),
    )

    latest = await documents.latest(user_id=editor.id, document_id=DOCUMENT_ID)
    assert latest is not None and latest.version_index == 2 and latest.title == "Plan, revised"
    found = await documents.version(user_id=editor.id, document_id=DOCUMENT_ID, version_index=1)
    assert found is not None and found.storage_key == first.storage_key and found.version_id == first.version_id
    assert [r.version_index for r in await documents.versions(user_id=editor.id, document_id=DOCUMENT_ID)] == [1, 2]
    for user_id in (outsider.id, "no-such-user"):
        assert await documents.latest(user_id=user_id, document_id=DOCUMENT_ID) is None, "not a member: no document"
        assert await documents.versions(user_id=user_id, document_id=DOCUMENT_ID) == []
    asked = [ids.document_id, DOCUMENT_ID, "no-such-document", elsewhere.document_id]
    many = await documents.latest_many(user_id=editor.id, document_ids=asked)
    assert [r.document_id for r in many] == sorted([ids.document_id, DOCUMENT_ID, elsewhere.document_id])
    assert [r.document_id for r in await documents.latest_many(user_id=outsider.id, document_ids=asked)] == [
        elsewhere.document_id
    ]
    listed = await documents.latest_in_projects(user_id=editor.id)
    assert [(r.project_name, r.title) for r in listed] == [
        ("Alpha", "Archive"),
        ("beta", "Plan"),
        ("beta", "Plan, revised"),
    ], "by project name in code point order, then by title"
    assert [(r.file_name, r.version_index) for r in listed] == [("plan.ifc", 1), ("rules.ids", 1), ("plan.ifc", 2)]

    assert await documents.change_set(user_id=editor.id, document_id=DOCUMENT_ID, version_index=1) is None
    assert await documents.change_set(user_id=editor.id, document_id=DOCUMENT_ID, version_index=2) == {
        "change_set_id": "topic-1",
        "base": {"document_id": DOCUMENT_ID, "version_index": 1},
        "proposed_by": "editor",
        "approved_by": "editor",
        "changes": CHANGES,
    }
    assert await documents.change_set(user_id=outsider.id, document_id=DOCUMENT_ID, version_index=2) is None
    since = await documents.versions_since(user_id=editor.id, document_id=DOCUMENT_ID, since=0, until=2)
    assert [(c["version_index"], c["changes"]) for c in since] == [(1, None), (2, CHANGES)]
    assert await documents.validation(user_id=editor.id, document_id=DOCUMENT_ID, version_index=2) is None

    with pytest.raises(HTTPException, match="Document not found"):  # held to the project it was given
        await documents.create_version(project_id=other.project_id, document_id=DOCUMENT_ID, **_version())
    with pytest.raises(HTTPException, match="Project not found"):  # the author is no user
        await documents.create_version(project_id=pid, document_id=DOCUMENT_ID, **_version(author="nobody"))
    again = await documents.latest(user_id=editor.id, document_id=DOCUMENT_ID)
    assert again is not None and again.version_index == 2, "a refused version takes no number"


async def publications(area: Area) -> None:
    users, projects, documents = area.users, area.projects, area.documents
    manager, outsider = await users.create("editor", PASSWORD), await users.create("outsider", PASSWORD)
    project = await projects.create("Building permit")
    await projects.set_member(project.project_id, manager.id, Role.MANAGER)
    made = await documents.create_version(project_id=project.project_id, document_id=None, **_version())
    where = {"document_id": made.document_id, "version_index": 1}
    assert await documents.publication(user_id=manager.id, **where) is None
    publication = {
        "id": new_id(),
        "storage_key": make_key("published", new_id(), "ifczip"),
        "file_name": "plan.ifczip",
        "size_in_bytes": 9,
        "sha256": "1" * 64,
        "published_at": "2026-11-12T10:00:00.000Z",
        "published_by": "editor",
    }
    event = {"type": "documents.publish", "actor": manager.id, "details": where}
    assert not await documents.publish(user_id=outsider.id, publication=publication, audit_event=event, **where), (
        "only a member's version"
    )
    assert await documents.publish(user_id=manager.id, publication=publication, audit_event=event, **where)
    assert not await documents.publish(
        user_id=manager.id, publication={**publication, "id": new_id()}, audit_event=event, **where
    ), "published already"
    assert await documents.publication(user_id=manager.id, **where) == publication
    assert await documents.publication(user_id=outsider.id, **where) is None

    keys = await projects.storage_keys(project.project_id)
    assert sorted(keys) == sorted([made.storage_key, publication["storage_key"]]), "the files a project owns"
    assert await projects.delete(project.project_id)
    assert await documents.latest(user_id=manager.id, document_id=made.document_id) is None, "with its project"


async def the_teams_read_the_latest_ids_file(area: Area) -> None:
    users, projects, teams, documents = area.users, area.projects, area.teams, area.documents
    lead = await users.create("editor", PASSWORD)
    project = await projects.create("Building permit")
    await projects.set_member(project.project_id, lead.id, Role.EDITOR)
    first = await documents.create_version(
        project_id=project.project_id, document_id=None, **_version(file_name="rules.ids")
    )
    second = await documents.create_version(
        project_id=project.project_id, document_id=first.document_id, **_version(file_name="rules.ids")
    )
    await teams.save(
        project.project_id,
        team_id=None,
        name="Structure",
        responsible_user_id=lead.id,
        member_ids=[lead.id],
        ids_document_id=first.document_id,
    )
    (part,) = await teams.parts(project.project_id)
    assert (part["name"], part["storage_key"], part["ids_version_index"]) == ("Structure", second.storage_key, 2)


async def upload_sessions_and_their_parts(area: Area) -> None:
    uploads = area.uploads
    files = [{"session_file_id": "f-1", "file_name": "plan.ifc", "state": "pending", "document_id": None}]
    session_id, token = await uploads.create(
        user_id="u-1",
        username="editor",
        callback_url="http://localhost:9/callback",
        callback_expires_in=300,
        server_context="ctx",
        files=files,
    )
    session = await uploads.by_token(token)
    assert session is not None and session.id == session_id and session.state == "new" and session.files == files
    assert session.server_context == "ctx" and session.project_id is None and not session.callback_expired
    assert await uploads.by_token(token + "x") is None and await uploads.by_token("x" * 129) is None
    assert await uploads.by_id(session_id) == session

    await uploads.update(session_id, state="metadata", project_id="p-1")
    changed = await uploads.by_id(session_id)
    assert changed is not None and (changed.state, changed.project_id, changed.files) == ("metadata", "p-1", files)
    files[0]["state"] = "parts"
    await uploads.update(session_id, state="uploading", files=files, extend=True)
    extended = await uploads.by_id(session_id)
    assert extended is not None and extended.files[0]["state"] == "parts" and extended.project_id == "p-1"
    assert extended.expires_at > session.expires_at, "the upload's own time"

    ids = await uploads.create_parts(session_id, 0, [(0, 1023), (1024, 1500)])
    assert await uploads.create_parts("no-such-session", 0, [(0, 9)]) != [], "ids, but no parts"
    part = await uploads.part(ids[1])
    assert part is not None and part["user_id"] == "u-1" and part["session_id"] == session_id
    assert (part["part_index"], part["range_start"], part["range_end"], part["received"]) == (1, 1024, 1500, False)
    await uploads.mark_received(ids[1], "parts/" + ids[1], 477)
    listed = await uploads.parts(session_id, 0)
    assert [(p["id"], p["received"], p.get("storage_key")) for p in listed] == [
        (ids[0], False, None),
        (ids[1], True, "parts/" + ids[1]),
    ]
    assert await uploads.parts(session_id, 1) == []
    assert await uploads.delete_parts(session_id, 0) == ["parts/" + ids[1]], "the keys of the parts received"
    assert await uploads.parts(session_id, 0) == [] and await uploads.part(ids[0]) is None


async def selection_sessions(area: Area) -> None:
    selections = area.selections
    session_id, token = await selections.create(
        user_id="u-1",
        callback_url="http://localhost:9/callback",
        callback_expires_in=300,
        server_context=None,
        extensions=[".ifc", ".ids"],
    )
    session = await selections.by_token(token)
    assert session is not None and session.id == session_id and session.state == "new"
    assert session.extensions == [".ifc", ".ids"] and session.selected == [] and session.server_context is None
    await selections.finish(session_id, state="selected", selected=[f"{DOCUMENT_ID}:2", f"{DOCUMENT_ID}:1"])
    finished = await selections.by_id(session_id)
    assert finished is not None and finished.state == "selected"
    assert finished.selected == [f"{DOCUMENT_ID}:2", f"{DOCUMENT_ID}:1"], "in the order chosen"
    assert await selections.by_token("not-a-token") is None and await selections.by_id("no-such-session") is None


CASES = (
    documents_and_their_versions,
    publications,
    the_teams_read_the_latest_ids_file,
    upload_sessions_and_their_parts,
    selection_sessions,
)


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.__name__)
async def test_on_the_graph(case: Callable[[Area], Awaitable[None]], graph: Graph) -> None:
    await case(
        Area(
            UserRepository(graph),
            ProjectRepository(graph),
            TeamRepository(graph),
            DocumentRepository(graph),
            UploadSessionRepository(graph, ui_ttl_seconds=600, upload_ttl_seconds=3600),
            SelectionSessionRepository(graph, ui_ttl_seconds=600),
        )
    )


def _on_postgresql(pg: Postgres) -> Area:
    return Area(
        PostgresUserRepository(pg),
        PostgresProjectRepository(pg),
        PostgresTeamRepository(pg),
        PostgresDocumentRepository(pg),
        PostgresUploadSessionRepository(pg, ui_ttl_seconds=600, upload_ttl_seconds=3600),
        PostgresSelectionSessionRepository(pg, ui_ttl_seconds=600),
    )


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.__name__)
async def test_on_postgresql(case: Callable[[Area], Awaitable[None]], pg: Postgres) -> None:
    await case(_on_postgresql(pg))


# -- PostgreSQL's own ----------------------------------------------------------------------------------------------


async def test_on_postgresql_versions_and_publications_made_at_once_keep_their_numbers(pg: Postgres) -> None:
    area = _on_postgresql(pg)
    editor = await area.users.create("editor", PASSWORD)
    project = await area.projects.create("Building permit")
    await area.projects.set_member(project.project_id, editor.id, Role.MANAGER)
    first = await area.documents.create_version(project_id=project.project_id, document_id=None, **_version())
    made = await asyncio.gather(
        *(
            area.documents.create_version(project_id=project.project_id, document_id=first.document_id, **_version())
            for _ in range(6)
        )
    )
    assert sorted(record.version_index for record in made) == [2, 3, 4, 5, 6, 7], "the document's row is the lock"
    publication = {
        "storage_key": "published/x.zip",
        "file_name": "plan.ifczip",
        "size_in_bytes": 9,
        "sha256": "1" * 64,
        "published_at": "2026-11-12T10:00:00.000Z",
        "published_by": "editor",
    }
    answers = await asyncio.gather(
        *(
            area.documents.publish(
                user_id=editor.id,
                document_id=first.document_id,
                version_index=7,
                publication={**publication, "id": new_id()},
                audit_event={"type": "documents.publish"},
            )
            for _ in range(4)
        )
    )
    assert sorted(answers) == [False, False, False, True], "one publication per version"


async def test_on_postgresql_the_seams_answer_what_the_other_areas_read(pg: Postgres) -> None:
    area = _on_postgresql(pg)
    editor = await area.users.create("editor", PASSWORD)
    project = await area.projects.create("Building permit")
    first = await area.documents.create_version(project_id=project.project_id, document_id=None, **_version())
    second = await area.documents.create_version(
        project_id=project.project_id, document_id=first.document_id, **_version()
    )
    heads = await pg.run("SELECT project_id, document_id, version_index, storage_key FROM document_heads")
    assert heads == [
        {
            "project_id": project.project_id,
            "document_id": first.document_id,
            "version_index": 2,
            "storage_key": second.storage_key,
        }
    ]
    files = await pg.run("SELECT storage_key FROM project_files WHERE project_id = $1", project.project_id)
    assert sorted(row["storage_key"] for row in files) == sorted([first.storage_key, second.storage_key])
    for view in ("SELECT count(*) AS n FROM version_validations", "SELECT count(*) AS n FROM version_graph_checks"):
        assert await pg.one(view) == {"n": 0}, "no version was checked"
    row = await pg.one("SELECT metadata FROM document_versions WHERE id = $1", first.version_id)
    assert row is not None and row["metadata"][0]["name"] == "file_name", "metadata is a jsonb document"
    await area.users.delete(editor.id)
    kept = await pg.one("SELECT author, uploaded_by FROM document_versions WHERE id = $1", first.version_id)
    assert kept == {"author": "editor", "uploaded_by": None}, "a deleted user leaves the versions they uploaded"


async def test_on_postgresql_expired_sessions_go_with_their_parts_files(pg: Postgres, tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path)
    expired = PostgresUploadSessionRepository(pg, ui_ttl_seconds=-60, upload_ttl_seconds=-60)
    lasting = PostgresUploadSessionRepository(pg, ui_ttl_seconds=600, upload_ttl_seconds=3600)
    gone_id, _ = await expired.create(
        user_id="u", username="u", callback_url="http://x", callback_expires_in=60, server_context=None, files=[]
    )
    kept_id, kept_token = await lasting.create(
        user_id="u", username="u", callback_url="http://x", callback_expires_in=60, server_context=None, files=[]
    )
    # The expired session's part outlasts it, and its file goes all the same; the lasting session's part stays.
    (gone_part,) = await lasting.create_parts(gone_id, 0, [(0, 2)])
    (kept_part,) = await lasting.create_parts(kept_id, 0, [(0, 2)])
    for part_id in (gone_part, kept_part):
        key = make_key("parts", part_id)
        storage.write_bytes(key, b"abc")
        await lasting.mark_received(part_id, key, 3)
    selections = PostgresSelectionSessionRepository(pg, ui_ttl_seconds=-60)
    await selections.create(
        user_id="u", callback_url="http://x", callback_expires_in=60, server_context=None, extensions=[]
    )

    assert await delete_expired(pg, storage=storage) == 3, "a part, its upload session and a selection session"
    assert (
        not storage.path(make_key("parts", gone_part)).exists() and storage.path(make_key("parts", kept_part)).exists()
    )
    assert await pg.one("SELECT count(*) AS n FROM upload_parts") == {"n": 1}
    assert await lasting.by_token(kept_token) is not None
    assert await pg.one("SELECT count(*) AS n FROM selection_sessions") == {"n": 0}


def test_the_browser_reads_a_document_and_a_selection_from_postgresql(
    settings: Settings, clean_database: None, graph_target: GraphTarget, postgres_target: PostgresTarget
) -> None:
    """The routes choose PostgreSQL's repositories when ``OPENCDE_STORE_URL`` names it: the details page, its
    download and the selection page read the version and the session there, and the graph holds no document."""
    content = b"ISO-10303-21;"

    async def seed() -> tuple[str, str]:
        postgres = await emptied_postgres(postgres_target)
        try:
            area = _on_postgresql(postgres)
            editor = await area.users.create("editor", PASSWORD)
            project = await area.projects.create("Building permit")
            await area.projects.set_member(project.project_id, editor.id, Role.EDITOR)
            fields = _version(title="Floor plan", size_in_bytes=len(content))
            LocalStorage(settings.data_dir).write_bytes(fields["storage_key"], content)
            made = await area.documents.create_version(project_id=project.project_id, document_id=None, **fields)
            _, token = await area.selections.create(
                user_id=editor.id,
                callback_url="http://localhost:9/callback",
                callback_expires_in=300,
                server_context=None,
                extensions=[],
            )
            return made.document_id, token
        finally:
            await postgres.close()

    document_id, token = asyncio.run(seed())
    apart = settings.model_copy(
        update={"store_url": postgres_target.url, "store_password": SecretStr(postgres_target.password)}
    )
    with TestClient(create_app(apart, startup_wait_seconds=30)) as client:
        page = client.get("/signin")
        signed_in = client.post(
            "/signin",
            data={"form_token": form_token(page.text), "username": "editor", "password": PASSWORD},
            follow_redirects=False,
        )
        assert signed_in.status_code == 302, signed_in.text
        details = client.get(f"/documents/1.0/documents/{document_id}/versions/1/details")
        assert details.status_code == 200 and "Floor plan" in details.text
        download = client.get(f"/documents/1.0/documents/{document_id}/versions/1/details/download")
        assert download.status_code == 200 and download.content == content
        assert client.get(f"/documents/1.0/documents/{document_id}/versions/2/details").status_code == 404
        selection = client.get(f"/documents/1.0/select-ui/{token}")
        assert selection.status_code == 200 and "Floor plan" in selection.text
    with GraphDatabase.driver(graph_target.uri, auth=(graph_target.user, graph_target.password)) as driver:
        records, _, _ = driver.execute_query(
            "MATCH (n) WHERE n:Document OR n:DocumentVersion OR n:SelectionSession RETURN count(n) AS n",
            database_=settings.database_name,
        )
    assert records[0]["n"] == 0, "the graph holds no document"
