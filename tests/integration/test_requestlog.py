# This file was generated with the assistance of an AI coding tool.
"""The request log: entries without bodies or tokens, the administration page, and the bearer JSON endpoint."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from opencde.main import create_app
from tests.conftest import test_settings as make_settings
from tests.integration.conftest import GraphTarget
from tests.integration.conftest_accounts import World, build_world, login_as
from tests.integration.helpers import Session, authorize, exchange
from tests.integration.test_web_signin import web_sign_in

pytestmark = [pytest.mark.integration, pytest.mark.security]


@pytest.fixture
def logged(graph_target: GraphTarget, clean_database: None, tmp_path) -> Iterator[tuple[TestClient, World]]:
    settings = make_settings(
        tmp_path,
        graph_dialect=graph_target.dialect,
        graph_uri=graph_target.uri,
        graph_user=graph_target.user,
        graph_password=graph_target.password,
        graph_connect_timeout_seconds=10.0,
        request_log_enabled=True,
    )
    world = build_world(settings)
    with TestClient(create_app(settings, startup_wait_seconds=30)) as client:
        yield client, world


def sign_in_with_scope(client: TestClient, world: World, username: str, scope: str) -> Session:
    code, _query, verifier = authorize(
        client,
        client_id=world.public_client_id,
        redirect_uri=world.redirect,
        username=username,
        password=world.password,
        scope=scope,
    )
    assert code is not None
    return exchange(client, code=code, verifier=verifier, client_id=world.public_client_id, redirect_uri=world.redirect)


def test_requests_are_logged_without_bodies_and_served_to_administrators(logged: tuple[TestClient, World]) -> None:
    client, world = logged
    editor = login_as(client, world, "editor")
    client.get("/foundation/1.0/current-user", headers={**editor.headers, "X-Request-ID": "trace-abc"})
    created = client.post(
        f"/bcf/3.0/projects/{world.project_id}/topics",
        json={"title": "Logged topic", "description": "DO-NOT-STORE-THIS-BODY"},
        headers=editor.headers,
    )
    assert created.status_code == 201, created.text
    assert client.get("/bcf/3.0/projects").status_code == 401  # anonymous
    client.portal.call(client.app.state.requestlog.wait_idle)  # type: ignore[attr-defined]

    # The page, for a signed-in administrator.
    web_sign_in(client, world, "admin")
    page = client.get("/admin/requests", params={"request_id": "trace-abc"})
    assert page.status_code == 200
    assert "trace-abc" in page.text and "/foundation/1.0/current-user" in page.text and ">editor<" in page.text

    # The JSON endpoint, for a bearer token with the admin scope held by an administrator.
    admin_api = sign_in_with_scope(client, world, "admin", "profile admin")
    response = client.get(
        "/admin/api/requests", params={"user": "editor", "path": "/bcf/3.0"}, headers=admin_api.headers
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["enabled"] is True and body["retention_hours"] == 72
    entries = body["requests"]
    assert entries and all(entry["username"] == "editor" for entry in entries)
    topic_post = next(entry for entry in entries if entry["method"] == "POST")
    assert topic_post["status"] == 201 and topic_post["client_id"] == world.public_client_id
    assert topic_post["bytes_in"] > 0 and topic_post["bytes_out"] > 0 and topic_post["duration_ms"] >= 0
    assert topic_post["path"] == f"/bcf/3.0/projects/{world.project_id}/topics" and "Topic" in topic_post["operation"]
    assert topic_post["request_id"] and topic_post["at"].endswith("Z")
    assert "DO-NOT-STORE-THIS-BODY" not in response.text and editor.access_token not in response.text

    # The token endpoint authenticates the client by form, not bearer, yet its rows name the client.
    token_rows = client.get(
        "/admin/api/requests", params={"path": "/foundation/oauth2/token"}, headers=admin_api.headers
    ).json()["requests"]
    assert token_rows and all(
        row["client_id"] == world.public_client_id and row["username"] is None for row in token_rows
    )
    assert editor.refresh_token not in response.text and all(row["status"] == 201 for row in token_rows)

    anonymous = client.get("/admin/api/requests", params={"status": 401}, headers=admin_api.headers).json()["requests"]
    assert anonymous and all(entry["username"] is None and entry["client_id"] is None for entry in anonymous)

    # Authorization: scope and role, both; CORS applies to the administration API.
    assert client.get("/admin/api/requests", headers=editor.headers).status_code == 403, "no admin scope"
    assert client.get("/admin/api/requests", headers=login_as(client, world, "admin").headers).status_code == 403
    assert (
        client.get(
            "/admin/api/requests", headers=sign_in_with_scope(client, world, "editor", "admin").headers
        ).status_code
        == 403
    )
    assert client.get("/admin/api/requests").status_code == 401
    preflight = client.options(
        "/admin/api/requests",
        headers={
            "Origin": "https://viewer.example",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert preflight.status_code == 200 and preflight.headers.get("access-control-allow-origin") == "*"
