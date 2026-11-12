# This file was generated with the assistance of an AI coding tool.
"""The change sets of the MCP endpoint (ADR 0028, step 2): the tools in Dataspatium's order and their arguments, a
draft opened, filled, mended and proposed, the trial read back, and the draft repository's statements. The database
is stood in for (``tests/mcp_drafts_support.py``); ``tests/integration/test_mcp_change_sets.py`` has its side.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from opencde.mcp import change_sets, routes, write_tools
from opencde.store.jobs import drafts
from opencde.store.jobs.drafts import ChangeSetDraftRepository, DraftRefused
from tests.mcp_drafts_support import (
    TOPIC,
    USER,
    DraftGraph,
    FakeProposing,
    FakeTopics,
    FakeTrials,
    _Topic,
    trial,
    version,
)
from tests.mcp_support import CLOUD, DOCUMENT, call, endpoint, principal, rpc

PROPOSER = principal(scopes=("mcp", "mcp:propose"))
WALL = {"storey": None, "start": [0, 0], "end": [4, 0], "thickness": None, "height": None, "name": "New wall",
        "type": None, "partition": None, "load_bearing": None, "status": None}  # fmt: skip
DOOR = {"wall_id": "new-1", "offset": 1, "width": None, "height": None, "sill": None, "fill": "door", "name": None,
        "type": None, "side": None}  # fmt: skip
RENAME = {"guid": "1Xezbq735AdBO_4DerG66G", "step_id": None, "path": None, "attribute": "Name", "op": "set",
          "index": None, "old": "Wall 1", "new": "Wall 1b", "copy": None}  # fmt: skip


@pytest.fixture
def graph() -> DraftGraph:
    return DraftGraph()


@pytest.fixture
def client(tmp_path: Path, graph: DraftGraph) -> Iterator[TestClient]:
    with endpoint(tmp_path, graph, PROPOSER, ifcgraph_enabled=True) as client:
        yield client


def result(answer: Any) -> dict[str, Any]:
    assert answer.status_code == 200, answer.text
    return answer.json()["result"]


def ok(answer: Any) -> dict[str, Any]:
    found = result(answer)
    assert found["isError"] is False, found["content"][0]["text"]
    return found["structuredContent"]


def refused(answer: Any) -> str:
    found = result(answer)
    assert found["isError"] is True, found
    return found["content"][0]["text"]


def opened(client: TestClient, version_index: int | None = None) -> str:
    return ok(call(client, "open_changeset", {"document_id": DOCUMENT, "version_index": version_index}))["changeset_id"]


# -- the tools --------------------------------------------------------------------------------------------------------


def test_the_change_sets_follow_list_models_in_dataspatiums_order(client: TestClient) -> None:
    listed = rpc(client, "tools/list").json()["result"]["tools"]
    assert [tool["name"] for tool in listed] == [
        "list_models",
        "open_changeset",
        *(tool["name"] for tool in write_tools.TOOLS),
        "change_attribute",
        "propose_changes",
        "get_proposal",
        "list_proposals",
        "server_query",
        "get_publication",
        "start_clash_check",
        "get_clash_check",
    ]
    by_name = {tool["name"]: tool for tool in listed}
    for spec in write_tools.TOOLS:
        schema = by_name[spec["name"]]["inputSchema"]
        assert list(schema["properties"]) == ["changeset_id", *spec["properties"]], "the app's schema, the handle first"
        assert {key: schema["properties"][key] for key in spec["properties"]} == spec["properties"]
        assert schema["required"] == list(schema["properties"]) and schema["additionalProperties"] is False
        assert by_name[spec["name"]]["annotations"]["readOnlyHint"] is False
    proposing = {"open_changeset", *(spec["name"] for spec in write_tools.TOOLS), "change_attribute", "propose_changes"}
    assert {tool.name: tool.scope for tool in routes.TOOLS} == {
        tool.name: "mcp:propose" if tool.name in proposing else "mcp" for tool in routes.TOOLS
    }
    assert not any(word in name for name in by_name for word in ("approve", "publish", "upload", "merge"))


def test_without_the_ifc_db_module_there_are_no_change_sets(tmp_path: Path) -> None:
    with endpoint(tmp_path, DraftGraph(), PROPOSER) as client:
        listed = [tool["name"] for tool in rpc(client, "tools/list").json()["result"]["tools"]]
        unknown = call(client, "open_changeset", {"document_id": DOCUMENT, "version_index": None})
    assert listed == ["list_models", "get_publication"], "the tools of the IFC-LPG module only while it is on"
    assert unknown.status_code == 400 and unknown.json()["error"]["code"] == -32602


def test_the_arguments_are_held_to_the_apps_schema_and_name_what_is_wrong(client: TestClient) -> None:
    handle = opened(client)
    as_text = refused(call(client, "create_wall", {"changeset_id": handle, **WALL, "thickness": "0.2"}))
    assert as_text.startswith("Invalid arguments: thickness: ") and "0.2" not in as_text, "JSON's types, as the app's"
    assert "thickness:" in refused(call(client, "create_wall", {"changeset_id": handle, **WALL, "thickness": True}))
    storeys = {"changeset_id": handle, "storeys": [{"elevation": 3}], "grid": None}
    assert "storeys.0.name: Field required" in refused(call(client, "create_storeys_and_grid", storeys))
    smuggled = {"changeset_id": handle, "storeys": [{"name": "Plan 2", "elevation": 3, "IGNORE_ALL": 1}], "grid": None}
    assert "IGNORE_ALL" not in refused(call(client, "create_storeys_and_grid", smuggled)), "a key is never quoted"
    extra = refused(call(client, "create_wall", {"changeset_id": handle, **WALL, "colour": "red"}))
    assert extra == "Invalid arguments: an argument the tool does not take"
    grid = {"x_spacing": 6, "x_count": 2.0, "y_spacing": 4, "y_count": 1}
    whole = ok(call(client, "create_storeys_and_grid", {"changeset_id": handle, "storeys": None, "grid": grid}))
    assert whole["description"] == "Storeys: –; grid of 2×1 bays of 6×4 m", "2.0 is a whole number, as in JSON Schema"
    assert refused(call(client, "create_wall", {**WALL, "changeset_id": handle} | {"start": None})) == (
        "start must be [x, y] in metres"
    ), "the app's own words"


# -- a change set opened, filled, mended and listed ---------------------------------------------------------------


def test_a_change_set_is_opened_on_the_latest_version_or_a_given_one(client: TestClient, graph: DraftGraph) -> None:
    answer = ok(call(client, "open_changeset", {"document_id": DOCUMENT.upper(), "version_index": None}))
    assert answer["base"] == {"document_id": DOCUMENT, "version_index": 3} and answer["max_steps"] == 200
    assert answer["expires_at"] > "2026" and answer["changeset_id"] in graph.drafts
    older = ok(call(client, "open_changeset", {"document_id": DOCUMENT, "version_index": 2}))
    assert older["base"]["version_index"] == 2
    assert refused(call(client, "open_changeset", {"document_id": DOCUMENT, "version_index": 9})) == (
        "The document has no version with this version_index"
    )
    for document_id in ("44444444-4444-4444-8444-444444444444", "../../etc/passwd"):
        assert refused(call(client, "open_changeset", {"document_id": document_id, "version_index": None})) == (
            change_sets.NO_DOCUMENT
        )
    opened_events = [event for event in graph.events() if event["type"] == "mcp.changeset.opened"]
    assert opened_events[0]["details"] == {
        "tool": "open_changeset",
        "client_info": {"name": "test-client", "version": "1.0"},
        "project_id": CLOUD,
        "document_id": DOCUMENT,
        "version_index": 3,
        "changeset_id": answer["changeset_id"],
    }


def test_a_version_that_is_no_ifc_model_has_no_change_set(tmp_path: Path) -> None:
    graph = DraftGraph(documents={DOCUMENT: (CLOUD, [version(1, "plan.pdf")])})
    with endpoint(tmp_path, graph, PROPOSER, ifcgraph_enabled=True) as client:
        text = refused(call(client, "open_changeset", {"document_id": DOCUMENT, "version_index": None}))
    assert text.startswith("The version is no IFC model") and not graph.drafts


def test_the_steps_are_the_apps_operations_with_their_refs(client: TestClient, graph: DraftGraph) -> None:
    handle = opened(client)
    wall = ok(call(client, "create_wall", {"changeset_id": handle, **WALL}))
    assert wall == {
        "ok": True,
        "step": 1,
        "description": "new-1 Wall New wall on the lowest storey from (0, 0) to (4, 0), 0.2 m thick, 3 m high",
        "ref": "new-1",
    }
    assert ok(call(client, "create_opening", {"changeset_id": handle, **DOOR}))["ref"] == "new-2"
    assert refused(call(client, "create_opening", {"changeset_id": handle, **DOOR, "wall_id": "new-7"})) == (
        "new-7 is not a ref of this change set (new-1 to new-2)"
    )
    assert ok(call(client, "change_attribute", {"changeset_id": handle, **RENAME}))["step"] == 3
    listed = ok(call(client, "manage_changeset", {"changeset_id": handle, "action": "list"}))["steps"]
    assert [(step["tool"], step["ref"]) for step in listed] == [
        ("create_wall", "new-1"),
        ("create_opening", "new-2"),
        ("change_attribute", None),
    ]
    stored = json.loads(graph.drafts[handle]["steps"])
    door = {key: value for key, value in DOOR.items() if key not in ("type", "side")}
    assert write_tools.to_wheel(stored) == [
        {"tool": "create_wall", "storey": None, "start": [0, 0], "end": [4, 0], "thickness": 0.2, "height": 3,
         "name": "New wall"},
        {"tool": "create_opening", **door, "width": 0.9, "height": 2.1, "sill": 0},
    ], "the defaults filled in, no partition, type, side, load_bearing or status unless given, and no refs"  # fmt: skip
    assert write_tools.changes(stored) == [
        {"guid": "1Xezbq735AdBO_4DerG66G", "attribute": "Name", "op": "set", "old": "Wall 1", "new": "Wall 1b"}
    ]
    assert ok(call(client, "manage_changeset", {"changeset_id": handle, "action": "remove_last"}))["steps"] == 2
    assert ok(call(client, "manage_changeset", {"changeset_id": handle, "action": "remove_last"}))["steps"] == 1
    assert ok(call(client, "create_opening", {"changeset_id": handle, **DOOR}))["ref"] == "new-2", "the ref given back"
    assert graph.drafts[handle]["refs"] == 2
    assert ok(call(client, "manage_changeset", {"changeset_id": handle, "action": "clear"})) == {"ok": True, "steps": 0}
    assert graph.drafts[handle]["steps"] == "[]" and graph.drafts[handle]["refs"] == 0


def test_a_type_an_element_and_an_edit_go_through_the_apps_schemas(client: TestClient, graph: DraftGraph) -> None:
    """define_type's layers, create_element's shape and stair and edit_element are held to the app's schemas, the
    nested objects with every field, and become the app's operations with their refs."""
    handle = opened(client)
    layers = [{"material": "Betong", "thickness": 0.2, "category": "concrete", "role": "load_bearing"}]
    wall_type = {"kind": "wall", "name": "YV1", "layers": layers, "predefined_type": None, "material": None,
                 "material_category": None, "operation": None, "partitioning": None, "width": None, "height": None,
                 "lining_depth": None}  # fmt: skip
    assert ok(call(client, "define_type", {"changeset_id": handle, **wall_type}))["ref"] == "new-1"
    typed = ok(call(client, "create_wall", {"changeset_id": handle, **WALL, "type": "new-1", "load_bearing": True}))
    assert typed["description"] == (
        "new-2 Wall New wall on the lowest storey from (0, 0) to (4, 0), 0.2 m thick, 3 m high, type new-1, "
        "load-bearing"
    )
    shape = {"profile": "rectangle", "x": 0.3, "y": 0.3, "radius": None, "outline": None, "depth": 3, "along": None}
    column = {"storey": None, "ifc_class": "IfcColumn", "predefined_type": None, "object_type": None, "type": None,
              "name": "P1", "at": [2, 0], "z": None, "rotation": None, "shape": shape, "stair": None, "part_of": None,
              "host": None}  # fmt: skip
    assert ok(call(client, "create_element", {"changeset_id": handle, **column}))["ref"] == "new-3"
    partial = {**column, "shape": {"profile": "circle", "radius": 0.2}}
    assert "shape" in refused(call(client, "create_element", {"changeset_id": handle, **partial}))
    stair = {"risers": 1.5, "riser_height": 0.175, "tread_length": 0.27, "width": None, "thickness": None,
             "landing": None}  # fmt: skip
    flight = {**column, "ifc_class": "IfcStair", "shape": None, "stair": stair}
    assert "stair.risers" in refused(call(client, "create_element", {"changeset_id": handle, **flight}))
    edit = {"id": "new-2", "name": None, "start": None, "end": [5, 0], "thickness": None, "height": None,
            "type": None, "outline": None, "offset": None, "width": None, "sill": None, "pitch": None,
            "overhang": None, "base": None}  # fmt: skip
    edited = ok(call(client, "edit_element", {"changeset_id": handle, **edit}))
    assert edited == {"ok": True, "step": 4, "description": "Change new-2: end at (5, 0)"}, "an edit has no ref"
    stored = write_tools.to_wheel(json.loads(graph.drafts[handle]["steps"]))
    assert [op["tool"] for op in stored] == ["define_type", "create_wall", "create_element", "edit_element"]
    assert stored[1]["type"] == "new-1" and stored[1]["load_bearing"] is True and "status" not in stored[1]
    assert stored[2]["shape"] == {**shape, "along": "z"} and stored[3] == {
        "tool": "edit_element",
        "id": "new-2",
        "end": [5, 0],
    }
    assert graph.drafts[handle]["refs"] == 3


def test_a_step_that_is_refused_leaves_the_draft_as_it_was(client: TestClient, graph: DraftGraph) -> None:
    handle = opened(client)
    ok(call(client, "create_wall", {"changeset_id": handle, **WALL}))
    before = dict(graph.drafts[handle])
    delete = {"changeset_id": handle, "ids": ["new-1"], "confirm": None}
    assert "confirm: true" in refused(call(client, "delete_elements", delete))
    assert graph.drafts[handle] == before, "the transaction was rolled back"


def test_an_unknown_expired_or_someone_elses_handle_asks_for_a_new_one(client: TestClient, graph: DraftGraph) -> None:
    handle = opened(client)
    graph.drafts["66666666-6666-4666-8666-666666666666"] = {**graph.drafts[handle], "user_id": "u-bert"}
    graph.drafts["66666666-6666-4666-8666-666666666666"]["changeset_id"] = "66666666-6666-4666-8666-666666666666"
    graph.drafts[handle]["expires_at"] = "2000-01-01T00:00:00.000Z"
    for changeset_id in (handle, "66666666-6666-4666-8666-666666666666", "77777777-7777-4777-8777-777777777777", "x"):
        assert refused(call(client, "create_wall", {"changeset_id": changeset_id, **WALL})) == change_sets.UNKNOWN


def test_change_attribute_takes_the_schemas_form_and_no_ref(client: TestClient) -> None:
    handle = opened(client)
    as_ref = refused(call(client, "change_attribute", {"changeset_id": handle, **RENAME, "guid": "new-1"}))
    assert as_ref.startswith("Invalid arguments: guid: String should match pattern")
    both = refused(call(client, "change_attribute", {"changeset_id": handle, **RENAME, "step_id": 170}))
    assert both == "The change is not one: the change: Value error, name the instance by step_id or by guid, not both " \
        "and not neither"  # fmt: skip
    deleting = refused(call(client, "change_attribute", {"changeset_id": handle, **RENAME, "op": "delete"}))
    assert deleting.startswith("Invalid arguments: op: Input should be 'set', 'add' or 'remove'")
    odd = {**RENAME, "new": {"anything": "else"}}
    assert refused(call(client, "change_attribute", {"changeset_id": handle, **odd})).startswith(
        "The change is not one"
    )
    typed = {**RENAME, "attribute": "NominalValue", "old": None, "new": {"type": "IfcLabel", "value": "EI60"}}
    shared = ok(call(client, "change_attribute", {"changeset_id": handle, **typed, "copy": True}))
    assert shared["description"] == "Set NominalValue of 1Xezbq735AdBO_4DerG66G"


def test_a_change_set_holds_at_most_200_steps(client: TestClient, graph: DraftGraph) -> None:
    handle = opened(client)
    graph.drafts[handle]["steps"] = json.dumps([{"tool": "delete_elements", "ids": [1], "confirm": True}] * 200)
    for name, arguments in (("create_wall", WALL), ("change_attribute", RENAME)):
        assert "holds 200 steps already" in refused(call(client, name, {"changeset_id": handle, **arguments}))


def test_a_user_has_at_most_ten_open_change_sets(client: TestClient, graph: DraftGraph) -> None:
    for _ in range(drafts.MAX_OPEN):
        opened(client)
    text = refused(call(client, "open_changeset", {"document_id": DOCUMENT, "version_index": None}))
    assert text.startswith("You have 10 open change sets") and len(graph.drafts) == 10


# -- the proposal and its trial ------------------------------------------------------------------------------------


@pytest.fixture
def proposing(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    FakeProposing.made = []
    FakeTopics.there = {}
    monkeypatch.setattr(change_sets, "Proposing", FakeProposing)
    monkeypatch.setattr(change_sets, "TopicRepository", FakeTopics)
    return FakeProposing.made


def test_a_proposal_is_a_topic_with_the_change_set_and_again_a_new_snippet_on_it(
    client: TestClient, graph: DraftGraph, proposing: list[dict[str, Any]]
) -> None:
    client.app.state.ifcgraph = FakeTrials()  # ty: ignore[unresolved-attribute]
    handle = opened(client)
    ok(call(client, "create_wall", {"changeset_id": handle, **WALL}))
    ok(call(client, "create_opening", {"changeset_id": handle, **DOOR}))
    ok(call(client, "change_attribute", {"changeset_id": handle, **RENAME}))
    asked = {"changeset_id": handle, "title": "A wall with a door", "description": None, "ai_model": "m" * 150}
    answer = ok(call(client, "propose_changes", asked))
    assert answer == {"project_id": CLOUD, "topic_guid": TOPIC, "state": "queued", "ops": 2, "changes": 1}
    (first,) = proposing
    assert first["topic"] is True and first["project_id"] == CLOUD and first["author"] == "anna"
    assert first["title"] == "A wall with a door" and first["reference"] == "changes.json"
    assert first["description"].splitlines()[0].startswith("new-1 Wall New wall"), "the steps' lines by default"
    change_set = first["change_set"]
    assert change_set["schema"] == "http://testserver/documents/1.0/ifc-changes/schema"
    assert change_set["base"] == {"document_id": DOCUMENT, "version_index": 3}
    provenance = change_set["provenance"]
    assert (provenance["user"], provenance["ai_model"]) == ("anna", "m" * 150)
    assert provenance["tool_call"] == "mcp:create_wall,create_opening,change_attribute"
    assert change_set["ops_form"] == "dataspatium-tools/1"
    assert [op["tool"] for op in change_set["ops"]] == ["create_wall", "create_opening"]
    assert all("ref" not in op for op in change_set["ops"]), "the server counts the refs itself"
    assert change_set["changes"] == write_tools.changes(json.loads(graph.drafts[handle]["steps"]))
    assert graph.drafts[handle]["topic_guid"] == TOPIC

    FakeTopics.there[TOPIC] = _Topic(TOPIC)
    ok(call(client, "manage_changeset", {"changeset_id": handle, "action": "remove_last"}))
    again = ok(call(client, "propose_changes", {**asked, "title": "Another title"}))
    assert again["topic_guid"] == TOPIC and again["changes"] == 0
    second = proposing[1]
    assert second["topic"] is False and second["topic_guid"] == TOPIC and "title" not in second
    assert "changes" in second["change_set"] and second["change_set"]["changes"] == []
    events = [event for event in graph.events() if event["type"] == "mcp.changeset.proposed"]
    assert events[0]["details"] == {
        "tool": "propose_changes",
        "client_info": {"name": "test-client", "version": "1.0"},
        "project_id": CLOUD,
        "document_id": DOCUMENT,
        "version_index": 3,
        "changeset_id": handle,
        "topic_guid": TOPIC,
        "ops": 2,
        "changes": 1,
        "ai_model": "m" * 100,
    }
    assert "A wall with a door" not in json.dumps([event["details"] for event in graph.events()])


def test_a_topic_that_went_or_lost_its_change_set_gets_a_new_one(
    client: TestClient, graph: DraftGraph, proposing: list[dict[str, Any]]
) -> None:
    handle = opened(client)
    ok(call(client, "create_wall", {"changeset_id": handle, **WALL}))
    asked = {"changeset_id": handle, "title": "A wall", "description": "Why", "ai_model": None}
    ok(call(client, "propose_changes", asked))
    FakeTopics.there[TOPIC] = _Topic(TOPIC, snippet=None)
    ok(call(client, "propose_changes", asked))
    assert [made["topic"] for made in proposing] == [True, True]
    assert proposing[0]["change_set"]["provenance"]["ai_model"] is None and proposing[0]["description"] == "Why"


def test_an_empty_change_set_is_not_proposed(client: TestClient, proposing: list[dict[str, Any]]) -> None:
    handle = opened(client)
    asked = {"changeset_id": handle, "title": "Nothing", "description": None, "ai_model": None}
    assert refused(call(client, "propose_changes", asked)).startswith("The change set is empty")
    assert not proposing


def test_the_trial_is_waited_for_and_given_with_at_most_50_findings(client: TestClient) -> None:
    issues = [{"kind": "schema", "severity": "error", "message": "x" * 5000} for _ in range(60)]
    trials = FakeTrials(
        trial("queued"),
        trial("running"),
        trial("issues", issues=issues, issue_count=60, created={"new-1": "1Xezbq735AdBO_4DerG66G"}, notes=[]),
    )
    client.app.state.ifcgraph = trials  # ty: ignore[unresolved-attribute]
    asked = {"project_id": CLOUD, "topic_guid": TOPIC, "wait_seconds": 5}
    answer = ok(call(client, "get_proposal", asked))
    assert answer["state"] == "issues" and answer["issue_count"] == 60 and answer["truncated"] is True
    assert len(answer["issues"]) == 50 and len(answer["issues"][0]["message"]) == 1000
    assert answer["created"] == {"new-1": "1Xezbq735AdBO_4DerG66G"} and answer["notes"] == []
    assert trials.asked[0] == {"user_id": USER, "project_id": CLOUD, "topic_guid": TOPIC}
    at_once = FakeTrials(trial("queued"))
    client.app.state.ifcgraph = at_once  # ty: ignore[unresolved-attribute]
    assert ok(call(client, "get_proposal", {**asked, "wait_seconds": None}))["state"] == "queued"
    assert len(at_once.asked) == 1, "null answers at once"
    too_long = refused(call(client, "get_proposal", {**asked, "wait_seconds": 21}))
    assert too_long.startswith("Invalid arguments: wait_seconds:")
    client.app.state.ifcgraph = FakeTrials(None)  # ty: ignore[unresolved-attribute]
    assert refused(call(client, "get_proposal", asked)) == "This topic has no change set that was tried"


def test_the_proposals_of_a_document_are_listed_without_addresses(tmp_path: Path) -> None:
    row = {"project_id": CLOUD, "topic_guid": TOPIC, "title": "T" * 300, "description": "D" * 300, "state": "clean",
           "base_version_index": 3, "change_count": 2, "author": "anna", "checked_at": None, "version_index": None}  # fmt: skip
    graph = DraftGraph(proposal_rows=[row, {**row, "topic_guid": "x"}])
    with endpoint(tmp_path, graph, principal(), ifcgraph_enabled=True) as client:
        answer = ok(call(client, "list_proposals", {"document_id": DOCUMENT, "limit": 1}))
        assert refused(call(client, "list_proposals", {"document_id": "nope", "limit": None})) == (
            change_sets.NO_DOCUMENT
        )
    (listed,) = answer["proposals"]
    assert answer["truncated"] is True
    assert listed["project_id"] == CLOUD and listed["topic_guid"] == TOPIC and listed["state"] == "clean"
    assert listed["title"] == "T" * 200 and listed["description"] == "D" * 200
    assert not any("url" in key for key in listed), "the addresses are the REST API's"
    (query,) = [params for query, params in graph.calls if "skip" in params]
    assert query["skip"] == 0 and query["limit"] == 2 and query["user_id"] == USER


# -- the draft repository ------------------------------------------------------------------------------------------


def test_every_statement_on_a_draft_starts_at_the_user_and_takes_only_parameters() -> None:
    for statement in (drafts.OPEN, drafts.GET, drafts.TAKE, drafts.SAVE):
        assert re.match(r"\s*MATCH \(u?:User \{id: \$user_id\}\)-\[:MEMBER_OF\]->", statement), statement
        for inside in re.findall(r"\{([^}]*)\}", statement):  # a pattern's map holds parameters and two constants
            for pair in inside.split(","):
                assert re.fullmatch(r"\s*\w+: (\$\w+|'\[\]'|0)\s*", pair), pair
    assert "WHERE d.user_id = $user_id AND d.expires_at > $now" in drafts.GET
    assert "WHERE open < $max_open" in drafts.OPEN
    assert drafts.TAKE.index("SET d.expires_at") < drafts.TAKE.index("RETURN"), "the lock before the read"


def _with(steps: list[dict[str, Any]]) -> Any:
    return lambda found: replace(found, steps=steps)


async def test_a_change_runs_in_one_transaction_and_a_refusal_writes_nothing() -> None:
    graph = DraftGraph()
    repository = ChangeSetDraftRepository(graph)  # ty: ignore[invalid-argument-type]
    draft = await repository.open(user_id=USER, project_id=CLOUD, document_id=DOCUMENT, version_index=3)
    assert draft is not None and draft.steps == [] and draft.base == {"document_id": DOCUMENT, "version_index": 3}
    assert await repository.open(user_id="u-bert", project_id=CLOUD, document_id=DOCUMENT, version_index=3) is None

    def boom(found: Any) -> Any:
        raise RuntimeError("refused")

    with pytest.raises(RuntimeError):
        await repository.update(user_id=USER, changeset_id=draft.changeset_id, change=boom)
    large = [{"tool": "assign", "ids": [1], "storey": "y" * 11_000, "material": None}] * 199
    for steps, words in (
        ([{"tool": "assign"}] * 201, "at most 200 steps"),
        ([{"tool": "transform_elements", "dx": float("nan")}], "too large for JSON"),
        (large, "at most 2 MB"),
    ):
        with pytest.raises(DraftRefused, match=words):
            await repository.update(user_id=USER, changeset_id=draft.changeset_id, change=_with(steps))
    assert graph.drafts[draft.changeset_id]["steps"] == "[]" and graph.transactions == 4
    assert drafts.SAVE not in [query for query, _params in graph.draft_queries()], "nothing saved by a refusal"
    changed = await repository.update(user_id=USER, changeset_id=draft.changeset_id, change=_with([{"tool": "x"}]))
    assert changed is not None and changed.steps == [{"tool": "x"}] and changed.expires_at >= draft.expires_at
    assert [query for query, _params in graph.draft_queries()][-2:] == [drafts.TAKE, drafts.SAVE]
    assert all(params["user_id"] in (USER, "u-bert") for _query, params in graph.draft_queries())
    assert await repository.get(user_id="u-bert", changeset_id=draft.changeset_id) is None
    assert await repository.update(user_id="u-bert", changeset_id=draft.changeset_id, change=boom) is None
