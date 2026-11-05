# This file was generated with the assistance of an AI coding tool.
import pytest
from pydantic import ValidationError

from opencde.settings import GraphDialect, Settings


def _settings(**values: object) -> Settings:
    return Settings(_env_file=None, **values)  # type: ignore[call-arg]


def test_production_requires_https_public_url() -> None:
    with pytest.raises(ValidationError, match="https"):
        _settings(environment="production", public_url="http://cde.example.com", graph_password="secret-enough")


def test_production_requires_graph_password() -> None:
    with pytest.raises(ValidationError, match="OPENCDE_GRAPH_PASSWORD"):
        _settings(environment="production", public_url="https://cde.example.com")


def test_development_allows_http_localhost() -> None:
    settings = _settings(environment="development", public_url="http://localhost:8000/")
    assert settings.public_url == "http://localhost:8000"  # trailing slash removed for safe concatenation


def test_graph_uri_scheme_is_checked() -> None:
    with pytest.raises(ValidationError, match="OPENCDE_GRAPH_URI"):
        _settings(environment="development", graph_uri="http://localhost:7687")


def test_database_name_follows_dialect() -> None:
    assert _settings(environment="development").database_name == "neo4j"
    assert _settings(environment="development", graph_dialect=GraphDialect.MEMGRAPH).database_name == "memgraph"
    assert _settings(environment="development", graph_database="kontroll").database_name == "kontroll"
