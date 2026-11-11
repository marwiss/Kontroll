# This file was generated with the assistance of an AI coding tool.
"""Dataspatium's write tools on an IFC model, with Dataspatium's own code (ADR 0021).

A copy of Dataspatium's class ``_ChangeSet`` (``python/dataspatium.py``, branch f43, commit 2173d22 of 2026-11-11)
and the module-level helpers it calls, kept in step by hand, so that one list of operations gives the same model in
the app and on the server. A change set that carries the operations as ``ops`` (``documents/changes.py``) is tried by
the apply worker (``apply.py``), which runs them with :func:`run` on the base version's file before its changes. The
operations are the AI's write tools in the app: ``create_storeys_and_grid``, ``create_wall``, ``create_slab``,
``create_roof``, ``create_opening``, ``set_properties``, ``set_classification``, ``assign``, ``transform_elements``,
``delete_elements`` and ``set_site``, each a JSON object with its tool's name as ``tool`` and its arguments beside it.
Lengths are metres, scaled to the file's unit. A wall, a slab, a roof or an opening (or the door or window that fills
it) gets the ref ``new-1``, ``new-2`` … in the order of the operations that create them (``_ChangeSet.CREATES``). An
operation names an element by its GlobalId, by its STEP id only where no GlobalId reaches it, or by such a ref (the
owner's decision F34 a, elements named by GlobalId, which the app's copy has too), and a storey by its name. Geometry
is raw entities, never ``ifcopenshell.geom``; nothing depends on Pyodide.

Against the original only this differs, so that the next copy is a diff away:

- the imports: ``math`` and ``sys``, which the original imports at the top of its module, are imported here;
- the error class: ``DataspatiumError`` keeps its name and its base, with a docstring of its own;
- ``_ChangeSet.MAX_PROPOSAL`` and ``_ChangeSet.proposal`` are left out: they lower the operations to attribute-level
  changes with the app's ``_Proposal``, which is not copied, since the server applies the operations themselves;
- the owner settings: :class:`ServerChangeSet`, below the copy, overrides ``owner_settings``, so that the owner
  histories IfcOpenShell's API makes name the proposer and this server instead of the file's own owner;
- ruff formats the copy in lines of 120 characters and lets its idioms be (``pyproject.toml``), and seven comments
  quiet bandit (``# nosec B110`` and ``B112``, five) and ty (``# ty: ignore[invalid-assignment]``, two); no statement
  changed.
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

    CREATES = ("create_wall", "create_slab", "create_roof", "create_opening")
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
            ordered = sorted(storeys, key=lambda s: float(s.Elevation or 0))
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

    # -- the file's structure
    def root(self, ifc_class, name):
        import ifcopenshell.guid

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

    @staticmethod
    def predefined(e, value):
        try:
            e.PredefinedType = value
        except Exception:  # nosec B110
            pass

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

    def prism(self, outline, height, z0=0.0):
        """A closed outline of (x, y) points extruded height along Z from z0."""
        pts = [self.point(x, y) for x, y in outline]
        if outline[0] != outline[-1]:
            pts.append(pts[0])
        profile = self.m.createIfcArbitraryClosedProfileDef("AREA", None, self.m.createIfcPolyline(pts))
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
        self.predefined(wall, "STANDARD")
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
            profile = self.m.createIfcArbitraryClosedProfileDef(
                "AREA", None, self.m.createIfcPolyline([self.point(u, v) for u, v in face + face[:1]])
            )
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
        import ifcopenshell.api.classification

        system = str(op.get("system") or "").strip()
        name = str(op.get("name") or "").strip()
        if not system or not name:
            raise DataspatiumError("system and name are required")
        found = [c for c in self.m.by_type("IfcClassification") if str(c.Name or "") == system]
        classification = (
            found[0] if found else ifcopenshell.api.classification.add_classification(self.m, classification=system)
        )
        code = str(op.get("code") or "").strip() or None
        uri = str(op.get("uri") or "").strip() or None
        for e in self.elements(op):
            ref = ifcopenshell.api.classification.add_reference(
                self.m, products=[e], identification=code, name=name, classification=classification
            )
            if uri and ref is not None and hasattr(ref, "Location"):
                ref.Location = uri
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
