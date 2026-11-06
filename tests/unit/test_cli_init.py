# This file was generated with the assistance of an AI coding tool.
"""`opencde init`: the two direct ways, the guide that asks, and what it says comes next."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from opencde import cli
from opencde.cli import app


@pytest.fixture
def answers(monkeypatch: pytest.MonkeyPatch) -> None:
    """A terminal someone answers in, which the test runner's input is not."""
    monkeypatch.setattr(cli, "_interactive", lambda: True)


def _env(path: Path) -> dict[str, str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return dict(line.split("=", 1) for line in lines if "=" in line and not line.startswith("#"))


def test_the_direct_ways_ask_nothing(tmp_path: Path) -> None:
    development = tmp_path / "development.env"
    assert CliRunner().invoke(app, ["init", "--dev", "--path", str(development)]).exit_code == 0
    assert _env(development)["OPENCDE_ENVIRONMENT"] == "development"
    production = tmp_path / "production.env"
    done = CliRunner().invoke(app, ["init", "--public-url", "https://cde.example.org", "--path", str(production)])
    assert done.exit_code == 0
    assert _env(production)["OPENCDE_DOMAIN"] == "cde.example.org"


def test_without_a_terminal_it_says_what_to_give(tmp_path: Path) -> None:
    done = CliRunner().invoke(app, ["init", "--path", str(tmp_path / ".env")])
    assert done.exit_code != 0 and "--public-url" in done.output and not (tmp_path / ".env").exists()


def test_an_existing_file_stays(tmp_path: Path, answers: None) -> None:
    path = tmp_path / ".env"
    path.write_text("OPENCDE_SECRET_KEY=keep-this\n", encoding="utf-8")
    done = CliRunner().invoke(app, ["init", "--path", str(path)], input="n\ny\n")
    assert done.exit_code != 0 and "--force" in done.output
    assert path.read_text(encoding="utf-8") == "OPENCDE_SECRET_KEY=keep-this\n"


def test_the_guide_for_this_machine(tmp_path: Path, answers: None) -> None:
    path = tmp_path / ".env"
    done = CliRunner().invoke(app, ["init", "--path", str(path)], input="n\ny\n")
    assert done.exit_code == 0, done.output
    env = _env(path)
    assert env["OPENCDE_ENVIRONMENT"] == "development"
    assert env["OPENCDE_IFCGRAPH_ENABLED"] == "true" and env["OPENCDE_REQUEST_LOG_ENABLED"] == "true"
    assert env["OPENCDE_DYNAMIC_CLIENT_REGISTRATION"] == "true"
    assert len([line for line in path.read_text().splitlines() if "DYNAMIC_CLIENT_REGISTRATION" in line]) == 1
    assert "compose.dev.yaml up -d --build --wait" in done.output and "opencde seed" in done.output


def test_the_guide_for_a_server_others_use(tmp_path: Path, answers: None) -> None:
    path = tmp_path / ".env"
    typed = [
        "y",
        "http://cde.example.org",
        "https://cde.example.org/path",
        "https://cde.example.org/",
        "me@example.org",
        "n",
        "y",
    ]
    done = CliRunner().invoke(app, ["init", "--path", str(path)], input="\n".join(typed) + "\n")
    assert done.exit_code == 0, done.output
    assert done.output.count("It has to be https://") == 2
    env = _env(path)
    assert env["OPENCDE_ENVIRONMENT"] == "production"
    assert env["OPENCDE_PUBLIC_URL"] == "https://cde.example.org" and env["OPENCDE_DOMAIN"] == "cde.example.org"
    assert env["OPENCDE_ACME_EMAIL"] == "me@example.org"
    assert env["OPENCDE_DYNAMIC_CLIENT_REGISTRATION"] == "false" and env["OPENCDE_IFCGRAPH_ENABLED"] == "true"
    for step in (
        "cde.example.org points at this machine",
        "compose.prod.yaml up -d",
        "user create admin --admin",
        "client create",
    ):
        assert step in done.output
    assert env["OPENCDE_SECRET_KEY"] not in done.output and env["OPENCDE_GRAPH_PASSWORD"] not in done.output


def test_the_settings_accept_what_the_guide_wrote(
    tmp_path: Path, answers: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    from opencde.settings import Settings

    path = tmp_path / ".env"
    typed = ["y", "https://cde.example.org", "", "n", "n"]
    assert CliRunner().invoke(app, ["init", "--path", str(path)], input="\n".join(typed) + "\n").exit_code == 0
    settings = Settings(_env_file=path)  # type: ignore[call-arg]
    assert settings.is_production and settings.public_url == "https://cde.example.org"
