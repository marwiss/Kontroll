# This file was generated with the assistance of an AI coding tool.
"""Foundation API responses that need no database, validated against the pinned schemas."""

import pytest
from fastapi.testclient import TestClient

from tests.conformance.schemas import validate

pytestmark = pytest.mark.conformance


def test_versions_service_matches_schema_and_lists_all_apis(client: TestClient) -> None:
    response = client.get("/foundation/versions")
    assert response.status_code == 200
    body = response.json()
    validate(body, "foundation-api/schemas/versions_GET.json", allow_documents_api_id=True)
    by_id = {v["api_id"]: v for v in body["versions"]}
    assert set(by_id) == {"foundation", "bcf", "documents"}
    assert by_id["bcf"]["version_id"] == "3.0"
    assert by_id["bcf"]["api_base_url"] == "http://testserver/bcf/3.0"
    assert by_id["documents"]["api_base_url"] == "http://testserver/documents/1.0"
    assert response.headers["etag"].startswith('"')
    cached = client.get("/foundation/versions", headers={"If-None-Match": response.headers["etag"]})
    assert cached.status_code == 304 and cached.content == b""


def test_auth_information_matches_schema(client: TestClient) -> None:
    body = client.get("/foundation/1.0/auth").json()
    validate(body, "foundation-api/schemas/auth_GET.json")
    assert body["oauth2_auth_url"] == "http://testserver/foundation/oauth2/auth"
    assert body["oauth2_token_url"] == "http://testserver/foundation/oauth2/token"
    assert body["http_basic_supported"] is False
    assert body["supported_oauth2_flows"] == ["authorization_code_grant"]
    assert "oauth2_dynamic_client_reg_url" not in body, "registration is off by default"
    assert body["oauth2_pkce_required"] is True


def test_bcf_2_1_style_aliases(client: TestClient) -> None:
    versions = client.get("/bcf/versions").json()["versions"]
    assert [v["version_id"] for v in versions] == ["3.0"] and versions[0]["api_id"] == "bcf"
    assert client.get("/bcf/3.0/auth").json()["oauth2_token_url"].endswith("/foundation/oauth2/token")


def test_current_user_requires_a_bearer_token(client: TestClient) -> None:
    response = client.get("/foundation/1.0/current-user")
    assert response.status_code == 401
    assert response.headers["www-authenticate"].startswith("Bearer")
    validate(response.json(), "foundation-api/schemas/error.json")
    basic = client.get("/foundation/1.0/current-user", headers={"Authorization": "Basic dXNlcjpwYXNz"})
    assert basic.status_code == 401, "HTTP Basic is not supported (http_basic_supported: false)"


def test_authorize_without_client_shows_an_error_page_and_never_redirects(client: TestClient) -> None:
    response = client.get(
        "/foundation/oauth2/auth", params={"response_type": "code", "redirect_uri": "https://evil.test/"}
    )
    assert response.status_code == 400
    assert response.headers["content-type"].startswith("text/html")
    assert "client_id" in response.text
    assert "location" not in response.headers
    csp = response.headers["content-security-policy"]
    assert "script-src 'self'" in csp and "frame-ancestors 'none'" in csp and "form-action 'self'" in csp


def test_index_page_and_static_assets(client: TestClient) -> None:
    index = client.get("/")
    assert index.status_code == 200 and index.headers["content-type"].startswith("text/html")
    assert "/foundation/versions" in index.text and "/docs" in index.text
    css = client.get("/static/css/tokens.css")
    assert css.status_code == 200 and "--dm-accent" in css.text
    assert css.headers["cache-control"] == "public, max-age=86400"
    assert client.get("/static/../pyproject.toml").status_code in (404, 400)
