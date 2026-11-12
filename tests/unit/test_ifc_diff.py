# This file was generated with the assistance of an AI coding tool.
"""The difference between two files, element by element (ADR 0021): what was added, removed and changed, by path.
The route and the page are proved against a database in ``tests/integration/test_ifc_diff.py``."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests.conftest import FIXTURES_DIR

pytest.importorskip("ifcopenshell", reason="the ifc-db extra is not installed")

from opencde.ifcgraph.diff import compare

MODEL = FIXTURES_DIR / "three_walls_gtin.ifc"
WALLS = ("1Xezbq735AdBO_4DerG66G", "3eT96F_cnDsOufCEsotwtp")


def edited_copy(path: Path) -> tuple[str, str]:
    """The fixture with one wall renamed and moved, its GTIN changed, one wall removed and one wall added."""
    import ifcopenshell
    import ifcopenshell.api
    import ifcopenshell.guid
    import ifcopenshell.util.element

    model = ifcopenshell.open(str(MODEL))
    first, second = model.by_guid(WALLS[0]), model.by_guid(WALLS[1])
    first.Name = "Renamed"
    location = first.ObjectPlacement.RelativePlacement.Location
    x, y, z = location.Coordinates
    location.Coordinates = (x + 100.0, y, z)
    for rel in first.IsDefinedBy:
        if rel.is_a("IfcRelDefinesByProperties") and rel.RelatingPropertyDefinition.Name == "Reuse":
            rel.RelatingPropertyDefinition.HasProperties[0].NominalValue = model.create_entity("IfcLabel", "4")
    new_wall = ifcopenshell.util.element.copy(model, second)
    new_wall.GlobalId = ifcopenshell.guid.new()
    new_wall.Name = "Added"
    ifcopenshell.api.run("root.remove_product", model, product=second)
    model.write(str(path))
    return new_wall.GlobalId, WALLS[1]


def test_the_difference_names_what_was_added_removed_and_changed(tmp_path: Path) -> None:
    edited = tmp_path / "edited.ifc"
    added_guid, _ = edited_copy(edited)
    report = compare(MODEL, edited)
    assert [element["guid"] for element in report["added"]] == [added_guid]
    assert report["added"][0]["name"] == "Added" and report["added"][0]["type"].startswith("IfcWall")
    assert [element["guid"] for element in report["removed"]] == [WALLS[1]]
    assert [element["guid"] for element in report["changed"]] == [WALLS[0]], report["changed"]
    changed = report["changed"][0]
    paths = {attribute["path"]: attribute for attribute in changed["attributes"]}
    assert paths["Name"] == {"path": "Name", "old": "YVT-A", "new": "Renamed"}
    assert paths["Reuse.GTIN"] == {"path": "Reuse.GTIN", "old": "3", "new": "4"}
    assert paths["ObjectPlacement"]["old"][0][3] + 100.0 == pytest.approx(paths["ObjectPlacement"]["new"][0][3])
    assert "Representation" not in paths, "the shape itself did not change"
    assert changed["storey"] == "1. etasje" and report["same"] > 0 and report["truncated"] is False


def test_the_same_file_differs_in_nothing_and_the_worker_answers_on_stdout(tmp_path: Path) -> None:
    report = compare(MODEL, MODEL)
    assert report["added"] == [] and report["removed"] == [] and report["changed"] == [] and report["same"] > 3
    run = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "opencde.ifcgraph.diff", str(MODEL), str(MODEL), "--max-entries", "5"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert run.returncode == 0, run.stderr
    assert json.loads(run.stdout)["same"] == report["same"]
    broken = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "opencde.ifcgraph.diff", str(MODEL), str(tmp_path / "missing.ifc")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert broken.returncode == 2 and json.loads(broken.stderr.strip().splitlines()[-1])["error"]
