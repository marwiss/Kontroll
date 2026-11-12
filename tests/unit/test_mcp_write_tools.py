# This file was generated with the assistance of an AI coding tool.
"""The copy of Dataspatium's write tools (``opencde/mcp/write_tools.py``) against what the app's own code answers.

The calls below are the examples of the app's tests (``tests/ai-change``, ``ai-roof``, ``ai-spaces`` and ``ai-site``
at Dataspatium's f43), with the fields commit 64e116e added (a partition wall, a classification's system, an outline
that repeats its first corner), and the answers and operations are what ``src/ai/write-tools.js`` at 64e116e gave for
them, run with Node from a copy of the file: the port must answer the same, refs and errors included, and hand the
wheel the same operations. JavaScript's own ways with numbers, texts and objects are tried one by one below.
"""

from __future__ import annotations

from typing import Any

import pytest

from opencde.mcp import write_tools

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


def test_the_tools_and_their_parameters_are_the_apps_in_its_order() -> None:
    assert [tool["name"] for tool in write_tools.TOOLS] == [
        "create_storeys_and_grid",
        "create_wall",
        "create_slab",
        "create_roof",
        "create_opening",
        "create_spaces",
        "set_properties",
        "set_classification",
        "assign",
        "transform_elements",
        "delete_elements",
        "set_site",
        "manage_changeset",
    ]
    assert list(write_tools.tool("create_wall")["properties"]) == [
        "storey", "start", "end", "thickness", "height", "name", "partition"
    ]  # fmt: skip
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
