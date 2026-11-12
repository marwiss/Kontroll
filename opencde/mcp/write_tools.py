# This file was generated with the assistance of an AI coding tool.
"""Dataspatium's write tools as the MCP endpoint offers them (ADR 0028, the design's §2): a copy, kept in step by hand.

A copy of ``src/ai/write-tools.js`` (Dataspatium, branch f43, commit 64e116e of 2026-11-12): the tools' schemas and
descriptions (``TOOLS``), ``build()`` with its checks, which turns one call into one operation in the form
``dataspatium-tools/1`` (the defaults filled in, the numbers checked, the texts cut at 200 characters), ``call()``,
which appends the operation to the open change set with the refs counted as the app counts them (``new-1``,
``new-2`` … in the order of ``create_wall``, ``create_slab``, ``create_roof``, ``create_opening`` and the rooms that
``create_spaces`` lists) and runs ``manage_changeset``, ``describe()`` with the English lines of the app's catalogue
(``src/ui/i18n/en.js``, the keys ``ai.change.*``), and ``toWheel``, which leaves the refs out, since the code that
applies the operations (``ifcgraph/ops.py``) counts them itself. An id is an element's GlobalId, its STEP id or a ref
(F34 a). The server keeps the change set as a draft (``store/jobs/drafts.py``), whose ``ops`` are this module's.

Against the original only this differs, so that the next copy is a diff away:

- JavaScript's semantics are spelled out where Python's differ: ``String()`` of a number (:func:`_js_number`),
  ``Math.round`` (:func:`_round`), ``slice`` in UTF-16 code units (:func:`_slice`, where a pair cut in half is
  dropped), and the regular expressions in ASCII and anchored at the very end;
- the person's language is the catalogue's English: the name ``create_spaces`` gives the rooms it names itself is
  ``Room {n}``, and the descriptions are the English lines;
- the server's own step ``change_attribute`` (a post in the change set's ``changes``) lives in ``cs["ops"]`` beside
  the operations, so that ``manage_changeset`` lists and removes it in its order; :func:`describe` describes it, and
  :func:`to_wheel` and :func:`changes` part the two;
- two descriptions and one message name tools the server does not have: ``set_classification`` says nothing of
  ``search_ifc_class`` and ``search_bsdd`` (a bSDD class's dictionary is still the system), and ``create_spaces`` names
  a room's index as a report's rooms give it instead of ``get_topology``;
- a room of ``create_spaces`` that is a list is no object here, where JavaScript finds the lists' own ``at``; the
  schema lets no such room through;
- ``call()`` answers an error as the app does, ``{"error": …}``, which the endpoint makes a tool error.
"""

from __future__ import annotations

import math
import re
from decimal import Decimal
from typing import Any

MAX_OPS = 200
MAX_IDS = 500
CREATES = ("create_wall", "create_slab", "create_roof", "create_opening", "create_spaces")
ROOF_SHAPES = ("gable", "hip", "shed", "flat")
MAX_ROOMS = 200
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


#: The tools as the providers see them: name, description and the properties of the parameters, in the app's order.
TOOLS: tuple[dict[str, Any], ...] = (
    {
        "name": "create_storeys_and_grid",
        "description": "Add building storeys (name and elevation in metres above the first) and/or a grid to the "
        "change set. The grid has x_count bays of x_spacing metres along X (axes A, B, …) and y_count bays of "
        "y_spacing along Y (axes 1, 2, …), with A1 at (0, 0). A storey that already exists is kept. Either may be "
        "null.",
        "properties": {
            "storeys": {
                "type": ["array", "null"],
                "items": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}, "elevation": {"type": "number"}},
                    "required": ["name", "elevation"],
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
        "name": "create_wall",
        "description": "Add a wall on a storey (null: the lowest) from start [x, y] to end [x, y] in metres in the "
        "storey's plane, with its thickness centred on that line and its height from the storey. Defaults: "
        "thickness 0.2, height 3. partition true makes a non-load-bearing interior wall (PredefinedType "
        "PARTITIONING); otherwise the wall is SOLIDWALL. Answers the ref of the wall.",
        "properties": {
            "storey": _str(),
            "start": _xy(),
            "end": _xy(),
            "thickness": _num(),
            "height": _num(),
            "name": _str(),
            "partition": _bool(),
        },
    },
    {
        "name": "create_slab",
        "description": "Add a floor slab on a storey, with its top at the storey's elevation. outline is a list of "
        "[x, y] corners in metres, or null to follow the grid's extent. Default thickness 0.25. Answers the ref of "
        "the slab.",
        "properties": {"storey": _str(), "outline": _outline(), "thickness": _num(), "name": _str()},
    },
    {
        "name": "create_roof",
        "description": "Add a roof on the walls of a storey (null: the top storey), as an IfcRoof of roof slabs: "
        "shape is gable, hip, shed or flat. outline is the [x, y] corners in metres of the rectangle it covers, or "
        "null for the bounding box of the storey's walls; an outline that is not a rectangle along x and y is "
        "replaced by its bounding box for now. pitch is degrees, more than 0 and at most 75 (defaults: 30 for gable "
        "and hip, 10 for shed; flat ignores it). overhang is metres beyond the outline at the eaves (default 0.4, "
        "for flat 0), thickness metres (default 0.25). ridge is x or y: for gable the direction of the ridge (null: "
        "along the longer side), for shed the axis it falls along, down toward negative x or y (null: y, so to the "
        "south when y points north); hip and flat ignore it. base is the eaves height in metres above the storey "
        "(null: the top of the storey's walls, else 2.7). Answers the ref of the roof.",
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
        },
    },
    {
        "name": "create_opening",
        "description": "Cut an opening in a wall (wall_id: its id or ref), offset metres from the wall's start, width "
        "by height metres, sill metres above the storey, and fill it with a door or a window (fill: door, window or "
        "null). Defaults: width 0.9, height 2.1, sill 0. Answers the ref of the door or window, or of the opening.",
        "properties": {
            "wall_id": {"type": ["integer", "string"]},
            "offset": _num(),
            "width": _num(),
            "height": _num(),
            "sill": _num(),
            "fill": _str(),
            "name": _str(),
        },
    },
    {
        "name": "create_spaces",
        "description": "Create the rooms the walls enclose as spaces (IfcSpace), from the topology of the model as "
        "it stands at this step, so that walls created earlier in the change set count. Each space gets the room's "
        "outline extruded to its height, is aggregated in its storey, gets Qto_SpaceBaseQuantities, and gets space "
        "boundaries to the walls along its edge and to the doors and windows in them (a door created later in such "
        "a wall joins them). storey is the storey's name; null makes every room on every storey with rooms, and "
        "then rooms must be null. rooms lists the rooms: each by at, an [x, y] point inside it in metres in the "
        "storey's plane, or by index, its index among the storey's rooms in a report (the other null), with name "
        "from the room programme (such as Kitchen) and long_name or null; null makes every room, named Room 1, "
        "Room 2 … in the person's language. A room that a space covers already is left out. height is metres "
        "(null: up to the next storey, or the walls' height on the top storey). Answers one ref per listed room, "
        "in order; with rooms null the spaces get no refs.",
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
                    },
                    "required": ["at", "index", "name", "long_name"],
                    "additionalProperties": False,
                },
            },
            "height": _num(),
        },
    },
    {
        "name": "set_properties",
        "description": "Set properties in one property set (pset, such as Pset_WallCommon) on elements (ids: ids or "
        "refs): properties is a list of {name, value} with string, number or boolean values. Missing sets are "
        "created.",
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
        "system on top. system is that system's name, name the class name, code its code and uri its address (for "
        "a bSDD class its uri). Written as an IfcClassificationReference under the system's IfcClassification, "
        "shared only when the system, the code and the uri match. edition, source and dictionary_uri describe the "
        "system (its edition, its publisher and the dictionary's address) and are written on its IfcClassification; "
        "the same system with another edition or dictionary_uri is another IfcClassification. For a class in a bSDD "
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
        "created when missing). Either may be null.",
        "properties": {"ids": _ids(), "storey": _str(), "material": _str()},
    },
    {
        "name": "transform_elements",
        "description": "Move elements (ids or refs) by dx, dy, dz metres.",
        "properties": {"ids": _ids(), "dx": _num(), "dy": _num(), "dz": _num()},
    },
    {
        "name": "delete_elements",
        "description": "Delete elements (ids or refs) with what depends on them. Only when the person asked for it "
        "in this conversation; confirm must be true to say so, and the person confirms again before approval.",
        "properties": {"ids": _ids(), "confirm": {"type": ["boolean", "null"]}},
    },
    {
        "name": "set_site",
        "description": "Set the model's place on earth: the site's latitude and longitude in WGS 84 degrees (south "
        "and west negative), its elevation in metres above sea level, and, when the model is drawn in a projected "
        "coordinate system, the map conversion: crs is the EPSG code (such as EPSG:3006 for SWEREF 99 TM), eastings "
        "and northings the coordinates of the model's origin in metres, and rotation the angle in degrees from grid "
        "east (the map's x axis, along the eastings) to the model's X axis, counter-clockwise positive, as "
        "IfcMapConversion measures it (0 when null: the model's X axis points east and its Y axis north). crs, "
        "eastings and northings go together; site_name renames the site. One call per model is enough: a second "
        "call replaces the first.",
        "properties": {
            "latitude": {"type": "number"},
            "longitude": {"type": "number"},
            "elevation": _num(),
            "crs": _str(),
            "eastings": _num(),
            "northings": _num(),
            "rotation": _num(),
            "site_name": _str(),
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
                {
                    "name": _slice(_string(s["name"]), 200),
                    "elevation": s.get("elevation") if _finite(s.get("elevation")) else 0,
                }
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
    if name == "create_wall":
        start = _point(a.get("start"), "start")
        end = _point(a.get("end"), "end")
        if math.hypot(end[0] - start[0], end[1] - start[1]) < 0.01:
            raise WriteToolError("start and end are the same point")
        wall = {
            "tool": name,
            "storey": _text(a, "storey"),
            "start": start,
            "end": end,
            "thickness": _number(a, "thickness", fallback=0.2, positive=True),
            "height": _number(a, "height", fallback=3, positive=True),
            "name": _text(a, "name"),
        }
        if a.get("partition") is True:
            wall["partition"] = True  # PARTITIONING in the wheel; SOLIDWALL otherwise
        return wall
    if name == "create_slab":
        outline = _outline_of(a)
        if _given(a.get("outline")) and (not outline or len(outline) < 3):
            raise WriteToolError("outline must be at least three [x, y] points, or null for the grid's extent")
        return {
            "tool": name,
            "storey": _text(a, "storey"),
            "outline": outline,
            "thickness": _number(a, "thickness", fallback=0.25, positive=True),
            "name": _text(a, "name"),
        }
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
        return {
            "tool": name,
            "storey": _text(a, "storey"),
            "shape": shape,
            "outline": outline,
            "pitch": pitch,
            "overhang": overhang,
            "thickness": _number(a, "thickness", fallback=0.25, positive=True),
            "ridge": ridge if shape in ("gable", "shed") else None,
            "base": _number(a, "base"),
            "name": _text(a, "name"),
        }
    if name == "create_opening":
        fill = _string(a["fill"]).lower() if _given(a.get("fill")) else None
        if fill and fill not in ("door", "window"):
            raise WriteToolError("fill must be door, window or null")
        if not _given(a.get("wall_id")):
            raise WriteToolError("wall_id is required")
        return {
            "tool": name,
            "wall_id": _id_or_ref(cs, a["wall_id"], "wall_id"),
            "offset": _number(a, "offset", fallback=0),
            "width": _number(a, "width", fallback=0.9, positive=True),
            "height": _number(a, "height", fallback=2.1, positive=True),
            "sill": _number(a, "sill", fallback=0),
            "fill": fill,
            "name": _text(a, "name"),
        }
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
                    {
                        "at": _point(r["at"], f"{which}: at") if _given(r.get("at")) else None,
                        "index": r["index"] if _given(r.get("index")) else None,
                        "name": _slice(_string(r["name"]), 200),
                        "long_name": _text(r, "long_name"),
                    }
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
        pset = _text(a, "pset", required=True)
        if not isinstance(a.get("properties"), list) or not a["properties"]:
            raise WriteToolError("properties must be a list of {name, value}")
        properties: dict[str, Any] = {}
        for p in a["properties"]:
            value = p.get("value") if isinstance(p, dict) else None
            if not isinstance(p, dict) or not _given(p.get("name")) or not isinstance(value, str | bool | int | float):
                raise WriteToolError("every property needs a name and a string, number or boolean value")
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
        return {"tool": name, "ids": _id_list(cs, a.get("ids")), "storey": storey, "material": material}
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
        return {
            "tool": name,
            "latitude": latitude,
            "longitude": longitude,
            "elevation": _number(a, "elevation"),
            "crs": crs.upper() if crs else None,
            "eastings": eastings,
            "northings": northings,
            "rotation": _number(a, "rotation", fallback=0, unit="degrees"),
            "site_name": _text(a, "site_name"),
        }
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
}


def _t(key: str, **params: Any) -> str:
    return _fill(_TEXTS.get(key, key), **params)


def _fmt(v: Any) -> str:
    if _finite(v):
        return _js_number(_round(_double(v) * 1000) / 1000)
    return "" if v is None else _string(v)


def _ids_text(ids: list[Any] | None) -> str:
    return ", ".join(_fmt(x) for x in ids or [])


def describe(op: dict[str, Any]) -> str:
    """One line about an operation, for the list and the answers."""
    tool = op.get("tool")
    if tool == "create_storeys_and_grid":
        storeys = ", ".join(f"{s['name']} ({_fmt(s['elevation'])} m)" for s in op.get("storeys") or []) or "–"
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
    if tool == "create_wall":
        return _t(
            "ai.change.create_wall",
            ref=op.get("ref") or "",
            name=op.get("name") or "",
            storey=op.get("storey") or _t("ai.change.storey.lowest"),
            x1=_fmt(op["start"][0]),
            y1=_fmt(op["start"][1]),
            x2=_fmt(op["end"][0]),
            y2=_fmt(op["end"][1]),
            thickness=_fmt(op["thickness"]),
            height=_fmt(op["height"]),
        ) + (_t("ai.change.wall.partition") if op.get("partition") else "")
    if tool == "create_slab":
        outline = op.get("outline")
        return _t(
            "ai.change.create_slab",
            ref=op.get("ref") or "",
            name=op.get("name") or "",
            storey=op.get("storey") or _t("ai.change.storey.lowest"),
            thickness=_fmt(op["thickness"]),
            outline=_t("ai.change.outline.points", n=str(len(outline))) if outline else _t("ai.change.outline.grid"),
        )
    if tool == "create_roof":
        b = _bounds(op["outline"]) if op.get("outline") else None
        return _t(
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
    if tool == "create_opening":
        return _t(
            "ai.change.create_opening",
            ref=op.get("ref") or "",
            fill=_t("ai.change.fill." + (op.get("fill") or "none")),
            name=op.get("name") or "",
            wall=_fmt(op["wall_id"]),
            width=_fmt(op["width"]),
            height=_fmt(op["height"]),
            offset=_fmt(op["offset"]),
        )
    if tool == "create_spaces":
        if op.get("rooms"):
            rooms = ", ".join(
                _t("ai.change.spaces.at", name=r["name"], x=_fmt(r["at"][0]), y=_fmt(r["at"][1]))
                if r.get("at")
                else _t("ai.change.spaces.index", name=r["name"], index=_fmt(r["index"]))
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
            material=_t("ai.change.assign.material", material=op["material"]) if op.get("material") else "",
        )
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
                "ai.change.set_site.crs", crs=op["crs"], eastings=_fmt(op["eastings"]), northings=_fmt(op["northings"])
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
