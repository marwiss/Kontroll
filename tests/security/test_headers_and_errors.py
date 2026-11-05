# This file was generated with the assistance of an AI coding tool.
"""Every response, including errors, carries the security headers and the spec error body."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from opencde.main import create_app
from tests.conftest import test_settings as make_settings  # aliased so pytest does not collect it as a test

pytestmark = pytest.mark.security

EXPECTED_HEADERS = {
    "content-security-policy": "default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "no-referrer",
    "cross-origin-opener-policy": "same-origin",
    "cache-control": "no-store",
}


@pytest.mark.parametrize("path", ["/healthz", "/does-not-exist", "/readyz"])
def test_security_headers_on_every_response(client: TestClient, path: str) -> None:
    response = client.get(path)
    for name, value in EXPECTED_HEADERS.items():
        assert response.headers.get(name) == value, name
    assert "permissions-policy" in response.headers


def test_not_found_uses_spec_error_body(client: TestClient) -> None:
    response = client.get("/nope")
    assert response.status_code == 404
    assert set(response.json()) == {"message"}


def test_method_not_allowed_uses_spec_error_body(client: TestClient) -> None:
    response = client.delete("/healthz")
    assert response.status_code == 405
    assert set(response.json()) == {"message"}


def test_oversized_body_is_rejected_before_parsing(client: TestClient) -> None:
    limit = client.app.state.settings.max_json_body_bytes  # type: ignore[attr-defined]
    response = client.post("/healthz", content=b"x", headers={"Content-Length": str(limit + 1)})
    assert response.status_code == 413
    assert response.json() == {"message": f"Request body exceeds {limit} bytes"}


def test_chunked_body_over_the_limit_is_cut_off(client: TestClient) -> None:
    """Omitting Content-Length does not bypass the limit: bytes are counted as they arrive."""
    limit = client.app.state.settings.max_json_body_bytes  # type: ignore[attr-defined]
    chunk = b"a=" + b"x" * 65534

    def body():  # a plain generator keeps the transfer chunked
        sent = 0
        while sent <= limit:
            yield chunk
            sent += len(chunk)

    response = client.post(
        "/foundation/oauth2/token", content=body(), headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    assert response.status_code == 413
    assert response.json() == {"message": f"Request body exceeds {limit} bytes"}


def test_request_id_is_echoed_or_minted(client: TestClient) -> None:
    echoed = client.get("/healthz", headers={"X-Request-ID": "trace-123"})
    assert echoed.headers["x-request-id"] == "trace-123"
    minted = client.get("/healthz")
    assert len(minted.headers["x-request-id"]) == 32
    hostile = client.get("/healthz", headers={"X-Request-ID": "<script>alert(1)</script>"})
    assert hostile.headers["x-request-id"] != "<script>alert(1)</script>"


def test_cors_is_bearer_only_never_credentials(client: TestClient) -> None:
    response = client.options(
        "/foundation/versions",
        headers={"Origin": "https://viewer.example", "Access-Control-Request-Method": "GET"},
    )
    assert response.headers.get("access-control-allow-origin") == "*"
    assert "access-control-allow-credentials" not in response.headers


@pytest.mark.parametrize("path", ["/signin", "/", "/documents/1.0/select-ui/some-token", "/healthz"])
def test_pages_are_never_shared_cross_origin(client: TestClient, path: str) -> None:
    """CORS belongs to the API (Foundation API 1.4); HTML pages and health checks stay same-origin."""
    response = client.get(path, headers={"Origin": "https://viewer.example"})
    assert "access-control-allow-origin" not in response.headers, path


def test_api_docs_have_their_own_policy_and_are_off_in_production(client: TestClient, tmp_path: Path) -> None:
    """Swagger UI loads from a CDN with an inline script, so it gets a policy of its own and is off in production."""
    docs = client.get("/docs")
    assert docs.status_code == 200
    assert "https://cdn.jsdelivr.net" in docs.headers["content-security-policy"]
    assert "frame-ancestors 'none'" in docs.headers["content-security-policy"]
    assert "/docs" in client.get("/").text
    assert "https://cdn.jsdelivr.net" not in client.get("/openapi.json").headers["content-security-policy"]

    production_like = make_settings(tmp_path / "prod", api_docs_enabled=False)
    with TestClient(create_app(production_like, startup_wait_seconds=0)) as hardened:
        assert hardened.get("/docs").status_code == 404
        assert hardened.get("/openapi.json").status_code == 200
        assert "/docs" not in hardened.get("/").text
