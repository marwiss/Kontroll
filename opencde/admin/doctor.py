# This file was generated with the assistance of an AI coding tool.
"""Health checks shown on the settings page and printed by ``opencde doctor``."""

from __future__ import annotations

import asyncio
import os
import socket
import struct
import time
from dataclasses import dataclass, field
from typing import Any

import httpx
from neo4j.exceptions import Neo4jError

from opencde import __version__
from opencde.graph.driver import ping_within
from opencde.graph.graph import Graph
from opencde.graph.schema import UNIQUE
from opencde.settings import Settings
from opencde.storage import LocalStorage
from opencde.timeutil import now_iso
from opencde.ui.i18n import translate

NTP_EPOCH_OFFSET = 2_208_988_800  # seconds from 1900-01-01 (NTP epoch) to 1970-01-01 (Unix epoch)
NTP_PORT = 123
MAX_CLOCK_OFFSET_SECONDS = 5.0  # codes live 60 s and tokens carry expiry times: the clock must be roughly right


@dataclass(frozen=True)
class Check:
    """One check's result. Its words live in the language catalogues: ``check.<key>`` names it and
    ``check.detail.<detail_key>`` says how it went; a value that needs no words goes in ``value``."""

    key: str
    ok: bool
    detail_key: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    value: str = ""

    def name_in(self, lang: str) -> str:
        return translate(lang, f"check.{self.key}")

    def detail_in(self, lang: str) -> str:
        return translate(lang, f"check.detail.{self.detail_key}", **self.params) if self.detail_key else self.value

    @property
    def name(self) -> str:
        """In English, for the command line and the administration API."""
        return self.name_in("en")

    @property
    def detail(self) -> str:
        return self.detail_in("en")


def ntp_offset_from_response(data: bytes, sent: float, received: float) -> float | None:
    """The local clock's offset from the server's transmit timestamp in an SNTP response (RFC 4330)."""
    if len(data) < 48:
        return None
    seconds, fraction = struct.unpack("!II", data[40:48])
    server_time = seconds - NTP_EPOCH_OFFSET + fraction / 2**32
    return server_time - (sent + received) / 2


def ntp_offset_seconds(server: str, timeout: float = 1.5) -> float | None:
    """Ask an NTP server what time it is, SNTP client mode, and return the offset; None when it does not answer."""
    request = b"\x1b" + bytes(47)  # leap indicator 0, version 3, mode 3 (client)
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(timeout)
            sent = time.time_ns() / 1e9
            sock.sendto(request, (server, NTP_PORT))
            data, _ = sock.recvfrom(48)
            received = time.time_ns() / 1e9
    except OSError:
        return None
    return ntp_offset_from_response(data, sent, received)


async def clock_check(server: str) -> Check:
    """Compare the server clock with NTP; expiry times are only as good as the clock."""
    if not server:
        return Check("clock", True, "not_checked_no_ntp", {"now": now_iso()})
    offset = await asyncio.to_thread(ntp_offset_seconds, server)
    if offset is None:
        return Check("clock", True, "not_checked_ntp", {"server": server, "port": NTP_PORT, "now": now_iso()})
    return Check(
        "clock",
        abs(offset) <= MAX_CLOCK_OFFSET_SECONDS,
        "clock_offset",
        {"offset": f"{offset:+.2f}", "server": server, "now": now_iso()},
    )


async def schema_check(graph: Graph) -> Check:
    """The unique constraints the server relies on; it creates them when it starts."""
    try:
        rows = await graph.schema_rows(graph.dialect.list_constraints)
    except Neo4jError as exc:
        return Check("schema", False, "schema_unlisted", {"code": exc.code})
    counts = {"found": len(rows), "expected": len(UNIQUE)}
    complete = len(rows) >= len(UNIQUE)
    return Check("schema", complete, "schema_count" if complete else "schema_short", counts)


async def headers_check(settings: Settings, transport: httpx.AsyncBaseTransport | None = None) -> Check:
    """Ask the server at its public address, which also tries the TLS certificate when the address is https."""
    url = settings.url("/healthz")
    try:
        async with httpx.AsyncClient(timeout=3.0, transport=transport) as client:
            response = await client.get(url)
    except httpx.HTTPError as exc:
        if "CERTIFICATE" in str(exc).upper():
            return Check("headers", False, "headers_certificate", {"url": url})
        return Check("headers", True, "headers_no_answer", {"url": url})
    wanted = ["x-content-type-options", "content-security-policy", "referrer-policy"]
    if settings.is_production:
        wanted.append("strict-transport-security")  # the proxy in front adds this one
    missing = [name for name in wanted if name not in response.headers]
    if missing:
        return Check("headers", False, "headers_missing", {"names": ", ".join(missing)})
    return Check("headers", True, "headers_present", {"url": url})


async def run_checks(settings: Settings, graph: Graph, storage: LocalStorage) -> list[Check]:
    checks = [Check("version", True, value=__version__), Check("environment", True, value=settings.environment)]
    checks.append(Check("apis", True, value=", ".join(settings.apis)))
    https = settings.public_url.startswith("https://")
    fine = https or settings.environment != "production"
    checks.append(
        Check("public_url", fine, value=settings.public_url)
        if https
        else Check("public_url", fine, "public_url_http", {"url": settings.public_url})
    )
    reachable = await ping_within(graph.driver, graph.database, settings.graph_connect_timeout_seconds)
    where = {"dialect": graph.dialect.name.value, "uri": settings.graph_uri, "database": settings.database_name}
    checks.append(Check("graph", reachable, "graph_ok" if reachable else "graph_silent", where))
    checks.append(await schema_check(graph) if reachable else Check("schema", False, "schema_no_database"))
    probe = storage.root / ".write-probe"
    try:
        probe.write_bytes(b"ok")
        probe.unlink()
        checks.append(Check("storage", True, "storage_ok", {"path": str(storage.root)}))
    except OSError as exc:
        checks.append(
            Check("storage", False, "storage_failed", {"path": str(storage.root), "error": type(exc).__name__})
        )
    if settings.renamed_settings:  # the old names still work, so this is a reminder rather than a fault
        names = ", ".join(f"{old} → {new}" for old, new in settings.renamed_settings)
        checks.append(Check("renamed_settings", True, "renamed_settings", {"names": names}))
    checks.append(Check("secret_key", len(settings.secret_key.get_secret_value()) >= 32, "secret_key"))
    checks.append(
        Check(
            "rate_limits",
            settings.rate_limits_enabled or settings.environment != "production",
            "rate_limits_on" if settings.rate_limits_enabled else "rate_limits_off",
        )
    )
    registration = "registration_on" if settings.dynamic_client_registration else "registration_off"
    checks.append(Check("dynamic_registration", True, registration))
    checks.append(Check("cors", True, "cors_origins", {"origins": ", ".join(settings.cors_origins)}))
    checks.append(await headers_check(settings))
    checks.append(await clock_check(settings.ntp_server))
    checks.append(Check("process", True, "process_pid", {"pid": os.getpid()}))
    return checks
