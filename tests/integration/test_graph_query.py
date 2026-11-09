# This file was generated with the assistance of an AI coding tool.
"""The read-only graph query for administrators: the JSON shapes, the fences and the audit trail."""

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from httpx import Response

from opencde.settings import GraphDialect, Settings
from tests.conftest import test_settings as make_settings
from tests.integration.conftest import GraphTarget
from tests.integration.conftest_accounts import World, build_world, login_as, login_with_scope

pytestmark = [pytest.mark.integration, pytest.mark.security]


@pytest.fixture
def settings(graph_target: GraphTarget, tmp_path: Path) -> Settings:
    """The integration settings with the graph query on and tight limits, so truncation and the clock show."""
    return make_settings(
        tmp_path,
        graph_dialect=graph_target.dialect,
        graph_uri=graph_target.uri,
        graph_user=graph_target.user,
        graph_password=graph_target.password,
        graph_connect_timeout_seconds=10.0,
        cleanup_interval_seconds=3600,
        graph_query_enabled=True,
        graph_query_max_rows=3,
        graph_query_timeout_seconds=1.0,
    )


@pytest.fixture
def world(settings: Settings, clean_database: None) -> World:
    return build_world(settings)


def query(client: TestClient, headers: dict[str, str], cypher: str, params: dict[str, Any] | None = None) -> Response:
    return client.post("/admin/api/graph/query", json={"cypher": cypher, "params": params or {}}, headers=headers)


def test_administrators_read_the_graph_as_json(client: TestClient, world: World, settings: Settings) -> None:
    admin = login_with_scope(client, world, "admin", "profile admin")
    h = admin.headers
    announced = client.get("/.well-known/dataregium").json()["extensions"]["graph_query"]
    assert announced == {"enabled": True, "url": "/admin/api/graph/query", "max_rows": 3, "timeout_seconds": 1.0}

    answer = query(
        client,
        h,
        "MATCH (u:User {username: $name})-[m:MEMBER_OF]->(p:Project) RETURN u, m, p, u.username AS name",
        {"name": "editor"},
    )
    assert answer.status_code == 200, answer.text
    body = answer.json()
    assert body["columns"] == ["u", "m", "p", "name"] and body["truncated"] is False and len(body["rows"]) == 1
    user, membership, project, name = body["rows"][0]
    assert name == "editor" and user["labels"] == ["User"] and user["identity"]
    assert user["properties"]["username"] == "editor" and "password_hash" not in user["properties"]
    assert membership["type"] == "MEMBER_OF" and membership["properties"]["role"] == "editor"
    assert membership["start"] == user["identity"] and membership["end"] == project["identity"]
    assert project["properties"]["project_id"] == world.project_id

    path = query(client, h, "MATCH path = (:User {username: 'editor'})-[:MEMBER_OF]->(:Project) RETURN path").json()
    walk = path["rows"][0][0]
    assert walk["length"] == 1 and [node["labels"] for node in walk["nodes"]] == [["User"], ["Project"]]
    assert walk["relationships"][0]["type"] == "MEMBER_OF"

    scalars = query(
        client,
        h,
        "RETURN 1 AS i, 1.5 AS f, 'x' AS s, true AS b, [1, 2] AS l, {a: 1} AS m, date('2026-01-01') AS d, null AS n",
    ).json()
    assert scalars["rows"] == [[1, 1.5, "x", True, [1, 2], {"a": 1}, "2026-01-01", None]]

    many = query(client, h, "MATCH (u:User) RETURN u.username ORDER BY u.username").json()
    assert len(many["rows"]) == 3 and many["truncated"] is True, "cut at max_rows and marked"

    if settings.graph_dialect is GraphDialect.NEO4J:  # Memgraph has no db.labels()
        labels = query(client, h, "CALL db.labels() YIELD label WITH label WHERE label = 'Project' RETURN label")
        assert labels.status_code == 200 and labels.json()["rows"] == [["Project"]]


def test_the_fences_hold(client: TestClient, world: World) -> None:
    admin = login_with_scope(client, world, "admin", "profile admin")
    h = admin.headers

    # Writing statements never reach the database.
    for statement in (
        "CREATE (n:Evil) RETURN n",
        "MATCH (u:User) SET u.disabled = true RETURN u",
        "MATCH (n) DETACH DELETE n",
        "CALL dbms.components() YIELD name RETURN name",
        "SHOW USERS",
    ):
        refused = query(client, h, statement)
        assert refused.status_code == 400 and refused.json()["code"] == "validation_error", statement
    assert query(client, h, "MATCH (n:Evil) RETURN count(n) AS n").json()["rows"] == [[0]]
    assert query(client, h, "MATCH (u:User {disabled: true}) RETURN count(u) AS n").json()["rows"] == [[0]]

    # Protected properties: named in the statement, named in a parameter, or reached by another route.
    assert query(client, h, "MATCH (u:User) RETURN u.password_hash").status_code == 400
    assert query(client, h, "MATCH (u:User) RETURN u[$key]", {"key": "password_hash"}).status_code == 400
    sneaky = query(client, h, "MATCH (u:User {username: 'admin'}) UNWIND keys(u) AS k RETURN k, u[k]")
    assert sneaky.status_code == 200 and "$argon2" not in sneaky.text, "a hash reaching the answer is redacted"
    whole = query(client, h, "MATCH (u:User {username: 'admin'}) RETURN properties(u) AS p").json()
    assert "username" in whole["rows"][0][0] and "password_hash" not in whole["rows"][0][0]

    # The database's own verdicts come back as 400 with its message; a slow statement is stopped.
    broken = query(client, h, "MATCH (n RETURN n")
    assert broken.status_code == 400 and "rejected the query" in broken.json()["message"]
    slow = query(
        client,
        h,
        "UNWIND range(1, 3000) AS a UNWIND range(1, 3000) AS b UNWIND range(1, 3000) AS c RETURN count(*) AS n",
    )
    assert slow.status_code == 400 and "time limit" in slow.json()["message"], slow.text
    assert query(client, h, "RETURN 1 AS n").json()["rows"] == [[1]], "the server is fine afterwards"

    # Everyone but administrators holding the scope.
    editor = login_with_scope(client, world, "editor", "profile admin")
    assert query(client, editor.headers, "RETURN 1").json()["code"] == "forbidden"
    assert query(client, login_as(client, world, "admin").headers, "RETURN 1").json()["code"] == "insufficient_scope"
    assert query(client, {}, "RETURN 1").json()["code"] == "unauthenticated"

    # Every call left a trace with the statement, never the parameters.
    events = client.get("/admin/api/audit", params={"type": "admin.graph.query"}, headers=h).json()["items"]
    assert len(events) >= 12 and all(event["details"]["statement"] for event in events)
    assert all("params" not in event["details"] and "password_hash" != event["details"].get("key") for event in events)
    assert any(event["details"].get("refused") for event in events)
    assert any(event["details"].get("failed") for event in events)
    assert any(event["details"].get("rows") is not None for event in events)
