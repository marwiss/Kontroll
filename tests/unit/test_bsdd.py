# This file was generated with the assistance of an AI coding tool.
"""Checking an upload against buildingSMART's Data Dictionary (OB-42), without the network: what a bSDD URI is, the
client against a stubbed bSDD that answers as bSDD's API does, the check on what the worker found, and the check in
the report of an upload. The worker itself is tried in ``test_bsdd_refs.py``, and the whole flow against a database
in ``tests/integration/test_ifc_bsdd.py``."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest
from ifc_lpg.validation import pack_report, unpack_report
from pydantic import ValidationError

from opencde.ids import new_id
from opencde.ifcgraph import bsdd as bsdd_module
from opencde.ifcgraph import service as service_module
from opencde.ifcgraph.bsdd import (
    IFC_DICTIONARY,
    BsddClient,
    BsddUnavailable,
    NotBsdd,
    _facet_words,
    check,
    class_uri,
    ifc_dictionary,
    parse_uri,
)
from opencde.ifcgraph.service import IfcGraphService, _issue_key, _made
from opencde.settings import Settings
from opencde.storage import LocalStorage, make_key
from tests.conftest import test_settings as make_settings  # aliased so pytest does not collect it as a test
from tests.unit.test_ifcgraph_service import LINE, SCHEMA_ANSWER, Graph, Log

IFC = "https://identifier.buildingsmart.org/uri/buildingsmart/ifc/4.3"
WALL = f"{IFC}/class/IfcWall"
FIRE_RATING = f"{IFC}/prop/FireRating"
WALL_COMMON = f"{IFC}/class/Pset_WallCommon"
NOWHERE = "https://identifier.buildingsmart.org/uri/example/nosuch/1.0/class/X"
BOGUS = "https://identifier.buildingsmart.org/uri/example/nosuch/1.0/prop/Bogus"
ELSEWHERE = "https://example.org/uri/example/nosuch/1.0/class/X"
DOOR = "2Ox9REZJX8xQXPdFCabqZL"
WALL_GUID = "3QaE2jy_91GAUd5Fq8oVjm"


def test_a_bsdd_uri_names_a_dictionary_and_a_class_or_property() -> None:
    wall = parse_uri(WALL)
    assert wall is not None and (wall.dictionary, wall.kind, wall.code) == (IFC_DICTIONARY, "class", "IfcWall")
    prop = parse_uri("HTTP://Identifier.buildingSMART.org/uri/buildingsmart/ifc/4.3/prop/FireRating/")
    assert prop is not None and prop.uri == FIRE_RATING and prop.kind == "prop", "http, the host's case, a slash"
    dictionary = parse_uri(" https://identifier.buildingsmart.org/uri/molio/cciconstruction/1.0 ")
    assert dictionary is not None and dictionary.kind is None and dictionary.dictionary == "molio/cciconstruction/1.0"
    assert class_uri(IFC_DICTIONARY, "Pset_WallCommon") == WALL_COMMON
    for other in (
        ELSEWHERE,
        "https://identifier.buildingsmart.org.example.org/uri/buildingsmart/ifc/4.3/class/IfcWall",
        "https://identifier.buildingsmart.org/other/x",
        "https://identifier.buildingsmart.org/uri/a/b/c/class/x/y",
        "https://identifier.buildingsmart.org/uri/a/b/c/thing/x",
        "https://identifier.buildingsmart.org/uri/a/b/c/class/x?then=elsewhere",
        "IfcWall",
        "",
        None,
        3,
    ):
        assert parse_uri(other) is None, other


def test_only_a_file_of_ifc_4_3_has_its_sets_checked_against_the_one_ifc_dictionary_bsdd_has() -> None:
    assert ifc_dictionary("IFC4X3") == ifc_dictionary("ifc4x3_add2") == IFC_DICTIONARY
    assert ifc_dictionary("IFC4") is None and ifc_dictionary("IFC2X3") is None and ifc_dictionary("") is None


class Bsdd:
    """bSDD's API as a transport: a script of statuses first (0 for a timeout), then the classes and properties it
    knows, the properties it lists for a class, and its 400 in its own words for a URI it does not know."""

    def __init__(
        self,
        known: dict[str, dict[str, Any]] | None = None,
        sets: dict[str, list[str]] | None = None,
        script: list[int] | None = None,
    ) -> None:
        self.known = known or {}
        self.sets = sets or {}
        self.script = list(script or [])
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.script:
            status = self.script.pop(0)
            if status == 0:
                raise httpx.ReadTimeout("too slow", request=request)
            headers = {"Retry-After": "2"} if status == 429 else {}
            return httpx.Response(status, json={"message": "later"}, headers=headers)
        params = request.url.params
        if request.url.path == "/api/Class/Properties/v1":
            codes = self.sets.get(params["ClassUri"], [])
            offset, limit = int(params["Offset"]), int(params["Limit"])
            page = [{"propertyCode": code, "propertySet": "Pset"} for code in codes[offset : offset + limit]]
            body = {"classUri": params["ClassUri"], "classProperties": page, "totalCount": len(codes)}
            return httpx.Response(200, json={**body, "offset": offset, "count": len(page)})
        uri = params["uri"]
        if uri in self.known:
            return httpx.Response(200, json=self.known[uri])
        words = "Class with URI" if request.url.path == "/api/Class/v1" else "Property with namespace URI"
        return httpx.Response(400, json={"message": f"{words} '{uri}' not found", "uri": uri, "statusCode": 400})


def client_for(bsdd: Bsdd, **options: Any) -> tuple[BsddClient, list[float]]:
    waits: list[float] = []

    async def sleep(seconds: float) -> None:
        waits.append(seconds)

    return BsddClient("https://bsdd.test", transport=httpx.MockTransport(bsdd), sleep=sleep, **options), waits


WALL_ANSWER = {"uri": WALL, "code": "IfcWall", "name": "Wall", "status": "Active", "definition": "A long text."}


async def test_the_client_asks_bsdd_as_its_api_wants_and_keeps_what_names_the_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(bsdd_module, "PAGE", 2)
    common = ["AcousticRating", "Combustible", "FireRating", "IsExternal", "LoadBearing"]
    bsdd = Bsdd({WALL: WALL_ANSWER, FIRE_RATING: {"code": "FireRating"}}, {WALL_COMMON: common})
    client, _ = client_for(bsdd)
    assert await client.lookup(WALL) == {"uri": WALL, "code": "IfcWall", "name": "Wall", "status": "Active"}
    assert await client.lookup(FIRE_RATING) == {"code": "FireRating"}
    assert await client.properties_of(WALL_COMMON) == frozenset(common), "every page"
    await client.aclose()
    wall, prop, *pages = bsdd.requests
    assert wall.url.path == "/api/Class/v1" and dict(wall.url.params) == {"uri": WALL}
    assert prop.url.path == "/api/Property/v5" and prop.url.params["uri"] == FIRE_RATING
    assert [(page.url.params["Offset"], page.url.params["Limit"]) for page in pages] == [
        ("0", "2"),
        ("2", "2"),
        ("4", "2"),
    ]
    assert all(page.url.path == "/api/Class/Properties/v1" for page in pages), "not the deprecated option"
    assert {request.url.host for request in bsdd.requests} == {"bsdd.test"} and client.host == "bsdd.test"
    assert wall.headers["user-agent"].startswith("Dataregium/") and wall.headers["accept"] == "application/json"


async def test_an_unknown_uri_is_none_and_what_is_not_bsdds_is_never_asked_about() -> None:
    bsdd = Bsdd()
    client, _ = client_for(bsdd)
    assert await client.lookup(NOWHERE) is None
    assert await client.lookup(f"{IFC}/prop/NoSuchProperty") is None
    assert await client.properties_of(f"{IFC}/class/Pset_NoSuchSet") == frozenset(), "bSDD lists nothing for it"
    for other in (ELSEWHERE, "https://identifier.buildingsmart.org/uri/molio/cciconstruction/1.0"):
        with pytest.raises(NotBsdd):
            await client.lookup(other)
    with pytest.raises(NotBsdd):
        await client.properties_of(FIRE_RATING)
    await client.aclose()
    assert [request.url.host for request in bsdd.requests] == ["bsdd.test"] * 3


async def test_a_5xx_or_a_429_is_retried_a_little_and_then_bsdd_is_out_of_reach() -> None:
    client, waits = client_for(Bsdd({WALL: WALL_ANSWER}, script=[503]))
    assert (await client.lookup(WALL) or {})["code"] == "IfcWall" and waits == [1.0]
    await client.aclose()
    throttling = Bsdd({WALL: WALL_ANSWER}, script=[429, 429, 429])
    client, waits = client_for(throttling)
    with pytest.raises(BsddUnavailable, match="429"):
        await client.lookup(WALL)
    await client.aclose()
    assert waits == [2.0, 3.0], "bSDD's Retry-After when it asks for more than the retry's own wait"
    assert len(throttling.requests) == 3


async def test_a_timeout_or_an_answer_that_is_not_the_apis_is_bsdd_out_of_reach() -> None:
    client, waits = client_for(Bsdd(script=[0]))
    with pytest.raises(BsddUnavailable, match="ReadTimeout"):
        await client.lookup(WALL)
    await client.aclose()
    assert waits == [], "a timeout is not retried"
    for status in (404, 400, 401):
        client, _ = client_for(Bsdd(script=[status]))
        with pytest.raises(BsddUnavailable, match=str(status)):
            await client.lookup(WALL)  # a path that moved, or a question the API did not take, is no unknown URI
        await client.aclose()

    def not_json(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>maintenance</html>")

    client = BsddClient("https://bsdd.test", transport=httpx.MockTransport(not_json))
    with pytest.raises(BsddUnavailable, match="JSON"):
        await client.lookup(WALL)
    await client.aclose()


async def test_an_answer_is_kept_until_it_expires() -> None:
    now = [1000.0]
    bsdd = Bsdd({WALL: WALL_ANSWER}, {WALL_COMMON: ["FireRating"]})
    client, _ = client_for(bsdd, cache_seconds=100, clock=lambda: now[0])
    assert await client.lookup(WALL) == await client.lookup(WALL) and len(bsdd.requests) == 1
    assert await client.lookup(NOWHERE) is None and await client.lookup(NOWHERE) is None and len(bsdd.requests) == 2
    assert await client.properties_of(WALL_COMMON) == await client.properties_of(WALL_COMMON)
    assert len(bsdd.requests) == 3, "the properties of a class are another question, kept as well"
    now[0] += 101
    await client.lookup(WALL)
    assert len(bsdd.requests) == 4, "asked again once the answer has expired"
    await client.aclose()
    uncached = Bsdd({WALL: WALL_ANSWER})
    client, _ = client_for(uncached, cache_seconds=0)
    await client.lookup(WALL)
    await client.lookup(WALL)
    assert len(uncached.requests) == 2, "OPENCDE_BSDD_CACHE_SECONDS=0 asks every time"
    await client.aclose()


def reference(step_id: int, uri: str, **more: Any) -> dict[str, Any]:
    return {
        "step_id": step_id,
        "uri": uri,
        "attribute": "Location",
        "identification": "X",
        "name": "Nothing",
        "location": uri,
        "classification": {"name": "Some dictionary", "source": "Someone", "location": None},
        "objects": [{"global_id": DOOR, "ifc_class": "IfcDoor"}],
        "object_count": 1,
        **more,
    }


FOUND = {
    "schema": "IFC4X3",
    "references": [
        reference(4, WALL, objects=[{"global_id": WALL_GUID, "ifc_class": "IfcWall"}], object_count=3),
        reference(5, NOWHERE),
        reference(6, FIRE_RATING, attribute="Identification", location=None, objects=[], object_count=0),
        reference(7, ELSEWHERE),
    ],
    "property_sets": {
        "Pset_WallCommon": {
            "step_id": 12,
            "properties": ["Bogus", "FireRating", "Reference"],
            "objects": [{"global_id": WALL_GUID, "ifc_class": "IfcWall"}],
            "object_count": 2,
        },
        "Pset_Custom": {"step_id": 15, "properties": ["A"], "objects": [], "object_count": 0},
    },
    "cut": True,
}


def known_to_bsdd() -> Bsdd:
    return Bsdd({WALL: WALL_ANSWER, FIRE_RATING: {"code": "FireRating"}}, {WALL_COMMON: ["FireRating", "IsExternal"]})


async def test_the_check_warns_of_what_bsdd_does_not_know_and_names_the_dictionaries() -> None:
    bsdd = known_to_bsdd()
    client, _ = client_for(bsdd)
    result = await check(FOUND, client)
    await client.aclose()
    assert result["check"] == {
        "name": "bsdd",
        "state": "done",
        "ruleset": "bSDD at bsdd.test: buildingsmart/ifc/4.3, example/nosuch/1.0",
        "issue_count": 5,
    }
    assert result["error_count"] == 0 and result["truncated"] is False
    issues = result["issues"]
    assert all(issue["kind"] == "bsdd" and issue["severity"] == "warning" for issue in issues)
    assert issues[0] == {
        "kind": "bsdd",
        "severity": "warning",
        "message": f"bSDD does not know the class {NOWHERE} of the classification reference #5 (identification 'X', "
        "name 'Nothing', in the classification 'Some dictionary'); it is on the IfcDoor 2Ox9REZJX8xQXPdFCabqZL.",
        "rule": "example/nosuch/1.0",
        "step_id": 5,
        "global_id": DOOR,
        "attribute": "Location",
    }
    assert "not the URI of a class or property at bSDD" in issues[1]["message"] and issues[1]["step_id"] == 7
    assert "rule" not in issues[1], "a URI that is not bSDD's names no dictionary of it"
    assert (issues[2]["attribute"], issues[2]["step_id"], issues[2]["rule"]) == ("Pset_Custom", 15, IFC_DICTIONARY)
    assert "no property set Pset_Custom" in issues[2]["message"] and "global_id" not in issues[2]
    assert (issues[3]["attribute"], issues[3]["global_id"]) == ("Pset_WallCommon.Bogus", WALL_GUID)
    assert "on 2 objects, among them the IfcWall" in issues[3]["message"]
    assert "only the first were looked up" in issues[4]["message"] and "step_id" not in issues[4]
    assert not any("Reference" in issue.get("attribute", "") for issue in issues), "bSDD leaves it out of every set"
    asked = [
        (request.url.path, request.url.params.get("uri") or request.url.params.get("ClassUri"))
        for request in bsdd.requests
    ]
    assert asked == [
        ("/api/Class/v1", WALL),
        ("/api/Class/v1", NOWHERE),
        ("/api/Property/v5", FIRE_RATING),
        ("/api/Class/Properties/v1", class_uri(IFC_DICTIONARY, "Pset_Custom")),
        ("/api/Class/Properties/v1", WALL_COMMON),
    ], "every reference once, the one on another host never, then every set as a class of the IFC dictionary"


async def test_the_sets_of_a_file_of_an_earlier_schema_are_not_checked() -> None:
    bsdd = known_to_bsdd()
    client, _ = client_for(bsdd)
    result = await check({**FOUND, "schema": "IFC4", "cut": False}, client)
    await client.aclose()
    assert [issue["step_id"] for issue in result["issues"]] == [5, 7], "only the references"
    assert not any(request.url.path == "/api/Class/Properties/v1" for request in bsdd.requests)
    assert result["check"]["ruleset"] == "bSDD at bsdd.test: buildingsmart/ifc/4.3, example/nosuch/1.0"
    client, _ = client_for(Bsdd())
    nothing = await check({"schema": "IFC2X3", "references": [], "property_sets": FOUND["property_sets"]}, client)
    await client.aclose()
    assert nothing["check"]["ruleset"] == "bSDD at bsdd.test: no dictionary referenced"
    assert nothing["issues"] == [] and nothing["check"]["issue_count"] == 0


async def test_bsdd_out_of_reach_stops_the_check() -> None:
    client, _ = client_for(Bsdd(script=[0]))
    with pytest.raises(BsddUnavailable):
        await check(FOUND, client)
    await client.aclose()


def prop(step_id: int, uri: str, set_name: str, name: str, **more: Any) -> dict[str, Any]:
    """A property that names a bSDD property, as the worker lists it."""
    return {
        "step_id": step_id,
        "uri": uri,
        "attribute": "Specification",
        "set": set_name,
        "name": name,
        "objects": [],
        "object_count": 0,
        **more,
    }


def ids_uri(uri: str, facet: str, specification: str, **more: Any) -> dict[str, Any]:
    """A bSDD URI of an IDS document, as the worker lists it."""
    return {"uri": uri, "facet": facet, "clause": "requirements", "specification": specification, **more}


IDS_URIS = [
    ids_uri(WALL, "classification", "Walls are classified", identifier="W-1", system="IFC", value="IfcWall"),
    ids_uri(NOWHERE, "classification", "Walls are classified", identifier="W-1", system="Nothing", value="X"),
    ids_uri(FIRE_RATING, "property", "Walls have a fire rating", set="Pset_WallCommon", name="FireRating"),
    ids_uri(BOGUS, "property", "Walls have a fire rating", identifier=None, set="Pset_Custom", name="Bogus"),
]
NOTHING_FOUND = {"schema": "IFC4", "references": [], "properties": [], "property_sets": {}}


async def test_the_check_warns_of_properties_and_of_ids_uris_that_bsdd_does_not_know() -> None:
    bsdd = known_to_bsdd()
    client, _ = client_for(bsdd)
    wall = {"objects": [{"global_id": WALL_GUID, "ifc_class": "IfcWall"}], "object_count": 2}
    door = {"objects": [{"global_id": DOOR, "ifc_class": "IfcDoor"}], "object_count": 1}
    found = {
        **NOTHING_FOUND,
        "properties": [
            prop(30, FIRE_RATING, "Pset_WallCommon", "FireRating", **wall),
            prop(31, BOGUS, "Custom", "Bogus", attribute="Description", **door),
        ],
    }
    ids = [{"document_id": "ids-a", "title": "Walls by bSDD", "uris": IDS_URIS, "cut": True}]
    result = await check(found, client, ids)
    await client.aclose()
    issues = result["issues"]
    assert result["check"]["issue_count"] == len(issues) == 4 and result["error_count"] == 0
    assert result["check"]["ruleset"] == "bSDD at bsdd.test: buildingsmart/ifc/4.3, example/nosuch/1.0"
    assert issues[0] == {
        "kind": "bsdd",
        "severity": "warning",
        "message": f"bSDD does not know the property {BOGUS} that the property 'Bogus' of the set 'Custom' (#31) names "
        f"in its Description; it is on the IfcDoor {DOOR}.",
        "rule": "example/nosuch/1.0",
        "step_id": 31,
        "global_id": DOOR,
        "attribute": "Custom.Bogus",
    }
    assert issues[1] == {
        "kind": "bsdd",
        "severity": "warning",
        "message": f"bSDD does not know the class {NOWHERE} that the IDS document 'Walls by bSDD' names in a "
        "classification facet of the requirements of its specification 'Walls are classified' (W-1), for the value "
        "'X' in the system 'Nothing'.",
        "rule": "example/nosuch/1.0",
        "document_id": "ids-a",
    }, "the IDS document and its specification named, and no instance of the file"
    assert issues[2]["message"].startswith(f"bSDD does not know the property {BOGUS} that the IDS document")
    assert issues[2]["message"].endswith(
        "of its specification 'Walls have a fire rating', for the property 'Bogus' in the set 'Pset_Custom'."
    )
    assert issues[3] == {
        "kind": "bsdd",
        "severity": "warning",
        "message": "The IDS document 'Walls by bSDD' names more bSDD URIs than the check reads, so only the first "
        "were looked up.",
        "document_id": "ids-a",
    }
    asked = [(request.url.path, request.url.params["uri"]) for request in bsdd.requests]
    assert asked == [
        ("/api/Property/v5", FIRE_RATING),
        ("/api/Property/v5", BOGUS),
        ("/api/Class/v1", WALL),
        ("/api/Class/v1", NOWHERE),
    ], "a URI that the file and an IDS document both name is asked about once"


def test_a_message_names_what_an_ids_facet_names_as_far_as_it_does() -> None:
    assert _facet_words({"facet": "classification", "system": "CCI"}) == ", in the system 'CCI'"
    assert _facet_words({"facet": "classification", "value": "L-BD"}) == ", for the value 'L-BD'"
    assert _facet_words({"facet": "property", "name": "FireRating"}) == ", for the property 'FireRating'"
    assert _facet_words({"facet": "property", "set": None, "name": None}) == "", "a restriction names nothing"


def test_a_finding_is_the_same_in_the_base_and_the_trial_by_its_set_and_property() -> None:
    bogus = {"kind": "bsdd", "rule": IFC_DICTIONARY, "global_id": WALL_GUID, "attribute": "Pset_WallCommon.Bogus"}
    other = {**bogus, "attribute": "Pset_WallCommon.Other", "message": "another property"}
    assert _issue_key(bogus) != _issue_key(other), "two properties of one set on one wall are two findings"
    assert _made(json.dumps([{"name": "schema", "state": "done"}, {"name": "bsdd", "state": "done"}]), "bsdd")
    assert not _made(json.dumps([{"name": "bsdd", "state": "failed"}]), "bsdd") and not _made(None, "bsdd")


@pytest.fixture
def checking(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[IfcGraphService, Graph, Log]:
    graph = Graph()
    log = Log()
    settings = make_settings(tmp_path, ifcgraph_enabled=True, bsdd_enabled=True, bsdd_api_url="https://bsdd.test")
    service = IfcGraphService(graph, LocalStorage(tmp_path), settings)
    monkeypatch.setattr(service_module, "log", log)
    monkeypatch.setattr(service, "_prepare_input", lambda key, name, workdir: tmp_path / "model.ifc")
    return service, graph, log


def answering(found: dict[str, Any], commands: list[list[str]]) -> Any:
    """The workers: the schema's check, and the bSDD references as the worker would find them."""

    async def answer(command: list[str], what: str, answers: tuple[int, ...] = (0,)) -> str:
        commands.append(command)
        if command[2] == "opencde.ifcgraph.bsdd_refs":
            assert answers == (0,) and command[-2:] == ["--memory-mb", "4096"]
            return json.dumps(found) + "\n"
        return json.dumps(SCHEMA_ANSWER)

    return answer


async def test_the_check_joins_the_report_of_an_upload_with_only_warnings(
    tmp_path: Path, checking: tuple[IfcGraphService, Graph, Log], monkeypatch: pytest.MonkeyPatch
) -> None:
    service, graph, log = checking
    service.bsdd = client_for(known_to_bsdd())[0]
    commands: list[list[str]] = []
    monkeypatch.setattr(service, "_in_a_process", answering(FOUND, commands))
    await service._validate("check-1", "documents/x", "model.ifc")
    await service.shutdown()

    assert commands[-1][2:4] == ["opencde.ifcgraph.bsdd_refs", str(tmp_path / "model.ifc")], "after the others"
    fields = graph.writes[-1][1]["fields"]
    assert graph.writes[-1][1]["state"] == "done"
    assert fields["issue_count"] == 6 and fields["error_count"] == 1, "the schema's error, and bSDD's five warnings"
    assert (
        fields["ruleset"] == "IfcOpenShell 0.9.0 (IFC4); bSDD at bsdd.test: buildingsmart/ifc/4.3, example/nosuch/1.0"
    )
    checks = json.loads(fields["checks"])
    assert [(check["name"], check["state"], check["issue_count"]) for check in checks] == [
        ("schema", "done", 1),
        ("bsdd", "done", 5),
    ]
    assert [issue["kind"] for issue in unpack_report(fields["report"])] == ["schema", *["bsdd"] * 5]
    assert log.events == [("ifc_validation_done", {"validation_id": "check-1", "issues": 6})]


async def test_bsdd_out_of_reach_fails_its_check_and_nothing_else(
    checking: tuple[IfcGraphService, Graph, Log], monkeypatch: pytest.MonkeyPatch
) -> None:
    service, graph, log = checking

    def gone(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"no route for {LINE}", request=request)

    service.bsdd = BsddClient("https://bsdd.test", transport=httpx.MockTransport(gone))
    monkeypatch.setattr(service, "_in_a_process", answering(FOUND, []))
    await service._validate("check-2", "documents/x", "model.ifc")
    await service.shutdown()

    fields = graph.writes[-1][1]["fields"]
    assert graph.writes[-1][1]["state"] == "done" and fields["issue_count"] == 1, "the file is checked all the same"
    assert fields["ruleset"] == "IfcOpenShell 0.9.0 (IFC4)", "only the checks that were made"
    assert json.loads(fields["checks"])[1] == {
        "name": "bsdd",
        "state": "failed",
        "ruleset": "bSDD at bsdd.test",
        "issue_count": 0,
        "error": "bSDD at bsdd.test could not be reached: ConnectError",
    }
    assert log.events == [
        ("ifc_bsdd_failed", {"error": "BsddUnavailable"}),
        ("ifc_validation_done", {"validation_id": "check-2", "issues": 1}),
    ], "what bSDD or the file said stays out of the log"


async def test_off_by_default_no_worker_reads_the_references(
    tmp_path: Path, checking: tuple[IfcGraphService, Graph, Log], monkeypatch: pytest.MonkeyPatch
) -> None:
    service, graph, _ = checking
    service.settings = make_settings(tmp_path, ifcgraph_enabled=True)
    commands: list[list[str]] = []
    monkeypatch.setattr(service, "_in_a_process", answering(FOUND, commands))
    await service._validate("check-3", "documents/x", "model.ifc")
    assert [command[2] for command in commands] == ["ifc_lpg.validation"] and service.bsdd is None
    assert [check["name"] for check in json.loads(graph.writes[-1][1]["fields"]["checks"])] == ["schema"]


IDS_DOCUMENTS = [
    {"document_id": "ids-a", "version_index": 2, "title": "Walls by bSDD", "storage_key": "documents/ids-a-2"},
    {"document_id": "ids-b", "version_index": 1, "title": "Broken", "storage_key": "documents/ids-b-1"},
]
IDS_REPORT = {
    "ruleset": "IfcTester 0.9.0: IDS 1.0",
    "issue_count": 0,
    "error_count": 0,
    "truncated": False,
    "issues": [],
    "rules_not_run": [],
    "specifications": [],
}


def answering_with_ids(commands: list[list[str]], read: dict[str, dict[str, Any]], *, fail: bool = False) -> Any:
    """The workers, with the IDS documents: the IDS check, and their bSDD URIs as the worker reads them from the
    files ``read`` names, any other being an IDS that cannot be read."""

    async def answer(command: list[str], what: str, answers: tuple[int, ...] = (0,)) -> str:
        commands.append(command)
        if command[2] == "ifc_lpg.ids":
            return json.dumps(IDS_REPORT)
        if command[2:4] == ["opencde.ifcgraph.bsdd_refs", "--ids"]:
            if fail:
                raise RuntimeError(f"could not read {LINE}")
            paths = command[command.index("--") + 1 :]
            return json.dumps({"ids": [read.get(Path(path).name, {"error": "it has a DTD"}) for path in paths]})
        if command[2] == "opencde.ifcgraph.bsdd_refs":
            return json.dumps(NOTHING_FOUND)
        return json.dumps(SCHEMA_ANSWER)

    return answer


def reports(graph: Graph) -> list[dict[str, Any]]:
    """The fields of every check that was made."""
    return [params["fields"] for _, params in graph.writes if params.get("state") == "done" and "fields" in params]


async def test_an_ids_version_is_read_once_and_its_unknown_uris_warn_in_every_report(
    checking: tuple[IfcGraphService, Graph, Log], monkeypatch: pytest.MonkeyPatch
) -> None:
    service, graph, log = checking
    bsdd = known_to_bsdd()
    service.bsdd = client_for(bsdd)[0]
    documents = [dict(document) for document in IDS_DOCUMENTS]

    async def listed(project_id: str) -> list[dict[str, Any]]:
        return documents

    monkeypatch.setattr(service, "_ids_documents", listed)
    commands: list[list[str]] = []
    read = {"ids-a-2": {"title": "the IDS's own title", "uris": IDS_URIS, "cut": False}}
    monkeypatch.setattr(service, "_in_a_process", answering_with_ids(commands, read))
    await service._validate("check-1", "documents/x", "model.ifc")
    await service._validate("check-2", "documents/y", "other.ifc")

    readings = [command for command in commands if command[2:4] == ["opencde.ifcgraph.bsdd_refs", "--ids"]]
    paths = [str(service.storage.path(str(document["storage_key"]))) for document in IDS_DOCUMENTS]
    assert readings == [
        [sys.executable, "-m", "opencde.ifcgraph.bsdd_refs", "--ids", "--memory-mb", "4096", "--", *paths]
    ], "every IDS version read once, the one that cannot be read too"
    assert len(bsdd.requests) == 4, "and every URI asked about once, however many reports name it"
    for fields in reports(graph):
        (made,) = [check for check in json.loads(fields["checks"]) if check["name"] == "bsdd"]
        assert made["state"] == "done" and made["issue_count"] == 2
        assert made["ruleset"] == "bSDD at bsdd.test: buildingsmart/ifc/4.3, example/nosuch/1.0"
        warnings = [issue for issue in unpack_report(fields["report"]) if issue["kind"] == "bsdd"]
        assert [(issue["severity"], issue["document_id"], issue["rule"]) for issue in warnings] == [
            ("warning", "ids-a", "example/nosuch/1.0")
        ] * 2
        assert all("the IDS document 'Walls by bSDD'" in issue["message"] for issue in warnings), "its title"
        assert fields["error_count"] == 1, "the schema's error alone: bSDD only warns"

    documents[0] = {**documents[0], "version_index": 3, "storage_key": "documents/ids-a-3"}
    read["ids-a-3"] = {"title": None, "uris": [], "cut": False}
    await service._validate("check-3", "documents/x", "model.ifc")
    await service.shutdown()
    readings = [command for command in commands if command[2:4] == ["opencde.ifcgraph.bsdd_refs", "--ids"]]
    assert readings[-1][-1:] == [str(service.storage.path("documents/ids-a-3"))], "only the new version is read"
    assert not [issue for issue in unpack_report(reports(graph)[-1]["report"]) if issue.get("document_id")]
    assert not any(event == "ifc_bsdd_ids_failed" for event, _ in log.events)


async def test_ids_documents_the_worker_could_not_read_are_left_out_this_once(
    checking: tuple[IfcGraphService, Graph, Log], monkeypatch: pytest.MonkeyPatch
) -> None:
    service, graph, log = checking
    service.bsdd = client_for(known_to_bsdd())[0]

    async def listed(project_id: str) -> list[dict[str, Any]]:
        return IDS_DOCUMENTS[:1]

    monkeypatch.setattr(service, "_ids_documents", listed)
    commands: list[list[str]] = []
    read = {"ids-a-2": {"title": None, "uris": IDS_URIS, "cut": False}}
    monkeypatch.setattr(service, "_in_a_process", answering_with_ids(commands, read, fail=True))
    await service._validate("check-1", "documents/x", "model.ifc")
    fields = reports(graph)[-1]
    (made,) = [check for check in json.loads(fields["checks"]) if check["name"] == "bsdd"]
    assert (made["state"], made["issue_count"]) == ("done", 0), "the file's own check stands"
    assert ("ifc_bsdd_ids_failed", {"error": "RuntimeError"}) in log.events, "what the worker said stays out"
    monkeypatch.setattr(service, "_in_a_process", answering_with_ids(commands, read))
    await service._validate("check-2", "documents/x", "model.ifc")
    await service.shutdown()
    assert json.loads(reports(graph)[-1]["checks"])[-1]["issue_count"] == 2, "read the next time"


def test_bsdd_is_asked_over_https_in_production_and_only_at_an_http_address(tmp_path: Path) -> None:
    def settings(**values: Any) -> Settings:
        return Settings(_env_file=None, data_dir=tmp_path / "data", **values)  # type: ignore[call-arg]

    production = {"public_url": "https://cde.example.com", "graph_password": "secret-enough", "secret_key": "k" * 40}
    with pytest.raises(ValidationError, match="OPENCDE_BSDD_API_URL"):
        settings(environment="production", **production, bsdd_enabled=True, bsdd_api_url="http://bsdd.example.com")
    off = settings(environment="production", **production, bsdd_api_url="http://bsdd.example.com")
    assert off.bsdd_enabled is False, "an address that is never asked refuses nothing"
    with pytest.raises(ValidationError, match="OPENCDE_BSDD_API_URL"):
        settings(environment="development", bsdd_api_url="ftp://bsdd.example.com")
    tidy = settings(environment="development", bsdd_api_url=" https://test.bsdd.buildingsmart.org/ ")
    assert tidy.bsdd_api_url == "https://test.bsdd.buildingsmart.org" and tidy.bsdd_enabled is False


class TrialGraph:
    """The base version of a trial with the report it was given, and nothing else in the project."""

    def __init__(self, checks: list[str]) -> None:
        self.row = {
            "storage_key": "documents/base.ifc",
            "file_name": "base.ifc",
            "base_report": pack_report(SCHEMA_ANSWER["issues"]),
            "base_checks": json.dumps([{"name": name, "state": "done"} for name in checks]),
        }

    async def one(self, query: str, **params: Any) -> dict[str, Any] | None:
        return self.row if "base_report" in query else None

    async def run(self, query: str, **params: Any) -> list[dict[str, Any]]:
        return []


@pytest.mark.parametrize(("checks", "state"), [(["schema"], "clean"), (["schema", "bsdd"], "issues")])
async def test_a_trial_keeps_only_the_findings_its_change_set_brings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, checks: list[str], state: str
) -> None:
    """A base checked before bSDD was asked, or while it was out of reach, is asked about during the trial, so that
    its own bSDD findings are not the change set's; a base that bSDD checked is not asked again."""
    storage = LocalStorage(tmp_path / "storage")
    snippet = make_key("snippets", new_id(), "json")
    storage.write_bytes(snippet, json.dumps({"base": {"document_id": "doc-1", "version_index": 1}}).encode())
    settings = make_settings(tmp_path, ifcgraph_enabled=True, bsdd_enabled=True, bsdd_api_url="https://bsdd.test")
    service = IfcGraphService(TrialGraph(checks), storage, settings)  # type: ignore[arg-type]
    service.bsdd = client_for(known_to_bsdd())[0]
    monkeypatch.setattr(service, "_prepare_input", lambda key, name, workdir: tmp_path / "model.ifc")
    readings: list[str] = []

    async def answer(command: list[str], what: str, answers: tuple[int, ...] = (0,)) -> str:
        if command[2] == "opencde.ifcgraph.apply":
            await asyncio.to_thread(Path(command[5]).write_bytes, b"ISO-10303-21;")  # the changed file
            return json.dumps({"count": 1, "applied": 1, "problems": []})
        if command[2] == "opencde.ifcgraph.bsdd_refs":
            readings.append(command[3])
            return json.dumps(FOUND)
        return json.dumps(SCHEMA_ANSWER)

    monkeypatch.setattr(service, "_in_a_process", answer)
    fields = await service._try_proposal(new_id(), "project-1", snippet)
    await service.shutdown()
    assert fields["state"] == state and fields["issue_count"] == (0 if state == "clean" else 5)
    assert len(readings) == (2 if state == "clean" else 1), "the base is read only when it was not checked"


async def test_a_trial_never_counts_the_ids_documents_findings_of_bsdd_as_its_own(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A URI of an IDS document says nothing of the change set: the base, checked before the document named it, lacks
    the finding, and the trial is clean all the same."""
    storage = LocalStorage(tmp_path / "storage")
    snippet = make_key("snippets", new_id(), "json")
    storage.write_bytes(snippet, json.dumps({"base": {"document_id": "doc-1", "version_index": 1}}).encode())
    settings = make_settings(tmp_path, ifcgraph_enabled=True, bsdd_enabled=True, bsdd_api_url="https://bsdd.test")
    service = IfcGraphService(TrialGraph(["schema", "bsdd"]), storage, settings)  # type: ignore[arg-type]
    service.bsdd = client_for(known_to_bsdd())[0]
    monkeypatch.setattr(service, "_prepare_input", lambda key, name, workdir: tmp_path / "model.ifc")

    async def listed(project_id: str) -> list[dict[str, Any]]:
        return IDS_DOCUMENTS[:1]

    monkeypatch.setattr(service, "_ids_documents", listed)
    read = {"ids-a-2": {"title": None, "uris": IDS_URIS, "cut": False}}
    workers = answering_with_ids([], read)

    async def answer(command: list[str], what: str, answers: tuple[int, ...] = (0,)) -> str:
        if command[2] == "opencde.ifcgraph.apply":
            await asyncio.to_thread(Path(command[5]).write_bytes, b"ISO-10303-21;")  # the changed file
            return json.dumps({"count": 1, "applied": 1, "problems": []})
        return await workers(command, what, answers)

    monkeypatch.setattr(service, "_in_a_process", answer)
    fields = await service._try_proposal(new_id(), "project-1", snippet)
    await service.shutdown()
    (made,) = [check for check in json.loads(fields["checks"]) if check["name"] == "bsdd"]
    assert made["issue_count"] == 2, "the trial's file was checked against the IDS document's URIs"
    assert fields["state"] == "clean" and fields["issue_count"] == 0 and unpack_report(fields["report"]) == []
