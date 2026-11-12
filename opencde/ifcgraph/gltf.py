# This file was generated with the assistance of an AI coding tool.
"""glTF from IFC-LPG's geometry records (OB-37): one binary glTF per version, built on request and cached.

IFC-LPG's worker (``python -m ifc_db.spatial``) runs IfcOpenShell's iterator once per conversion and writes JSON
Lines: a header, each mesh once before the first product that uses it, each product with its mesh, its matrix to
project coordinates (16 numbers, column by column, as glTF's ``node.matrix``), its box and its storey, and an end
with the counts. This module turns such a file into a ``.glb``: every shared mesh becomes one glTF mesh and every
product a node that instances it, so a mesh that a hundred products share is in the file once; the nodes hang under
one node per storey, with the products outside a storey beside them; a root node turns the model from IFC's Z up to
glTF's Y up. ``lod=box`` gives the boxes instead: one unit cube that every product instances through a scaling
matrix, a few bytes per product, for an overview or a selection. ``classes`` and ``storey`` pick the products.

No library is used: a glTF file is JSON and a buffer of little-endian floats and integers, which ``struct`` writes.
"""

from __future__ import annotations

import json
import struct
from pathlib import Path
from typing import Any

from opencde import __version__

FORMAT = "ifc-lpg-geometry"
VERSION = 1
LODS = ("full", "box")
MAGIC = b"glTF"
_JSON, _BIN = 0x4E4F534A, 0x004E4942
_FLOAT, _UINT = 5126, 5125
_ARRAY, _ELEMENTS = 34962, 34963
_IDENTITY = (1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0)
# IFC has Z up, glTF Y up: x stays, y becomes z, z becomes -y (column by column).
_Z_UP_TO_Y_UP = [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, -1.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0]
_CUBE_VERTS = [0, 0, 0, 1, 0, 0, 1, 1, 0, 0, 1, 0, 0, 0, 1, 1, 0, 1, 1, 1, 1, 0, 1, 1]
_CUBE_FACES = [
    0, 2, 1, 0, 3, 2,  # bottom
    4, 5, 6, 4, 6, 7,  # top
    0, 1, 5, 0, 5, 4,  # front
    1, 2, 6, 1, 6, 5,  # right
    2, 3, 7, 2, 7, 6,  # back
    3, 0, 4, 3, 4, 7,  # left
]  # fmt: skip
_BOX_MATERIAL = {"name": "box", "diffuse": [0.6, 0.6, 0.6], "transparency": 0.4}
_SMALLEST = 1e-6  # a box with no extent along an axis still scales to something


class GeometryError(ValueError):
    """The records cannot be read, or ask for what they do not hold."""


class _Buffer:
    """The binary chunk, with a buffer view and an accessor per array."""

    def __init__(self) -> None:
        self.data = bytearray()
        self.views: list[dict[str, Any]] = []
        self.accessors: list[dict[str, Any]] = []

    def _view(self, payload: bytes, target: int) -> int:
        while len(self.data) % 4:
            self.data += b"\0"
        self.views.append({"buffer": 0, "byteOffset": len(self.data), "byteLength": len(payload), "target": target})
        self.data += payload
        return len(self.views) - 1

    def vec3(self, values: list[float]) -> int:
        count = len(values) // 3
        xs, ys, zs = values[0::3], values[1::3], values[2::3]
        view = self._view(struct.pack(f"<{len(values)}f", *values), _ARRAY)
        self.accessors.append(
            {
                "bufferView": view,
                "componentType": _FLOAT,
                "count": count,
                "type": "VEC3",
                "min": [min(xs), min(ys), min(zs)],
                "max": [max(xs), max(ys), max(zs)],
            }
        )
        return len(self.accessors) - 1

    def indices(self, values: list[int]) -> int:
        view = self._view(struct.pack(f"<{len(values)}I", *values), _ELEMENTS)
        self.accessors.append({"bufferView": view, "componentType": _UINT, "count": len(values), "type": "SCALAR"})
        return len(self.accessors) - 1


def _materials_of(mesh: dict[str, Any], materials: dict[tuple[Any, ...], int], out: list[dict[str, Any]]) -> list[int]:
    """The glTF material index for each of the mesh's materials, made once per distinct colour."""
    found: list[int] = []
    for material in mesh.get("materials") or ():
        diffuse = material.get("diffuse") or [0.8, 0.8, 0.8]
        transparency = material.get("transparency") or 0.0
        key = (material.get("name"), tuple(diffuse), transparency)
        if key not in materials:
            alpha = max(0.0, min(1.0, 1.0 - float(transparency)))
            entry: dict[str, Any] = {
                "name": material.get("name") or "material",
                "pbrMetallicRoughness": {
                    "baseColorFactor": [*(max(0.0, min(1.0, float(c))) for c in diffuse[:3]), alpha],
                    "metallicFactor": 0.0,
                    "roughnessFactor": 0.9,
                },
                "doubleSided": True,
            }
            if alpha < 1.0:
                entry["alphaMode"] = "BLEND"
            out.append(entry)
            materials[key] = len(out) - 1
        found.append(materials[key])
    return found


def _mesh(record: dict[str, Any], buffer: _Buffer, materials: dict[tuple[Any, ...], int], out: list) -> dict[str, Any]:
    """One glTF mesh with a primitive per material, from a mesh record."""
    verts = [float(v) for v in record["verts"]]
    faces = [int(i) for i in record["faces"]]
    if len(verts) < 9 or len(verts) % 3 or len(faces) < 3 or len(faces) % 3:
        raise GeometryError(f"mesh {record.get('id')!r} is not triangles")
    if max(faces) * 3 >= len(verts):
        raise GeometryError(f"mesh {record.get('id')!r} points outside its vertices")
    attributes = {"POSITION": buffer.vec3(verts)}
    normals = record.get("normals")
    if normals and len(normals) == len(verts):
        attributes["NORMAL"] = buffer.vec3([float(n) for n in normals])
    by_material = _materials_of(record, materials, out)
    material_ids = record.get("material_ids") or []
    groups: dict[int | None, list[int]] = {}
    for face in range(len(faces) // 3):
        material = material_ids[face] if face < len(material_ids) else -1
        index = by_material[material] if 0 <= material < len(by_material) else None
        groups.setdefault(index, []).extend(faces[face * 3 : face * 3 + 3])
    primitives = []
    for index, triangles in groups.items():
        primitive: dict[str, Any] = {"attributes": attributes, "indices": buffer.indices(triangles), "mode": 4}
        if index is not None:
            primitive["material"] = index
        primitives.append(primitive)
    return {"name": str(record.get("id")), "primitives": primitives}


def _box_matrix(low: list[float], high: list[float]) -> list[float]:
    scale = [max(float(b) - float(a), _SMALLEST) for a, b in zip(low, high, strict=True)]
    return [scale[0], 0.0, 0.0, 0.0, 0.0, scale[1], 0.0, 0.0, 0.0, 0.0, scale[2], 0.0, *map(float, low), 1.0]


def _records(path: Path):
    """The records, one by one, with the file's shape checked as it is read."""
    with path.open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            try:
                record = json.loads(line)
            except ValueError as exc:
                raise GeometryError(f"line {number} is no JSON") from exc
            if not isinstance(record, dict) or "t" not in record:
                raise GeometryError(f"line {number} is of no known kind")
            if number == 1 and (
                record["t"] != "h" or record.get("format") != FORMAT or record.get("version") != VERSION
            ):
                raise GeometryError(f"the file is not {FORMAT} version {VERSION}")
            yield record


def build_glb(
    records: Path, *, lod: str = "full", classes: set[str] | None = None, storey: str | None = None
) -> tuple[bytes, dict[str, Any]]:
    """The ``.glb`` of the products the filters keep, and a summary (``products``, ``meshes``, ``bytes``)."""
    if lod not in LODS:
        raise GeometryError(f"lod is one of {', '.join(LODS)}")
    buffer = _Buffer()
    materials: dict[tuple[Any, ...], int] = {}
    gltf_materials: list[dict[str, Any]] = []
    meshes: list[dict[str, Any]] = []
    mesh_records: dict[str, dict[str, Any]] = {}  # kept until a product needs them, so unused ones cost no bytes
    mesh_index: dict[str, int] = {}
    nodes: list[dict[str, Any]] = []
    storeys: dict[str | None, list[int]] = {}
    header: dict[str, Any] = {}
    end: dict[str, Any] | None = None
    box_mesh: int | None = None
    for record in _records(records):
        kind = record["t"]
        if kind == "h":
            header = record
        elif kind == "m":
            if lod == "full":
                mesh_records[str(record.get("id"))] = record
        elif kind == "p":
            if classes is not None and record.get("class") not in classes:
                continue
            if storey is not None and record.get("storey") != storey:
                continue
            if lod == "box":
                if box_mesh is None:
                    cube = {"id": "box", "verts": _CUBE_VERTS, "faces": _CUBE_FACES, "material_ids": [0] * 12}
                    meshes.append(_mesh({**cube, "materials": [_BOX_MATERIAL]}, buffer, materials, gltf_materials))
                    box_mesh = len(meshes) - 1
                mesh, matrix = box_mesh, _box_matrix(record["bbox_min"], record["bbox_max"])
            else:
                mesh_id = str(record.get("mesh"))
                if mesh_id not in mesh_index:
                    if mesh_id not in mesh_records:
                        raise GeometryError(f"product {record.get('global_id')!r} uses a mesh the file lacks")
                    meshes.append(_mesh(mesh_records.pop(mesh_id), buffer, materials, gltf_materials))
                    mesh_index[mesh_id] = len(meshes) - 1
                mesh = mesh_index[mesh_id]
                matrix = [float(v) for v in record.get("matrix") or _IDENTITY]
                if len(matrix) != 16:
                    raise GeometryError(f"product {record.get('global_id')!r} has no matrix of 16 numbers")
            node: dict[str, Any] = {
                "name": str(record.get("global_id")),
                "mesh": mesh,
                "extras": {"class": record.get("class"), "step": record.get("step"), "storey": record.get("storey")},
            }
            if tuple(matrix) != _IDENTITY:
                node["matrix"] = matrix
            nodes.append(node)
            storeys.setdefault(record.get("storey"), []).append(len(nodes) - 1)
        elif kind == "end":
            end = record
        elif kind != "x":
            raise GeometryError(f"a record of kind {kind!r} is unknown")
    if end is None:
        raise GeometryError("the file is cut short: it has no end")
    # The storey nodes, the loose products and the root above them all.
    children: list[int] = []
    for guid, members in storeys.items():
        if guid is None:
            children.extend(members)
        else:
            nodes.append({"name": guid, "children": members, "extras": {"storey": guid}})
            children.append(len(nodes) - 1)
    nodes.append({"name": "project", "children": children, "matrix": _Z_UP_TO_Y_UP})
    document: dict[str, Any] = {
        "asset": {
            "version": "2.0",
            "generator": f"Dataregium {__version__}",
            "extras": {
                "format": FORMAT,
                "schema": header.get("schema"),
                "ifcopenshell": header.get("ifcopenshell"),
                "units": header.get("units"),
                "coordinates": header.get("coordinates"),
                "source_sha256": (header.get("source") or {}).get("sha256"),
                "lod": lod,
                "products": sum(len(members) for members in storeys.values()),
                "failed": end.get("failed", 0),
            },
        },
        "scene": 0,
        "scenes": [{"nodes": [len(nodes) - 1]}],
        "nodes": nodes,
        "meshes": meshes,
        "materials": gltf_materials,
        "accessors": buffer.accessors,
        "bufferViews": buffer.views,
        "buffers": [{"byteLength": len(buffer.data)}],
    }
    if not meshes:
        for key in ("meshes", "materials", "accessors", "bufferViews", "buffers"):
            document.pop(key)
    return _pack(document, bytes(buffer.data)), {
        "products": document["asset"]["extras"]["products"],
        "meshes": len(meshes),
    }


def _pack(document: dict[str, Any], binary: bytes) -> bytes:
    text = json.dumps(document, separators=(",", ":"), allow_nan=False).encode("utf-8")
    text += b" " * (-len(text) % 4)
    binary += b"\0" * (-len(binary) % 4)
    chunks = struct.pack("<II", len(text), _JSON) + text
    if binary:
        chunks += struct.pack("<II", len(binary), _BIN) + binary
    return MAGIC + struct.pack("<II", 2, 12 + len(chunks)) + chunks


def read_glb(data: bytes) -> tuple[dict[str, Any], bytes]:
    """The JSON document and the binary chunk of a ``.glb`` (for the tests and the checks)."""
    if data[:4] != MAGIC or len(data) < 20:
        raise GeometryError("not a glTF binary")
    version, length = struct.unpack("<II", data[4:12])
    if version != 2 or length != len(data):
        raise GeometryError("not a glTF 2.0 binary of its stated length")
    offset, document, binary = 12, None, b""
    while offset < length:
        size, kind = struct.unpack("<II", data[offset : offset + 8])
        payload = data[offset + 8 : offset + 8 + size]
        if kind == _JSON:
            document = json.loads(payload.decode("utf-8"))
        elif kind == _BIN:
            binary = payload
        offset += 8 + size
    if document is None:
        raise GeometryError("the glTF has no JSON chunk")
    return document, binary
