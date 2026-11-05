# This file was generated with the assistance of an AI coding tool.
"""The sample model ships with the package for the seed and stays identical to the test fixture."""

from pathlib import Path

from opencde.seed import SAMPLE_MODEL, SAMPLE_MODEL_WALLS

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "three_walls_gtin.ifc"


def test_packaged_sample_model_matches_the_fixture() -> None:
    assert SAMPLE_MODEL.is_file()
    assert SAMPLE_MODEL.read_bytes() == FIXTURE.read_bytes(), "keep opencde/seed_data and tests/fixtures identical"


def test_sample_model_contains_the_documented_walls() -> None:
    text = FIXTURE.read_text(encoding="utf-8", errors="replace")
    for global_id in SAMPLE_MODEL_WALLS:
        assert f"IFCWALLSTANDARDCASE('{global_id}'" in text
