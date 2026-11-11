# This file was generated with the assistance of an AI coding tool.
"""Which teams' parts a change set touches (F19 a): the objects the changes name, and what the teams' IDS select. The
approval that follows from it is proved against a database in ``tests/integration/test_teams.py``."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests.conftest import FIXTURES_DIR

pytest.importorskip("ifcopenshell", reason="the ifc-lpg extra is not installed")

from opencde.ifcgraph.parts import answer

MODEL = FIXTURES_DIR / "three_walls_gtin.ifc"
WALLS_IDS = FIXTURES_DIR / "walls.ids"
WALL = "1Xezbq735AdBO_4DerG66G"
BUILDING = "3AMeTOOFsdVLZuNV0$27s5"


def test_a_change_to_a_wall_touches_the_part_the_walls_ids_points_out(tmp_path: Path) -> None:
    broken = tmp_path / "broken.ids"
    broken.write_bytes(b"<ids/>")
    rename = {"guid": WALL, "attribute": "Name", "op": "set", "new": "x"}
    found = answer(MODEL, MODEL, [rename], [WALLS_IDS, broken])
    assert found["objects"] == 1 and found["teams"] == [0], "the walls are what walls.ids applies to"
    assert [error["ids"] for error in found["errors"]] == [1], "an IDS that cannot be read touches nothing"

    building = {"guid": BUILDING, "attribute": "Name", "op": "set", "new": "x"}
    assert answer(MODEL, MODEL, [building], [WALLS_IDS])["teams"] == [], "the building is in no wall's part"
    assert answer(MODEL, MODEL, [{"step_id": 999_999, "op": "delete"}], [WALLS_IDS])["objects"] == 0


def test_the_worker_answers_on_stdout(tmp_path: Path) -> None:
    changes = tmp_path / "changes.json"
    changes.write_text(json.dumps({"changes": [{"guid": WALL, "attribute": "Name", "op": "set"}]}), encoding="utf-8")
    command = [
        sys.executable,
        "-m",
        "opencde.ifcgraph.parts",
        "--",
        str(MODEL),
        str(MODEL),
        str(changes),
        str(WALLS_IDS),
    ]
    run = subprocess.run(command, capture_output=True, text=True, check=False)  # noqa: S603
    assert run.returncode == 0, run.stderr
    assert json.loads(run.stdout)["teams"] == [0]
