# This file was generated with the assistance of an AI coding tool.
"""``server_query`` and ``get_publication`` through the MCP endpoint on a converted model, against Neo4j and Memgraph
(ADR 0028): the listing, the queries and ``changed-since`` as the REST routes answer them, a publication as
``GET …/publication`` gives it without its address, a stranger given nothing, and a project whose policy is local
refused on a team server into the audit log (F29 a).
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from neo4j import GraphDatabase

from opencde.bootstrap import make_graph
from opencde.ifcgraph.queries import QUERIES
from opencde.main import create_app
from opencde.settings import Settings
from opencde.store.accounts.projects import ProjectRepository
from tests.conftest import FIXTURES_DIR
from tests.integration.conftest import GraphTarget
from tests.integration.conftest_accounts import World, build_world, login_as
from tests.integration.helpers import Session, authorize, exchange
from tests.integration.test_ifc_queries import WALLS, converted, queries_url
from tests.integration.test_ifc_validation import MODEL, checked, settings_for, upload
from tests.integration.test_web_signin import web_sign_in
from tests.mcp_support import META, MODERN

pytestmark = [pytest.mark.integration, pytest.mark.security]
pytest.importorskip("ifcopenshell", reason="the ifc-lpg extra is not installed")

NOTHING = {"name": None, "class": None, "pset": None, "property": None, "global_id": None, "since": None}


async def set_policy(settings: Settings, project_id: str, ai_policy: str) -> None:
    graph = make_graph(settings)
    try:
        await ProjectRepository(graph).set_ai_policy(project_id, ai_policy)
    finally:
        await graph.close()


@pytest.fixture
def mcp_settings(graph_target: GraphTarget, tmp_path: Any) -> Settings:
    return settings_for(graph_target, tmp_path, mcp_enabled=True)


@pytest.fixture
def mcp_client(mcp_settings: Settings, clean_database: None) -> Iterator[tuple[TestClient, World]]:
    """The endpoint on a team server, whose one project of the member's has the policy cloud."""
    world = build_world(mcp_settings)
    asyncio.run(set_policy(mcp_settings, world.project_id, "cloud"))
    with TestClient(create_app(mcp_settings, startup_wait_seconds=30)) as client:
        yield client, world


def bound(client: TestClient, world: World, username: str) -> Session:
    """A token for the endpoint, with the scope ``mcp``, as an AI program signs the person in."""
    resource = "http://testserver/mcp"
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


def tool(client: TestClient, session: Session, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
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


def ask(client: TestClient, session: Session, version: dict[str, Any], **arguments: Any) -> dict[str, Any]:
    given = {"document_id": version["document_id"], "version_index": version["version_index"], **NOTHING}
    return tool(client, session, "server_query", given | arguments)


def answered(result: dict[str, Any]) -> dict[str, Any]:
    assert result["isError"] is False, result["content"][0]["text"]
    return result["structuredContent"]


def rows_of(answer: dict[str, Any]) -> list[dict[str, Any]]:
    return [dict(zip(answer["columns"], row, strict=True)) for row in answer["rows"]]


def test_a_member_asks_a_converted_model_as_the_routes_answer(mcp_client: tuple[TestClient, World]) -> None:
    client, world = mcp_client
    editor = login_as(client, world, "editor")
    web_sign_in(client, world, "editor")  # the upload page asks for a browser session
    walls = upload(client, world, editor, "three_walls_gtin.ifc", (FIXTURES_DIR / "three_walls_gtin.ifc").read_bytes())
    rest = converted(client, editor, walls)
    assert rest["model_state"] == "done"
    ai = bound(client, world, "viewer")

    listing = answered(ask(client, ai, walls))
    assert listing["model_state"] == "done" and listing["max_rows"] == 500
    assert listing["queries"] == rest["queries"] and listing["workcopy"] == rest["workcopy"], "the REST listing"
    assert [query["name"] for query in listing["queries"]] == [*QUERIES, "changed-since"]

    classes = answered(ask(client, ai, walls, name="element-classes"))
    assert {row["class"]: row["count"] for row in rows_of(classes)}["IfcWallStandardCase"] == 3
    elements = answered(ask(client, ai, walls, name="elements", **{"class": "IfcWall"}))
    assert {row["global_id"] for row in rows_of(elements)} == WALLS and elements["count"] == 3
    through_rest = client.get(f"{queries_url(walls)}/elements", params={"class": "IfcWall"}, headers=editor.headers)
    assert elements["rows"] == through_rest.json()["rows"] and elements["truncated"] is False
    latest = answered(ask(client, ai, walls | {"version_index": None}, name="storeys"))
    assert [row["name"] for row in rows_of(latest)] == ["1. etasje"], "null asks the latest version"
    (wall,) = rows_of(answered(ask(client, ai, walls, name="entity", global_id="1Xezbq735AdBO_4DerG66G")))
    assert wall["step_id"] == 242 and wall["attributes"]["Name"] == "YVT-A"
    gtin = rows_of(answered(ask(client, ai, walls, name="property", pset="Reuse", property="GTIN")))
    assert sorted(row["value"] for row in gtin) == ["1", "2", "3"]
    changes = answered(ask(client, ai, walls, name="changed-since", since=0))
    assert changes["rows"] == [[1, None, "editor", None, True, None, None, None, None, None]]

    refused = ask(client, ai, walls, name="elements")
    assert refused["isError"] is True and refused["content"][0]["text"] == "elements needs the parameter class"
    later = ask(client, ai, walls, name="changed-since", since=1)
    assert later["content"][0]["text"] == "since must be an earlier version than this one"


def test_a_publication_is_given_without_its_address(mcp_client: tuple[TestClient, World]) -> None:
    client, world = mcp_client
    editor = login_as(client, world, "editor")
    web_sign_in(client, world, "editor")  # the upload page asks for a browser session
    manager = login_as(client, world, "manager")
    version = upload(client, world, editor, "three_walls.ifc", MODEL.read_bytes())
    checked(client, editor, version)
    ai = bound(client, world, "viewer")
    where = {"document_id": version["document_id"], "version_index": version["version_index"]}
    assert answered(tool(client, ai, "get_publication", where))["published"] is False
    made = client.post(version["links"]["document_version"]["url"] + "/publication", headers=manager.headers)
    assert made.status_code == 201, made.text
    published = answered(tool(client, ai, "get_publication", where))
    assert published == {"published": True} | {
        key: value for key, value in made.json().items() if key != "download_url"
    }
    assert "download" not in str(published)


def _denials(settings: Settings) -> list[dict[str, Any]]:
    password = settings.graph_password.get_secret_value()
    with GraphDatabase.driver(settings.graph_uri, auth=(settings.graph_user, password)) as driver:
        rows, _, _ = driver.execute_query(
            "MATCH (e:AuditEvent {type: 'mcp.denied'}) RETURN e.actor_user_id AS actor, e.details AS details",
            database_=settings.database_name,
        )
    return [dict(row) for row in rows]


def test_a_stranger_gets_nothing_and_a_local_project_is_refused(
    mcp_client: tuple[TestClient, World], mcp_settings: Settings
) -> None:
    client, world = mcp_client
    settings = mcp_settings
    editor = login_as(client, world, "editor")
    web_sign_in(client, world, "editor")  # the upload page asks for a browser session
    walls = upload(client, world, editor, "three_walls_gtin.ifc", (FIXTURES_DIR / "three_walls_gtin.ifc").read_bytes())
    converted(client, editor, walls)
    stranger = ask(client, bound(client, world, "outsider"), walls, name="storeys")
    assert stranger["content"][0]["text"] == "There is no such document version among your projects"
    assert not _denials(settings)

    asyncio.run(set_policy(settings, world.project_id, "local"))
    ai = bound(client, world, "editor")
    for name, arguments in (
        ("server_query", {"document_id": walls["document_id"], "version_index": None, **NOTHING}),
        ("get_publication", {"document_id": walls["document_id"], "version_index": walls["version_index"]}),
    ):
        refused = tool(client, ai, name, arguments)
        assert refused["isError"] is True and "local only" in refused["content"][0]["text"], name
    denials = _denials(settings)
    assert len(denials) == 2 and all(denial["actor"] == world.users["editor"] for denial in denials)
    assert all(
        '"reason": "policy"' in denial["details"] and world.project_id in denial["details"] for denial in denials
    )
