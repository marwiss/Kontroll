# This file was generated with the assistance of an AI coding tool.
"""The examples in the API document are real: each one is a body the server accepts."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from opencde.auth.routes import RegistrationRequest
from opencde.bcf.schemas import CommentPOST, TopicPOST, ViewpointPOST
from opencde.documents.schemas import SelectDocuments

MODELS: tuple[type[BaseModel], ...] = (TopicPOST, CommentPOST, ViewpointPOST, SelectDocuments, RegistrationRequest)


@pytest.mark.parametrize("model", MODELS, ids=lambda model: model.__name__)
def test_the_example_is_a_body_the_server_accepts(client: TestClient, model: type[BaseModel]) -> None:
    schemas = client.get("/openapi.json").json()["components"]["schemas"]
    examples = schemas[model.__name__].get("examples")
    assert examples, "the document shows it"
    for example in examples:
        model.model_validate(example)
