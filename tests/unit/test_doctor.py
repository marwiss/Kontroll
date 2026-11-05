# This file was generated with the assistance of an AI coding tool.
"""The clock check of `opencde doctor`: SNTP parsing and graceful failure without a network."""

import struct

import pytest

from opencde.admin.doctor import NTP_EPOCH_OFFSET, clock_check, ntp_offset_from_response, ntp_offset_seconds


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
