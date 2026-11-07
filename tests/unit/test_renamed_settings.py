# This file was generated with the assistance of an AI coding tool.
"""The IFC-graph module became IFC-LPG in November 2026: its settings and command take the new names, and the old ones still work."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from opencde.admin.api import _settings_payload
from opencde.cli import app
from opencde.settings import Settings, env_name

BASE = {"environment": "test", "public_url": "http://testserver", "secret_key": "k" * 40}


def settings(tmp_path: Path, env_file: Path | None = None, **values: object) -> Settings:
    return Settings(_env_file=env_file, data_dir=tmp_path / "data", **{**BASE, **values})  # type: ignore[call-arg]


@pytest.fixture(autouse=True)
def no_ifc_settings_in_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    import os

    for name in [name for name in os.environ if name.upper().startswith(("OPENCDE_IFCGRAPH_", "OPENCDE_IFC_LPG_"))]:
        monkeypatch.delenv(name)


def test_the_new_names_are_read_and_the_old_ones_still(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENCDE_IFCGRAPH_ENABLED", "true")
    monkeypatch.setenv("OPENCDE_IFCGRAPH_MEMORY_MB", "512")
    old = settings(tmp_path)
    assert old.ifcgraph_enabled is True and old.ifcgraph_memory_mb == 512, "a server keeps its configuration"
    assert old.renamed_settings == [
        ("OPENCDE_IFCGRAPH_ENABLED", "OPENCDE_IFC_LPG_ENABLED"),
        ("OPENCDE_IFCGRAPH_MEMORY_MB", "OPENCDE_IFC_LPG_MEMORY_MB"),
    ]
    monkeypatch.setenv("OPENCDE_IFC_LPG_MEMORY_MB", "1024")
    assert settings(tmp_path).ifcgraph_memory_mb == 1024, "the new name wins over the old"
    monkeypatch.delenv("OPENCDE_IFCGRAPH_ENABLED")
    monkeypatch.delenv("OPENCDE_IFCGRAPH_MEMORY_MB")
    new = settings(tmp_path)
    assert new.ifcgraph_memory_mb == 1024 and new.renamed_settings == []
    assert settings(tmp_path, ifcgraph_enabled=True).ifcgraph_enabled, "the field's own name still sets it in code"


def test_an_old_name_in_the_env_file_is_noticed(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "# OPENCDE_IFCGRAPH_INCLUDE_GEOMETRY=true\nexport OPENCDE_IFCGRAPH_GTIN_PROPERTY=Code\nOPENCDE_LOG_LEVEL=DEBUG\n",
        encoding="utf-8",
    )
    read = settings(tmp_path, env_file=env)
    assert read.ifcgraph_gtin_property == "Code" and read.ifcgraph_include_geometry is False, "a comment sets nothing"
    assert read.renamed_settings == [("OPENCDE_IFCGRAPH_GTIN_PROPERTY", "OPENCDE_IFC_LPG_GTIN_PROPERTY")]


def test_the_name_a_setting_is_read_from() -> None:
    assert env_name("ifcgraph_enabled") == "OPENCDE_IFC_LPG_ENABLED"
    assert env_name("ifcgraph_gtin_property_set") == "OPENCDE_IFC_LPG_GTIN_PROPERTY_SET"
    assert env_name("graph_uri") == "OPENCDE_GRAPH_URI"


def test_the_administration_shows_the_new_names(tmp_path: Path) -> None:
    raw = _settings_payload(settings(tmp_path, ifcgraph_enabled=True))["raw"]
    assert raw["OPENCDE_IFC_LPG_ENABLED"] is True and "OPENCDE_IFCGRAPH_ENABLED" not in raw


def test_the_command_has_its_new_name_and_answers_to_the_old() -> None:
    runner = CliRunner()
    assert "ifc-lpg" in runner.invoke(app, ["--help"]).output
    for name in ("ifc-lpg", "ifcgraph"):
        done = runner.invoke(app, [name, "--help"])
        assert done.exit_code == 0 and "prune" in done.output, (name, done.output)


def test_doctor_names_the_settings_that_still_have_their_old_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name, value in {
        "ENVIRONMENT": "development",
        "PUBLIC_URL": "http://127.0.0.1:9",
        "GRAPH_URI": "bolt://127.0.0.1:9",
        "GRAPH_PASSWORD": "not-the-password-of-anything",
        "GRAPH_CONNECT_TIMEOUT_SECONDS": "1",
        "NTP_SERVER": "",
        "DATA_DIR": str(tmp_path),
        "IFCGRAPH_INCLUDE_GEOMETRY": "false",
    }.items():
        monkeypatch.setenv(f"OPENCDE_{name}", value)
    monkeypatch.setenv("OPENCDE_ENV_FILE", str(tmp_path / "none.env"))
    output = CliRunner().invoke(app, ["doctor"]).output
    assert "OK      Renamed settings" in output, output
    assert "OPENCDE_IFCGRAPH_INCLUDE_GEOMETRY → OPENCDE_IFC_LPG_INCLUDE_GEOMETRY" in output
