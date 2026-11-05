# This file was generated with the assistance of an AI coding tool.
"""Deep links into Dataspatium: only when configured, always URL-encoded, with the agreed route."""

from pathlib import Path

from opencde.ui.links import dataspatium_link
from tests.conftest import test_settings as make_settings


def test_no_link_without_a_configured_installation(tmp_path: Path) -> None:
    assert dataspatium_link(make_settings(tmp_path), project_id="p1") is None


def test_links_carry_the_server_project_document_and_version(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, dataspatium_url="https://app.example/", public_url="https://cde.example.org")
    assert (
        dataspatium_link(settings, project_id="p 1")
        == "https://app.example/#/inhamta/opencde?server=https%3A%2F%2Fcde.example.org&project=p+1"
    )
    full = dataspatium_link(settings, project_id="p1", document_id="d1", version_index=2)
    assert full is not None and full.endswith("?server=https%3A%2F%2Fcde.example.org&project=p1&document=d1&version=2")
    assert dataspatium_link(settings) == "https://app.example/#/inhamta/opencde?server=https%3A%2F%2Fcde.example.org"
