# This file was generated with the assistance of an AI coding tool.
"""The form of a change set and its published schema (ADR 0021): what passes, what does not, and what the schema
says about itself. The route and the snippet upload are proved against a database in
``tests/integration/test_ifc_changes.py``."""

from __future__ import annotations

import json
from typing import Any

from opencde.documents.changes import (
    MAX_CHANGES,
    SCHEMA_DIALECT,
    SCHEMA_PATH,
    SNIPPET_TYPE,
    change_set_schema,
    problems,
)

GUID = "1Xezbq735AdBO_4DerG66G"


def change_set(**changes: Any) -> dict[str, Any]:
    return {
        "schema": f"https://cde.example{SCHEMA_PATH}",
        "base": {"document_id": "11111111-2222-4333-8444-555555555555", "version_index": 3},
        "provenance": {"user": "anna", "ai_model": "claude-opus-5-5", "tool_call": "rename_element"},
        "changes": [
            {"guid": GUID, "attribute": "Name", "op": "set", "old": "Wall 1", "new": "Wall 1b"},
            {
                "guid": GUID,
                "path": "IsDefinedBy[0].RelatingPropertyDefinition.HasProperties[2]",
                "attribute": "NominalValue",
                "op": "set",
                "new": {"type": "IfcLengthMeasure", "value": 3.2},
            },
            {"step_id": 99, "attribute": "Items", "op": "add", "new": {"step_id": 120}},
            {"step_id": 99, "attribute": "Items", "op": "remove", "index": 0},
            {"step_id": 5, "attribute": "PredefinedType", "op": "set", "new": {"enum": "NOTDEFINED"}, "copy": True},
            {"step_id": 7, "attribute": "CoordList", "op": "set", "new": [[1.0, 2.0, 3.0], [4, 5, 6]]},
        ],
        **changes,
    }


def test_a_change_set_names_its_base_its_proposer_and_each_change_on_one_attribute() -> None:
    assert problems(change_set()) == []
    assert problems(change_set(provenance={"user": "anna"})) == [], "an AI model and a tool call are optional"


def test_what_is_not_a_change_set_is_named_without_the_data() -> None:
    assert problems({"schema": "x"}) == [
        "base: Field required",
        "provenance: Field required",
        "changes: Field required",
    ]
    both = change_set(changes=[{"guid": GUID, "step_id": 1, "attribute": "Name", "op": "set", "new": "x"}])
    assert problems(both) == [
        "changes.0: Value error, name the instance by step_id or by guid, not both and not neither"
    ]
    assert problems(change_set(changes=[{"step_id": 1, "attribute": "name", "op": "move"}])) == [
        "changes.0.attribute: String should match pattern '^[A-Z][A-Za-z0-9]*$'",
        "changes.0.op: Input should be 'set', 'add', 'remove' or 'delete'",
    ]
    path_without_guid = change_set(changes=[{"step_id": 1, "path": "Items[0]", "attribute": "Name", "op": "set"}])
    assert problems(path_without_guid) == ["changes.0: Value error, a path starts from a guid"]
    assert problems(change_set(changes=[{"step_id": 1, "attribute": "Items", "op": "remove"}])) == [
        "changes.0: Value error, remove names the member by index or by its old value"
    ]
    too_deep = change_set(changes=[{"step_id": 7, "attribute": "X", "op": "set", "new": [[[1]]]}])
    found = problems(too_deep)
    assert found and all(problem.startswith("changes.0.new") for problem in found), found
    assert "[[[1]]]" not in " ".join(found) and len(found) <= 5, "never the data, never a wall of text"
    assert problems(change_set(changes=[])) == ["changes: List should have at least 1 item after validation, not 0"]
    unknown = change_set(changes=[{"step_id": 1, "attribute": "Name", "op": "set", "new": "x", "extra": 1}])
    assert problems(unknown) == ["changes.0.extra: Extra inputs are not permitted"]
    assert problems(change_set(base={"document_id": "not-a-uuid", "version_index": 1}))[0].startswith(
        "base.document_id: String should match pattern"
    )


def test_the_schema_names_itself_and_holds_the_example() -> None:
    schema = change_set_schema("https://cde.example")
    assert schema["$schema"] == SCHEMA_DIALECT and schema["$id"] == f"https://cde.example{SCHEMA_PATH}"
    assert schema["title"] == SNIPPET_TYPE and schema["additionalProperties"] is False
    assert set(schema["required"]) == {"schema", "base", "provenance", "changes"}
    assert schema["properties"]["changes"]["maxItems"] == MAX_CHANGES
    change = schema["$defs"]["Change"]
    assert set(change["properties"]) == {"step_id", "guid", "path", "attribute", "op", "index", "old", "new", "copy"}
    assert change["properties"]["op"]["enum"] == ["set", "add", "remove", "delete"]
    assert json.loads(json.dumps(schema)) == schema, "plain JSON"
    assert all(
        "Reference" in ref
        or "Typed" in ref
        or "Enumeration" in ref
        or "Base" in ref
        or "Change" in ref
        or "Provenance" in ref
        for ref in schema["$defs"]
    )


def test_a_deletion_names_an_instance_by_its_step_id_and_nothing_else() -> None:
    """IFC-LPG F13 a: what no GlobalId reaches is named by its STEP id alone, and a deletion changes no attribute."""
    deleting = change_set(changes=[{"step_id": 9001, "op": "delete"}])
    assert problems(deleting) == []
    assert problems(change_set(changes=[{"guid": GUID, "op": "delete"}])), "a rooted entity is not deleted this way"
    assert problems(change_set(changes=[{"step_id": 9001, "attribute": "Coordinates", "op": "delete"}]))
    assert problems(change_set(changes=[{"step_id": 99, "op": "set", "new": "no attribute"}])), "set names one"
