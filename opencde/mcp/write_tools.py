# This file was generated with the assistance of an AI coding tool.
"""Dataspatium's write tools as the MCP endpoint offers them (ADR 0028, the design's §2): a copy, kept in step by hand.

A copy of ``src/ai/write-tools.js`` (Dataspatium, branch f43, commit 334ec55 of 2026-11-12, whose errors
name a place instead of quoting the call, as this copy's did first): the tools' schemas and
descriptions (``TOOLS``), ``build()`` with its checks, which turns one call into one operation in the form
``dataspatium-tools/1`` (the defaults filled in, the numbers checked, the texts cut at 200 characters, an optional
field on the operation only when given), ``call()``, which appends the operation to the open change set with the
refs counted as the app counts them (``new-1``, ``new-2`` … in the order of ``create_wall``, ``create_slab``,
``create_roof``, ``create_opening``, ``define_type``, ``create_element`` and the rooms that ``create_spaces`` lists),
advises the guidance's naming for a set of the model's own and runs ``manage_changeset``, ``describe()`` with the
English lines of the app's catalogue (``src/ui/i18n/en.js``, the keys ``ai.change.*``), ``unitIn`` (:func:`unit_in`)
and ``toWheel``, which leaves the refs out, since the code that applies the operations (``ifcgraph/ops.py``) counts
them itself. An id is an element's or a type's GlobalId, its STEP id or a ref (F34 a). The server keeps the change set
as a draft (``store/jobs/drafts.py``), whose ``ops`` are this module's. The app's ``withGuids``, which names the
elements of a proposal by GlobalId, and ``summary``, which counts its steps for the app's panel, are not copied.

Against the original only this differs, so that the next copy is a diff away:

- JavaScript's semantics are spelled out where Python's differ: ``String()`` of a number (:func:`_js_number`),
  ``Math.round`` (:func:`_round`), ``slice`` in UTF-16 code units (:func:`_slice`, where a pair cut in half is
  dropped), ``trim()`` and ``\\s`` with JavaScript's white space (:func:`_trim`), and the regular expressions in ASCII
  and anchored at the very end, their ``.`` without a line terminator;
- the person's language is the catalogue's English: the name ``create_spaces`` gives the rooms it names itself is
  ``Room {n}``, and the descriptions are the English lines;
- the server's own step ``change_attribute`` (a post in the change set's ``changes``) lives in ``cs["ops"]`` beside
  the operations, so that ``manage_changeset`` lists and removes it in its order; :func:`describe` describes it, and
  :func:`to_wheel` and :func:`changes` part the two;
- four descriptions and three messages name tools the server does not have: ``set_classification`` says nothing of
  ``search_ifc_class`` and ``search_bsdd`` (a bSDD class's dictionary is still the system), ``create_spaces`` names
  a room's index as a report's rooms give it instead of ``get_topology``, ``create_element`` says nothing of
  ``search_ifc_class`` in its description and in two errors on ``predefined_type``, and ``edit_element`` leaves out
  that ``get_parameters`` reads an element's measures;
- a room of ``create_spaces`` that is a list is no object here, where JavaScript finds the lists' own ``at``; the
  schema lets no such room through;
- ``call()`` answers an error as the app does, ``{"error": …}``, which the endpoint makes a tool error;
"""

from __future__ import annotations

import math
import re
from decimal import Decimal
from typing import Any

MAX_OPS = 200
MAX_IDS = 500
CREATES = (
    "create_wall",
    "create_slab",
    "create_roof",
    "create_opening",
    "create_spaces",
    "define_type",
    "create_element",
)
ROOF_SHAPES = ("gable", "hip", "shed", "flat")
MAX_ROOMS = 200
#: The kinds of define_type: with material layers, and without (a material at most; doors and windows with their
#: geometry).
LAYERED_KINDS = ("wall", "slab", "roof", "covering")
ELEMENT_KINDS = ("column", "beam", "footing", "railing", "door", "window")
TYPE_KINDS = LAYERED_KINDS + ELEMENT_KINDS
#: The type class of each kind (IFC4 and later); slab and roof types are both IfcSlabType, so their names must differ.
TYPE_CLASS = {
    "wall": "IfcWallType",
    "slab": "IfcSlabType",
    "roof": "IfcSlabType",
    "covering": "IfcCoveringType",
    "column": "IfcColumnType",
    "beam": "IfcBeamType",
    "footing": "IfcFootingType",
    "railing": "IfcRailingType",
    "door": "IfcDoorType",
    "window": "IfcWindowType",
}
#: The door OperationTypes and window PartitioningTypes whose geometry IfcOpenShell draws; the first is the default.
DOOR_OPERATIONS = (
    "SINGLE_SWING_LEFT",
    "SINGLE_SWING_RIGHT",
    "DOUBLE_SWING_LEFT",
    "DOUBLE_SWING_RIGHT",
    "DOUBLE_DOOR_SINGLE_SWING",
    "DOUBLE_DOOR_DOUBLE_SWING",
    "SLIDING_TO_LEFT",
    "SLIDING_TO_RIGHT",
    "DOUBLE_DOOR_SLIDING",
)
WINDOW_PARTITIONS = (
    "SINGLE_PANEL",
    "DOUBLE_PANEL_VERTICAL",
    "DOUBLE_PANEL_HORIZONTAL",
    "TRIPLE_PANEL_VERTICAL",
    "TRIPLE_PANEL_HORIZONTAL",
    "TRIPLE_PANEL_BOTTOM",
    "TRIPLE_PANEL_TOP",
    "TRIPLE_PANEL_LEFT",
    "TRIPLE_PANEL_RIGHT",
)
#: The classes create_element makes (IfcFurniture is IfcFurnishingElement in IFC2X3), and the define_type kind of
#: those that have one.
ELEMENT_CLASSES = (
    "IfcColumn",
    "IfcBeam",
    "IfcMember",
    "IfcFooting",
    "IfcPile",
    "IfcCovering",
    "IfcRailing",
    "IfcChimney",
    "IfcShadingDevice",
    "IfcSanitaryTerminal",
    "IfcFurniture",
    "IfcFurnishingElement",
    "IfcStair",
)
CLASS_KIND = {
    "IfcColumn": "column",
    "IfcBeam": "beam",
    "IfcFooting": "footing",
    "IfcCovering": "covering",
    "IfcRailing": "railing",
}
MAX_RISERS = 60
MAX_OUTLINE = 500
MAX_LAYERS = 20
#: IfcMaterial.Category as IfcOpenShell recommends it, and the roles of IfcMaterialLayer.Category (the wheel spells
#: them per schema).
MATERIAL_CATEGORIES = (
    "concrete",
    "steel",
    "aluminium",
    "block",
    "brick",
    "stone",
    "wood",
    "glass",
    "gypsum",
    "plastic",
    "earth",
)
LAYER_ROLES = ("load_bearing", "insulation", "inner_finish", "outer_finish")
#: Pset_*Common.Status: the schema's values for an element's life (the wheel checks them against the template).
STATUSES = ("NEW", "EXISTING", "DEMOLISH", "TEMPORARY")
#: Units a value might carry after its number ("40 dB"), in lower case without spaces, as the wheel's ``_CS_UNITS``.
UNITS = frozenset(
    (
        "mm", "cm", "dm", "m", "km", "mm2", "cm2", "dm2", "m2", "km2", "mm²", "cm²", "dm²", "m²", "km²", "mm3", "cm3",
        "dm3", "m3", "mm³", "cm³", "dm³", "m³", "l", "liter", "litre", "g", "kg", "t", "ton", "n", "kn", "pa", "kpa",
        "mpa", "gpa", "db", "dba", "db(a)", "w", "kw", "mw", "wh", "kwh", "mwh", "w/m2k", "w/m²k", "w/(m2k)",
        "w/(m²k)", "w/m2,k", "w/m²,k", "w/(m2·k)", "w/(m²·k)", "w/m²·k", "w/mk", "w/(mk)", "w/m·k", "w/(m·k)",
        "m2k/w", "m²k/w", "°c", "°", "deg", "k", "%", "h", "min", "s", "l/s", "m3/h", "m³/h", "m3/s", "m³/s",
        "kg/m3", "kg/m³", "kg/m2", "kg/m²", "kg/m", "lux", "lx", "st", "pcs", "kr", "sek", "nok", "dkk", "isk", "eur",
        "kgco2e", "kgco2-ekv",
    )
)  # fmt: skip
#: The compound EPSG codes of SWEREF 99 with RH 2000 heights: 5845 (TM) to 5857 (the local zones in the order of 3007
#: to 3018).
RH2000_CODES = (5845, 5857)
#: The fields edit_element takes per kind of element besides name (the wheel's ``_ChangeSet.EDITS``), and the kind a
#: create step makes.
EDITS = {
    "wall": ("start", "end", "thickness", "height", "type"),
    "slab": ("outline", "thickness", "type"),
    "opening": ("offset", "width", "height", "sill"),
    "roof": ("pitch", "overhang", "base"),
}
EDIT_OF = {"create_wall": "wall", "create_slab": "slab", "create_opening": "opening", "create_roof": "roof"}
EDIT_KINDS = (
    "a wall takes start, end, thickness, height and type; a slab outline, thickness and type; an opening, door or "
    "window offset, width, height and sill; a roof pitch, overhang and base; any element name"
)
CHANGE_ATTRIBUTE = "change_attribute"  # the server's own step: a post in `changes`


def _str() -> dict[str, Any]:
    return {"type": ["string", "null"]}


def _num() -> dict[str, Any]:
    return {"type": ["number", "null"]}


def _xy() -> dict[str, Any]:
    return {"type": ["array", "null"], "items": {"type": "number"}}


def _ids() -> dict[str, Any]:
    return {"type": "array", "items": {"type": ["integer", "string"]}}


def _bool() -> dict[str, Any]:
    return {"type": ["boolean", "null"]}


def _outline() -> dict[str, Any]:
    return {"type": ["array", "null"], "items": {"type": "array", "items": {"type": "number"}}}


def _type_ref() -> dict[str, Any]:
    return {"type": ["integer", "string", "null"]}


#: The tools as the providers see them: name, description and the properties of the parameters, in the app's order.
TOOLS: tuple[dict[str, Any], ...] = (
    {
        "name": "create_storeys_and_grid",
        "description": "Add building storeys (name and elevation in metres above the first) and/or a grid to the "
        "change set. Name the storeys with one numbering for the whole project that follows their height from the "
        "lowest up (such as Plan 1, Plan 2 …, a basement below them), and say the entrance level in the description, "
        'such as "Plan 2 (Entré)"; description and long_name (a longer name) are optional, null when not given. The '
        "grid has x_count bays of x_spacing metres along X (axes A, B, …) and y_count bays of y_spacing along Y (axes "
        "1, 2, …), with A1 at (0, 0). A storey that already exists is kept, and gets the description and long_name "
        "given. Either may be null.",
        "properties": {
            "storeys": {
                "type": ["array", "null"],
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "elevation": {"type": "number"},
                        "description": _str(),
                        "long_name": _str(),
                    },
                    "required": ["name", "elevation", "description", "long_name"],
                    "additionalProperties": False,
                },
            },
            "grid": {
                "type": ["object", "null"],
                "properties": {
                    "x_spacing": {"type": "number"},
                    "x_count": {"type": "integer"},
                    "y_spacing": {"type": "number"},
                    "y_count": {"type": "integer"},
                },
                "required": ["x_spacing", "x_count", "y_spacing", "y_count"],
                "additionalProperties": False,
            },
        },
    },
    {
        "name": "define_type",
        "description": "Define a type before the elements that use it. kind is wall (an IfcWallType), slab (an "
        "IfcSlabType), roof (an IfcSlabType ROOF for the roof slabs of create_roof) or covering (an IfcCoveringType), "
        "each with its material layers; or column, beam, footing, railing, door or window (an IfcColumnType, "
        "IfcBeamType, IfcFootingType, IfcRailingType, IfcDoorType or IfcWindowType; IfcDoorStyle and IfcWindowStyle "
        "in IFC2X3) with layers null and, when known, its material as material and material_category. name is the "
        "type's name, such as YV1. layers are its material layers, each {material, thickness in metres, category, "
        "role}: for a wall from its right side to its left as seen from its start toward its end (so the outside "
        "first when the outer walls run counter-clockwise), for a slab, a roof or a covering from the top down (a "
        "cladding from its outer face in). category (and material_category) is the material's IFC category (concrete, "
        "steel, aluminium, block, brick, stone, wood, glass, gypsum, plastic or earth) and role the layer's "
        "(load_bearing, insulation, inner_finish or outer_finish); give them only when known, else null. "
        "predefined_type is the type's PredefinedType from its class's list, such as SOLIDWALL or PARTITIONING for a "
        "wall, FLOOR or BASESLAB for a slab, FLOORING, CEILING or CLADDING for a covering, PAD_FOOTING or "
        "STRIP_FOOTING for a footing and HANDRAIL or GUARDRAIL for a railing (null: FLOOR for a slab, COLUMN, BEAM, "
        "DOOR and WINDOW, NOTDEFINED for the others; a roof type is ROOF). A door type has operation, its "
        "OperationType: SINGLE_SWING_LEFT (the default), SINGLE_SWING_RIGHT, DOUBLE_SWING_LEFT, DOUBLE_SWING_RIGHT, "
        "DOUBLE_DOOR_SINGLE_SWING, DOUBLE_DOOR_DOUBLE_SWING, SLIDING_TO_LEFT, SLIDING_TO_RIGHT or "
        "DOUBLE_DOOR_SLIDING, LEFT with the hinges on the left as seen in the direction it opens. A window type has "
        "partitioning, its PartitioningType: SINGLE_PANEL (the default), DOUBLE_PANEL_VERTICAL, "
        "DOUBLE_PANEL_HORIZONTAL, TRIPLE_PANEL_VERTICAL, TRIPLE_PANEL_HORIZONTAL, TRIPLE_PANEL_BOTTOM, "
        "TRIPLE_PANEL_TOP, TRIPLE_PANEL_LEFT or TRIPLE_PANEL_RIGHT. Both have width and height in metres (null: 0.9 × "
        "2.1 for a door, 1.2 × 1.2 for a window) and lining_depth, the depth of the lining across the wall (at least "
        "0.05 m, the default; the wall's thickness fills the reveal), and get their geometry from these. Answers the "
        "ref of the type, which create_wall, create_slab, create_roof, create_element and create_opening take as "
        "type; put shared properties on the type with set_properties and its ref.",
        "properties": {
            "kind": {"type": "string"},
            "name": {"type": "string"},
            "layers": {
                "type": ["array", "null"],
                "items": {
                    "type": "object",
                    "properties": {
                        "material": {"type": "string"},
                        "thickness": {"type": "number"},
                        "category": _str(),
                        "role": _str(),
                    },
                    "required": ["material", "thickness", "category", "role"],
                    "additionalProperties": False,
                },
            },
            "predefined_type": _str(),
            "material": _str(),
            "material_category": _str(),
            "operation": _str(),
            "partitioning": _str(),
            "width": _num(),
            "height": _num(),
            "lining_depth": _num(),
        },
    },
    {
        "name": "create_wall",
        "description": "Add a wall on a storey (null: the lowest) from start [x, y] to end [x, y] in metres in the "
        "storey's plane, with its thickness centred on that line and its height from the storey. Defaults: thickness "
        "0.2, height 3. partition true makes a non-load-bearing interior wall (PredefinedType PARTITIONING) when the "
        "wall has no type; otherwise the wall is SOLIDWALL or takes its PredefinedType from the type. With type (the "
        "ref of a define_type wall type, or a wall type's GlobalId or id) the wall takes its thickness from the "
        "type's layers, so leave thickness null. Walls whose lines meet at a corner, or that end on another wall's "
        "line, are joined by the app when the change set is applied: let them meet on their lines, and never lengthen "
        "or overlap them to close a corner. load_bearing is true for a wall that bears load and false for one that "
        "does not, as the brief or the person says; null when they do not say, never assumed. status is NEW, "
        "EXISTING, DEMOLISH or TEMPORARY as the brief says (EXISTING for a wall of an existing building), else null. "
        "The app sets IsExternal itself from the storey's topology. Answers the ref of the wall.",
        "properties": {
            "storey": _str(),
            "start": _xy(),
            "end": _xy(),
            "thickness": _num(),
            "height": _num(),
            "name": _str(),
            "type": _type_ref(),
            "partition": _bool(),
            "load_bearing": _bool(),
            "status": _str(),
        },
    },
    {
        "name": "create_slab",
        "description": "Add a floor slab on a storey, with its top at the storey's elevation. outline is a list of "
        "[x, y] corners in metres, or null to follow the grid's extent. Default thickness 0.25. With type (the ref of "
        "a define_type slab type, or a slab type's GlobalId or id) the slab takes its thickness from the type's "
        "layers, so leave thickness null. load_bearing is true for a slab that bears load and false for one that does "
        "not, as the brief or the person says; null when they do not say, never assumed. status is NEW, EXISTING, "
        "DEMOLISH or TEMPORARY as the brief says, else null. Answers the ref of the slab.",
        "properties": {
            "storey": _str(),
            "outline": _outline(),
            "thickness": _num(),
            "name": _str(),
            "type": _type_ref(),
            "load_bearing": _bool(),
            "status": _str(),
        },
    },
    {
        "name": "create_roof",
        "description": "Add a roof on the walls of a storey (null: the top storey), as an IfcRoof of roof slabs: "
        "shape is gable, hip, shed or flat. outline is the [x, y] corners in metres of the rectangle it covers, or "
        "null for the bounding box of the storey's walls; an outline that is not a rectangle along x and y is "
        "replaced by its bounding box for now. pitch is degrees, more than 0 and at most 75 (defaults: 30 for gable "
        "and hip, 10 for shed; flat ignores it). overhang is metres beyond the outline at the eaves (default 0.4, for "
        "flat 0), thickness metres (default 0.25). ridge is x or y: for gable the direction of the ridge (null: along "
        "the longer side), for shed the axis it falls along, down toward negative x or y (null: y, so to the south "
        "when y points north); hip and flat ignore it. base is the eaves height in metres above the storey (null: the "
        "top of the storey's walls, else 2.7). With type (the ref of a define_type roof type, or a roof type's "
        "GlobalId or id) every roof slab takes its thickness from the type's layers, so leave thickness null. status "
        "is NEW, EXISTING, DEMOLISH or TEMPORARY as the brief says, else null; the app marks the roof external "
        "itself. Answers the ref of the roof.",
        "properties": {
            "storey": _str(),
            "shape": {"type": "string"},
            "outline": _outline(),
            "pitch": _num(),
            "overhang": _num(),
            "thickness": _num(),
            "ridge": _str(),
            "base": _num(),
            "name": _str(),
            "type": _type_ref(),
            "status": _str(),
        },
    },
    {
        "name": "create_opening",
        "description": "Cut an opening in a wall (wall_id: its id or ref), offset metres from the wall's start, width "
        "by height metres, sill metres above the storey, and fill it with a door or a window (fill: door, window or "
        "null). Defaults: width 0.9, height 2.1, sill 0. With type (the ref of a define_type door or window type, or "
        "such a type's GlobalId or id, with fill door or window) the door or window takes its width, height and "
        "geometry from the type, so leave width and height null; it stands flush with the wall's left face as seen "
        "from the wall's start toward its end (the inside of an outer wall drawn counter-clockwise), and a door opens "
        "toward that side, a LEFT door with its hinges at the opening's side nearest the wall's start; side right "
        "turns it around, flush with the right face and opening toward it (side null: left). Answers the ref of the "
        "door or window, or of the opening.",
        "properties": {
            "wall_id": {"type": ["integer", "string"]},
            "offset": _num(),
            "width": _num(),
            "height": _num(),
            "sill": _num(),
            "fill": _str(),
            "name": _str(),
            "type": _type_ref(),
            "side": _str(),
        },
    },
    {
        "name": "create_element",
        "description": "Add a building element that has no tool of its own, of the most specific IFC class: "
        "IfcColumn, IfcBeam, IfcMember, IfcFooting, IfcPile, IfcCovering, IfcRailing, IfcChimney, IfcShadingDevice, "
        "IfcSanitaryTerminal, IfcFurniture (IfcFurnishingElement in IFC2X3) or IfcStair for a straight stair; never "
        "IfcBuildingElementProxy. predefined_type is a value of the class's list, such as COLUMN; BEAM or LINTEL; "
        "STUD or RAFTER; PAD_FOOTING or STRIP_FOOTING; BORED or DRIVEN; FLOORING, CEILING, CLADDING, ROOFING or "
        "INSULATION; HANDRAIL, GUARDRAIL or BALUSTRADE; JALOUSIE or AWNING; WASHHANDBASIN or TOILETPAN; TABLE or BED; "
        "null for NOTDEFINED or the type's, and USERDEFINED only with object_type. type is the ref of a define_type "
        "step of the class's kind (column, beam, footing, covering or railing) or a type's GlobalId or id. at is [x, "
        "y] metres in the storey's plane, z metres above the storey and rotation degrees counter-clockwise from x. "
        "shape is the body: profile rectangle (x by y metres), circle (radius) or polygon (outline, [x, y] corners in "
        "the storey's plane; at and rotation are then ignored), extruded depth metres. along z (the default) stands "
        "the profile in the plan centred on at and extrudes it up from z: a column, footing, pile, covering, chimney, "
        "sanitary terminal or furniture (give a footing or a pile a negative z to reach down). along x lays the "
        "profile across, centred on a line at height z, and extrudes it from at in the direction of rotation, x its "
        "width and y its height: a beam, member or railing. A covering with a type takes its depth from the type's "
        "layers, so leave depth null. part_of (a ref, GlobalId or id) makes the element a part of a whole, such as a "
        "railing of a stair: aggregated in it and on its storey, not in the storey itself, so leave storey null. host "
        "(only for IfcCovering) is the element or space it covers. For IfcStair shape is null and stair is the "
        "flight: risers (the number of risers, from 2), riser_height and tread_length in metres, width (default 1), "
        "thickness (the waist at right angles to the slope, at least riser_height; default 0.2) and landing (the "
        "length in metres of a landing at the top, or null); at is the foot of the first riser's middle and rotation "
        "the direction it rises, and the last riser is the front edge of the landing or of the floor above. Answers "
        "the ref of the element.",
        "properties": {
            "storey": _str(),
            "ifc_class": {"type": "string"},
            "predefined_type": _str(),
            "object_type": _str(),
            "type": _type_ref(),
            "name": _str(),
            "at": _xy(),
            "z": _num(),
            "rotation": _num(),
            "shape": {
                "type": ["object", "null"],
                "properties": {
                    "profile": {"type": "string"},
                    "x": _num(),
                    "y": _num(),
                    "radius": _num(),
                    "outline": _outline(),
                    "depth": _num(),
                    "along": _str(),
                },
                "required": ["profile", "x", "y", "radius", "outline", "depth", "along"],
                "additionalProperties": False,
            },
            "stair": {
                "type": ["object", "null"],
                "properties": {
                    "risers": {"type": ["integer", "null"]},
                    "riser_height": _num(),
                    "tread_length": _num(),
                    "width": _num(),
                    "thickness": _num(),
                    "landing": _num(),
                },
                "required": ["risers", "riser_height", "tread_length", "width", "thickness", "landing"],
                "additionalProperties": False,
            },
            "part_of": _type_ref(),
            "host": _type_ref(),
        },
    },
    {
        "name": "create_spaces",
        "description": "Create the rooms the walls enclose as spaces (IfcSpace), from the topology of the model as it "
        "stands at this step, so that walls created earlier in the change set count. Each space gets the room's "
        "outline extruded to its height, is aggregated in its storey, gets Qto_SpaceBaseQuantities, and gets space "
        "boundaries to the walls along its edge and to the doors and windows in them (a door created later in such a "
        "wall joins them). storey is the storey's name; null makes every room on every storey with rooms, and then "
        "rooms must be null. rooms lists the rooms: each by at, an [x, y] point inside it in metres in the storey's "
        "plane, or by index, its index among the storey's rooms in a report (the other null), with name from the room "
        "programme (such as Kitchen) and long_name or null; null makes every room, named Room 1, Room 2 … in the "
        "person's language. Give each listed room a number, unique in the building (such as the storey's number and "
        "two digits: 101, 102 … on Plan 1): the number becomes the space's Name, the name its LongName and long_name "
        "its description; with number null the name is the Name and long_name the LongName. room_type is the room's "
        "type when the brief gives one (such as Bedroom), written as ObjectType with PredefinedType USERDEFINED; null "
        "when not given. A room that a space covers already is left out. height is metres (null: up to the next "
        "storey, or the walls' height on the top storey). Answers one ref per listed room, in order; with rooms null "
        "the spaces get no refs.",
        "properties": {
            "storey": _str(),
            "rooms": {
                "type": ["array", "null"],
                "items": {
                    "type": "object",
                    "properties": {
                        "at": _xy(),
                        "index": {"type": ["integer", "null"]},
                        "name": {"type": "string"},
                        "long_name": _str(),
                        "number": _str(),
                        "room_type": _str(),
                    },
                    "required": ["at", "index", "name", "long_name", "number", "room_type"],
                    "additionalProperties": False,
                },
            },
            "height": _num(),
        },
    },
    {
        "name": "set_properties",
        "description": "Set properties in one property set (pset) on elements or types (ids: ids or refs): properties "
        "is a list of {name, value} with string, number or boolean values. Use IFC's own sets first (Pset_… for "
        "properties, Qto_… for quantities, such as Pset_WallCommon): the app checks them against the schema's "
        "templates when the change set is applied, so give the template's property names; a boolean is true or false, "
        'a measure a number without its unit (40, not "40 dB"; lengths in metres, areas m², volumes m³, angles '
        "degrees), an enumeration one of its values. A set of your own must never start with Pset_ or Qto_: name it "
        "country-origin-project_Name (such as SE-ACME-42_Acoustics), its properties in PascalCase without å, ä or ö, "
        "and its values without units. Never set IsExternal on walls, doors, windows or roofs, which the app sets "
        "from the topology, nor the base quantities, which it computes. Missing sets are created.",
        "properties": {
            "ids": _ids(),
            "pset": {"type": "string"},
            "properties": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}, "value": {"type": ["string", "number", "boolean"]}},
                    "required": ["name", "value"],
                    "additionalProperties": False,
                },
            },
        },
    },
    {
        "name": "set_classification",
        "description": "Classify elements (ids or refs) with a class of the classification system the person names; "
        "never assume a system. The IFC class with its PredefinedType is the classification itself; this adds a "
        "system on top. system is that system's name, name the class name, code its code and uri its address (for a "
        "bSDD class its uri). Written as an IfcClassificationReference under the system's IfcClassification, shared "
        "only when the system, the code and the uri match. edition, source and dictionary_uri describe the system "
        "(its edition, its publisher and the dictionary's address) and are written on its IfcClassification; the same "
        "system with another edition or dictionary_uri is another IfcClassification. For a class in a bSDD "
        "dictionary, take its dictionary as system with its edition, source and dictionary_uri. Never invent a code "
        "or an edition; null when not known.",
        "properties": {
            "ids": _ids(),
            "system": {"type": "string"},
            "name": {"type": "string"},
            "code": _str(),
            "uri": _str(),
            "edition": _str(),
            "source": _str(),
            "dictionary_uri": _str(),
        },
    },
    {
        "name": "assign",
        "description": "Move elements (ids or refs) to a storey (by name) and/or give them a material (by name, "
        "created when missing). Either may be null. category is the material's IFC category (concrete, steel, "
        "aluminium, block, brick, stone, wood, glass, gypsum, plastic or earth), given with the material when known, "
        "else null.",
        "properties": {"ids": _ids(), "storey": _str(), "material": _str(), "category": _str()},
    },
    {
        "name": "edit_element",
        "description": "Change an existing element in place, keeping its GlobalId: id is its id, GlobalId or ref, and "
        "every other field is null to keep it. A wall takes start and end ([x, y] metres in its storey's plane), "
        "thickness, height and type; its openings keep their place along it while its direction stays the same (else "
        "their offset from its start), and the app joins it anew with the walls it meets. A slab takes outline (its "
        "[x, y] corners in metres), thickness and type, its top staying where it is. An opening, or the door or "
        "window in it, takes offset (metres from the wall's start), width, height and sill; the opening and its door "
        "or window change together and must stay within the wall. A roof takes pitch, overhang and base (the eaves' "
        "height above the storey), and its roof slabs follow. Any element takes name. A typed wall or slab takes its "
        "thickness from its type, so give another wall or slab type (define_type) to change it. Change elements with "
        "this instead of deleting and recreating them.",
        "properties": {
            "id": {"type": ["integer", "string"]},
            "name": _str(),
            "start": _xy(),
            "end": _xy(),
            "thickness": _num(),
            "height": _num(),
            "type": _type_ref(),
            "outline": _outline(),
            "offset": _num(),
            "width": _num(),
            "sill": _num(),
            "pitch": _num(),
            "overhang": _num(),
            "base": _num(),
        },
    },
    {
        "name": "transform_elements",
        "description": "Move elements (ids or refs) by dx, dy, dz metres in their storey's plane. A door or window "
        "moves with its opening; to slide one along its wall, edit_element with offset is better. The site, the "
        "building and the storeys are never moved: their place and heights are the whole project's.",
        "properties": {"ids": _ids(), "dx": _num(), "dy": _num(), "dz": _num()},
    },
    {
        "name": "delete_elements",
        "description": "Delete elements (ids or refs) with what depends on them. Only when the person asked for it in "
        "this conversation; confirm must be true to say so, and the person confirms again before approval.",
        "properties": {"ids": _ids(), "confirm": _bool()},
    },
    {
        "name": "set_site",
        "description": "Set the model's place on earth: the site's latitude and longitude in WGS 84 degrees (south "
        "and west negative), its elevation in metres above sea level, and, when the model is drawn in a projected "
        "coordinate system, the map conversion: crs is the EPSG code (such as EPSG:3006 for SWEREF 99 TM), eastings "
        "and northings the coordinates of the model's origin in metres, and rotation the angle in degrees from grid "
        "east (the map's x axis, along the eastings) to the model's X axis, counter-clockwise positive, as "
        "IfcMapConversion measures it (0 when null: the model's X axis points east and its Y axis north). crs, "
        "eastings and northings go together; site_name renames the site. For a building in Sweden prefer the local "
        "SWEREF 99 zone with RH 2000 heights as one compound code, EPSG:5846 to EPSG:5857 for the zones 12 00 to 23 "
        "15 in the order of EPSG:3007 to EPSG:3018 (such as EPSG:5850 for SWEREF 99 18 00 + RH 2000), when the "
        "eastings and northings are in that zone; coordinates in SWEREF 99 TM take EPSG:5845 (TM + RH 2000). Never "
        "convert coordinates between zones yourself: use the code of the coordinates you were given. vertical_datum "
        "is the height system of the elevation when the code does not give one (null: RH 2000 for EPSG:3006 to "
        "EPSG:3018). One call per model is enough: a second call replaces the first.",
        "properties": {
            "latitude": {"type": "number"},
            "longitude": {"type": "number"},
            "elevation": _num(),
            "crs": _str(),
            "eastings": _num(),
            "northings": _num(),
            "rotation": _num(),
            "site_name": _str(),
            "vertical_datum": _str(),
        },
    },
    {
        "name": "manage_changeset",
        "description": "The open change set: action list shows its steps, remove_last drops the last step, clear "
        "empties it.",
        "properties": {"action": {"type": "string"}},
    },
)
_BY_NAME = {tool["name"]: tool for tool in TOOLS}


def has(name: str) -> bool:
    return name in _BY_NAME


def tool(name: str) -> dict[str, Any]:
    return _BY_NAME[name]


class WriteToolError(Exception):
    """A call that build() refuses, in the app's words: the AI mends the call."""


# -- JavaScript's semantics, where Python's differ ----------------------------------------------------------------

_REF = re.compile(r"new-[0-9]+", re.ASCII)
_DIGITS = re.compile(r"[0-9]+", re.ASCII)
#: An IFC GlobalId: 22 characters of IFC's base 64 (a proposal to a server names elements so; decision F34 a).
GUID = re.compile(r"[0-9A-Za-z_$]{22}", re.ASCII)
_EPSG = re.compile(r"EPSG:[0-9]+", re.ASCII | re.IGNORECASE)
_PLACEHOLDER = re.compile(r"\{(\w+)\}", re.ASCII)
_INDEX = re.compile(r"0|[1-9][0-9]*", re.ASCII)
#: What JavaScript's ``\s`` and ``trim()`` take: its white space and its line terminators.
_JS_SPACE_CHARS = "\t\n\v\f\r   " + "".join(map(chr, range(0x2000, 0x200B))) + "    　﻿"
_JS_SPACE = re.escape(_JS_SPACE_CHARS)  # within a character class
_SPACES = re.compile(f"[{_JS_SPACE}]+")
_SPACES_OR_HYPHENS = re.compile(f"[{_JS_SPACE}-]+")
_ENUM_VALUE = re.compile(r"[A-Z][A-Z0-9_]*", re.ASCII)
_STANDARD_SET = re.compile(r"(pset|qto)_", re.ASCII | re.IGNORECASE)
#: A number with a unit written after it ("40 dB"), as the app's ``unitIn`` reads it; ``.`` takes no line terminator.
_UNIT_IN = re.compile(
    f"[{_JS_SPACE}]*([-+]?[0-9]+(?:[.,][0-9]+)?(?:[eE][-+]?[0-9]+)?)[{_JS_SPACE}]*"
    f"([^0-9{_JS_SPACE}.,+-][^\n\r  ]*?)[{_JS_SPACE}]*"
)
#: A set of the model's own as the guidance names it: country, origin and project, then the set's name
#: (SE-ACME-42_Acoustics).
OWN_SET = re.compile(r"[A-Z]{2}-[A-Za-z0-9]+(?:-[A-Za-z0-9]+)?(?:_[A-Za-z0-9]+)?", re.ASCII)
_PASCAL = re.compile(r"[A-Z][A-Za-z0-9]*", re.ASCII)


def _trim(value: str) -> str:
    """``value.trim()``."""
    return value.strip(_JS_SPACE_CHARS)


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _double(value: int | float) -> float:
    """A number as JavaScript holds it: a double, infinite beyond the doubles' range."""
    try:
        return float(value)
    except OverflowError:
        return math.inf if value > 0 else -math.inf


def _finite(value: Any) -> bool:
    return _is_number(value) and math.isfinite(_double(value))


def _integer(value: Any) -> bool:
    """``Number.isInteger``."""
    return _finite(value) and math.floor(_double(value)) == _double(value)


def _given(value: Any) -> bool:
    return value is not None and value != ""


def _round(value: float) -> int:
    """``Math.round``: the nearer integer, and a half toward positive infinity."""
    low = math.floor(value)
    return low + 1 if value - low >= 0.5 else low


def _js_number(value: float) -> str:
    """``String(number)``: the shortest digits that read back as the number, without a point when it is whole, in
    fixed notation from 1e-6 to 1e21 and in exponent notation beyond."""
    if value == 0:
        return "0"
    if isinstance(value, int) and abs(value) < 2**53:
        return str(value)
    value = _double(value)
    if not math.isfinite(value):
        return "NaN" if math.isnan(value) else "Infinity" if value > 0 else "-Infinity"
    sign, digits, exponent = Decimal(repr(value)).as_tuple()
    shortest = "".join(str(digit) for digit in digits)
    text = shortest.rstrip("0")  # repr's digits, without the zeros of a whole number's ".0"
    k, n = len(text), len(shortest) + int(exponent)
    if k <= n <= 21:
        body = text + "0" * (n - k)
    elif 0 < n <= 21:
        body = text[:n] + "." + text[n:]
    elif -6 < n <= 0:
        body = "0." + "0" * -n + text
    else:
        body = text[0] + ("." + text[1:] if k > 1 else "") + "e" + ("+" if n - 1 >= 0 else "-") + str(abs(n - 1))
    return ("-" if sign else "") + body


def _string(value: Any) -> str:
    """``String(value)``."""
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if _is_number(value):
        return _js_number(value)
    if isinstance(value, list):
        return ",".join("" if item is None else _string(item) for item in value)
    return "null" if value is None else "[object Object]"


def _truthy(value: Any) -> bool:
    """JavaScript's truth: every list and object is true, and only an empty text, zero and null are false."""
    if isinstance(value, list | dict):
        return True
    return bool(value) and not (isinstance(value, float) and math.isnan(value))


def _slice(value: str, length: int) -> str:
    """``value.slice(0, length)``, counted in UTF-16 code units."""
    return value.encode("utf-16-le")[: 2 * length].decode("utf-16-le", errors="ignore")


def _in_js_order(values: dict[str, Any]) -> dict[str, Any]:
    """An object's keys in JavaScript's order: those that are array indexes first, ascending, then the rest as made."""
    indexes = sorted((key for key in values if _INDEX.fullmatch(key) and int(key) < 2**32 - 1), key=int)
    return {key: values[key] for key in [*indexes, *(key for key in values if key not in indexes)]}


def _fill(text: str, **params: Any) -> str:
    """``t(key, params)`` with the line already looked up: each ``{name}`` given replaced, the others kept."""
    return _PLACEHOLDER.sub(lambda m: _string(params[m[1]]) if m[1] in params else m[0], text)


# -- the checks and build() ----------------------------------------------------------------------------------------


def _number(
    args: dict[str, Any],
    key: str,
    *,
    required: bool = False,
    fallback: float | None = None,
    positive: bool = False,
    unit: str = "metres",
) -> Any:
    v: Any = args.get(key)
    if not _given(v):
        if required:
            raise WriteToolError(f"{key} is required ({unit})")
        return fallback
    if not _finite(v):
        raise WriteToolError(f"{key} must be a number ({unit})")
    if positive and v <= 0:
        raise WriteToolError(f"{key} must be greater than zero")
    return v


def _point(v: Any, key: str) -> list[Any]:
    if not isinstance(v, list) or len(v) != 2 or not _finite(v[0]) or not _finite(v[1]):
        raise WriteToolError(f"{key} must be [x, y] in metres")
    return [v[0], v[1]]


def _text(args: dict[str, Any], key: str, *, required: bool = False) -> str | None:
    v = args.get(key)
    if not _given(v):
        if required:
            raise WriteToolError(f"{key} is required")
        return None
    return _slice(_string(v), 200)


def _id_list(cs: dict[str, Any], v: Any) -> list[Any]:
    if not isinstance(v, list) or not v:
        raise WriteToolError("ids must be a list of element ids or refs")
    if len(v) > MAX_IDS:
        raise WriteToolError(f"at most {MAX_IDS} ids in one step")
    return [_id_or_ref(cs, x, "ids") for x in v]


def _id_or_ref(cs: dict[str, Any], x: Any, key: str) -> Any:
    refs = cs["refs"]
    if isinstance(x, str) and _REF.fullmatch(x):
        if int(x[4:]) < 1 or int(x[4:]) > refs:
            within = f"new-1 to new-{refs}" if refs else "none yet"
            raise WriteToolError(f"{x} is not a ref of this change set ({within})")
        return x
    n = int(x) if isinstance(x, str) and _DIGITS.fullmatch(x) else x
    if isinstance(n, str) and GUID.fullmatch(n):
        return n
    if not _integer(n) or n < 1:
        raise WriteToolError(f"{key} must hold element ids (integers), GlobalIds or refs (new-1, …)")
    return int(n)


def _corners(points: list[list[Any]]) -> list[list[Any]]:
    """[x, y] corners without a repeat of the first one at the end: the wheel closes an outline on its first point
    (GEM111)."""
    out = list(points)
    while len(out) > 1 and out[-1][0] == out[0][0] and out[-1][1] == out[0][1]:
        out.pop()
    return out


def _bounds(points: list[list[Any]]) -> list[float]:
    """The bounding box [x0, y0, x1, y1] of [x, y] points."""
    box = [math.inf, math.inf, -math.inf, -math.inf]
    for p in points:
        box = [min(box[0], p[0]), min(box[1], p[1]), max(box[2], p[0]), max(box[3], p[1])]
    return box


def _rectangular(points: list[list[Any]]) -> bool:
    """Whether [x, y] points are the four corners of their bounding box (a closing corner may repeat the first)."""
    last = points[-1]
    p = points[:-1] if len(points) > 4 and last[0] == points[0][0] and last[1] == points[0][1] else points
    if len(p) != 4:
        return False
    x0, y0, x1, y1 = _bounds(p)

    def side(v: float, lo: float, hi: float) -> str:
        return "lo" if abs(v - lo) < 1e-3 else "hi" if abs(v - hi) < 1e-3 else ""

    hit = {side(q[0], x0, x1) + "," + side(q[1], y0, y1) for q in p}
    return len(hit) == 4 and all(not k.startswith(",") and not k.endswith(",") for k in hit)


def _outline_of(a: dict[str, Any]) -> list[list[Any]] | None:
    if not _given(a.get("outline")):
        return None
    return _corners([_point(p, "outline") for p in a["outline"]]) if isinstance(a["outline"], list) else None


def _is_ref(x: Any) -> bool:
    return isinstance(x, str) and _REF.fullmatch(x) is not None


def _layers_thickness(layers: list[dict[str, Any]]) -> float:
    """The total of a type's layers in metres."""
    total = 0.0
    for layer in layers:
        total += _double(layer["thickness"])
    return _round(total * 1e6) / 1e6 if math.isfinite(total * 1e6) else total


def _type_of(cs: dict[str, Any], a: dict[str, Any], kind: str, tool: str) -> dict[str, Any] | None:
    """The type a create step names, as {ref, thickness}: the ref of a define_type step of the kind, checked here and
    with its layers' thickness, or a type's id or GlobalId in the model, which the wheel checks (thickness null); null
    without a type."""
    if not _given(a.get("type")):
        return None
    ref = _id_or_ref(cs, a["type"], "type")
    if not _is_ref(ref):
        return {"ref": ref, "thickness": None}
    found = next((op for op in cs["ops"] if op.get("ref") == ref), None)
    if not found or found["tool"] != "define_type":
        raise WriteToolError(f"type {ref} is not a type; give the ref of a define_type step, or a type's id")
    if found["kind"] != kind:
        raise WriteToolError(f"type {ref} is a {found['kind']} type; {tool} takes a {kind} type")
    return {"ref": ref, "thickness": _layers_thickness(found["layers"])}


def _typed_thickness(a: dict[str, Any], typed: dict[str, Any]) -> Any:
    """A typed step's thickness: the layers', which a thickness given must match (within half a millimetre)."""
    own = _number(a, "thickness", positive=True)
    if own is not None and typed["thickness"] is not None and abs(own - typed["thickness"]) > 0.0005:
        raise WriteToolError(
            f"thickness {_fmt(own)} m differs from the {_fmt(typed['thickness'])} m of the layers of type "
            f"{_string(typed['ref'])}; leave thickness null"
        )
    return typed["thickness"] if typed["thickness"] is not None else own


def _common(a: dict[str, Any], op: dict[str, Any], bearing: bool) -> dict[str, Any]:
    """The load_bearing (walls and slabs) and status of a create step, checked and put on the op only when given: the
    wheel writes them in the common set, on the type when every occurrence agrees. A partition is not load-bearing."""
    if bearing and _given(a.get("load_bearing")):
        if not isinstance(a["load_bearing"], bool):
            raise WriteToolError("load_bearing must be true, false or null (not given)")
        if a["load_bearing"] and a.get("partition") is True:
            raise WriteToolError(
                "partition true makes a non-load-bearing wall; leave partition null for a load-bearing wall"
            )
        op["load_bearing"] = a["load_bearing"]
    if _given(a.get("status")):
        status = _trim(_string(a["status"])).upper()
        if status not in STATUSES:
            raise WriteToolError(f"status must be {', '.join(STATUSES)} or null")
        op["status"] = status
    return op


def unit_in(value: Any) -> list[str] | None:
    """[number, unit] of a text that is a number with its unit written after it ("40 dB"); null otherwise."""
    if not isinstance(value, str):
        return None
    m = _UNIT_IN.fullmatch(value)
    return [m[1], m[2]] if m and _SPACES.sub("", m[2]).lower() in UNITS else None


def _standard_set(pset: str) -> bool:
    """Whether a set is IFC's own (Pset_…, Qto_…), which the wheel checks against the schema's templates."""
    return _STANDARD_SET.match(pset) is not None


def _own_set_advice(op: dict[str, Any]) -> str | None:
    """Advice, not a refusal, for a set of the model's own: the guidance's naming (country-origin-project_Name) and
    PascalCase property names in plain letters; null when both are kept."""
    if _standard_set(op["pset"]):
        return None
    tips = []
    if not OWN_SET.fullmatch(op["pset"]):
        tips.append(
            "name a set of your own country-origin-project_Name in letters a-z, digits and hyphens, such as "
            f"SE-ACME-42_Acoustics, rather than {op['pset']}"
        )
    odd = [name for name in op["properties"] if not _PASCAL.fullmatch(name)]
    if odd:
        tips.append(
            "give its properties PascalCase names without spaces, å, ä or ö, such as SoundReduction, rather than "
            + ", ".join(odd)
        )
    return f"advice: {'; '.join(tips)}. Use IFC's own sets (Pset_…) first when one has the property." if tips else None


def _storey_texts(s: dict[str, Any], op: dict[str, Any]) -> dict[str, Any]:
    """A storey's optional description and long_name on its operation, each only when given, so that older change
    sets keep their form."""
    for key in ("description", "long_name"):
        v = _text(s, key)
        if v and _trim(v):
            op[key] = _trim(v)
    return op


def _room_extras(r: dict[str, Any], room: dict[str, Any]) -> dict[str, Any]:
    """A listed room's optional number and room_type on its operation, each only when given: with a number the wheel
    names the space by it, with the name as its long name."""
    number = _slice(_trim(_string(r["number"])), 60) if _given(r.get("number")) else ""
    if number:
        room["number"] = number
    room_type = _text(r, "room_type")
    if room_type and _trim(room_type):
        room["room_type"] = _trim(room_type)
    return room


def _vertical_datum(a: dict[str, Any], crs: str | None, op: dict[str, Any]) -> dict[str, Any]:
    """set_site's optional vertical_datum on its operation, only when given: the height system of the elevation for a
    code without heights. A compound code names its own, so RH 2000 with one is dropped and another refused."""
    v = _text(a, "vertical_datum")
    datum = _trim(v) if v else ""
    if not datum:
        return op
    if not crs:
        raise WriteToolError("vertical_datum goes with a crs, such as EPSG:3006 with RH 2000")
    code = int(crs[5:])
    if RH2000_CODES[0] <= code <= RH2000_CODES[1]:
        if _SPACES.sub("", datum).upper() == "RH2000":
            return op
        raise WriteToolError(
            f"{crs.upper()} gives its heights in RH 2000 already; leave vertical_datum null, or give the plan code "
            f"EPSG:{code - 2839} with this vertical_datum"
        )
    op["vertical_datum"] = _slice(datum, 60)
    return op


def _edit_op(cs: dict[str, Any], a: dict[str, Any]) -> dict[str, Any]:
    """An edit_element step: only the fields given, checked as the create steps check them, of one kind of element
    (EDITS) and, for an element of this change set, of its kind; a type's ref must be a wall or slab type, whose layers
    give the thickness."""
    if not _given(a.get("id")):
        raise WriteToolError("id is required: the element's id, GlobalId or ref (new-1, …)")
    op: dict[str, Any] = {"tool": "edit_element", "id": _id_or_ref(cs, a["id"], "id")}
    label = _text(a, "name")
    if label is not None and not _trim(label):
        raise WriteToolError("name must not be empty; null keeps it")
    if label is not None:
        op["name"] = _trim(label)
    if _given(a.get("start")):
        op["start"] = _point(a["start"], "start")
    if _given(a.get("end")):
        op["end"] = _point(a["end"], "end")
    if op.get("start") and op.get("end"):
        if math.hypot(op["end"][0] - op["start"][0], op["end"][1] - op["start"][1]) < 0.01:
            raise WriteToolError("start and end are the same point")
    if _given(a.get("outline")):
        outline = _corners([_point(p, "outline") for p in a["outline"]]) if isinstance(a["outline"], list) else None
        if not outline or len(outline) < 3:
            raise WriteToolError("outline must be at least three [x, y] points, or null to keep it")
        op["outline"] = outline
    for key in ("thickness", "height", "width"):
        v = _number(a, key, positive=True)
        if v is not None:
            op[key] = v
    for key in ("offset", "sill", "base"):
        v = _number(a, key)
        if v is not None:
            op[key] = v
    pitch = _number(a, "pitch", unit="degrees")
    if pitch is not None and (pitch <= 0 or pitch > 75):
        raise WriteToolError("pitch must be more than 0 and at most 75 degrees")
    if pitch is not None:
        op["pitch"] = pitch
    overhang = _number(a, "overhang")
    if overhang is not None and overhang < 0:
        raise WriteToolError("overhang must be zero or more (metres)")
    if overhang is not None:
        op["overhang"] = overhang
    measures = [key for key in op if key not in ("tool", "id", "name")] + (["type"] if _given(a.get("type")) else [])
    if not measures and label is None:
        raise WriteToolError(f"nothing to change: {EDIT_KINDS}; give at least one, and null for the rest")
    kinds = [kind for kind, fields in EDITS.items() if all(m in fields for m in measures)]
    if measures and not kinds:
        raise WriteToolError(f"{', '.join(measures)} do not go together: {EDIT_KINDS}")
    made = _step_of(cs, op["id"])
    if made and measures and EDIT_OF.get(made["tool"]) not in kinds:
        takes = EDITS[EDIT_OF[made["tool"]]] if made["tool"] in EDIT_OF else None
        raise WriteToolError(
            f"{op['id']} is made by {made['tool']}, so it takes {', '.join(takes) + ' or name' if takes else 'only name'}"
        )
    if made and made["tool"] in EDIT_OF:
        kinds = [EDIT_OF[made["tool"]]]
    if _given(a.get("type")):
        kind = kinds[0] if len(kinds) == 1 else None
        ref = _id_or_ref(cs, a["type"], "type")
        if _is_ref(ref):
            found = next((o for o in cs["ops"] if o.get("ref") == ref), None)
            if not found or found["tool"] != "define_type":
                raise WriteToolError(f"type {ref} is not a type; give the ref of a define_type step, or a type's id")
            if found["kind"] not in kinds:
                raise WriteToolError(
                    f"type {ref} is a {found['kind']} type; edit_element gives "
                    f"{'a ' + kind if kind else 'a wall or a slab'} a type of its own kind"
                )
            layers = _layers_thickness(found["layers"])
            if "thickness" in op and abs(op["thickness"] - layers) > 0.0005:
                raise WriteToolError(
                    f"thickness {_fmt(op['thickness'])} m differs from the {_fmt(layers)} m of the layers of type "
                    f"{ref}; leave thickness null"
                )
            op["thickness"] = layers
        op["type"] = ref
    return op


def _either(words: tuple[str, ...] | list[str]) -> str:
    """'a, b or c'."""
    return ", ".join(words[:-1]) + " or " + words[-1]


def _step_of(cs: dict[str, Any], ref: Any) -> dict[str, Any] | None:
    """A ref of this change set and the step that made it (a space of create_spaces by its refs), or null for an id
    or GlobalId."""
    if not _is_ref(ref):
        return None
    return next((op for op in cs["ops"] if op.get("ref") == ref or ref in (op.get("refs") or [])), None)


def _fill_type(cs: dict[str, Any], a: dict[str, Any], fill: str | None) -> dict[str, Any] | None:
    """The door or window type of create_opening, as {ref, fill, width, height}: a define_type ref of kind door or
    window with its size, or a type of the model, whose size the wheel reads (fill must then be given); null without
    a type."""
    if not _given(a.get("type")):
        return None
    ref = _id_or_ref(cs, a["type"], "type")
    found = _step_of(cs, ref)
    if not _is_ref(ref):
        if not fill:
            raise WriteToolError("with a type of the model, give fill door or window")
        return {"ref": ref, "fill": fill, "width": None, "height": None}
    if not found or found["tool"] != "define_type":
        raise WriteToolError(
            f"type {ref} is not a type; give the ref of a define_type step, or a type's id or GlobalId"
        )
    if found["kind"] not in ("door", "window"):
        raise WriteToolError(f"type {ref} is a {found['kind']} type; create_opening takes a door or window type")
    if fill and fill != found["kind"]:
        raise WriteToolError(f"type {ref} is a {found['kind']} type, so fill must be {found['kind']} or null")
    return {"ref": ref, "fill": found["kind"], "width": found["width"], "height": found["height"]}


def _fill_size(a: dict[str, Any], typed: dict[str, Any], key: str) -> Any:
    """A typed opening's width or height: the type's, which one given must match; null for a type of the model
    without one given."""
    own = _number(a, key, positive=True)
    if own is not None and typed[key] is not None and abs(own - typed[key]) > 0.0005:
        raise WriteToolError(
            f"{key} {_fmt(own)} m differs from the {_fmt(typed[key])} m of type {_string(typed['ref'])}; leave width "
            "and height null"
        )
    return typed[key] if typed[key] is not None else own


def _element_type(cs: dict[str, Any], a: dict[str, Any], cls: str) -> dict[str, Any] | None:
    """The type of create_element, as {ref, kind, thickness}: a define_type ref of the class's kind (a covering's
    with its layers' thickness), or a type of the model, which the wheel checks; null without a type."""
    if not _given(a.get("type")):
        return None
    ref = _id_or_ref(cs, a["type"], "type")
    kind = CLASS_KIND.get(cls)
    if not _is_ref(ref):
        return {"ref": ref, "kind": kind, "thickness": None}
    found = _step_of(cs, ref)
    if not found or found["tool"] != "define_type":
        raise WriteToolError(
            f"type {ref} is not a type; give the ref of a define_type step, or a type's id or GlobalId"
        )
    if not kind:
        raise WriteToolError(
            f"define_type makes no type for {cls}; give a type of the model by its GlobalId or id, or null"
        )
    if found["kind"] != kind:
        raise WriteToolError(f"type {ref} is a {found['kind']} type; {cls} takes a {kind} type")
    return {"ref": ref, "kind": kind, "thickness": _layers_thickness(found["layers"]) if found["layers"] else None}


def _prefixed(prefix: str, read: Any, *args: Any, **kwargs: Any) -> Any:
    """A check of a field of a nested object, its error prefixed with the object's name (``shape.``, ``stair.``)."""
    try:
        return read(*args, **kwargs)
    except WriteToolError as exc:
        raise WriteToolError(prefix + str(exc)) from None


def _shape_of(s: Any, typed: dict[str, Any] | None) -> dict[str, Any]:
    """create_element's shape, checked; its depth from a covering type's layers."""
    if not isinstance(s, dict):
        raise WriteToolError("shape must be {profile, x, y, radius, outline, depth, along}")
    profile = _trim(_string(s["profile"])).lower() if _given(s.get("profile")) else ""
    along = _trim(_string(s["along"])).lower() if _given(s.get("along")) else "z"
    if along not in ("z", "x"):
        raise WriteToolError(
            "shape.along must be z (standing, extruded up from z) or x (lying, extruded in the direction of rotation)"
        )
    out: dict[str, Any] = {
        "profile": profile, "x": None, "y": None, "radius": None, "outline": None, "depth": None, "along": along
    }  # fmt: skip
    if profile == "rectangle":
        out["x"] = _prefixed("shape.", _number, s, "x", required=True, positive=True)
        out["y"] = _prefixed("shape.", _number, s, "y", required=True, positive=True)
    elif profile == "circle":
        out["radius"] = _prefixed("shape.", _number, s, "radius", required=True, positive=True)
    elif profile == "polygon":
        if along != "z":
            raise WriteToolError("a polygon is an outline in the plan, so shape.along must be z")
        if not isinstance(s.get("outline"), list):
            raise WriteToolError("shape.outline must be [x, y] corners in metres in the storey's plane")
        out["outline"] = _corners([_point(p, "shape.outline") for p in s["outline"]])
        if len(out["outline"]) < 3 or len(out["outline"]) > MAX_OUTLINE:
            raise WriteToolError(f"shape.outline must be 3 to {MAX_OUTLINE} different [x, y] corners")
    else:
        raise WriteToolError("shape.profile must be rectangle, circle or polygon")
    depth = _prefixed("shape.", _number, s, "depth", positive=True)
    if typed and typed["thickness"] is not None:
        if depth is not None and abs(depth - typed["thickness"]) > 0.0005:
            raise WriteToolError(
                f"shape.depth {_fmt(depth)} m differs from the {_fmt(typed['thickness'])} m of the layers of type "
                f"{_string(typed['ref'])}; leave depth null"
            )
        out["depth"] = typed["thickness"]
    elif depth is None and not (typed and typed["kind"] == "covering"):
        raise WriteToolError("shape.depth is required (metres)")
    else:
        out["depth"] = depth
    if out["depth"] is not None and out["depth"] > 200:
        raise WriteToolError("shape.depth must be at most 200 m")
    return out


def _stair_of(s: Any) -> dict[str, Any]:
    """create_element's stair, checked: the flight of a straight stair."""
    if not isinstance(s, dict):
        raise WriteToolError("an IfcStair needs stair: {risers, riser_height, tread_length, width, thickness, landing}")
    risers = s.get("risers")
    if not _integer(risers) or risers < 2 or risers > MAX_RISERS:
        raise WriteToolError(f"stair.risers must be a whole number from 2 to {MAX_RISERS}")
    riser = _prefixed("stair.", _number, s, "riser_height", required=True, positive=True)
    out = {
        "risers": risers,
        "riser_height": riser,
        "tread_length": _prefixed("stair.", _number, s, "tread_length", required=True, positive=True),
        "width": _prefixed("stair.", _number, s, "width", fallback=1, positive=True),
        "thickness": _prefixed("stair.", _number, s, "thickness", fallback=max(0.2, riser), positive=True),
        "landing": _prefixed("stair.", _number, s, "landing", positive=True),
    }
    if out["thickness"] < riser - 1e-9:
        raise WriteToolError(
            f"stair.thickness {_fmt(out['thickness'])} m (the waist at right angles to the slope) must be at least "
            f"the riser height, {_fmt(riser)} m"
        )
    return out


def _whole_ref(cs: dict[str, Any], x: Any, key: str, tools: tuple[str, ...]) -> Any:
    """part_of or host of create_element: a ref of a step that makes such a whole or host, or an id or GlobalId the
    wheel checks."""
    ref = _id_or_ref(cs, x, key)
    found = _step_of(cs, ref)
    if found and found["tool"] not in tools:
        raise WriteToolError(f"{key} {ref} is the {found['tool']} step; {key} takes {_either(tools)}")
    return ref


def _no_twin(cs: dict[str, Any], kind: str, type_name: str) -> None:
    """No two define_type steps of one type class with the same name (in any case)."""
    twin = next(
        (
            op
            for op in cs["ops"]
            if op["tool"] == "define_type"
            and TYPE_CLASS[op["kind"]] == TYPE_CLASS[kind]
            and op["name"].lower() == type_name.lower()
        ),
        None,
    )
    if twin:
        raise WriteToolError(
            f"{twin['ref']} is a {twin['kind']} type of the same name already; give its ref as type, or choose "
            "another name"
        )


def _predefined(a: dict[str, Any]) -> str | None:
    return _trim(_string(a["predefined_type"])).upper() if _given(a.get("predefined_type")) else None


def _element_type_op(cs: dict[str, Any], tool: str, kind: str, type_name: str, a: dict[str, Any]) -> dict[str, Any]:
    """define_type for a kind without layers: its material, and a door's operation or a window's partitioning with
    the size and lining."""
    layers = a.get("layers")
    if len(layers) if isinstance(layers, list) else _given(layers):
        raise WriteToolError(f"a {kind} type has no layers; give its material as material, or null")
    predefined = _predefined(a)
    if predefined and not _ENUM_VALUE.fullmatch(predefined):
        raise WriteToolError(
            "predefined_type must be a PredefinedType such as COLUMN, BEAM, PAD_FOOTING, HANDRAIL, DOOR or WINDOW, "
            "or null"
        )
    if predefined == "USERDEFINED":
        raise WriteToolError(
            "USERDEFINED needs the name of a kind of its own, which define_type does not take; choose a value from "
            "the class's list, or NOTDEFINED"
        )
    _no_twin(cs, kind, type_name)
    op: dict[str, Any] = {
        "tool": tool,
        "kind": kind,
        "name": type_name,
        "layers": None,
        "predefined_type": predefined or None,
    }
    given_material = _text(a, "material")
    material = _trim(given_material) if given_material else ""
    category = _trim(_string(a["material_category"])).lower() if _given(a.get("material_category")) else None
    if category and category not in MATERIAL_CATEGORIES:
        raise WriteToolError(f"material_category must be {', '.join(MATERIAL_CATEGORIES)} or null")
    if material:
        op["material"] = material
        op["material_category"] = category or None
    if kind not in ("door", "window"):
        return op
    key = "operation" if kind == "door" else "partitioning"
    values = DOOR_OPERATIONS if kind == "door" else WINDOW_PARTITIONS
    value = _SPACES_OR_HYPHENS.sub("_", _trim(_string(a[key])).upper()) if _given(a.get(key)) else values[0]
    if value not in values:
        raise WriteToolError(f"{key} must be {_either(values)}")
    op[key] = value
    op["width"] = _number(a, "width", fallback=0.9 if kind == "door" else 1.2, positive=True)
    op["height"] = _number(a, "height", fallback=2.1 if kind == "door" else 1.2, positive=True)
    op["lining_depth"] = _number(a, "lining_depth", fallback=0.05, positive=True)
    if op["width"] < 0.3 or op["width"] > 20 or op["height"] < 0.3 or op["height"] > 20:
        raise WriteToolError("width and height must be 0.3 to 20 m")
    if op["lining_depth"] < 0.05 or op["lining_depth"] > 2:
        raise WriteToolError("lining_depth must be 0.05 to 2 m")
    return op


def _define_type(cs: dict[str, Any], name: str, a: dict[str, Any]) -> dict[str, Any]:
    kind = _trim(_string(a["kind"])).lower() if _given(a.get("kind")) else ""
    if kind not in TYPE_KINDS:
        raise WriteToolError(f"kind must be {_either(TYPE_KINDS)}")
    type_name = _trim(_text(a, "name", required=True) or "")
    if not type_name:
        raise WriteToolError("name is required")
    if kind not in LAYERED_KINDS:
        return _element_type_op(cs, name, kind, type_name, a)
    given = a.get("layers")
    if not isinstance(given, list) or not given or len(given) > MAX_LAYERS:
        raise WriteToolError(
            f"layers must be a list of 1 to {MAX_LAYERS} {{material, thickness, category, role}}, the thickness in "
            "metres"
        )
    layers = []
    for i, layer in enumerate(given):
        which = f"layer {i + 1}"
        if not isinstance(layer, dict) or not _given(layer.get("material")) or not _trim(_string(layer["material"])):
            raise WriteToolError(f"{which} needs a material")
        if not _finite(layer.get("thickness")) or layer["thickness"] <= 0:
            raise WriteToolError(f"{which}: thickness must be a number greater than zero (metres)")
        category = _trim(_string(layer["category"])).lower() if _given(layer.get("category")) else None
        if category and category not in MATERIAL_CATEGORIES:
            raise WriteToolError(f"{which}: category must be {', '.join(MATERIAL_CATEGORIES)} or null")
        role = _SPACES_OR_HYPHENS.sub("_", _trim(_string(layer["role"])).lower()) if _given(layer.get("role")) else None
        if role and role not in LAYER_ROLES:
            raise WriteToolError(f"{which}: role must be {', '.join(LAYER_ROLES)} or null")
        layers.append(
            {
                "material": _slice(_trim(_string(layer["material"])), 200),
                "thickness": layer["thickness"],
                "category": category or None,
                "role": role or None,
            }
        )
    if _layers_thickness(layers) > 5:
        raise WriteToolError("the layers add up to more than 5 m")
    predefined = _predefined(a)
    if predefined and not _ENUM_VALUE.fullmatch(predefined):
        raise WriteToolError(
            "predefined_type must be a PredefinedType such as SOLIDWALL, PARTITIONING, FLOOR or BASESLAB, or null"
        )
    if predefined == "USERDEFINED":
        raise WriteToolError(
            "USERDEFINED needs the name of a kind of its own, which define_type does not take; choose a value from "
            "the class's list, or NOTDEFINED"
        )
    if kind == "roof" and predefined and predefined != "ROOF":
        raise WriteToolError("a roof type is an IfcSlabType ROOF; leave predefined_type null")
    _no_twin(cs, kind, type_name)
    return {"tool": name, "kind": kind, "name": type_name, "layers": layers, "predefined_type": predefined or None}


def _create_element(cs: dict[str, Any], name: str, a: dict[str, Any]) -> dict[str, Any]:
    wanted = _trim(_string(a["ifc_class"])).lower() if _given(a.get("ifc_class")) else None
    cls = next((c for c in ELEMENT_CLASSES if c.lower() == wanted), None) if wanted is not None else None
    if not cls:
        raise WriteToolError(
            f"ifc_class must be {_either(ELEMENT_CLASSES)}; walls, slabs, roofs, openings with their doors and "
            "windows, and spaces have tools of their own, and IfcBuildingElementProxy is never used"
        )
    predefined = _predefined(a)
    if predefined and not _ENUM_VALUE.fullmatch(predefined):
        raise WriteToolError(
            "predefined_type must be a value of the class's list, such as COLUMN or STRIP_FOOTING, or null"
        )
    given_type = _text(a, "object_type")
    object_type = _trim(given_type) if given_type else None
    if predefined == "USERDEFINED" and not object_type:
        raise WriteToolError(
            "USERDEFINED needs object_type, the name of its kind; or choose a value of the class's list"
        )
    typed = _element_type(cs, a, cls)
    op: dict[str, Any] = {
        "tool": name,
        "storey": _text(a, "storey"),
        "ifc_class": cls,
        "predefined_type": predefined,
        "object_type": object_type or None,
        "name": _text(a, "name"),
        "at": None,
        "z": _number(a, "z", fallback=0),
        "rotation": _number(a, "rotation", fallback=0, unit="degrees"),
        "shape": None,
        "stair": None,
        "part_of": None,
        "host": None,
    }
    if typed:
        op["type"] = typed["ref"]
    if cls == "IfcStair":
        if _given(a.get("shape")):
            raise WriteToolError("an IfcStair takes stair, not shape")
        if _given(a.get("part_of")) or _given(a.get("host")):
            raise WriteToolError(
                "a stair is not part_of another element and covers nothing, so part_of and host must be null"
            )
        if predefined and predefined != "STRAIGHT_RUN_STAIR":
            raise WriteToolError(
                "create_element makes straight stairs of one flight: predefined_type STRAIGHT_RUN_STAIR or null"
            )
        op["at"] = _point(a.get("at"), "at")
        op["stair"] = _stair_of(a.get("stair"))
        return op
    if _given(a.get("stair")):
        raise WriteToolError(f"stair is for IfcStair; {cls} takes shape")
    op["shape"] = _shape_of(a.get("shape"), typed)
    if op["shape"]["profile"] != "polygon":
        op["at"] = _point(a.get("at"), "at")
    if _given(a.get("part_of")):
        op["part_of"] = _whole_ref(cs, a["part_of"], "part_of", ("create_element", "create_roof"))
    if _given(a.get("host")):
        if cls != "IfcCovering":
            raise WriteToolError(
                "host is for IfcCovering: the element or space it covers; a part of a whole is part_of"
            )
        op["host"] = _whole_ref(
            cs, a["host"], "host", ("create_wall", "create_slab", "create_roof", "create_element", "create_spaces")
        )
    return op


def build(cs: dict[str, Any], name: str, args: dict[str, Any] | None) -> dict[str, Any]:
    """The operation for one call, checked, in the shape the wheel reads."""
    a = args or {}
    if name == "create_storeys_and_grid":
        storeys = []
        given = a.get("storeys")
        for s in given if isinstance(given, list) else []:
            if not isinstance(s, dict) or not _given(s.get("name")):
                raise WriteToolError("every storey needs a name")
            storeys.append(
                _storey_texts(
                    s,
                    {
                        "name": _slice(_string(s["name"]), 200),
                        "elevation": s.get("elevation") if _finite(s.get("elevation")) else 0,
                    },
                )
            )
        grid = None
        if isinstance(a.get("grid"), dict):
            g = a["grid"]
            grid = {
                "x_spacing": _number(g, "x_spacing", required=True, positive=True),
                "x_count": _number(g, "x_count", fallback=1, positive=True),
                "y_spacing": _number(g, "y_spacing", required=True, positive=True),
                "y_count": _number(g, "y_count", fallback=1, positive=True),
            }
            if (
                not _integer(grid["x_count"])
                or not _integer(grid["y_count"])
                or grid["x_count"] > 100
                or grid["y_count"] > 100
            ):
                raise WriteToolError("x_count and y_count must be whole numbers, at most 100")
        if not storeys and not grid:
            raise WriteToolError("give storeys, a grid or both")
        return {"tool": name, "storeys": storeys, "grid": grid}
    if name == "define_type":
        return _define_type(cs, name, a)
    if name == "create_element":
        return _create_element(cs, name, a)
    if name == "create_wall":
        start = _point(a.get("start"), "start")
        end = _point(a.get("end"), "end")
        if math.hypot(end[0] - start[0], end[1] - start[1]) < 0.01:
            raise WriteToolError("start and end are the same point")
        typed = _type_of(cs, a, "wall", name)
        wall = {
            "tool": name,
            "storey": _text(a, "storey"),
            "start": start,
            "end": end,
            "thickness": _typed_thickness(a, typed) if typed else _number(a, "thickness", fallback=0.2, positive=True),
            "height": _number(a, "height", fallback=3, positive=True),
            "name": _text(a, "name"),
        }
        if typed:
            wall["type"] = typed["ref"]
        if a.get("partition") is True:
            wall["partition"] = True  # PARTITIONING in the wheel when untyped; SOLIDWALL otherwise
        return _common(a, wall, True)
    if name == "create_slab":
        outline = _outline_of(a)
        if _given(a.get("outline")) and (not outline or len(outline) < 3):
            raise WriteToolError("outline must be at least three [x, y] points, or null for the grid's extent")
        typed = _type_of(cs, a, "slab", name)
        slab = {
            "tool": name,
            "storey": _text(a, "storey"),
            "outline": outline,
            "thickness": _typed_thickness(a, typed) if typed else _number(a, "thickness", fallback=0.25, positive=True),
            "name": _text(a, "name"),
        }
        if typed:
            slab["type"] = typed["ref"]
        return _common(a, slab, True)
    if name == "create_roof":
        shape = _string(a["shape"]).lower() if _given(a.get("shape")) else ""
        if shape not in ROOF_SHAPES:
            raise WriteToolError("shape must be gable, hip, shed or flat")
        outline = _outline_of(a)
        if _given(a.get("outline")) and (not outline or len(outline) < 3):
            raise WriteToolError(
                "outline must be at least three [x, y] points, or null for the bounding box of the storey's walls"
            )
        if outline:
            b = _bounds(outline)
            if b[2] - b[0] < 0.1 or b[3] - b[1] < 0.1:
                raise WriteToolError("outline must span at least 0.1 m along x and along y")
        flat = shape == "flat"
        pitch = 0 if flat else _number(a, "pitch", fallback=10 if shape == "shed" else 30, unit="degrees")
        if not flat and (pitch <= 0 or pitch > 75):
            raise WriteToolError("pitch must be more than 0 and at most 75 degrees; use shape flat for a flat roof")
        overhang = _number(a, "overhang", fallback=0 if flat else 0.4)
        if overhang < 0:
            raise WriteToolError("overhang must be zero or more (metres)")
        ridge = _string(a["ridge"]).lower() if _given(a.get("ridge")) else None
        if ridge and ridge not in ("x", "y"):
            raise WriteToolError("ridge must be x, y or null")
        typed = _type_of(cs, a, "roof", name)
        roof = {
            "tool": name,
            "storey": _text(a, "storey"),
            "shape": shape,
            "outline": outline,
            "pitch": pitch,
            "overhang": overhang,
            "thickness": _typed_thickness(a, typed) if typed else _number(a, "thickness", fallback=0.25, positive=True),
            "ridge": ridge if shape in ("gable", "shed") else None,
            "base": _number(a, "base"),
            "name": _text(a, "name"),
        }
        if typed:
            roof["type"] = typed["ref"]
        return _common(a, roof, False)
    if name == "create_opening":
        fill = _string(a["fill"]).lower() if _given(a.get("fill")) else None
        if fill and fill not in ("door", "window"):
            raise WriteToolError("fill must be door, window or null")
        if not _given(a.get("wall_id")):
            raise WriteToolError("wall_id is required")
        typed = _fill_type(cs, a, fill)
        if typed:
            fill = typed["fill"]
        opening = {
            "tool": name,
            "wall_id": _id_or_ref(cs, a["wall_id"], "wall_id"),
            "offset": _number(a, "offset", fallback=0),
            "width": _fill_size(a, typed, "width") if typed else _number(a, "width", fallback=0.9, positive=True),
            "height": _fill_size(a, typed, "height") if typed else _number(a, "height", fallback=2.1, positive=True),
            "sill": _number(a, "sill", fallback=0),
            "fill": fill,
            "name": _text(a, "name"),
        }
        if typed:
            side = _trim(_string(a["side"])).lower() if _given(a.get("side")) else "left"
            if side not in ("left", "right"):
                raise WriteToolError(
                    "side must be left or right, seen from the wall's start toward its end, or null for left"
                )
            opening["type"] = typed["ref"]
            opening["side"] = side
        return opening
    if name == "create_spaces":
        storey = _text(a, "storey")
        rooms = None
        if _given(a.get("rooms")):
            if not isinstance(a["rooms"], list) or not a["rooms"]:
                raise WriteToolError("rooms must be a list of {at or index, name, long_name}, or null for every room")
            if len(a["rooms"]) > MAX_ROOMS:
                raise WriteToolError(f"at most {MAX_ROOMS} rooms in one step")
            if not storey:
                raise WriteToolError(
                    "name the storey the rooms are on; storey null goes with rooms null (every room on every storey)"
                )
            indexes: set[Any] = set()
            rooms = []
            for i, r in enumerate(a["rooms"]):
                which = f"room {i + 1}"
                if not isinstance(r, dict):
                    raise WriteToolError(f"{which} must be {{at or index, name, long_name}}")
                if _given(r.get("at")) == _given(r.get("index")):
                    raise WriteToolError(
                        f"{which} needs either at, an [x, y] point inside it in metres, or index, its index among the "
                        "storey's rooms in a report"
                    )
                if not _given(r.get("name")):
                    raise WriteToolError(f"{which} needs a name")
                if _given(r.get("index")) and (not _integer(r["index"]) or r["index"] < 1):
                    raise WriteToolError(f"{which}: index must be a whole number from 1")
                if _given(r.get("index")) and r["index"] in indexes:
                    raise WriteToolError(f"{which}: index {_string(r['index'])} is listed twice")
                if _given(r.get("index")):
                    indexes.add(r["index"])
                rooms.append(
                    _room_extras(
                        r,
                        {
                            "at": _point(r["at"], f"{which}: at") if _given(r.get("at")) else None,
                            "index": r["index"] if _given(r.get("index")) else None,
                            "name": _slice(_string(r["name"]), 200),
                            "long_name": _text(r, "long_name"),
                        },
                    )
                )
            numbers = [r.get("number") for r in rooms]
            twice = next((i for i, r in enumerate(rooms) if r.get("number") and numbers.index(r["number"]) != i), None)
            if twice is not None:
                raise WriteToolError(
                    f"room {twice + 1} has the number of room {numbers.index(numbers[twice]) + 1}; a room number is "
                    "unique in the building"
                )
        # Without a list the wheel names the rooms itself: the person's word for a room with {n} for its index.
        return {
            "tool": name,
            "storey": storey,
            "rooms": rooms,
            "height": _number(a, "height", positive=True),
            "default_name": None if rooms else _TEXTS["ai.change.spaces.name"],
        }
    if name == "set_properties":
        pset: Any = _text(a, "pset", required=True)
        if not isinstance(a.get("properties"), list) or not a["properties"]:
            raise WriteToolError("properties must be a list of {name, value}")
        if _STANDARD_SET.fullmatch(_trim(pset)):
            raise WriteToolError(
                f"{pset} is no set's name: give IFC's set, such as Pset_WallCommon, or a set of your own, such as "
                "SE-ACME-42_Acoustics"
            )
        properties: dict[str, Any] = {}
        for i, p in enumerate(a["properties"]):
            value = p.get("value") if isinstance(p, dict) else None
            if not isinstance(p, dict) or not _given(p.get("name")) or not isinstance(value, str | bool | int | float):
                raise WriteToolError("every property needs a name and a string, number or boolean value")
            unit = unit_in(value)
            if unit:
                number = unit[0].replace(",", ".", 1)
                raise WriteToolError(
                    f"property {i + 1}: give the number only, without its unit ({number}): IFC gives the property "
                    "its unit"
                )
            properties[_slice(_string(p["name"]), 200)] = _slice(value, 1000) if isinstance(value, str) else value
        return {"tool": name, "ids": _id_list(cs, a.get("ids")), "pset": pset, "properties": _in_js_order(properties)}
    if name == "set_classification":
        system = _text(a, "system", required=True)
        class_name = _text(a, "name", required=True)
        classified = {
            "tool": name,
            "ids": _id_list(cs, a.get("ids")),
            "system": system,
            "code": _text(a, "code"),
            "name": class_name,
            "uri": _text(a, "uri"),
        }
        for key in ("edition", "source", "dictionary_uri"):  # the system's facts, when given
            value = _text(a, key)
            if value:
                classified[key] = value
        return classified
    if name == "assign":
        storey = _text(a, "storey")
        material = _text(a, "material")
        if not storey and not material:
            raise WriteToolError("give a storey, a material or both")
        assigned = {"tool": name, "ids": _id_list(cs, a.get("ids")), "storey": storey, "material": material}
        if _given(a.get("category")):
            category = _trim(_string(a["category"])).lower()
            if not material:
                raise WriteToolError("category goes with a material")
            if category not in MATERIAL_CATEGORIES:
                raise WriteToolError(f"category must be {', '.join(MATERIAL_CATEGORIES)} or null")
            assigned["category"] = category  # IfcMaterial.Category
        return assigned
    if name == "edit_element":
        return _edit_op(cs, a)
    if name == "transform_elements":
        op = {
            "tool": name,
            "ids": _id_list(cs, a.get("ids")),
            "dx": _number(a, "dx", fallback=0),
            "dy": _number(a, "dy", fallback=0),
            "dz": _number(a, "dz", fallback=0),
        }
        if not op["dx"] and not op["dy"] and not op["dz"]:
            raise WriteToolError("nothing to move: dx, dy and dz are all zero")
        return op
    if name == "delete_elements":
        if a.get("confirm") is not True:
            raise WriteToolError(
                "deleting needs confirm: true, and only when the person asked for it in this conversation"
            )
        return {"tool": name, "ids": _id_list(cs, a.get("ids")), "confirm": True}
    if name == "set_site":
        latitude = _number(a, "latitude", required=True, unit="degrees")
        longitude = _number(a, "longitude", required=True, unit="degrees")
        if latitude < -90 or latitude > 90:
            raise WriteToolError("latitude must be between -90 and 90 degrees")
        if longitude < -180 or longitude > 180:
            raise WriteToolError("longitude must be between -180 and 180 degrees")
        crs = _text(a, "crs")
        eastings = _number(a, "eastings")
        northings = _number(a, "northings")
        if crs:
            if not _EPSG.fullmatch(crs):
                raise WriteToolError("crs must be an EPSG code such as EPSG:3006")
            if eastings is None or northings is None:
                raise WriteToolError("eastings and northings (metres) are required with crs")
        elif eastings is not None or northings is not None:
            raise WriteToolError("eastings and northings need a crs such as EPSG:3006")
        return _vertical_datum(
            a,
            crs,
            {
                "tool": name,
                "latitude": latitude,
                "longitude": longitude,
                "elevation": _number(a, "elevation"),
                "crs": crs.upper() if crs else None,
                "eastings": eastings,
                "northings": northings,
                "rotation": _number(a, "rotation", fallback=0, unit="degrees"),
                "site_name": _text(a, "site_name"),
            },
        )
    raise WriteToolError(f"unknown tool {name}")


def call(cs: dict[str, Any], name: str, args: dict[str, Any] | None) -> dict[str, Any]:
    """Run one write tool against a change set ``{"ops": [...], "refs": n}``: the operation is checked and appended,
    never applied. Errors are answers, so the model can mend the call."""
    if not cs:
        return {"error": "no change set is open"}
    if name == "manage_changeset":
        action = _string(args["action"]) if args and _truthy(args.get("action")) else "list"
        if action == "clear":
            cs["ops"] = []
            cs["refs"] = 0
            return {"ok": True, "steps": 0}
        if action == "remove_last":
            last = cs["ops"].pop() if cs["ops"] else None
            if last:
                cs["refs"] -= len(last["refs"]) if last.get("refs") is not None else 1 if last.get("ref") else 0
            return {"ok": True, "removed": describe(last) if last else None, "steps": len(cs["ops"])}
        if action != "list":
            return {"error": "action must be list, remove_last or clear"}
        return {
            "steps": [
                {
                    "step": i + 1,
                    "tool": op["tool"],
                    "ref": op.get("ref") or (", ".join(op["refs"]) if op.get("refs") else None),
                    "description": describe(op),
                }
                for i, op in enumerate(cs["ops"])
            ]
        }
    if not has(name):
        return {"error": f"unknown tool {name}"}
    if len(cs["ops"]) >= MAX_OPS:
        return {"error": f"the change set holds {MAX_OPS} steps already; ask the person to approve it first"}
    try:
        op = build(cs, name, args)
    except WriteToolError as exc:
        return {"error": str(exc)}
    # create_spaces gets a ref per listed room, in their order, as the wheel numbers them; the other creates one each.
    if name == "create_spaces":
        op["refs"] = []
        for _room in op["rooms"] or []:
            cs["refs"] += 1
            op["refs"].append(f"new-{cs['refs']}")
    elif name in CREATES:
        cs["refs"] += 1
        op["ref"] = f"new-{cs['refs']}"
    cs["ops"].append(op)
    out: dict[str, Any] = {"ok": True, "step": len(cs["ops"]), "description": describe(op)}
    if op.get("ref"):
        out["ref"] = op["ref"]
    if op.get("refs"):
        out["refs"] = op["refs"]
    if op["tool"] == "create_roof" and op["outline"] and not _rectangular(op["outline"]):
        b = _bounds(op["outline"])
        out["note"] = (
            f"the outline is not a rectangle along x and y ({len(op['outline'])} corners), so for now the roof covers "
            f"its bounding box: {_fmt(b[2] - b[0])} × {_fmt(b[3] - b[1])} m from ({_fmt(b[0])}, {_fmt(b[1])})"
        )
    advice = _own_set_advice(op) if op["tool"] == "set_properties" else None
    if advice:
        out["note"] = advice
    return out


# -- describe() with the English lines of the app's catalogue ------------------------------------------------------

_TEXTS = {
    "ai.change.storey.lowest": "the lowest storey",
    "ai.change.create_storeys_and_grid": "Storeys: {storeys}{grid}",
    "ai.change.grid": "; grid of {nx}×{ny} bays of {x}×{y} m",
    "ai.change.create_wall": "{ref} Wall {name} on {storey} from ({x1}, {y1}) to ({x2}, {y2}), {thickness} m thick, "
    "{height} m high",
    "ai.change.wall.partition": ", a non-load-bearing interior wall",
    "ai.change.create_slab": "{ref} Slab {name} on {storey}, {thickness} m thick{outline}",
    "ai.change.outline.grid": ", following the grid",
    "ai.change.outline.points": ", {n} corners",
    "ai.change.create_opening": "{ref} {fill} {name} in wall {wall}, {width}×{height} m, {offset} m from the wall's "
    "start",
    "ai.change.fill.door": "Door",
    "ai.change.fill.window": "Window",
    "ai.change.fill.none": "Opening",
    "ai.change.set_properties": "{pset} on {ids}: {props}",
    "ai.change.set_classification": "Classify {ids} in {system}: {cls}",
    "ai.change.assign": "Assign {ids}{storey}{material}",
    "ai.change.assign.storey": " to storey {storey}",
    "ai.change.assign.material": " the material {material}",
    "ai.change.transform_elements": "Move {ids} by ({dx}, {dy}, {dz}) m",
    "ai.change.delete_elements": "Delete {ids}",
    "ai.change.set_site": "Site{name}: {lat}, {lon}{elevation}{crs}",
    "ai.change.set_site.elevation": ", height {elevation} m",
    "ai.change.set_site.crs": ", {crs} E {eastings} N {northings}",
    "ai.change.set_site.rotation": ", rotated {rotation}°",
    "ai.change.create_roof": "{ref} Roof{name} on {storey}: {shape}{pitch} {extent}{overhang}",
    "ai.change.roof.gable": "gable roof",
    "ai.change.roof.hip": "hip roof",
    "ai.change.roof.shed": "shed roof",
    "ai.change.roof.flat": "flat roof",
    "ai.change.roof.size": "over {x} × {y} m",
    "ai.change.roof.walls": "over the walls",
    "ai.change.roof.overhang": ", overhang {overhang} m",
    "ai.change.storey.top": "the top storey",
    "ai.change.create_spaces": "{ref} Rooms on {storey}: {rooms}{height}",
    "ai.change.spaces.at": "{name} at ({x}, {y})",
    "ai.change.spaces.index": "{name} (room {index})",
    "ai.change.spaces.all": "every room the walls enclose, named {names} …",
    "ai.change.spaces.every": "every storey with rooms",
    "ai.change.spaces.height": ", {height} m high",
    "ai.change.spaces.name": "Room {n}",
    "ai.change.bearing.true": ", load-bearing",
    "ai.change.bearing.false": ", not load-bearing",
    "ai.change.status.new": ", new",
    "ai.change.status.existing": ", existing",
    "ai.change.status.demolish": ", to be demolished",
    "ai.change.status.temporary": ", temporary",
    "ai.change.define_type": "{ref} {kind} {name}{predefined}: {layers} ({thickness} m)",
    "ai.change.type.wall": "Wall type",
    "ai.change.type.slab": "Slab type",
    "ai.change.type.roof": "Roof type",
    "ai.change.typed": ", type {type}",
    "ai.change.type.covering": "Covering type",
    "ai.change.type.column": "Column type",
    "ai.change.type.beam": "Beam type",
    "ai.change.type.footing": "Footing type",
    "ai.change.type.railing": "Railing type",
    "ai.change.type.door": "Door type",
    "ai.change.type.window": "Window type",
    "ai.change.define_type.element": "{ref} {kind} {name}{predefined}",
    "ai.change.define_type.size": ": {operation}, {width}×{height} m",
    "ai.change.define_type.material": ", material {material}",
    "ai.change.side.right": ", facing the wall's right side",
    "ai.change.create_element": "{ref} {cls}{predefined}{name} on {storey}{at}: {body}",
    "ai.change.at": " at ({x}, {y})",
    "ai.change.storey.whole": "the whole's storey",
    "ai.change.shape.rectangle": "rectangle {x} × {y} m",
    "ai.change.shape.circle": "circle of radius {radius} m",
    "ai.change.shape.polygon": "outline of {n} corners",
    "ai.change.shape.up": ", {depth} m up",
    "ai.change.shape.along": ", {depth} m long in the direction {rotation}°",
    "ai.change.stair": "straight stair of {risers} risers, riser height {riser} m, tread length {tread} m, {width} m "
    "wide, rising in the direction {rotation}°",
    "ai.change.stair.landing": ", landing {landing} m",
    "ai.change.part_of": ", part of {whole}",
    "ai.change.host": ", covering {host}",
    "ai.change.edit_element": "Change {id}: {changes}",
    "ai.change.edit.name": "name {name}",
    "ai.change.edit.start": "start at {point}",
    "ai.change.edit.end": "end at {point}",
    "ai.change.edit.thickness": "thickness {value} m",
    "ai.change.edit.height": "height {value} m",
    "ai.change.edit.type": "type {type}",
    "ai.change.edit.outline": "outline of {n} corners",
    "ai.change.edit.offset": "{value} m from the wall's start",
    "ai.change.edit.width": "width {value} m",
    "ai.change.edit.sill": "sill {value} m",
    "ai.change.edit.pitch": "pitch {value}°",
    "ai.change.edit.overhang": "overhang {value} m",
    "ai.change.edit.base": "eaves height {value} m",
}


def _t(key: str, **params: Any) -> str:
    return _fill(_TEXTS.get(key, key), **params)


def _fmt(v: Any) -> str:
    if _finite(v):
        return _js_number(_round(_double(v) * 1000) / 1000)
    return "" if v is None else _string(v)


def _ids_text(ids: list[Any] | None) -> str:
    return ", ".join(_fmt(x) for x in ids or [])


def _thick(op: dict[str, Any]) -> str:
    """The thickness of a step, a dash when the wheel takes it from a type of the model."""
    return "–" if op.get("thickness") is None else _fmt(op["thickness"])


def _typed_text(op: dict[str, Any]) -> str:
    """ ", type new-1" after a typed wall, slab or roof."""
    return _t("ai.change.typed", type=_fmt(op["type"])) if op.get("type") is not None else ""


def _common_text(op: dict[str, Any]) -> str:
    """ ", load-bearing" and ", existing" after a step that gives them (a partition says it bears no load already)."""
    bearing = op.get("load_bearing")
    out = (
        _t("ai.change.bearing." + ("true" if bearing else "false"))
        if isinstance(bearing, bool) and not (op.get("partition") and not bearing)
        else ""
    )
    return out + (_t("ai.change.status." + _string(op["status"]).lower()) if op.get("status") else "")


def _edit_text(op: dict[str, Any]) -> str:
    """What an edit_element step changes, in the order of the tool's fields."""

    def at(p: list[Any]) -> str:
        return f"({_fmt(p[0])}, {_fmt(p[1])})"

    parts = []
    if op.get("name"):
        parts.append(_t("ai.change.edit.name", name=op["name"]))
    if op.get("start"):
        parts.append(_t("ai.change.edit.start", point=at(op["start"])))
    if op.get("end"):
        parts.append(_t("ai.change.edit.end", point=at(op["end"])))
    if "thickness" in op:
        parts.append(_t("ai.change.edit.thickness", value=_fmt(op["thickness"])))
    if "type" in op:
        parts.append(_t("ai.change.edit.type", type=_fmt(op["type"])))
    if op.get("outline"):
        parts.append(_t("ai.change.edit.outline", n=str(len(op["outline"]))))
    for key in ("offset", "width", "height", "sill", "pitch", "overhang", "base"):
        if key in op:
            parts.append(_t("ai.change.edit." + key, value=_fmt(op[key])))
    return ", ".join(parts)


def _describe_type(op: dict[str, Any]) -> str:
    base = {
        "ref": op.get("ref") or "",
        "kind": _t("ai.change.type." + op["kind"]),
        "name": op["name"],
        "predefined": " " + op["predefined_type"] if op.get("predefined_type") else "",
    }
    if not op.get("layers"):
        size = (
            _t(
                "ai.change.define_type.size",
                operation=op.get("operation") or op.get("partitioning"),
                width=_fmt(op["width"]),
                height=_fmt(op["height"]),
            )
            if op.get("width")
            else ""
        )
        material = _t("ai.change.define_type.material", material=op["material"]) if op.get("material") else ""
        return _t("ai.change.define_type.element", **base) + size + material
    layers = ", ".join(f"{layer['material']} {_fmt(layer['thickness'])} m" for layer in op["layers"])
    return _t("ai.change.define_type", **base, layers=layers, thickness=_fmt(_layers_thickness(op["layers"])))


def _describe_element(op: dict[str, Any]) -> str:
    s: Any = op.get("shape")
    depth = _fmt(s["depth"]) if s and s.get("depth") is not None else "–"
    stair = op.get("stair")
    if stair:
        body = _t(
            "ai.change.stair",
            risers=_fmt(stair["risers"]),
            riser=_fmt(stair["riser_height"]),
            tread=_fmt(stair["tread_length"]),
            width=_fmt(stair["width"]),
            rotation=_fmt(op["rotation"]),
        ) + (_t("ai.change.stair.landing", landing=_fmt(stair["landing"])) if stair.get("landing") else "")
    else:
        body = _t(
            "ai.change.shape." + s["profile"],
            x=_fmt(s["x"]),
            y=_fmt(s["y"]),
            radius=_fmt(s["radius"]),
            n=str(len(s["outline"] or [])),
        ) + (
            _t("ai.change.shape.along", depth=depth, rotation=_fmt(op["rotation"]))
            if s["along"] == "x"
            else _t("ai.change.shape.up", depth=depth)
        )
    whole = _t("ai.change.storey.whole") if op.get("part_of") else _t("ai.change.storey.lowest")
    return (
        _t(
            "ai.change.create_element",
            ref=op.get("ref") or "",
            cls=op["ifc_class"],
            predefined=" " + op["predefined_type"] if op.get("predefined_type") else "",
            name=" " + op["name"] if op.get("name") else "",
            storey=op.get("storey") or whole,
            at=_t("ai.change.at", x=_fmt(op["at"][0]), y=_fmt(op["at"][1])) if op.get("at") else "",
            body=body,
        )
        + _typed_text(op)
        + (_t("ai.change.part_of", whole=_fmt(op["part_of"])) if op.get("part_of") else "")
        + (_t("ai.change.host", host=_fmt(op["host"])) if op.get("host") else "")
    )


def describe(op: dict[str, Any]) -> str:
    """One line about an operation, for the list and the answers."""
    tool = op.get("tool")
    if tool == "create_storeys_and_grid":
        storeys = (
            ", ".join(
                f"{s['name']}{' – ' + s['description'] if s.get('description') else ''} ({_fmt(s['elevation'])} m)"
                for s in op.get("storeys") or []
            )
            or "–"
        )
        g = op.get("grid")
        grid = (
            _t(
                "ai.change.grid",
                x=_fmt(g["x_spacing"]),
                y=_fmt(g["y_spacing"]),
                nx=_fmt(g["x_count"]),
                ny=_fmt(g["y_count"]),
            )
            if g
            else ""
        )
        return _t("ai.change.create_storeys_and_grid", storeys=storeys, grid=grid)
    if tool == "define_type":
        return _describe_type(op)
    if tool == "create_element":
        return _describe_element(op)
    if tool == "create_wall":
        return (
            _t(
                "ai.change.create_wall",
                ref=op.get("ref") or "",
                name=op.get("name") or "",
                storey=op.get("storey") or _t("ai.change.storey.lowest"),
                x1=_fmt(op["start"][0]),
                y1=_fmt(op["start"][1]),
                x2=_fmt(op["end"][0]),
                y2=_fmt(op["end"][1]),
                thickness=_thick(op),
                height=_fmt(op["height"]),
            )
            + _typed_text(op)
            + (_t("ai.change.wall.partition") if op.get("partition") else "")
            + _common_text(op)
        )
    if tool == "create_slab":
        outline = op.get("outline")
        return (
            _t(
                "ai.change.create_slab",
                ref=op.get("ref") or "",
                name=op.get("name") or "",
                storey=op.get("storey") or _t("ai.change.storey.lowest"),
                thickness=_thick(op),
                outline=_t("ai.change.outline.points", n=str(len(outline)))
                if outline
                else _t("ai.change.outline.grid"),
            )
            + _typed_text(op)
            + _common_text(op)
        )
    if tool == "create_roof":
        b = _bounds(op["outline"]) if op.get("outline") else None
        return (
            _t(
                "ai.change.create_roof",
                ref=op.get("ref") or "",
                name=" " + op["name"] if op.get("name") else "",
                storey=op.get("storey") or _t("ai.change.storey.top"),
                shape=_t("ai.change.roof." + op["shape"]),
                pitch="" if op["shape"] == "flat" else f" {_fmt(op['pitch'])}°",
                extent=_t("ai.change.roof.size", x=_fmt(b[2] - b[0]), y=_fmt(b[3] - b[1]))
                if b
                else _t("ai.change.roof.walls"),
                overhang=_t("ai.change.roof.overhang", overhang=_fmt(op["overhang"])) if op.get("overhang") else "",
            )
            + _typed_text(op)
            + _common_text(op)
        )
    if tool == "create_opening":
        return (
            _t(
                "ai.change.create_opening",
                ref=op.get("ref") or "",
                fill=_t("ai.change.fill." + (op.get("fill") or "none")),
                name=op.get("name") or "",
                wall=_fmt(op["wall_id"]),
                width="–" if op["width"] is None else _fmt(op["width"]),
                height="–" if op["height"] is None else _fmt(op["height"]),
                offset=_fmt(op["offset"]),
            )
            + _typed_text(op)
            + (_t("ai.change.side.right") if op.get("side") == "right" else "")
        )
    if tool == "create_spaces":
        if op.get("rooms"):

            def named(r: dict[str, Any]) -> str:
                return f"{r['number']} {r['name']}" if r.get("number") else r["name"]

            rooms = ", ".join(
                _t("ai.change.spaces.at", name=named(r), x=_fmt(r["at"][0]), y=_fmt(r["at"][1]))
                if r.get("at")
                else _t("ai.change.spaces.index", name=named(r), index=_fmt(r["index"]))
                for r in op["rooms"]
            )
        else:
            names = ", ".join(_t("ai.change.spaces.name", n=n) for n in (1, 2))
            rooms = _t("ai.change.spaces.all", names=names)
        refs = op.get("refs") or []
        return _t(
            "ai.change.create_spaces",
            ref=f"{refs[0]}–{refs[-1]}" if len(refs) > 1 else refs[0] if refs else "",
            storey=op.get("storey") or _t("ai.change.spaces.every"),
            rooms=rooms,
            height=_t("ai.change.spaces.height", height=_fmt(op["height"])) if op.get("height") else "",
        )
    if tool == "set_properties":
        props = ", ".join(f"{k} = {_fmt(v)}" for k, v in (op.get("properties") or {}).items())
        return _t("ai.change.set_properties", pset=op["pset"], ids=_ids_text(op.get("ids")), props=props)
    if tool == "set_classification":
        cls = " ".join(value for value in (op.get("code"), op.get("name")) if value)
        system = " ".join(value for value in (op.get("system"), op.get("edition")) if value)
        return _t("ai.change.set_classification", ids=_ids_text(op.get("ids")), system=system, cls=cls)
    if tool == "assign":
        return _t(
            "ai.change.assign",
            ids=_ids_text(op.get("ids")),
            storey=_t("ai.change.assign.storey", storey=op["storey"]) if op.get("storey") else "",
            material=_t(
                "ai.change.assign.material",
                material=f"{op['material']} ({op['category']})" if op.get("category") else op["material"],
            )
            if op.get("material")
            else "",
        )
    if tool == "edit_element":
        return _t("ai.change.edit_element", id=_fmt(op["id"]), changes=_edit_text(op))
    if tool == "transform_elements":
        return _t(
            "ai.change.transform_elements",
            ids=_ids_text(op.get("ids")),
            dx=_fmt(op["dx"]),
            dy=_fmt(op["dy"]),
            dz=_fmt(op["dz"]),
        )
    if tool == "delete_elements":
        return _t("ai.change.delete_elements", ids=_ids_text(op.get("ids")))
    if tool == "set_site":

        def deg(v: float) -> str:
            return _js_number(_round(v * 1e6) / 1e6)

        crs = ""
        if op.get("crs"):
            crs = _t(
                "ai.change.set_site.crs",
                crs=f"{op['crs']} + {op['vertical_datum']}" if op.get("vertical_datum") else op["crs"],
                eastings=_fmt(op["eastings"]),
                northings=_fmt(op["northings"]),
            )
            crs += _t("ai.change.set_site.rotation", rotation=_fmt(op["rotation"])) if op.get("rotation") else ""
        return _t(
            "ai.change.set_site",
            name=" " + op["site_name"] if op.get("site_name") else "",
            lat=deg(op["latitude"]),
            lon=deg(op["longitude"]),
            elevation=""
            if op.get("elevation") is None
            else _t("ai.change.set_site.elevation", elevation=_fmt(op["elevation"])),
            crs=crs,
        )
    if tool == CHANGE_ATTRIBUTE:
        change = op["change"]
        where = (
            f"{change['guid']}" + (f"/{change['path']}" if change.get("path") else "")
            if change.get("guid")
            else f"#{change['step_id']}"
        )
        return f"{change['op'].capitalize()} {change['attribute']} of {where}"
    return _string(tool)


def to_wheel(ops: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The operations as the wheel reads them: without the refs the list shows, and without the server's steps on
    ``changes``."""
    return [
        {key: value for key, value in op.items() if key not in ("ref", "refs")}
        for op in ops
        if op["tool"] != CHANGE_ATTRIBUTE
    ]


def changes(ops: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The posts in ``changes`` that the steps ``change_attribute`` made, in their order."""
    return [dict(op["change"]) for op in ops if op["tool"] == CHANGE_ATTRIBUTE]
