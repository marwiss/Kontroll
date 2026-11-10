# This file was generated with the assistance of an AI coding tool.
"""What Dataregium relies on from IFC-LPG, the library its IFC graph comes from (ADR 0014).

IFC-LPG's own tests cover the round trip. These cover how Dataregium uses it: the graph side in the server's process
without IfcOpenShell, the workers with the extra, and buildingSMART's rules without the server's settings.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _project() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]


def test_the_graph_side_is_always_installed_and_the_workers_come_with_the_extra() -> None:
    project = _project()
    assert any(requirement.startswith("ifc-lpg>=") for requirement in project["dependencies"])
    assert project["optional-dependencies"]["ifc-lpg"] == ["ifc-lpg[ifcopenshell]>=1.0.0", "ifcclash>=0.9.0"]
    assert '"--extra ifc-lpg"' in (ROOT / "docker" / "Dockerfile").read_text(encoding="utf-8"), (
        "the image has the workers"
    )


def test_the_server_process_needs_no_ifcopenshell() -> None:
    """The modules Dataregium imports in its own process; the slim image has no IfcOpenShell."""
    import ifc_lpg.exporter
    import ifc_lpg.importer
    import ifc_lpg.validation

    assert callable(ifc_lpg.importer.delete_model) and callable(ifc_lpg.exporter.export_records)
    assert ifc_lpg.validation.unpack_report(ifc_lpg.validation.pack_report([{"kind": "x"}])) == [{"kind": "x"}]


def test_the_rules_see_none_of_the_servers_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    from ifc_lpg import gherkin

    monkeypatch.setenv("OPENCDE_SECRET_KEY", "not for the rules")
    monkeypatch.setenv("OPENCDE_GRAPH_PASSWORD", "nor this")
    assert not [key for key in gherkin._clean_environment() if key.startswith("OPENCDE_")]
