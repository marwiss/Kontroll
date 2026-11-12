# This file was generated with the assistance of an AI coding tool.
"""The copy of Dataspatium's write tools (``opencde/mcp/write_tools.py``) against what the app's own code answers.

The calls below are the examples of the app's tests (``tests/ai-change``, ``ai-roof``, ``ai-spaces`` and ``ai-site``
at Dataspatium's f43), with the fields commit 64e116e added (a partition wall, a classification's system, an outline
that repeats its first corner), and the answers and operations are what ``src/ai/write-tools.js`` at 64e116e gave for
them, run with Node from a copy of the file: the port must answer the same, refs and errors included, and hand the
wheel the same operations. The tools and fields of commit 437982f (``define_type``, ``create_element``,
``edit_element``, a typed wall, slab, roof and opening, load_bearing and status, a storey's description, a room's
number and type, a material's category and the vertical datum) are tried by the calls in
``fixtures/write_tools_437982f.json``, one sequence that builds and one that is refused, with the answers and
operations that the app's file at 437982f gave for them; at 437982f the app still answers the examples below as it
did at 64e116e. JavaScript's own ways with numbers, texts and objects are tried one by one below.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from opencde.mcp import write_tools
from tests.conftest import FIXTURES_DIR

#: What the app's write-tools.js at 437982f answered: per sequence the calls with their answers, and the wheel's list.
AT_437982F = json.loads((FIXTURES_DIR / "write_tools_437982f.json").read_text(encoding="utf-8"))
#: The server's words where the app's name a tool the server does not offer (the module's docstring).
SERVER_WORDS = ((" (search_ifc_class gives them)", ""), (" (search_ifc_class)", ""))

# The calls, the client's answer to each, and the operations its toWheel gave at the end.
THE_CHANGE_TEST = [
    (
        "create_storeys_and_grid",
        {
            "storeys": [{"name": "Plan 1", "elevation": 0}, {"name": "Plan 2", "elevation": 3}],
            "grid": {"x_spacing": 6, "x_count": 1, "y_spacing": 4, "y_count": 1},
        },
        {"ok": True, "step": 1, "description": "Storeys: Plan 1 (0 m), Plan 2 (3 m); grid of 1×1 bays of 6×4 m"},
    ),
    (
        "create_wall",
        {"storey": "Plan 1", "start": [0, 0], "end": [6, 0], "thickness": None, "height": None, "name": "Vägg S"},
        {
            "ok": True,
            "step": 2,
            "description": "new-1 Wall Vägg S on Plan 1 from (0, 0) to (6, 0), 0.2 m thick, 3 m high",
            "ref": "new-1",
        },
    ),
    (
        "create_slab",
        {"storey": "Plan 1", "outline": None, "thickness": None, "name": None},
        {
            "ok": True,
            "step": 3,
            "description": "new-2 Slab  on Plan 1, 0.25 m thick, following the grid",
            "ref": "new-2",
        },
    ),
    (
        "create_opening",
        {"wall_id": "new-1", "offset": 1, "width": None, "height": None, "sill": None, "fill": "door", "name": "Dörr"},
        {
            "ok": True,
            "step": 4,
            "description": "new-3 Door Dörr in wall new-1, 0.9×2.1 m, 1 m from the wall's start",
            "ref": "new-3",
        },
    ),
    (
        "create_opening",
        {"wall_id": "new-9", "offset": 1, "width": None, "height": None, "sill": None, "fill": None, "name": None},
        {"error": "new-9 is not a ref of this change set (new-1 to new-3)"},
    ),
    (
        "create_wall",
        {"storey": None, "start": [0, 0], "end": [0, 0], "thickness": 0.2, "height": 3, "name": None},
        {"error": "start and end are the same point"},
    ),
    (
        "create_wall",
        {"storey": None, "start": [0, 0], "end": [1, 0], "thickness": -1, "height": 3, "name": None},
        {"error": "thickness must be greater than zero"},
    ),
    (
        "set_properties",
        {
            "ids": ["new-1", 12],
            "pset": "Pset_WallCommon",
            "properties": [{"name": "IsExternal", "value": True}, {"name": "FireRating", "value": "EI60"}],
        },
        {"ok": True, "step": 5, "description": "Pset_WallCommon on new-1, 12: IsExternal = true, FireRating = EI60"},
    ),
    ("assign", {"ids": [12], "storey": None, "material": None}, {"error": "give a storey, a material or both"}),
    (
        "transform_elements",
        {"ids": [12], "dx": 0, "dy": None, "dz": 0},
        {"error": "nothing to move: dx, dy and dz are all zero"},
    ),
    (
        "delete_elements",
        {"ids": [12], "confirm": None},
        {"error": "deleting needs confirm: true, and only when the person asked for it in this conversation"},
    ),
    (
        "delete_elements",
        {"ids": ["1Xezbq735AdBO_4DerG66G"], "confirm": True},
        {"ok": True, "step": 6, "description": "Delete 1Xezbq735AdBO_4DerG66G"},
    ),
    (
        "manage_changeset",
        {"action": "list"},
        {
            "steps": [
                {
                    "step": 1,
                    "tool": "create_storeys_and_grid",
                    "ref": None,
                    "description": "Storeys: Plan 1 (0 m), Plan 2 (3 m); grid of 1×1 bays of 6×4 m",
                },
                {
                    "step": 2,
                    "tool": "create_wall",
                    "ref": "new-1",
                    "description": "new-1 Wall Vägg S on Plan 1 from (0, 0) to (6, 0), 0.2 m thick, 3 m high",
                },
                {
                    "step": 3,
                    "tool": "create_slab",
                    "ref": "new-2",
                    "description": "new-2 Slab  on Plan 1, 0.25 m thick, following the grid",
                },
                {
                    "step": 4,
                    "tool": "create_opening",
                    "ref": "new-3",
                    "description": "new-3 Door Dörr in wall new-1, 0.9×2.1 m, 1 m from the wall's start",
                },
                {
                    "step": 5,
                    "tool": "set_properties",
                    "ref": None,
                    "description": "Pset_WallCommon on new-1, 12: IsExternal = true, FireRating = EI60",
                },
                {"step": 6, "tool": "delete_elements", "ref": None, "description": "Delete 1Xezbq735AdBO_4DerG66G"},
            ]
        },
    ),
    (
        "manage_changeset",
        {"action": "remove_last"},
        {"ok": True, "removed": "Delete 1Xezbq735AdBO_4DerG66G", "steps": 5},
    ),
    ("manage_changeset", {"action": "undo"}, {"error": "action must be list, remove_last or clear"}),
]
THE_CHANGE_TEST_WHEEL = [
    {
        "tool": "create_storeys_and_grid",
        "storeys": [{"name": "Plan 1", "elevation": 0}, {"name": "Plan 2", "elevation": 3}],
        "grid": {"x_spacing": 6, "x_count": 1, "y_spacing": 4, "y_count": 1},
    },
    {
        "tool": "create_wall",
        "storey": "Plan 1",
        "start": [0, 0],
        "end": [6, 0],
        "thickness": 0.2,
        "height": 3,
        "name": "Vägg S",
    },
    {"tool": "create_slab", "storey": "Plan 1", "outline": None, "thickness": 0.25, "name": None},
    {
        "tool": "create_opening",
        "wall_id": "new-1",
        "offset": 1,
        "width": 0.9,
        "height": 2.1,
        "sill": 0,
        "fill": "door",
        "name": "Dörr",
    },
    {
        "tool": "set_properties",
        "ids": ["new-1", 12],
        "pset": "Pset_WallCommon",
        "properties": {"IsExternal": True, "FireRating": "EI60"},
    },
]
THE_ROOF_TEST = [
    (
        "create_roof",
        {
            "storey": "Plan 3",
            "shape": "gable",
            "outline": [[0, 0], [12, 0], [12, 8], [0, 8]],
            "pitch": None,
            "overhang": None,
            "thickness": None,
            "ridge": None,
            "base": None,
            "name": None,
        },
        {
            "ok": True,
            "step": 1,
            "description": "new-1 Roof on Plan 3: gable roof 30° over 12 × 8 m, overhang 0.4 m",
            "ref": "new-1",
        },
    ),
    (
        "create_roof",
        {
            "storey": "Plan 3",
            "shape": "flat",
            "outline": None,
            "pitch": 80,
            "overhang": None,
            "thickness": None,
            "ridge": "y",
            "base": None,
            "name": None,
        },
        {"ok": True, "step": 2, "description": "new-2 Roof on Plan 3: flat roof over the walls", "ref": "new-2"},
    ),
    (
        "create_roof",
        {
            "storey": None,
            "shape": "SHED",
            "outline": [[0, 0], [6, 0], [6, 4], [3, 6], [0, 4]],
            "pitch": 12.5,
            "overhang": 0.6,
            "thickness": 0.3,
            "ridge": "X",
            "base": 5.4,
            "name": "Huvudtak",
        },
        {
            "ok": True,
            "step": 3,
            "description": "new-3 Roof Huvudtak on the top storey: shed roof 12.5° over 6 × 6 m, overhang 0.6 m",
            "ref": "new-3",
            "note": "the outline is not a rectangle along x and y (5 corners), so for now the roof covers its bounding box: 6 × 6 m from (0, 0)",
        },
    ),
    (
        "create_roof",
        {
            "storey": None,
            "shape": "gable",
            "outline": None,
            "pitch": 80,
            "overhang": None,
            "thickness": None,
            "ridge": None,
            "base": None,
            "name": None,
        },
        {"error": "pitch must be more than 0 and at most 75 degrees; use shape flat for a flat roof"},
    ),
]
THE_ROOF_TEST_WHEEL = [
    {
        "tool": "create_roof",
        "storey": "Plan 3",
        "shape": "gable",
        "outline": [[0, 0], [12, 0], [12, 8], [0, 8]],
        "pitch": 30,
        "overhang": 0.4,
        "thickness": 0.25,
        "ridge": None,
        "base": None,
        "name": None,
    },
    {
        "tool": "create_roof",
        "storey": "Plan 3",
        "shape": "flat",
        "outline": None,
        "pitch": 0,
        "overhang": 0,
        "thickness": 0.25,
        "ridge": None,
        "base": None,
        "name": None,
    },
    {
        "tool": "create_roof",
        "storey": None,
        "shape": "shed",
        "outline": [[0, 0], [6, 0], [6, 4], [3, 6], [0, 4]],
        "pitch": 12.5,
        "overhang": 0.6,
        "thickness": 0.3,
        "ridge": "x",
        "base": 5.4,
        "name": "Huvudtak",
    },
]
THE_SPACES_TEST = [
    (
        "create_storeys_and_grid",
        {
            "storeys": [{"name": "Plan 3", "elevation": 6}],
            "grid": {"x_spacing": 6, "x_count": 2, "y_spacing": 8, "y_count": 1},
        },
        {"ok": True, "step": 1, "description": "Storeys: Plan 3 (6 m); grid of 2×1 bays of 6×8 m"},
    ),
    (
        "create_wall",
        {"storey": "Plan 3", "start": [0, 0], "end": [12, 0], "thickness": 0.2, "height": 3, "name": "Syd"},
        {
            "ok": True,
            "step": 2,
            "description": "new-1 Wall Syd on Plan 3 from (0, 0) to (12, 0), 0.2 m thick, 3 m high",
            "ref": "new-1",
        },
    ),
    (
        "create_wall",
        {"storey": "Plan 3", "start": [12, 0], "end": [12, 8], "thickness": 0.2, "height": 3, "name": "Öst"},
        {
            "ok": True,
            "step": 3,
            "description": "new-2 Wall Öst on Plan 3 from (12, 0) to (12, 8), 0.2 m thick, 3 m high",
            "ref": "new-2",
        },
    ),
    (
        "create_wall",
        {"storey": "Plan 3", "start": [12, 8], "end": [0, 8], "thickness": 0.2, "height": 3, "name": "Norr"},
        {
            "ok": True,
            "step": 4,
            "description": "new-3 Wall Norr on Plan 3 from (12, 8) to (0, 8), 0.2 m thick, 3 m high",
            "ref": "new-3",
        },
    ),
    (
        "create_wall",
        {"storey": "Plan 3", "start": [0, 8], "end": [0, 0], "thickness": 0.2, "height": 3, "name": "Väst"},
        {
            "ok": True,
            "step": 5,
            "description": "new-4 Wall Väst on Plan 3 from (0, 8) to (0, 0), 0.2 m thick, 3 m high",
            "ref": "new-4",
        },
    ),
    (
        "create_wall",
        {"storey": "Plan 3", "start": [6, 0], "end": [6, 8], "thickness": 0.2, "height": 3, "name": "Mitt"},
        {
            "ok": True,
            "step": 6,
            "description": "new-5 Wall Mitt on Plan 3 from (6, 0) to (6, 8), 0.2 m thick, 3 m high",
            "ref": "new-5",
        },
    ),
    (
        "create_opening",
        {"wall_id": "new-5", "offset": 3, "width": 0.9, "height": 2.1, "sill": 0, "fill": "door", "name": "Dörr"},
        {
            "ok": True,
            "step": 7,
            "description": "new-6 Door Dörr in wall new-5, 0.9×2.1 m, 3 m from the wall's start",
            "ref": "new-6",
        },
    ),
    (
        "create_spaces",
        {
            "storey": "Plan 3",
            "rooms": [
                {"at": [3, 4], "index": None, "name": "Kök", "long_name": None},
                {"at": [9, 4], "index": None, "name": "Vardagsrum", "long_name": "Vardagsrum med matplats"},
            ],
            "height": None,
        },
        {
            "ok": True,
            "step": 8,
            "description": "new-7–new-8 Rooms on Plan 3: Kök at (3, 4), Vardagsrum at (9, 4)",
            "refs": ["new-7", "new-8"],
        },
    ),
    (
        "set_properties",
        {"ids": ["new-8"], "pset": "Pset_SpaceCommon", "properties": [{"name": "IsExternal", "value": False}]},
        {"ok": True, "step": 9, "description": "Pset_SpaceCommon on new-8: IsExternal = false"},
    ),
    (
        "manage_changeset",
        {"action": "remove_last"},
        {"ok": True, "removed": "Pset_SpaceCommon on new-8: IsExternal = false", "steps": 8},
    ),
    (
        "manage_changeset",
        {"action": "remove_last"},
        {"ok": True, "removed": "new-7–new-8 Rooms on Plan 3: Kök at (3, 4), Vardagsrum at (9, 4)", "steps": 7},
    ),
    (
        "create_spaces",
        {"storey": None, "rooms": None, "height": 2.6},
        {
            "ok": True,
            "step": 8,
            "description": " Rooms on every storey with rooms: every room the walls enclose, named Room 1, Room 2 …, 2.6 m high",
        },
    ),
    (
        "create_spaces",
        {"storey": None, "rooms": [{"at": None, "index": 1, "name": "A", "long_name": None}], "height": None},
        {"error": "name the storey the rooms are on; storey null goes with rooms null (every room on every storey)"},
    ),
]
THE_SPACES_TEST_WHEEL = [
    {
        "tool": "create_storeys_and_grid",
        "storeys": [{"name": "Plan 3", "elevation": 6}],
        "grid": {"x_spacing": 6, "x_count": 2, "y_spacing": 8, "y_count": 1},
    },
    {
        "tool": "create_wall",
        "storey": "Plan 3",
        "start": [0, 0],
        "end": [12, 0],
        "thickness": 0.2,
        "height": 3,
        "name": "Syd",
    },
    {
        "tool": "create_wall",
        "storey": "Plan 3",
        "start": [12, 0],
        "end": [12, 8],
        "thickness": 0.2,
        "height": 3,
        "name": "Öst",
    },
    {
        "tool": "create_wall",
        "storey": "Plan 3",
        "start": [12, 8],
        "end": [0, 8],
        "thickness": 0.2,
        "height": 3,
        "name": "Norr",
    },
    {
        "tool": "create_wall",
        "storey": "Plan 3",
        "start": [0, 8],
        "end": [0, 0],
        "thickness": 0.2,
        "height": 3,
        "name": "Väst",
    },
    {
        "tool": "create_wall",
        "storey": "Plan 3",
        "start": [6, 0],
        "end": [6, 8],
        "thickness": 0.2,
        "height": 3,
        "name": "Mitt",
    },
    {
        "tool": "create_opening",
        "wall_id": "new-5",
        "offset": 3,
        "width": 0.9,
        "height": 2.1,
        "sill": 0,
        "fill": "door",
        "name": "Dörr",
    },
    {"tool": "create_spaces", "storey": None, "rooms": None, "height": 2.6, "default_name": "Room {n}"},
]
THE_SITE_TEST = [
    (
        "set_site",
        {
            "latitude": 59.3293,
            "longitude": 18.0686,
            "elevation": 12.5,
            "crs": "epsg:3006",
            "eastings": 674032,
            "northings": 6580822,
            "rotation": 15,
            "site_name": "Kvarteret",
        },
        {
            "ok": True,
            "step": 1,
            "description": "Site Kvarteret: 59.3293, 18.0686, height 12.5 m, EPSG:3006 E 674032 N 6580822, rotated 15°",
        },
    ),
    (
        "set_site",
        {
            "latitude": -33.9,
            "longitude": -70.6,
            "elevation": None,
            "crs": None,
            "eastings": None,
            "northings": None,
            "rotation": None,
            "site_name": None,
        },
        {"ok": True, "step": 2, "description": "Site: -33.9, -70.6"},
    ),
    (
        "set_site",
        {
            "latitude": 91,
            "longitude": 18,
            "elevation": None,
            "crs": None,
            "eastings": None,
            "northings": None,
            "rotation": None,
            "site_name": None,
        },
        {"error": "latitude must be between -90 and 90 degrees"},
    ),
    (
        "set_site",
        {
            "latitude": 59,
            "longitude": 18,
            "elevation": None,
            "crs": "EPSG:3006",
            "eastings": None,
            "northings": 1,
            "rotation": None,
            "site_name": None,
        },
        {"error": "eastings and northings (metres) are required with crs"},
    ),
    (
        "set_classification",
        {
            "ids": ["2O2Fr$t4X7Zf8NOew3FLOH", "7"],
            "system": "Uniclass 2015",
            "name": "Walls",
            "code": "EF_25_10",
            "uri": None,
        },
        {"ok": True, "step": 3, "description": "Classify 2O2Fr$t4X7Zf8NOew3FLOH, 7 in Uniclass 2015: EF_25_10 Walls"},
    ),
    (
        "assign",
        {"ids": ["2O2Fr$t4X7Zf8NOew3FLOH"], "storey": "Plan 2", "material": "Concrete"},
        {"ok": True, "step": 4, "description": "Assign 2O2Fr$t4X7Zf8NOew3FLOH to storey Plan 2 the material Concrete"},
    ),
    (
        "transform_elements",
        {"ids": ["2O2Fr$t4X7Zf8NOew3FLOH"], "dx": 0.25, "dy": None, "dz": -0.1},
        {"ok": True, "step": 5, "description": "Move 2O2Fr$t4X7Zf8NOew3FLOH by (0.25, 0, -0.1) m"},
    ),
    (
        "manage_changeset",
        {"action": "list"},
        {
            "steps": [
                {
                    "step": 1,
                    "tool": "set_site",
                    "ref": None,
                    "description": "Site Kvarteret: 59.3293, 18.0686, height 12.5 m, EPSG:3006 E 674032 N 6580822, rotated 15°",
                },
                {"step": 2, "tool": "set_site", "ref": None, "description": "Site: -33.9, -70.6"},
                {
                    "step": 3,
                    "tool": "set_classification",
                    "ref": None,
                    "description": "Classify 2O2Fr$t4X7Zf8NOew3FLOH, 7 in Uniclass 2015: EF_25_10 Walls",
                },
                {
                    "step": 4,
                    "tool": "assign",
                    "ref": None,
                    "description": "Assign 2O2Fr$t4X7Zf8NOew3FLOH to storey Plan 2 the material Concrete",
                },
                {
                    "step": 5,
                    "tool": "transform_elements",
                    "ref": None,
                    "description": "Move 2O2Fr$t4X7Zf8NOew3FLOH by (0.25, 0, -0.1) m",
                },
            ]
        },
    ),
    ("manage_changeset", {"action": "clear"}, {"ok": True, "steps": 0}),
]
THE_SITE_TEST_WHEEL = []
THE_FIELDS_OF_64E116E = [
    (
        "create_wall",
        {
            "storey": "Plan 1",
            "start": [0, 0],
            "end": [4, 0],
            "thickness": 0.1,
            "height": 2.7,
            "name": "Mellanvägg",
            "partition": True,
        },
        {
            "ok": True,
            "step": 1,
            "description": "new-1 Wall Mellanvägg on Plan 1 from (0, 0) to (4, 0), 0.1 m thick, 2.7 m high, a non-load-bearing interior wall",
            "ref": "new-1",
        },
    ),
    (
        "create_wall",
        {
            "storey": "Plan 1",
            "start": [0, 0],
            "end": [0, 4],
            "thickness": None,
            "height": None,
            "name": None,
            "partition": False,
        },
        {
            "ok": True,
            "step": 2,
            "description": "new-2 Wall  on Plan 1 from (0, 0) to (0, 4), 0.2 m thick, 3 m high",
            "ref": "new-2",
        },
    ),
    (
        "create_slab",
        {
            "storey": "Plan 1",
            "outline": [[0, 0], [4, 0], [4, 4], [0, 4], [0, 0], [0, 0]],
            "thickness": None,
            "name": None,
        },
        {"ok": True, "step": 3, "description": "new-3 Slab  on Plan 1, 0.25 m thick, 4 corners", "ref": "new-3"},
    ),
    (
        "create_roof",
        {
            "storey": None,
            "shape": "gable",
            "outline": [[0, 0], [12, 0], [12, 8], [0, 8], [0, 0]],
            "pitch": None,
            "overhang": None,
            "thickness": None,
            "ridge": None,
            "base": None,
            "name": None,
        },
        {
            "ok": True,
            "step": 4,
            "description": "new-4 Roof on the top storey: gable roof 30° over 12 × 8 m, overhang 0.4 m",
            "ref": "new-4",
        },
    ),
    (
        "create_slab",
        {"storey": None, "outline": [[1, 1], [2, 2], [1, 1]], "thickness": None, "name": None},
        {"error": "outline must be at least three [x, y] points, or null for the grid's extent"},
    ),
    (
        "set_classification",
        {
            "ids": ["new-1"],
            "system": "CCI Construction",
            "name": "Innervägg",
            "code": "AAB",
            "uri": "https://identifier.buildingsmart.org/uri/molio/cciconstruction/1.0/class/AAB",
            "edition": "1.0",
            "source": "Molio",
            "dictionary_uri": "https://identifier.buildingsmart.org/uri/molio/cciconstruction/1.0",
        },
        {"ok": True, "step": 5, "description": "Classify new-1 in CCI Construction 1.0: AAB Innervägg"},
    ),
    (
        "set_classification",
        {
            "ids": ["new-2"],
            "system": "Uniclass 2015",
            "name": "Walls",
            "code": None,
            "uri": None,
            "edition": None,
            "source": "",
            "dictionary_uri": None,
        },
        {"ok": True, "step": 6, "description": "Classify new-2 in Uniclass 2015: Walls"},
    ),
]
THE_FIELDS_OF_64E116E_WHEEL = [
    {
        "tool": "create_wall",
        "storey": "Plan 1",
        "start": [0, 0],
        "end": [4, 0],
        "thickness": 0.1,
        "height": 2.7,
        "name": "Mellanvägg",
        "partition": True,
    },
    {
        "tool": "create_wall",
        "storey": "Plan 1",
        "start": [0, 0],
        "end": [0, 4],
        "thickness": 0.2,
        "height": 3,
        "name": None,
    },
    {
        "tool": "create_slab",
        "storey": "Plan 1",
        "outline": [[0, 0], [4, 0], [4, 4], [0, 4]],
        "thickness": 0.25,
        "name": None,
    },
    {
        "tool": "create_roof",
        "storey": None,
        "shape": "gable",
        "outline": [[0, 0], [12, 0], [12, 8], [0, 8]],
        "pitch": 30,
        "overhang": 0.4,
        "thickness": 0.25,
        "ridge": None,
        "base": None,
        "name": None,
    },
    {
        "tool": "set_classification",
        "ids": ["new-1"],
        "system": "CCI Construction",
        "code": "AAB",
        "name": "Innervägg",
        "uri": "https://identifier.buildingsmart.org/uri/molio/cciconstruction/1.0/class/AAB",
        "edition": "1.0",
        "source": "Molio",
        "dictionary_uri": "https://identifier.buildingsmart.org/uri/molio/cciconstruction/1.0",
    },
    {
        "tool": "set_classification",
        "ids": ["new-2"],
        "system": "Uniclass 2015",
        "code": None,
        "name": "Walls",
        "uri": None,
    },
]


@pytest.mark.parametrize(
    ("calls", "wheel"),
    [
        (THE_CHANGE_TEST, THE_CHANGE_TEST_WHEEL),
        (THE_ROOF_TEST, THE_ROOF_TEST_WHEEL),
        (THE_SPACES_TEST, THE_SPACES_TEST_WHEEL),
        (THE_SITE_TEST, THE_SITE_TEST_WHEEL),
        (THE_FIELDS_OF_64E116E, THE_FIELDS_OF_64E116E_WHEEL),
    ],
    ids=["change", "roof", "spaces", "site", "64e116e"],
)
def test_the_port_answers_the_apps_examples_as_the_app_does(calls: list[Any], wheel: list[Any]) -> None:
    cs: dict[str, Any] = {"ops": [], "refs": 0}
    for name, arguments, answer in calls:
        assert write_tools.call(cs, name, arguments) == answer, name
    assert write_tools.to_wheel(cs["ops"]) == wheel, "the operations the server tries"


@pytest.mark.parametrize("sequence", ["built", "refused"])
def test_the_port_answers_the_calls_of_437982f_as_the_app_does(sequence: str) -> None:
    cs: dict[str, Any] = {"ops": [], "refs": 0}
    for name, arguments, answer in AT_437982F[sequence]["calls"]:
        if "error" in answer:
            for app, server in SERVER_WORDS:
                answer["error"] = answer["error"].replace(app, server)
        assert write_tools.call(cs, name, arguments) == answer, name
    assert write_tools.to_wheel(cs["ops"]) == AT_437982F[sequence]["wheel"], "the operations the server tries"


def test_the_sequence_of_437982f_gives_every_new_tool_and_field() -> None:
    """Every tool that 437982f added and every field it added to a tool is given, not null, in a call the app took."""
    given: dict[str, set[str]] = {}
    for name, arguments, answer in AT_437982F["built"]["calls"]:
        if not answer.get("ok"):
            continue
        fields = {key for key, value in arguments.items() if value not in (None, "", [])}
        for key in ("storeys", "rooms"):
            fields |= {f"{key}.{sub}" for item in arguments.get(key) or [] for sub, v in item.items() if v}
        for key in ("shape", "stair"):  # the objects of create_element; a roof's shape is a word
            nested = arguments.get(key) if isinstance(arguments.get(key), dict) else {}
            fields |= {f"{key}.{sub}" for sub, v in nested.items() if v is not None}
        given.setdefault(name, set()).update(fields)
    added = {
        "define_type": {"kind", "name", "layers", "predefined_type", "material", "material_category", "operation",
                        "partitioning", "width", "height", "lining_depth"},
        "create_element": {"storey", "ifc_class", "predefined_type", "object_type", "type", "name", "at", "z",
                           "rotation", "shape", "stair", "part_of", "host", "shape.profile", "shape.x", "shape.y",
                           "shape.radius", "shape.outline", "shape.depth", "shape.along", "stair.risers",
                           "stair.riser_height", "stair.tread_length", "stair.width", "stair.landing"},
        "edit_element": {"id", "name", "end", "thickness", "height", "type", "offset", "width", "sill", "pitch",
                         "overhang", "base"},
        "create_wall": {"type", "partition", "load_bearing", "status"},
        "create_slab": {"type", "load_bearing", "status"},
        "create_roof": {"type", "status"},
        "create_opening": {"type", "side"},
        "assign": {"category"},
        "set_site": {"vertical_datum"},
        "create_storeys_and_grid": {"storeys.description", "storeys.long_name"},
        "create_spaces": {"rooms.number", "rooms.room_type"},
    }  # fmt: skip
    for name, fields in added.items():
        assert fields <= given[name], (name, fields - given[name])


def test_the_server_names_no_tool_it_does_not_offer() -> None:
    """The app's create_element points at search_ifc_class and its edit_element at get_parameters, read tools of the
    app that the server's MCP endpoint does not have: the server's words leave them out and keep the rest."""
    offered = {tool["name"] for tool in write_tools.TOOLS}
    for tool in write_tools.TOOLS:
        for name in ("search_ifc_class", "search_bsdd", "get_parameters", "get_topology"):
            assert name not in tool["description"] or name in offered, (tool["name"], name)
    element = write_tools.tool("create_element")["description"]
    assert "predefined_type is a value of the class's list, such as COLUMN;" in element
    assert write_tools.tool("edit_element")["description"].endswith(
        "type (define_type) to change it. Change elements with this instead of deleting and recreating them."
    )
    column = {"ifc_class": "IfcColumn", "predefined_type": "USERDEFINED", "at": [0, 0]}
    assert write_tools.call({"ops": [], "refs": 0}, "create_element", column) == {
        "error": "USERDEFINED needs object_type, the name of its kind; or choose a value of the class's list"
    }


def test_a_unit_in_a_value_is_read_as_the_app_reads_it() -> None:
    """``unitIn``: a number with a unit of the list after it, in JavaScript's white space; a line break inside the
    unit is no unit, as JavaScript's ``.`` takes none, and the digits are ASCII digits."""
    assert write_tools.unit_in("40 dB") == ["40", "dB"]
    assert write_tools.unit_in(" -1,5e3　kN﻿") == ["-1,5e3", "kN"]
    assert write_tools.unit_in("0.18 W/(m² K)") == ["0.18", "W/(m² K)"], "spaces inside the unit are left out"
    assert write_tools.unit_in("40 parsecs") is None and write_tools.unit_in("dB 40") is None
    assert write_tools.unit_in("40\ndB") == ["40", "dB"] and write_tools.unit_in("40 d\nB") is None
    assert write_tools.unit_in(40) is None and write_tools.unit_in("٤٠ dB") is None


def test_texts_are_trimmed_of_javascripts_white_space() -> None:
    cs: dict[str, Any] = {"ops": [], "refs": 0}
    layer = {"material": "﻿Betong ", "thickness": 0.2, "category": " Concrete", "role": None}
    out = write_tools.call(cs, "define_type", {"kind": " wall\n", "name": "　YV1\x85", "layers": [layer]})
    assert out["description"] == "new-1 Wall type YV1\x85: Betong 0.2 m (0.2 m)", "U+0085 is no white space in JS"
    assert cs["ops"][0]["layers"][0] == {"material": "Betong", "thickness": 0.2, "category": "concrete", "role": None}


def test_the_tools_and_their_parameters_are_the_apps_in_its_order() -> None:
    assert [tool["name"] for tool in write_tools.TOOLS] == [
        "create_storeys_and_grid",
        "define_type",
        "create_wall",
        "create_slab",
        "create_roof",
        "create_opening",
        "create_element",
        "create_spaces",
        "set_properties",
        "set_classification",
        "assign",
        "edit_element",
        "transform_elements",
        "delete_elements",
        "set_site",
        "manage_changeset",
    ]
    assert write_tools.CREATES[-2:] == ("define_type", "create_element"), "the new tools that hand out a ref"
    assert list(write_tools.tool("create_wall")["properties"]) == [
        "storey", "start", "end", "thickness", "height", "name", "type", "partition", "load_bearing", "status"
    ]  # fmt: skip
    assert list(write_tools.tool("define_type")["properties"]) == [
        "kind", "name", "layers", "predefined_type", "material", "material_category", "operation", "partitioning",
        "width", "height", "lining_depth"
    ]  # fmt: skip
    assert list(write_tools.tool("create_element")["properties"]) == [
        "storey", "ifc_class", "predefined_type", "object_type", "type", "name", "at", "z", "rotation", "shape",
        "stair", "part_of", "host"
    ]  # fmt: skip
    assert list(write_tools.tool("edit_element")["properties"]) == [
        "id", "name", "start", "end", "thickness", "height", "type", "outline", "offset", "width", "sill", "pitch",
        "overhang", "base"
    ]  # fmt: skip
    assert list(write_tools.tool("assign")["properties"]) == ["ids", "storey", "material", "category"]
    assert list(write_tools.tool("set_site")["properties"])[-1] == "vertical_datum"
    assert list(write_tools.tool("set_classification")["properties"]) == [
        "ids", "system", "name", "code", "uri", "edition", "source", "dictionary_uri"
    ]  # fmt: skip
    assert write_tools.tool("create_wall")["properties"]["partition"] == {"type": ["boolean", "null"]}


def test_texts_are_cut_in_utf_16_units_and_objects_keep_javascripts_key_order() -> None:
    cs: dict[str, Any] = {"ops": [], "refs": 0}
    wall = {"storey": "ÅÄÖ" * 80, "start": [0, 0], "end": [0.0000015, 2.5], "thickness": 0.30000000000000004,
            "height": 2.0, "name": "\U0001f600" * 150}  # fmt: skip
    out = write_tools.call(cs, "create_wall", wall)
    assert out["description"] == (
        f"new-1 Wall {chr(0x1F600) * 100} on {'ÅÄÖ' * 66}ÅÄ from (0, 0) to (0, 2.5), 0.3 m thick, 2 m high"
    )
    assert cs["ops"][0]["name"] == "\U0001f600" * 100 and len(cs["ops"][0]["storey"]) == 200
    properties = [{"name": "2", "value": 1}, {"name": "b", "value": "x" * 1200}, {"name": "1", "value": 2.5}]
    out = write_tools.call(
        cs, "set_properties", {"ids": ["new-1", "007"], "pset": "Pset_Test", "properties": properties}
    )
    assert out["description"] == "Pset_Test on new-1, 7: 1 = 2.5, 2 = 1, b = " + "x" * 1000
    assert list(cs["ops"][1]["properties"]) == ["1", "2", "b"] and cs["ops"][1]["ids"] == ["new-1", 7]
    assert write_tools.call(cs, "create_storeys_and_grid", {"storeys": None, "grid": {}}) == {
        "error": "x_spacing is required (metres)"
    }, "an empty object is an object, as in JavaScript"
    grid = {"x_spacing": 6, "x_count": 2.0, "y_spacing": 4, "y_count": 101}
    assert write_tools.call(cs, "create_storeys_and_grid", {"storeys": [], "grid": grid}) == {
        "error": "x_count and y_count must be whole numbers, at most 100"
    }
    opening = {"wall_id": "1Xezbq735AdBO_4DerG66G", "offset": None, "width": None, "height": None, "sill": None,
               "fill": "WINDOW", "name": None}  # fmt: skip
    assert write_tools.call(cs, "create_opening", opening)["description"] == (
        "new-2 Window  in wall 1Xezbq735AdBO_4DerG66G, 0.9×2.1 m, 0 m from the wall's start"
    ), "a wall named by its GlobalId (F34 a)"


@pytest.mark.parametrize(
    ("number", "written"),
    [
        (0, "0"),
        (-0.0, "0"),
        (3, "3"),
        (2.0, "2"),
        (100, "100"),
        (0.2, "0.2"),
        (0.1 + 0.2, "0.30000000000000004"),
        (1e21, "1e+21"),
        (1e20, "100000000000000000000"),
        (1e-7, "1e-7"),
        (0.000001, "0.000001"),
        (0.0000015, "0.0000015"),
        (123456.789, "123456.789"),
        (-2.5, "-2.5"),
        (1e300, "1e+300"),
        (9007199254740993, "9007199254740992"),
        (123e-20, "1.23e-18"),
    ],
)
def test_a_number_is_written_as_javascripts_string_writes_it(number: float, written: str) -> None:
    assert write_tools._js_number(number) == written  # what Node's String() gave


def test_rounding_is_javascripts_half_toward_positive_infinity() -> None:
    assert [write_tools._round(x) for x in (2.5, -2.5, 0.49999999999999994, -0.5, 1.5, 0.5)] == [3, -2, 0, 0, 2, 1]


def test_the_wheel_gets_the_operations_and_the_changes_go_apart() -> None:
    change = {"guid": "1Xezbq735AdBO_4DerG66G", "attribute": "Name", "op": "set", "old": "Wall 1", "new": "Wall 1b"}
    cs: dict[str, Any] = {"ops": [], "refs": 0}
    wall = {"storey": None, "start": [0, 0], "end": [4, 0], "thickness": None, "height": None, "name": None}
    write_tools.call(cs, "create_wall", wall)
    cs["ops"].append({"tool": write_tools.CHANGE_ATTRIBUTE, "change": change})
    assert write_tools.to_wheel(cs["ops"]) == [{"tool": "create_wall", **wall, "thickness": 0.2, "height": 3}]
    assert write_tools.changes(cs["ops"]) == [change]
    listed = write_tools.call(cs, "manage_changeset", {"action": "list"})["steps"]
    assert listed[1] == {
        "step": 2,
        "tool": "change_attribute",
        "ref": None,
        "description": "Set Name of 1Xezbq735AdBO_4DerG66G",
    }
    removed = write_tools.call(cs, "manage_changeset", {"action": "remove_last"})
    assert removed == {"ok": True, "removed": "Set Name of 1Xezbq735AdBO_4DerG66G", "steps": 1} and cs["refs"] == 1


def test_a_change_set_holds_200_steps_and_a_step_500_ids() -> None:
    cs: dict[str, Any] = {"ops": [{"tool": "delete_elements", "ids": [1], "confirm": True}] * 200, "refs": 0}
    full = write_tools.call(cs, "delete_elements", {"ids": [2], "confirm": True})
    assert full == {"error": "the change set holds 200 steps already; ask the person to approve it first"}
    many = write_tools.call(
        {"ops": [], "refs": 0}, "assign", {"ids": list(range(1, 502)), "storey": "Plan 1", "material": None}
    )
    assert many == {"error": "at most 500 ids in one step"}
    assert write_tools.call({"ops": [], "refs": 0}, "publish_version", {}) == {"error": "unknown tool publish_version"}
    assert not write_tools.has("publish_version") and not write_tools.has("approve")
