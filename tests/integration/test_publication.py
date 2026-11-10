# This file was generated with the assistance of an AI coding tool.
"""Publishing a version (F9 a, OB-23.3): a manager publishes, the server keeps an .ifczip of an IFC file and a .zip
of another, the metadata names the publication, and a version is published once."""

from __future__ import annotations

import io
import zipfile
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from opencde.main import create_app
from tests.integration.conftest import GraphTarget
from tests.integration.conftest_accounts import World, build_world, login_as
from tests.integration.test_ifc_validation import MODEL, WALLS, checked, settings_for, upload
from tests.integration.test_web_signin import web_sign_in

pytestmark = pytest.mark.integration


@pytest.fixture
def ifc_client(graph_target: GraphTarget, clean_database: None, tmp_path: Any) -> Iterator[tuple[TestClient, World]]:
    settings = settings_for(graph_target, tmp_path)
    world = build_world(settings)
    with TestClient(create_app(settings, startup_wait_seconds=30)) as client:
        yield client, world


def entries(client: TestClient, headers: dict[str, str], version: dict[str, Any]) -> dict[str, list[str]]:
    response = client.get(version["links"]["document_version_metadata"]["url"], headers=headers)
    assert response.status_code == 200, response.text
    return {entry["name"]: entry["value"] for entry in response.json()["metadata"]}


def test_a_manager_publishes_a_checked_version_once(ifc_client: tuple[TestClient, World]) -> None:
    client, world = ifc_client
    editor = login_as(client, world, "editor")
    web_sign_in(client, world, "editor")
    manager = login_as(client, world, "manager")
    version = upload(client, world, editor, "three_walls.ifc", MODEL.read_bytes())
    checked(client, editor, version)
    url = version["links"]["document_version"]["url"] + "/publication"
    assert client.get(url, headers=editor.headers).status_code == 404, "not published yet"
    assert "publication" not in entries(client, editor.headers, version)

    assert client.post(url, headers=editor.headers).status_code == 403, "an editor does not publish"
    viewer = login_as(client, world, "viewer")
    assert client.post(url, headers=viewer.headers).status_code == 403
    outsider = login_as(client, world, "outsider")
    assert client.post(url, headers=outsider.headers).status_code == 404, "outside the project it does not exist"
    assert client.post(url).status_code == 401

    made = client.post(url, headers=manager.headers)
    assert made.status_code == 201, made.text
    published = made.json()
    assert published["published_by"] == "manager" and published["file_name"] == "three_walls.ifczip"
    assert published["download_url"] == url + "/download"
    assert client.get(url, headers=viewer.headers).json() == published, "every member sees it"
    download = client.get(published["download_url"], headers=viewer.headers)
    assert download.status_code == 200 and download.headers["content-type"] == "application/zip"
    assert len(download.content) == published["size_in_bytes"]
    with zipfile.ZipFile(io.BytesIO(download.content)) as archive:
        assert archive.namelist() == ["three_walls.ifc"]
        assert archive.read("three_walls.ifc") == MODEL.read_bytes(), "the archive holds the version as it is"
    metadata = entries(client, viewer.headers, version)
    assert metadata["published_by"] == ["manager"] and metadata["publication"] == [url]
    assert metadata["published_at"] == [published["published_at"]]

    again = client.post(url, headers=manager.headers)
    assert again.status_code == 409, "a version is published once"
    assert client.get(url, headers=outsider.headers).status_code == 404
    assert client.get(published["download_url"], headers=outsider.headers).status_code == 404
    missing = version["links"]["document_versions"]["url"] + "/9/publication"
    assert client.post(missing, headers=manager.headers).status_code == 404


def test_a_version_with_errors_is_not_published_and_another_file_becomes_a_zip(
    ifc_client: tuple[TestClient, World],
) -> None:
    client, world = ifc_client
    editor = login_as(client, world, "editor")
    web_sign_in(client, world, "editor")
    manager = login_as(client, world, "manager")
    twice = MODEL.read_bytes().replace(WALLS[1].encode(), WALLS[0].encode())  # one GlobalId on two walls
    flawed = upload(client, world, editor, "twice.ifc", twice)
    assert checked(client, editor, flawed)["ifc_validation_status"] == ["issues"]
    refused = client.post(flawed["links"]["document_version"]["url"] + "/publication", headers=manager.headers)
    assert refused.status_code == 409 and "mend it in a new version" in refused.text

    notes = upload(client, world, editor, "notes.txt", b"minutes of the meeting")
    published = client.post(notes["links"]["document_version"]["url"] + "/publication", headers=manager.headers)
    assert published.status_code == 201, published.text
    assert published.json()["file_name"] == "notes.txt.zip"
    download = client.get(published.json()["download_url"], headers=editor.headers)
    with zipfile.ZipFile(io.BytesIO(download.content)) as archive:
        assert archive.read("notes.txt") == b"minutes of the meeting"
