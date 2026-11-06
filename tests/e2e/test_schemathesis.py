# This file was generated with the assistance of an AI coding tool.
"""Contract fuzzing of the OpenAPI document with Schemathesis, against the real server.

Every documented operation is called over HTTP with generated inputs as an
editor of the test project (bearer token). The checks: no 5xx ever, responses
match the documented response schemas, and malformed input is rejected with a
4xx (Foundation API 1.5), and an operation that declares a token refuses to
answer without one. ``OPENCDE_SCHEMATHESIS_EXAMPLES`` raises the number of
generated examples per operation for the nightly long run, which also runs the
phases that only the command line has.

The requests use ids of things that exist, in a project the editor is a member of. With made-up ids nearly every
request would get a 404 before it reached the code behind it. An operation that deletes gets things of its own
each time, so that the others have something left to work on.

The server runs in a thread with its own event loop (the ``live_server``
fixture), so Schemathesis talks plain HTTP to it; calling the ASGI app
directly would cross event loops with the database driver.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest
import schemathesis
from hypothesis import HealthCheck
from hypothesis import settings as hypothesis_settings
from schemathesis import GenerationMode
from schemathesis.checks import negative_data_rejection, not_a_server_error, response_schema_conformance
from schemathesis.core.parameters import ParameterLocation
from schemathesis.specs.openapi.checks import ignored_auth

from opencde_client import OpenCdeClient
from opencde_client.testing import headless_authorize
from tests.ui.conftest import LiveServer

pytestmark = [pytest.mark.e2e, pytest.mark.security, pytest.mark.slow]

EXAMPLES = int(os.environ.get("OPENCDE_SCHEMATHESIS_EXAMPLES", "5"))
VIEWPOINT = {
    "perspective_camera": {
        "camera_view_point": {"x": 1.0, "y": 2.0, "z": 3.0},
        "camera_direction": {"x": 0.0, "y": 1.0, "z": 0.0},
        "camera_up_vector": {"x": 0.0, "y": 0.0, "z": 1.0},
        "field_of_view": 60.0,
        "aspect_ratio": 1.5,
    }
}


@pytest.fixture
def cde(live_server: LiveServer) -> Iterator[OpenCdeClient]:
    world = live_server.world
    with OpenCdeClient(live_server.url, client_id=world.public_client_id) as client:
        client.use_tokens(
            headless_authorize(client.oauth, username="editor", password=world.password, redirect_uri=world.redirect)
        )
        yield client


@pytest.fixture
def bearer(cde: OpenCdeClient) -> dict[str, str]:
    return {"Authorization": f"Bearer {cde.tokens.access_token}"}


def _things(cde: OpenCdeClient, project_id: str) -> dict[str, str]:
    """A topic with a comment and a viewpoint."""
    topic = cde.bcf.create_topic(project_id, {"title": "For the generated requests"})["guid"]
    comment = cde.bcf.create_comment(project_id, topic, {"comment": "A comment"})["guid"]
    viewpoint = cde.bcf.create_viewpoint(project_id, topic, VIEWPOINT)["guid"]
    return {"topic_id": topic, "comment_id": comment, "viewpoint_id": viewpoint}


@pytest.fixture
def api_schema(live_server: LiveServer, cde: OpenCdeClient):
    schema = schemathesis.openapi.from_url(f"{live_server.url}/openapi.json")
    project_id = live_server.world.project_id
    real = {"project_id": project_id, **_things(cde, project_id)}
    schema.config.update(parameters={f"path.{name}": value for name, value in real.items()})
    # The test brings its own token, so a generated case must not count on leaving it out: the check below would
    # take the answer to a request with the token for an answer to one without. ``ignored_auth`` asks without one.
    schema.config.generation.update(
        modes=[GenerationMode.POSITIVE, GenerationMode.NEGATIVE], max_examples=EXAMPLES, with_security_parameters=False
    )
    return schema


schema = schemathesis.pytest.from_fixture("api_schema")


@schema.parametrize()
@hypothesis_settings(max_examples=EXAMPLES, deadline=None, suppress_health_check=list(HealthCheck))
def test_operations_never_fail_and_reject_bad_input(
    case, bearer: dict[str, str], cde: OpenCdeClient, live_server: LiveServer
) -> None:
    if case.method == "DELETE" and "topic_id" in case.path_parameters:
        case.path_parameters.update(_things(cde, live_server.world.project_id))
    # The generator may believe it has spoilt a path parameter, but the test fills those in, so what goes out is valid.
    negated = {location for location, part in case.meta.components.items() if part.mode.is_negative}
    only_our_ids = negated <= {ParameterLocation.PATH}
    checks = [not_a_server_error, response_schema_conformance, ignored_auth]
    case.call_and_validate(headers=bearer, checks=checks if only_our_ids else [*checks, negative_data_rejection])


@pytest.mark.skipif("OPENCDE_SCHEMATHESIS_EXAMPLES" not in os.environ, reason="the long run belongs to the nightly job")
def test_the_coverage_and_stateful_phases(
    live_server: LiveServer, bearer: dict[str, str], cde: OpenCdeClient, tmp_path: Path
) -> None:
    """The phases only the command line runs: methods the document leaves out, and calls chained by their answers."""
    project_id = live_server.world.project_id
    real = {"project_id": project_id, **_things(cde, project_id)}
    config = tmp_path / "schemathesis.toml"
    lines = "".join(f'"path.{name}" = "{value}"\n' for name, value in real.items())
    config.write_text(f"[parameters]\n{lines}", encoding="utf-8")
    result = subprocess.run(  # noqa: S603  # the program is ours, the arguments are this test's
        [
            shutil.which("schemathesis") or "schemathesis",
            "--config-file",
            str(config),
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
        env={**os.environ, "PYTHONUTF8": "1"},
    )
    print(result.stdout[-4000:].encode("ascii", "replace").decode())  # what the phases covered, shown with -s
    assert result.returncode == 0, result.stdout[-8000:]
