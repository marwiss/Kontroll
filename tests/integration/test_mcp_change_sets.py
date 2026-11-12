# This file was generated with the assistance of an AI coding tool.
"""A change set made through the MCP endpoint against a real database and the IFC-DB module (ADR 0028, step 2):
an editor's AI opens a draft on an uploaded model, adds a wall and a door in it with Dataspatium's write tools,
proposes it, and reads the trial: clean, with the GlobalIds of what the operations made by their refs. Proposed
again with the same handle, the change set goes on the same topic; the draft expires and the cleaner takes it.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from opencde.bootstrap import make_graph
from opencde.graph.cleanup import delete_expired
from opencde.main import create_app
from opencde.settings import Settings
from opencde.store.accounts.projects import ProjectRepository
from tests.integration.conftest import GraphTarget
from tests.integration.conftest_accounts import World, build_world, login_as
from tests.integration.helpers import Session, authorize, exchange
from tests.integration.test_ifc_validation import MODEL, checked, settings_for, upload
from tests.integration.test_web_signin import web_sign_in
from tests.mcp_support import META, MODERN

pytestmark = [pytest.mark.integration, pytest.mark.security]
pytest.importorskip("ifcopenshell", reason="the ifc-db extra is not installed")

RESOURCE = "http://testserver/mcp"
WALL = {"storey": None, "start": [0, 0], "end": [4, 0], "thickness": 0.2, "height": 3, "name": "New wall",
        "type": None, "partition": None, "load_bearing": None, "status": None}  # fmt: skip
DOOR = {"wall_id": "new-1", "offset": 1, "width": 0.9, "height": 2.1, "sill": 0, "fill": "door", "name": None,
        "type": None, "side": None}  # fmt: skip


async def _cloud(settings: Settings, project_id: str) -> None:
    graph = make_graph(settings)
    try:
        await ProjectRepository(graph).set_ai_policy(project_id, "cloud")
    finally:
        await graph.close()


@pytest.fixture
def mcp_client(graph_target: GraphTarget, clean_database: None, tmp_path: Any) -> Iterator[tuple[TestClient, World]]:
    settings = settings_for(graph_target, tmp_path, mcp_enabled=True)
    world = build_world(settings)
    asyncio.run(_cloud(settings, world.project_id))  # a team server serves the cloud projects (F29 a)
    with TestClient(create_app(settings, startup_wait_seconds=30)) as client:
        yield client, world


def _bound(client: TestClient, world: World, username: str, scope: str) -> Session:
    code, query, verifier = authorize(
        client,
        client_id=world.public_client_id,
        redirect_uri=world.redirect,
        username=username,
        password=world.password,
        scope=scope,
        resource=RESOURCE,
    )
    assert code, query
    return exchange(
        client, code=code, verifier=verifier, client_id=world.public_client_id, redirect_uri=world.redirect,
        resource=RESOURCE,
    )  # fmt: skip


def _tool(client: TestClient, session: Session, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    message = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments, "_meta": META},
    }
    sent = {**session.headers, "MCP-Protocol-Version": MODERN, "Mcp-Method": "tools/call", "Mcp-Name": name}
    answer = client.post("/mcp", json=message, headers=sent)
    assert answer.status_code == 200, answer.text
    return answer.json()["result"]


def _ok(result: dict[str, Any]) -> dict[str, Any]:
    assert result["isError"] is False, result["content"][0]["text"]
    return result["structuredContent"]


def _tried(client: TestClient, session: Session, project_id: str, topic_guid: str) -> dict[str, Any]:
    deadline = time.monotonic() + 300
    while True:
        asked = {"project_id": project_id, "topic_guid": topic_guid, "wait_seconds": 20}
        report = _ok(_tool(client, session, "get_proposal", asked))
        if report["state"] not in ("queued", "running"):
            return report
        assert time.monotonic() < deadline, "the trial did not finish in time"


def test_an_ai_proposes_a_wall_with_a_door_and_reads_a_clean_trial(mcp_client: tuple[TestClient, World]) -> None:
    client, world = mcp_client
    editor = login_as(client, world, "editor")
    web_sign_in(client, world, "editor")  # the upload page asks for a browser session
    version = upload(client, world, editor, "three_walls_gtin.ifc", MODEL.read_bytes())
    assert checked(client, editor, version)["ifc_validation_status"] == ["passed"]
    document_id = version["document_id"]
    ai = _bound(client, world, "editor", "mcp mcp:propose")

    opened = _ok(_tool(client, ai, "open_changeset", {"document_id": document_id, "version_index": None}))
    assert opened["base"] == {"document_id": document_id, "version_index": 1}
    handle = opened["changeset_id"]
    assert _ok(_tool(client, ai, "create_wall", {"changeset_id": handle, **WALL}))["ref"] == "new-1"
    assert _ok(_tool(client, ai, "create_opening", {"changeset_id": handle, **DOOR}))["ref"] == "new-2"
    asked = {"changeset_id": handle, "title": "A wall with a door", "description": None, "ai_model": "claude-test"}
    proposed = _ok(_tool(client, ai, "propose_changes", asked))
    assert proposed["project_id"] == world.project_id and proposed["state"] == "queued" and proposed["ops"] == 2

    report = _tried(client, ai, world.project_id, proposed["topic_guid"])
    assert report["state"] == "clean", report
    assert report["change_count"] == 2 and report["applied"] == 2
    assert list(report["created"]) == ["new-1", "new-2"], "the wall and the door, by their refs"
    rest = client.get(
        f"/bcf/3.0/projects/{world.project_id}/topics/{proposed['topic_guid']}/ifc-proposal", headers=editor.headers
    ).json()
    assert rest["created"] == report["created"] and rest["state"] == "clean", "the same trial as REST gives it"
    listed = _ok(_tool(client, ai, "list_proposals", {"document_id": document_id, "limit": None}))["proposals"]
    assert [(row["topic_guid"], row["title"]) for row in listed] == [(proposed["topic_guid"], "A wall with a door")]

    _ok(_tool(client, ai, "manage_changeset", {"changeset_id": handle, "action": "remove_last"}))
    again = _ok(_tool(client, ai, "propose_changes", asked))
    assert again["topic_guid"] == proposed["topic_guid"] and again["ops"] == 1, "a new snippet on the same topic"
    assert list(_tried(client, ai, world.project_id, again["topic_guid"])["created"]) == ["new-1"]

    reader = _bound(client, world, "contributor", "mcp mcp:propose")
    refused = _tool(client, reader, "open_changeset", {"document_id": document_id, "version_index": None})
    assert refused["isError"] is True and "editor or manager" in refused["content"][0]["text"]
    assert _tool(client, reader, "create_wall", {"changeset_id": handle, **WALL})["isError"] is True

    async def expire() -> int:
        """The draft's 24 hours run out, and the cleaner deletes it with what else has expired."""
        graph = make_graph(client.app.state.settings)  # ty: ignore[unresolved-attribute]
        try:
            await graph.run(
                "MATCH (d:ChangeSetDraft {changeset_id: $id}) SET d.expires_at = $past",
                id=handle,
                past="2000-01-01T00:00:00.000Z",
            )
            return await delete_expired(graph)
        finally:
            await graph.close()

    assert asyncio.run(expire()) >= 1
    gone = _tool(client, ai, "manage_changeset", {"changeset_id": handle, "action": "list"})
    assert gone["isError"] is True and "Open a new one" in gone["content"][0]["text"]
