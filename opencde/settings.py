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
from contextvars import ContextVar
from enum import StrEnum
from pathlib import Path
from typing import Literal, Self
from urllib.parse import urlsplit

from limits import parse
from pydantic import AliasChoices, Field, PrivateAttr, SecretStr, ValidationInfo, field_validator, model_validator
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

SECRETS_DIR = Path("/run/secrets")

# The IFC-LPG module was the IFC-graph module until November 2026. Its settings are read by their new names first and by the
# old ones still, so that a server keeps its configuration across the upgrade, and the old names in use are reported.
IFC_PREFIX = "OPENCDE_IFC_LPG_"
OLD_IFC_PREFIX = "OPENCDE_IFCGRAPH_"
_IFC_FIELD = "ifcgraph_"
_OLD_NAMES_SEEN: ContextVar[tuple[str, ...]] = ContextVar("old_setting_names", default=())


def _ifc(name: str) -> AliasChoices:
    """Where an IFC-LPG setting is read from: its own name, then the name it had until November 2026."""
    return AliasChoices(IFC_PREFIX + name.upper(), OLD_IFC_PREFIX + name.upper())


def env_name(field: str) -> str:
    """The environment variable a setting is read from, as the documentation names it."""
    if field.startswith(_IFC_FIELD):
        return IFC_PREFIX + field.removeprefix(_IFC_FIELD).upper()
    return "OPENCDE_" + field.upper()


def _paths(value: object) -> list[Path]:
    if isinstance(value, str | os.PathLike):
        return [Path(value)]
    if isinstance(value, list | tuple):
        return [Path(item) for item in value if isinstance(item, str | os.PathLike)]
    return []


def _names_given(env_file: object, secrets_dir: object) -> set[str]:
    """The names of the variables, env-file lines and secret files a server is given. Values are never read."""
    names = {name.upper() for name in os.environ}
    for path in _paths(env_file):
        if path.is_file():
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                key, sep, _ = line.strip().removeprefix("export ").partition("=")
                if sep and key and not key.startswith("#"):
                    names.add(key.strip().upper())
    for folder in _paths(secrets_dir):
        if folder.is_dir():
            names.update(entry.name.upper() for entry in folder.iterdir())
    return names


RATE_LIMIT_STORES = ("memory://", "redis://", "rediss://")
GRAPH_URI_SCHEMES = ("bolt://", "bolt+s://", "bolt+ssc://", "neo4j://", "neo4j+s://", "neo4j+ssc://")
# A published Bolt address must be encrypted with a certificate clients can verify ("+ssc" trusts anything).
SECURE_GRAPH_URI_SCHEMES = ("bolt+s://", "neo4j+s://")

#: What the local engine answers to as Host and public URL (ADR 0023).
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
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
        validate_by_name=True,  # a setting with other names (the IFC-LPG ones) is still given by its field's name
    )
    _old_names: tuple[str, ...] = PrivateAttr(default=())

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """The usual sources. On the way, note the old names of renamed settings among what they are given."""
        given = _names_given(
            getattr(dotenv_settings, "env_file", None), getattr(file_secret_settings, "secrets_dir", None)
        )
        _OLD_NAMES_SEEN.set(tuple(sorted(name for name in given if name.startswith(OLD_IFC_PREFIX))))
        return init_settings, env_settings, dotenv_settings, file_secret_settings

    @model_validator(mode="after")
    def _remember_old_names(self) -> Self:
        self._old_names = _OLD_NAMES_SEEN.get()
        _OLD_NAMES_SEEN.set(())
        return self

    @property
    def renamed_settings(self) -> list[tuple[str, str]]:
        """The old names this server is given for renamed settings, each with the name to use instead."""
        return [(old, IFC_PREFIX + old.removeprefix(OLD_IFC_PREFIX)) for old in self._old_names]

    # --- deployment -------------------------------------------------------
    environment: Literal["development", "test", "production", "local"] = Field(
        "production",
        description="'development' relaxes the https requirement and prints readable logs; 'local' is the engine on "
        "a person's own computer: http on the loopback only, with a Host check, explicit CORS origins and the "
        "passwords `opencde init --local` wrote (ADR 0023).",
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
    # --- the working copy (ADR 0024) ---------------------------------------
    workcopy_graph_uri: str | None = Field(
        None,
        description="Bolt URI of a second graph, the working copy, where the head model of every document is "
        "imported too for fast queries (Memgraph, in memory); the first graph stays the archive. Empty: none.",
    )
    workcopy_graph_dialect: GraphDialect = Field(GraphDialect.MEMGRAPH, description="The working copy's dialect.")
    workcopy_graph_user: str = ""
    workcopy_graph_password: SecretStr = SecretStr("")
    workcopy_graph_database: str | None = Field(None, description="The working copy's database name; by dialect.")
    # --- the server's own storage (F24 a) ---------------------------------
    store_graph_uri: str | None = Field(
        None,
        description="Bolt URI of a graph for the server's own data (accounts, documents, topics, jobs), apart from the "
        "IFC graph; the two meet by values only. Refused until every statement of the server follows; empty: the IFC graph's connection holds both.",
    )
    store_graph_dialect: GraphDialect = Field(GraphDialect.NEO4J, description="The server's own graph's dialect.")
    store_graph_user: str = ""
    store_graph_password: SecretStr = SecretStr("")
    store_graph_database: str | None = Field(None, description="The server's own graph's database name; by dialect.")
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
    apis: list[Literal["bcf-3.0", "bcf-2.1", "documents"]] = Field(
        ["bcf-3.0", "bcf-2.1", "documents"],
        description="The APIs the server offers. The Foundation API comes with BCF API 3.0 and the Documents API, which "
        'need it. ["bcf-2.1"] makes a server for BCF API 2.1 alone, ["documents"] a document server.',
    )

    # --- optional modules -------------------------------------------------
    # The IFC-LPG module: read as OPENCDE_IFC_LPG_*, and still as OPENCDE_IFCGRAPH_* (see `_ifc`).
    ifcgraph_enabled: bool = Field(
        False,
        validation_alias=_ifc("enabled"),
        description="Convert uploaded IFC models to graph data (needs the ifc-lpg extra).",
    )
    ifcgraph_timeout_seconds: int = Field(
        900, ge=10, validation_alias=_ifc("timeout_seconds"), description="Kill a conversion that takes longer."
    )
    ifcgraph_memory_mb: int = Field(
        4096,
        ge=256,
        validation_alias=_ifc("memory_mb"),
        description="Address-space limit of the conversion worker (POSIX).",
    )
    ifcgraph_max_entities: int = Field(
        5_000_000, ge=1000, validation_alias=_ifc("max_entities"), description="Refuse models with more entities."
    )
    ifcgraph_include_geometry: bool = Field(
        False,
        validation_alias=_ifc("include_geometry"),
        description="Also import representation items, profiles and placements (much larger graphs).",
    )
    ifcgraph_lossless: bool = Field(
        True,
        validation_alias=_ifc("lossless"),
        description="Keep all of a converted model in the graph, geometry as text, so that the file can be written back.",
    )
    ifcgraph_spatial: bool = Field(
        True,
        validation_alias=_ifc("spatial"),
        description="After a conversion, work out where every product is: a box per product in the graph and the "
        "geometry records that `GET …/ifc-geometry` builds glTF from (needs the ifc-lpg extra).",
    )
    ifcgraph_geometry_threads: int = Field(
        2, ge=1, le=64, validation_alias=_ifc("geometry_threads"), description="Threads of the geometry worker."
    )
    ifcgraph_validate_uploads: bool = Field(
        True,
        validation_alias=_ifc("validate_uploads"),
        description="Check every IFC file uploaded as a document version against the IFC schema, and show the result "
        "in the version's metadata.",
    )
    ifcgraph_gherkin_env: str = Field(
        "",
        validation_alias=_ifc("gherkin_env"),
        description="Folder of the environment buildingSMART's ifc-gherkin-rules run in, made by "
        "`python -m ifc_lpg.gherkin_install`; uploads are then checked against them too. Empty leaves them out.",
    )
    ifcgraph_clash_enabled: bool = Field(
        False,
        validation_alias=_ifc("clash_enabled"),
        description="Offer the clash check between two IFC document versions, run with IfcClash in a worker process "
        "(needs the ifc-lpg extra and the IFC-LPG module).",
    )
    ifcgraph_clash_max_clashes: int = Field(
        10_000,
        ge=100,
        le=100_000,
        validation_alias=_ifc("clash_max_clashes"),
        description="The most clashes a report keeps.",
    )
    ifcgraph_gtin_property_set: str = Field(
        "Reuse", validation_alias=_ifc("gtin_property_set"), description="Property set holding the GTIN of an element."
    )
    ifcgraph_gtin_property: str = Field(
        "GTIN", validation_alias=_ifc("gtin_property"), description="Property within that set."
    )
    # --- buildingSMART's Data Dictionary (OB-42) ----------------------------
    bsdd_enabled: bool = Field(
        False,
        description="Check the classification references of every IFC upload, and the Pset_ and Qto_ sets of an "
        "IFC 4.3 file, against buildingSMART's Data Dictionary (bSDD) over the network, as the check `bsdd` of the "
        "version's report. Off unless the server may reach bSDD.",
    )
    bsdd_api_url: str = Field(
        "https://api.bsdd.buildingsmart.org",
        description="Where bSDD's API answers: the official release, or https://test.bsdd.buildingsmart.org.",
    )
    bsdd_timeout_seconds: float = Field(10.0, gt=0, le=120, description="The time limit of each question to bSDD.")
    bsdd_cache_seconds: int = Field(
        86_400,
        ge=0,
        description="How long an answer of bSDD is kept in memory, so that a server process asks about a URI once "
        "a day; 0 asks every time.",
    )

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

    @field_validator("apis")
    @classmethod
    def _some_api(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError('OPENCDE_APIS must name at least one of "bcf-3.0", "bcf-2.1" and "documents"')
        return list(dict.fromkeys(value))

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

    @field_validator("store_graph_uri")
    @classmethod
    def _store_not_yet(cls, value: str | None) -> str | None:
        """The server's own data cannot be put in another graph yet: the IFC-LPG service's own records, the command
        line, the backup and the doctor still open the IFC graph alone (ADR 0027, the third step)."""
        if value is not None:
            raise ValueError(
                "OPENCDE_STORE_GRAPH_URI is not supported yet: the server's own data shares the IFC graph's connection"
            )
        return value

    @field_validator("workcopy_graph_uri")
    @classmethod
    def _workcopy_uri(cls, value: str | None) -> str | None:
        value = (value or "").strip() or None
        if value is not None and not value.startswith(GRAPH_URI_SCHEMES):
            raise ValueError(f"OPENCDE_WORKCOPY_GRAPH_URI must use one of {', '.join(GRAPH_URI_SCHEMES)}")
        return value

    @field_validator("bsdd_api_url")
    @classmethod
    def _check_bsdd_api_url(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        if not value.startswith(("http://", "https://")):
            raise ValueError("OPENCDE_BSDD_API_URL must start with http:// or https://")
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
                    "OPENCDE_GRAPH_PUBLIC_BOLT_URL must use bolt+s:// or neo4j+s:// in production (docs/en/deploy/bolt.md)"
                )
            if not self.graph_password.get_secret_value():
                raise ValueError("OPENCDE_GRAPH_PASSWORD is required in production")
            if len(self.secret_key.get_secret_value()) < MIN_SECRET_KEY_LENGTH:
                raise ValueError(
                    f"OPENCDE_SECRET_KEY must have at least {MIN_SECRET_KEY_LENGTH} characters in production"
                )
            if self.allow_localhost_redirects:
                raise ValueError("OPENCDE_ALLOW_LOCALHOST_REDIRECTS is only allowed outside production")
            if self.bsdd_enabled and not self.bsdd_api_url.startswith("https://"):
                raise ValueError("OPENCDE_BSDD_API_URL must be https in production")
        elif self.environment == "local":
            host = urlsplit(self.public_url).hostname or ""
            if not self.public_url.startswith(("http://", "https://")) or host not in LOOPBACK_HOSTS:
                raise ValueError(
                    "OPENCDE_PUBLIC_URL must be the loopback in the local environment, such as http://127.0.0.1:8000"
                )
            if not self.graph_password.get_secret_value():
                raise ValueError("OPENCDE_GRAPH_PASSWORD is required in the local environment (opencde init --local)")
            if len(self.secret_key.get_secret_value()) < MIN_SECRET_KEY_LENGTH:
                raise ValueError(
                    f"OPENCDE_SECRET_KEY must have at least {MIN_SECRET_KEY_LENGTH} characters in the local environment"
                )
            if "*" in self.cors_origins:
                raise ValueError(
                    "OPENCDE_CORS_ORIGINS must name the origins in the local environment; '*' is not allowed there"
                )
            if self.graph_public_bolt_url:
                raise ValueError("OPENCDE_GRAPH_PUBLIC_BOLT_URL is not used in the local environment")
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
    def is_local(self) -> bool:
        """The engine on a person's own computer (ADR 0023): loopback only, with a Host check."""
        return self.environment == "local"

    def offers(self, api: str) -> bool:
        """Whether the server offers an API: "bcf-3.0", "bcf-2.1", "documents", or "foundation", which comes with
        the two that need it."""
        if api == "foundation":
            return "bcf-3.0" in self.apis or "documents" in self.apis
        return api in self.apis

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

    @property
    def has_workcopy(self) -> bool:
        return self.workcopy_graph_uri is not None

    @property
    def has_store(self) -> bool:
        return self.store_graph_uri is not None

    @property
    def store_database_name(self) -> str:
        if self.store_graph_database:
            return self.store_graph_database
        return {GraphDialect.NEO4J: "neo4j", GraphDialect.MEMGRAPH: "memgraph"}[self.store_graph_dialect]

    @property
    def workcopy_database_name(self) -> str:
        if self.workcopy_graph_database:
            return self.workcopy_graph_database
        return {GraphDialect.NEO4J: "neo4j", GraphDialect.MEMGRAPH: "memgraph"}[self.workcopy_graph_dialect]

    def url(self, path: str) -> str:
        """Absolute URL for a server path, built from the public URL."""
        return f"{self.public_url}/{path.lstrip('/')}"
