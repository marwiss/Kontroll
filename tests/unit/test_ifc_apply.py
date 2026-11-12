# This file was generated with the assistance of an AI coding tool.
"""Applying a change set to a file (ADR 0021): by GlobalId and path, by STEP id, on aggregates, on a copy, and what
is skipped and why. The proposal around it is proved against a database in ``tests/integration/test_ifc_proposal.py``."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from tests.conftest import FIXTURES_DIR

pytest.importorskip("ifcopenshell", reason="the ifc-lpg extra is not installed")

from opencde.ifcgraph.apply import apply_all, from_ifc

MODEL = FIXTURES_DIR / "three_walls_gtin.ifc"
WALL = "1Xezbq735AdBO_4DerG66G"
PATH_TO_GTIN = "IsDefinedBy[0].RelatingPropertyDefinition.HasProperties[0]"


def apply(tmp_path: Path, *changes: dict[str, Any]) -> tuple[dict[str, Any], Any]:
    import ifcopenshell

    out = tmp_path / "out.ifc"
    summary = apply_all(MODEL, list(changes), out)
    return summary, ifcopenshell.open(str(out))


def test_changes_reach_an_instance_by_guid_and_path_or_by_step_id(tmp_path: Path) -> None:
    summary, model = apply(
        tmp_path,
        {"guid": WALL, "attribute": "Name", "op": "set", "old": "YVT-A", "new": "YVT-A2"},
        {
            "guid": WALL,
            "path": PATH_TO_GTIN,
            "attribute": "NominalValue",
            "op": "set",
            "old": {"type": "IfcLabel", "value": "3"},
            "new": {"type": "IfcLabel", "value": "4"},
        },
        {"step_id": 287, "attribute": "Description", "op": "set", "new": "set by its number"},
        {"step_id": 202, "attribute": "Points", "op": "add", "new": {"step_id": 196}},
        {"step_id": 202, "attribute": "Points", "op": "remove", "index": 0},
    )
    assert summary["problems"] == [] and summary["applied"] == 5 and summary["count"] == 5
    assert sorted(summary["touched"]) == [202, 242, 287]
    wall = model.by_guid(WALL)
    assert wall.Name == "YVT-A2"
    gtin = wall.IsDefinedBy[0].RelatingPropertyDefinition.HasProperties[0]
    assert gtin.id() == 287 and from_ifc(gtin.NominalValue) == {"type": "IfcLabel", "value": "4"}
    assert gtin.Description == "set by its number"
    points = model.by_id(202).Points
    assert len(points) == 5 and points[-1].id() == 196 and points[0].id() == 196


def test_a_copy_leaves_the_shared_instance_to_the_others(tmp_path: Path) -> None:
    import ifcopenshell

    before = ifcopenshell.open(str(MODEL))
    location = before.by_guid(WALL).ObjectPlacement.RelativePlacement.Location
    summary, model = apply(
        tmp_path,
        {
            "guid": WALL,
            "path": "ObjectPlacement.RelativePlacement.Location",
            "attribute": "Coordinates",
            "op": "set",
            "new": [1.0, 2.0, 3.0],
            "copy": True,
        },
    )
    assert summary["problems"] == [] and summary["applied"] == 1
    moved = model.by_guid(WALL).ObjectPlacement.RelativePlacement.Location
    assert moved.id() != location.id() and moved.Coordinates == (1.0, 2.0, 3.0)
    assert model.by_id(location.id()).Coordinates == location.Coordinates, "the original is as it was"


def test_what_cannot_be_applied_is_skipped_and_named(tmp_path: Path) -> None:
    summary, model = apply(
        tmp_path,
        {"guid": WALL, "attribute": "Name", "op": "set", "old": "not the name", "new": "x"},
        {"guid": "0000000000000000000000", "attribute": "Name", "op": "set", "new": "x"},
        {"step_id": 999_999, "attribute": "Name", "op": "set", "new": "x"},
        {"guid": WALL, "path": "NoSuchAttribute", "attribute": "Name", "op": "set", "new": "x"},
        {"guid": WALL, "attribute": "IsDefinedBy", "op": "set", "new": None},
        {"guid": WALL, "attribute": "Name", "op": "set", "new": {"step_id": 202}},
        {"guid": WALL, "attribute": "Name", "op": "set", "new": "applied all the same"},
        {"step_id": 202, "attribute": "Points", "op": "remove", "index": 99},
        {"guid": WALL, "path": "IsDefinedBy[0]", "attribute": "Name", "op": "set", "new": "x", "copy": True},
    )
    assert summary["applied"] == 1 and model.by_guid(WALL).Name == "applied all the same"
    errors = {problem["change"]: problem["error"] for problem in summary["problems"]}
    assert errors[0] == "Name no longer holds the old value"
    assert errors[1] == "no instance with GlobalId 0000000000000000000000"
    assert errors[2] == "no instance #999999"
    assert errors[3] == "IfcWallStandardCase has no attribute NoSuchAttribute"
    assert errors[4] == "IsDefinedBy is an inverse attribute; change the relationship instead"
    assert errors[5].startswith("Name does not take the value")
    assert errors[7] == "Points has no member 99"
    assert errors[8] == "copy needs a path whose last step is a forward attribute"
    assert "YVT" not in json.dumps(summary), "the problems never quote the file"


def test_the_worker_answers_on_stdout(tmp_path: Path) -> None:
    changes = tmp_path / "changes.json"
    changes.write_text(
        json.dumps({"changes": [{"guid": WALL, "attribute": "Name", "op": "set", "new": "from the worker"}]}),
        encoding="utf-8",
    )
    out = tmp_path / "out.ifc"
    run = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "opencde.ifcgraph.apply", str(MODEL), str(changes), str(out)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert run.returncode == 0, run.stderr
    assert json.loads(run.stdout)["applied"] == 1 and out.exists()
    broken = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "opencde.ifcgraph.apply", str(MODEL), str(tmp_path / "missing.json"), str(out)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert broken.returncode == 2 and json.loads(broken.stderr.strip().splitlines()[-1])["error"]


def test_the_worker_reads_what_the_changes_point_at_in_the_change_sets_form(tmp_path: Path) -> None:
    """For the conflicts of an approval: the base's and the latest version's values beside the proposal's."""
    changes = [
        {"guid": WALL, "attribute": "Name"},
        {"guid": WALL, "path": "OwnerHistory", "attribute": "ChangeAction"},
        {"guid": WALL, "path": "OwnerHistory", "attribute": "CreationDate"},
        {"guid": WALL, "attribute": "OwnerHistory"},
        {"guid": WALL, "path": PATH_TO_GTIN, "attribute": "NominalValue"},
        {"guid": WALL, "attribute": "NoSuchAttribute"},
        {"guid": "0NotInTheModel00000000", "attribute": "Name"},
    ]
    listed = tmp_path / "changes.json"
    listed.write_text(json.dumps({"changes": changes}), encoding="utf-8")
    run = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "opencde.ifcgraph.apply", str(MODEL), str(listed), "--read"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert run.returncode == 0, run.stderr
    values = json.loads(run.stdout)["values"]
    assert values[0] == {"value": "YVT-A"}
    assert values[1] == {"value": {"enum": "NOCHANGE"}}, "an enumeration in the change set's form"
    assert values[2] == {"value": 1693857534}
    assert values[3] == {"value": {"step_id": 32}}, "an instance without a GlobalId by its STEP id"
    assert values[4]["value"]["type"] == "IfcLabel" and values[4]["value"]["value"] == "3"
    assert "error" in values[5] and "error" in values[6]
    assert not (tmp_path / "out.ifc").exists(), "nothing is written"


def test_an_instance_nothing_refers_to_is_deleted_and_one_still_referred_to_is_not(tmp_path: Path) -> None:
    """IFC-LPG F13 a: what no GlobalId reaches can be deleted by its STEP id, never what something refers to."""
    import ifcopenshell

    head, tail = MODEL.read_bytes().rsplit(b"ENDSEC;", 1)
    base = tmp_path / "loose.ifc"
    base.write_bytes(head + b"#9001=IFCCARTESIANPOINT((9.,9.,9.));\r\n" + b"ENDSEC;" + tail)
    out = tmp_path / "out.ifc"
    summary = apply_all(base, [{"step_id": 9001, "op": "delete"}, {"step_id": 196, "op": "delete"}], out)
    assert summary["applied"] == 1 and summary["touched"] == [9001]
    assert summary["problems"] == [{"change": 1, "error": "#196 is still referred to; remove what refers to it first"}]
    model = ifcopenshell.open(str(out))
    with pytest.raises(RuntimeError):
        model.by_id(9001)
    assert model.by_id(196).is_a("IfcCartesianPoint")


# -- Dataspatium's write tools in a change set (``ops``), before its changes --------------------------------------

OTHER_WALL = "3eT96F_cnDsOufCEsotwtp"  # YVT-B, #373
STOREY_RELATIONSHIP = "0PUNS2OuLwupG5o8M6iDor"  # the storey's IfcRelContainedInSpatialStructure, #257
LOCATION = f"{WALL}/ObjectPlacement.RelativePlacement.Location.Coordinates"
NEW_GTIN = {"tool": "set_properties", "ids": [WALL], "pset": "Reuse", "properties": {"GTIN": "4"}}
NEW_WALL = {"tool": "create_wall", "start": [0, 0], "end": [4, 0], "name": "New"}


def test_the_operations_come_first_and_a_change_they_made_counts_as_applied(tmp_path: Path) -> None:
    """The app sends the changes its operations make to existing instances beside them, for the merge: a change the
    operations made already counts as applied and is not made twice, one they did not make is applied as any, and
    one that says otherwise than the operations did is an issue."""
    import ifcopenshell

    ops = [
        NEW_GTIN,
        NEW_WALL,
        {"tool": "create_storeys_and_grid", "storeys": [{"name": "2. etasje", "elevation": 3}]},
        {"tool": "assign", "ids": [OTHER_WALL], "storey": "2. etasje"},
    ]
    made = [
        {
            "guid": WALL,
            "path": PATH_TO_GTIN,
            "attribute": "NominalValue",
            "op": "set",
            "old": {"type": "IfcLabel", "value": "3"},
            "new": {"type": "IfcLabel", "value": "4"},
        },
        {"guid": STOREY_RELATIONSHIP, "attribute": "RelatedElements", "op": "remove", "old": {"guid": OTHER_WALL}},
    ]
    rename = {"guid": OTHER_WALL, "attribute": "Name", "op": "set", "old": "YVT-B", "new": "YVT-B2"}
    other = {**made[0], "new": {"type": "IfcLabel", "value": "5"}}
    out = tmp_path / "out.ifc"
    summary = apply_all(MODEL, [*made, rename, other], out, ops=ops, proposer="anna")
    assert summary["applied"] == 3 and summary["count"] == 4
    assert summary["problems"] == [{"change": 3, "error": "NominalValue no longer holds the old value"}]
    assert summary["ops"]["applied"] == summary["ops"]["count"] == 4 and summary["ops"]["failed"] is None
    model = ifcopenshell.open(str(out))
    assert from_ifc(model.by_id(287).NominalValue) == {"type": "IfcLabel", "value": "4"}
    assert model.by_guid(OTHER_WALL).Name == "YVT-B2"
    assert OTHER_WALL not in [element.GlobalId for element in model.by_guid(STOREY_RELATIONSHIP).RelatedElements]
    assert model.by_guid(summary["ops"]["created"]["new-1"]).Name == "New"
    assert {WALL, OTHER_WALL, summary["ops"]["created"]["new-1"]} <= set(summary["ops"]["objects"])


def test_an_operation_that_fails_leaves_the_changes_unapplied(tmp_path: Path) -> None:
    import ifcopenshell

    rename = {"guid": OTHER_WALL, "attribute": "Name", "op": "set", "new": "YVT-B2"}
    nowhere = {**NEW_WALL, "storey": "nowhere"}
    out = tmp_path / "out.ifc"
    summary = apply_all(MODEL, [rename], out, ops=[NEW_GTIN, nowhere, NEW_WALL], keep_theirs=[f"{WALL}/.Name"])
    assert summary["ops"]["failed"] == {
        "op": 1,
        "tool": "create_wall",
        "error": "no storey named 'nowhere'; the storeys are 1. etasje",
    }
    assert summary["ops"]["applied"] == 1 and summary["applied"] == 0 and summary["problems"] == []
    assert ifcopenshell.open(str(out)).by_guid(OTHER_WALL).Name == "YVT-B"


def test_keep_theirs_gives_each_key_back_the_value_the_file_held(tmp_path: Path) -> None:
    """A key given up gets the latest version's value back after the operations and the changes, also where an
    operation put a new instance on its path, as a move gives the wall a new point; the rest of the operations
    stand."""
    import ifcopenshell

    before = ifcopenshell.open(str(MODEL)).by_guid(WALL).ObjectPlacement.RelativePlacement.Location.Coordinates
    ops = [{"tool": "transform_elements", "ids": [WALL], "dx": 1, "dy": 0, "dz": 0}, NEW_GTIN, NEW_WALL]
    rename = {"guid": OTHER_WALL, "attribute": "Name", "op": "set", "new": "ours"}
    out = tmp_path / "out.ifc"
    summary = apply_all(
        MODEL, [rename], out, ops=ops, keep_theirs=[LOCATION, "#287.NominalValue", f"{OTHER_WALL}/.Name"]
    )
    assert summary["problems"] == [] and summary["ops"]["failed"] is None
    model = ifcopenshell.open(str(out))
    moved = model.by_guid(WALL).ObjectPlacement.RelativePlacement.Location
    assert moved.Coordinates == before, "where the latest version had it, on the point the move made"
    assert from_ifc(model.by_id(287).NominalValue) == {"type": "IfcLabel", "value": "3"}
    assert model.by_guid(OTHER_WALL).Name == "YVT-B" and model.by_guid(summary["ops"]["created"]["new-1"])

    gone = apply_all(MODEL, [], out, ops=ops, keep_theirs=["#999999.Name", f"{WALL}/.Nothing", f"{WALL}.IsDefinedBy"])
    assert gone["problems"] == [
        {"keep": 0, "error": "no instance #999999"},
        {"keep": 1, "error": "IfcWallStandardCase has no attribute Nothing"},
        {"keep": 2, "error": "IsDefinedBy is an inverse attribute"},
    ]
    deleted = apply_all(
        MODEL, [], out, ops=[{"tool": "delete_elements", "ids": [WALL], "confirm": True}], keep_theirs=[LOCATION]
    )
    assert deleted["problems"] == [{"keep": 0, "error": f"no instance with GlobalId {WALL}"}], "nothing to give back"


def test_the_worker_applies_the_operations_and_names_the_proposer(tmp_path: Path) -> None:
    import ifcopenshell

    changes = tmp_path / "changes.json"
    changes.write_text(json.dumps({"changes": [], "ops": [NEW_WALL], "ops_form": "dataspatium-tools/1"}), "utf-8")
    out = tmp_path / "out.ifc"
    run = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "opencde.ifcgraph.apply", str(MODEL), str(changes), str(out), "--proposer=-anna"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert run.returncode == 0, run.stderr
    answer = json.loads(run.stdout)
    assert answer["count"] == 0 and answer["ops"]["applied"] == 1
    assert answer["ops"]["notes"] == [
        "IsExternal was left out on the walls of storey 1. etasje that the change set made or changed, and on their "
        "doors and windows: 8 wall ends stand open, so the app cannot tell outside from inside"
    ], "the new wall stands alone, so the topology tells no outside"
    model = ifcopenshell.open(str(out))
    wall = model.by_guid(answer["ops"]["created"]["new-1"])
    container = next(iter(wall.ContainedInStructure)).OwnerHistory
    assert container.LastModifyingUser.ThePerson.Id == "-anna", "the proposer, also with a name like an option"
