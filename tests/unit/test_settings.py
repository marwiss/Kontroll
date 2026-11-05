# This file was generated with the assistance of an AI coding tool.
import pytest
from pydantic import ValidationError

from opencde.settings import GraphDialect, Settings


def _settings(**values: object) -> Settings:
    return Settings(_env_file=None, **values)  # type: ignore[call-arg]


PROD = {"public_url": "https://cde.example.com", "graph_password": "secret-enough", "secret_key": "k" * 40}


def test_production_requires_https_public_url() -> None:
    with pytest.raises(ValidationError, match="https"):
        _settings(environment="production", **{**PROD, "public_url": "http://cde.example.com"})


def test_production_requires_graph_password_and_secret_key() -> None:
    with pytest.raises(ValidationError, match="OPENCDE_GRAPH_PASSWORD"):
        _settings(environment="production", **{**PROD, "graph_password": ""})
    with pytest.raises(ValidationError, match="OPENCDE_SECRET_KEY"):
        _settings(environment="production", **{**PROD, "secret_key": "short"})
    with pytest.raises(ValidationError, match="LOCALHOST"):
        _settings(environment="production", **PROD, allow_localhost_redirects=True)
    assert _settings(environment="production", **PROD).is_production


def test_development_allows_http_localhost_and_generates_a_key() -> None:
    settings = _settings(environment="development", public_url="http://localhost:8000/")
    assert settings.public_url == "http://localhost:8000"  # trailing slash removed for safe concatenation
    assert len(settings.secret_key.get_secret_value()) >= 32
    assert settings.url("/foundation/versions") == "http://localhost:8000/foundation/versions"


def test_graph_uri_scheme_is_checked() -> None:
    with pytest.raises(ValidationError, match="OPENCDE_GRAPH_URI"):
        _settings(environment="development", graph_uri="http://localhost:7687")


def test_database_name_follows_dialect() -> None:
    assert _settings(environment="development").database_name == "neo4j"
    assert _settings(environment="development", graph_dialect=GraphDialect.MEMGRAPH).database_name == "memgraph"
    assert _settings(environment="development", graph_database="kontroll").database_name == "kontroll"


def test_upload_part_cannot_exceed_upload_limit() -> None:
    with pytest.raises(ValidationError, match="UPLOAD_PART"):
        _settings(environment="development", max_upload_bytes=10, upload_part_bytes=20)
