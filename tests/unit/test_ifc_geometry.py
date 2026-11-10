# This file was generated with the assistance of an AI coding tool.
"""glTF from IFC-LPG's geometry records (OB-37): the builder on the records of the fixture model, and the route's
announcement and guard. The route against a database is in ``tests/integration/test_ifc_geometry.py``."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from opencde.ifcgraph.gltf import GeometryError, build_glb, read_glb
from opencde.main import create_app
from tests.conftest import FIXTURES_DIR
from tests.unit.test_capabilities import make_settings

RECORDS = FIXTURES_DIR / "three_walls_geometry.jsonl"  # python -m ifc_lpg.spatial three_walls_gtin.ifc
WALLS = ("1Xezbq735AdBO_4DerG66G", "3eT96F_cnDsOufCEsotwtp", "3k3LbXmTfDWODxdSuyCGYE")


def test_every_product_is_a_node_that_instances_its_mesh_under_its_storey() -> None:
    data, summary = build_glb(RECORDS)
    assert summary == {"products": 3, "meshes": 3}
    document, binary = read_glb(data)
    assert document["asset"]["version"] == "2.0" and document["asset"]["extras"]["units"] == "m"
    assert document["asset"]["extras"]["source_sha256"] and document["asset"]["extras"]["lod"] == "full"
    products = [node for node in document["nodes"] if "mesh" in node]
    assert sorted(node["name"] for node in products) == sorted(WALLS)
    assert all(node["extras"]["class"] == "IfcWallStandardCase" and node["extras"]["storey"] for node in products)
    storeys = [node for node in document["nodes"] if "children" in node and node["name"] != "project"]
    assert len(storeys) == 1 and sorted(storeys[0]["children"]) == sorted(document["nodes"].index(n) for n in products)
    root = document["nodes"][document["scenes"][0]["nodes"][0]]
    assert root["name"] == "project" and root["matrix"][5] == 0.0 and root["matrix"][6] == -1.0, "Z up becomes Y up"
    assert len(document["meshes"]) == 3 and document["buffers"][0]["byteLength"] == len(binary)
    for mesh in document["meshes"]:
        for primitive in mesh["primitives"]:
            position = document["accessors"][primitive["attributes"]["POSITION"]]
            assert position["type"] == "VEC3" and position["count"] >= 8 and len(position["min"]) == 3
            indices = document["accessors"][primitive["indices"]]
            assert indices["componentType"] == 5125 and indices["count"] % 3 == 0 and "material" in primitive
    assert document["materials"][0]["pbrMetallicRoughness"]["baseColorFactor"][3] == 1.0
    assert len(data) % 4 == 0


def test_the_boxes_share_one_cube_and_the_filters_pick_the_products() -> None:
    data, summary = build_glb(RECORDS, lod="box")
    document, _ = read_glb(data)
    assert summary == {"products": 3, "meshes": 1} and len(document["meshes"]) == 1
    boxes = [node for node in document["nodes"] if "mesh" in node]
    assert all(node["mesh"] == 0 and node["matrix"][0] > 0 and node["matrix"][15] == 1.0 for node in boxes)
    assert document["materials"][0]["alphaMode"] == "BLEND", "a box is seen through"

    data, summary = build_glb(RECORDS, classes={"IfcWallStandardCase"})
    assert summary["products"] == 3
    data, summary = build_glb(RECORDS, classes={"IfcSlab"})
    assert summary == {"products": 0, "meshes": 0}
    document, binary = read_glb(data)
    assert "meshes" not in document and binary == b"" and document["scenes"] == [{"nodes": [0]}]
    first = json.loads(RECORDS.read_text(encoding="utf-8").splitlines()[-2])
    data, summary = build_glb(RECORDS, storey=first["storey"])
    assert summary["products"] == 3
    assert build_glb(RECORDS, storey="0NotAStorey00000000000")[1]["products"] == 0


def test_a_file_that_is_not_whole_or_not_this_format_is_refused(tmp_path: Path) -> None:
    lines = RECORDS.read_text(encoding="utf-8").splitlines()
    cut = tmp_path / "cut.jsonl"
    cut.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")
    with pytest.raises(GeometryError, match="no end"):
        build_glb(cut)
    other = tmp_path / "other.jsonl"
    other.write_text('{"t": "h", "format": "something-else", "version": 1}\n', encoding="utf-8")
    with pytest.raises(GeometryError, match="not ifc-lpg-geometry"):
        build_glb(other)
    with pytest.raises(GeometryError, match="lod"):
        build_glb(RECORDS, lod="points")
    with pytest.raises(GeometryError):
        read_glb(b"not a glb")


def test_the_geometry_is_announced_with_the_module_and_guarded(tmp_path: Path) -> None:
    with TestClient(create_app(make_settings(tmp_path, ifcgraph_enabled=True), startup_wait_seconds=0)) as client:
        announced = client.get("/.well-known/dataregium").json()["extensions"]["ifc_geometry"]
        assert announced == {
            "enabled": True,
            "url": "/documents/1.0/documents/{document_id}/versions/{version_index}/ifc-geometry",
            "format": "model/gltf-binary",
            "lods": ["full", "box"],
        }
        refused = client.get(f"/documents/1.0/documents/{'0' * 32}/versions/1/ifc-geometry")
        assert refused.status_code == 401 and refused.json()["code"] == "unauthenticated", "mounted, guarded"
    settings = make_settings(tmp_path, ifcgraph_enabled=True, ifcgraph_spatial=False)
    with TestClient(create_app(settings, startup_wait_seconds=0)) as client:
        assert client.get("/.well-known/dataregium").json()["extensions"]["ifc_geometry"] == {"enabled": False}
