# This file was generated with the assistance of an AI coding tool.
"""The IFC converter on the fixture model (skipped when IfcOpenShell is not installed)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from opencde.ifcgraph.worker import main as worker_main
from tests.conftest import FIXTURES_DIR

pytest.importorskip("ifcopenshell", reason="the ifc-lpg extra is not installed")

from opencde.ifcgraph.convert import convert

MODEL = FIXTURES_DIR / "three_walls_gtin.ifc"
WALLS = ("1Xezbq735AdBO_4DerG66G", "3eT96F_cnDsOufCEsotwtp", "3k3LbXmTfDWODxdSuyCGYE")


def test_convert_produces_labelled_nodes_and_attribute_edges() -> None:
    records = list(convert(MODEL))
    header = next(r for r in records if r["t"] == "h")
    nodes = [r for r in records if r["t"] == "n"]
    edges = [r for r in records if r["t"] == "e"]
    assert header["schema"] == "IFC2X3" and header["ifc_project_guid"] == "1CGyzxdzHaJybf9L4wHy3R"
    assert header["entities"] == len(nodes) and header["relationships"] == len(edges)
    assert header["skipped"] > 0, "geometry is left out by default"
    assert not any("IfcCartesianPoint" in n["labels"] for n in nodes)

    # IfcOpenShell goes through a file in an order that differs between platforms.
    walls = sorted((n for n in nodes if n["props"].get("GlobalId") in WALLS), key=lambda n: n["props"]["Name"])
    assert len(walls) == 3
    labels = walls[0]["labels"]
    assert (
        labels[0] == "IfcWallStandardCase"
        and "IfcWall" in labels
        and "IfcProduct" in labels
        and labels[-1] == "IfcRoot"
    )
    assert walls[0]["props"]["ifc_class"] == "IfcWallStandardCase" and walls[0]["props"]["Name"] == "YVT-A"
    assert "OwnerHistory" not in walls[0]["props"]

    by_step = {n["step"]: n for n in nodes}
    gtin_values = {
        n["props"]["NominalValue"]
        for n in nodes
        if n["props"].get("ifc_class") == "IfcPropertySingleValue" and n["props"].get("Name") == "GTIN"
    }
    assert gtin_values == {"1", "2", "3"}, "select values are unwrapped to their literal"
    wall_step = walls[0]["step"]
    defined_by = [e for e in edges if e["a"] == wall_step and e["type"] == "IsDefinedBy"]
    assert defined_by, "inverse attributes become edges too"
    relating = [e for e in edges if e["a"] == defined_by[0]["b"] and e["type"] == "RelatingPropertyDefinition"]
    assert relating and by_step[relating[0]["b"]]["props"]["ifc_class"] == "IfcPropertySet"
    assert all(e["a"] in by_step and e["b"] in by_step for e in edges), "edges only between exported nodes"
    owner_histories = [n for n in nodes if n["props"]["ifc_class"] == "IfcOwnerHistory"]
    assert len(owner_histories) == 1, "only the project's owner history is kept"
    linked_from = [by_step[e["a"]]["props"]["ifc_class"] for e in edges if e["b"] == owner_histories[0]["step"]]
    assert linked_from == ["IfcProject"], "and every other entity that shares it has no edge to it"


def test_geometry_can_be_included_and_limits_are_enforced(tmp_path: Path) -> None:
    with_geometry = [r for r in convert(MODEL, include_geometry=True) if r["t"] == "n"]
    assert any("IfcCartesianPoint" in n["labels"] for n in with_geometry)
    with pytest.raises(Exception, match="more than 10 entities"):
        list(convert(MODEL, max_entities=10))

    out = tmp_path / "records.jsonl"
    assert worker_main([str(MODEL), str(out)]) == 0
    kinds = [json.loads(line)["t"] for line in out.read_text().splitlines()]
    assert kinds.index("h") > 0 and all(k == "e" for k in kinds[kinds.index("h") + 1 :]), "nodes, header, then edges"
    assert worker_main([str(MODEL), str(out), "--max-entities", "10"]) == 3
    assert worker_main([str(tmp_path / "missing.ifc"), str(out)]) == 4
