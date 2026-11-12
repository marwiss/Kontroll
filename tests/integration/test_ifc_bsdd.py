# This file was generated with the assistance of an AI coding tool.
"""Checking an upload against buildingSMART's Data Dictionary (OB-42): the check ``bsdd`` in the report of a version,
with bSDD stubbed, so that no test reaches the network."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from opencde.ifcgraph.bsdd import BsddClient
from opencde.main import create_app
from tests.integration.conftest import GraphTarget
from tests.integration.conftest_accounts import build_world, login_as
from tests.integration.test_ifc_validation import checked, settings_for, upload
from tests.integration.test_web_signin import web_sign_in
from tests.unit.test_bsdd_refs import (  # skips this module without IfcOpenShell
    BSDD_IDS,
    FIRE_RATING,
    NOWHERE,
    model_with_property_uris,
    model_with_references,
)

pytestmark = pytest.mark.integration

IFC = "https://identifier.buildingsmart.org/uri/buildingsmart/ifc/4.3"
WALL = f"{IFC}/class/IfcWall"
SETS = {f"{IFC}/class/Pset_WallCommon": ["AcousticRating", "FireRating", "IsExternal", "LoadBearing"]}


def bsdd_answers(request: httpx.Request) -> httpx.Response:
    """bSDD's API as it answers: the IFC wall, the properties of Pset_WallCommon, and its 400 for what it does not
    know."""
    params = request.url.params
    if request.url.path == "/api/Class/Properties/v1":
        codes = SETS.get(params["ClassUri"], [])
        page = [{"propertyCode": code, "propertySet": "Pset_WallCommon"} for code in codes]
        return httpx.Response(200, json={"classProperties": page, "totalCount": len(codes), "offset": 0})
    if params["uri"] == WALL:
        return httpx.Response(200, json={"uri": WALL, "code": "IfcWall", "name": "Wall", "status": "Active"})
    words = {"message": f"Class with URI '{params['uri']}' not found", "uri": params["uri"], "statusCode": 400}
    return httpx.Response(400, json=words)


def bsdd_gone(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("no route to bSDD", request=request)


def uploaded_with_bsdd(
    graph_target: GraphTarget, tmp_path: Path, answers: Callable[[httpx.Request], httpx.Response]
) -> tuple[dict[str, Any], dict[str, Any], Any]:
    """An IFC 4.3 file with bSDD references uploaded with the check on, bSDD answering as ``answers`` does; the
    version, the file's ids and the report, once the file is checked."""
    settings = settings_for(graph_target, tmp_path, bsdd_enabled=True, bsdd_api_url="https://bsdd.test")
    world = build_world(settings)
    file = tmp_path / "refs.ifc"
    ids = model_with_references(file)
    with TestClient(create_app(settings, startup_wait_seconds=30)) as client:
        client.app.state.ifcgraph.bsdd = BsddClient("https://bsdd.test", transport=httpx.MockTransport(answers))  # type: ignore[attr-defined]
        editor = login_as(client, world, "editor")
        web_sign_in(client, world, "editor")
        version = upload(client, world, editor, "refs.ifc", file.read_bytes())
        entries = checked(client, editor, version)
        body = client.get(entries["ifc_validation_report"][0], headers=editor.headers).json()
        page = client.get(version["links"]["document_details"]["url"], headers={"Accept-Language": "en"})
        assert page.status_code == 200
    return {"entries": entries, "body": body, "page": page.text}, ids, version


def test_an_upload_is_checked_against_bsdd_and_the_report_warns_of_what_it_does_not_know(
    graph_target: GraphTarget, clean_database: None, tmp_path: Path
) -> None:
    found, ids, _ = uploaded_with_bsdd(graph_target, tmp_path, bsdd_answers)
    entries, body = found["entries"], found["body"]
    assert entries["ifc_validation_status"] == ["warnings"], "bSDD only warns"
    assert "bSDD at bsdd.test: buildingsmart/ifc/4.3, example/nosuch/1.0" in entries["ifc_validation_ruleset"]
    (check,) = [check for check in body["checks"] if check["name"] == "bsdd"]
    assert check["state"] == "done" and check.get("error") is None
    warnings = [issue for issue in body["issues"] if issue["kind"] == "bsdd"]
    assert check["issue_count"] == len(warnings) == 3 and all(issue["severity"] == "warning" for issue in warnings)
    by_attribute = {issue["attribute"]: issue for issue in warnings}
    assert set(by_attribute) == {"Location", "Pset_Custom", "Pset_WallCommon.Bogus"}, "Reference is left out"
    unknown = by_attribute["Location"]
    assert (unknown["rule"], unknown["step_id"], unknown["global_id"]) == (
        "example/nosuch/1.0",
        ids["unknown"],
        ids["door"],
    )
    assert NOWHERE in unknown["message"] and "IfcDoor" in unknown["message"]
    bogus = by_attribute["Pset_WallCommon.Bogus"]
    assert (bogus["rule"], bogus["step_id"], bogus["global_id"]) == ("buildingsmart/ifc/4.3", ids["pset"], ids["wall"])
    assert "no property set Pset_Custom" in by_attribute["Pset_Custom"]["message"]
    assert "bSDD: example/nosuch/1.0" in found["page"], "the version's page names the dictionary"


def test_when_bsdd_is_out_of_reach_the_check_fails_and_the_file_stands(
    graph_target: GraphTarget, clean_database: None, tmp_path: Path
) -> None:
    found, _, _ = uploaded_with_bsdd(graph_target, tmp_path, bsdd_gone)
    entries, body = found["entries"], found["body"]
    assert entries["ifc_validation_status"] == ["passed"], "bSDD out of reach is no error of the model"
    assert not any(ruleset.startswith("bSDD") for ruleset in entries["ifc_validation_ruleset"])
    (check,) = [check for check in body["checks"] if check["name"] == "bsdd"]
    assert (check["state"], check["issue_count"], check["ruleset"]) == ("failed", 0, "bSDD at bsdd.test")
    assert check["error"] == "bSDD at bsdd.test could not be reached: ConnectError"
    assert "bSDD at bsdd.test could not check the file." in found["page"]


def bsdd_knowing_fire_rating(request: httpx.Request) -> httpx.Response:
    """bSDD as ``bsdd_answers``, which also knows the IFC dictionary's FireRating."""
    if request.url.params.get("uri") == FIRE_RATING:
        return httpx.Response(200, json={"uri": FIRE_RATING, "code": "FireRating", "name": "Fire rating"})
    return bsdd_answers(request)


def test_the_properties_and_the_projects_ids_documents_are_checked_against_bsdd(
    graph_target: GraphTarget, clean_database: None, tmp_path: Path
) -> None:
    """A property's Specification that bSDD does not know warns with the property; a URI of the project's IDS
    document that it does not know warns with the document and its specification, in the report of the file."""
    settings = settings_for(graph_target, tmp_path, bsdd_enabled=True, bsdd_api_url="https://bsdd.test")
    world = build_world(settings)
    file = tmp_path / "props.ifc"
    ids = model_with_property_uris(file)
    with TestClient(create_app(settings, startup_wait_seconds=30)) as client:
        transport = httpx.MockTransport(bsdd_knowing_fire_rating)
        client.app.state.ifcgraph.bsdd = BsddClient("https://bsdd.test", transport=transport)  # type: ignore[attr-defined]
        editor = login_as(client, world, "editor")
        web_sign_in(client, world, "editor")
        document = upload(client, world, editor, "bsdd.ids", BSDD_IDS.read_bytes())
        version = upload(client, world, editor, "props.ifc", file.read_bytes())
        entries = checked(client, editor, version)
        body = client.get(entries["ifc_validation_report"][0], headers=editor.headers).json()
    assert any(check["name"] == "ids" and check["state"] == "done" for check in body["checks"])
    (made,) = [check for check in body["checks"] if check["name"] == "bsdd"]
    warnings = [issue for issue in body["issues"] if issue["kind"] == "bsdd"]
    assert made["state"] == "done" and made["issue_count"] == len(warnings) == 6
    assert all(issue["severity"] == "warning" for issue in warnings)
    of_the_file = {issue["attribute"]: issue for issue in warnings if "document_id" not in issue}
    assert set(of_the_file) == {"Custom.Bogus", "Pset_WallCommon.Note", "Pset_WallCommon.Class"}
    bogus = of_the_file["Custom.Bogus"]
    assert (bogus["rule"], bogus["step_id"], bogus["global_id"]) == ("example/nosuch/1.0", ids["bogus"], ids["door"])
    assert "names in its Specification" in bogus["message"] and "IfcDoor" in bogus["message"]
    of_the_ids = [issue for issue in warnings if "document_id" in issue]
    assert {issue["document_id"] for issue in of_the_ids} == {document["document_id"]}
    assert all("the IDS document 'bsdd.ids'" in issue["message"] for issue in of_the_ids)
    assert sorted(issue["message"].split("its specification ")[1].split("'")[1] for issue in of_the_ids) == [
        "Doors are classified",
        "Walls are classified",
        "Walls have a fire rating",
    ]
    assert all("step_id" not in issue and "global_id" not in issue for issue in of_the_ids), "nothing of the file"
    assert NOWHERE in of_the_ids[0]["message"]
