# This file was generated with the assistance of an AI coding tool.
"""The OAuth2 metadata documents against their RFCs: the authorization server's (RFC 8414) and the MCP endpoint's as
a protected resource (RFC 9728), with what the MCP specification adds to each (ADR 0028)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from opencde.main import create_app
from tests.conftest import test_settings as make_settings

pytestmark = pytest.mark.conformance

URI = {"type": "string", "pattern": "^https?://[^#]+$"}
LIST = {"type": "array", "items": {"type": "string"}, "minItems": 1, "uniqueItems": True}

# RFC 8414 §2. The MCP specification adds code_challenge_methods_supported: without it a client must not go on.
AUTHORIZATION_SERVER = {
    "type": "object",
    "required": [
        "issuer",
        "authorization_endpoint",
        "token_endpoint",
        "response_types_supported",
        "code_challenge_methods_supported",
    ],
    "properties": {
        "issuer": {"type": "string", "pattern": "^https?://[^?#]+$"},  # §2: no query, no fragment
        "authorization_endpoint": URI,
        "token_endpoint": URI,
        "revocation_endpoint": URI,
        "registration_endpoint": URI,
        "scopes_supported": LIST,
        "response_types_supported": LIST,
        "response_modes_supported": LIST,
        "grant_types_supported": LIST,
        "token_endpoint_auth_methods_supported": LIST,
        "revocation_endpoint_auth_methods_supported": LIST,
        "code_challenge_methods_supported": {
            **LIST,
            "contains": {"const": "S256"},
            "not": {"contains": {"const": "plain"}},
        },
        "authorization_response_iss_parameter_supported": {"type": "boolean"},  # RFC 9207 §3
    },
}

# RFC 9728 §2. The MCP specification makes authorization_servers a must.
PROTECTED_RESOURCE = {
    "type": "object",
    "required": ["resource", "authorization_servers"],
    "properties": {
        "resource": {"type": "string", "pattern": "^https?://[^#]+$"},
        "authorization_servers": LIST,
        "scopes_supported": LIST,
        "bearer_methods_supported": {"type": "array", "items": {"enum": ["header", "body", "query"]}},
    },
}


@contextmanager
def _server(tmp_path: Path, **overrides: object) -> Iterator[TestClient]:
    with TestClient(create_app(make_settings(tmp_path, **overrides), startup_wait_seconds=0)) as client:
        yield client


@pytest.fixture
def mcp_on(tmp_path: Path) -> Iterator[TestClient]:
    with _server(tmp_path, mcp_enabled=True) as client:
        yield client


def _metadata_url(identifier: str, well_known: str) -> str:
    """RFC 8414 §3.1 and RFC 9728 §3.1: the well-known name goes between the host and the path."""
    parts = urlsplit(identifier)
    return f"{parts.scheme}://{parts.netloc}/.well-known/{well_known}{parts.path}"


def test_the_authorization_server_metadata_follows_rfc_8414(client: TestClient) -> None:
    response = client.get(_metadata_url("http://testserver", "oauth-authorization-server"))
    assert response.status_code == 200 and response.headers["content-type"] == "application/json"
    body = response.json()
    Draft202012Validator(AUTHORIZATION_SERVER).validate(body)
    assert body["issuer"] == "http://testserver", "§3.3: the issuer the address was made from"
    assert body["response_types_supported"] == ["code"] and body["response_modes_supported"] == ["query"]
    assert body["grant_types_supported"] == ["authorization_code", "refresh_token"], "never implicit or password"
    assert body["code_challenge_methods_supported"] == ["S256"]
    assert body["authorization_response_iss_parameter_supported"] is True
    assert body["token_endpoint_auth_methods_supported"] == ["client_secret_basic", "client_secret_post", "none"]
    assert body["scopes_supported"] == ["profile", "bcf", "documents", "project", "admin"]
    assert "registration_endpoint" not in body, "registration is off by default"


def test_it_says_what_the_foundation_api_says(client: TestClient, tmp_path: Path) -> None:
    """Two ways to discover one authorization server, which must agree."""

    def agree(server: TestClient) -> dict[str, object]:
        metadata = server.get("/.well-known/oauth-authorization-server").json()
        foundation = server.get("/foundation/1.0/auth").json()
        assert metadata["authorization_endpoint"] == foundation["oauth2_auth_url"]
        assert metadata["token_endpoint"] == foundation["oauth2_token_url"]
        assert metadata["revocation_endpoint"] == foundation["oauth2_revocation_url"]
        assert metadata["code_challenge_methods_supported"] == foundation["oauth2_pkce_methods"]
        assert metadata.get("registration_endpoint") == foundation.get("oauth2_dynamic_client_reg_url")
        return metadata

    agree(client)
    with _server(tmp_path, dynamic_client_registration=True) as registering:
        assert agree(registering)["registration_endpoint"] == "http://testserver/foundation/oauth2/reg"


def test_the_protected_resource_metadata_follows_rfc_9728(mcp_on: TestClient) -> None:
    resource = "http://testserver/mcp"
    response = mcp_on.get(_metadata_url(resource, "oauth-protected-resource"))
    assert response.status_code == 200 and response.headers["content-type"] == "application/json"
    body = response.json()
    Draft202012Validator(PROTECTED_RESOURCE).validate(body)
    assert body == {
        "resource": resource,  # §3.3: identical to the identifier the address was made from
        "authorization_servers": ["http://testserver"],
        "scopes_supported": ["mcp", "mcp:propose"],
        "bearer_methods_supported": ["header"],
    }
    # Its authorization server is found where RFC 8414 says, names itself the same, and offers the scopes.
    issuer = body["authorization_servers"][0]
    server = mcp_on.get(_metadata_url(issuer, "oauth-authorization-server")).json()
    assert server["issuer"] == issuer
    assert set(body["scopes_supported"]) <= set(server["scopes_supported"])


def test_the_protected_resource_metadata_exists_only_with_the_endpoint(client: TestClient) -> None:
    assert client.get("/.well-known/oauth-protected-resource/mcp").status_code == 404
    assert "/.well-known/oauth-protected-resource/mcp" not in client.get("/openapi.json").json()["paths"]


@pytest.mark.parametrize(
    "path", ["/.well-known/oauth-authorization-server", "/.well-known/oauth-protected-resource/mcp"]
)
def test_both_documents_are_public_cacheable_and_readable_across_origins(mcp_on: TestClient, path: str) -> None:
    response = mcp_on.get(path, headers={"Origin": "https://app.example"})
    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=300"
    assert response.headers["access-control-allow-origin"] == "*", "browser clients read them cross-origin"
    schema = mcp_on.get("/openapi.json").json()["paths"][path]["get"]
    assert "security" not in schema and "$ref" in str(schema["responses"]["200"]), "public, with its schema"
