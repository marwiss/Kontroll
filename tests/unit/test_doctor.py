# This file was generated with the assistance of an AI coding tool.
"""`opencde doctor`: the clock (SNTP parsing, no network needed), the headers, and the command itself."""

import struct
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from opencde.admin.doctor import (
    NTP_EPOCH_OFFSET,
    clock_check,
    headers_check,
    ntp_offset_from_response,
    ntp_offset_seconds,
)
from opencde.cli import app
from tests.conftest import test_settings as settings_for_tests


def _response(server_unix_time: float) -> bytes:
    seconds = int(server_unix_time)
    fraction = int((server_unix_time - seconds) * 2**32)
    return bytes(40) + struct.pack("!II", seconds + NTP_EPOCH_OFFSET, fraction)


def test_offset_is_measured_against_the_middle_of_the_round_trip() -> None:
    sent, received = 1_000_000.0, 1_000_000.2
    assert ntp_offset_from_response(_response(1_000_000.1), sent, received) == pytest.approx(0.0, abs=1e-6)
    assert ntp_offset_from_response(_response(1_000_003.6), sent, received) == pytest.approx(3.5, abs=1e-6)
    assert ntp_offset_from_response(b"short", sent, received) is None


async def test_unreachable_server_and_no_server_do_not_fail_the_check() -> None:
    assert ntp_offset_seconds("127.0.0.1", timeout=0.2) is None  # nothing listens on UDP 123 here, or it is refused

    nothing = await clock_check("")
    assert nothing.ok and nothing.detail.startswith("not checked")


GOOD_HEADERS = {
    "x-content-type-options": "nosniff",
    "content-security-policy": "default-src 'none'",
    "referrer-policy": "no-referrer",
}


def _answering(headers: dict[str, str]) -> httpx.MockTransport:
    return httpx.MockTransport(lambda _request: httpx.Response(200, headers=headers))


async def test_the_headers_check_names_what_is_missing() -> None:
    settings = settings_for_tests()
    assert (await headers_check(settings, _answering(GOOD_HEADERS))).ok
    partial = await headers_check(settings, _answering({"referrer-policy": "no-referrer"}))
    assert not partial.ok
    assert "x-content-type-options" in partial.detail and "content-security-policy" in partial.detail


async def test_production_also_wants_hsts_from_the_proxy() -> None:
    settings = settings_for_tests(
        environment="production", public_url="https://cde.example.org", graph_password="x" * 20
    )
    assert not (await headers_check(settings, _answering(GOOD_HEADERS))).ok
    with_hsts = {**GOOD_HEADERS, "strict-transport-security": "max-age=31536000"}
    assert (await headers_check(settings, _answering(with_hsts))).ok


async def test_no_server_is_not_a_failure_but_a_bad_certificate_is() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    def bad_certificate(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED] certificate has expired", request=request)

    nobody = await headers_check(settings_for_tests(), httpx.MockTransport(refuse))
    assert nobody.ok and nobody.detail.startswith("not checked")
    assert not (await headers_check(settings_for_tests(), httpx.MockTransport(bad_certificate))).ok


def test_the_command_reports_every_check_and_fails_without_a_database(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    for name, value in {
        "ENVIRONMENT": "development",
        "PUBLIC_URL": "http://127.0.0.1:9",
        "GRAPH_URI": "bolt://127.0.0.1:9",
        "GRAPH_PASSWORD": "not-the-password-of-anything",
        "GRAPH_CONNECT_TIMEOUT_SECONDS": "1",
        "NTP_SERVER": "",
        "DATA_DIR": str(tmp_path),
    }.items():
        monkeypatch.setenv(f"OPENCDE_{name}", value)
    result = CliRunner().invoke(app, ["doctor"])
    assert result.exit_code == 1, result.output
    for line in (
        "OK      Public URL",
        "FAIL    Graph database",
        "FAIL    Schema",
        "OK      Storage",
        "OK      CORS",
        "OK      Security headers: not checked",
        "OK      Clock against NTP: not checked",
    ):
        assert line in result.output, result.output
