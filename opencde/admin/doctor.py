# This file was generated with the assistance of an AI coding tool.
"""Health checks shown on the settings page (and usable by ``opencde doctor``)."""

from __future__ import annotations

import asyncio
import os
import socket
import struct
import time
from dataclasses import dataclass

from opencde import __version__
from opencde.graph.driver import ping_within
from opencde.graph.graph import Graph
from opencde.settings import Settings
from opencde.storage import LocalStorage
from opencde.timeutil import now_iso

NTP_EPOCH_OFFSET = 2_208_988_800  # seconds from 1900-01-01 (NTP epoch) to 1970-01-01 (Unix epoch)
NTP_PORT = 123
MAX_CLOCK_OFFSET_SECONDS = 5.0  # codes live 60 s and tokens carry expiry times: the clock must be roughly right


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str


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
        return Check("Clock against NTP", True, f"not checked (no NTP server configured); now {now_iso()}")
    offset = await asyncio.to_thread(ntp_offset_seconds, server)
    if offset is None:
        return Check(
            "Clock against NTP", True, f"not checked ({server} did not answer on UDP {NTP_PORT}); now {now_iso()}"
        )
    return Check(
        "Clock against NTP",
        abs(offset) <= MAX_CLOCK_OFFSET_SECONDS,
        f"offset {offset:+.2f} s against {server}; now {now_iso()}",
    )


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
    checks.append(await clock_check(settings.ntp_server))
    checks.append(Check("Process", True, f"pid {os.getpid()}"))
    return checks
