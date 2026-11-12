# This file was generated with the assistance of an AI coding tool.
"""``start_clash_check`` and ``get_clash_check`` through the MCP endpoint, against Neo4j and Memgraph (ADR 0028, ADR
0019): a member starts a check of two versions, waits for its report and finds what the REST route finds, the start is
in the audit log, and someone outside the project can neither start one nor read it.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient
from neo4j import GraphDatabase

from opencde.main import create_app
from opencde.settings import Settings
from tests.conftest import FIXTURES_DIR
from tests.integration.conftest import GraphTarget
from tests.integration.conftest_accounts import build_world, login_as
from tests.integration.helpers import Session
from tests.integration.test_ifc_clash import shifted_copy
from tests.integration.test_ifc_validation import settings_for, upload
from tests.integration.test_mcp_server_query import bound, set_policy, tool
from tests.integration.test_web_signin import web_sign_in

pytestmark = [pytest.mark.integration, pytest.mark.security]
pytest.importorskip("ifcclash", reason="the ifc-lpg extra is not installed")


def _events(settings: Settings, kind: str) -> list[dict[str, Any]]:
    password = settings.graph_password.get_secret_value()
    with GraphDatabase.driver(settings.graph_uri, auth=(settings.graph_user, password)) as driver:
        rows, _, _ = driver.execute_query(
            "MATCH (e:AuditEvent {type: $kind}) RETURN e.actor_user_id AS actor, e.details AS details",
            kind=kind,
            database_=settings.database_name,
        )
    return [dict(row) for row in rows]


def waited(client: TestClient, session: Session, project_id: str, clash_id: str) -> dict[str, Any]:
    """The report once the check is over, asked with the longest wait the tool takes."""
    deadline = time.monotonic() + 300
    while True:
        result = tool(
            client, session, "get_clash_check", {"project_id": project_id, "clash_id": clash_id, "wait_seconds": 20}
        )
        assert result["isError"] is False, result["content"][0]["text"]
        report = result["structuredContent"]
        if report["state"] in ("done", "failed"):
            return report
        assert time.monotonic() < deadline, "the clash check did not finish in time"


def test_a_member_starts_a_check_and_waits_for_its_report(
    graph_target: GraphTarget, clean_database: None, tmp_path: Any
) -> None:
    settings = settings_for(
        graph_target, tmp_path, mcp_enabled=True, ifcgraph_clash_enabled=True, ifcgraph_validate_uploads=False
    )
    world = build_world(settings)
    asyncio.run(set_policy(settings, world.project_id, "cloud"))
    with TestClient(create_app(settings, startup_wait_seconds=30)) as client:
        editor = login_as(client, world, "editor")
        web_sign_in(client, world, "editor")  # the upload page asks for a browser session
        original = upload(client, world, editor, "walls.ifc", (FIXTURES_DIR / "three_walls_gtin.ifc").read_bytes())
        moved = upload(client, world, editor, "walls-moved.ifc", shifted_copy())
        ai = bound(client, world, "viewer")
        arguments = {
            "project_id": world.project_id,
            "a": {"document_id": original["document_id"], "version_index": original["version_index"], "types": None},
            "b": {"document_id": moved["document_id"], "version_index": moved["version_index"], "types": ["IfcWall"]},
            "mode": None,
            "tolerance": None,
            "clearance": None,
        }

        started = tool(client, ai, "start_clash_check", arguments)
        assert started["isError"] is False, started["content"][0]["text"]
        clash_id = started["structuredContent"]["clash_id"]
        assert started["structuredContent"]["state"] == "queued"
        report = waited(client, ai, world.project_id, clash_id)
        assert report["state"] == "done", report["error"]
        assert report["count"] >= 1 and report["set_a"] == 3 and report["set_b"] == 3 and not report["truncated"]
        assert report["request"]["mode"] == "intersection" and report["request"]["tolerance"] == 0.001
        clash = report["clashes"][0]
        assert clash["kind"] == "intersection" and clash["depth"] > 0.001 and len(clash["point"]) == 3
        assert clash["a"]["document_id"] == original["document_id"] and clash["b"]["guid"] != clash["a"]["guid"]
        assert "url" not in report, "no address of the REST API"
        rest = client.get(f"/documents/1.0/projects/{world.project_id}/ifc-clash/{clash_id}", headers=editor.headers)
        assert rest.json()["clashes"] == report["clashes"], "the REST route's report"
        (event,) = _events(settings, "mcp.clash.started")
        assert event["actor"] == world.users["viewer"] and clash_id in event["details"]

        outsider = bound(client, world, "outsider")
        refused = tool(client, outsider, "start_clash_check", arguments)
        assert refused["content"][0]["text"] == "There is no project with this id among your projects"
        hidden = tool(
            client,
            outsider,
            "get_clash_check",
            {"project_id": world.project_id, "clash_id": clash_id, "wait_seconds": 0},
        )
        assert hidden["isError"] is True and "no project" in hidden["content"][0]["text"]


def test_the_tools_are_refused_where_the_check_is_off(
    graph_target: GraphTarget, clean_database: None, tmp_path: Any
) -> None:
    settings = settings_for(graph_target, tmp_path, mcp_enabled=True)
    world = build_world(settings)
    asyncio.run(set_policy(settings, world.project_id, "cloud"))
    with TestClient(create_app(settings, startup_wait_seconds=30)) as client:
        ai = bound(client, world, "editor")
        side = {"document_id": world.project_id, "version_index": 1, "types": None}
        given = {
            "project_id": world.project_id,
            "a": side,
            "b": side,
            "mode": None,
            "tolerance": None,
            "clearance": None,
        }
        refused = tool(client, ai, "start_clash_check", given)
    assert refused["isError"] is True and refused["content"][0]["text"] == "The clash check is off on this server"
    assert not _events(settings, "mcp.clash.started")
