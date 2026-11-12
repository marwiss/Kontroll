# This file was generated with the assistance of an AI coding tool.
"""The rooms of each storey (F36 a, the server makes the client's room check) from the copy of Dataspatium's topology
(``opencde/ifcgraph/ops.py``), through the worker (``opencde/ifcgraph/topology.py``), on small files made here with
the copied write tools: a closed room of four walls, a room with a door, a storey with a dangling wall and an open
one, walls with and without an Axis, a wall that cannot be read, north from the map conversion, the storeys of an
IFC4X3 file by their placements, and the answer's limits. The section in the reports is tried in
``test_ifc_rooms.py``."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("shapely", reason="the ifc-db extra is not installed")
pytest.importorskip("ifcopenshell", reason="the ifc-db extra is not installed")

import ifcopenshell
import ifcopenshell.api.root
import ifcopenshell.api.spatial
import ifcopenshell.util.element

from opencde.ifcgraph import ops
from opencde.ifcgraph import topology as worker
from opencde.ifcgraph.ops import run
from tests.unit.test_ifc_ops import DOOR, FOUR_WALLS, STOREYS, new_model

FACINGS = {"new-1": "S", "new-2": "E", "new-3": "N", "new-4": "W"}  # the walls of FOUR_WALLS, by their refs
STUB = {"tool": "create_wall", "storey": "Level 1", "start": [5, 0], "end": [5, 2], "thickness": 0.2, "height": 3}


def built(*more: dict[str, Any], walls: list[dict[str, Any]] = FOUR_WALLS) -> tuple[Any, dict[str, str]]:
    """A file with two storeys and the walls on the lower one, as the app's write tools make it; and the refs."""
    model = new_model()
    answer = run(model, [STOREYS, *walls, *more], proposer="anna")
    assert answer["failed"] is None, answer
    return model, answer["created"]


def rooms_of(model: Any) -> dict[str, Any]:
    """The worker's section for the lower storey of the model."""
    return worker.section(model, ops._ifc_topology(model))["storeys"][0]


def test_a_closed_room_of_four_walls_is_one_room_with_four_external_walls() -> None:
    model, refs = built()
    storey = rooms_of(model)
    assert (storey["storey"], storey["elevation"], storey["closed"]) == ("Level 1", 0.0, True)
    (room,) = storey["rooms"]
    assert room == {
        "index": 1,
        "area": 60.0,
        "perimeter": 32.0,
        "walls": sorted(refs[ref] for ref in FACINGS),
        "neighbours": [],
    }, "between the centre lines: 10 by 6 m"
    assert {wall["global_id"]: wall["facing"] for wall in storey["external"]} == {
        refs[ref]: facing for ref, facing in FACINGS.items()
    }
    assert [wall["facing"] for wall in storey["external"]] == ["N", "E", "S", "W"], "in the order of the compass"
    assert [wall["length"] for wall in storey["external"]] == [10.0, 6.0, 10.0, 6.0]
    assert (storey["dangles"], storey["dangling_walls"], storey["walls"], storey["unread"]) == ([], [], 4, 0)
    assert (storey["tolerance"], storey["north"]) == (0.15, "model"), "half of 0.2 m plus 0.05 m; no north given"


def test_a_door_leaves_the_room_closed_and_an_inner_wall_makes_two_neighbours() -> None:
    model, _ = built(DOOR)
    storey = rooms_of(model)
    assert storey["closed"] and len(storey["rooms"]) == 1 and storey["walls"] == 4, "the door is no wall"
    middle = {"tool": "create_wall", "storey": "Level 1", "start": [4, 0], "end": [4, 6], "thickness": 0.2}
    model, refs = built(middle)
    storey = rooms_of(model)
    assert [(room["index"], room["area"], room["neighbours"]) for room in storey["rooms"]] == [
        (1, 24.0, [2]),
        (2, 36.0, [1]),
    ], "from west to east"
    assert all(refs["new-5"] in room["walls"] for room in storey["rooms"]) and storey["closed"]
    assert refs["new-5"] not in {wall["global_id"] for wall in storey["external"]}, "an inner wall"


def test_a_dangling_wall_leaves_the_storey_open_and_is_named() -> None:
    model, refs = built(STUB)
    storey = rooms_of(model)
    assert len(storey["rooms"]) == 1 and storey["closed"] is False, "the room is there, the storey is not closed"
    assert storey["dangles"] == [[5.0, 2.0]] and storey["dangling_walls"] == [refs["new-5"]]
    model, refs = built(walls=FOUR_WALLS[:3])
    storey = rooms_of(model)
    assert (storey["rooms"], storey["external"], storey["closed"]) == ([], [], False), "three walls enclose nothing"
    assert storey["dangles"] == [[0.0, 0.0], [0.0, 6.0]]
    assert storey["dangling_walls"] == sorted([refs["new-1"], refs["new-3"]]), "the south and the north wall"


def test_walls_without_an_axis_are_read_from_their_body_and_a_wall_without_either_is_named() -> None:
    """A wall from another program may lack the Axis: its centre line is then the long axis of its body's footprint,
    which the geometry kernel builds. One with no shape at all is counted and named, and the others stand."""
    model, refs = built()
    for ref in ("new-1", "new-2"):
        shape = model.by_guid(refs[ref]).Representation
        shape.Representations = [r for r in shape.Representations if r.RepresentationIdentifier == "Body"]
    (storey_entity,) = [s for s in model.by_type("IfcBuildingStorey") if s.Name == "Level 1"]
    bare = ifcopenshell.api.root.create_entity(model, ifc_class="IfcWall", name="Bare")
    ifcopenshell.api.spatial.assign_container(model, products=[bare], relating_structure=storey_entity)
    storey = rooms_of(model)
    assert (storey["walls"], storey["unread"], storey["unread_walls"]) == (5, 1, [bare.GlobalId])
    (room,) = storey["rooms"]
    assert room["area"] == pytest.approx(60.0) and storey["closed"], "the footprints meet the axes"
    assert {wall["global_id"] for wall in storey["external"]} == {refs[ref] for ref in FACINGS}


def test_north_comes_from_the_map_conversion() -> None:
    """With the model's x axis turned to the map's north, the east wall faces north."""
    site = {"tool": "set_site", "latitude": 59.3, "longitude": 18.1, "crs": "EPSG:3006", "eastings": 674032.5,
            "northings": 6580821.25, "rotation": 90}  # fmt: skip
    model, refs = built(site)
    storey = rooms_of(model)
    assert storey["north"] == "map"
    assert {wall["global_id"]: wall["facing"] for wall in storey["external"]} == {
        refs["new-1"]: "E",
        refs["new-2"]: "N",
        refs["new-3"]: "W",
        refs["new-4"]: "S",
    }


def test_the_storeys_of_an_ifc4x3_file_have_no_elevation_and_are_ordered_by_their_placement() -> None:
    """IFC4X3 deprecates a storey's Elevation (bSI rule IFC102): create_storeys_and_grid gives the height to the
    placement alone, and the lowest and the highest storey, and the topology's order, come from the placements."""
    model = new_model("IFC4X3")
    upside_down = {
        "tool": "create_storeys_and_grid",
        "storeys": [{"name": "Level 2", "elevation": 3.5}, {"name": "Level 1", "elevation": 0}],
    }
    outline = [[0, 0], [10, 0], [10, 6], [0, 6]]
    slab = {"tool": "create_slab", "outline": outline}
    roof = {"tool": "create_roof", "shape": "flat", "outline": outline, "base": 3}
    answer = run(model, [upside_down, *FOUR_WALLS, slab, roof], proposer="anna")
    assert answer["failed"] is None, answer
    assert [(s.Name, s.Elevation) for s in model.by_type("IfcBuildingStorey")] == [("Level 2", None), ("Level 1", None)]
    slab_at, roof_at = (
        ifcopenshell.util.element.get_container(model.by_guid(answer["created"][ref])).Name
        for ref in ("new-5", "new-6")
    )
    assert (slab_at, roof_at) == ("Level 1", "Level 2"), "no storey named: the lowest, and for a roof the highest"
    assert [(s["storey"], s["elevation"]) for s in ops._ifc_topology(model)] == [("Level 1", 0.0), ("Level 2", 3.5)]
    assert len(rooms_of(model)["rooms"]) == 1 and rooms_of(model)["closed"]


def test_the_rooms_are_numbered_as_the_app_numbers_them() -> None:
    """The rooms of one row of the plan are numbered from west to east, and a room around another, with the same
    centre, comes before it."""
    model, _ = built({"tool": "create_wall", "storey": "Level 1", "start": [7, 0], "end": [7, 6], "thickness": 0.2})
    assert [room["area"] for room in rooms_of(model)["rooms"]] == [42.0, 18.0]
    inner = [
        {"tool": "create_wall", "storey": "Level 1", "start": start, "end": end, "thickness": 0.2}
        for start, end in (([3, 2], [7, 2]), ([7, 2], [7, 4]), ([7, 4], [3, 4]), ([3, 4], [3, 2]))
    ]
    model, _ = built(*inner)
    storey = rooms_of(model)
    assert [(room["area"], room["neighbours"]) for room in storey["rooms"]] == [(52.0, [2]), (8.0, [1])]
    assert len(storey["external"]) == 4 and storey["closed"], "the inner walls face no outside"


def test_the_answer_is_cut_where_its_lists_are_long_and_says_so() -> None:
    model, _ = built()
    (found,) = [x for x in ops._ifc_topology(model) if x["storey"] == "Level 1"]
    many = {**found, "storey": "x" * 500, "dangles": [[0.0, float(i)] for i in range(worker.MAX_LISTED + 5)]}
    answer = worker.section(model, [many] * (worker.MAX_STOREYS + 1))
    assert answer["cut"] is True and len(answer["storeys"]) == worker.MAX_STOREYS
    assert len(answer["storeys"][0]["dangles"]) == worker.MAX_LISTED and len(answer["storeys"][0]["storey"]) == 200
    assert worker.section(model, [found])["cut"] is False
    assert json.loads(json.dumps(worker.section(model, [found]))) == worker.section(model, [found]), "plain JSON"


def test_the_worker_answers_on_stdout_and_its_errors_without_the_files_words(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    model, refs = built(DOOR)
    path = tmp_path / "walls.ifc"
    model.write(str(path))
    done = subprocess.run(  # noqa: S603  # the arguments are this test's own
        [sys.executable, "-m", "opencde.ifcgraph.topology", str(path), "--memory-mb", "2048"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    answer = json.loads(done.stdout.strip().splitlines()[-1])
    assert answer["cut"] is False and [s["storey"] for s in answer["storeys"]] == ["Level 1", "Level 2"]
    assert answer["storeys"][0]["rooms"][0]["walls"] == sorted(refs[ref] for ref in FACINGS)

    broken = tmp_path / "broken.ifc"
    broken.write_text("ISO-10303-21;\nDATA;\n#1=IFCWALL('a secret of the file');\nENDSEC;\n", encoding="utf-8")
    assert worker.main([str(broken)]) == 0
    said = json.loads(capsys.readouterr().out)
    assert set(said) == {"error"} and "secret" not in said["error"], "only what was raised"
    monkeypatch.setattr(ops, "TOPOLOGY_MAX_WALLS", 3)
    assert worker.main([str(path)]) == 0
    assert json.loads(capsys.readouterr().out) == {"error": "the topology reads at most 3 walls; there are 4"}
