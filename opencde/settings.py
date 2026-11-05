# This file was generated with the assistance of an AI coding tool.
"""Server configuration.

Every setting is read from an environment variable prefixed ``OPENCDE_``, from a
``.env`` file in the working directory, or from a Docker secret file named
``/run/secrets/opencde_<setting>``. Nothing is hard-coded for a particular
deployment: the same image runs on a laptop and behind a public domain.

Defaults are safe rather than convenient. The server refuses to start in
production without an ``https`` public URL and a graph database password.
"""

from __future__ import annotations

import os
from enum import StrEnum
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

SECRETS_DIR = Path("/run/secrets")

GRAPH_URI_SCHEMES = ("bolt://", "bolt+s://", "bolt+ssc://", "neo4j://", "neo4j+s://", "neo4j+ssc://")


class GraphDialect(StrEnum):
    """Graph databases the server can talk to through the Bolt protocol."""

    NEO4J = "neo4j"
    MEMGRAPH = "memgraph"


class Settings(BaseSettings):
    """All runtime configuration. Instantiate once at startup."""

    model_config = SettingsConfigDict(
        env_prefix="OPENCDE_",
        env_file=os.environ.get("OPENCDE_ENV_FILE", ".env"),
        env_file_encoding="utf-8",
        secrets_dir=str(SECRETS_DIR) if SECRETS_DIR.is_dir() else None,
        extra="ignore",
    )

    environment: Literal["development", "test", "production"] = Field(
        "production",
        description="'development' relaxes the https requirement and prints readable logs.",
    )
    public_url: str = Field(
        "http://localhost:8000",
        description="Base URL clients use to reach the server. Used in links and OAuth2 metadata. https in production.",
    )

    graph_dialect: GraphDialect = Field(GraphDialect.NEO4J, description="Which graph database the server talks to.")
    graph_uri: str = Field(
        "bolt://localhost:7687", description="Bolt URI. Use neo4j+s:// or bolt+s:// for remote databases."
    )
    graph_user: str = "neo4j"
    graph_password: SecretStr = SecretStr("")
    graph_database: str | None = Field(None, description="Database name. Defaults to 'neo4j' or 'memgraph' by dialect.")
    graph_connect_timeout_seconds: float = Field(5.0, gt=0)

    data_dir: Path = Field(Path("data"), description="Where uploaded documents and images are stored.")

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_json: bool = Field(True, description="JSON logs for production; set false for readable console logs.")

    cors_origins: list[str] = Field(
        ["*"],
        description="Origins allowed to call the API from browsers (Foundation API 1.4). Bearer tokens, never cookies.",
    )
    max_json_body_bytes: int = Field(1_048_576, gt=0, description="Largest accepted JSON request body.")
    trusted_proxies: list[str] = Field(
        ["127.0.0.1"],
        description="Proxies whose X-Forwarded-* headers are trusted (Caddy, a tunnel). Nothing else is trusted.",
    )

    @field_validator("public_url")
    @classmethod
    def _normalize_public_url(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        if not value.startswith(("http://", "https://")):
            raise ValueError("OPENCDE_PUBLIC_URL must start with http:// or https://")
        return value

    @field_validator("graph_uri")
    @classmethod
    def _check_graph_uri(cls, value: str) -> str:
        if not value.startswith(GRAPH_URI_SCHEMES):
            raise ValueError(f"OPENCDE_GRAPH_URI must use one of {', '.join(GRAPH_URI_SCHEMES)}")
        return value

    @model_validator(mode="after")
    def _production_guards(self) -> Self:
        if self.environment == "production":
            if not self.public_url.startswith("https://"):
                raise ValueError(
                    "OPENCDE_PUBLIC_URL must be https in production "
                    "(set OPENCDE_ENVIRONMENT=development for local testing)"
                )
            if not self.graph_password.get_secret_value():
                raise ValueError("OPENCDE_GRAPH_PASSWORD is required in production")
        return self

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def database_name(self) -> str:
        """The graph database to use, by explicit setting or by dialect default."""
        if self.graph_database:
            return self.graph_database
        return {GraphDialect.NEO4J: "neo4j", GraphDialect.MEMGRAPH: "memgraph"}[self.graph_dialect]
