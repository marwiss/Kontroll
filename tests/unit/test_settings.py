# This file was generated with the assistance of an AI coding tool.
import tempfile
from pathlib import Path

import pytest
from pydantic import ValidationError

from opencde.settings import GraphDialect, Settings


def _settings(**values: object) -> Settings:
    values.setdefault("data_dir", Path(tempfile.mkdtemp()) / "data")  # a generated key lands there, not in the tree
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


def test_a_published_bolt_address_must_be_encrypted_in_production() -> None:
    """An open database port carries the database password; production announces it only over TLS."""
    for insecure in ("bolt://cde.example.com:7687", "neo4j+ssc://cde.example.com:7687"):
        with pytest.raises(ValidationError, match="bolt\\+s://"):
            _settings(environment="production", **PROD, graph_public_bolt_url=insecure)
    secure = _settings(environment="production", **PROD, graph_public_bolt_url="bolt+s://cde.example.com:7687")
    assert secure.graph_public_bolt_url == "bolt+s://cde.example.com:7687"
    with pytest.raises(ValidationError, match="OPENCDE_GRAPH_PUBLIC_BOLT_URL"):
        _settings(environment="development", graph_public_bolt_url="https://cde.example.com:7687")
    local = _settings(environment="development", graph_public_bolt_url="bolt://localhost:7697")
    assert local.graph_public_bolt_url == "bolt://localhost:7697", "plain Bolt is fine outside production"
    blank = _settings(environment="development", graph_public_bolt_url="  ")
    assert blank.graph_public_bolt_url is None, "blank means not published"


def test_development_allows_http_localhost_and_generates_a_key(tmp_path: Path) -> None:
    settings = _settings(environment="development", public_url="http://localhost:8000/", data_dir=tmp_path / "data")
    assert settings.public_url == "http://localhost:8000"  # trailing slash removed for safe concatenation
    assert len(settings.secret_key.get_secret_value()) >= 32
    assert settings.url("/foundation/versions") == "http://localhost:8000/foundation/versions"


def test_a_generated_key_is_kept_in_the_data_directory(tmp_path: Path) -> None:
    """Restarts and worker processes sign forms and sessions with the same key; an explicit key is left alone."""
    first = _settings(environment="development", data_dir=tmp_path / "data")
    second = _settings(environment="development", data_dir=tmp_path / "data")
    assert first.secret_key.get_secret_value() == second.secret_key.get_secret_value()
    assert (tmp_path / "data" / "secret_key").read_text(encoding="utf-8") == first.secret_key.get_secret_value()
    explicit = _settings(environment="development", data_dir=tmp_path / "data", secret_key="k" * 40)
    assert explicit.secret_key.get_secret_value() == "k" * 40
    elsewhere = _settings(environment="development", data_dir=tmp_path / "other")
    assert elsewhere.secret_key.get_secret_value() != first.secret_key.get_secret_value()


def test_graph_uri_scheme_is_checked() -> None:
    with pytest.raises(ValidationError, match="OPENCDE_GRAPH_URI"):
        _settings(environment="development", graph_uri="http://localhost:7687")


def test_database_name_follows_dialect() -> None:
    assert _settings(environment="development").database_name == "neo4j"
    assert _settings(environment="development", graph_dialect=GraphDialect.MEMGRAPH).database_name == "memgraph"
    assert _settings(environment="development", graph_database="dataregium").database_name == "dataregium"


def test_upload_part_cannot_exceed_upload_limit() -> None:
    with pytest.raises(ValidationError, match="UPLOAD_PART"):
        _settings(environment="development", max_upload_bytes=10, upload_part_bytes=20)
