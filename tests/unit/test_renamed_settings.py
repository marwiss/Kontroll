# This file was generated with the assistance of an AI coding tool.
"""The IFC-graph module became IFC-LPG and then IFC-DB in November 2026: its settings and command take the newest names,
and the old ones still work."""

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

    prefixes = ("OPENCDE_IFCGRAPH_", "OPENCDE_IFC_LPG_", "OPENCDE_IFC_DB_")
    for name in [name for name in os.environ if name.upper().startswith(prefixes)]:
        monkeypatch.delenv(name)


def test_the_new_names_are_read_and_the_old_ones_still(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENCDE_IFCGRAPH_ENABLED", "true")
    monkeypatch.setenv("OPENCDE_IFCGRAPH_MEMORY_MB", "512")
    monkeypatch.setenv("OPENCDE_IFC_LPG_TIMEOUT_SECONDS", "60")
    old = settings(tmp_path)
    assert old.ifcgraph_enabled is True and old.ifcgraph_memory_mb == 512, "a server keeps its configuration"
    assert old.ifcgraph_timeout_seconds == 60, "and the names of the IFC-LPG module are read too"
    assert old.renamed_settings == [
        ("OPENCDE_IFCGRAPH_ENABLED", "OPENCDE_IFC_DB_ENABLED"),
        ("OPENCDE_IFCGRAPH_MEMORY_MB", "OPENCDE_IFC_DB_MEMORY_MB"),
        ("OPENCDE_IFC_LPG_TIMEOUT_SECONDS", "OPENCDE_IFC_DB_TIMEOUT_SECONDS"),
    ]
    monkeypatch.setenv("OPENCDE_IFC_LPG_MEMORY_MB", "1024")
    assert settings(tmp_path).ifcgraph_memory_mb == 1024, "IFC-LPG's name wins over IFC-graph's"
    monkeypatch.setenv("OPENCDE_IFC_DB_MEMORY_MB", "2048")
    assert settings(tmp_path).ifcgraph_memory_mb == 2048, "the new name wins over both old ones"
    for name in ("OPENCDE_IFCGRAPH_ENABLED", "OPENCDE_IFCGRAPH_MEMORY_MB", "OPENCDE_IFC_LPG_MEMORY_MB"):
        monkeypatch.delenv(name)
    monkeypatch.delenv("OPENCDE_IFC_LPG_TIMEOUT_SECONDS")
    new = settings(tmp_path)
    assert new.ifcgraph_memory_mb == 2048 and new.renamed_settings == []
    assert settings(tmp_path, ifcgraph_enabled=True).ifcgraph_enabled, "the field's own name still sets it in code"


def test_an_old_name_in_the_env_file_is_noticed(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "# OPENCDE_IFCGRAPH_INCLUDE_GEOMETRY=true\nexport OPENCDE_IFCGRAPH_GTIN_PROPERTY=Code\nOPENCDE_LOG_LEVEL=DEBUG\n",
        encoding="utf-8",
    )
    read = settings(tmp_path, env_file=env)
    assert read.ifcgraph_gtin_property == "Code" and read.ifcgraph_include_geometry is False, "a comment sets nothing"
    assert read.renamed_settings == [("OPENCDE_IFCGRAPH_GTIN_PROPERTY", "OPENCDE_IFC_DB_GTIN_PROPERTY")]


def test_the_name_a_setting_is_read_from() -> None:
    assert env_name("ifcgraph_enabled") == "OPENCDE_IFC_DB_ENABLED"
    assert env_name("ifcgraph_gtin_property_set") == "OPENCDE_IFC_DB_GTIN_PROPERTY_SET"
    assert env_name("graph_uri") == "OPENCDE_GRAPH_URI"


def test_the_administration_shows_the_new_names(tmp_path: Path) -> None:
    raw = _settings_payload(settings(tmp_path, ifcgraph_enabled=True))["raw"]
    assert raw["OPENCDE_IFC_DB_ENABLED"] is True
    assert "OPENCDE_IFC_LPG_ENABLED" not in raw and "OPENCDE_IFCGRAPH_ENABLED" not in raw


def test_the_command_has_its_new_name_and_answers_to_the_old() -> None:
    runner = CliRunner()
    shown = runner.invoke(app, ["--help"]).output
    assert "ifc-db" in shown and "ifc-lpg" not in shown and "ifcgraph" not in shown, "the old names are hidden"
    for name in ("ifc-db", "ifc-lpg", "ifcgraph"):
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
        "IFC_LPG_LOSSLESS": "true",
    }.items():
        monkeypatch.setenv(f"OPENCDE_{name}", value)
    monkeypatch.setenv("OPENCDE_ENV_FILE", str(tmp_path / "none.env"))
    output = CliRunner().invoke(app, ["doctor"]).output
    assert "OK      Renamed settings" in output, output
    assert "OPENCDE_IFCGRAPH_INCLUDE_GEOMETRY → OPENCDE_IFC_DB_INCLUDE_GEOMETRY" in output
    assert "OPENCDE_IFC_LPG_LOSSLESS → OPENCDE_IFC_DB_LOSSLESS" in output
