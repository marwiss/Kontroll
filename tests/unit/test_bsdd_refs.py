# This file was generated with the assistance of an AI coding tool.
"""The worker that reads an upload's references to buildingSMART's Data Dictionary (OB-42), on files built here: which
references count as bSDD's and how their URI is made, the objects they are on, the properties that name a bSDD
property, and the Pset_ and Qto_ sets; and the bSDD URIs of an IDS document."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("ifcopenshell", reason="the ifc-db extra is not installed")

from opencde.ifcgraph import bsdd_refs
from opencde.ifcgraph.bsdd_refs import answer, ids_uris
from tests.conftest import FIXTURES_DIR

IFC = "https://identifier.buildingsmart.org/uri/buildingsmart/ifc/4.3"
NOWHERE = "https://identifier.buildingsmart.org/uri/example/nosuch/1.0/class/X"
FIRE_RATING = f"{IFC}/prop/FireRating"
BOGUS = "https://identifier.buildingsmart.org/uri/example/nosuch/1.0/prop/Bogus"
BSDD_IDS = FIXTURES_DIR / "bsdd.ids"  # names classes and properties by their bSDD URIs


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


def model_with_property_uris(path: Path, schema: str = "IFC4X3") -> dict[str, Any]:
    """A file whose properties name bSDD properties in their ``Specification``, or in their ``Description`` before
    IFC 4.3: FireRating in the Pset_WallCommon of two walls, which bSDD knows, and Bogus in a set of one's own on a
    door, which it does not; beside them, properties whose text is a note, a class's URI or a URI elsewhere. Returns
    the GlobalIds and STEP ids."""
    import ifcopenshell

    model = ifcopenshell.file(schema=schema)
    where = "Specification" if schema.startswith("IFC4X3") else "Description"  # renamed in IFC 4.3
    model.create_entity("IfcProject", GlobalId=guid(), Name="P")
    walls = [model.create_entity("IfcWall", GlobalId=guid(), Name=f"W{n}") for n in (1, 2)]
    door = model.create_entity("IfcDoor", GlobalId=guid(), Name="D1")

    def single(name: str, text: str) -> Any:
        value = model.create_entity("IfcLabel", "x")
        return model.create_entity("IfcPropertySingleValue", Name=name, NominalValue=value, **{where: text})

    fire_ratings = []
    for wall in walls:
        fire_ratings.append(single("FireRating", FIRE_RATING))
        others = [single("Note", "A wall of the ground floor"), single("Class", f"{IFC}/class/IfcWall")]
        common = model.create_entity(
            "IfcPropertySet", GlobalId=guid(), Name="Pset_WallCommon", HasProperties=[fire_ratings[-1], *others]
        )
        model.create_entity(
            "IfcRelDefinesByProperties", GlobalId=guid(), RelatedObjects=[wall], RelatingPropertyDefinition=common
        )
    bogus = single("Bogus", BOGUS)
    own = model.create_entity(
        "IfcPropertySet",
        GlobalId=guid(),
        Name="Custom",
        HasProperties=[bogus, single("Elsewhere", "https://example.org/prop/Elsewhere")],
    )
    model.create_entity(
        "IfcRelDefinesByProperties", GlobalId=guid(), RelatedObjects=[door], RelatingPropertyDefinition=own
    )
    model.write(str(path))
    return {
        "walls": [wall.GlobalId for wall in walls],
        "door": door.GlobalId,
        "fire_rating": fire_ratings[0].id(),
        "bogus": bogus.id(),
    }


@pytest.mark.parametrize(("schema", "where"), [("IFC4", "Description"), ("IFC4X3", "Specification")])
def test_the_worker_lists_the_properties_that_name_a_bsdd_property(tmp_path: Path, schema: str, where: str) -> None:
    path = tmp_path / "props.ifc"
    ids = model_with_property_uris(path, schema)
    found = answer(path)
    assert found["cut"] is False and found["references"] == []
    assert found["properties"] == [
        {
            "step_id": ids["fire_rating"],
            "uri": FIRE_RATING,
            "attribute": where,
            "set": "Pset_WallCommon",
            "name": "FireRating",
            "objects": [{"global_id": guid, "ifc_class": "IfcWall"} for guid in ids["walls"]],
            "object_count": 2,
        },
        {
            "step_id": ids["bogus"],
            "uri": BOGUS,
            "attribute": where,
            "set": "Custom",
            "name": "Bogus",
            "objects": [{"global_id": ids["door"], "ifc_class": "IfcDoor"}],
            "object_count": 1,
        },
    ], "once for a set name, a property name and a URI, however many sets; a note, a class or another host never"


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
    monkeypatch.setattr(bsdd_refs, "MAX_PROPERTIES", 500)
    monkeypatch.setattr(bsdd_refs, "MAX_PROPERTY_URIS", 1)
    model_with_property_uris(path)
    found = answer(path)
    assert [prop["name"] for prop in found["properties"]] == ["FireRating"] and found["cut"] is True


def test_the_worker_reads_the_bsdd_uris_of_an_ids_document_once_a_specification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("ifctester", reason="IfcTester is not installed")
    found = ids_uris(BSDD_IDS)
    assert found["title"] == "Walls by bSDD" and found["cut"] is False
    assert found["uris"][0] == {
        "uri": f"{IFC}/class/IfcWall",
        "facet": "classification",
        "clause": "requirements",
        "specification": "Walls are classified",
        "identifier": "W-1",
        "system": "IFC",
        "value": "IfcWall",
    }
    assert found["uris"][3] == {
        "uri": BOGUS,
        "facet": "property",
        "clause": "requirements",
        "specification": "Walls have a fire rating",
        "identifier": None,
        "set": "Pset_Custom",
        "name": "Bogus",
    }
    assert [(entry["specification"], entry["uri"]) for entry in found["uris"]] == [
        ("Walls are classified", f"{IFC}/class/IfcWall"),
        ("Walls are classified", NOWHERE),
        ("Walls have a fire rating", FIRE_RATING),
        ("Walls have a fire rating", BOGUS),
        ("Doors are classified", NOWHERE),
    ], "a URI on another host is not bSDD's; one a specification names twice is listed once for it"
    assert found["uris"][4]["value"] is None, "a class named by its system alone"
    assert ids_uris(FIXTURES_DIR / "walls.ids") == {"title": "Walls for reuse", "uris": [], "cut": False}
    dtd = tmp_path / "dtd.ids"
    dtd.write_bytes(b'<?xml version="1.0"?><!DOCTYPE ids [<!ENTITY x "y">]><ids/>')
    assert "DTD" in ids_uris(dtd)["error"], "read as the IDS check reads it, which refuses a DTD"
    monkeypatch.setattr(bsdd_refs, "MAX_IDS_URIS", 2)
    bounded = ids_uris(BSDD_IDS)
    assert len(bounded["uris"]) == 2 and bounded["cut"] is True


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
    two = [*command, str(path)]
    assert subprocess.run(two, capture_output=True, check=False).returncode == 2, "one IFC file at a time"  # noqa: S603


def test_the_worker_answers_for_ids_documents_on_stdout(tmp_path: Path) -> None:
    pytest.importorskip("ifctester", reason="IfcTester is not installed")
    command = [sys.executable, "-m", "opencde.ifcgraph.bsdd_refs", "--ids", "--memory-mb", "2048", "--"]
    paths = [str(BSDD_IDS), str(tmp_path / "none.ids")]
    run = subprocess.run([*command, *paths], capture_output=True, text=True, check=False)  # noqa: S603
    assert run.returncode == 0, run.stderr
    read, missing = json.loads(run.stdout)["ids"]
    assert len(read["uris"]) == 5 and "error" in missing, "an entry for each document, in the order given"
