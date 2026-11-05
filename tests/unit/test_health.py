# This file was generated with the assistance of an AI coding tool.
from fastapi.testclient import TestClient

from opencde import __version__


def test_healthz_reports_version(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}


def test_readyz_is_503_without_database(client: TestClient) -> None:
    response = client.get("/readyz")
    assert response.status_code == 503
    assert response.json() == {"status": "not_ready", "graph": "unavailable"}


def test_index_points_to_docs_and_versions(client: TestClient) -> None:
    response = client.get("/")
    assert response.headers["content-type"].startswith("text/html")
    assert "/docs" in response.text and "/foundation/versions" in response.text


def test_openapi_document_is_served(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    assert schema["info"]["title"] == "Kontroll OpenCDE server"
    assert schema["info"]["license"]["name"] == "AGPL-3.0-or-later"
