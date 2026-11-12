# This file was generated with the assistance of an AI coding tool.
"""``list_models`` through the MCP endpoint against a real database (ADR 0028): the IFC documents of a member's
projects with the latest version and its model's conversion, a project outside the member's not there, and the AI
policy kept where the data goes (F29 a): a team server lists a ``local`` project not at all and refuses it by its id
into the audit log, and the local engine serves every project.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import pytest
from fastapi.testclient import TestClient
from neo4j import GraphDatabase

from opencde.accounts.roles import Role
from opencde.bootstrap import make_graph
from opencde.main import create_app
from opencde.settings import Settings
from opencde.store.accounts.projects import ProjectRepository
from opencde.store.documents.versions import DocumentRepository
from opencde.store.jobs.conversions import STATE_DONE, STATE_RUNNING, ConversionRepository
from tests.integration.conftest_accounts import World, build_world
from tests.integration.helpers import Session, authorize, exchange
from tests.mcp_support import META, MODERN

pytestmark = [pytest.mark.integration, pytest.mark.security]

LOOPBACK = "http://127.0.0.1:8000"


@dataclass(frozen=True)
class Models:
    walls: str
    slab: str
    old: str
    local_project: str


@pytest.fixture
def settings(settings: Settings) -> Settings:
    return settings.model_copy(update={"mcp_enabled": True})


@pytest.fixture
def world(settings: Settings, clean_database: None) -> World:
    return build_world(settings)


async def _version(documents: DocumentRepository, project_id: str, title: str, file_name: str, doc: str | None):
    return await documents.create_version(
        project_id=project_id,
        document_id=doc,
        title=title,
        version_number="",
        file_name=file_name,
        size_in_bytes=1,
        sha256="0" * 64,
        storage_key=f"documents/{title}-{file_name}",
        author="editor",
        metadata=[],
    )


async def _models(settings: Settings, world: World) -> Models:
    """In the editor's project (made cloud): walls in two versions with a model each, a slab whose model is under way,
    a model of old without one and a plan that is no model; a model in a local project of the editor's, and one in
    a project the editor is not in."""
    graph = make_graph(settings)
    try:
        documents, conversions, projects = (
            DocumentRepository(graph),
            ConversionRepository(graph),
            ProjectRepository(graph),
        )
        await projects.set_ai_policy(world.project_id, "cloud")
        walls = await _version(documents, world.project_id, "Walls", "walls.ifc", None)
        newer = await _version(documents, world.project_id, "Walls", "walls.ifc", walls.document_id)
        slab = await _version(documents, world.project_id, "Slab", "slab.ifczip", None)
        old = await _version(documents, world.project_id, "Old model", "old.IFC", None)
        await _version(documents, world.project_id, "Plan", "plan.pdf", None)
        local = await projects.create("Local project")
        await projects.set_member(local.project_id, world.users["editor"], Role.EDITOR)
        await _version(documents, local.project_id, "Local walls", "local.ifc", None)
        await _version(documents, world.other_project_id, "Elsewhere", "elsewhere.ifc", None)
        for version, state, schema in (
            (walls, STATE_DONE, "IFC2X3"),
            (newer, STATE_DONE, "IFC4"),
            (slab, STATE_RUNNING, None),
        ):
            model_id = f"model-{version.version_id}"
            await conversions.create(
                project_id=world.project_id,
                model_id=model_id,
                file_name=version.file_name,
                storage_key=version.storage_key,
                document_id=version.document_id,
                version_index=version.version_index,
            )
            await conversions.set_state(model_id, state, **({"schema": schema} if schema else {}))
        return Models(walls.document_id, slab.document_id, old.document_id, local.project_id)
    finally:
        await graph.close()


@pytest.fixture
def models(settings: Settings, world: World) -> Models:
    return asyncio.run(_models(settings, world))


def _bound(client: TestClient, world: World, username: str, resource: str) -> Session:
    code, query, verifier = authorize(
        client,
        client_id=world.public_client_id,
        redirect_uri=world.redirect,
        username=username,
        password=world.password,
        scope="mcp",
        resource=resource,
    )
    assert code, query
    return exchange(
        client,
        code=code,
        verifier=verifier,
        client_id=world.public_client_id,
        redirect_uri=world.redirect,
        resource=resource,
    )


def _list(client: TestClient, session: Session, project_id: str | None) -> dict[str, Any]:
    message = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": "list_models", "arguments": {"project_id": project_id}, "_meta": META},
    }
    sent = {**session.headers, "MCP-Protocol-Version": MODERN, "Mcp-Method": "tools/call", "Mcp-Name": "list_models"}
    answer = client.post("/mcp", json=message, headers=sent)
    assert answer.status_code == 200, answer.text
    return answer.json()["result"]


def _denials(settings: Settings) -> list[dict[str, Any]]:
    password = settings.graph_password.get_secret_value()
    with GraphDatabase.driver(settings.graph_uri, auth=(settings.graph_user, password)) as driver:
        rows, _, _ = driver.execute_query(
            "MATCH (e:AuditEvent {type: 'mcp.denied'}) RETURN e.actor_user_id AS actor, e.details AS details",
            database_=settings.database_name,
        )
    return [dict(row) for row in rows]


def test_a_member_finds_the_models_of_the_cloud_projects_with_their_state(
    client: TestClient, world: World, models: Models, settings: Settings
) -> None:
    editor = _bound(client, world, "editor", "http://testserver/mcp")
    result = _list(client, editor, None)
    assert result["isError"] is False
    answer = result["structuredContent"]
    assert answer["truncated"] is False
    rows = [
        (row["title"], row["file_name"], row["version_index"], row["model_state"], row["schema"])
        for row in answer["models"]
    ]
    assert rows == [
        ("Old model", "old.IFC", 1, None, None),
        ("Slab", "slab.ifczip", 1, "running", None),
        ("Walls", "walls.ifc", 2, "done", "IFC4"),
    ], "the latest version and its own model; the plan is no model, and the local project is not listed"
    assert {row["project_id"] for row in answer["models"]} == {world.project_id}
    assert {(row["project_name"], row["role"], row["ai_policy"]) for row in answer["models"]} == {
        ("Building permit", "editor", "cloud")
    }
    assert {row["document_id"] for row in answer["models"]} == {models.walls, models.slab, models.old}
    viewer = _bound(client, world, "viewer", "http://testserver/mcp")
    assert {row["role"] for row in _list(client, viewer, world.project_id)["structuredContent"]["models"]} == {"viewer"}
    assert not _denials(settings)


def test_a_local_project_is_refused_by_its_id_and_a_strangers_is_not_there(
    client: TestClient, world: World, models: Models, settings: Settings
) -> None:
    editor = _bound(client, world, "editor", "http://testserver/mcp")
    refused = _list(client, editor, models.local_project)
    assert refused["isError"] is True and "local only" in refused["content"][0]["text"]
    (denial,) = _denials(settings)
    assert denial["actor"] == world.users["editor"]
    assert '"reason": "policy"' in denial["details"] and models.local_project in denial["details"]
    stranger = _list(client, editor, world.other_project_id)
    assert stranger["isError"] is True and "no project with this id" in stranger["content"][0]["text"]
    outsider = _bound(client, world, "outsider", "http://testserver/mcp")
    assert _list(client, outsider, None)["structuredContent"]["models"] == [], "the outsider's project is local"


@pytest.fixture
def local_engine(settings: Settings, world: World, models: Models) -> Iterator[TestClient]:
    """The same database served by the local engine on the loopback."""
    local = settings.model_copy(update={"environment": "local", "public_url": LOOPBACK, "cors_origins": ["null"]})
    with TestClient(create_app(local, startup_wait_seconds=30), base_url=LOOPBACK) as engine:
        yield engine


def test_the_local_engine_serves_every_project_of_the_member(
    local_engine: TestClient, world: World, models: Models, settings: Settings
) -> None:
    editor = _bound(local_engine, world, "editor", f"{LOOPBACK}/mcp")
    everything = _list(local_engine, editor, None)["structuredContent"]["models"]
    assert [row["project_name"] for row in everything] == ["Building permit"] * 3 + ["Local project"]
    local = _list(local_engine, editor, models.local_project)
    assert local["isError"] is False and local["structuredContent"]["models"][0]["ai_policy"] == "local"
    assert not _denials(settings)
