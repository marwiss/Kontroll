# This file was generated with the assistance of an AI coding tool.
"""Checking an upload against buildingSMART's Data Dictionary (OB-42), without the network: what a bSDD URI is, the
client against a stubbed bSDD that answers as bSDD's API does, the check on what the worker found, and the check in
the report of an upload. The worker itself is tried in ``test_bsdd_refs.py``, and the whole flow against a database
in ``tests/integration/test_ifc_bsdd.py``."""

from __future__ import annotations

import asyncio
import json
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
