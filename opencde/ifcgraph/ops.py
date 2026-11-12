# This file was generated with the assistance of an AI coding tool.
"""Dataspatium's write tools on an IFC model and its topology of the walls, with Dataspatium's own code (ADR 0021).

A copy of Dataspatium's class ``_ChangeSet`` and of its topology (``_ifc_topology``), with the module-level helpers
they call (``python/dataspatium.py``, branch f43, commit 64e116e of 2026-11-12), kept in step by hand, so that one
list of operations gives the same model in the app and on the server, and the server finds the rooms the app finds.
A change set that carries the operations as ``ops`` (``documents/changes.py``) is tried by the apply worker
(``apply.py``), which runs them with :func:`run` on the base version's file before its changes; the topology worker
(``topology.py``) finds the rooms of a file (the owner's decision F36 a: the server makes the client's room check).
The operations are the AI's write tools in the app: ``create_storeys_and_grid``, ``create_wall``, ``create_slab``,
``create_roof``, ``create_opening``, ``create_spaces``, ``set_properties``, ``set_classification``, ``assign``,
``transform_elements``, ``delete_elements`` and ``set_site``, each a JSON object with its tool's name as ``tool`` and
its arguments beside it. Lengths are metres, scaled to the file's unit. A wall, a slab, a roof or an opening (or the
door or window that fills it) gets the ref ``new-1``, ``new-2`` … in the order of the operations that create them
(``_ChangeSet.CREATES``), and so does each room that ``create_spaces`` lists, in its order; the spaces of ``rooms``
null get none. An operation names an element by its GlobalId, by its STEP id only where no GlobalId reaches it, or by
such a ref (the owner's decision F34 a, elements named by GlobalId, which the app's copy has too), and a storey by its
name. ``create_wall`` gives a wall its centre line as an ``Axis`` representation, which the topology reads, and
``create_spaces`` makes the rooms of the topology spaces (F37 a: rooms become IfcSpace through a proposal), each with
its quantities and its boundaries to the walls, doors and windows along its edge; a door or window made later in a
wall that bounds a space bounds it too. Every class and enumeration value an operation sets is checked against the
file's schema (the app's decision B-57.2, the right IFC class), and a value the release deprecates is never written
(bSI rule IFC102): a wall is ``SOLIDWALL``, or ``PARTITIONING`` with ``partition``; in IFC4X3 a storey has its
height in its placement alone and a room is ``SPACE`` with ``Pset_SpaceCommon.IsExternal`` false. The change set's
geometry is raw entities: only the topology builds a body, with ``ifcopenshell.geom``, for a wall without an
``Axis``. Nothing depends on Pyodide.

Against the original only this differs, so that the next copy is a diff away:

- the imports: ``math`` and ``sys``, which the original imports at the top of its module, are imported here;
- the error class: ``DataspatiumError`` keeps its name and its base, with a docstring of its own;
- ``_ChangeSet.MAX_PROPOSAL`` and ``_ChangeSet.proposal`` are left out: they lower the operations to attribute-level
  changes with the app's ``_Proposal``, which is not copied, since the server applies the operations themselves;
- of the original's part on the right IFC class only what ``_ChangeSet`` calls is copied (``DEPRECATED_VALUES``,
  ``_ifc_schema``, ``_ifc_declaration``, ``_ifc_enum_items``, ``_ifc_concrete`` and ``IFC_NEW_SCHEMAS``, which the
  original keeps further down): not its read tools ``_ifc_class_search`` and ``_ifc_class_report`` with their
  helpers;
- the owner settings: :class:`ServerChangeSet`, below the copy, overrides ``owner_settings``, so that the owner
  histories IfcOpenShell's API makes name the proposer and this server instead of the file's own owner;
- ``_ifc_topology`` also gives each storey the GlobalIds of the walls it could not read (``unread_walls``), and
  ``_topo_plan`` those of the walls with an open end (``dangling``), for the report's rooms, which name elements by
  GlobalId; the lines that do so are marked ``# Dataregium``;
- ruff formats the copy in lines of 120 characters and lets its idioms be (``pyproject.toml``), and ten comments quiet
  bandit (``# nosec B110`` and ``B112``, seven) and ty (``# ty: ignore``, three); no other statement changed.
"""

from __future__ import annotations

import math
import re
import sys
from typing import Any

from opencde import __version__


class DataspatiumError(Exception):
    """An operation that cannot be applied, in the words of Dataspatium's code (in the app, the app's language)."""


def _is_na(v):
    if v is None:
        return True
    try:
        if v is getattr(sys.modules.get("pandas"), "NA", object()) or v is getattr(
            sys.modules.get("pandas"), "NaT", object()
        ):
            return True
    except Exception:  # nosec B110
        pass
    return isinstance(v, float) and math.isnan(v)


def _ifc_text(v):
    return None if v is None else str(v)


def _ifc_value(v):
    if _is_na(v):
        return None
    if hasattr(v, "item") and not isinstance(v, (str, bytes)):
        try:
            v = v.item()
        except Exception:  # nosec B110
            pass
    if isinstance(v, bool) or v is None:
        return v
    if isinstance(v, int):
        return int(v)
    if isinstance(v, float):
        return float(v)
    return str(v)


# ---- the change set of "Ändra med AI" ---------------------------------------------------------
# The AI's write tools never touch the model themselves: they fill a change set (a JSON list of operations) that the person
# previews and approves in the app; only then does _ifc_changeset() apply it, as a recipe step with undo. Lengths are metres and
# are scaled to the file's unit. A created element gets a ref ("new-1", "new-2", ...) in the order of the operations
# create_wall, create_slab, create_roof and create_opening, so that a later operation can name it before the file has given it an id.


def _cs_num(op, key, default=None, positive=False, unit="metres"):
    v = op.get(key)
    if v is None:
        if default is None:
            raise DataspatiumError("%s is required (%s)" % (key, unit))
        v = default
    try:
        v = float(v)
    except (TypeError, ValueError):
        raise DataspatiumError("%s must be a number (%s)" % (key, unit))
    if positive and v <= 0:
        raise DataspatiumError("%s must be greater than zero" % key)
    return v


def _cs_xy(value, key):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise DataspatiumError("%s must be [x, y] in metres" % key)
    try:
        return float(value[0]), float(value[1])
    except (TypeError, ValueError):
        raise DataspatiumError("%s must be [x, y] in metres" % key)


def _cs_label(i):
    """A, B, ..., Z, AA, AB, ... for the grid's axes along X."""
    out = ""
    i += 1
    while i > 0:
        i, r = divmod(i - 1, 26)
        out = chr(65 + r) + out
    return out


def _cs_angle(degrees):
    """An IfcCompoundPlaneAngleMeasure: degrees, minutes, seconds and millionths of a second, every part carrying the sign."""
    sign = -1 if float(degrees) < 0 else 1
    micro = int(round(abs(float(degrees)) * 3600.0 * 1000000.0))
    d, micro = divmod(micro, 3600 * 1000000)
    m, micro = divmod(micro, 60 * 1000000)
    s, micro = divmod(micro, 1000000)
    return [sign * d, sign * m, sign * s, sign * micro]


def _cs_crs_facts(crs):
    """The datum, projection and zone an EPSG code stands for, for the projected systems the Nordic countries draw in; (None, None,
    None) for a code outside the table. IFC4 requires the datum on IfcProjectedCRS, IFC4X3 does not."""
    code = int(crs[5:])
    if code == 3006:
        return "SWEREF99", "Transverse Mercator", "TM"
    if 3007 <= code <= 3018:
        return (
            "SWEREF99",
            "Transverse Mercator",
            (
                "12 00",
                "13 30",
                "15 00",
                "16 30",
                "18 00",
                "14 15",
                "15 45",
                "17 15",
                "18 45",
                "20 15",
                "21 45",
                "23 15",
            )[code - 3007],
        )
    if 25828 <= code <= 25838:
        return "ETRS89", "Transverse Mercator", "UTM %dN" % (code - 25800)
    if code == 3067:
        return "ETRS89", "Transverse Mercator", "TM35FIN"
    if 3873 <= code <= 3885:
        return "ETRS89", "Transverse Mercator", "GK%dFIN" % (code - 3854)
    if 5105 <= code <= 5130:
        return "ETRS89", "Transverse Mercator", "NTM zone %d" % (code - 5100)
    if code == 3057:
        return "ISN93", "Lambert Conformal Conic", "Lambert 1993"
    if code == 8088:
        return "ISN2016", "Lambert Conformal Conic", "Lambert 2016"
    if 32601 <= code <= 32660:
        return "WGS84", "Transverse Mercator", "UTM %dN" % (code - 32600)
    if 32701 <= code <= 32760:
        return "WGS84", "Transverse Mercator", "UTM %dS" % (code - 32700)
    if code == 3857:
        return "WGS84", "Pseudo-Mercator", None
    return None, None, None


# Placements as matrices [X, Y, Z, origin] (the axes as columns, in file units), for reading where the walls stand.
def _cs_unit(v):
    n = math.sqrt(sum(c * c for c in v))
    return [c / n for c in v] if n > 1e-12 else None


def _cs_dot(u, v):
    return u[0] * v[0] + u[1] * v[1] + u[2] * v[2]


def _cs_turn(m, v):
    """The direction v of the matrix m's coordinates in its parent's."""
    return [m[0][i] * v[0] + m[1][i] * v[1] + m[2][i] * v[2] for i in range(3)]


def _cs_at(m, p):
    """The point p of the matrix m's coordinates in its parent's."""
    return [a + b for a, b in zip(_cs_turn(m, p), m[3])]


def _cs_compose(a, b):
    return [_cs_turn(a, b[0]), _cs_turn(a, b[1]), _cs_turn(a, b[2]), _cs_at(a, b[3])]


def _cs_invert(m):
    """The inverse of a rigid placement: the rotation transposed and the origin turned back."""
    x, y, z, o = m
    return [
        [x[0], y[0], z[0]],
        [x[1], y[1], z[1]],
        [x[2], y[2], z[2]],
        [-_cs_dot(x, o), -_cs_dot(y, o), -_cs_dot(z, o)],
    ]


def _cs_axes(position):
    """An IfcAxis2Placement3D or 2D as a matrix; the identity for none."""
    if position is None:
        return [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0], [0.0, 0.0, 0.0]]
    origin = ([float(c) for c in position.Location.Coordinates] + [0.0, 0.0])[:3]
    if position.is_a("IfcAxis2Placement2D"):
        z = [0.0, 0.0, 1.0]
        ref = (
            ([float(c) for c in position.RefDirection.DirectionRatios] + [0.0])[:3]
            if position.RefDirection is not None
            else [1.0, 0.0, 0.0]
        )
    else:
        z = (
            _cs_unit([float(c) for c in position.Axis.DirectionRatios])
            if position.Axis is not None
            else [0.0, 0.0, 1.0]
        )
        ref = (
            [float(c) for c in position.RefDirection.DirectionRatios]
            if position.RefDirection is not None
            else ([0.0, 1.0, 0.0] if abs(z[0]) > 0.9 else [1.0, 0.0, 0.0])
        )
    x = _cs_unit([a - _cs_dot(ref, z) * b for a, b in zip(ref, z)])
    return [x, [z[1] * x[2] - z[2] * x[1], z[2] * x[0] - z[0] * x[2], z[0] * x[1] - z[1] * x[0]], z, origin]


def _cs_placement(placement, depth=0):
    """The absolute matrix of an object placement (a chain of IfcLocalPlacement); None for one the app cannot follow."""
    if placement is None:
        return _cs_axes(None)
    if depth > 64 or not placement.is_a("IfcLocalPlacement"):
        return None
    parent = _cs_placement(placement.PlacementRelTo, depth + 1)
    return None if parent is None else _cs_compose(parent, _cs_axes(placement.RelativePlacement))


def _cs_profile_points(profile):
    """The outer corners of a profile in its plane: rectangles and polyline outlines; [] for curves the app does not read."""
    if profile.is_a("IfcRectangleProfileDef"):
        hx, hy = float(profile.XDim) / 2.0, float(profile.YDim) / 2.0
        m = _cs_axes(profile.Position)
        return [_cs_at(m, (x, y, 0.0))[:2] for x, y in ((-hx, -hy), (hx, -hy), (hx, hy), (-hx, hy))]
    curve = profile.OuterCurve if profile.is_a("IfcArbitraryClosedProfileDef") else None
    if curve is not None and curve.is_a("IfcPolyline"):
        return [[float(c) for c in p.Coordinates][:2] for p in curve.Points]
    if curve is not None and curve.is_a("IfcIndexedPolyCurve"):
        return [[float(c) for c in p][:2] for p in curve.Points.CoordList]
    return []


def _cs_item_points(item, depth=0):
    """The corners of a body item in its own coordinates: extruded rectangles and polylines, Boolean results by their first operand,
    faceted and tessellated solids; [] for what the app does not read."""
    if item is None or depth > 16:
        return []
    if item.is_a("IfcBooleanResult"):
        return _cs_item_points(item.FirstOperand, depth + 1)
    if item.is_a("IfcExtrudedAreaSolid"):
        d = _cs_unit([float(c) for c in item.ExtrudedDirection.DirectionRatios])
        m = _cs_axes(item.Position)
        return [
            _cs_at(m, (x + d[0] * k, y + d[1] * k, d[2] * k))
            for x, y in _cs_profile_points(item.SweptArea)
            for k in (0.0, float(item.Depth))
        ]
    if item.is_a("IfcFacetedBrep"):
        return [
            [float(c) for c in p.Coordinates]
            for f in item.Outer.CfsFaces
            for b in f.Bounds
            if b.Bound.is_a("IfcPolyLoop")
            for p in b.Bound.Polygon
        ]
    if item.is_a("IfcTessellatedFaceSet"):
        return [[float(c) for c in p] for p in item.Coordinates.CoordList]
    return []


def _cs_rectangle(points):
    """Whether (x, y) points are the four corners of their bounding box (a closing corner may repeat the first)."""
    pts = list(points[:-1]) if len(points) > 4 and tuple(points[0]) == tuple(points[-1]) else list(points)
    if len(pts) != 4:
        return False
    x0, y0, x1, y1 = min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts)
    corners = set()
    for x, y in pts:
        cx = 0 if abs(x - x0) < 1e-3 else 1 if abs(x - x1) < 1e-3 else None
        cy = 0 if abs(y - y0) < 1e-3 else 1 if abs(y - y1) < 1e-3 else None
        if cx is None or cy is None:
            return False
        corners.add((cx, cy))
    return len(corners) == 4


def _cs_roof_faces(shape, length, width, overhang, ridge):
    """The faces of a roof over the rectangle [0, length] x [0, width] in metres: (fall, corners), fall the horizontal direction the
    face falls toward and corners its outline in plan, the eaves first and then the upper corners back, with the overhang beyond the
    rectangle on every side. A shed falls toward negative y (ridge x: negative x); a gable's ridge runs along the longer side unless
    ridge says x or y; a hip roof's hips run at 45 degrees in plan, so its ridge lies along the longer side (a point over a square)."""
    a, b, o = float(length), float(width), float(overhang)
    sw, se, ne, nw = (-o, -o), (a + o, -o), (a + o, b + o), (-o, b + o)
    south, north, west, east = (0.0, -1.0), (0.0, 1.0), (-1.0, 0.0), (1.0, 0.0)
    if shape == "flat" or (shape == "shed" and ridge != "x"):
        return [(south, [sw, se, ne, nw])]
    if shape == "shed":
        return [(west, [nw, sw, se, ne])]
    if shape == "gable":
        if ridge == "x" or (ridge != "y" and a >= b):
            return [
                (south, [sw, se, (a + o, b / 2.0), (-o, b / 2.0)]),
                (north, [ne, nw, (-o, b / 2.0), (a + o, b / 2.0)]),
            ]
        return [(west, [nw, sw, (a / 2.0, -o), (a / 2.0, b + o)]), (east, [se, ne, (a / 2.0, b + o), (a / 2.0, -o)])]
    if a >= b:
        r1, r2 = (b / 2.0, b / 2.0), (a - b / 2.0, b / 2.0)
        faces = [(south, [sw, se, r2, r1]), (north, [ne, nw, r1, r2]), (west, [nw, sw, r1]), (east, [se, ne, r2])]
    else:
        r1, r2 = (a / 2.0, a / 2.0), (a / 2.0, b - a / 2.0)
        faces = [(west, [nw, sw, r1, r2]), (east, [se, ne, r2, r1]), (south, [sw, se, r1]), (north, [ne, nw, r2])]
    return [
        (fall, [p for i, p in enumerate(c) if i == 0 or abs(p[0] - c[i - 1][0]) + abs(p[1] - c[i - 1][1]) > 1e-6])
        for fall, c in faces
    ]


class _ChangeSet:
    """Applies a change set to an IfcOpenShell model and reports what it created, changed and deleted."""

    CREATES = ("create_wall", "create_slab", "create_roof", "create_opening", "create_spaces")
    ROOF_TYPES = {"gable": "GABLE_ROOF", "hip": "HIP_ROOF", "shed": "SHED_ROOF", "flat": "FLAT_ROOF"}

    def __init__(self, model):
        import ifcopenshell.util.unit

        self.m = model
        try:
            self.scale = float(ifcopenshell.util.unit.calculate_unit_scale(model) or 1.0)  # metres per file unit
        except Exception:
            self.scale = 1.0
        self.refs = {}
        self.created = []
        self.changed = {}
        self.deleted = []
        self.notes = []  # what an operation could not do in the file's schema, for the report
        self.n_created = 0
        owners = model.by_type("IfcOwnerHistory")
        self.owner = owners[0] if owners else None
        self._body = None
        self._axis = None
        self._schema = None

    # -- units, lookups and bookkeeping
    def u(self, metres):
        return float(metres) / self.scale

    def entity(self, ref):
        """An element by its STEP id, its GlobalId (22 characters: a proposal names elements so, decision F34 a at Dataregium), or a
        ref of this change set."""
        if isinstance(ref, str) and ref in self.refs:
            return self.refs[ref]
        if isinstance(ref, str) and len(ref) == 22 and not ref.isdigit():
            try:
                e = self.m.by_guid(ref)
            except Exception:
                e = None
            if e is None:
                raise DataspatiumError("no element with GlobalId %r" % (ref,))
            return e
        try:
            e = self.m.by_id(int(ref))
        except Exception:
            raise DataspatiumError("no element with id %r" % (ref,))
        if e is None:
            raise DataspatiumError("no element with id %r" % (ref,))
        return e

    def elements(self, op):
        ids = op.get("ids")
        if not isinstance(ids, (list, tuple)) or not ids:
            raise DataspatiumError("ids must be a list of element ids or refs")
        return [self.entity(x) for x in ids]

    def storey(self, name, top=False):
        """A storey by its name; without one the lowest, or with top the highest."""
        storeys = self.m.by_type("IfcBuildingStorey")
        if not storeys:
            raise DataspatiumError("the model has no storey; create one with create_storeys_and_grid first")
        if name is None or str(name).strip() == "":
            # IFC4.3's storeys have their height in the placement
            ordered = sorted(storeys, key=lambda s: _topo_elevation(s, self.scale))
            return ordered[-1] if top else ordered[0]
        for exact in (True, False):
            for s in storeys:
                a, b = str(s.Name or ""), str(name)
                if (a == b) if exact else (a.lower() == b.lower()):
                    return s
        raise DataspatiumError(
            "no storey named %r; the storeys are %s" % (name, ", ".join(str(s.Name) for s in storeys))
        )

    def container(self, e):
        import ifcopenshell.util.element as el

        try:
            return el.get_container(e)
        except Exception:
            return None

    def record(self, e, storey=None):
        return {
            "id": e.id(),
            "guid": getattr(e, "GlobalId", None),
            "ifc_class": e.is_a(),
            "name": _ifc_text(getattr(e, "Name", None)),
            "storey": _ifc_text(getattr(storey, "Name", None)) if storey is not None else None,
        }

    def register(self, e, storey=None, ref=True):
        rec = self.record(e, storey)
        if ref:
            self.n_created += 1
            rec["ref"] = "new-%d" % self.n_created
            self.refs[rec["ref"]] = e
        self.created.append(rec)
        return rec

    def touch(self, e):
        if any(c["id"] == e.id() for c in self.created):
            return
        self.changed[e.id()] = self.record(e, self.container(e))

    # -- the right class (decision B-57.2): every class and enumeration value an operation sets is checked against the schema
    def schema_def(self):
        if self._schema is None:
            self._schema = _ifc_schema(getattr(self.m, "schema_identifier", None) or self.m.schema)
        return self._schema

    def check_class(self, ifc_class):
        """The entity's declaration in the file's schema; a DataspatiumError, with the classes to use instead, when it does not exist
        there or is abstract."""
        schema = self.schema_def()
        decl = _ifc_declaration(schema, ifc_class)
        if decl is not None and decl.as_entity() is not None and not decl.is_abstract():
            return decl
        if decl is not None and decl.as_entity() is not None:
            raise DataspatiumError(
                "%s is abstract in %s; use one of %s" % (ifc_class, schema.name(), ", ".join(_ifc_concrete(decl)[:30]))
            )
        import difflib

        near = difflib.get_close_matches(
            str(ifc_class),
            [d.name() for d in schema.declarations() if d.as_entity() is not None and not d.is_abstract()],
            8,
            0.6,
        )
        raise DataspatiumError(
            "%s is not an entity of %s%s" % (ifc_class, schema.name(), "; near: " + ", ".join(near) if near else "")
        )

    def check_enum(self, e, value, attribute="PredefinedType"):
        """Whether the schema gives the element the enumeration `attribute`; a DataspatiumError that lists the allowed values for one
        it does not take, and for USERDEFINED without the name of the type (ObjectType on an occurrence, ElementType on a type)."""
        items = _ifc_enum_items(self.check_class(e.is_a()), attribute)
        if items is None:
            return False
        gone = DEPRECATED_VALUES.get(self.m.schema, {}).get(e.is_a(), ()) if attribute == "PredefinedType" else ()
        allowed = [i for i in items if i not in gone]
        if value in gone:
            raise DataspatiumError(
                "%s is deprecated for %s in %s (bSI rule IFC102); use one of %s"
                % (value, e.is_a(), self.schema_def().name(), ", ".join(allowed))
            )
        if value not in items:
            raise DataspatiumError(
                "%s is not a %s of %s in %s; it takes %s"
                % (value, attribute, e.is_a(), self.schema_def().name(), ", ".join(allowed))
            )
        if value == "USERDEFINED" and attribute == "PredefinedType":
            named = "ElementType" if e.is_a("IfcTypeObject") else "ObjectType"
            if not str(getattr(e, named, None) or "").strip():
                raise DataspatiumError(
                    "%s USERDEFINED needs %s, the name of the user-defined type; or use one of %s"
                    % (e.is_a(), named, ", ".join(i for i in allowed if i not in ("USERDEFINED", "NOTDEFINED")))
                )
        return True

    def predefined(self, e, value):
        """Set the element's PredefinedType after check_enum; an entity whose schema has none (walls, doors and windows in IFC2X3)
        takes nothing."""
        if self.check_enum(e, value):
            e.PredefinedType = value

    # -- the file's structure
    def root(self, ifc_class, name):
        import ifcopenshell.guid

        self.check_class(ifc_class)
        e = self.m.create_entity(ifc_class, GlobalId=ifcopenshell.guid.new(), Name=str(name))
        if self.owner is not None:
            e.OwnerHistory = self.owner
        return e

    def owner_settings(self):
        """IFC2X3 needs an owner history on every IfcRoot, also on the relationships the API makes: lend it the file's."""
        import ifcopenshell.api.owner.settings as settings

        if self.m.schema != "IFC2X3" or self.owner is None:
            return None
        previous = (settings.get_user, settings.get_application)
        owner = self.owner
        settings.get_user = lambda _file: owner.OwningUser  # ty: ignore[invalid-assignment]
        settings.get_application = lambda _file: owner.OwningApplication  # ty: ignore[invalid-assignment]
        return previous

    @staticmethod
    def restore_owner_settings(previous):
        if previous is None:
            return
        import ifcopenshell.api.owner.settings as settings

        settings.get_user, settings.get_application = previous

    def building(self):
        import ifcopenshell.api.aggregate

        buildings = self.m.by_type("IfcBuilding")
        if buildings:
            return buildings[0]
        site = self.site()
        building = self.root("IfcBuilding", "Building")
        building.CompositionType = "ELEMENT"
        building.ObjectPlacement = self.placement(site.ObjectPlacement, 0, 0, 0)
        ifcopenshell.api.aggregate.assign_object(self.m, products=[building], relating_object=site)
        self.register(building, ref=False)
        return building

    def site(self, name=None):
        """The file's site: the first IfcSite, or a new one under the project, with the buildings that hung on the project moved under it."""
        import ifcopenshell.api.aggregate

        sites = self.m.by_type("IfcSite")
        if sites:
            return sites[0]
        projects = self.m.by_type("IfcProject")
        if not projects:
            raise DataspatiumError("the model has no IfcProject")
        site = self.root("IfcSite", name or "Site")
        site.CompositionType = "ELEMENT"
        site.ObjectPlacement = self.placement(None, 0, 0, 0)
        ifcopenshell.api.aggregate.assign_object(self.m, products=[site], relating_object=projects[0])
        for building in self.m.by_type("IfcBuilding"):
            if any(rel.RelatingObject.id() == projects[0].id() for rel in (building.Decomposes or ())):
                ifcopenshell.api.aggregate.assign_object(self.m, products=[building], relating_object=site)
                self.touch(building)
        self.register(site, ref=False)
        return site

    def model_context(self):
        """The 3D model context (ContextType Model, not a sub-context), made when the file has none."""
        parents = [
            c
            for c in self.m.by_type("IfcGeometricRepresentationContext")
            if not c.is_a("IfcGeometricRepresentationSubContext") and (c.ContextType or "Model") == "Model"
        ]
        if parents:
            return parents[0]
        import ifcopenshell.api.context

        return ifcopenshell.api.context.add_context(self.m, context_type="Model")

    def length_unit(self):
        """The project's length unit (an IfcNamedUnit), or None."""
        for project in self.m.by_type("IfcProject"):
            units = project.UnitsInContext
            for unit in (units.Units or ()) if units is not None else ():
                if unit.is_a("IfcNamedUnit") and getattr(unit, "UnitType", None) == "LENGTHUNIT":
                    return unit
        return None

    def body(self):
        if self._body is not None:
            return self._body
        subs = [
            c for c in self.m.by_type("IfcGeometricRepresentationSubContext") if (c.ContextIdentifier or "") == "Body"
        ]
        if subs:
            self._body = subs[0]
            return subs[0]
        import ifcopenshell.api.context

        self._body = ifcopenshell.api.context.add_context(
            self.m,
            context_type="Model",
            context_identifier="Body",
            target_view="MODEL_VIEW",
            parent=self.model_context(),
        )
        return self._body

    def axis_context(self):
        """The sub-context of the walls' 'Axis' representations (Model/Axis/GRAPH_VIEW), made when the file has none."""
        if self._axis is not None:
            return self._axis
        subs = [
            c for c in self.m.by_type("IfcGeometricRepresentationSubContext") if (c.ContextIdentifier or "") == "Axis"
        ]
        if subs:
            self._axis = subs[0]
            return subs[0]
        import ifcopenshell.api.context

        self._axis = ifcopenshell.api.context.add_context(
            self.m,
            context_type="Model",
            context_identifier="Axis",
            target_view="GRAPH_VIEW",
            parent=self.model_context(),
        )
        return self._axis

    def contain(self, e, storey):
        import ifcopenshell.api.spatial

        ifcopenshell.api.spatial.assign_container(self.m, products=[e], relating_structure=storey)

    # -- geometry, in file units
    def point(self, x, y, z=None):
        return self.m.createIfcCartesianPoint([float(x), float(y)] if z is None else [float(x), float(y), float(z)])

    def direction(self, x, y, z=None):
        return self.m.createIfcDirection([float(x), float(y)] if z is None else [float(x), float(y), float(z)])

    def axis3(self, x, y, z, dx=1.0, dy=0.0):
        return self.m.createIfcAxis2Placement3D(self.point(x, y, z), self.direction(0, 0, 1), self.direction(dx, dy, 0))

    def placement(self, parent, x, y, z, dx=1.0, dy=0.0):
        return self.m.createIfcLocalPlacement(parent, self.axis3(x, y, z, dx, dy))

    def shape(self, solid):
        rep = self.m.createIfcShapeRepresentation(self.body(), "Body", "SweptSolid", [solid])
        return self.m.createIfcProductDefinitionShape(None, None, [rep])

    def box(self, length, width, height, x0=0.0, y0=0.0, z0=0.0):
        """A rectangle of length (X) by width (Y) with its corner at (x0, y0), extruded height along Z from z0."""
        position = self.m.createIfcAxis2Placement2D(self.point(x0 + length / 2.0, y0 + width / 2.0), None)
        profile = self.m.createIfcRectangleProfileDef("AREA", None, position, float(length), float(width))
        return self.shape(
            self.m.createIfcExtrudedAreaSolid(profile, self.axis3(0, 0, z0), self.direction(0, 0, 1), float(height))
        )

    def closed(self, outline):
        """A closed IfcPolyline through (x, y) corners: a repeated first corner at the end is dropped, and the line closes on the first
        corner's own IfcCartesianPoint, not a copy of it (bSI rule GEM111)."""
        corners = [tuple(float(v) for v in p) for p in outline]
        while len(corners) > 1 and corners[-1] == corners[0]:
            corners.pop()
        if len(corners) < 3:
            raise DataspatiumError("an outline needs at least three different corners")
        pts = [self.point(x, y) for x, y in corners]
        return self.m.createIfcPolyline(pts + pts[:1])

    def prism(self, outline, height, z0=0.0):
        """A closed outline of (x, y) points extruded height along Z from z0."""
        profile = self.m.createIfcArbitraryClosedProfileDef("AREA", None, self.closed(outline))
        return self.shape(
            self.m.createIfcExtrudedAreaSolid(profile, self.axis3(0, 0, z0), self.direction(0, 0, 1), float(height))
        )

    def wall_thickness(self, wall):
        """The YDim of the wall's rectangle profile, in file units; 0.2 m when the wall has another shape."""
        rep = getattr(wall, "Representation", None)
        for r in rep.Representations if rep is not None else []:
            for item in r.Items or []:
                if item.is_a("IfcExtrudedAreaSolid") and item.SweptArea.is_a("IfcRectangleProfileDef"):
                    return float(item.SweptArea.YDim)
        return self.u(0.2)

    def grid_outline(self):
        pts = []
        for g in self.m.by_type("IfcGrid"):
            for axis in list(g.UAxes or []) + list(g.VAxes or []):
                curve = axis.AxisCurve
                for p in curve.Points if curve.is_a("IfcPolyline") else []:
                    c = list(p.Coordinates)
                    pts.append((c[0] * self.scale, c[1] * self.scale))
        if not pts:
            raise DataspatiumError("give an outline, or create a grid first so that the slab can follow it")
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        return [(min(xs), min(ys)), (max(xs), min(ys)), (max(xs), max(ys)), (min(xs), max(ys))]

    def wall_extent(self, storey):
        """The bounding box (x0, y0, x1, y1) of the storey's walls in its plane and the height of their tops above it, in metres;
        (None, None) when no wall on the storey has a body the app can read."""
        frame = _cs_placement(storey.ObjectPlacement)
        if frame is None:
            return None, None
        back = _cs_invert(frame)
        pts = []
        for wall in self.m.by_type("IfcWall"):
            container = self.container(wall)
            if container is None or container.id() != storey.id():
                continue
            try:
                m = _cs_placement(wall.ObjectPlacement)
                rep = wall.Representation
                if m is None or rep is None:
                    continue
                m = _cs_compose(back, m)
                for r in rep.Representations or ():
                    if (r.RepresentationIdentifier or "") == "Body":
                        pts += [_cs_at(m, p) for item in (r.Items or ()) for p in _cs_item_points(item)]
            except Exception:  # nosec B112
                continue
        if not pts:
            return None, None
        s = self.scale
        return (
            min(p[0] for p in pts) * s,
            min(p[1] for p in pts) * s,
            max(p[0] for p in pts) * s,
            max(p[1] for p in pts) * s,
        ), max(p[2] for p in pts) * s

    # -- the operations
    def op_create_storeys_and_grid(self, op):
        import ifcopenshell.api.aggregate

        storeys = op.get("storeys") or []
        grid = op.get("grid")
        if not storeys and not grid:
            raise DataspatiumError("give storeys, a grid or both")
        building = self.building()
        made = []
        for s in storeys:
            if not isinstance(s, dict) or not str(s.get("name") or "").strip():
                raise DataspatiumError("every storey needs a name")
            existing = [x for x in self.m.by_type("IfcBuildingStorey") if str(x.Name or "") == str(s["name"])]
            if existing:
                made.append(existing[0])
                continue
            elevation = _cs_num(s, "elevation", 0.0)
            storey = self.root("IfcBuildingStorey", s["name"])
            storey.CompositionType = "ELEMENT"
            if self.m.schema != "IFC4X3":
                # deprecated in IFC4.3 (IFC102): there the placement alone gives the height
                storey.Elevation = self.u(elevation)
            storey.ObjectPlacement = self.placement(building.ObjectPlacement, 0, 0, self.u(elevation))
            ifcopenshell.api.aggregate.assign_object(self.m, products=[storey], relating_object=building)
            self.register(storey, ref=False)
            made.append(storey)
        if grid:
            if not isinstance(grid, dict):
                raise DataspatiumError("grid must be an object with x_spacing, x_count, y_spacing and y_count")
            self.make_grid(grid, made[0] if made else self.storey(None))

    def make_grid(self, grid, storey):
        xs = _cs_num(grid, "x_spacing", positive=True)
        ys = _cs_num(grid, "y_spacing", positive=True)
        xn = int(_cs_num(grid, "x_count", 1.0, positive=True))
        yn = int(_cs_num(grid, "y_count", 1.0, positive=True))
        if xn > 100 or yn > 100:
            raise DataspatiumError("at most 100 bays per direction")
        width, depth = xs * xn, ys * yn
        u_axes = [
            self.m.createIfcGridAxis(
                _cs_label(i),
                self.m.createIfcPolyline([self.point(self.u(i * xs), 0), self.point(self.u(i * xs), self.u(depth))]),
                True,
            )
            for i in range(xn + 1)
        ]
        v_axes = [
            self.m.createIfcGridAxis(
                str(j + 1),
                self.m.createIfcPolyline([self.point(0, self.u(j * ys)), self.point(self.u(width), self.u(j * ys))]),
                True,
            )
            for j in range(yn + 1)
        ]
        g = self.root("IfcGrid", "Grid")
        g.ObjectPlacement = self.placement(storey.ObjectPlacement, 0, 0, 0)
        g.UAxes = u_axes
        g.VAxes = v_axes
        self.contain(g, storey)
        self.register(g, storey, ref=False)

    def op_create_wall(self, op):
        storey = self.storey(op.get("storey"))
        x1, y1 = _cs_xy(op.get("start"), "start")
        x2, y2 = _cs_xy(op.get("end"), "end")
        length = math.hypot(x2 - x1, y2 - y1)
        if length <= 0:
            raise DataspatiumError("start and end are the same point")
        thickness = _cs_num(op, "thickness", 0.2, positive=True)
        height = _cs_num(op, "height", 3.0, positive=True)
        wall = self.root("IfcWall", op.get("name") or "Wall")
        wall.ObjectPlacement = self.placement(
            storey.ObjectPlacement, self.u(x1), self.u(y1), 0, (x2 - x1) / length, (y2 - y1) / length
        )
        wall.Representation = self.box(
            self.u(length), self.u(thickness), self.u(height), 0, -self.u(thickness) / 2.0, 0
        )
        # The centreline as the wall's 'Axis' (Curve2D), after the body, so that the topology reads it without the geometry kernel.
        axis = self.m.createIfcPolyline([self.point(0, 0), self.point(self.u(length), 0)])
        wall.Representation.Representations = list(wall.Representation.Representations) + [
            self.m.createIfcShapeRepresentation(self.axis_context(), "Axis", "Curve2D", [axis])
        ]
        # STANDARD is deprecated (IFC102): a wall the AI calls a non-load-bearing interior wall partitions, any other is solid.
        self.predefined(wall, "PARTITIONING" if op.get("partition") is True else "SOLIDWALL")
        self.contain(wall, storey)
        self.register(wall, storey)

    def op_create_slab(self, op):
        storey = self.storey(op.get("storey"))
        thickness = _cs_num(op, "thickness", 0.25, positive=True)
        outline = op.get("outline") or self.grid_outline()
        if not isinstance(outline, (list, tuple)) or len(outline) < 3:
            raise DataspatiumError("outline must be at least three [x, y] points")
        pts = [_cs_xy(p, "outline") for p in outline]
        slab = self.root("IfcSlab", op.get("name") or "Slab")
        slab.ObjectPlacement = self.placement(storey.ObjectPlacement, 0, 0, 0)
        slab.Representation = self.prism(
            [(self.u(x), self.u(y)) for x, y in pts], self.u(thickness), -self.u(thickness)
        )
        self.predefined(slab, "FLOOR")
        self.contain(slab, storey)
        self.register(slab, storey)

    def op_create_roof(self, op):
        """A roof over a rectangle: an IfcRoof in the storey (the highest when none is named) that aggregates one roof slab (IfcSlab
        ROOF) per face, the roof alone with a ref. The rectangle is the outline's bounding box or the storey's walls'; the eaves lie on
        its sides at base above the storey (by default the top of the walls, else 2.7 m), every face rises inward at the pitch (the
        ridge base + half the span x tan(pitch) high), and the overhang reaches beyond the sides. A face is the polygon of its outline
        in its own plane (Axis the face's normal, RefDirection along the eaves), extruded straight up by thickness / cos(pitch): its
        thickness at right angles is the given one, and neighbouring faces meet in the vertical planes through the ridge and the hips
        without a gap or an overlap."""
        import ifcopenshell.api.aggregate

        shape = str(op.get("shape") or "").strip().lower()
        if shape not in self.ROOF_TYPES:
            raise DataspatiumError("shape must be gable, hip, shed or flat")
        storey = self.storey(op.get("storey"), top=True)
        flat = shape == "flat"
        pitch = 0.0 if flat else _cs_num(op, "pitch", 10.0 if shape == "shed" else 30.0, unit="degrees")
        if not flat and not 0.0 < pitch <= 75.0:
            raise DataspatiumError("pitch must be more than 0 and at most 75 degrees; use shape flat for a flat roof")
        overhang = _cs_num(op, "overhang", 0.0 if flat else 0.4)
        if overhang < 0:
            raise DataspatiumError("overhang must be zero or more (metres)")
        thickness = _cs_num(op, "thickness", 0.25, positive=True)
        ridge = str(op.get("ridge") or "").strip().lower() or None
        if ridge not in (None, "x", "y"):
            raise DataspatiumError("ridge must be x, y or null")
        outline = op.get("outline")
        extent, top = self.wall_extent(storey) if not outline or op.get("base") is None else (None, None)
        if outline:
            if not isinstance(outline, (list, tuple)) or len(outline) < 3:
                raise DataspatiumError("outline must be at least three [x, y] points")
            pts = [_cs_xy(p, "outline") for p in outline]
            extent = (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))
            if not _cs_rectangle(pts):
                self.notes.append(
                    "the roof's outline is not a rectangle along x and y (%d corners), so the roof covers its bounding box"
                    % len(pts)
                )
        elif extent is None:
            raise DataspatiumError(
                "give an outline: storey %r has no walls whose shape the app can read" % _ifc_text(storey.Name)
            )
        x0, y0, x1, y1 = extent
        length, width = x1 - x0, y1 - y0
        if length < 0.1 or width < 0.1:
            raise DataspatiumError(
                "the roof must span at least 0.1 m along x and along y, not %.3g x %.3g m" % (length, width)
            )
        base = _cs_num(op, "base", 2.7 if top is None else top)
        name = op.get("name") or "Roof"
        roof = self.root("IfcRoof", name)
        roof.ObjectPlacement = self.placement(storey.ObjectPlacement, self.u(x0), self.u(y0), self.u(base))
        if self.m.schema == "IFC2X3":
            if self.check_enum(roof, self.ROOF_TYPES[shape], "ShapeType"):
                roof.ShapeType = self.ROOF_TYPES[shape]
        else:
            self.predefined(roof, self.ROOF_TYPES[shape])
        self.contain(roof, storey)
        self.register(roof, storey)
        p = math.radians(pitch)
        sin, cos, tan = math.sin(p), math.cos(p), math.tan(p)
        slabs = []
        for i, (fall, corners) in enumerate(_cs_roof_faces(shape, length, width, overhang, ridge)):
            fx, fy = fall
            eaves = max(x * fx + y * fy for x, y in ((0.0, 0.0), (length, 0.0), (length, width), (0.0, width)))
            pts = [(x, y, (eaves - x * fx - y * fy) * tan) for x, y in corners]  # metres in the roof's placement
            along, up, normal = (-fy, fx, 0.0), (-fx * cos, -fy * cos, sin), (fx * sin, fy * sin, cos)
            o = pts[0]
            face = [
                [self.u(_cs_dot([q[k] - o[k] for k in range(3)], axis)) for axis in (along, up)] for q in pts
            ]  # in the face's plane
            profile = self.m.createIfcArbitraryClosedProfileDef("AREA", None, self.closed(face))
            position = self.m.createIfcAxis2Placement3D(
                self.point(self.u(o[0]), self.u(o[1]), self.u(o[2])), self.direction(*normal), self.direction(*along)
            )
            slab = self.root("IfcSlab", "%s %d" % (name, i + 1))
            slab.ObjectPlacement = self.placement(roof.ObjectPlacement, 0, 0, 0)
            slab.Representation = self.shape(
                self.m.createIfcExtrudedAreaSolid(
                    profile, position, self.direction(0.0, sin, cos), self.u(thickness / cos)
                )
            )
            self.predefined(slab, "ROOF")
            slabs.append(slab)
        ifcopenshell.api.aggregate.assign_object(self.m, products=slabs, relating_object=roof)
        for slab in slabs:
            self.register(slab, storey, ref=False)

    def op_create_opening(self, op):
        import ifcopenshell.api.feature

        wall = self.entity(op.get("wall_id"))
        if not wall.is_a("IfcWall"):
            raise DataspatiumError("wall_id must name a wall, not %s" % wall.is_a())
        fill = op.get("fill")
        if fill not in (None, "", "door", "window"):
            raise DataspatiumError("fill must be door, window or null")
        offset = _cs_num(op, "offset", 0.0)
        width = _cs_num(op, "width", 0.9, positive=True)
        height = _cs_num(op, "height", 2.1, positive=True)
        sill = _cs_num(op, "sill", 0.0)
        thickness = self.wall_thickness(wall)
        storey = self.container(wall)
        opening = self.root("IfcOpeningElement", op.get("name") or "Opening")
        opening.ObjectPlacement = self.placement(wall.ObjectPlacement, self.u(offset), 0, self.u(sill))
        margin = self.u(0.02)
        opening.Representation = self.box(
            self.u(width), thickness + 2 * margin, self.u(height), 0, -thickness / 2.0 - margin, 0
        )
        self.predefined(opening, "OPENING")
        ifcopenshell.api.feature.add_feature(self.m, feature=opening, element=wall)
        self.touch(wall)
        if not fill:
            self.register(opening, storey)
            return
        self.register(opening, storey, ref=False)
        e = self.root(
            "IfcDoor" if fill == "door" else "IfcWindow", op.get("name") or ("Door" if fill == "door" else "Window")
        )
        e.ObjectPlacement = self.placement(opening.ObjectPlacement, 0, 0, 0)
        leaf = self.u(0.05)
        e.Representation = self.box(self.u(width), leaf, self.u(height), 0, -leaf / 2.0, 0)
        e.OverallHeight = self.u(height)
        e.OverallWidth = self.u(width)
        self.predefined(e, "DOOR" if fill == "door" else "WINDOW")
        ifcopenshell.api.feature.add_filling(self.m, opening=opening, element=e)
        if storey is not None:
            self.contain(e, storey)
        self.register(e, storey)
        # A door or window in a wall that already bounds spaces bounds the one whose edge it stands on, as create_spaces would have.
        mid = self.plan_point(e, self.u(width) / 2.0)
        for b in list(getattr(wall, "ProvidesBoundaries", None) or ()):
            outline = self.space_outline(b.RelatingSpace) if b.RelatingSpace.is_a("IfcSpace") else None
            if (
                mid is not None
                and outline is not None
                and outline.boundary.distance(_topo_point(mid)) <= thickness * self.scale / 2.0 + 0.05
            ):
                self.bound(b.RelatingSpace, e, b.InternalOrExternalBoundary == "EXTERNAL")

    # -- spaces and their boundaries
    def bound(self, space, element, external):
        """A physical IfcRelSpaceBoundary of a space against a wall, door or window, without connection geometry for now."""
        import ifcopenshell.guid

        rel = self.m.create_entity(
            "IfcRelSpaceBoundary",
            GlobalId=ifcopenshell.guid.new(),
            RelatingSpace=space,
            RelatedBuildingElement=element,
            PhysicalOrVirtualBoundary="PHYSICAL",
            InternalOrExternalBoundary="EXTERNAL" if external else "INTERNAL",
        )
        if self.owner is not None:
            rel.OwnerHistory = self.owner
        return rel

    @staticmethod
    def fillings(wall):
        """The doors and windows in a wall's openings."""
        return [
            f.RelatedBuildingElement
            for v in (getattr(wall, "HasOpenings", None) or ())
            for f in (getattr(v.RelatedOpeningElement, "HasFillings", None) or ())
        ]

    def plan_point(self, e, along=0.0):
        """Where an element's placement stands in the world's plan, `along` file units along its x axis, in metres; None if unknown."""
        m = _cs_placement(getattr(e, "ObjectPlacement", None))
        if m is None:
            return None
        p = _cs_at(m, (along, 0.0, 0.0))
        return p[0] * self.scale, p[1] * self.scale

    def space_outline(self, space):
        """A space's footprint in the world's plan in metres (shapely): the profile of an extruded body, else the hull of its body's
        corners; None without a body the app can read."""
        from shapely.geometry import MultiPoint, Polygon

        m = _cs_placement(space.ObjectPlacement)
        rep = space.Representation
        pts = []
        for r in rep.Representations if rep is not None and m is not None else ():
            if (r.RepresentationIdentifier or "Body") != "Body":
                continue
            for item in r.Items or ():
                corners = [_cs_at(m, p) for p in _cs_item_points(item)]
                if item.is_a("IfcExtrudedAreaSolid") and len(corners) >= 6:
                    return Polygon([(q[0] * self.scale, q[1] * self.scale) for q in corners[::2]])
                pts += corners
        hull = MultiPoint([(q[0] * self.scale, q[1] * self.scale) for q in pts]).convex_hull if len(pts) >= 3 else None
        return hull if hull is not None and hull.geom_type == "Polygon" else None

    def storey_height(self, storey):
        """The default height of a storey's spaces in metres: up to the next storey, else to the top of its walls, else 3."""
        z = _topo_elevation(storey, self.scale)
        above = sorted(
            e for e in (_topo_elevation(s, self.scale) for s in self.m.by_type("IfcBuildingStorey")) if e > z + 1e-6
        )
        if above:
            return above[0] - z
        top = self.wall_extent(storey)[1]
        return top if top and top > 0 else 3.0

    def pick_rooms(self, topo, rooms, frame):
        """The listed rooms of one storey's topology, as (room, name, long name): each by a point inside it in the storey's plane, or by
        its index in get_topology. A point that hits no room, an index that does not exist and a room named twice are errors."""
        storey = _ifc_text(topo["_storey"].Name)
        back = _cs_invert(frame)

        def where(r):
            p = r["polygon"].representative_point()
            q = _cs_at(back, (p.x / self.scale, p.y / self.scale, frame[3][2]))
            return "%d at (%.2f, %.2f)" % (r["index"], q[0] * self.scale, q[1] * self.scale)

        out, seen = [], {}
        for i, entry in enumerate(rooms):
            if not isinstance(entry, dict) or not str(entry.get("name") or "").strip():
                raise DataspatiumError("room %d needs a name" % (i + 1))
            if entry.get("at") is not None:
                x, y = _cs_xy(entry.get("at"), "at")
                w = _cs_at(frame, (x / self.scale, y / self.scale, 0.0))
                hit = [
                    r
                    for r in topo["rooms"]
                    if r["polygon"].contains(_topo_point((w[0] * self.scale, w[1] * self.scale)))
                ]
                if not hit:
                    raise DataspatiumError(
                        "room %d: no closed room on storey %r has (%g, %g) inside; its rooms are %s"
                        % (i + 1, storey, x, y, "; ".join(where(r) for r in topo["rooms"]))
                    )
                room = hit[0]
            else:
                index = entry.get("index")
                if (
                    isinstance(index, bool)
                    or not isinstance(index, (int, float))
                    or int(index) != index
                    or not 1 <= int(index) <= len(topo["rooms"])
                ):
                    raise DataspatiumError(
                        "room %d: storey %r has rooms 1 to %d, not %r" % (i + 1, storey, len(topo["rooms"]), index)
                    )
                room = topo["rooms"][int(index) - 1]
            if room["index"] in seen:
                raise DataspatiumError(
                    "rooms %d and %d are the same room (%s)" % (seen[room["index"]], i + 1, where(room))
                )
            seen[room["index"]] = i + 1
            out.append(
                (room, str(entry["name"]).strip()[:255], str(entry.get("long_name") or "").strip()[:255] or None)
            )
        return out

    def make_space(self, storey, frame, room, name, long_name, height):
        """An IfcSpace with the room's outline (holes as voids) in the storey's plane, extruded height metres up from the storey."""
        back = _cs_invert(frame)

        def curve(ring):
            return self.closed(
                [_cs_at(back, (c[0] / self.scale, c[1] / self.scale, frame[3][2]))[:2] for c in ring.coords]
            )

        poly = room["polygon"]
        if poly.interiors:
            profile = self.m.createIfcArbitraryProfileDefWithVoids(
                "AREA", None, curve(poly.exterior), [curve(r) for r in poly.interiors]
            )
        else:
            profile = self.m.createIfcArbitraryClosedProfileDef("AREA", None, curve(poly.exterior))
        space = self.root("IfcSpace", name)
        space.LongName = long_name
        space.CompositionType = "ELEMENT"
        if self.m.schema == "IFC2X3":
            if self.check_enum(space, "INTERNAL", "InteriorOrExteriorSpace"):
                space.InteriorOrExteriorSpace = "INTERNAL"
        elif self.m.schema == "IFC4X3":
            # INTERNAL is deprecated in IFC4.3 (IFC102); that the room is inside is IsExternal false
            self.predefined(space, "SPACE")
        else:
            self.predefined(space, "INTERNAL")
        space.ObjectPlacement = self.placement(storey.ObjectPlacement, 0, 0, 0)
        space.Representation = self.shape(
            self.m.createIfcExtrudedAreaSolid(profile, self.axis3(0, 0, 0), self.direction(0, 0, 1), self.u(height))
        )
        return space

    def space_quantities(self, space, room, height):
        """Qto_SpaceBaseQuantities in the file's units: the outline's area and perimeter, the area inside the walls' faces, the volumes."""
        import ifcopenshell.api.pset
        import ifcopenshell.util.unit

        def per(kind):
            try:
                return float(ifcopenshell.util.unit.calculate_unit_scale(self.m, kind) or 1.0)
            except Exception:
                return 1.0

        area, volume = per("AREAUNIT"), per("VOLUMEUNIT")
        gross, net = room["polygon"].area, room["net_area"]
        qto = ifcopenshell.api.pset.add_qto(self.m, product=space, name="Qto_SpaceBaseQuantities")
        ifcopenshell.api.pset.edit_qto(
            self.m,
            qto=qto,
            properties={
                "Height": self.u(height),
                "GrossPerimeter": self.u(room["polygon"].length),
                "GrossFloorArea": gross / area,
                "NetFloorArea": net / area,
                "GrossVolume": gross * height / volume,
                "NetVolume": net * height / volume,
            },
        )

    def op_create_spaces(self, op):
        """The rooms the walls enclose as spaces, from the topology of the file as it stands at this step, so that walls made earlier
        in the change set count: per room an IfcSpace aggregated in its storey, with the room's outline extruded to the height (by
        default up to the next storey, or to the top of the walls), Qto_SpaceBaseQuantities, and physical space boundaries to the walls
        along its edge (external where the topology finds the wall external) and to the doors and windows in them that stand on that
        edge. Listed rooms need the storey and get a ref each, in their order; without a list every room on the storey (or on every
        storey with rooms) is made, named by default_name with its index for {n}, and none gets a ref."""
        import ifcopenshell.api.aggregate

        rooms = op.get("rooms")
        listed = rooms is not None
        if listed and (not isinstance(rooms, list) or not rooms):
            raise DataspatiumError("rooms must be a list of {at or index, name, long_name}, or null for every room")
        named = str(op.get("storey") or "").strip()
        if listed and not named:
            raise DataspatiumError("name the storey the rooms are on; storey null goes with rooms null")
        storey = self.storey(named) if named else None
        height = None if op.get("height") is None else _cs_num(op, "height", positive=True)
        found = [
            x
            for x in _ifc_topology(
                self.m, storeys={_ifc_text(storey.Name)} if storey is not None else None, shapes=True
            )
            if x["rooms"] and (storey is None or x["_storey"].id() == storey.id())
        ]
        if not found:
            raise DataspatiumError(
                "the walls enclose no room on %s; close the walls first (the preview's topology shows the open ends)"
                % ("storey %r" % _ifc_text(storey.Name) if storey is not None else "any storey")
            )
        template = str(op.get("default_name") or "Room {n}")
        made = 0
        for topo in found:
            s = topo["_storey"]
            frame = _cs_placement(s.ObjectPlacement)
            if frame is None:
                raise DataspatiumError("the placement of storey %r cannot be followed" % _ifc_text(s.Name))
            chosen = (
                self.pick_rooms(topo, rooms, frame)
                if listed
                else [(r, template.replace("{n}", str(r["index"])), None) for r in topo["rooms"]]
            )
            # The storey's spaces so far: a room one of them covers is not made twice, and a name is not given twice.
            others = [
                (p, self.space_outline(p))
                for rel in (getattr(s, "IsDecomposedBy", None) or ())
                for p in rel.RelatedObjects
                if p.is_a("IfcSpace")
            ]
            covered = [
                (
                    room,
                    name,
                    next(
                        (p for p, o in others if o is not None and o.contains(room["polygon"].representative_point())),
                        None,
                    ),
                )
                for room, name, _ in chosen
            ]
            for room, name, space in covered:
                if space is not None and listed:
                    raise DataspatiumError(
                        "room %d on storey %r lies in the space %r already"
                        % (room["index"], _ifc_text(s.Name), _ifc_text(space.Name))
                    )
                if space is not None:
                    self.notes.append(
                        "room %d on storey %s was left out: the space %s covers it already"
                        % (room["index"], _ifc_text(s.Name), _ifc_text(space.Name))
                    )
            chosen = [c for c, (_, _, space) in zip(chosen, covered) if space is None]
            twice = [n for _, n, _ in chosen if n in {str(p.Name or "") for p, _ in others}]
            if twice:
                raise DataspatiumError("storey %r has a space named %r already" % (_ifc_text(s.Name), twice[0]))
            if not chosen:
                continue
            made += len(chosen)
            h = height or self.storey_height(s)
            external = {e["wall"] for e in topo["external"]}
            spaces = []
            for room, name, long_name in chosen:
                space = self.make_space(s, frame, room, name, long_name, h)
                spaces.append(space)
                for wall in (self.m.by_id(i) for i in room["walls"]):
                    self.bound(space, wall, wall.id() in external)
                    for f in self.fillings(wall):
                        mid = self.plan_point(f, float(getattr(f, "OverallWidth", None) or 0.0) / 2.0)
                        if mid is not None and room["polygon"].boundary.distance(_topo_point(mid)) <= topo["tolerance"]:
                            self.bound(space, f, wall.id() in external)
            ifcopenshell.api.aggregate.assign_object(self.m, products=spaces, relating_object=s)
            for space, (room, _, _) in zip(spaces, chosen):
                self.space_quantities(space, room, h)
                if self.m.schema == "IFC4X3":
                    import ifcopenshell.api.pset

                    pset = ifcopenshell.api.pset.add_pset(self.m, product=space, name="Pset_SpaceCommon")
                    ifcopenshell.api.pset.edit_pset(self.m, pset=pset, properties={"IsExternal": False})
                self.register(space, s, ref=listed)
        if not made:
            raise DataspatiumError("every room the walls enclose has a space already")

    def op_set_properties(self, op):
        import ifcopenshell.api.pset
        import ifcopenshell.util.element as el

        name = op.get("pset")
        props = op.get("properties")
        if not name or not isinstance(props, dict) or not props:
            raise DataspatiumError("pset and properties (an object of name: value) are required")
        values = {str(k): _ifc_value(v) for k, v in props.items()}
        for e in self.elements(op):
            existing = el.get_psets(e, psets_only=True).get(str(name))
            pset = (
                self.m.by_id(existing["id"])
                if existing and existing.get("id")
                else ifcopenshell.api.pset.add_pset(self.m, product=e, name=str(name))
            )
            ifcopenshell.api.pset.edit_pset(self.m, pset=pset, properties=values)
            self.touch(e)

    def op_set_classification(self, op):
        """A reference to a class of the system the person names, on the elements. A reference is reused only when its system, its
        code (Identification; ItemReference in IFC2X3) and its Location all match, and without a code its name too; otherwise it is
        made under that system's IfcClassification. (IfcOpenShell's add_reference reuses any reference with the same code in the
        file, whatever its system, and any reference without a code when none is given.) The system's own facts, when given (edition,
        source and dictionary_uri), go on its IfcClassification as Edition, Source and Location (IFC4) or Specification (IFC4.3); a
        system of the same name with another edition or address is another IfcClassification. Nothing is fetched: the facts come from
        the call. IFC2X3 requires Source and Edition, so an empty label stands for one not given, and its IfcClassification is not
        related to the project (IFC2X3 relates only references)."""
        import ifcopenshell.api.classification
        import ifcopenshell.guid

        system = str(op.get("system") or "").strip()
        name = str(op.get("name") or "").strip()
        if not system or not name:
            raise DataspatiumError("system and name are required")
        edition, source, address = (
            str(op.get(key) or "").strip() or None for key in ("edition", "source", "dictionary_uri")
        )
        address_attribute = {"IFC4": "Location", "IFC4X3": "Specification"}.get(self.m.schema)

        def same_system(c):
            here = getattr(c, address_attribute, None) if address_attribute else None
            return (
                str(c.Name or "") == system
                and not (edition and c.Edition and str(c.Edition) != edition)
                and not (address and here and str(here) != address)
            )

        classification = next((c for c in self.m.by_type("IfcClassification") if same_system(c)), None)
        if classification is None and self.m.schema == "IFC2X3":
            classification = self.m.create_entity(
                "IfcClassification", Source=source or "", Edition=edition or "", Name=system
            )
        elif classification is None:
            classification = ifcopenshell.api.classification.add_classification(self.m, classification=system)
        if edition and not classification.Edition:
            classification.Edition = edition
        if source and not classification.Source:
            classification.Source = source
        if address and address_attribute and not getattr(classification, address_attribute, None):
            setattr(classification, address_attribute, address)
        code = str(op.get("code") or "").strip() or None
        uri = str(op.get("uri") or "").strip() or None
        code_attribute = "ItemReference" if self.m.schema == "IFC2X3" else "Identification"

        def system_of(ref):
            source = ref.ReferencedSource
            for _ in range(16):  # a reference may hang under another reference of the same system
                if source is None or not source.is_a("IfcClassificationReference"):
                    break
                source = source.ReferencedSource
            return source

        # Without a code a class is known by its name alone, so the name must match as well.
        ref = next(
            (
                r
                for r in self.m.by_type("IfcClassificationReference")
                if system_of(r) == classification
                and (getattr(r, code_attribute, None) or None) == code
                and (r.Location or None) == uri
                and (code is not None or str(r.Name or "") == name)
            ),
            None,
        )
        if ref is None:
            ref = self.m.create_entity(
                "IfcClassificationReference",
                Location=uri,
                Name=name,
                ReferencedSource=classification,
                **{code_attribute: code},
            )
        elements = self.elements(op)
        rel = next(
            (r for r in self.m.by_type("IfcRelAssociatesClassification") if r.RelatingClassification == ref), None
        )
        if rel is None:
            rel = self.m.create_entity(
                "IfcRelAssociatesClassification",
                GlobalId=ifcopenshell.guid.new(),
                RelatedObjects=elements,
                RelatingClassification=ref,
            )
            if self.owner is not None:
                rel.OwnerHistory = self.owner
        else:
            rel.RelatedObjects = list(rel.RelatedObjects) + [e for e in elements if e not in rel.RelatedObjects]
        for e in elements:
            self.touch(e)

    def op_assign(self, op):
        import ifcopenshell.api.material

        storey = self.storey(op["storey"]) if op.get("storey") else None
        material = op.get("material")
        if storey is None and not material:
            raise DataspatiumError("give a storey, a material or both")
        for e in self.elements(op):
            if storey is not None:
                self.contain(e, storey)
            if material:
                found = [x for x in self.m.by_type("IfcMaterial") if str(x.Name or "") == str(material)]
                mat = found[0] if found else ifcopenshell.api.material.add_material(self.m, name=str(material))
                try:
                    ifcopenshell.api.material.unassign_material(self.m, products=[e])
                except Exception:  # nosec B110
                    pass
                ifcopenshell.api.material.assign_material(self.m, products=[e], type="IfcMaterial", material=mat)
            self.touch(e)

    def op_transform_elements(self, op):
        dx, dy, dz = _cs_num(op, "dx", 0.0), _cs_num(op, "dy", 0.0), _cs_num(op, "dz", 0.0)
        for e in self.elements(op):
            pl = getattr(e, "ObjectPlacement", None)
            if pl is None or not pl.is_a("IfcLocalPlacement") or not pl.RelativePlacement.is_a("IfcAxis2Placement3D"):
                raise DataspatiumError("element %d has no local placement to move" % e.id())
            c = list(pl.RelativePlacement.Location.Coordinates) + [0.0, 0.0, 0.0]
            pl.RelativePlacement.Location = self.point(c[0] + self.u(dx), c[1] + self.u(dy), c[2] + self.u(dz))
            self.touch(e)

    def op_delete_elements(self, op):
        """Delete elements; the doors and windows in an element's openings go with it, so nothing is left hanging in the air."""
        import ifcopenshell.api.root

        if op.get("confirm") is not True:
            raise DataspatiumError("deleting needs confirm: true, which the person gives")
        targets = self.elements(op)
        ids = {e.id() for e in targets}
        for e in targets:
            fillings = []
            for rel in getattr(e, "HasOpenings", None) or ():
                opening = rel.RelatedOpeningElement
                for f in getattr(opening, "HasFillings", None) or ():
                    if f.RelatedBuildingElement.id() not in ids:
                        fillings.append(f.RelatedBuildingElement)
            for f in fillings + [e]:
                rec = self.record(f, self.container(f))
                if f is not e:
                    rec["with"] = e.id()
                self.deleted.append(rec)
                self.changed.pop(f.id(), None)
                ifcopenshell.api.root.remove_product(self.m, product=f)

    def op_set_site(self, op):
        """The model's place on earth: the site's WGS 84 position (compound plane angles, every part signed), its height above the sea
        and its name, and with a crs the map conversion of the model context to that projected CRS (IFC4 and IFC4X3; IFC2X3 has none,
        which the report notes). The site goes into the changed list; a CRS or conversion that had to be made into the created list."""
        latitude = _cs_num(op, "latitude", unit="degrees")
        longitude = _cs_num(op, "longitude", unit="degrees")
        if not -90.0 <= latitude <= 90.0:
            raise DataspatiumError("latitude must be between -90 and 90 degrees")
        if not -180.0 <= longitude <= 180.0:
            raise DataspatiumError("longitude must be between -180 and 180 degrees")
        elevation = None if op.get("elevation") is None else _cs_num(op, "elevation")
        crs = str(op.get("crs") or "").strip().upper() or None
        eastings = northings = None
        if crs is not None:
            if not (crs.startswith("EPSG:") and crs[5:].isdigit()):
                raise DataspatiumError("crs must be an EPSG code such as EPSG:3006")
            eastings = _cs_num(op, "eastings")
            northings = _cs_num(op, "northings")
        elif op.get("eastings") is not None or op.get("northings") is not None:
            raise DataspatiumError("eastings and northings need a crs such as EPSG:3006")
        rotation = _cs_num(op, "rotation", 0.0, unit="degrees")
        site_name = str(op.get("site_name") or "").strip()[:255] or None
        site = self.site(site_name)
        site.RefLatitude = _cs_angle(latitude)
        site.RefLongitude = _cs_angle(longitude)
        if elevation is not None:
            site.RefElevation = self.u(elevation)
        if site_name:
            site.Name = site_name
        self.touch(site)
        if crs is None:
            return
        if self.m.schema == "IFC2X3":
            self.notes.append(
                "the map conversion to %s was skipped: IFC2X3 has no IfcMapConversion; the site's latitude, longitude and elevation were set"
                % crs
            )
            return
        self.map_conversion(crs, eastings, northings, 0.0 if elevation is None else elevation, rotation)

    def map_conversion(self, crs, eastings, northings, height, rotation):
        """One IfcProjectedCRS named by the EPSG code and one IfcMapConversion from the model context to it, made or updated, never
        doubled. Lengths come in metres and are written in the file's unit, which is also the map unit."""
        context = self.model_context()
        conversions = self.m.by_type("IfcMapConversion")
        conversion = next(
            (c for c in conversions if c.SourceCRS is not None and c.SourceCRS.id() == context.id()),
            conversions[0] if conversions else None,
        )
        target = (
            conversion.TargetCRS
            if conversion is not None
            and conversion.TargetCRS is not None
            and conversion.TargetCRS.is_a("IfcProjectedCRS")
            else None
        )
        if target is None:
            found = self.m.by_type("IfcProjectedCRS")
            target = found[0] if found else None
        datum, projection, zone = _cs_crs_facts(crs)
        if datum is None and self.m.schema == "IFC4":
            datum = ""  # IFC4 requires a datum; an empty identifier says the app does not know this code's
            self.notes.append(
                "the geodetic datum of %s is not known to the app; IFC4 requires one, so it is written empty" % crs
            )
        values = {
            "Name": crs,
            "GeodeticDatum": datum,
            "MapProjection": projection,
            "MapZone": zone,
            "MapUnit": self.length_unit(),
        }
        if target is None:
            target = self.m.create_entity("IfcProjectedCRS", **values)
            self.register(target, ref=False)
        else:
            for key, value in values.items():
                setattr(target, key, value)
            self.touch(target)
        angle = math.radians(rotation)
        values = {
            "SourceCRS": context,
            "TargetCRS": target,
            "Eastings": self.u(eastings),
            "Northings": self.u(northings),
            "OrthogonalHeight": self.u(height),
            "XAxisAbscissa": math.cos(angle),
            "XAxisOrdinate": math.sin(angle),
            "Scale": 1.0,
        }
        if conversion is None:
            conversion = self.m.create_entity("IfcMapConversion", **values)
            self.register(conversion, ref=False)
        else:
            for key, value in values.items():
                setattr(conversion, key, value)
            self.touch(conversion)

    def apply(self, ops):
        if not isinstance(ops, list):
            raise DataspatiumError("the change set must be a list of operations")
        if self.m.schema == "IFC2X3" and self.owner is None:
            raise DataspatiumError("the IFC2X3 file has no owner history to give new entities")
        previous = self.owner_settings()
        try:
            self.apply_all(ops)
        finally:
            self.restore_owner_settings(previous)
        if self.owner is not None:
            # The API makes some relationships without an owner history; IFC2X3 requires one on every IfcRoot.
            for e in self.m.by_type("IfcRoot"):
                if e.OwnerHistory is None:
                    e.OwnerHistory = self.owner

    def apply_all(self, ops):
        for i, op in enumerate(ops):
            name = op.get("tool") if isinstance(op, dict) else None
            fn = getattr(self, "op_" + str(name), None) if name else None
            if fn is None:
                raise DataspatiumError("step %d: unknown operation %r" % (i + 1, name))
            try:
                fn(op)
            except DataspatiumError as exc:
                raise DataspatiumError("step %d (%s): %s" % (i + 1, name, exc))
            except Exception as exc:
                raise DataspatiumError("step %d (%s): %s: %s" % (i + 1, name, type(exc).__name__, exc))

    def findings(self, limit=50):
        """The schema check of the whole model: (findings, number of errors)."""
        import ifcopenshell.validate

        logger = ifcopenshell.validate.json_logger()
        try:
            ifcopenshell.validate.validate(self.m, logger, express_rules=False)
        except Exception as exc:
            return [
                {
                    "level": "error",
                    "ifc_class": None,
                    "id": None,
                    "attribute": None,
                    "message": "validation failed: %s" % exc,
                }
            ], 1
        out = []
        errors = 0
        for s in logger.statements:
            if not isinstance(s, dict):
                continue
            level = str(s.get("level", "")).lower()
            inst = s.get("instance")
            if level == "error":
                errors += 1
            if len(out) < limit:
                out.append(
                    {
                        "level": level,
                        "ifc_class": inst.is_a() if inst is not None else None,
                        "id": inst.id() if inst is not None else None,
                        "attribute": _ifc_text(s.get("attribute")),
                        "message": str(s.get("message", "")),
                    }
                )
        return out, errors


# ---- the building's topology (decision F46 a) -------------------------------------------------------
# The walls' centrelines per storey become rooms with shapely (which comes with IfcOpenShell): the line ends are snapped to each
# other within a tolerance, the lines noded and polygonized. Rooms that share a stretch of boundary border each other, the walls
# along the rooms' union are the external walls with the compass sector they face, and the lines' free ends are the open ends
# that a closed storey cannot have. Lengths are metres, coordinates the model's plan.

TOPOLOGY_MAX_WALLS = 2000
TOPOLOGY_MIN_ROOM = 0.5  # m²; smaller polygons are slivers between lines, not rooms
TOPOLOGY_MIN_WIDTH = 0.5  # m; so are narrower ones, such as the gap between the layers of a wall
_FACINGS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")


def _topo_north(model):
    """(a, b, source): the model's plan turned to the map, east = a*dx - b*dy and north = b*dx + a*dy. From IfcMapConversion's
    XAxisAbscissa and XAxisOrdinate when the file has one (it takes precedence over TrueNorth, as IFC 4.3 says), else from the
    model context's TrueNorth, else the model's +y is north."""
    contexts = [
        c
        for c in model.by_type("IfcGeometricRepresentationContext")
        if not c.is_a("IfcGeometricRepresentationSubContext")
    ]
    context = next((c for c in contexts if (c.ContextType or "Model") == "Model"), contexts[0] if contexts else None)
    try:
        conversions = model.by_type("IfcMapConversion")
    except Exception:  # IFC2X3 has no IfcMapConversion
        conversions = []
    own = [
        c for c in conversions if context is not None and c.SourceCRS is not None and c.SourceCRS.id() == context.id()
    ]
    conversion = own[0] if own else (conversions[0] if len(conversions) == 1 else None)
    if conversion is not None:
        a = 1.0 if conversion.XAxisAbscissa is None else float(conversion.XAxisAbscissa)
        b = 0.0 if conversion.XAxisOrdinate is None else float(conversion.XAxisOrdinate)
        if math.hypot(a, b) > 0:
            return a / math.hypot(a, b), b / math.hypot(a, b), "map"
    north = getattr(context, "TrueNorth", None) if context is not None else None
    if north is not None:
        r = [float(v) for v in north.DirectionRatios] + [0.0, 0.0]
        if math.hypot(r[0], r[1]) > 0:
            return r[1] / math.hypot(r[0], r[1]), r[0] / math.hypot(r[0], r[1]), "true_north"
    return 1.0, 0.0, "model"


def _topo_point(p):
    """A shapely point of (x, y)."""
    from shapely.geometry import Point

    return Point(float(p[0]), float(p[1]))


def _topo_facing(dx, dy, north):
    """The compass sector (N, NE, ... NW) a direction in the plan points to."""
    a, b = north[0], north[1]
    bearing = math.degrees(math.atan2(a * dx - b * dy, b * dx + a * dy)) % 360.0
    return _FACINGS[int((bearing + 22.5) // 45.0) % 8]


def _topo_curve(item):
    """The (x, y) points of an axis curve in its own coordinates: an IfcPolyline, an IfcIndexedPolyCurve or an IfcTrimmedCurve of an
    IfcLine; None for another curve."""
    if item.is_a("IfcPolyline"):
        return [(float(p.Coordinates[0]), float(p.Coordinates[1])) for p in item.Points]
    if item.is_a("IfcIndexedPolyCurve"):
        coords = [(float(c[0]), float(c[1])) for c in item.Points.CoordList]
        if not getattr(item, "Segments", None):
            return coords
        out = []
        for segment in item.Segments:
            for i in segment.wrappedValue:
                if not out or out[-1] != coords[int(i) - 1]:
                    out.append(coords[int(i) - 1])
        return out
    if item.is_a("IfcTrimmedCurve") and item.BasisCurve.is_a("IfcLine"):
        line = item.BasisCurve
        p0 = [float(v) for v in line.Pnt.Coordinates]
        o = [float(v) for v in line.Dir.Orientation.DirectionRatios]
        step = float(line.Dir.Magnitude) / (math.sqrt(sum(v * v for v in o)) or 1.0)

        def at(trim):
            for t in trim:
                if hasattr(t, "is_a") and t.is_a("IfcCartesianPoint"):
                    return float(t.Coordinates[0]), float(t.Coordinates[1])
            for t in trim:
                u = float(getattr(t, "wrappedValue", t))  # an IfcParameterValue along the line
                return p0[0] + u * step * o[0], p0[1] + u * step * o[1]
            return None

        ends = at(item.Trim1), at(item.Trim2)
        return list(ends) if ends[0] and ends[1] else None
    return None


def _topo_axis(wall, scale):
    """The wall's 'Axis' representation in plan, in metres in world coordinates through its placement; None without one."""
    import ifcopenshell.util.placement as placement

    rep = getattr(wall, "Representation", None)
    for r in rep.Representations if rep is not None else ():
        if (r.RepresentationIdentifier or "") != "Axis":
            continue
        for item in r.Items or ():
            pts = _topo_curve(item)
            if pts and len(pts) >= 2:
                m = (getattr(placement, "get_local_placement", None) or placement.get_placement)(
                    wall.ObjectPlacement
                )  # get_placement since IfcOpenShell 0.9.1
                return [
                    ((m[0][0] * x + m[0][1] * y + m[0][3]) * scale, (m[1][0] * x + m[1][1] * y + m[1][3]) * scale)
                    for x, y in pts
                ]
    return None


def _topo_thickness(wall, scale):
    """The wall's thickness in metres: the narrow side of an extruded rectangle, else its material layers; None when unknown."""
    rep = getattr(wall, "Representation", None)
    for r in rep.Representations if rep is not None else ():
        for item in r.Items or ():
            if item.is_a("IfcExtrudedAreaSolid") and item.SweptArea.is_a("IfcRectangleProfileDef"):
                return min(float(item.SweptArea.XDim), float(item.SweptArea.YDim)) * scale
    try:
        import ifcopenshell.util.element as el

        mat = el.get_material(wall)
        layers = mat.ForLayerSet if mat is not None and mat.is_a("IfcMaterialLayerSetUsage") else mat
        if layers is not None and layers.is_a("IfcMaterialLayerSet"):
            return sum(float(x.LayerThickness or 0) for x in layers.MaterialLayers) * scale or None
    except Exception:  # nosec B110
        pass
    return None


def _topo_settings():
    import ifcopenshell.geom

    settings = ifcopenshell.geom.settings()
    settings.set("use-world-coords", True)
    try:
        settings.set("disable-opening-subtractions", True)  # the footprint needs no openings, and the booleans are slow
    except Exception:  # nosec B110
        pass
    return settings


def _topo_footprint(wall, settings):
    """(centreline, width) from the body's footprint: its vertices (world coordinates, metres) projected to the plan, their minimum
    rotated rectangle and its long axis."""
    import ifcopenshell.geom
    import ifcopenshell.util.shape as shape_util
    import shapely

    verts = shape_util.get_vertices(ifcopenshell.geom.create_shape(settings, wall).geometry)  # ty: ignore[invalid-argument-type, unresolved-attribute]
    if len(verts) < 2:
        return None, None
    rect = shapely.oriented_envelope(shapely.MultiPoint([(float(v[0]), float(v[1])) for v in verts]))
    if rect.geom_type == "LineString":
        return [rect.coords[0], rect.coords[-1]], 0.0
    if rect.geom_type != "Polygon" or rect.is_empty:
        return None, None
    c = list(rect.exterior.coords)

    def mid(p, q):
        return (p[0] + q[0]) / 2.0, (p[1] + q[1]) / 2.0

    if math.dist(c[0], c[1]) >= math.dist(c[1], c[2]):
        return [mid(c[0], c[3]), mid(c[1], c[2])], math.dist(c[1], c[2])
    return [mid(c[0], c[1]), mid(c[3], c[2])], math.dist(c[0], c[1])


def _topo_cross(p, d, a, b):
    """(t, x): where the line through p along the unit vector d crosses the line through a and b, p + t * d; None when parallel."""
    rx, ry = b[0] - a[0], b[1] - a[1]
    den = d[0] * ry - d[1] * rx
    if abs(den) < 1e-9 * (math.hypot(rx, ry) or 1.0):
        return None
    t = ((a[0] - p[0]) * ry - (a[1] - p[1]) * rx) / den
    return t, (round(p[0] + t * d[0], 6), round(p[1] + t * d[1], 6))


def _topo_pairs(pts, radius):
    """The pairs (distance, a, b) of points at most radius apart, closest first, found on a grid of cells radius wide."""
    cells = {}
    size = max(radius, 1e-6)
    out = []
    for n, p in enumerate(pts):
        cx, cy = math.floor(p[0] / size), math.floor(p[1] / size)
        for cell in [(cx + dx, cy + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)]:
            out.extend((math.dist(pts[m], p), m, n) for m in cells.get(cell, ()) if math.dist(pts[m], p) <= radius)
        cells.setdefault((cx, cy), []).append(n)
    return sorted(out)


def _topo_snap(lines, tol, widths=None):
    """The lines with their ends snapped, in three steps. Ends that coincide within a centimetre meet at their mean. Another end goes
    along its own line, extended or trimmed, to the nearest crossing with a line near it (a T junction; or a corner, where that
    line's free end goes there too, as when both walls of a corner stop at the other's face), moving at most half the thickness of
    the wall it meets plus 0.05 m, and never more than tol. Ends still free pair up within tol, closest first, unless their walls run
    side by side as the layers of a wall do. A point that lands inside a line is inserted in it, so that noding joins the two exactly."""
    from shapely.geometry import LineString, Point
    from shapely.strtree import STRtree

    out = [[(round(float(c[0]), 6), round(float(c[1]), 6)) for c in line] for line in lines]
    reach = [min(tol, float(w or 0.2) / 2.0 + 0.05) for w in (widths or [None] * len(out))]
    ends = [(i, k) for i in range(len(out)) for k in (0, -1)]

    def end(m):
        return out[ends[m][0]][ends[m][1]]

    def direction(m):
        """The unit vector along the line out of its end m, or None."""
        i, k = ends[m]
        p, q = out[i][k], (out[i][1] if k == 0 else out[i][-2])
        n = math.dist(p, q)
        return ((p[0] - q[0]) / n, (p[1] - q[1]) / n) if n > 0 else None

    def meet(group):
        mean = (
            round(sum(end(m)[0] for m in group) / len(group), 6),
            round(sum(end(m)[1] for m in group) / len(group), 6),
        )
        for m in group:
            out[ends[m][0]][ends[m][1]] = mean

    parent = list(range(len(ends)))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for _, a, b in _topo_pairs([end(m) for m in range(len(ends))], 0.01):
        parent[find(a)] = find(b)
    groups = {}
    for m in range(len(ends)):
        groups.setdefault(find(m), []).append(m)
    free = {g[0] for g in groups.values() if len(g) == 1}
    for g in groups.values():
        if len(g) > 1:
            meet(g)
    geoms = [LineString(c) for c in out]
    tree = STRtree(geoms)
    inserted = {}
    for m in sorted(free):
        d = direction(m)
        if m not in free or d is None:
            continue  # taken to a corner by the other wall's end, or a line without length
        i, k = ends[m]
        p = end(m)
        best = None
        for j in (int(x) for x in tree.query(Point(p).buffer(2.0 * tol)) if int(x) != i):
            for a, b in zip(out[j], out[j][1:]):
                hit = _topo_cross(p, d, a, b)
                if hit is None or abs(hit[0]) > reach[j] or (best is not None and abs(hit[0]) >= best[0]):
                    continue
                corner = None
                off = LineString([a, b]).distance(Point(hit[1]))
                if off > 1e-6:  # beyond the other line's end: a corner, when that end is free and near enough
                    corner = 2 * j + (0 if math.dist(hit[1], out[j][0]) < math.dist(hit[1], out[j][-1]) else 1)
                    if off > reach[i] or corner not in free:
                        continue
                best = (abs(hit[0]), j, hit[1], corner)
        if best is None:
            continue
        _, j, x, corner = best
        free.discard(m)
        out[i][k] = x
        if corner is None:
            inserted.setdefault(j, []).append(x)
        else:
            free.discard(corner)
            out[j][ends[corner][1]] = x
    left = sorted(free)
    for _, a, b in _topo_pairs([end(m) for m in left], tol):
        ma, mb = left[a], left[b]
        if ma not in free or mb not in free:
            continue
        da, db = direction(ma), direction(mb)
        pa, pb = end(ma), end(mb)
        if (
            da
            and db
            and abs(da[0] * db[1] - da[1] * db[0]) < 0.17
            and abs((pb[0] - pa[0]) * da[1] - (pb[1] - pa[1]) * da[0]) > 0.05
        ):
            continue  # parallel within 10 degrees and side by side
        free.difference_update((ma, mb))
        meet([ma, mb])
    for j, points in inserted.items():
        first, last = out[j][0], out[j][-1]
        inner = sorted(set(out[j][1:-1]) | set(points), key=lambda c: geoms[j].project(Point(c)))
        out[j] = [first] + [c for c in inner if c != first and c != last] + [last]
    return out


def _topo_outward(union, part, tol, north):
    """The compass sector a wall along the rooms' union faces: the normal of its longest piece there that points out of the rooms."""
    from shapely.geometry import Point

    pieces = [g for g in getattr(part, "geoms", [part]) if g.geom_type == "LineString" and g.length > 0]
    if not pieces:
        return None
    piece = max(pieces, key=lambda g: g.length)
    (x0, y0), (x1, y1) = piece.coords[0][:2], piece.coords[-1][:2]
    n = math.hypot(x1 - x0, y1 - y0)
    if n == 0:
        return None
    nx, ny = -(y1 - y0) / n, (x1 - x0) / n
    mid = piece.interpolate(0.5, normalized=True)
    for eps in (0.05, tol + 0.05):
        left = union.covers(Point(mid.x + nx * eps, mid.y + ny * eps))
        right = union.covers(Point(mid.x - nx * eps, mid.y - ny * eps))
        if left != right:
            return _topo_facing(-nx, -ny, north) if left else _topo_facing(nx, ny, north)
    return None


def _topo_plan(walls, tol, north=(1.0, 0.0, "model"), shapes=False):
    """One storey's plan from its walls' centrelines, with shapely alone: `walls` are dicts {"id", "guid", "name", "line": [(x, y),
    ...], "width"} in metres (width may be None). Rooms are the polygons over TOPOLOGY_MIN_ROOM and TOPOLOGY_MIN_WIDTH. A wall
    belongs to a room, and is external, when it runs along the room's boundary (or the union's) for longer than one that only meets
    it there; two rooms are neighbours when their boundaries share such a stretch. With shapes, every room also has its "polygon"
    (shapely, counter-clockwise) and its "net_area" inside the walls' faces, for create_spaces; neither goes into JSON."""
    from shapely.geometry import LineString
    from shapely.geometry.polygon import orient
    from shapely.ops import polygonize_full, unary_union
    from shapely.strtree import STRtree

    snapped = _topo_snap([w["line"] for w in walls], tol, [w.get("width") for w in walls])
    keep = [i for i, c in enumerate(snapped) if LineString(c).length > 1e-6]
    if not keep:
        return {"rooms": [], "external": [], "dangles": [], "closed": False, "dangling": []}  # Dataregium
    walls = [walls[i] for i in keep]
    geoms = [LineString(snapped[i]) for i in keep]
    noded = unary_union(geoms)
    edges = [g for g in getattr(noded, "geoms", [noded]) if g.geom_type == "LineString"]
    degree = {}
    for e in edges:
        for c in (e.coords[0], e.coords[-1]):
            key = (round(c[0], 6), round(c[1], 6))
            degree[key] = degree.get(key, 0) + 1
    dangles = sorted([round(x, 3), round(y, 3)] for (x, y), n in degree.items() if n == 1)
    # Dataregium: the walls whose line ends where an end dangles, by GlobalId.
    loose = {key for key, n in degree.items() if n == 1}
    dangling = sorted(
        {
            walls[i].get("guid")
            for i, g in enumerate(geoms)
            for c in (g.coords[0], g.coords[-1])
            if (round(c[0], 6), round(c[1], 6)) in loose
        }
        - {None}
    )
    polygons = list(polygonize_full(edges)[0].geoms)
    rooms = sorted(
        (p for p in polygons if p.area > TOPOLOGY_MIN_ROOM and not p.buffer(-TOPOLOGY_MIN_WIDTH / 2.0).is_empty),
        key=lambda p: (round(p.centroid.y), round(p.centroid.x, 6), -round(p.area, 6)),
    )  # a room around another comes first
    tree = STRtree(geoms)
    meets = 2.0 * tol + 0.01  # a wall that only meets a boundary runs at most 2 * tol inside its buffer

    def along(zone):
        out = []
        for j in tree.query(zone):
            part = geoms[int(j)].intersection(zone)
            if part.length > meets:
                out.append((int(j), part))
        return out

    neighbours = [set() for _ in rooms]
    room_tree = STRtree(rooms)
    for i, r in enumerate(rooms):
        for k in (int(x) for x in room_tree.query(r)):
            if k > i and r.boundary.intersection(rooms[k].boundary).length > meets:
                neighbours[i].add(k)
                neighbours[k].add(i)
    out_rooms = []
    for i, r in enumerate(rooms):
        members = along(r.boundary.buffer(tol))
        rec = {
            "index": i + 1,
            "area": round(r.area, 2),
            "perimeter": round(r.length, 2),
            "walls": sorted({walls[j]["id"] for j, _ in members}),
            "neighbours": sorted(k + 1 for k in neighbours[i]),
        }
        if shapes:
            # inside the faces: the outline less a band of half each wall's thickness along it
            bands = unary_union(
                [geoms[j].buffer(float(walls[j].get("width") or 0.2) / 2.0, cap_style="flat") for j, _ in members]
            )
            rec["polygon"], rec["net_area"] = orient(r, sign=1.0), r.difference(bands).area
        out_rooms.append(rec)
    external = []
    if rooms:
        union = unary_union(polygons)  # with the slivers between the layers of a wall, which are inside too
        for j, part in along(union.boundary.buffer(tol)):
            facing = _topo_outward(union, part, tol, north)
            if facing:
                external.append(
                    {
                        "wall": walls[j]["id"],
                        "guid": walls[j].get("guid"),
                        "name": walls[j].get("name"),
                        "facing": facing,
                        "length": round(part.length, 2),
                    }
                )
        external.sort(key=lambda e: (_FACINGS.index(e["facing"]), e["wall"]))
    return {
        "rooms": out_rooms,
        "external": external,
        "dangles": dangles,
        "closed": bool(rooms) and not dangles,
        "dangling": dangling,  # Dataregium
    }


def _topo_elevation(storey, scale):
    if storey.Elevation is not None:
        return float(storey.Elevation) * scale
    try:
        import ifcopenshell.util.placement as placement

        return (
            float(
                (getattr(placement, "get_local_placement", None) or placement.get_placement)(storey.ObjectPlacement)[2][
                    3
                ]
            )
            * scale
        )  # get_placement since 0.9.1
    except Exception:
        return 0.0


def _ifc_topology(model, tolerance=None, storeys=None, shapes=False):
    """The building's topology per storey (decision F46 a), as a list in the storeys' order of elevation:

        {"storey", "elevation" (m), "rooms": [{"index" (from 1), "area" (m²), "perimeter" (m), "walls": [wall ids], "neighbours":
         [room indices]}], "external": [{"wall", "guid", "name", "facing" (N, NE, E, SE, S, SW, W, NW), "length" (m)}], "dangles":
         [[x, y], ...] (open wall ends, metres), "closed" (at least one room and nothing dangles), "walls" (on the storey), "unread"
         (walls whose centreline could not be read), "tolerance" (m), "north" (map, true_north or model)}

    A wall's centreline is its 'Axis' representation through its placement, else the long axis of its body's footprint
    (ifcopenshell.geom). The ends are snapped within `tolerance` metres (by default half the storey's thickest wall plus 0.05 m).
    `storeys` (names) limits the storeys read. At most TOPOLOGY_MAX_WALLS walls. With shapes (for create_spaces, never for JSON) the
    rooms carry their polygons and net areas (_topo_plan) and every storey its entity as "_storey".
    """
    import ifcopenshell.util.unit

    try:
        scale = float(ifcopenshell.util.unit.calculate_unit_scale(model) or 1.0)  # metres per file unit
    except Exception:
        scale = 1.0
    north = _topo_north(model)
    chosen = []
    for s in model.by_type("IfcBuildingStorey"):
        if storeys is not None and _ifc_text(s.Name) not in storeys:
            continue
        chosen.append(
            (
                s,
                [
                    e
                    for rel in (getattr(s, "ContainsElements", None) or ())
                    for e in (rel.RelatedElements or ())
                    if e.is_a("IfcWall")
                ],
            )
        )
    total = sum(len(walls) for _, walls in chosen)
    if total > TOPOLOGY_MAX_WALLS:
        raise DataspatiumError("the topology reads at most %d walls; there are %d" % (TOPOLOGY_MAX_WALLS, total))
    settings = None
    out = []
    for s, walls in sorted(chosen, key=lambda x: _topo_elevation(x[0], scale)):
        read, widths, unread = [], [], 0
        missed = []  # Dataregium
        for w in walls:
            try:
                line = _topo_axis(w, scale)
                width = _topo_thickness(w, scale) if line else None
            except Exception:
                line = None
            if not line:
                try:
                    if settings is None:
                        settings = _topo_settings()
                    line, width = _topo_footprint(w, settings)
                except Exception:
                    line = None
            if not line or math.dist(line[0], line[-1]) <= 1e-6:
                unread += 1
                missed.append(getattr(w, "GlobalId", None))  # Dataregium
                continue
            read.append(
                {
                    "id": w.id(),
                    "guid": getattr(w, "GlobalId", None),
                    "name": _ifc_text(getattr(w, "Name", None)),
                    "line": line,
                    "width": width,
                }
            )
            if width:
                widths.append(width)
        tol = float(tolerance) if tolerance else max([x for x in widths if x <= 1.0] or [0.2]) / 2.0 + 0.05
        rec = {"storey": _ifc_text(s.Name), "elevation": round(_topo_elevation(s, scale), 3)}
        rec.update(_topo_plan(read, tol, north, shapes))
        rec.update({"walls": len(walls), "unread": unread, "tolerance": round(tol, 3), "north": north[2]})
        rec["unread_walls"] = missed  # Dataregium
        if shapes:
            rec["_storey"] = s
        out.append(rec)
    return out


# ---- the right IFC class (decision B-57.2) ------------------------------------------------------------
# In native IFC the class is the classification (decision B-59): the most specific entity with its PredefinedType, an ObjectType
# only for USERDEFINED, and a type object; a system the person names comes on top through set_classification. Of this part of the
# original only what _ChangeSet calls is copied: the app's read tools _ifc_class_search and _ifc_class_report are not.

# PredefinedTypes the IFC releases deprecate (bSI rule IFC102), by the file's schema family: never written, flagged in the search.
DEPRECATED_VALUES = {
    "IFC4": {
        "IfcWall": ("STANDARD", "POLYGONAL", "ELEMENTEDWALL"),
        "IfcWallType": ("STANDARD", "POLYGONAL", "ELEMENTEDWALL"),
    },
    "IFC4X3": {
        "IfcWall": ("STANDARD", "POLYGONAL"),
        "IfcWallType": ("STANDARD", "POLYGONAL"),
        "IfcSpace": ("INTERNAL", "EXTERNAL"),
        "IfcSpaceType": ("INTERNAL", "EXTERNAL"),
        "IfcBuildingElementProxy": ("PROVISIONFORSPACE", "PROVISIONFORVOID"),
    },
}


def _ifc_schema(name):
    """IfcOpenShell's definition of a schema by its name (IFC2X3, IFC4, IFC4X3_ADD2 ...), or by the one of its line that the app's
    IfcOpenShell carries (a file header's IFC4X3 or IFC2X3_TC1)."""
    import ifcopenshell

    upper = str(name or "").upper()
    for candidate in (str(name), next((s for s in IFC_NEW_SCHEMAS if upper.startswith(s.split("_")[0])), None)):
        try:
            return ifcopenshell.schema_by_name(candidate)
        except Exception:  # nosec B112
            continue
    raise DataspatiumError("unknown IFC schema %r; the app reads %s" % (name, ", ".join(IFC_NEW_SCHEMAS)))


def _ifc_declaration(schema, name):
    """A declaration of the schema by name; None for one it lacks."""
    try:
        return schema.declaration_by_name(str(name))
    except Exception:
        return None


def _ifc_enum_items(decl, attribute="PredefinedType"):
    """The items of an entity's enumeration attribute; None when the entity has no such attribute."""
    import ifcopenshell.util.attribute

    attr = next((a for a in decl.all_attributes() if a.name() == attribute), None)
    if attr is None:
        return None
    try:
        return list(ifcopenshell.util.attribute.get_enum_items(attr))
    except Exception:
        return None


def _ifc_concrete(decl):
    """The names of the non-abstract entities at or below a declaration, in order."""
    out, stack = set(), [decl]
    while stack:
        d = stack.pop()
        if not d.is_abstract():
            out.add(d.name())
        stack.extend(d.subtypes())
    return sorted(out)


# The schemas a new model can be written in (OB-06): the newest first, which is the default.
IFC_NEW_SCHEMAS = ("IFC4X3_ADD2", "IFC4", "IFC2X3")


# ---- the server's own, below the copy -----------------------------------------------------------------------------

SERVER = "Dataregium"  # the organisation and the application that the owner histories name beside the proposer
MAX_NOTES = 100
MAX_MESSAGE = 300
# How apply_all() above words the operation that failed: its step counted from 1, its tool, and why.
FAILED_STEP = re.compile(r"^step ([0-9]+)(?: \(([a-z_]+)\))?: (.*)$", re.DOTALL)


class ServerChangeSet(_ChangeSet):
    """``_ChangeSet`` as the server runs it: the owner histories that IfcOpenShell's API makes name the proposer and
    this server, as an IfcPersonAndOrganization and an IfcApplication found in the file from an earlier proposal or
    made in it once, instead of the file's own owner. That holds where the file records owners: always in IFC2X3, where
    every IfcRoot needs one and the original lends the file's, and in a later schema when the file has a user and an
    application, which IfcOpenShell's defaults would name; a file without owners gets none, as in the app. What the
    copy itself makes still gets the file's first owner history (``self.owner``), as in the app."""

    def __init__(self, model: Any, proposer: str) -> None:
        super().__init__(model)
        self.proposer = str(proposer or "unknown")[:255]
        self._owning: tuple[Any, Any] | None = None

    def owner_settings(self) -> Any:
        import ifcopenshell.api.owner.settings as settings

        if self.m.schema == "IFC2X3":
            if self.owner is None:
                return None
        elif not (self.m.by_type("IfcPersonAndOrganization") and self.m.by_type("IfcApplication")):
            return None
        previous = (settings.get_user, settings.get_application)
        settings.get_user = lambda _file: self.owning()[0]  # ty: ignore[invalid-assignment]
        settings.get_application = lambda _file: self.owning()[1]  # ty: ignore[invalid-assignment]
        return previous

    def _identification(self, actor: Any) -> Any:
        return actor.Id if self.m.schema == "IFC2X3" else actor.Identification

    def owning(self) -> tuple[Any, Any]:
        """The proposer as the user and this server as the application of an owner history."""
        if self._owning is not None:
            return self._owning
        import ifcopenshell.api.owner

        application = next(
            (
                found
                for found in self.m.by_type("IfcApplication")
                if found.ApplicationIdentifier == SERVER and found.Version == __version__
            ),
            None,
        )
        if application is None:
            organisation = ifcopenshell.api.owner.add_organisation(self.m, identification=SERVER, name=SERVER)
            application = ifcopenshell.api.owner.add_application(
                self.m,
                application_developer=organisation,
                version=__version__,
                application_full_name=SERVER,
                application_identifier=SERVER,
            )
        organisation = application.ApplicationDeveloper
        user = next(
            (
                found
                for found in self.m.by_type("IfcPersonAndOrganization")
                if found.TheOrganization.id() == organisation.id()
                and self._identification(found.ThePerson) == self.proposer
            ),
            None,
        )
        if user is None:
            named = "Id" if self.m.schema == "IFC2X3" else "Identification"
            person = self.m.create_entity("IfcPerson", **{named: self.proposer, "FamilyName": self.proposer})
            user = ifcopenshell.api.owner.add_person_and_organisation(self.m, person=person, organisation=organisation)
        self._owning = (user, application)
        return self._owning


def run(model: Any, ops: list[dict[str, Any]], *, proposer: str) -> dict[str, Any]:
    """The operations applied to ``model`` in their order, as the app applies them.

    The answer says how many operations there are and how many applied, the GlobalId of each created element by its
    ref (``created``), the GlobalIds of what they created or changed and is still there (``objects``) and of what they
    deleted (``removed``), the notes on what an operation could not do in the file's schema, and in ``failed`` the
    operation that failed: its index from 0, its tool and why, in the words of the copy, which may quote its
    arguments and the names in the file. The operations after it are not applied, as in the app.
    """
    changeset = ServerChangeSet(model, proposer)
    failed: dict[str, Any] | None = None
    try:
        changeset.apply(ops)
    except DataspatiumError as exc:
        failed = _failed(str(exc))
    removed = {str(record["guid"]) for record in changeset.deleted if record.get("guid")}
    made = [*changeset.created, *changeset.changed.values()]
    return {
        "count": len(ops),
        "applied": len(ops) if failed is None else int(failed["op"] or 0),
        "created": {
            str(record["ref"]): str(record["guid"])
            for record in changeset.created
            if record.get("ref") and record.get("guid")
        },
        "objects": sorted({str(record["guid"]) for record in made if record.get("guid")} - removed),
        "removed": sorted(removed),
        "notes": [str(note)[:MAX_MESSAGE] for note in changeset.notes[:MAX_NOTES]],
        "failed": failed,
    }


def _failed(message: str) -> dict[str, Any]:
    """The failed operation from the words of ``apply_all``; without an index and a tool when the file cannot take the
    operations at all, as an IFC2X3 file without an owner history."""
    match = FAILED_STEP.match(message)
    if match is None:
        return {"op": None, "tool": None, "error": message[:MAX_MESSAGE]}
    return {"op": int(match.group(1)) - 1, "tool": match.group(2), "error": match.group(3)[:MAX_MESSAGE]}
