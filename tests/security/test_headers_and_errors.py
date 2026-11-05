# This file was generated with the assistance of an AI coding tool.
"""Every response, including errors, carries the security headers and the spec error body."""

import pytest
from fastapi.testclient import TestClient

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


def test_request_id_is_echoed_or_minted(client: TestClient) -> None:
    echoed = client.get("/healthz", headers={"X-Request-ID": "trace-123"})
    assert echoed.headers["x-request-id"] == "trace-123"
    minted = client.get("/healthz")
    assert len(minted.headers["x-request-id"]) == 32
    hostile = client.get("/healthz", headers={"X-Request-ID": "<script>alert(1)</script>"})
    assert hostile.headers["x-request-id"] != "<script>alert(1)</script>"


def test_cors_is_bearer_only_never_credentials(client: TestClient) -> None:
    response = client.options(
        "/healthz",
        headers={"Origin": "https://viewer.example", "Access-Control-Request-Method": "GET"},
    )
    assert response.headers.get("access-control-allow-origin") == "*"
    assert "access-control-allow-credentials" not in response.headers
