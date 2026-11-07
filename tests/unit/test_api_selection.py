# This file was generated with the assistance of an AI coding tool.
"""OPENCDE_APIS: a server can offer all its APIs, BCF API 2.1 alone, or the Documents API alone."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from opencde.main import create_app
from tests.conftest import test_settings as make_settings  # aliased so pytest does not collect it as a test


def serve(tmp_path: Path, apis: list[str]) -> Iterator[TestClient]:
    with TestClient(create_app(make_settings(tmp_path, apis=apis), startup_wait_seconds=0)) as client:
        yield client


def paths(client: TestClient) -> set[str]:
    return set(client.get("/openapi.json").json()["paths"])


# One address of each API that asks for a token: it answers 401 when the API is offered, 404 when it is not.
BCF30 = "/bcf/3.0/projects"
BCF21 = "/bcf/2.1/projects"
DOCUMENTS = "/documents/1.0/documents/d/versions"


def offered(client: TestClient, path: str) -> bool:
    status = client.get(path).status_code
    assert status in (401, 404), (path, status)
    return status == 401


def test_by_default_every_api_is_offered(client: TestClient) -> None:
    versions = client.get("/foundation/versions").json()["versions"]
    assert [(v["api_id"], v["version_id"]) for v in versions] == [
        ("foundation", "1.0"),
        ("bcf", "3.0"),
        ("bcf", "2.1"),
        ("documents", "1.0"),
    ]
    assert [v["version_id"] for v in client.get("/bcf/versions").json()["versions"]] == ["3.0", "2.1"]
    body = client.get("/.well-known/kontroll").json()
    assert body["apis"] == {"foundation": "1.0", "bcf": "3.0", "documents": "1.0"}
    assert body["bcf_versions"] == ["3.0", "2.1"]
    assert offered(client, BCF30) and offered(client, BCF21) and offered(client, DOCUMENTS)


@pytest.fixture
def bcf21(tmp_path: Path) -> Iterator[TestClient]:
    yield from serve(tmp_path, ["bcf-2.1"])


def test_a_server_for_bcf_21_alone_offers_that_and_sign_in(bcf21: TestClient) -> None:
    assert [v["version_id"] for v in bcf21.get("/bcf/versions").json()["versions"]] == ["2.1"]
    auth = bcf21.get("/bcf/2.1/auth").json()
    assert auth["oauth2_auth_url"] == "http://testserver/foundation/oauth2/auth", "sign-in stays where it is"
    assert bcf21.get("/foundation/oauth2/auth").status_code != 404, "the authorization endpoint serves 2.1 too"
    for gone in ("/foundation/versions", "/foundation/1.0/auth", "/bcf/3.0/auth"):
        assert bcf21.get(gone).status_code == 404, gone
    assert offered(bcf21, BCF21) and not offered(bcf21, BCF30) and not offered(bcf21, DOCUMENTS)
    body = bcf21.get("/.well-known/kontroll").json()
    assert body["apis"] == {"bcf": "2.1"} and body["bcf_versions"] == ["2.1"]
    assert not [path for path in paths(bcf21) if path.startswith(("/foundation/1.0", "/bcf/3.0", "/documents/"))]
    page = bcf21.get("/", headers={"Accept-Language": "en"}).text
    assert "GET /bcf/versions" in page and "GET /foundation/versions" not in page, "the start page tells where to look"


def test_a_document_server_offers_the_documents_api_with_the_foundation_api(tmp_path: Path) -> None:
    for client in serve(tmp_path, ["documents"]):
        versions = client.get("/foundation/versions").json()["versions"]
        assert [v["api_id"] for v in versions] == ["foundation", "documents"]
        assert client.get("/foundation/1.0/auth").status_code == 200, "the Documents API finds sign-in there"
        assert client.get("/bcf/versions").status_code == 404
        assert offered(client, DOCUMENTS) and not offered(client, BCF30) and not offered(client, BCF21)
        assert not [path for path in paths(client) if path.startswith("/bcf/")]
        body = client.get("/.well-known/kontroll").json()
        assert body["apis"] == {"foundation": "1.0", "documents": "1.0"} and body["bcf_versions"] == []


def test_the_setting_must_name_known_apis_and_at_least_one(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="at least one"):
        make_settings(tmp_path, apis=[])
    with pytest.raises(ValidationError):
        make_settings(tmp_path, apis=["bcf-4.0"])
    assert make_settings(tmp_path, apis=["bcf-2.1", "bcf-2.1"]).apis == ["bcf-2.1"]
    assert make_settings(tmp_path, apis=["documents"]).offers("foundation")
    assert not make_settings(tmp_path, apis=["bcf-2.1"]).offers("foundation")


def test_the_setting_is_read_from_the_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from opencde.settings import Settings

    monkeypatch.setenv("OPENCDE_APIS", '["bcf-2.1"]')
    settings = Settings(_env_file=None, environment="test", data_dir=tmp_path / "data")  # type: ignore[call-arg]
    assert settings.apis == ["bcf-2.1"]
