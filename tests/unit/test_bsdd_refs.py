# This file was generated with the assistance of an AI coding tool.
"""The worker that reads an upload's references to buildingSMART's Data Dictionary (OB-42), on files built here: which
references count as bSDD's and how their URI is made, the objects they are on, and the Pset_ and Qto_ sets."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("ifcopenshell", reason="the ifc-lpg extra is not installed")

from opencde.ifcgraph import bsdd_refs
from opencde.ifcgraph.bsdd_refs import answer

IFC = "https://identifier.buildingsmart.org/uri/buildingsmart/ifc/4.3"
NOWHERE = "https://identifier.buildingsmart.org/uri/example/nosuch/1.0/class/X"


def guid() -> str:
    import ifcopenshell.guid

    return ifcopenshell.guid.new()


def model_with_references(path: Path, schema: str = "IFC4X3") -> dict[str, Any]:
    """A file with a classification reference bSDD knows, one it does not, one that is not bSDD's, a property set of
    the IFC dictionary with a property that is not in it, and a set of one's own. Returns the GlobalIds and STEP ids."""
    import ifcopenshell

    model = ifcopenshell.file(schema=schema)
    model.create_entity("IfcProject", GlobalId=guid(), Name="P")
    wall = model.create_entity("IfcWall", GlobalId=guid(), Name="W1")
    door = model.create_entity("IfcDoor", GlobalId=guid(), Name="D1")
    where = "Specification" if schema.startswith("IFC4X3") else "Location"  # renamed in IFC 4.3
    ifc = model.create_entity("IfcClassification", Source="buildingSMART", Name="IFC", **{where: IFC})
    known = model.create_entity(
        "IfcClassificationReference", Identification="IfcWall", Name="Wall", ReferencedSource=ifc
    )
    unknown = model.create_entity("IfcClassificationReference", Location=NOWHERE, Identification="X", Name="Nothing")
    other = model.create_entity("IfcClassificationReference", Location="https://example.org/dict/class/Y")
    for related, reference in (([wall, door], known), ([door], unknown), ([wall], other)):
        model.create_entity(
            "IfcRelAssociatesClassification", GlobalId=guid(), RelatedObjects=related, RelatingClassification=reference
        )

    def single(name: str, value: str) -> Any:
        return model.create_entity(
            "IfcPropertySingleValue", Name=name, NominalValue=model.create_entity("IfcLabel", value)
        )

    common = model.create_entity(
        "IfcPropertySet",
        GlobalId=guid(),
        Name="Pset_WallCommon",
        HasProperties=[single("FireRating", "REI60"), single("Bogus", "x"), single("Reference", "W-1")],
    )
    custom = model.create_entity(
        "IfcPropertySet", GlobalId=guid(), Name="Pset_Custom", HasProperties=[single("A", "a")]
    )
    model.create_entity("IfcPropertySet", GlobalId=guid(), Name="Custom_Other", HasProperties=[single("B", "b")])
    for related, definition in (([wall], common), ([door], custom)):
        model.create_entity(
            "IfcRelDefinesByProperties", GlobalId=guid(), RelatedObjects=related, RelatingPropertyDefinition=definition
        )
    model.write(str(path))
    return {
        "wall": wall.GlobalId,
        "door": door.GlobalId,
        "known": known.id(),
        "unknown": unknown.id(),
        "pset": common.id(),
    }


@pytest.mark.parametrize("schema", ["IFC4", "IFC4X3"])
def test_the_worker_lists_the_bsdd_references_with_their_objects_and_the_sets(tmp_path: Path, schema: str) -> None:
    path = tmp_path / "refs.ifc"
    ids = model_with_references(path, schema)
    found = answer(path)
    assert found["schema"] == schema and found["cut"] is False
    by_step = {reference["step_id"]: reference for reference in found["references"]}
    assert set(by_step) == {ids["known"], ids["unknown"]}, "a reference on another host is not bSDD's"
    known = by_step[ids["known"]]
    assert known["uri"] == f"{IFC}/class/IfcWall", "the identification under the classification's dictionary"
    assert known["attribute"] == "Identification" and known["identification"] == "IfcWall"
    assert known["location"] is None and known["name"] == "Wall"
    assert known["classification"] == {"name": "IFC", "source": "buildingSMART", "location": IFC}
    assert known["objects"] == [
        {"global_id": ids["wall"], "ifc_class": "IfcWall"},
        {"global_id": ids["door"], "ifc_class": "IfcDoor"},
    ]
    assert known["object_count"] == 2
    unknown = by_step[ids["unknown"]]
    assert (unknown["uri"], unknown["attribute"], unknown["location"]) == (NOWHERE, "Location", NOWHERE)
    assert unknown["classification"] is None and unknown["objects"] == [
        {"global_id": ids["door"], "ifc_class": "IfcDoor"}
    ]
    sets = found["property_sets"]
    assert set(sets) == {"Pset_WallCommon", "Pset_Custom"}, "only the sets named as IFC's own"
    assert sets["Pset_WallCommon"] == {
        "step_id": ids["pset"],
        "properties": ["Bogus", "FireRating", "Reference"],
        "objects": [{"global_id": ids["wall"], "ifc_class": "IfcWall"}],
        "object_count": 1,
    }
    assert sets["Pset_Custom"]["properties"] == ["A"] and sets["Pset_Custom"]["objects"][0]["ifc_class"] == "IfcDoor"


def test_an_ifc2x3_file_names_its_classes_by_item_reference_under_the_source(tmp_path: Path) -> None:
    """IFC2X3's classification has no URI of its own, so a bSDD dictionary URI in its ``Source`` is read instead."""
    import ifcopenshell

    model = ifcopenshell.file(schema="IFC2X3")
    cci = model.create_entity(
        "IfcClassification",
        Source="https://identifier.buildingsmart.org/uri/molio/cciconstruction/1.0",
        Edition="1.0",
        Name="CCI",
    )
    reference = model.create_entity(
        "IfcClassificationReference", ItemReference="L-BD", Name="Wall structure", ReferencedSource=cci
    )
    loose = model.create_entity("IfcClassificationReference", ItemReference="L-XX", Name="No dictionary")
    length = model.create_entity("IfcQuantityLength", Name="Length", LengthValue=2.0)
    model.create_entity("IfcElementQuantity", GlobalId=guid(), Name="Qto_WallBaseQuantities", Quantities=[length])
    path = tmp_path / "cci.ifc"
    model.write(str(path))
    found = answer(path)
    assert found["schema"] == "IFC2X3"
    [cci_reference] = found["references"]
    assert cci_reference["step_id"] == reference.id() and loose.id() not in [r["step_id"] for r in found["references"]]
    assert cci_reference["uri"] == "https://identifier.buildingsmart.org/uri/molio/cciconstruction/1.0/class/L-BD"
    assert (cci_reference["attribute"], cci_reference["identification"]) == ("ItemReference", "L-BD")
    assert cci_reference["objects"] == [] and cci_reference["object_count"] == 0
    assert found["property_sets"]["Qto_WallBaseQuantities"]["properties"] == ["Length"]


def test_the_answer_is_bounded_and_says_so(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "refs.ifc"
    model_with_references(path)
    monkeypatch.setattr(bsdd_refs, "MAX_REFERENCES", 1)
    found = answer(path)
    assert len(found["references"]) == 1 and found["cut"] is True
    monkeypatch.setattr(bsdd_refs, "MAX_REFERENCES", 1_000)
    monkeypatch.setattr(bsdd_refs, "MAX_PROPERTIES", 2)
    found = answer(path)
    assert found["property_sets"]["Pset_WallCommon"]["properties"] == ["Bogus", "FireRating"] and found["cut"] is True


def test_the_worker_answers_on_stdout(tmp_path: Path) -> None:
    path = tmp_path / "refs.ifc"
    ids = model_with_references(path)
    command = [sys.executable, "-m", "opencde.ifcgraph.bsdd_refs", str(path)]
    run = subprocess.run(command, capture_output=True, text=True, check=False)  # noqa: S603
    assert run.returncode == 0, run.stderr
    found = json.loads(run.stdout)
    assert {reference["step_id"] for reference in found["references"]} == {ids["known"], ids["unknown"]}
    missing = [*command[:-1], str(tmp_path / "none.ifc")]
    run = subprocess.run(missing, capture_output=True, text=True, check=False)  # noqa: S603
    assert run.returncode == 2 and "error" in json.loads(run.stderr.strip().splitlines()[-1])
