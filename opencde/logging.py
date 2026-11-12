# This file was generated with the assistance of an AI coding tool.
"""Structured logging with secret redaction.

Every log line is a JSON object (or a readable console line in development)
carrying the request id bound by the middleware. Values under keys that look
like credentials are replaced before anything is written, so a careless
``log.info("token", access_token=...)`` can never leak.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Mapping, MutableMapping
from typing import Any

import structlog

REDACTED = "[redacted]"

# Keys containing any of these fragments are redacted (``access_token``,
# ``refresh_token_hash``, ``db_password``, ``Set-Cookie`` ...). Hiding a harmless
# counter now and then is a price worth paying for never leaking a credential.
SENSITIVE_FRAGMENTS = (
    "token",
    "secret",
    "password",
    "passwd",
    "authorization",
    "cookie",
    "api_key",
    "apikey",
    "credential",
)
# Exact key names that carry OAuth2 or login secrets without a telling name.
SENSITIVE_KEYS = frozenset({"code", "code_verifier", "otp", "pin"})


def _is_sensitive(key: str) -> bool:
    lowered = key.lower()
    return lowered in SENSITIVE_KEYS or any(fragment in lowered for fragment in SENSITIVE_FRAGMENTS)


def _redact(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {k: REDACTED if isinstance(k, str) and _is_sensitive(k) else _redact(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return type(value)(_redact(v) for v in value)
    return value


def redact_secrets(_logger: Any, _method: str, event_dict: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
    """structlog processor: mask credential-like keys at any depth of the event."""
    for key in list(event_dict):
        event_dict[key] = REDACTED if _is_sensitive(key) else _redact(event_dict[key])
    return event_dict


def configure_logging(level: str = "INFO", json_output: bool = True) -> None:
    """Route structlog and stdlib logging (uvicorn included) through one pipeline."""
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        redact_secrets,
        structlog.processors.StackInfoRenderer(),
    ]
    if json_output:
        # A traceback without the frames' locals: they hold request bodies, tokens and secrets, by value.
        frames = structlog.tracebacks.ExceptionDictTransformer(show_locals=False)
        shared_processors.append(structlog.processors.ExceptionRenderer(frames))
        renderer: Any = structlog.processors.JSONRenderer()
    else:
        shared_processors.append(structlog.processors.format_exc_info)
        renderer = structlog.dev.ConsoleRenderer()

    numeric_level = logging.getLevelNamesMapping()[level.upper()]
    structlog.configure(
        processors=[*shared_processors, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[structlog.stdlib.ProcessorFormatter.remove_processors_meta, renderer],
        foreign_pre_chain=shared_processors,
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(numeric_level)

    # uvicorn installs its own handlers; let its records flow through ours instead.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True

    # The Bolt driver logs every protocol message at DEBUG; that drowns the
    # application log, so the driver never goes below INFO.
    logging.getLogger("neo4j").setLevel(max(numeric_level, logging.INFO))


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
