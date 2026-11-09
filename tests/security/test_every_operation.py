# This file was generated with the assistance of an AI coding tool.
"""Every operation of the API document: it needs a token or is on the list of public ones, and other methods get 405.

The list is written out so that a new public operation is a decision someone makes in a review, not a
missing dependency nobody notices (OWASP API2, API5).
"""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.security

METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE")
AN_ID = "00000000-0000-4000-8000-000000000000"

PUBLIC = {
    ("GET", "/foundation/versions"),
    ("GET", "/foundation/1.0/auth"),
    ("GET", "/foundation/oauth2/auth"),  # the sign-in page
    ("POST", "/foundation/oauth2/auth"),  # its form, protected by a signed form token
    ("POST", "/foundation/oauth2/token"),  # the client authenticates in the request
    ("POST", "/foundation/oauth2/revoke"),  # the same
    ("POST", "/foundation/oauth2/reg"),  # off unless the operator allows it
    ("GET", "/bcf/versions"),  # BCF API 2.1's versions service
    ("GET", "/bcf/2.1/auth"),  # and its authentication information
    ("POST", "/bcf/2.1/oauth2/reg"),  # off unless the operator allows it
    ("GET", "/.well-known/dataregium"),
    ("GET", "/.well-known/kontroll"),
}

# A method the document leaves out on an address where another route takes it.
OTHER_ROUTES = {
    ("PUT", "/bcf/3.0/projects/{project_id}/topics/events"),  # "events" is then a topic id
    ("DELETE", "/bcf/3.0/projects/{project_id}/topics/events"),
    ("PUT", "/bcf/2.1/projects/{project_id}/topics/events"),
    ("DELETE", "/bcf/2.1/projects/{project_id}/topics/events"),
}


def _filled(path: str) -> str:
    return re.sub(r"\{[^}]+\}", AN_ID, path)


def _operations(client: TestClient) -> list[tuple[str, str, dict]]:
    paths = client.get("/openapi.json").json()["paths"]
    return [
        (method.upper(), path, operation)
        for path, item in paths.items()
        for method, operation in item.items()
        if method.upper() in METHODS
    ]


def test_the_only_operations_without_a_token_are_the_listed_ones(client: TestClient) -> None:
    public = {(method, path) for method, path, operation in _operations(client) if not operation.get("security")}
    assert public == PUBLIC


def test_the_document_declares_the_bearer_scheme(client: TestClient) -> None:
    schemes = client.get("/openapi.json").json()["components"]["securitySchemes"]
    assert schemes["bearer"]["type"] == "http" and schemes["bearer"]["scheme"] == "bearer"


def test_every_other_operation_refuses_a_request_without_a_token(client: TestClient) -> None:
    protected = [(m, p) for m, p, operation in _operations(client) if operation.get("security")]
    assert len(protected) > 50, "the list is not empty by accident"
    for method, path in protected:
        response = client.request(method, _filled(path))
        assert response.status_code == 401, f"{method} {path}: {response.status_code}"
        assert response.headers["www-authenticate"].startswith("Bearer"), f"{method} {path}"
        assert response.json()["code"] == "unauthenticated", f"{method} {path}"


def test_a_method_the_api_does_not_have_answers_405(client: TestClient) -> None:
    documented: dict[str, set[str]] = {}
    for method, path, _operation in _operations(client):
        documented.setdefault(path, set()).add(method)
    others: list[str] = []
    checked = 0
    for path, methods in documented.items():
        for method in sorted(set(METHODS) - methods):
            if (method, path) in OTHER_ROUTES:
                continue
            response = client.request(method, _filled(path))
            checked += 1
            if response.status_code != 405 or "allow" not in response.headers or "message" not in response.json():
                others.append(f"{method} {path}: {response.status_code}")
    assert not others, others
    assert checked > 100, "the loop reached the API"
