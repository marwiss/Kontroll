# This file was generated with the assistance of an AI coding tool.
"""The rooms of each storey in the report of an upload and of a precheck, with OPENCDE_ROOMS_ENABLED on (F36 a, the
server makes the client's room check; F38 a, the rooms only warn): a small closed model, made with the app's write
tools, is one closed room of four external walls, beside the issues and never one of them."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from opencde.ifcgraph.ops import run
from opencde.main import create_app
from tests.integration.conftest import GraphTarget
from tests.integration.conftest_accounts import build_world, login_as
from tests.integration.test_ifc_precheck import wait_for
from tests.integration.test_ifc_validation import checked, settings_for, upload
from tests.integration.test_web_signin import web_sign_in
from tests.unit.test_ifc_ops import DOOR, FOUR_WALLS, STOREYS, new_model  # skips this module without IfcOpenShell

pytestmark = pytest.mark.integration
pytest.importorskip("shapely", reason="the ifc-lpg extra is not installed")


def closed_model(path: Path) -> list[str]:
    """Four walls with a door on the lower of two storeys, written to ``path``; the walls' GlobalIds."""
    model = new_model()
    answer = run(model, [STOREYS, *FOUR_WALLS, DOOR], proposer="anna")
    assert answer["failed"] is None, answer
    model.write(str(path))
    return sorted(answer["created"][ref] for ref in ("new-1", "new-2", "new-3", "new-4"))


def lower_storey(report: dict[str, Any]) -> dict[str, Any]:
    (storey,) = [storey for storey in report["rooms"]["storeys"] if storey["storey"] == "Level 1"]
    return storey


def test_an_upload_and_a_precheck_report_the_rooms_beside_their_issues(
    graph_target: GraphTarget, clean_database: None, tmp_path: Path
) -> None:
    settings = settings_for(graph_target, tmp_path, rooms_enabled=True)
    world = build_world(settings)
    file = tmp_path / "box.ifc"
    walls = closed_model(file)
    with TestClient(create_app(settings, startup_wait_seconds=30)) as client:
        editor = login_as(client, world, "editor")
        web_sign_in(client, world, "editor")
        announced = client.get("/.well-known/dataregium").json()["extensions"]["ifc_validation"]
        assert announced["rooms"] is True

        version = upload(client, world, editor, "box.ifc", file.read_bytes())
        entries = checked(client, editor, version)
        assert entries["ifc_validation_status"] != ["issues"], "the rooms are no issue"
        body = client.get(entries["ifc_validation_report"][0], headers=editor.headers).json()
        assert body["error_count"] == 0 and all(check["name"] != "rooms" for check in body["checks"])
        storey = lower_storey(body)
        assert storey["closed"] is True and storey["walls"] == 4 and storey["dangles"] == []
        (room,) = storey["rooms"]
        assert (room["index"], room["area"], room["perimeter"], room["walls"]) == (1, 60.0, 32.0, walls)
        assert {wall["global_id"] for wall in storey["external"]} == set(walls)
        assert [wall["facing"] for wall in storey["external"]] == ["N", "E", "S", "W"], "in the order of the compass"
        page = client.get(version["links"]["document_details"]["url"], headers={"Accept-Language": "en"})
        assert page.status_code == 200 and "<h2>Rooms</h2>" in page.text and "<td>Level 1</td>" in page.text

        # The same file checked first: the precheck's report has the same rooms.
        base = f"/documents/1.0/projects/{world.project_id}/ifc-precheck"
        as_ifc = {"Content-Disposition": 'attachment; filename="box.ifc"'}
        started = client.post(base, content=file.read_bytes(), headers={**editor.headers, **as_ifc})
        assert started.status_code == 202, started.text
        report = wait_for(client, editor, started.json()["url"])
        assert report["error_count"] == 0 and lower_storey(report) == storey


def test_without_the_setting_the_report_has_no_rooms(
    graph_target: GraphTarget, clean_database: None, tmp_path: Path
) -> None:
    settings = settings_for(graph_target, tmp_path)
    world = build_world(settings)
    file = tmp_path / "box.ifc"
    closed_model(file)
    with TestClient(create_app(settings, startup_wait_seconds=30)) as client:
        editor = login_as(client, world, "editor")
        version = upload(client, world, editor, "box.ifc", file.read_bytes())
        entries = checked(client, editor, version)
        body = client.get(entries["ifc_validation_report"][0], headers=editor.headers).json()
        assert "rooms" not in body, "off unless the operator turns it on"
