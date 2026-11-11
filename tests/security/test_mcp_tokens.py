# This file was generated with the assistance of an AI coding tool.
"""A token bound to the MCP endpoint reaches no REST operation, and the MCP endpoint takes no other token.

ADR 0028 and F31 a: an AI's token never reaches the approval or the publication of the REST APIs. The token store
stands in for the database, so that every operation of the API document is tried with a token that is valid but bound
(the database's side is in ``tests/integration/test_mcp_tokens.py``).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from opencde.auth.dependencies import get_tokens
from opencde.auth.resources import MCP_PATH
from opencde.auth.scopes import MCP_PROPOSE
from opencde.deps import SettingsDep
from opencde.errors import install_error_handlers
from opencde.main import create_app
from opencde.mcp.auth import McpPrincipal, require_mcp_scope
from opencde.store.oauth2.tokens import Principal
from tests.conftest import test_settings as make_settings
from tests.security.test_every_operation import AN_ID, PUBLIC, _filled, _operations

pytestmark = pytest.mark.security

MCP = "http://testserver/mcp"
METADATA = "http://testserver/.well-known/oauth-protected-resource/mcp"
BEARER = {"Authorization": "Bearer a-token-the-store-knows"}
REST_SCOPES = ("profile", "bcf", "documents", "project", "admin")
REFUSAL = "This access token is for the MCP endpoint, not for this API"


def principal(resource: str | None, scopes: tuple[str, ...] = ("mcp", "mcp:propose")) -> Principal:
    """An administrator who signed in a moment ago, so that nothing but the binding can be a reason to refuse."""
    return Principal(
        user_id="u1",
        username="anna",
        display_name="Anna",
        is_admin=True,
        client_id="ai-client",
        scopes=scopes,
        token_hash="hash",
        auth_time="2999-01-01T00:00:00Z",
        resource=resource,
    )


class OneToken:
    """A token store that knows one token, whatever is presented."""

    def __init__(self, found: Principal | None) -> None:
        self.found = found

    async def principal(self, access_token: str) -> Principal | None:
        return self.found


@contextmanager
def server(tmp_path: Path, found: Principal | None) -> Iterator[TestClient]:
    """The application with every optional part of the API on, so that the sweep reaches all of it."""
    settings = make_settings(
        tmp_path, mcp_enabled=True, graph_query_enabled=True, request_log_enabled=True, dynamic_client_registration=True
    )
    app = create_app(settings, startup_wait_seconds=0)
    app.dependency_overrides[get_tokens] = lambda: OneToken(found)
    with TestClient(app) as client:
        yield client


def test_every_rest_operation_refuses_a_token_bound_to_the_mcp_endpoint(tmp_path: Path) -> None:
    with server(tmp_path, principal(MCP, ("mcp", "mcp:propose"))) as client:
        protected = [
            (method, path)
            for method, path, operation in _operations(client)
            if operation.get("security") and path.split("/")[1] != MCP_PATH.strip("/")  # the one place it is for
        ]
        assert len(protected) > 50, "the list is not empty by accident"
        for method, path in protected:
            response = client.request(method, _filled(path), headers=BEARER)
            assert response.status_code == 401, f"{method} {path}: {response.status_code}"
            assert response.json() == {"message": REFUSAL, "code": "invalid_token"}, f"{method} {path}"
            assert response.headers["www-authenticate"] == 'Bearer realm="opencde", error="invalid_token"', path
        # By name too, since they are what the binding is for: the approval and the publication.
        assert ("POST", "/bcf/3.0/projects/{project_id}/topics/{topic_id}/ifc-proposal/approve") in protected
        assert ("POST", "/documents/1.0/documents/{document_id}/versions/{version_index}/publication") in protected


def test_a_bound_token_with_every_rest_scope_is_refused_as_well(tmp_path: Path) -> None:
    """The binding decides, not the scopes: a bound token never reaches REST, whatever it holds."""
    with server(tmp_path, principal(MCP, REST_SCOPES)) as client:
        for method, path in (
            ("GET", "/foundation/1.0/current-user"),
            ("GET", "/bcf/3.0/projects"),
            ("POST", f"/bcf/3.0/projects/{AN_ID}/topics/{AN_ID}/ifc-proposal/approve"),
            ("POST", f"/documents/1.0/documents/{AN_ID}/versions/1/publication"),
            ("GET", "/admin/api/users"),
        ):
            response = client.request(method, path, headers=BEARER)
            assert response.status_code == 401 and response.json()["code"] == "invalid_token", path


def test_the_same_token_unbound_is_taken_so_the_binding_is_the_reason(tmp_path: Path) -> None:
    with server(tmp_path, principal(None, REST_SCOPES)) as client:
        answer = client.get("/foundation/1.0/current-user", headers=BEARER)
        assert answer.status_code == 200 and answer.json() == {"id": "anna", "name": "Anna"}
    with server(tmp_path, principal(MCP)) as client:
        refused = client.get("/foundation/1.0/current-user", headers=BEARER)
        assert refused.status_code == 401 and refused.json()["message"] == REFUSAL
    with server(tmp_path, principal("http://old.example/mcp", REST_SCOPES)) as client:
        assert client.get("/bcf/3.0/projects", headers=BEARER).status_code == 401, "bound to an earlier address"


def test_with_the_mcp_endpoint_on_its_metadata_is_the_one_public_operation_more(tmp_path: Path) -> None:
    with server(tmp_path, None) as client:
        public = {(method, path) for method, path, operation in _operations(client) if not operation.get("security")}
        assert public == PUBLIC | {("GET", "/.well-known/oauth-protected-resource/mcp")}


# -- mcp_principal: what the MCP endpoint will stand on ------------------------------------------------------------


@contextmanager
def endpoint(tmp_path: Path, found: Principal | None) -> Iterator[TestClient]:
    """Two routes as the endpoint will have them: one that reads and one that proposes."""
    probe = FastAPI()
    install_error_handlers(probe)
    probe.state.settings = make_settings(tmp_path, mcp_enabled=True)
    probe.dependency_overrides[get_tokens] = lambda: OneToken(found)

    @probe.post("/mcp")
    async def read(caller: McpPrincipal) -> dict[str, str]:
        return {"user": caller.username}

    @probe.post("/mcp/propose")
    async def propose(caller: McpPrincipal, settings: SettingsDep) -> dict[str, str]:
        require_mcp_scope(caller, MCP_PROPOSE, settings)
        return {"user": caller.username}

    with TestClient(probe) as client:
        yield client


def test_without_a_token_the_mcp_endpoint_names_its_metadata_and_scope(tmp_path: Path) -> None:
    with endpoint(tmp_path, principal(MCP)) as client:
        response = client.post("/mcp")
    assert response.status_code == 401 and response.json()["code"] == "unauthenticated"
    assert response.headers["www-authenticate"] == f'Bearer resource_metadata="{METADATA}", scope="mcp"'


@pytest.mark.parametrize(
    "found",
    [
        None,  # unknown, expired or revoked
        principal(None, ("profile", "bcf", "documents")),  # a REST token, such as Dataspatium's
        principal(None, ("mcp", "mcp:propose")),  # MCP scopes without the binding
        principal("http://old.example/mcp"),  # bound to another address
    ],
    ids=["unknown", "rest", "unbound", "elsewhere"],
)
def test_the_mcp_endpoint_takes_no_token_but_one_bound_to_it(tmp_path: Path, found: Principal | None) -> None:
    with endpoint(tmp_path, found) as client:
        response = client.post("/mcp", headers=BEARER)
    assert response.status_code == 401 and response.json()["code"] == "invalid_token"
    expected = f'Bearer error="invalid_token", resource_metadata="{METADATA}", scope="mcp"'
    assert response.headers["www-authenticate"] == expected


def test_reading_needs_mcp_and_proposing_mcp_propose_with_a_step_up(tmp_path: Path) -> None:
    with endpoint(tmp_path, principal(MCP, ("mcp",))) as reader:
        assert reader.post("/mcp", headers=BEARER).json() == {"user": "anna"}
        refused = reader.post("/mcp/propose", headers=BEARER)
    assert refused.status_code == 403 and refused.json()["code"] == "insufficient_scope"
    expected = f'Bearer error="insufficient_scope", resource_metadata="{METADATA}", scope="mcp mcp:propose"'
    assert refused.headers["www-authenticate"] == expected
    with endpoint(tmp_path, principal(MCP, ("mcp", "mcp:propose"))) as proposer:
        assert proposer.post("/mcp/propose", headers=BEARER).json() == {"user": "anna"}
    with endpoint(tmp_path, principal(MCP, ("mcp:propose",))) as without_read:
        answer = without_read.post("/mcp", headers=BEARER)
    assert answer.status_code == 403
    assert (
        answer.headers["www-authenticate"]
        == f'Bearer error="insufficient_scope", resource_metadata="{METADATA}", scope="mcp"'
    )
