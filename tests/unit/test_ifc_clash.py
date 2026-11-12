# This file was generated with the assistance of an AI coding tool.
"""The clash check: its worker on two files, and what a topic and a viewpoint get (ADR 0019). The routes are
proved against a database in ``tests/integration/test_ifc_clash.py``."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pytest

from opencde.documents.routes_clash import _topic_body, camera_looking_at
from tests.conftest import FIXTURES_DIR


def test_the_camera_looks_down_from_the_south_east_at_a_distance_set_by_the_size() -> None:
    near = camera_looking_at([10.0, 20.0, 3.0], None)
    assert near.camera_view_point.x > 10 and near.camera_view_point.y < 20 and near.camera_view_point.z > 3
    assert near.camera_up_vector.z == 1
    assert math.isclose(near.camera_direction.x, -near.camera_direction.y) and near.camera_direction.z < 0
    distance = math.dist(
        (10.0, 20.0, 3.0), (near.camera_view_point.x, near.camera_view_point.y, near.camera_view_point.z)
    )
    assert math.isclose(distance, 5.0, rel_tol=1e-6), "2 m of extent by default: 2 * 1.5 + 2"
    far = camera_looking_at([0.0, 0.0, 0.0], 100.0)
    assert math.isclose(
        math.dist((0, 0, 0), (far.camera_view_point.x, far.camera_view_point.y, far.camera_view_point.z)), 40.0
    )


def _pair() -> dict[str, Any]:
    element = {"document_id": "d", "version_index": 1, "id": 1, "guid": "1Xezbq735AdBO_4DerG66G", "type": "IfcWall"}
    return {
        "a": {**element, "name": "Wall 1", "storey": "Level 1"},
        "b": {**element, "guid": "3eT96F_cnDsOufCEsotwtp", "type": "IfcDuctSegment", "name": None, "storey": None},
        "kind": "intersection",
        "depth": 0.182,
        "distance": 0.0,
        "point": [12.431, 7.902, 6.35],
        "extent": None,
    }


def test_a_topic_takes_type_status_and_label_only_where_the_extensions_allow() -> None:
    plain = _topic_body(_pair(), {})
    assert plain.title == "IfcWall Wall 1 against IfcDuctSegment 3eT96F_cnDsOufCEsotwtp"
    assert plain.topic_type is None and plain.topic_status is None and plain.labels is None
    assert "182 mm" in (plain.description or "") and "no storey" in (plain.description or "")
    rich = _topic_body(_pair(), {"topic_type": ["Clash"], "topic_status": ["Open"], "topic_label": ["Clash"]})
    assert (rich.topic_type, rich.topic_status, rich.labels) == ("Clash", "Open", ["Clash"])


@pytest.fixture(scope="module")
def shifted_walls(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    """The wall fixture, and a copy with new GlobalIds whose walls are moved sideways and up, so that they clash."""
    pytest.importorskip("ifcopenshell", reason="the ifc-db extra is not installed")
    import ifcopenshell
    import ifcopenshell.guid

    folder = tmp_path_factory.mktemp("clash")
    a = FIXTURES_DIR / "three_walls_gtin.ifc"
    model = ifcopenshell.open(str(a))
    for wall in model.by_type("IfcWall"):
        wall.GlobalId = ifcopenshell.guid.new()
        location = wall.ObjectPlacement.RelativePlacement.Location
        x, y, z = location.Coordinates
        location.Coordinates = (x, y + 0.1, z + 0.3)
    b = folder / "shifted.ifc"
    model.write(str(b))
    return a, b


def test_the_worker_finds_the_wall_that_was_moved_into_another(shifted_walls: tuple[Path, Path]) -> None:
    pytest.importorskip("ifcclash", reason="the ifc-db extra is not installed")
    from opencde.ifcgraph.clash import check

    a, b = shifted_walls
    report = check(a, b, mode="intersection", tolerance=0.001, clearance=0.05, types_a=[], types_b=[], max_clashes=10)
    assert (report["set_a"], report["set_b"], report["missing"], report["truncated"]) == (3, 3, 0, False)
    assert report["count"] == len(report["clashes"]) >= 1
    clash = report["clashes"][0]
    assert clash["kind"] == "intersection" and clash["depth"] and clash["depth"] > 0.001
    assert clash["a"]["guid"] in {"1Xezbq735AdBO_4DerG66G", "3eT96F_cnDsOufCEsotwtp", "3k3LbXmTfDWODxdSuyCGYE"}
    assert clash["b"]["guid"] not in {"1Xezbq735AdBO_4DerG66G", "3eT96F_cnDsOufCEsotwtp", "3k3LbXmTfDWODxdSuyCGYE"}
    assert clash["a"]["type"].startswith("IfcWall") and clash["a"]["storey"] and len(clash["point"]) == 3
    assert isinstance(clash["a"]["id"], int)


def test_the_worker_counts_clearance_and_keeps_only_so_many(shifted_walls: tuple[Path, Path]) -> None:
    pytest.importorskip("ifcclash", reason="the ifc-db extra is not installed")
    from opencde.ifcgraph.clash import check

    a, b = shifted_walls
    report = check(
        a, b, mode="clearance", tolerance=0.001, clearance=0.5, types_a=["IfcWall"], types_b=[], max_clashes=2
    )
    assert report["mode"] == "clearance" and report["count"] == 2 and report["truncated"] is True
    assert all(c["kind"] == "clearance" and c["depth"] is None and c["distance"] >= 0 for c in report["clashes"])


def test_the_worker_runs_as_a_process_and_answers_on_stdout(shifted_walls: tuple[Path, Path]) -> None:
    pytest.importorskip("ifcclash", reason="the ifc-db extra is not installed")
    import json
    import subprocess
    import sys

    a, b = shifted_walls
    done = subprocess.run(  # noqa: S603  # the arguments are this test's own
        [sys.executable, "-m", "opencde.ifcgraph.clash", str(a), str(b), "--tolerance", "0.001"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=300,
    )
    assert done.returncode == 0, done.stderr
    report = json.loads(done.stdout.strip().splitlines()[-1])
    assert report["count"] >= 1
    missing = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "opencde.ifcgraph.clash", str(a), str(b / "nowhere.ifc")],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=300,
    )
    assert missing.returncode == 2 and "error" in json.loads(missing.stderr.strip().splitlines()[-1])
