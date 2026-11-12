# This file was generated with the assistance of an AI coding tool.
"""Dataspatium's write tools applied with the app's own code (``opencde/ifcgraph/ops.py``), on small files made here:
storeys, a grid, walls, slabs, roofs and openings with their refs, elements named by GlobalId, properties, a
classification with its system's facts, a storey and a material, a move, a deletion, the site with an EPSG code, the
units of a millimetre file, the owner histories, and the classes and values the schema allows; and, from
Dataspatium's 437982f on IFC4 and IFC4X3, layered and door, window, column and covering types, the building
elements and stairs of create_element, wall joins, base quantities and the common sets, a storey's description, a
room's number and type, a material's category, the vertical datum, elements changed in place, the templates that hold
a standard set, and a door moved with its opening while the site, the building and the storeys stay. The trial around
it is proved against a database in ``tests/integration/test_ifc_proposal.py``."""

from __future__ import annotations

import math
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest

from tests.conftest import FIXTURES_DIR

pytest.importorskip("ifcopenshell", reason="the ifc-db extra is not installed")

import ifcopenshell
import ifcopenshell.api.aggregate
import ifcopenshell.api.context
import ifcopenshell.api.owner
import ifcopenshell.api.owner.settings as owner_settings
import ifcopenshell.api.project
import ifcopenshell.api.root
import ifcopenshell.api.unit
import ifcopenshell.util.element
import ifcopenshell.util.placement

from opencde import __version__
from opencde.documents.changes import OPS_TOOLS
from opencde.ifcgraph.ops import SERVER, DataspatiumError, ServerChangeSet, _ChangeSet, run

FIXTURE = FIXTURES_DIR / "three_walls_gtin.ifc"  # IFC2X3 in millimetres, with an owner history and one storey


@contextmanager
def lent_owner(model: ifcopenshell.file) -> Iterator[None]:
    """An author for the file being made, as an IFC2X3 file needs one on every IfcRoot."""
    organisation = ifcopenshell.api.owner.add_organisation(model, identification="AUTHOR", name="Author")
    person = ifcopenshell.api.owner.add_person(model, identification="author", family_name="Author", given_name="")
    user = ifcopenshell.api.owner.add_person_and_organisation(model, person=person, organisation=organisation)
    application = ifcopenshell.api.owner.add_application(
        model, application_developer=organisation, version="1", application_full_name="Tool", application_identifier="T"
    )
    model.createIfcOwnerHistory(OwningUser=user, OwningApplication=application, ChangeAction="ADDED", CreationDate=1)
    previous = (owner_settings.get_user, owner_settings.get_application)
    owner_settings.get_user = lambda _file: user  # ty: ignore[invalid-assignment]
    owner_settings.get_application = lambda _file: application  # ty: ignore[invalid-assignment]
    try:
        yield
    finally:
        owner_settings.get_user, owner_settings.get_application = previous


def new_model(schema: str = "IFC4", prefix: str | None = None) -> ifcopenshell.file:
    """A project with its length unit (metres, or with a prefix), a model context, a site and a building."""
    model = ifcopenshell.api.project.create_file(version=schema)

    def build() -> None:
        project = ifcopenshell.api.root.create_entity(model, ifc_class="IfcProject", name="Project")
        unit = ifcopenshell.api.unit.add_si_unit(model, unit_type="LENGTHUNIT", prefix=prefix)
        ifcopenshell.api.unit.assign_unit(model, units=[unit])
        ifcopenshell.api.context.add_context(model, context_type="Model")
        site = ifcopenshell.api.root.create_entity(model, ifc_class="IfcSite", name="Site")
        building = ifcopenshell.api.root.create_entity(model, ifc_class="IfcBuilding", name="Building")
        ifcopenshell.api.aggregate.assign_object(model, products=[site], relating_object=project)
        ifcopenshell.api.aggregate.assign_object(model, products=[building], relating_object=site)

    if schema == "IFC2X3":
        with lent_owner(model):
            build()
    else:
        build()
    return model


STOREYS = {
    "tool": "create_storeys_and_grid",
    "storeys": [{"name": "Level 1", "elevation": 0}, {"name": "Level 2", "elevation": 3.5}],
    "grid": {"x_spacing": 5, "x_count": 2, "y_spacing": 4, "y_count": 1},
}
WALL = {"tool": "create_wall", "storey": "Level 1", "start": [0, 0], "end": [10, 0], "thickness": 0.2, "height": 3}
SLAB = {"tool": "create_slab", "storey": None, "outline": None, "thickness": 0.25, "name": "Floor"}
DOOR = {"tool": "create_opening", "wall_id": "new-1", "offset": 1, "width": 0.9, "height": 2.1, "fill": "door"}


def placed_at(element: Any) -> list[float]:
    """Where an element is, in the file's units, from its placement and those it is relative to."""
    matrix = ifcopenshell.util.placement.get_local_placement(element.ObjectPlacement)
    return [round(float(matrix[i][3]), 6) for i in range(3)]


def extrusion(element: Any) -> Any:
    """The solid of an element's body; a wall has its Axis beside it."""
    (representation,) = [r for r in element.Representation.Representations if r.RepresentationIdentifier == "Body"]
    (solid,) = representation.Items
    return solid


def test_every_tool_of_the_schema_is_an_operation_of_the_copy() -> None:
    """The schema's names and the copy's ``op_`` methods are one list, so neither has a tool the other lacks."""
    operations = {name[3:] for name in dir(_ChangeSet) if name.startswith("op_")}
    assert operations == set(OPS_TOOLS)


def test_the_tools_that_create_hand_out_the_refs() -> None:
    assert _ChangeSet.CREATES == (
        "create_wall",
        "create_slab",
        "create_roof",
        "create_opening",
        "create_spaces",
        "define_type",
        "create_element",
    )


@pytest.mark.parametrize(("schema", "prefix", "per_metre"), [("IFC4", None, 1), ("IFC2X3", "MILLI", 1000)])
def test_a_wall_carries_its_centre_line_as_its_axis_after_its_body(
    schema: str, prefix: str | None, per_metre: int
) -> None:
    """The topology reads a wall's centre line without the geometry kernel: create_wall writes it as the Axis, a
    polyline from (0, 0) to (length, 0) in the wall's own placement and the file's unit, in a sub-context
    Model/Axis/GRAPH_VIEW that the file's walls share."""
    model = new_model(schema, prefix)
    answer = run(model, [STOREYS, WALL, {**WALL, "start": [10, 0], "end": [10, 6]}], proposer="anna")
    assert answer["failed"] is None, answer
    first, second = (model.by_guid(answer["created"][ref]) for ref in ("new-1", "new-2"))
    body, axis = first.Representation.Representations
    assert (body.RepresentationIdentifier, axis.RepresentationIdentifier, axis.RepresentationType) == (
        "Body",
        "Axis",
        "Curve2D",
    )
    (line,) = axis.Items
    assert line.is_a("IfcPolyline")
    assert [list(p.Coordinates) for p in line.Points] == [[0, 0], pytest.approx([10 * per_metre, 0])]
    (context,) = [c for c in model.by_type("IfcGeometricRepresentationSubContext") if c.ContextIdentifier == "Axis"]
    assert (context.ContextType, context.TargetView, context.ParentContext.ContextType) == (
        "Model",
        "GRAPH_VIEW",
        "Model",
    )
    assert axis.ContextOfItems == context == second.Representation.Representations[1].ContextOfItems, "one shared"
    (other,) = second.Representation.Representations[1].Items
    assert [list(p.Coordinates) for p in other.Points] == [[0, 0], pytest.approx([6 * per_metre, 0])], "its own way"
    findings, errors = ServerChangeSet(model, "anna").findings()
    assert errors == 0, findings


def test_a_file_with_an_axis_context_keeps_it_for_its_new_walls() -> None:
    model = new_model()
    (parent,) = model.by_type("IfcGeometricRepresentationContext")
    own = ifcopenshell.api.context.add_context(
        model, context_type="Model", context_identifier="Axis", target_view="GRAPH_VIEW", parent=parent
    )
    answer = run(model, [STOREYS, WALL], proposer="anna")
    wall = model.by_guid(answer["created"]["new-1"])
    assert wall.Representation.Representations[1].ContextOfItems == own
    assert [c.ContextIdentifier for c in model.by_type("IfcGeometricRepresentationSubContext")].count("Axis") == 1


def test_storeys_a_grid_a_wall_a_slab_and_a_door_get_their_refs_in_order() -> None:
    model = new_model()
    answer = run(model, [STOREYS, WALL, SLAB, DOOR], proposer="anna")
    assert answer["failed"] is None and answer["count"] == answer["applied"] == 4
    assert list(answer["created"]) == ["new-1", "new-2", "new-3"], "a wall, a slab and the door: storeys get none"
    wall, slab, door = (model.by_guid(answer["created"][ref]) for ref in ("new-1", "new-2", "new-3"))
    assert (wall.is_a(), slab.is_a(), door.is_a()) == ("IfcWall", "IfcSlab", "IfcDoor")
    storeys = {storey.Name: storey for storey in model.by_type("IfcBuildingStorey")}
    assert set(storeys) == {"Level 1", "Level 2"} and storeys["Level 2"].Elevation == pytest.approx(3.5)
    assert ifcopenshell.util.element.get_container(wall) == storeys["Level 1"]
    assert ifcopenshell.util.element.get_container(slab) == storeys["Level 1"], "the lowest storey when none is named"
    (grid,) = model.by_type("IfcGrid")
    assert [axis.AxisTag for axis in grid.UAxes] == ["A", "B", "C"] and [a.AxisTag for a in grid.VAxes] == ["1", "2"]
    box = extrusion(wall)
    assert (box.SweptArea.XDim, box.SweptArea.YDim, box.Depth) == pytest.approx((10, 0.2, 3))
    outline = [tuple(point.Coordinates) for point in extrusion(slab).SweptArea.OuterCurve.Points]
    assert outline[:4] == [(0, 0), (10, 0), (10, 4), (0, 4)], "no outline: the slab follows the grid"
    (opening,) = model.by_type("IfcOpeningElement")
    assert [rel.RelatingBuildingElement for rel in opening.VoidsElements] == [wall]
    assert [rel.RelatedBuildingElement for rel in opening.HasFillings] == [door]
    assert placed_at(door) == pytest.approx([1, 0, 0]), "one metre along the wall"
    present = {model.by_guid(guid).GlobalId for guid in answer["objects"]}
    assert set(answer["created"].values()) <= present and answer["removed"] == []
    findings, errors = ServerChangeSet(model, "anna").findings()
    assert errors == 0, findings


def test_properties_a_classification_a_storey_and_a_material() -> None:
    model = new_model()
    answer = run(
        model,
        [
            STOREYS,
            WALL,
            {
                "tool": "set_properties",
                "ids": ["new-1"],
                "pset": "Pset_WallCommon",
                "properties": {"FireRating": "EI60"},
            },
            {
                "tool": "set_properties",
                "ids": ["new-1"],
                "pset": "Pset_WallCommon",
                "properties": {"IsExternal": True, "ThermalTransmittance": 0.18},
            },
            {
                "tool": "set_classification",
                "ids": ["new-1"],
                "system": "CoClass",
                "name": "Wall",
                "code": "QQA",
                "uri": "https://identifier.buildingsmart.org/uri/coclass/QQA",
            },
            {"tool": "assign", "ids": ["new-1"], "storey": "Level 2", "material": "Concrete"},
        ],
        proposer="anna",
    )
    assert answer["failed"] is None, answer
    wall = model.by_guid(answer["created"]["new-1"])
    psets = ifcopenshell.util.element.get_psets(wall)
    assert psets["Pset_WallCommon"]["FireRating"] == "EI60" and psets["Pset_WallCommon"]["IsExternal"] is True
    assert psets["Pset_WallCommon"]["ThermalTransmittance"] == pytest.approx(0.18), "one set, filled twice"
    (reference,) = model.by_type("IfcClassificationReference")
    assert (reference.Identification, reference.Name, reference.ReferencedSource.Name) == ("QQA", "Wall", "CoClass")
    assert reference.Location == "https://identifier.buildingsmart.org/uri/coclass/QQA"
    assert ifcopenshell.util.element.get_container(wall).Name == "Level 2"
    assert ifcopenshell.util.element.get_material(wall).Name == "Concrete"


@pytest.mark.parametrize(("schema", "address"), [("IFC4", "Location"), ("IFC4X3", "Specification"), ("IFC2X3", None)])
def test_a_classification_carries_its_systems_facts_and_reuses_only_the_same_class(
    schema: str, address: str | None
) -> None:
    """set_classification's edition, source and dictionary_uri go on the system's IfcClassification, the address as
    Location in IFC4 and Specification in IFC4X3; the same class of the same system is one reference with one
    relationship, a system of the same name with another edition is another, and IFC2X3 gets empty labels for the
    Source and Edition it requires."""
    model = new_model(schema)
    uri = "https://identifier.buildingsmart.org/uri/molio/cciconstruction/1.0"
    cci = {"tool": "set_classification", "system": "CCI Construction", "name": "Wall", "code": "QQA",
           "edition": "1.0", "source": "Molio", "dictionary_uri": uri}  # fmt: skip
    own = {"tool": "set_classification", "ids": ["new-1"], "system": "Own", "name": "Wall"}
    answer = run(
        model,
        [STOREYS, WALL, WALL, {**cci, "ids": ["new-1"]}, {**cci, "ids": ["new-2"]},
         {**cci, "ids": ["new-2"], "edition": "2.0"}, own],
        proposer="anna",
    )  # fmt: skip
    assert answer["failed"] is None, answer
    systems = {(c.Name, c.Edition): c for c in model.by_type("IfcClassification")}
    first, second = systems["CCI Construction", "1.0"], systems["CCI Construction", "2.0"]
    assert first.Source == second.Source == "Molio" and len(systems) == 3
    assert address is None or getattr(first, address) == uri
    blank = "" if schema == "IFC2X3" else None
    assert (systems["Own", blank].Source, systems["Own", blank].Edition) == (blank, blank)
    code = "ItemReference" if schema == "IFC2X3" else "Identification"
    refs = {
        (r.ReferencedSource.Name, r.ReferencedSource.Edition): r for r in model.by_type("IfcClassificationReference")
    }
    assert len(refs) == 3 and getattr(refs["CCI Construction", "1.0"], code) == "QQA"
    related = {
        r.RelatingClassification.id(): [o.GlobalId for o in r.RelatedObjects]
        for r in model.by_type("IfcRelAssociatesClassification")
    }
    walls = [answer["created"][ref] for ref in ("new-1", "new-2")]
    assert related[refs["CCI Construction", "1.0"].id()] == walls, "one relationship for both walls"
    assert related[refs["CCI Construction", "2.0"].id()] == walls[1:]
    findings, errors = ServerChangeSet(model, "anna").findings()
    assert errors == 0, findings


@pytest.mark.parametrize("schema", ["IFC4", "IFC4X3", "IFC2X3"])
def test_a_wall_is_solid_or_with_partition_partitioning(schema: str) -> None:
    """STANDARD is deprecated (bSI rule IFC102): a wall is SOLIDWALL, and PARTITIONING with partition true only;
    IFC2X3's walls have no PredefinedType."""
    model = new_model(schema)
    answer = run(model, [STOREYS, WALL, {**WALL, "partition": True}, {**WALL, "partition": "yes"}], proposer="anna")
    assert answer["failed"] is None, answer
    walls = [model.by_guid(answer["created"][ref]) for ref in ("new-1", "new-2", "new-3")]
    kinds = [getattr(wall, "PredefinedType", None) for wall in walls]
    assert kinds == ([None] * 3 if schema == "IFC2X3" else ["SOLIDWALL", "PARTITIONING", "SOLIDWALL"])


def test_a_deprecated_or_unknown_value_and_a_class_the_schema_lacks_are_refused() -> None:
    """B-57.2, the right IFC class: every class and enumeration value the copy sets is checked against the file's
    schema, and a value the release deprecates is never written (IFC102)."""
    model = new_model("IFC4X3")
    built = run(model, [STOREYS, WALL], proposer="anna")
    wall = model.by_guid(built["created"]["new-1"])
    changeset = ServerChangeSet(model, "anna")
    with pytest.raises(
        DataspatiumError, match=r"^STANDARD is deprecated for IfcWall in IFC4X3_ADD2 \(bSI rule IFC102\)"
    ):
        changeset.predefined(wall, "STANDARD")
    with pytest.raises(DataspatiumError, match=r"^INTERNAL is deprecated for IfcSpace"):
        changeset.predefined(model.create_entity("IfcSpace"), "INTERNAL")
    with pytest.raises(DataspatiumError, match=r"^BOGUS is not a PredefinedType of IfcWall in IFC4X3_ADD2; it takes "):
        changeset.predefined(wall, "BOGUS")
    with pytest.raises(DataspatiumError, match=r"^IfcWall USERDEFINED needs ObjectType"):
        changeset.predefined(wall, "USERDEFINED")
    assert wall.PredefinedType == "SOLIDWALL", "as it was"
    with pytest.raises(DataspatiumError, match=r"^IfcElement is abstract in IFC4X3_ADD2; use one of "):
        changeset.root("IfcElement", "Element")
    with pytest.raises(DataspatiumError, match=r"^IfcBuildingElement is not an entity of IFC4X3_ADD2; near: "):
        changeset.root("IfcBuildingElement", "Element")
    older = ServerChangeSet(new_model("IFC4"), "anna")
    with pytest.raises(DataspatiumError, match=r"^STANDARD is deprecated for IfcWall in IFC4 "):
        older.predefined(older.m.create_entity("IfcWall"), "STANDARD")
    open_outline = {"tool": "create_slab", "outline": [[0, 0], [1, 0], [0, 0]]}
    refused = run(model, [open_outline], proposer="anna")
    assert refused["failed"]["error"] == "an outline needs at least three different corners"


def test_a_move_and_a_deletion_that_takes_the_door_along() -> None:
    model = new_model()
    built = run(model, [STOREYS, WALL, DOOR], proposer="anna")
    wall_guid, door_guid = built["created"]["new-1"], built["created"]["new-2"]
    wall = model.by_guid(wall_guid)
    moved = run(model, [{"tool": "transform_elements", "ids": [wall.id()], "dx": 1, "dy": 2, "dz": 0.5}], proposer="a")
    assert moved["failed"] is None and moved["objects"] == [wall_guid] and moved["created"] == {}
    assert placed_at(wall) == pytest.approx([1, 2, 0.5])

    refused = run(model, [{"tool": "delete_elements", "ids": [wall.id()]}], proposer="anna")
    assert refused["failed"] == {
        "op": 0,
        "tool": "delete_elements",
        "error": "deleting needs confirm: true, which the person gives",
    }
    assert refused["applied"] == 0 and model.by_guid(wall_guid)
    deleted = run(model, [{"tool": "delete_elements", "ids": [wall.id()], "confirm": True}], proposer="anna")
    assert deleted["failed"] is None and deleted["removed"] == sorted([wall_guid, door_guid])
    assert not model.by_type("IfcWall") and not model.by_type("IfcDoor"), "the door in its opening goes too"


def test_the_site_gets_its_place_on_earth_and_the_map_conversion_its_epsg_code() -> None:
    model = new_model()
    site_op = {
        "tool": "set_site",
        "latitude": 59.329444,
        "longitude": -18.068611,
        "elevation": 28,
        "crs": "EPSG:3006",
        "eastings": 674032.5,
        "northings": 6580821.25,
        "rotation": 90,
        "site_name": "Riddarholmen",
    }
    answer = run(model, [site_op], proposer="anna")
    assert answer["failed"] is None and answer["notes"] == []
    (site,) = model.by_type("IfcSite")
    assert site.Name == "Riddarholmen" and site.RefElevation == pytest.approx(28)
    assert tuple(site.RefLatitude) == (59, 19, 45, 998400) and tuple(site.RefLongitude) == (-18, -4, -6, -999600)
    (crs,) = model.by_type("IfcProjectedCRS")
    assert (crs.Name, crs.GeodeticDatum, crs.MapProjection, crs.MapZone) == (
        "EPSG:3006",
        "SWEREF99",
        "Transverse Mercator",
        "TM",
    )
    (conversion,) = model.by_type("IfcMapConversion")
    assert (conversion.Eastings, conversion.Northings, conversion.OrthogonalHeight) == pytest.approx(
        (674032.5, 6580821.25, 28)
    )
    assert (conversion.XAxisAbscissa, conversion.XAxisOrdinate) == pytest.approx((0, 1), abs=1e-12)
    run(model, [{**site_op, "eastings": 1, "northings": 2}], proposer="anna")
    assert len(model.by_type("IfcMapConversion")) == 1 and model.by_type("IfcMapConversion")[0].Eastings == 1, (
        "made once, then updated"
    )

    old = new_model("IFC2X3")
    noted = run(old, [site_op], proposer="anna")
    assert noted["failed"] is None and old.by_type("IfcSite")[0].Name == "Riddarholmen"
    assert noted["notes"] == [
        "the map conversion to EPSG:3006 was skipped: IFC2X3 has no IfcMapConversion; the site's latitude, longitude "
        "and elevation were set"
    ]
    refused = run(model, [{**site_op, "crs": "SWEREF 99 TM"}], proposer="anna")
    assert refused["failed"]["error"] == "crs must be an EPSG code such as EPSG:3006"


def test_lengths_are_metres_in_a_file_of_millimetres() -> None:
    model = new_model(prefix="MILLI")
    answer = run(
        model,
        [
            STOREYS,
            WALL,
            {"tool": "transform_elements", "ids": ["new-1"], "dx": 1, "dy": 0, "dz": 0},
            {"tool": "set_site", "latitude": 60, "longitude": 10, "elevation": 20, "crs": "EPSG:25832",
             "eastings": 600000, "northings": 6650000},
        ],
        proposer="anna",
    )  # fmt: skip
    assert answer["failed"] is None, answer
    wall = model.by_guid(answer["created"]["new-1"])
    box = extrusion(wall)
    assert (box.SweptArea.XDim, box.SweptArea.YDim, box.Depth) == pytest.approx((10_000, 200, 3_000))
    assert placed_at(wall) == pytest.approx([1_000, 0, 0])
    level_2 = next(storey for storey in model.by_type("IfcBuildingStorey") if storey.Name == "Level 2")
    assert level_2.Elevation == pytest.approx(3_500)
    assert model.by_type("IfcSite")[0].RefElevation == pytest.approx(20_000)
    (conversion,) = model.by_type("IfcMapConversion")
    assert (conversion.Eastings, conversion.OrthogonalHeight, conversion.Scale) == pytest.approx(
        (600_000, 20, 0.001)
    ), "in the map's metres, with the file's unit as the Scale (bSI rule GRF005)"
    (crs,) = model.by_type("IfcProjectedCRS")
    assert crs.MapZone == "UTM 32N" and (crs.MapUnit.Name, crs.MapUnit.Prefix) == ("METRE", None)
    assert model.by_type("IfcBuilding")[0].ElevationOfRefHeight == pytest.approx(20_000), "the building's height"


def test_the_existing_millimetre_model_gets_a_wall_and_a_window_in_its_wall() -> None:
    model = ifcopenshell.open(str(FIXTURE))
    answer = run(
        model,
        [
            {"tool": "create_wall", "start": [0, 0], "end": [4, 0]},
            {"tool": "create_opening", "wall_id": 242, "offset": 1, "width": 1.2, "height": 1.2, "sill": 0.9,
             "fill": "window"},
            {"tool": "set_properties", "ids": [373], "pset": "Pset_WallCommon", "properties": {"FireRating": "EI60"}},
        ],
        proposer="anna",
    )  # fmt: skip
    assert answer["failed"] is None and list(answer["created"]) == ["new-1", "new-2"]
    new_wall = model.by_guid(answer["created"]["new-1"])
    assert ifcopenshell.util.element.get_container(new_wall).Name == "1. etasje", "the file's only storey"
    assert extrusion(new_wall).SweptArea.XDim == pytest.approx(4_000) and extrusion(new_wall).Depth == pytest.approx(
        3_000
    )
    window = model.by_guid(answer["created"]["new-2"])
    assert window.is_a("IfcWindow") and window.OverallWidth == pytest.approx(1_200)
    assert "1Xezbq735AdBO_4DerG66G" in answer["objects"], "the wall that got the opening is touched"
    assert "3eT96F_cnDsOufCEsotwtp" in answer["objects"], "and the wall that got the property"


FOUR_WALLS = [
    {"tool": "create_wall", "storey": "Level 1", "start": start, "end": end, "thickness": 0.2, "height": 3}
    for start, end in (([0, 0], [10, 0]), ([10, 0], [10, 6]), ([10, 6], [0, 6]), ([0, 6], [0, 0]))
]


def roof_slabs(roof: Any) -> list[Any]:
    return [part for rel in roof.IsDecomposedBy for part in rel.RelatedObjects]


def boundaries(space: Any) -> dict[str, tuple[str, str]]:
    """What bounds a space, by GlobalId: whether inside or outside, and that it is physical."""
    return {
        rel.RelatedBuildingElement.GlobalId: (rel.InternalOrExternalBoundary, rel.PhysicalOrVirtualBoundary)
        for rel in space.BoundedBy
    }


def quantities(space: Any) -> dict[str, float]:
    return ifcopenshell.util.element.get_psets(space, qtos_only=True)["Qto_SpaceBaseQuantities"]


@pytest.mark.parametrize(
    ("schema", "prefix", "per_metre"), [("IFC4", None, 1), ("IFC2X3", "MILLI", 1000), ("IFC4X3", None, 1)]
)
def test_create_spaces_makes_a_closed_room_with_a_door_a_space_bounded_by_its_walls_and_the_door(
    schema: str, prefix: str | None, per_metre: int
) -> None:
    """F37 a, the rooms become IfcSpace through a proposal: a listed room, found by a point inside it, is an IfcSpace in
    its storey with the next ref, the room's outline extruded up to the next storey, its quantities, and a physical
    boundary to each of the four walls along its edge and to the door in one of them, external as the walls are. It is
    INTERNAL, except in IFC4X3, which deprecates that (bSI rule IFC102): there it is SPACE, with IsExternal false."""
    model = new_model(schema, prefix)
    kitchen = {"at": [5, 3], "name": "Kitchen", "long_name": "Kök"}
    spaces = {"tool": "create_spaces", "storey": "Level 1", "rooms": [kitchen], "height": None}
    answer = run(model, [STOREYS, *FOUR_WALLS, DOOR, spaces], proposer="anna")
    assert answer["failed"] is None, answer
    assert list(answer["created"]) == ["new-1", "new-2", "new-3", "new-4", "new-5", "new-6"], "walls, door, room"
    space = model.by_guid(answer["created"]["new-6"])
    assert (space.is_a(), space.Name, space.LongName) == ("IfcSpace", "Kitchen", "Kök")
    kind = space.InteriorOrExteriorSpace if schema == "IFC2X3" else space.PredefinedType
    assert kind == ("SPACE" if schema == "IFC4X3" else "INTERNAL")
    psets = ifcopenshell.util.element.get_psets(space)
    if schema == "IFC4X3":
        assert psets["Pset_SpaceCommon"]["IsExternal"] is False, "inside, as IFC4X3 says it"
    else:
        assert "Pset_SpaceCommon" not in psets
    points = extrusion(space).SweptArea.OuterCurve.Points
    assert len(points) == 5 and points[-1].id() == points[0].id(), "closed on its first point (bSI rule GEM111)"
    (aggregate,) = space.Decomposes
    assert aggregate.RelatingObject.Name == "Level 1" and space.GlobalId in answer["objects"]
    walls = [answer["created"][ref] for ref in ("new-1", "new-2", "new-3", "new-4")]
    assert boundaries(space) == {guid: ("EXTERNAL", "PHYSICAL") for guid in [*walls, answer["created"]["new-5"]]}
    assert extrusion(space).Depth == pytest.approx(3.5 * per_metre), "up to the next storey"
    found = quantities(space)
    assert found["GrossFloorArea"] == pytest.approx(60) and found["GrossPerimeter"] == pytest.approx(32 * per_metre)
    assert found["NetFloorArea"] == pytest.approx(9.8 * 5.8), "inside the walls' faces"
    assert found["Height"] == pytest.approx(3.5 * per_metre)
    findings, errors = ServerChangeSet(model, "anna").findings()
    assert errors == 0, findings


def test_a_window_made_later_bounds_the_space_its_wall_bounds_and_every_room_gets_a_space() -> None:
    """rooms null makes every room the walls enclose, named by default_name, without refs; a window cut afterwards in
    a wall that bounds a space bounds it too, as create_spaces would have made it."""
    model = new_model()
    every = {"tool": "create_spaces", "storey": None, "rooms": None, "default_name": "Rum {n}"}
    built = run(model, [STOREYS, *FOUR_WALLS, every], proposer="anna")
    assert built["failed"] is None and list(built["created"]) == ["new-1", "new-2", "new-3", "new-4"], "no ref"
    (space,) = model.by_type("IfcSpace")
    assert space.Name == "Rum 1" and len(boundaries(space)) == 4
    window = {"tool": "create_opening", "wall_id": built["created"]["new-2"], "offset": 2, "width": 1.2,
              "height": 1.2, "sill": 0.9, "fill": "window"}  # fmt: skip
    answer = run(model, [window], proposer="anna")
    assert answer["failed"] is None
    assert boundaries(space)[answer["created"]["new-1"]] == ("EXTERNAL", "PHYSICAL"), "the new window joins them"
    again = run(model, [every], proposer="anna")
    assert again["failed"]["error"] == "every room the walls enclose has a space already"
    listed = {"tool": "create_spaces", "storey": "Level 1", "rooms": [{"index": 1, "name": "Hall"}]}
    taken = run(model, [listed], proposer="anna")
    assert taken["failed"]["error"] == "room 1 on storey 'Level 1' lies in the space 'Rum 1' already"
    nowhere = run(model, [{**listed, "storey": "Level 2"}], proposer="anna")
    assert nowhere["failed"]["error"].startswith("the walls enclose no room on storey 'Level 2'")


def test_a_gable_roof_on_a_storey_is_an_ifcroof_of_two_roof_slabs() -> None:
    """create_roof over the storey's walls: an IfcRoof in the storey on the walls' tops, the only one with a ref, which
    aggregates one roof slab per face."""
    model = new_model()
    gable = {"tool": "create_roof", "storey": "Level 1", "shape": "gable", "pitch": 30, "overhang": 0.5}
    answer = run(model, [STOREYS, *FOUR_WALLS, gable], proposer="anna")
    assert answer["failed"] is None and answer["notes"] == [], answer
    assert list(answer["created"]) == ["new-1", "new-2", "new-3", "new-4", "new-5"], "the four walls and the roof"
    roof = model.by_guid(answer["created"]["new-5"])
    assert roof.is_a("IfcRoof") and roof.PredefinedType == "GABLE_ROOF"
    assert ifcopenshell.util.element.get_container(roof).Name == "Level 1"
    assert placed_at(roof) == pytest.approx([-0.1, -0.1, 3]), "the walls' outer corner, on their tops"
    slabs = roof_slabs(roof)
    assert len(slabs) == 2 and all(slab.is_a("IfcSlab") and slab.PredefinedType == "ROOF" for slab in slabs)
    assert {slab.GlobalId for slab in slabs} <= set(answer["objects"]) and len(model.by_type("IfcSlab")) == 2
    findings, errors = ServerChangeSet(model, "anna").findings()
    assert errors == 0, findings


def test_a_hip_a_flat_and_a_shed_roof_and_what_a_roof_needs() -> None:
    model = new_model()
    built = run(model, [STOREYS, *FOUR_WALLS], proposer="anna")
    assert built["failed"] is None
    outline = [[0, 0], [10, 0], [10, 6], [0, 6]]
    for shape, faces, kind in (("hip", 4, "HIP_ROOF"), ("flat", 1, "FLAT_ROOF"), ("shed", 1, "SHED_ROOF")):
        answer = run(model, [{"tool": "create_roof", "shape": shape, "outline": outline, "base": 3}], proposer="anna")
        assert answer["failed"] is None, (shape, answer)
        roof = model.by_guid(answer["created"]["new-1"])
        assert roof.PredefinedType == kind and len(roof_slabs(roof)) == faces, shape
        assert ifcopenshell.util.element.get_container(roof).Name == "Level 2", "the top storey when none is named"
    bent = run(
        model,
        [{"tool": "create_roof", "shape": "flat", "outline": [[0, 0], [8, 0], [8, 3], [4, 6], [0, 6]], "base": 3}],
        proposer="anna",
    )
    assert bent["notes"] == [
        "the roof's outline is not a rectangle along x and y (5 corners), so the roof covers its bounding box"
    ]
    dome = run(model, [{"tool": "create_roof", "shape": "dome"}], proposer="anna")
    assert dome["failed"]["error"] == "shape must be gable, hip, shed or flat"
    bare = run(model, [{"tool": "create_roof", "storey": "Level 2", "shape": "gable"}], proposer="anna")
    assert bare["failed"]["error"] == "give an outline: storey 'Level 2' has no walls whose shape the app can read"


def test_an_element_is_named_by_its_globalid_its_step_id_or_its_ref() -> None:
    """F34 a: an operation names an element by its GlobalId, by its STEP id where no GlobalId reaches it, and what the
    change set created by its ref; the server's copy takes all three, as the app's does."""
    model = ifcopenshell.open(str(FIXTURE))
    door = {"tool": "create_opening", "wall_id": "1Xezbq735AdBO_4DerG66G", "offset": 1, "width": 0.9, "fill": "door"}
    tagged = {"tool": "set_properties", "pset": "SE-DR-1_Test", "properties": {"Tagged": True}}
    answer = run(model, [door, {**tagged, "ids": ["3eT96F_cnDsOufCEsotwtp", 459, "new-1"]}], proposer="anna")
    assert answer["failed"] is None, answer
    (opening,) = model.by_type("IfcOpeningElement")
    assert [rel.RelatingBuildingElement.GlobalId for rel in opening.VoidsElements] == ["1Xezbq735AdBO_4DerG66G"], (
        "the wall named by its GlobalId gets the opening"
    )
    for element in (
        model.by_guid("3eT96F_cnDsOufCEsotwtp"),
        model.by_id(459),
        model.by_guid(answer["created"]["new-1"]),
    ):
        assert ifcopenshell.util.element.get_psets(element)["SE-DR-1_Test"]["Tagged"] is True
    by_text = run(model, [{**tagged, "ids": ["373"]}], proposer="anna")
    assert by_text["failed"] is None and by_text["objects"] == ["3eT96F_cnDsOufCEsotwtp"], "a STEP id as digits"
    unknown = run(model, [{"tool": "create_opening", "wall_id": "0NotInTheModel00000000"}], proposer="anna")
    assert unknown["failed"]["error"] == "no element with GlobalId '0NotInTheModel00000000'"
    digits = run(model, [{"tool": "create_opening", "wall_id": "0" * 22}], proposer="anna")
    assert digits["failed"]["error"] == f"no element with id '{'0' * 22}'", "22 digits are a STEP id, as in the app"


def test_an_operation_that_fails_stops_the_rest_and_says_which() -> None:
    model = ifcopenshell.open(str(FIXTURE))
    walls = len(model.by_type("IfcWall"))
    answer = run(
        model,
        [
            {"tool": "create_wall", "start": [0, 0], "end": [4, 0]},
            {"tool": "create_wall", "storey": "Level 9", "start": [0, 0], "end": [4, 0]},
            {"tool": "create_wall", "start": [0, 0], "end": [8, 0]},
        ],
        proposer="anna",
    )
    assert answer["failed"] == {
        "op": 1,
        "tool": "create_wall",
        "error": "no storey named 'Level 9'; the storeys are 1. etasje",
    }
    assert answer["applied"] == 1 and answer["count"] == 3 and list(answer["created"]) == ["new-1"]
    assert len(model.by_type("IfcWall")) == walls + 1, "the third is not applied"
    no_ref = run(model, [{"tool": "create_opening", "wall_id": "new-7"}], proposer="anna")
    assert no_ref["failed"]["error"] == "no element with id 'new-7'", "a ref of another change set names nothing"
    not_a_wall = run(model, [{"tool": "create_opening", "wall_id": 167}], proposer="anna")
    assert not_a_wall["failed"]["error"] == "wall_id must name a wall, not IfcBuildingStorey"


def test_the_owner_histories_name_the_proposer_and_the_server() -> None:
    """IFC2X3 needs an owner on every IfcRoot: what the API makes is owned by the proposer with this server as the
    application, what the copy makes gets the file's first owner history as in the app, the proposer as its last
    modifier where the API changed it later, and the settings are given back afterwards."""
    before = (owner_settings.get_user, owner_settings.get_application)
    model = ifcopenshell.open(str(FIXTURE))
    first = model.by_type("IfcOwnerHistory")[0]
    answer = run(model, [WALL | {"storey": None}, DOOR], proposer="anna")
    assert answer["failed"] is None
    assert (owner_settings.get_user, owner_settings.get_application) == before, "given back"
    (server,) = [found for found in model.by_type("IfcApplication") if found.ApplicationIdentifier == SERVER]
    assert (server.Version, server.ApplicationFullName, server.ApplicationDeveloper.Name) == (
        __version__,
        SERVER,
        SERVER,
    )
    made = [history for history in model.by_type("IfcOwnerHistory") if history.OwningApplication == server]
    assert made and all(history.OwningUser.ThePerson.Id == "anna" for history in made)
    (opening,) = model.by_type("IfcOpeningElement")
    assert opening.VoidsElements[0].OwnerHistory in made, "a relationship the API made"
    container = next(iter(model.by_guid(answer["created"]["new-1"]).ContainedInStructure)).OwnerHistory
    assert container.OwningUser == first.OwningUser and container.LastModifyingUser.ThePerson.Id == "anna", (
        "the storey's relationship got the wall: its owner, copied, names the proposer as its last modifier"
    )
    wall = model.by_guid(answer["created"]["new-1"]).OwnerHistory
    assert wall.OwningUser == first.OwningUser and wall.CreationDate == first.CreationDate, "the file's, copied"
    assert wall.LastModifyingUser.ThePerson.Id == "anna" and wall.LastModifyingApplication == server, "the opening"
    assert first.LastModifyingUser is None, "the shared one is as it was"
    assert all(entity.OwnerHistory is not None for entity in model.by_type("IfcRoot")), "every IfcRoot has one"
    again = run(model, [WALL | {"storey": None}], proposer="anna")
    assert again["failed"] is None
    assert len([a for a in model.by_type("IfcApplication") if a.ApplicationIdentifier == SERVER]) == 1, "found again"
    assert len([p for p in model.by_type("IfcPerson") if p.Id == "anna"]) == 1

    plain = new_model()
    run(plain, [STOREYS, WALL], proposer="anna")
    assert not plain.by_type("IfcOwnerHistory") and not plain.by_type("IfcApplication"), "none, as in the app"


def test_a_compound_angle_carries_its_sign_in_every_part() -> None:
    """The site's angles as the app writes them, and the copy's units on the way: degrees to IFC's four parts."""
    from opencde.ifcgraph.ops import _cs_angle, _cs_crs_facts

    assert _cs_angle(-0.5) == [0, -30, 0, 0] and _cs_angle(10.5) == [10, 30, 0, 0]
    assert _cs_crs_facts("EPSG:3011") == ("SWEREF99", "Transverse Mercator", "18 00")
    assert _cs_crs_facts("EPSG:4326") == (None, None, None)
    assert math.isclose(sum(part / 60**i for i, part in enumerate(_cs_angle(59.5)[:3])), 59.5)


# -- the operations and fields of Dataspatium's 437982f ------------------------------------------------------------


def layer(material: str, thickness: float, category: str | None = None, role: str | None = None) -> dict[str, Any]:
    return {"material": material, "thickness": thickness, "category": category, "role": role}


#: A 0.3 m outer wall from the outside in, a floor and a roof from the top down, as define_type takes them.
YV1 = {"tool": "define_type", "kind": "wall", "name": "YV1", "predefined_type": "SOLIDWALL",
       "layers": [layer("Puts", 0.02, None, "outer_finish"), layer("Lättbetong", 0.25, "block", "load_bearing"),
                  layer("Puts", 0.03, None, "inner_finish")]}  # fmt: skip
BJ1 = {"tool": "define_type", "kind": "slab", "name": "BJ1", "predefined_type": None,
       "layers": [layer("Parkett", 0.015, "wood"), layer("Betong", 0.2, "concrete", "load_bearing")]}  # fmt: skip
TAK1 = {"tool": "define_type", "kind": "roof", "name": "TAK1", "predefined_type": None,
        "layers": [layer("Takpannor", 0.05), layer("Takstol", 0.2, "wood", "load_bearing")]}  # fmt: skip
#: Four outer walls of type new-1, counter-clockwise so that their right side is the outside, and a partition.
TYPED_BOX = [
    {"tool": "create_wall", "storey": "Level 1", "start": start, "end": end, "thickness": 0.3, "height": 3,
     "name": name, "type": "new-1", "load_bearing": True, "status": "EXISTING"}
    for name, start, end in (("S", [0, 0], [8, 0]), ("E", [8, 0], [8, 6]), ("N", [8, 6], [0, 6]), ("W", [0, 6], [0, 0]))
]  # fmt: skip
PARTITION = {"tool": "create_wall", "storey": "Level 1", "start": [4, 0], "end": [4, 6], "thickness": 0.1,
             "height": 3, "name": "Mid", "partition": True, "load_bearing": False}  # fmt: skip
STOREYS_437982F = {
    "tool": "create_storeys_and_grid",
    "storeys": [
        {"name": "Level 1", "elevation": 0, "description": "Level 1 (Entrance)", "long_name": "Entrance level"},
        {"name": "Level 2", "elevation": 3.5},
    ],
    "grid": None,
}


def made(model: ifcopenshell.file, answer: dict[str, Any], ref: str) -> Any:
    return model.by_guid(answer["created"][ref])


def layers_of(element: Any) -> list[tuple[str, float, str | None, str | None]]:
    """A type's layers: material, thickness, the material's category and the layer's."""
    found = ifcopenshell.util.element.get_material(element)
    return [
        (x.Material.Name, round(float(x.LayerThickness), 6), x.Material.Category, x.Category)
        for x in found.MaterialLayers
    ]


@pytest.mark.parametrize(
    ("schema", "finish"), [("IFC4", ("Finish", "Finish")), ("IFC4X3", ("Outer finish", "Inner finish"))]
)
def test_layered_types_give_walls_slabs_and_roofs_their_layers_joins_and_quantities(
    schema: str, finish: tuple[str, str]
) -> None:
    """define_type makes a wall, slab and roof type with its material layers and a ref; a typed wall takes the type,
    its thickness from the layers and an IfcMaterialLayerSetUsage, the walls whose axes meet are joined, what the
    change set made gets its base quantities, and LoadBearing, Status and IsExternal land in the common sets."""
    model = new_model(schema)
    floor = {"tool": "create_slab", "storey": "Level 1", "outline": [[0, 0], [8, 0], [8, 6], [0, 6]],
             "thickness": 0.215, "type": "new-2", "load_bearing": True, "status": "NEW"}  # fmt: skip
    roof = {"tool": "create_roof", "storey": "Level 1", "shape": "gable", "pitch": 30, "thickness": 0.25,
            "type": "new-3", "status": "NEW"}  # fmt: skip
    answer = run(model, [STOREYS_437982F, YV1, BJ1, TAK1, *TYPED_BOX, PARTITION, floor, roof], proposer="anna")
    assert answer["failed"] is None and answer["notes"] == [], answer
    assert list(answer["created"]) == [f"new-{n}" for n in range(1, 11)], "types, walls, slab and roof, in order"
    wall_type, slab_type, roof_type = (made(model, answer, ref) for ref in ("new-1", "new-2", "new-3"))
    assert (wall_type.is_a(), wall_type.Name, wall_type.PredefinedType) == ("IfcWallType", "YV1", "SOLIDWALL")
    assert (slab_type.PredefinedType, roof_type.is_a(), roof_type.PredefinedType) == ("FLOOR", "IfcSlabType", "ROOF")
    assert layers_of(wall_type) == [
        ("Puts", 0.02, None, finish[0]),
        ("Lättbetong", 0.25, "block", "LoadBearing"),
        ("Puts", 0.03, None, finish[1]),
    ], "the material's category and the layer's role, as the schema spells it"
    south = made(model, answer, "new-4")
    usage = ifcopenshell.util.element.get_material(south, should_skip_usage=False)
    assert ifcopenshell.util.element.get_type(south) == wall_type and south.PredefinedType is None
    assert (usage.LayerSetDirection, usage.DirectionSense) == ("AXIS2", "POSITIVE")
    assert usage.OffsetFromReferenceLine == pytest.approx(-0.15), "centred on the axis, the first layer outside"
    assert extrusion(south).SweptArea.YDim == pytest.approx(0.3)
    joins = {
        (r.RelatingElement.Name, r.RelatingConnectionType, r.RelatedElement.Name, r.RelatedConnectionType)
        for r in model.by_type("IfcRelConnectsPathElements")
    }
    assert ("S", "ATEND", "E", "ATSTART") in joins and ("Mid", "ATSTART", "S", "ATPATH") in joins and len(joins) == 6
    quantities = ifcopenshell.util.element.get_psets(south, qtos_only=True)["Qto_WallBaseQuantities"]
    assert quantities["Width"] == pytest.approx(0.3) and quantities["Height"] == pytest.approx(3)
    common = ifcopenshell.util.element.get_psets(south)["Pset_WallCommon"]
    assert (common["LoadBearing"], common["Status"], common["IsExternal"]) == (True, ["EXISTING"], True)
    middle = ifcopenshell.util.element.get_psets(made(model, answer, "new-8"))["Pset_WallCommon"]
    assert (middle["LoadBearing"], middle["IsExternal"]) == (False, False), "inside, from the topology"
    slab = made(model, answer, "new-9")
    assert ifcopenshell.util.element.get_type(slab) == slab_type
    assert ifcopenshell.util.element.get_psets(slab)["Pset_SlabCommon"]["Status"] == ["NEW"]
    typed_roof_slabs = {ifcopenshell.util.element.get_type(s) for s in roof_slabs(made(model, answer, "new-10"))}
    assert typed_roof_slabs == {roof_type}
    findings, errors = ServerChangeSet(model, "anna").findings()
    assert errors == 0, findings


def element(ifc_class: str, **fields: Any) -> dict[str, Any]:
    """A create_element step on Level 1, standing at (2, 3)."""
    return {"tool": "create_element", "storey": "Level 1", "ifc_class": ifc_class, "at": [2, 3], "z": 0,
            "rotation": 0, **fields}  # fmt: skip


def shape(profile: str, **fields: Any) -> dict[str, Any]:
    return {"profile": profile, "x": None, "y": None, "radius": None, "outline": None, "depth": None, "along": "z",
            **fields}  # fmt: skip


@pytest.mark.parametrize("schema", ["IFC4", "IFC4X3"])
def test_door_window_column_and_covering_types_and_the_elements_that_take_them(schema: str) -> None:
    """define_type's kinds without layers: a door and a window type with IfcOpenShell's geometry as a mapped
    representation, whose fillings take their size from them; a column type with its material; a layered covering
    type. create_element makes a column, a beam, a covering over a slab, a straight stair with its flight and
    landing, a railing as a part of the stair, and furniture of a kind of its own."""
    model = new_model(schema)
    door_type = {"tool": "define_type", "kind": "door", "name": "D1", "layers": None, "material": "Oak",
                 "material_category": "wood", "operation": "SINGLE_SWING_RIGHT", "width": 1.0, "height": 2.1,
                 "lining_depth": 0.05}  # fmt: skip
    window_type = {"tool": "define_type", "kind": "window", "name": "F1", "layers": None,
                   "partitioning": "DOUBLE_PANEL_VERTICAL", "width": 1.2, "height": 1.4, "lining_depth": 0.1}  # fmt: skip
    column_type = {"tool": "define_type", "kind": "column", "name": "C1", "layers": None, "material": "Concrete",
                   "material_category": "concrete"}  # fmt: skip
    covering_type = {"tool": "define_type", "kind": "covering", "name": "K1", "predefined_type": "FLOORING",
                     "layers": [layer("Tiles", 0.01, "stone"), layer("Glue", 0.005)]}  # fmt: skip
    door = {"tool": "create_opening", "wall_id": "new-5", "offset": 1, "width": 1.0, "height": 2.1, "sill": 0,
            "fill": "door", "type": "new-1", "side": "right"}  # fmt: skip
    window = {"tool": "create_opening", "wall_id": "new-5", "offset": 5, "width": 1.2, "height": 1.4, "sill": 0.9,
              "fill": "window", "type": "new-2", "side": "left"}  # fmt: skip
    floor = {"tool": "create_slab", "storey": "Level 1", "outline": [[0, 0], [8, 0], [8, 6], [0, 6]],
             "thickness": 0.2}  # fmt: skip
    flight = {"risers": 16, "riser_height": 0.1875, "tread_length": 0.25, "width": 1.0, "thickness": 0.2,
              "landing": 1.0}  # fmt: skip
    elements = [
        element("IfcColumn", name="P1", type="new-3", shape=shape("rectangle", x=0.3, y=0.3, depth=3)),
        element("IfcBeam", name="B1", predefined_type="LINTEL", at=[0, 3], z=2.7,
                shape=shape("rectangle", x=0.2, y=0.3, depth=4, along="x")),
        element("IfcCovering", name="Tiles", type="new-4", at=None, host="new-8",
                shape=shape("polygon", outline=[[0, 0], [4, 0], [4, 6], [0, 6]], depth=0.015)),
        element("IfcStair", name="Stair", at=[5, 1], rotation=90, stair=flight),
        element("IfcRailing", storey=None, name="Rail", predefined_type="HANDRAIL", at=[5.5, 1], z=0.9, rotation=90,
                part_of="new-12", shape=shape("circle", radius=0.025, depth=3.75, along="x")),
        element("IfcFurniture", predefined_type="USERDEFINED", object_type="Table", at=[6, 4],
                shape=shape("circle", radius=0.5, depth=0.75)),
    ]  # fmt: skip
    ops = [STOREYS, door_type, window_type, column_type, covering_type, {**WALL, "end": [8, 0]}, door, window, floor]
    answer = run(model, [*ops, *elements], proposer="anna")
    assert answer["failed"] is None, answer
    assert list(answer["created"]) == [f"new-{n}" for n in range(1, 15)]
    d1, f1 = made(model, answer, "new-1"), made(model, answer, "new-2")
    assert (d1.is_a(), d1.OperationType, d1.PredefinedType) == ("IfcDoorType", "SINGLE_SWING_RIGHT", "DOOR")
    assert (f1.is_a(), f1.PartitioningType) == ("IfcWindowType", "DOUBLE_PANEL_VERTICAL")
    assert [m.MappedRepresentation.RepresentationIdentifier for m in d1.RepresentationMaps] == ["Body"]
    linings = [p.Name if p.is_a("IfcPropertySet") else p.is_a() for p in d1.HasPropertySets]
    assert linings == (
        ["Pset_DoorLiningProperties", "Pset_DoorPanelProperties"]
        if schema == "IFC4X3"
        else ["IfcDoorLiningProperties", "IfcDoorPanelProperties"]
    ), "IFC4.3 deprecates the definitions for their standard sets"
    oak = ifcopenshell.util.element.get_material(d1)
    assert (oak.Name, oak.Category) == ("Oak", "wood")
    filled_door, filled_window = made(model, answer, "new-6"), made(model, answer, "new-7")
    assert ifcopenshell.util.element.get_type(filled_door) == d1 and filled_door.OverallWidth == pytest.approx(1.0)
    assert [i.is_a() for r in filled_door.Representation.Representations for i in r.Items] == ["IfcMappedItem"]
    assert ifcopenshell.util.element.get_type(filled_window) == f1
    assert filled_window.OverallHeight == pytest.approx(1.4)
    column, beam, covering, stair, railing, furniture = (made(model, answer, f"new-{n}") for n in range(9, 15))
    assert ifcopenshell.util.element.get_type(column).Name == "C1"
    assert ifcopenshell.util.element.get_material(column).Name == "Concrete", "from its type"
    assert ifcopenshell.util.element.get_container(column).Name == "Level 1"
    assert (beam.is_a(), beam.PredefinedType) == ("IfcBeam", "LINTEL")
    assert ifcopenshell.util.element.get_type(covering).Name == "K1"
    assert covering.Decomposes[0].RelatingObject == made(model, answer, "new-8"), (
        "IFC4 deprecates IfcRelCoversBldgElements: the covering is a part of the slab it covers"
    )
    parts = sorted((p.is_a(), p.PredefinedType) for r in stair.IsDecomposedBy for p in r.RelatedObjects)
    assert parts == [("IfcRailing", "HANDRAIL"), ("IfcSlab", "LANDING"), ("IfcStairFlight", "STRAIGHT")]
    assert stair.PredefinedType == "STRAIGHT_RUN_STAIR" and railing.Decomposes[0].RelatingObject == stair
    assert not railing.ContainedInStructure, "a part is in the storey through its whole"
    (run_of_steps,) = [p for r in stair.IsDecomposedBy for p in r.RelatedObjects if p.is_a("IfcStairFlight")]
    risers = ifcopenshell.util.element.get_psets(run_of_steps)["Pset_StairFlightCommon"]
    assert risers["RiserHeight"] == pytest.approx(0.1875) and risers["NumberOfRiser"] == 16
    assert (furniture.PredefinedType, furniture.ObjectType) == ("USERDEFINED", "Table")
    findings, errors = ServerChangeSet(model, "anna").findings()
    assert errors == 0, findings


@pytest.mark.parametrize("schema", ["IFC4", "IFC4X3"])
def test_storeys_rooms_materials_and_the_site_take_their_new_fields(schema: str) -> None:
    """A storey's description and long name, a room's number and type, the material's category and the vertical
    datum; IFC4.3 deprecates a storey's Elevation and a space's INTERNAL and EXTERNAL (bSI rule IFC102)."""
    model = new_model(schema)
    kitchen = {"at": [3, 3], "index": None, "name": "Kitchen", "long_name": "Kitchen to the west", "number": "101",
               "room_type": "Kitchen"}  # fmt: skip
    living = {"at": [7, 3], "index": None, "name": "Living room", "long_name": None}
    rooms = {"tool": "create_spaces", "storey": "Level 1", "rooms": [kitchen, living], "height": None}
    material = {"tool": "assign", "ids": ["new-1"], "storey": None, "material": "Concrete", "category": "concrete"}
    site = {"tool": "set_site", "latitude": 59.33, "longitude": 18.07, "elevation": 12, "crs": "EPSG:3006",
            "eastings": 674032, "northings": 6580822, "rotation": 0, "vertical_datum": "RH 2000"}  # fmt: skip
    middle = {**PARTITION, "start": [5, 0], "end": [5, 6]}
    answer = run(model, [STOREYS_437982F, *FOUR_WALLS, middle, rooms, material, site], proposer="anna")
    assert answer["failed"] is None, answer
    first = next(s for s in model.by_type("IfcBuildingStorey") if s.Name == "Level 1")
    assert (first.Description, first.LongName) == ("Level 1 (Entrance)", "Entrance level")
    assert first.Elevation == (None if schema == "IFC4X3" else 0), "the height in the placement alone in IFC4.3"
    numbered, plain = made(model, answer, "new-6"), made(model, answer, "new-7")
    assert (numbered.Name, numbered.LongName, numbered.Description) == ("101", "Kitchen", "Kitchen to the west")
    assert (numbered.ObjectType, numbered.PredefinedType) == ("Kitchen", "USERDEFINED")
    assert (plain.Name, plain.LongName) == ("Living room", None)
    assert plain.PredefinedType == ("SPACE" if schema == "IFC4X3" else "INTERNAL")
    concrete = ifcopenshell.util.element.get_material(made(model, answer, "new-1"))
    assert (concrete.Name, concrete.Category) == ("Concrete", "concrete")
    (crs,) = model.by_type("IfcProjectedCRS")
    assert (crs.Name, crs.VerticalDatum, crs.Description) == ("EPSG:3006", "RH 2000", "SWEREF 99 TM + RH 2000")
    findings, errors = ServerChangeSet(model, "anna").findings()
    assert errors == 0, findings


@pytest.mark.parametrize("schema", ["IFC4", "IFC4X3"])
def test_edit_element_changes_elements_in_place_and_keeps_their_globalids(schema: str) -> None:
    """edit_element: a name, a door's offset with its opening, a roof's pitch, a slab's outline and a wall's end, each
    on the element itself; a field its kind does not take, and a door beyond its wall, are refused."""
    model = new_model(schema)
    floor = {"tool": "create_slab", "storey": "Level 1", "outline": [[0, 0], [10, 0], [10, 6], [0, 6]],
             "thickness": 0.2}  # fmt: skip
    gable = {"tool": "create_roof", "storey": "Level 1", "shape": "gable", "pitch": 30, "overhang": 0.5}
    door = {**DOOR, "wall_id": "new-1"}
    built = run(model, [STOREYS, *FOUR_WALLS, door, floor, gable], proposer="anna")
    assert built["failed"] is None, built
    guids = dict(built["created"])
    edits = [
        {"tool": "edit_element", "id": guids["new-1"], "name": "South"},
        {"tool": "edit_element", "id": guids["new-5"], "offset": 3},
        {"tool": "edit_element", "id": guids["new-7"], "pitch": 20},
        {"tool": "edit_element", "id": guids["new-6"], "outline": [[0, 0], [10, 0], [10, 7], [0, 7]]},
    ]
    answer = run(model, edits, proposer="anna")
    assert answer["failed"] is None and answer["created"] == {}, answer
    south, filled, slab, roof = (model.by_guid(guids[ref]) for ref in ("new-1", "new-5", "new-6", "new-7"))
    assert south.Name == "South" and {guids[f"new-{n}"] for n in (1, 5, 6, 7)} <= set(answer["objects"])
    (opening,) = model.by_type("IfcOpeningElement")
    assert placed_at(filled) == pytest.approx([3, 0, 0]) and placed_at(opening) == pytest.approx([3, 0, 0])
    corners = [tuple(p.Coordinates) for p in extrusion(slab).SweptArea.OuterCurve.Points][:4]
    assert corners == [(0, 0), (10, 0), (10, 7), (0, 7)]
    assert len(roof_slabs(roof)) == 2
    wrong = run(model, [{"tool": "edit_element", "id": guids["new-1"], "pitch": 20}], proposer="anna")
    assert wrong["failed"]["error"].endswith("takes start, end, thickness, height, type or name, not pitch")
    beyond = run(model, [{"tool": "edit_element", "id": guids["new-5"], "offset": 9.5}], proposer="anna")
    assert "would reach beyond wall" in beyond["failed"]["error"]
    longer = run(model, [{"tool": "edit_element", "id": guids["new-1"], "end": [11, 0]}], proposer="anna")
    assert longer["failed"] is None and model.by_guid(guids["new-1"]) == south, longer
    (axis,) = [r for r in south.Representation.Representations if r.RepresentationIdentifier == "Axis"]
    assert [tuple(p.Coordinates) for p in axis.Items[0].Points] == [(0, 0), (11, 0)], "the centre line, as drawn"
    assert placed_at(filled) == pytest.approx([3, 0, 0]), "the door keeps its place along the wall"


@pytest.mark.parametrize("schema", ["IFC4", "IFC4X3"])
def test_set_properties_holds_ifcs_own_sets_to_their_templates(schema: str) -> None:
    """A set named Pset_ or Qto_ is checked against IfcOpenShell's template of the file's schema: an unknown set or
    property, a value of the wrong type or outside an enumeration, and a number with its unit are refused; a set of
    the model's own takes any property, but never a unit in a value."""
    model = new_model(schema)
    assert run(model, [STOREYS, WALL], proposer="anna")["failed"] is None
    wall = model.by_type("IfcWall")[0].GlobalId

    def refused(pset: str, properties: dict[str, Any]) -> str:
        op = {"tool": "set_properties", "ids": [wall], "pset": pset, "properties": properties}
        answer = run(model, [op], proposer="anna")
        assert answer["failed"] is not None, (pset, properties)
        return answer["failed"]["error"]

    assert refused("Pset_WallCommon", {"Colour": "red"}).startswith("Pset_WallCommon has no property Colour")
    assert refused("Pset_WallCommon", {"LoadBearing": "yes"}) == (
        "Pset_WallCommon.LoadBearing is true or false, not 'yes'"
    )
    assert refused("Pset_WallCommon", {"ThermalTransmittance": "0.18 W/m2K"}) == (
        "Pset_WallCommon.ThermalTransmittance: give the number only, without its unit (0.18, not '0.18 W/m2K'): IFC "
        "gives the property its unit"
    )
    assert refused("Pset_WallCommon", {"Status": "PLANNED"}).startswith("Pset_WallCommon.Status takes one of ")
    assert refused("Pset_MyOwn", {"A": 1}).startswith(f"Pset_MyOwn is not a property or quantity set of {schema};")
    assert refused("SE-ACME-42_Acoustics", {"Rw": "52 dB"}).startswith("SE-ACME-42_Acoustics.Rw: give the number only")
    fine = {"ThermalTransmittance": 0.18, "loadbearing": True, "Status": "NEW"}
    op = {"tool": "set_properties", "ids": [wall], "pset": "Pset_WallCommon", "properties": fine}
    assert run(model, [op], proposer="anna")["failed"] is None
    common = ifcopenshell.util.element.get_psets(model.by_guid(wall))["Pset_WallCommon"]
    assert (common["ThermalTransmittance"], common["LoadBearing"], common["Status"]) == (0.18, True, ["NEW"]), (
        "the template's spelling of a name, and an enumeration as a list"
    )


@pytest.mark.parametrize("schema", ["IFC4", "IFC4X3"])
def test_a_door_moves_with_its_opening_and_the_site_building_and_storeys_stay(schema: str) -> None:
    model = new_model(schema)
    built = run(model, [STOREYS, WALL, DOOR], proposer="anna")
    door = made(model, built, "new-2")
    step = {"tool": "transform_elements", "ids": [door.GlobalId], "dx": 1, "dy": 0, "dz": 0}
    assert run(model, [step], proposer="anna")["failed"] is None
    (opening,) = model.by_type("IfcOpeningElement")
    assert placed_at(door) == pytest.approx([2, 0, 0]) and placed_at(opening) == pytest.approx([2, 0, 0])
    for whole in (*model.by_type("IfcSite"), *model.by_type("IfcBuilding"), model.by_type("IfcBuildingStorey")[0]):
        answer = run(model, [{**step, "ids": [whole.GlobalId]}], proposer="anna")
        assert answer["failed"]["error"].startswith(f"{whole.is_a()} #{whole.id()} {whole.Name!r} is not moved: ")
