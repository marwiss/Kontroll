# This file was generated with the assistance of an AI coding tool.
"""Dataspatium's write tools applied with the app's own code (``opencde/ifcgraph/ops.py``), on small files made here:
storeys, a grid, walls, slabs, roofs and openings with their refs, elements named by GlobalId, properties, a
classification, a storey and a material, a move, a deletion, the site with an EPSG code, the units of a millimetre
file and the owner histories. The trial around it is proved against a database in
``tests/integration/test_ifc_proposal.py``."""

from __future__ import annotations

import math
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest

from tests.conftest import FIXTURES_DIR

pytest.importorskip("ifcopenshell", reason="the ifc-lpg extra is not installed")

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
from opencde.ifcgraph.ops import SERVER, ServerChangeSet, _ChangeSet, run

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
    (representation,) = element.Representation.Representations
    (solid,) = representation.Items
    return solid


def test_every_tool_of_the_schema_is_an_operation_of_the_copy() -> None:
    """The schema's names and the copy's ``op_`` methods are one list, so neither has a tool the other lacks."""
    operations = {name[3:] for name in dir(_ChangeSet) if name.startswith("op_")}
    assert operations == set(OPS_TOOLS)


def test_the_tools_that_create_hand_out_the_refs() -> None:
    assert _ChangeSet.CREATES == ("create_wall", "create_slab", "create_roof", "create_opening")


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
    assert (conversion.Eastings, conversion.OrthogonalHeight) == pytest.approx((600_000_000, 20_000))
    assert model.by_type("IfcProjectedCRS")[0].MapZone == "UTM 32N"


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
    tagged = {"tool": "set_properties", "pset": "Pset_Test", "properties": {"Tagged": True}}
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
        assert ifcopenshell.util.element.get_psets(element)["Pset_Test"]["Tagged"] is True
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
