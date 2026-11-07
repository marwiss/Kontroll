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

from limits import parse
from pydantic import Field, SecretStr, ValidationInfo, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

SECRETS_DIR = Path("/run/secrets")

RATE_LIMIT_STORES = ("memory://", "redis://", "rediss://")
GRAPH_URI_SCHEMES = ("bolt://", "bolt+s://", "bolt+ssc://", "neo4j://", "neo4j+s://", "neo4j+ssc://")
# A published Bolt address must be encrypted with a certificate clients can verify ("+ssc" trusts anything).
SECURE_GRAPH_URI_SCHEMES = ("bolt+s://", "neo4j+s://")

MIN_SECRET_KEY_LENGTH = 32
MIN_PASSWORD_LENGTH = 12
SECRET_KEY_FILE = "secret_key"  # a file name under the data directory, not a key  # noqa: S105  # nosec B105


def _stored_secret_key(data_dir: Path) -> str:
    """A generated key kept in the data directory, so that restarts and worker processes share it.

    Production refuses to run without an explicit key. Outside production a key that changed on
    every start voided every sign-in form and session at each restart, which the first reader of
    the quick start met as "the sign-in form has expired". A directory that cannot hold the file
    leaves a key for this process only.
    """
    path = data_dir / SECRET_KEY_FILE
    try:
        stored = path.read_text(encoding="utf-8").strip()
        if len(stored) >= MIN_SECRET_KEY_LENGTH:
            return stored
    except FileNotFoundError:
        pass
    except OSError:
        return secrets.token_urlsafe(48)
    key = secrets.token_urlsafe(48)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:  # another process wrote it first
        return _stored_secret_key(data_dir)
    except OSError:
        return key
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(key)
    return key


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
        hide_input_in_errors=True,  # a refused value can be, or hold, a password
    )

    # --- deployment -------------------------------------------------------
    environment: Literal["development", "test", "production"] = Field(
        "production",
        description="'development' relaxes the https requirement and prints readable logs.",
    )
    public_url: str = Field(
        "http://127.0.0.1:8000",
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
    ntp_server: str = Field(
        "pool.ntp.org",
        description="NTP server for the clock check of `opencde doctor` and the settings page. Empty disables it.",
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
    refresh_token_idle_seconds: int = Field(
        14 * 24 * 3600,
        ge=3600,
        description="A refresh token unused for this long stops working; the user signs in again.",
    )
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
    dynamic_client_registration_token: SecretStr = Field(
        SecretStr(""),
        description="When set, registering takes this value as a bearer token (RFC 7591 initial access token).",
    )
    dynamic_client_approval: bool = Field(
        False, description="A self-registered client can sign nobody in until an administrator approves it."
    )
    dynamic_client_unused_days: int = Field(
        30,
        ge=1,
        description="A self-registered client that issues no token for this many days is deleted with its tokens.",
    )
    request_log_enabled: bool = Field(
        False,
        description="Keep a log of every request (method, path, status, timing, caller; never bodies or tokens) "
        "for /admin/requests and /admin/api/requests. An extension outside the specifications.",
    )
    request_log_retention_hours: int = Field(72, ge=1, description="How long request log entries are kept.")
    admin_api_enabled: bool = Field(
        True, description="Serve the JSON administration API under /admin/api (bearer tokens with the admin scope)."
    )
    dataspatium_url: str | None = Field(
        None,
        description="Address of a Dataspatium installation to link to from the server's pages and the "
        "capabilities document (an extension outside the specifications).",
    )
    graph_public_bolt_url: str | None = Field(
        None,
        description="Bolt address of the graph database as clients may reach it, announced in the capabilities "
        "document. Leave empty unless the database is deliberately published (the development overlay does on "
        "bolt://127.0.0.1:7697).",
    )
    graph_query_enabled: bool = Field(
        False,
        description="Offer POST /admin/api/graph/query: read-only Cypher against the whole graph for administrators "
        "holding the admin scope (an extension outside the specifications). Off unless an administration client "
        "needs it.",
    )
    graph_query_max_rows: int = Field(
        1000, ge=1, le=10_000, description="Rows a graph query may return; the rest is cut and marked truncated."
    )
    graph_query_timeout_seconds: float = Field(
        10.0, gt=0, le=120, description="A graph query running longer than this is stopped."
    )
    allow_localhost_redirects: bool = Field(
        False,
        description="Accept http://localhost redirect URIs besides the loopback IPs RFC 8252 allows. Development only.",
    )
    rate_limits_enabled: bool = True
    rate_limit_api: str = Field(
        "600/minute",
        description="Requests per address. Everyone behind one address shares them, so a large office may raise it.",
    )
    rate_limit_sign_in: str = Field(
        "10/minute",
        description="Sign-in attempts per address, shared the same way; the wait per user name stops guessing anyway.",
    )
    rate_limit_storage: SecretStr = Field(
        SecretStr("memory://"),
        description="Where the counts live. Several server processes share a store such as redis://host:6379/0.",
    )
    sign_in_throttle_enabled: bool = Field(True, description="Make a user name wait after repeated failed sign-ins.")
    sign_in_free_attempts: int = Field(5, ge=1, description="Failures in a row before the wait begins.")
    sign_in_delay_seconds: int = Field(30, ge=1, description="The first wait; each further failure doubles it.")
    sign_in_max_delay_seconds: int = Field(
        900, ge=1, description="The ceiling, so that nobody can lock an account out."
    )
    admin_ui_enabled: bool = True
    api_docs_enabled: bool | None = Field(
        None,
        description="Serve the interactive API documentation at /docs (Swagger UI, loaded from a CDN). "
        "Unset means: only outside production. The OpenAPI document at /openapi.json is always served.",
    )
    server_assigned_id_prefix: str = Field("ISSUE-", description="Prefix of human-readable topic ids (BCF 3.2.9).")

    # --- optional modules -------------------------------------------------
    ifcgraph_enabled: bool = Field(
        False, description="Convert uploaded IFC models to graph data (needs the ifcgraph extra)."
    )
    ifcgraph_timeout_seconds: int = Field(900, ge=10, description="Kill a conversion that takes longer.")
    ifcgraph_memory_mb: int = Field(4096, ge=256, description="Address-space limit of the conversion worker (POSIX).")
    ifcgraph_max_entities: int = Field(5_000_000, ge=1000, description="Refuse models with more entities.")
    ifcgraph_include_geometry: bool = Field(
        False, description="Also import representation items, profiles and placements (much larger graphs)."
    )
    ifcgraph_lossless: bool = Field(
        False,
        description="Keep all of a converted model in the graph, geometry included, so that the file can be written back.",
    )
    ifcgraph_gtin_property_set: str = Field("Reuse", description="Property set holding the GTIN of an element.")
    ifcgraph_gtin_property: str = Field("GTIN", description="Property within that set.")

    # --- logging ----------------------------------------------------------
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_json: bool = Field(True, description="JSON logs for production; set false for readable console logs.")

    @field_validator("rate_limit_api", "rate_limit_sign_in")
    @classmethod
    def _check_rate_limit(cls, value: str, info: ValidationInfo) -> str:
        try:
            parse(value)
        except ValueError:
            raise ValueError(f'OPENCDE_{str(info.field_name).upper()} must read like "600/minute"') from None
        return value

    @field_validator("rate_limit_storage")
    @classmethod
    def _check_rate_limit_storage(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().startswith(RATE_LIMIT_STORES):
            raise ValueError(f"OPENCDE_RATE_LIMIT_STORAGE must use one of {', '.join(RATE_LIMIT_STORES)}")
        return value

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

    @field_validator("graph_public_bolt_url")
    @classmethod
    def _check_public_bolt_url(cls, value: str | None) -> str | None:
        value = (value or "").strip() or None
        if value is not None and not value.startswith(GRAPH_URI_SCHEMES):
            raise ValueError(f"OPENCDE_GRAPH_PUBLIC_BOLT_URL must use one of {', '.join(GRAPH_URI_SCHEMES)}")
        return value

    @model_validator(mode="after")
    def _production_guards(self) -> Self:
        if self.environment == "production":
            if not self.public_url.startswith("https://"):
                raise ValueError(
                    "OPENCDE_PUBLIC_URL must be https in production "
                    "(set OPENCDE_ENVIRONMENT=development for local testing)"
                )
            if self.graph_public_bolt_url and not self.graph_public_bolt_url.startswith(SECURE_GRAPH_URI_SCHEMES):
                # A published database port carries the database password; never announce it in the clear.
                raise ValueError(
                    "OPENCDE_GRAPH_PUBLIC_BOLT_URL must use bolt+s:// or neo4j+s:// in production (docs/deploy/bolt.md)"
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
            # Development and tests: a generated key, kept in the data directory so that
            # forms and sessions survive a restart and every worker signs the same way.
            object.__setattr__(self, "secret_key", SecretStr(_stored_secret_key(self.data_dir)))
        if self.upload_part_bytes > self.max_upload_bytes:
            raise ValueError("OPENCDE_UPLOAD_PART_BYTES cannot exceed OPENCDE_MAX_UPLOAD_BYTES")
        return self

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def api_docs_on(self) -> bool:
        """Whether /docs is served: the explicit setting, or everywhere except production."""
        return self.api_docs_enabled if self.api_docs_enabled is not None else not self.is_production

    @property
    def database_name(self) -> str:
        """The graph database to use, by explicit setting or by dialect default."""
        if self.graph_database:
            return self.graph_database
        return {GraphDialect.NEO4J: "neo4j", GraphDialect.MEMGRAPH: "memgraph"}[self.graph_dialect]

    def url(self, path: str) -> str:
        """Absolute URL for a server path, built from the public URL."""
        return f"{self.public_url}/{path.lstrip('/')}"
