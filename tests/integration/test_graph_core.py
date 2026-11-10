# This file was generated with the assistance of an AI coding tool.
"""Schema, cleanup and the account repositories against a real graph database."""

import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from neo4j.exceptions import ClientError as GraphClientError

from opencde.accounts.projects import ProjectRepository
from opencde.accounts.roles import Role
from opencde.accounts.users import AccountError, UserRepository
from opencde.admin.doctor import schema_check
from opencde.auth.clients import ClientError, ClientRepository
from opencde.documents.repository import DocumentRepository
from opencde.graph.cleanup import delete_expired
from opencde.graph.dialect import NEO4J
from opencde.graph.graph import Graph
from opencde.graph.schema import apply_schema
from opencde.ids import new_id
from opencde.seed import (
    SAMPLE_MODEL,
    SEED_COMMENT_GUID,
    SEED_DOCUMENT_ID,
    SEED_TOPIC_GUID,
    SEED_VIEWPOINT_GUID,
    SeedError,
    seed,
)
from opencde.storage import LocalStorage
from opencde.timeutil import later_iso
from tests.integration.conftest import GraphTarget

pytestmark = pytest.mark.integration


async def test_schema_is_idempotent_and_enforces_uniqueness(graph: Graph) -> None:
    assert await apply_schema(graph) == 0, "second application changes nothing"
    await graph.run("CREATE (:Project {project_id: 'p1', name: 'A', created_at: 'x'})")
    with pytest.raises(GraphClientError):  # Neo4j raises ConstraintError, Memgraph a generic ClientError
        await graph.run("CREATE (:Project {project_id: 'p1', name: 'B', created_at: 'x'})")


async def test_the_schema_can_be_applied_twice_at_once_on_an_empty_database(graph: Graph) -> None:
    """The server and `opencde seed` start together right after `docker compose up`: neither may fail."""
    if graph.dialect is not NEO4J:
        pytest.skip("dropping the whole schema by name is written for Neo4j")
    for row in await graph.run("SHOW CONSTRAINTS YIELD name"):
        await graph.run("DROP CONSTRAINT $name", name=row["name"])
    for row in await graph.run("SHOW INDEXES YIELD name, type WHERE type <> 'LOOKUP' RETURN name"):
        await graph.run("DROP INDEX $name", name=row["name"])
    await asyncio.gather(apply_schema(graph), apply_schema(graph), apply_schema(graph))
    assert await apply_schema(graph) == 0, "the schema is complete afterwards"


async def test_the_doctor_counts_the_constraints_on_both_products(graph: Graph) -> None:
    check = await schema_check(graph)
    assert check.ok, check.detail


def test_readyz_reports_dialect(client: TestClient, graph_target: GraphTarget) -> None:
    response = client.get("/readyz")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "graph": "ok",
        "dialect": graph_target.dialect.value,
        "workcopy": "none",
    }


async def test_expired_nodes_are_deleted_in_batches(graph: Graph) -> None:
    await graph.run(
        "UNWIND range(1, 1203) AS i CREATE (:AccessToken {token_hash: toString(i), expires_at: $past})",
        past=later_iso(-10),
    )
    await graph.run("CREATE (:AccessToken {token_hash: 'keep', expires_at: $future})", future=later_iso(3600))
    assert await delete_expired(graph) == 1203
    rows = await graph.run("MATCH (t:AccessToken) RETURN t.token_hash AS h")
    assert [row["h"] for row in rows] == ["keep"]


async def test_users_projects_and_roles(graph: Graph) -> None:
    users = UserRepository(graph)
    projects = ProjectRepository(graph)

    alice = await users.create("alice@example.test", "a-long-and-strong-passphrase", full_name="Alice")
    assert await users.authenticate("alice@example.test", "a-long-and-strong-passphrase") == alice
    assert await users.authenticate("alice@example.test", "wrong") is None
    assert await users.authenticate("nobody", "a-long-and-strong-passphrase") is None

    with pytest.raises(AccountError, match="taken"):
        await users.create("alice@example.test", "another-long-passphrase-123")
    with pytest.raises(AccountError, match="password rejected"):
        await users.create("bob", "short")
    with pytest.raises(AccountError, match="user name"):
        await users.create("bad name!", "a-long-and-strong-passphrase")

    project = await projects.create("Building permit")
    assert await users.project_role(alice.id, project.project_id) is None
    await projects.set_member(project.project_id, alice.id, Role.EDITOR)
    assert await users.project_role(alice.id, project.project_id) is Role.EDITOR
    await projects.set_member(project.project_id, alice.id, Role.MANAGER)
    assert await users.memberships(alice.id) == [(project.project_id, "Building permit", Role.MANAGER)]
    assert [p.project_id for p, _ in await projects.list_for_user(alice.id)] == [project.project_id]

    extensions = await projects.extensions(project.project_id)
    assert extensions is not None
    assert extensions["users"] == ["alice@example.test"]
    assert "Open" in extensions["topic_status"]
    updated = await projects.set_extensions(project.project_id, {"topic_status": ["Open", "Closed", "Open"]})
    assert updated["topic_status"] == ["Open", "Closed"]
    with pytest.raises(AccountError, match="unknown extension"):
        await projects.set_extensions(project.project_id, {"colour": ["red"]})

    await users.update(alice.id, disabled=True)
    assert await users.authenticate("alice@example.test", "a-long-and-strong-passphrase") is None
    assert [u.username for u in await users.search(query="ALICE")] == ["alice@example.test"]

    assert await projects.remove_member(project.project_id, alice.id) is True
    assert await projects.members(project.project_id) == []
    assert await projects.delete(project.project_id) is True
    assert await projects.get(project.project_id) is None
    assert await projects.all() == []


async def test_deleting_a_project_keeps_its_people_and_their_other_projects(graph: Graph) -> None:
    """Topics and versions point at the users who made them, and users at all their projects.

    So deleting a project follows only what the project owns: the people in it, the other projects they are in and
    the files of those projects stay.
    """
    users = UserRepository(graph)
    projects = ProjectRepository(graph)
    documents = DocumentRepository(graph)
    alice = await users.create("alice@example.test", "a-long-and-strong-passphrase")
    doomed = await projects.create("Doomed")
    kept = await projects.create("Kept")
    document_ids = {}
    for project in (doomed, kept):
        await projects.set_member(project.project_id, alice.id, Role.EDITOR)
        version = await documents.create_version(
            project_id=project.project_id,
            document_id=None,
            title="Plan",
            version_number="1",
            file_name="plan.pdf",
            size_in_bytes=1,
            sha256="0" * 64,
            storage_key=f"documents/{project.project_id}",
            author=alice.username,
            metadata=[],
        )
        document_ids[project.project_id] = version.document_id
        await graph.run(
            """
            MATCH (p:Project {project_id: $project_id}), (u:User {id: $user_id})
            CREATE (p)-[:HAS_TOPIC]->(:Topic {guid: $guid, snippet_storage_key: $snippet})-[:CREATED_BY]->(u)
            """,
            project_id=project.project_id,
            user_id=alice.id,
            guid=new_id(),
            snippet=f"snippets/{project.project_id}.bin",
        )

    keys = sorted(await projects.storage_keys(doomed.project_id))  # what the administration deletes from the disk
    assert await projects.delete(doomed.project_id) is True

    assert await users.get(alice.id) is not None
    assert await users.memberships(alice.id) == [(kept.project_id, "Kept", Role.EDITOR)]
    assert await documents.latest(user_id=alice.id, document_id=document_ids[kept.project_id]) is not None
    rows = await graph.run(
        "MATCH (:Project {project_id: $id})-[:HAS_TOPIC]->(t:Topic)-[:CREATED_BY]->(:User) RETURN count(t) AS n",
        id=kept.project_id,
    )
    assert rows[0]["n"] == 1
    rows = await graph.run("MATCH (n) WHERE n:Document OR n:DocumentVersion OR n:Topic RETURN count(n) AS n")
    assert rows[0]["n"] == 3, "the deleted project's document, version and topic are gone, the kept one's are not"
    assert keys == [f"documents/{doomed.project_id}", f"snippets/{doomed.project_id}.bin"]


async def test_clients_secrets_and_redirects(graph: Graph) -> None:
    clients = ClientRepository(graph)
    confidential, secret = await clients.create("Server app", ["https://app.example.test/cb"], public=False)
    assert secret is not None and len(secret) >= 40
    assert await clients.authenticate(confidential.client_id, secret) == confidential
    assert await clients.authenticate(confidential.client_id, "wrong") is None
    assert await clients.authenticate(confidential.client_id, None) is None
    assert await clients.authenticate("00000000-0000-4000-8000-000000000000", secret) is None

    public, none = await clients.create("Native app", ["http://127.0.0.1/cb", "myapp://callback"], public=True)
    assert none is None
    assert await clients.authenticate(public.client_id, None) == public
    assert await clients.authenticate(public.client_id, "anything") is None, "public clients never present a secret"

    with pytest.raises(ClientError, match="loopback"):
        await clients.create("Bad", ["http://example.test/cb"], public=True)
    with pytest.raises(ClientError, match="fragment"):
        await clients.create("Bad", ["https://example.test/cb#frag"], public=True)
    with pytest.raises(ClientError, match="unsafe"):
        await clients.create("Bad", ["javascript:alert(1)"], public=True)

    rotated = await clients.rotate_secret(confidential.client_id)
    assert await clients.authenticate(confidential.client_id, secret) is None
    assert await clients.authenticate(confidential.client_id, rotated) is not None

    await clients.update(confidential.client_id, disabled=True)
    assert await clients.authenticate(confidential.client_id, rotated) is None
    assert len(await clients.all()) == 2
    assert await clients.delete(confidential.client_id) is True
    assert await clients.get(confidential.client_id) is None


async def test_seed_only_fills_an_empty_database(graph: Graph, tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path / "storage")
    result = await seed(graph, storage=storage, shared_password="demo-passphrase-for-tests")
    assert set(result.passwords) == {"admin", "officer", "developer", "inspection_manager", "inspector"}
    assert set(result.projects) == {"Building permit", "Demolition permit"}
    assert result.confidential_client_secret
    users = UserRepository(graph)
    officer = await users.get_by_username("officer")
    assert officer is not None
    assert len(await users.memberships(officer.id)) == 2

    # The sample model and a topic with a viewpoint and a comment, all with the ids clients rely on.
    content = await graph.one(
        """
        MATCH (p:Project {project_id: $project_id})-[:HAS_DOCUMENT]->(d:Document)-[:HAS_VERSION]->(v:DocumentVersion),
              (p)-[:HAS_TOPIC]->(t:Topic)
        OPTIONAL MATCH (t)-[:HAS_VIEWPOINT]->(vp:Viewpoint)
        OPTIONAL MATCH (t)-[:HAS_COMMENT]->(c:Comment)
        RETURN d.document_id AS document, v.file_name AS file_name, v.sha256 AS sha256, t.guid AS topic,
               t.server_assigned_id AS assigned, collect(DISTINCT vp.guid) AS viewpoints, collect(DISTINCT c.guid) AS comments
        """,
        project_id=result.projects["Building permit"],
    )
    assert content is not None
    assert content["document"] == SEED_DOCUMENT_ID and content["file_name"] == "three_walls_gtin.ifc"
    assert content["topic"] == SEED_TOPIC_GUID and content["assigned"] == "ISSUE-0001"
    assert content["viewpoints"] == [SEED_VIEWPOINT_GUID] and content["comments"] == [SEED_COMMENT_GUID]
    stored = next((tmp_path / "storage" / "documents").iterdir())
    assert stored.read_bytes() == SAMPLE_MODEL.read_bytes()
    with pytest.raises(SeedError):
        await seed(graph, storage=storage)


async def test_deleting_the_sample_project_takes_what_it_owns_and_nothing_else(graph: Graph, tmp_path: Path) -> None:
    result = await seed(graph, storage=LocalStorage(tmp_path / "storage"), shared_password="demo-passphrase-for-tests")
    projects = ProjectRepository(graph)
    users = UserRepository(graph)
    doomed, kept = result.projects["Building permit"], result.projects["Demolition permit"]
    assert await projects.storage_keys(doomed), "the sample model is a stored file of the project"
    assert await projects.storage_keys(kept) == []

    assert await projects.delete(doomed) is True

    rows = await graph.run("MATCH (n) UNWIND labels(n) AS label RETURN label, count(*) AS n")
    counts = {row["label"]: int(row["n"]) for row in rows}
    assert counts["User"] == 5 and counts["Project"] == 1
    owned = ("Topic", "Event", "Comment", "Viewpoint", "Component", "Bitmap", "FileRef", "DocumentReference")
    assert [label for label in (*owned, "Document", "DocumentVersion", "BcfDocument") if label in counts] == []
    officer = await users.get_by_username("officer")
    assert officer is not None
    assert [project_id for project_id, _, _ in await users.memberships(officer.id)] == [kept]
