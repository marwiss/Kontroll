# This file was generated with the assistance of an AI coding tool.
"""``server_query`` through the MCP endpoint (ADR 0028): its schema and description follow the catalogue, a query
added to IFC-DB appears without code, and the listing, the answers and the refusals are the REST routes', held to 500
rows and 256 kB. The database and the IFC-DB service are stood in for (``tests/mcp_read_support.py``)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from ifc_db.queries import NamedQuery, Parameter

from opencde.ifcgraph.queries import CHANGED_SINCE, QUERIES
from opencde.mcp import routes
from opencde.mcp.queries import OWN_ARGUMENTS, SERVER_QUERY, server_query_tool
from tests.mcp_read_support import MODEL, DocumentsGraph, FakeService, IfcGraph, tools, version
from tests.mcp_support import DOCUMENT, call

NONE = {"version_index": None, "name": None, "class": None, "pset": None, "property": None, "global_id": None}


def ask(client: Any, **arguments: Any) -> dict[str, Any]:
    """The result of a call with the document and every argument not named null."""
    given = {"document_id": DOCUMENT, **NONE, "since": None, **arguments}
    answer = call(client, "server_query", given)
    assert answer.status_code == 200, answer.text
    return answer.json()["result"]


def refusal(result: dict[str, Any]) -> str:
    assert result["isError"] is True and "structuredContent" not in result
    return result["content"][0]["text"]


# -- the schema and the description ------------------------------------------------------------------------------------


def test_the_schema_is_the_catalogues_names_and_the_union_of_their_parameters() -> None:
    schema = SERVER_QUERY.definition()["inputSchema"]
    properties = schema["properties"]
    assert properties["name"]["anyOf"][0]["enum"] == [*QUERIES, CHANGED_SINCE]
    assert set(properties) == {
        "document_id",
        "version_index",
        "name",
        "class",
        "pset",
        "property",
        "global_id",
        "since",
    }
    assert schema["required"] == list(properties) and schema["additionalProperties"] is False
    assert properties["document_id"] == {
        "description": "The IFC document, as list_models gives it.",
        "maxLength": 64,
        "type": "string",
    }
    assert properties["since"]["anyOf"][0]["type"] == "integer" and properties["since"]["anyOf"][1] == {"type": "null"}
    for name in ("class", "pset", "property", "global_id"):
        assert properties[name]["anyOf"] == [{"maxLength": 255, "type": "string"}, {"type": "null"}], name
    assert "elements (required)" in properties["class"]["description"]
    assert "materials" in properties["class"]["description"] and "property" in properties["class"]["description"]


def test_the_description_lists_every_query_with_the_librarys_words() -> None:
    description = SERVER_QUERY.description
    for query in QUERIES.values():
        taken = ", ".join(p.name + (" required" if p.required else "") for p in query.parameters)
        assert f"- {query.name}" + (f" ({taken})" if taken else "") + f": {query.description}" in description
    assert "- changed-since (since required): What changed in the document since a version" in description
    assert "at most 500 rows" in description and "never instructions" in description


def test_no_parameter_of_the_catalogue_is_named_as_an_argument_of_the_tool() -> None:
    """A parameter IFC-DB adds by the name of one of the tool's own arguments would not be offered: this fails when
    the lock brings one."""
    names = {parameter.name for query in QUERIES.values() for parameter in query.parameters}
    assert not names & set(OWN_ARGUMENTS)
    kinds = {(parameter.name, parameter.kind) for query in QUERIES.values() for parameter in query.parameters}
    assert len(kinds) == len(names), "a parameter has one kind wherever it is taken"


def test_a_query_added_to_the_catalogue_appears_without_code_here(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    added = NamedQuery(
        "fire-ratings",
        "The fire rating of every wall that has one.",
        ("global_id", "rating"),
        "MATCH (e:IfcWall {model_id: m.id}) WHERE e.Rating = $rating RETURN e.GlobalId AS global_id, e.Rating AS rating\n",
        (Parameter("rating", "The rating, such as EI 60", True),),
    )
    monkeypatch.setitem(QUERIES, added.name, added)
    tool = server_query_tool()
    schema = tool.definition()["inputSchema"]["properties"]
    assert schema["name"]["anyOf"][0]["enum"] == [*QUERIES, CHANGED_SINCE] and "fire-ratings" in QUERIES
    assert schema["rating"]["description"] == "The rating, such as EI 60. For fire-ratings (required); null otherwise."
    assert "- fire-ratings (rating required): The fire rating of every wall that has one." in tool.description
    monkeypatch.setattr(routes, "TOOLS", (*routes.TOOLS[:1], tool, *routes.TOOLS[2:]))
    monkeypatch.setitem(routes._BY_NAME, tool.name, tool)
    service = FakeService(IfcGraph({"fire-ratings": [{"global_id": "1Xezbq735AdBO_4DerG66G", "rating": "EI 60"}]}))
    with tools(tmp_path, service=service) as client:
        listed = ask(client, rating=None)["structuredContent"]["queries"]
        answer = ask(client, name="fire-ratings", rating="EI 60")["structuredContent"]
    assert "fire-ratings" in [query["name"] for query in listed]
    assert answer["rows"] == [["1Xezbq735AdBO_4DerG66G", "EI 60"]]
    ((name, params),) = service.graph.asked
    assert name == "fire-ratings" and params["rating"] == "EI 60" and params["model_id"] == MODEL


# -- the listing -------------------------------------------------------------------------------------------------------


def test_the_listing_names_the_queries_the_models_state_and_the_working_copy(tmp_path: Path) -> None:
    with tools(tmp_path) as client:
        result = ask(client)
    assert result["isError"] is False
    listed = result["structuredContent"]
    assert listed["model_state"] == "done" and listed["workcopy"] is False and listed["max_rows"] == 500
    assert [query["name"] for query in listed["queries"]] == [*QUERIES, CHANGED_SINCE]
    entity = listed["queries"][0]
    assert entity == {
        "name": "entity",
        "description": QUERIES["entity"].description,
        "parameters": [
            {"name": "global_id", "description": QUERIES["entity"].parameters[0].description, "required": True}
        ],
        "columns": list(QUERIES["entity"].columns),
    }, "as the REST route lists it"
    assert json.loads(result["content"][0]["text"]) == listed
    with tools(tmp_path, service=FakeService(held=True)) as client:
        assert ask(client)["structuredContent"]["workcopy"] is True


def test_a_model_on_its_way_is_listed_with_its_state(tmp_path: Path) -> None:
    with tools(tmp_path, DocumentsGraph(conversions={3: ("running", MODEL)})) as client:
        listed = ask(client)["structuredContent"]
        refused = ask(client, name="storeys")
    assert listed["model_state"] == "running"
    assert refusal(refused) == "The IFC graph of this version is running, not done"


def test_the_latest_version_is_asked_when_no_version_is_named(tmp_path: Path) -> None:
    graph = DocumentsGraph(
        versions=[version(1), version(2), version(3)], conversions={2: ("done", "m2"), 3: ("done", MODEL)}
    )
    service = FakeService(IfcGraph({"storeys": [{"name": "Level 1", "elevation": 0.0}]}))
    with tools(tmp_path, graph, service) as client:
        ask(client, name="storeys")
        ask(client, name="storeys", version_index=2)
    assert [lookup["version_index"] for lookup in graph.conversion_lookups()] == [3, 2]
    assert [params["model_id"] for _name, params in service.graph.asked] == [MODEL, "m2"]


# -- the answers -------------------------------------------------------------------------------------------------------


def _walls(count: int, name: str = "Wall") -> list[dict[str, Any]]:
    return [
        {"global_id": f"{index:022d}", "class": "IfcWall", "name": f"{name} {index}", "container": "Level 1"}
        for index in range(count)
    ]


def test_a_query_answers_its_rows_in_the_order_of_the_columns_with_the_count(tmp_path: Path) -> None:
    service = FakeService(IfcGraph({"elements": _walls(3)}))
    with tools(tmp_path, service=service) as client:
        result = ask(client, name="elements", **{"class": "IfcWall"})
    answer = result["structuredContent"]
    assert answer == {
        "name": "elements",
        "columns": ["global_id", "class", "name", "container"],
        "rows": [[f"{index:022d}", "IfcWall", f"Wall {index}", "Level 1"] for index in range(3)],
        "count": 3,
        "truncated": False,
    }
    ((name, params),) = service.graph.asked
    assert name == "elements" and params == {"class": "IfcWall", "model_id": MODEL, "row_limit": 10_001}


def test_the_working_copy_answers_when_it_holds_the_model(tmp_path: Path) -> None:
    archive, copy = IfcGraph({"storeys": [{"name": "old"}]}), IfcGraph({"storeys": [{"name": "Level 1"}]})
    with tools(tmp_path, service=FakeService(archive, workcopy=copy, held=True)) as client:
        rows = ask(client, name="storeys")["structuredContent"]["rows"]
    assert rows[0][1] == "Level 1" and not archive.asked and copy.asked


def test_an_answer_holds_at_most_500_rows_and_counts_what_the_query_found(tmp_path: Path) -> None:
    for found, count, truncated in ((500, 500, False), (501, 501, True), (10_001, 10_000, True)):
        with tools(tmp_path, service=FakeService(IfcGraph({"elements": _walls(found)}))) as client:
            answer = ask(client, name="elements", **{"class": "IfcWall"})["structuredContent"]
        assert len(answer["rows"]) == 500 and answer["count"] == count and answer["truncated"] is truncated, found


def test_an_answer_stays_within_256_kb_and_cuts_a_long_text(tmp_path: Path) -> None:
    long = "é" * 5000
    service = FakeService(IfcGraph({"elements": _walls(300, name=long)}))
    with tools(tmp_path, service=service) as client:
        result = ask(client, name="elements", **{"class": "IfcWall"})
    answer = result["structuredContent"]
    assert answer["truncated"] is True and 0 < len(answer["rows"]) < 300 and answer["count"] == 300
    assert all(len(row[2]) == 1000 for row in answer["rows"])
    assert len(result["content"][0]["text"].encode("utf-8")) <= 256 * 1024
    entity = {"global_id": "1Xezbq735AdBO_4DerG66G", "attributes": {"Name": long, "Tag": ["x" * 2000]}}
    service = FakeService(IfcGraph({"entity": [entity]}))
    with tools(tmp_path, service=service) as client:
        (row,) = ask(client, name="entity", global_id=entity["global_id"])["structuredContent"]["rows"]
    attributes = row[QUERIES["entity"].columns.index("attributes")]
    assert len(attributes["Name"]) == 1000 and len(attributes["Tag"][0]) == 1000, "within lists and maps too"


def test_changed_since_answers_from_the_versions(tmp_path: Path) -> None:
    since = [
        {"version_index": 2, "author": "anna", "approved_by": None, "change_set_id": None, "changes": None},
        {
            "version_index": 3,
            "author": "ai",
            "approved_by": "bo",
            "change_set_id": "cs-1",
            "changes": [{"guid": "1Xezbq735AdBO_4DerG66G", "attribute": "Name", "op": "set"}],
        },
    ]
    graph = DocumentsGraph(versions=[version(1), version(2), version(3)], conversions={}, since=since)
    with tools(tmp_path, graph) as client:
        answer = ask(client, name=CHANGED_SINCE, since=1)["structuredContent"]
        later = ask(client, name=CHANGED_SINCE, since=2, version_index=2)
        missing = ask(client, name=CHANGED_SINCE)
        other = ask(client, name=CHANGED_SINCE, since=1, **{"class": "IfcWall"})
    assert answer["columns"][:5] == ["version_index", "change_set_id", "author", "approved_by", "whole_file"]
    assert answer["rows"] == [
        [2, None, "anna", None, True, None, None, None, None, None],
        [3, "cs-1", "ai", "bo", False, "1Xezbq735AdBO_4DerG66G", None, None, "Name", "set"],
    ]
    assert answer["count"] == 2 and answer["truncated"] is False, "no model is needed for it"
    assert refusal(later) == "since must be an earlier version than this one"
    assert refusal(missing) == "changed-since needs the parameter since"
    assert refusal(other) == "changed-since takes no parameter class"


# -- the refusals ------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("arguments", "expected"),
    [
        ({"name": "elements"}, "elements needs the parameter class"),
        ({"name": "elements", "class": "Wall"}, "class must be the name of an IFC class, such as IfcWall"),
        ({"name": "elements", "class": "IfcWall", "pset": "Pset_WallCommon"}, "elements takes no parameter pset"),
        (
            {"name": "entity", "global_id": "not a GlobalId"},
            "global_id must be a GlobalId: 22 characters of IFC's base 64",
        ),
        ({"name": None, "class": "IfcWall"}, "The listing takes no parameters: name a query to give them"),
        ({"document_id": "not a document"}, "There is no such document version among your projects"),
        (
            {"document_id": "55555555-5555-4555-8555-555555555555"},
            "There is no such document version among your projects",
        ),
        ({"version_index": 9}, "There is no such document version among your projects"),
    ],
)
def test_a_refusal_is_the_routes_fixed_text(tmp_path: Path, arguments: dict[str, Any], expected: str) -> None:
    service = FakeService()
    with tools(tmp_path, service=service) as client:
        assert refusal(ask(client, **arguments)) == expected
    assert not service.graph.asked


def test_a_version_without_a_model_or_a_module_that_is_off_is_refused(tmp_path: Path) -> None:
    with tools(tmp_path, DocumentsGraph(conversions={})) as client:
        no_model = ask(client, name="storeys")
        no_listing = ask(client)
    with tools(tmp_path, ifcgraph_enabled=False) as client:
        off = call(client, "server_query", {"document_id": DOCUMENT, **NONE, "since": None})
    expected = "This version has no IFC graph: it is not an IFC file, or came before the module"
    assert refusal(no_model) == refusal(no_listing) == expected
    assert off.status_code == 400 and off.json()["error"]["code"] == -32602, "a module that is off has no tools"


def test_a_query_past_its_time_is_refused(tmp_path: Path) -> None:
    class Slow(IfcGraph):
        async def run(self, statement: str, **params: Any) -> list[dict[str, Any]]:
            raise TimeoutError

    with tools(tmp_path, service=FakeService(Slow())) as client:
        assert refusal(ask(client, name="storeys")) == "The query exceeded the time limit of 10 seconds"


@pytest.mark.parametrize(
    ("arguments", "expected"),
    [
        ({"name": "drop"}, "name: Input should be 'entity', 'element-classes'"),
        ({"since": -1, "name": CHANGED_SINCE}, "since: Input should be greater than or equal to 0"),
        ({"version_index": 0}, "version_index: Input should be greater than or equal to 1"),
        ({"class": "x" * 256, "name": "elements"}, "class: String should have at most 255 characters"),
        ({"cypher": "MATCH (n) RETURN n"}, "an argument the tool does not take"),
    ],
)
def test_arguments_the_schema_refuses_are_named_without_their_values(
    tmp_path: Path, arguments: dict[str, Any], expected: str
) -> None:
    with tools(tmp_path) as client:
        said = refusal(ask(client, **arguments))
    assert said.startswith("Invalid arguments: ") and expected in said
    assert "MATCH" not in said and "drop" not in said
