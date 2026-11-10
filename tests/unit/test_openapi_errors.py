# This file was generated with the assistance of an AI coding tool.
"""The API document names the answer the server gives to a request it cannot read: 400 with the error body, not
FastAPI's 422 (F13 b, S-2), so that a client generated from the document handles what really comes."""

from __future__ import annotations

import jsonschema
from fastapi.testclient import TestClient

from opencde.errors import ERROR_SCHEMA


def test_the_document_says_400_with_the_error_body_where_fastapi_says_422(client: TestClient) -> None:
    document = client.get("/openapi.json").json()
    responses = [
        operation["responses"]
        for item in document["paths"].values()
        for operation in item.values()
        if isinstance(operation, dict) and "responses" in operation
    ]
    assert not [codes for codes in responses if "422" in codes], "no operation promises 422 for a malformed request"
    with_400 = [codes["400"] for codes in responses if "400" in codes]
    assert len(with_400) > 100, "every operation with parameters or a body"
    assert all(
        answer["content"]["application/json"]["schema"] == {"$ref": "#/components/schemas/Error"} for answer in with_400
    )
    schemas = document["components"]["schemas"]
    assert schemas["Error"] == ERROR_SCHEMA and "HTTPValidationError" not in schemas


def test_what_the_server_answers_is_what_the_document_says(client: TestClient) -> None:
    malformed = client.post("/foundation/oauth2/reg", json={"redirect_uris": "not a list"})
    assert malformed.status_code == 400
    jsonschema.validate(malformed.json(), ERROR_SCHEMA)
