# This file was generated with the assistance of an AI coding tool.
"""The pinned buildingSMART schemas load and are themselves valid, so later tests can trust them."""

import json
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft3Validator
from openapi_spec_validator import validate as validate_openapi

from tests.conftest import SPEC_DIR

pytestmark = pytest.mark.conformance

BCF_SCHEMAS = sorted((SPEC_DIR / "bcf-api" / "Schemas").rglob("*.json"))
FOUNDATION_SCHEMAS = sorted((SPEC_DIR / "foundation-api" / "schemas").glob("*.json"))


def test_expected_number_of_schemas_is_pinned() -> None:
    assert len(BCF_SCHEMAS) == 52, "BCF-API release_3_0 ships 52 schema files"
    assert len(FOUNDATION_SCHEMAS) == 6, "foundation-API v1.0 ships 6 schema files"


@pytest.mark.parametrize(
    "schema_path", BCF_SCHEMAS + FOUNDATION_SCHEMAS, ids=lambda p: p.relative_to(SPEC_DIR).as_posix()
)
def test_schema_is_valid_json_schema_draft3(schema_path: Path) -> None:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft3Validator.check_schema(schema)


def _string_keys(value: object) -> object:
    """YAML reads ``200:`` as an integer; OpenAPI response codes are strings."""
    if isinstance(value, dict):
        return {str(key): _string_keys(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_string_keys(item) for item in value]
    return value


def test_documents_swagger_is_valid_openapi_3() -> None:
    raw = yaml.safe_load((SPEC_DIR / "documents-api" / "swagger.yaml").read_text(encoding="utf-8"))
    document = _string_keys(raw)
    assert isinstance(document, dict)
    assert document["openapi"] == "3.0.0"
    assert document["info"]["version"] == "1.0"
    validate_openapi(document)
    assert len(document["paths"]) == 12


def test_sources_file_pins_commits() -> None:
    text = (SPEC_DIR / "SOURCES.md").read_text(encoding="utf-8")
    for sha in (
        "701e5ceb3548b2feec73f4ec56f5a1d6112bd16f",
        "d8577940560a4ee8428ca0b073cd0572fb2bc0e3",
        "938bd7636e094c2dc3c65ad6dae846ac3c7b6a9b",
    ):
        assert sha in text
