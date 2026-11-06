# This file was generated with the assistance of an AI coding tool.
"""Contract fuzzing of the OpenAPI document with Schemathesis, against the real server.

Every documented operation is called over HTTP with generated inputs as an
editor of the test project (bearer token). The checks: no 5xx ever, responses
match the documented response schemas, and malformed input is rejected with a
4xx (Foundation API 1.5), and an operation that declares a token refuses to
answer without one. ``OPENCDE_SCHEMATHESIS_EXAMPLES`` raises the number of
generated examples per operation for the nightly long run, which also runs the
phases that only the command line has.

The server runs in a thread with its own event loop (the ``live_server``
fixture), so Schemathesis talks plain HTTP to it; calling the ASGI app
directly would cross event loops with the database driver.
"""

from __future__ import annotations

import os
import shutil
import subprocess

import pytest
import schemathesis
from hypothesis import HealthCheck
from hypothesis import settings as hypothesis_settings
from schemathesis import GenerationMode
from schemathesis.checks import negative_data_rejection, not_a_server_error, response_schema_conformance
from schemathesis.specs.openapi.checks import ignored_auth

from opencde_client import OpenCdeClient
from opencde_client.testing import headless_authorize
from tests.ui.conftest import LiveServer

pytestmark = [pytest.mark.e2e, pytest.mark.security, pytest.mark.slow]

EXAMPLES = int(os.environ.get("OPENCDE_SCHEMATHESIS_EXAMPLES", "5"))


@pytest.fixture
def bearer(live_server: LiveServer) -> dict[str, str]:
    world = live_server.world
    with OpenCdeClient(live_server.url, client_id=world.public_client_id) as cde:
        tokens = headless_authorize(cde.oauth, username="editor", password=world.password, redirect_uri=world.redirect)
    return {"Authorization": f"Bearer {tokens.access_token}"}


@pytest.fixture
def api_schema(live_server: LiveServer):
    schema = schemathesis.openapi.from_url(f"{live_server.url}/openapi.json")
    schema.config.generation.update(modes=[GenerationMode.POSITIVE, GenerationMode.NEGATIVE], max_examples=EXAMPLES)
    return schema


schema = schemathesis.pytest.from_fixture("api_schema")


@schema.parametrize()
@hypothesis_settings(max_examples=EXAMPLES, deadline=None, suppress_health_check=list(HealthCheck))
def test_operations_never_fail_and_reject_bad_input(case, bearer: dict[str, str]) -> None:
    case.call_and_validate(
        headers=bearer,
        checks=[not_a_server_error, response_schema_conformance, negative_data_rejection, ignored_auth],
    )


@pytest.mark.skipif("OPENCDE_SCHEMATHESIS_EXAMPLES" not in os.environ, reason="the long run belongs to the nightly job")
def test_the_coverage_and_stateful_phases(live_server: LiveServer, bearer: dict[str, str]) -> None:
    """The phases only the command line runs: methods the document leaves out, and calls chained by their answers."""
    result = subprocess.run(  # noqa: S603  # the program is ours, the arguments are this test's
        [
            shutil.which("schemathesis") or "schemathesis",
            "run",
            f"{live_server.url}/openapi.json",
            "--header",
            f"Authorization: {bearer['Authorization']}",
            "--phases",
            "coverage,stateful",
            "--checks",
            "not_a_server_error,unsupported_method,ignored_auth,use_after_free,ensure_resource_availability",
            "--max-examples",
            str(EXAMPLES),
            "--no-color",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=1800,
    )
    assert result.returncode == 0, result.stdout[-6000:]
