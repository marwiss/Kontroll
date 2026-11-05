# This file was generated with the assistance of an AI coding tool.
"""Health checks shown on the settings page (and usable by ``opencde doctor``)."""

from __future__ import annotations

import os
from dataclasses import dataclass

from opencde import __version__
from opencde.graph.driver import ping_within
from opencde.graph.graph import Graph
from opencde.settings import Settings
from opencde.storage import LocalStorage
from opencde.timeutil import now_iso


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str


async def run_checks(settings: Settings, graph: Graph, storage: LocalStorage) -> list[Check]:
    checks = [Check("Version", True, __version__), Check("Environment", True, settings.environment)]
    https = settings.public_url.startswith("https://")
    checks.append(
        Check(
            "Public URL",
            https or settings.environment != "production",
            settings.public_url + ("" if https else " (http: fine for development only)"),
        )
    )
    reachable = await ping_within(graph.driver, graph.database, settings.graph_connect_timeout_seconds)
    checks.append(
        Check(
            "Graph database",
            reachable,
            f"{graph.dialect.name.value} at {settings.graph_uri}, database {settings.database_name}"
            + ("" if reachable else ": does not answer"),
        )
    )
    probe = storage.root / ".write-probe"
    try:
        probe.write_bytes(b"ok")
        probe.unlink()
        checks.append(Check("Storage", True, f"{storage.root} is writable"))
    except OSError as exc:
        checks.append(Check("Storage", False, f"{storage.root}: {exc.__class__.__name__}"))
    checks.append(Check("Secret key", len(settings.secret_key.get_secret_value()) >= 32, "at least 32 characters"))
    checks.append(
        Check(
            "Rate limits",
            settings.rate_limits_enabled or settings.environment != "production",
            "enabled" if settings.rate_limits_enabled else "disabled (acceptable outside production)",
        )
    )
    checks.append(
        Check(
            "Dynamic client registration",
            True,
            "enabled (POST /foundation/oauth2/reg)" if settings.dynamic_client_registration else "disabled",
        )
    )
    checks.append(Check("Server clock (UTC)", True, now_iso()))
    checks.append(Check("Process", True, f"pid {os.getpid()}"))
    return checks
