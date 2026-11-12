# This file was generated with the assistance of an AI coding tool.
"""The worker that names the element a finding of buildingSMART's rules is in, on a copy of the three walls that
breaks GEM111 (a polyline with a duplicated point): the class of each instance and the nearest rooted entity."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("ifcopenshell", reason="the ifc-db extra is not installed")

from opencde.ifcgraph import elements
from opencde.ifcgraph.elements import answer, main, steps_of
from tests.conftest import FIXTURES_DIR

WALL = "1Xezbq735AdBO_4DerG66G"  # #242, whose body's profile is the polyline #202
PROJECT = "1CGyzxdzHaJybf9L4wHy3R"  # #91
GOOD_POLYLINE = b"#202= IFCPOLYLINE((#194,#196,#198,#200,#194));"
BAD_POLYLINE = b"#202= IFCPOLYLINE((#194,#196,#196,#198,#200,#194));"  # #196 twice: GEM111
ORPHAN = b"#99999=IFCCARTESIANPOINT((1.,2.,3.));\n"  # a point nothing refers to


def broken(folder: Path, *, orphan: bool = False) -> Path:
    """The three walls with the outline of #242's body breaking GEM111, and with ``orphan`` a point that nothing
    reaches, which breaks IFC106 too."""
    data = (FIXTURES_DIR / "three_walls_gtin.ifc").read_bytes()
    assert data.count(GOOD_POLYLINE) == 1
    head, tail = data.replace(GOOD_POLYLINE, BAD_POLYLINE).rsplit(b"ENDSEC;", 1)
    path = folder / "gem111.ifc"
    path.write_bytes(head + (ORPHAN if orphan else b"") + b"ENDSEC;" + tail)
    return path


def test_an_instance_gets_its_class_and_the_nearest_rooted_entity(tmp_path: Path) -> None:
    found = answer(broken(tmp_path, orphan=True), [202, 242, 99999, 123456])["elements"]
    assert found["202"] == {"ifc_class": "IfcPolyline", "root_global_id": WALL}, (
        "Representation.Representations[0].Items[0].SweptArea.OuterCurve of the wall"
    )
    assert found["242"] == {"ifc_class": "IfcWallStandardCase", "root_global_id": WALL}, "a rooted entity is its own"
    assert found["99999"] == {"ifc_class": "IfcCartesianPoint", "root_global_id": None}, "nothing reaches it"
    assert "123456" not in found, "no such instance"


def test_a_path_may_go_backward_through_an_inverse_attribute(tmp_path: Path) -> None:
    found = answer(broken(tmp_path), [270, 32])["elements"]
    # A styled item is referred to only by a styled representation, which refers to its context, which the project's
    # contexts reach as RepresentationsInContext: an inverse step, as IFC-DB's paths take one.
    assert found["270"] == {"ifc_class": "IfcStyledItem", "root_global_id": PROJECT}
    # Every rooted entity refers to the owner history; the lowest GlobalId of them is taken, the site's.
    assert found["32"] == {"ifc_class": "IfcOwnerHistory", "root_global_id": "01uPthe3Uixx0TRWar3Vt8"}


def test_the_searches_share_a_limit_so_that_the_answer_comes_in_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(elements, "MAX_SEARCHED", 4)  # the polyline's wall is 7 steps back
    found = answer(broken(tmp_path), [202, 270, 242])["elements"]
    assert found["202"]["root_global_id"] is None and found["270"]["root_global_id"] is None
    assert found["202"]["ifc_class"] == "IfcPolyline", "the class is read all the same"
    assert found["242"]["root_global_id"] == WALL, "a rooted entity needs no search"


def test_the_worker_reads_the_ids_the_server_wrote_and_answers_on_stdout(tmp_path: Path) -> None:
    steps = tmp_path / "steps.json"
    steps.write_text(json.dumps([202, 202, True, -1, "7"]), encoding="utf-8")
    assert steps_of(steps) == [202], "each id once, and only ids"
    done = subprocess.run(  # noqa: S603 - this interpreter and the worker, with fixed arguments
        [sys.executable, "-m", "opencde.ifcgraph.elements", str(broken(tmp_path)), str(steps)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout.strip().splitlines()[-1]) == {
        "elements": {"202": {"ifc_class": "IfcPolyline", "root_global_id": WALL}}
    }


def test_a_file_that_cannot_be_read_is_an_error_on_stderr(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "steps.json").write_text("[1]", encoding="utf-8")
    (tmp_path / "bad.ifc").write_bytes(b"not a model")
    assert main([str(tmp_path / "bad.ifc"), str(tmp_path / "steps.json")]) == 2
    assert "error" in json.loads(capsys.readouterr().err)
