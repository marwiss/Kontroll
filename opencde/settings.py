# This file was generated with the assistance of an AI coding tool.
"""Server configuration.

Every setting is read from an environment variable prefixed ``OPENCDE_``, from a
``.env`` file in the working directory, or from a Docker secret file named
``/run/secrets/opencde_<setting>``. Nothing is hard-coded for a particular
deployment: the same image runs on a laptop and behind a public domain.

Defaults are safe rather than convenient. The server refuses to start in
production without an ``https`` public URL, a graph database password and a
secret key for signed form tokens and session cookies.
"""

from __future__ import annotations

import os
import secrets
from enum import StrEnum
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

SECRETS_DIR = Path("/run/secrets")

GRAPH_URI_SCHEMES = ("bolt://", "bolt+s://", "bolt+ssc://", "neo4j://", "neo4j+s://", "neo4j+ssc://")

MIN_SECRET_KEY_LENGTH = 32
MIN_PASSWORD_LENGTH = 12


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

    # --- deployment -------------------------------------------------------
    environment: Literal["development", "test", "production"] = Field(
        "production",
        description="'development' relaxes the https requirement and prints readable logs.",
    )
    public_url: str = Field(
        "http://localhost:8000",
        description="Base URL clients use to reach the server. Used in links and OAuth2 metadata. https in production.",
    )
    secret_key: SecretStr = Field(
        SecretStr(""),
        description="Signs form tokens and session cookies. At least 32 characters; required in production.",
    )
    trusted_proxies: list[str] = Field(
        ["127.0.0.1"],
        description="Proxies whose X-Forwarded-* headers are trusted (Caddy, a tunnel). Nothing else is trusted.",
    )
    cors_origins: list[str] = Field(
        ["*"],
        description="Origins allowed to call the API from browsers (Foundation API 1.4). Bearer tokens, never cookies.",
    )

    # --- graph database ---------------------------------------------------
    graph_dialect: GraphDialect = Field(GraphDialect.NEO4J, description="Which graph database the server talks to.")
    graph_uri: str = Field(
        "bolt://localhost:7687", description="Bolt URI. Use neo4j+s:// or bolt+s:// for remote databases."
    )
    graph_user: str = "neo4j"
    graph_password: SecretStr = SecretStr("")
    graph_database: str | None = Field(None, description="Database name. Defaults to 'neo4j' or 'memgraph' by dialect.")
    graph_connect_timeout_seconds: float = Field(5.0, gt=0)
    cleanup_interval_seconds: int = Field(
        60, ge=5, description="How often expired codes, tokens and sessions are deleted."
    )

    # --- storage ----------------------------------------------------------
    data_dir: Path = Field(Path("data"), description="Where uploaded documents and images are stored.")
    max_upload_bytes: int = Field(
        1_073_741_824, gt=0, description="Largest document a client may upload (Documents API)."
    )
    upload_part_bytes: int = Field(52_428_800, gt=0, description="Size of the parts the server asks clients to upload.")
    max_image_bytes: int = Field(10_485_760, gt=0, description="Largest snapshot or bitmap accepted (decoded).")
    max_json_body_bytes: int = Field(
        16_777_216, gt=0, description="Largest accepted JSON request body (viewpoints carry images)."
    )

    # --- OAuth2 and sessions ----------------------------------------------
    authorization_code_ttl_seconds: int = Field(60, ge=10, le=600)
    access_token_ttl_seconds: int = Field(3600, ge=60)
    refresh_token_ttl_seconds: int = Field(30 * 24 * 3600, ge=3600)
    web_session_ttl_seconds: int = Field(8 * 3600, ge=300, description="Absolute lifetime of a browser session.")
    web_session_idle_seconds: int = Field(
        30 * 60, ge=60, description="Browser session ends after this much inactivity."
    )
    form_token_ttl_seconds: int = Field(600, ge=60, description="Validity of signed sign-in and consent forms.")
    documents_session_ttl_seconds: int = Field(
        600, ge=60, description="Validity of Documents API UI links (expires_in)."
    )
    upload_session_ttl_seconds: int = Field(
        24 * 3600, ge=600, description="How long a client has to upload the parts of a document."
    )
    dynamic_client_registration: bool = Field(
        False, description="Offer POST /foundation/oauth2/reg (Foundation API 2.2.3). Off unless you need it."
    )
    allow_localhost_redirects: bool = Field(
        False,
        description="Accept http://localhost redirect URIs besides the loopback IPs RFC 8252 allows. Development only.",
    )
    rate_limits_enabled: bool = True
    admin_ui_enabled: bool = True
    server_assigned_id_prefix: str = Field("ISSUE-", description="Prefix of human-readable topic ids (BCF 3.2.9).")

    # --- optional modules -------------------------------------------------
    ifcgraph_enabled: bool = Field(
        False, description="Convert uploaded IFC models to graph data (needs the ifcgraph extra)."
    )

    # --- logging ----------------------------------------------------------
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_json: bool = Field(True, description="JSON logs for production; set false for readable console logs.")

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
            if len(self.secret_key.get_secret_value()) < MIN_SECRET_KEY_LENGTH:
                raise ValueError(
                    f"OPENCDE_SECRET_KEY must have at least {MIN_SECRET_KEY_LENGTH} characters in production"
                )
            if self.allow_localhost_redirects:
                raise ValueError("OPENCDE_ALLOW_LOCALHOST_REDIRECTS is only allowed outside production")
        elif not self.secret_key.get_secret_value():
            # Development and tests: a fresh key per process keeps things working
            # while making it obvious that nothing signed survives a restart.
            object.__setattr__(self, "secret_key", SecretStr(secrets.token_urlsafe(48)))
        if self.upload_part_bytes > self.max_upload_bytes:
            raise ValueError("OPENCDE_UPLOAD_PART_BYTES cannot exceed OPENCDE_MAX_UPLOAD_BYTES")
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

    def url(self, path: str) -> str:
        """Absolute URL for a server path, built from the public URL."""
        return f"{self.public_url}/{path.lstrip('/')}"
