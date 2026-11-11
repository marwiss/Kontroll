# This file was generated with the assistance of an AI coding tool.
"""A project's AI policy (F29 a, F30 a, ADR 0028): `local` unless someone chose `cloud`, set with parameters only, and
read by every member through the Documents API in the shape the API document gives. Setting it through the project
administration and the administration is proved against a database in ``tests/integration/test_ai_policy.py``."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any

import jsonschema
import pytest
from fastapi.testclient import TestClient

from opencde.accounts.roles import Role
from opencde.auth.dependencies import current_principal
from opencde.deps import get_projects
from opencde.errors import ERROR_SCHEMA
from opencde.store.accounts.projects import AI_POLICIES, DEFAULT_AI_POLICY, Project, ProjectRepository, _project
from opencde.store.accounts.users import AccountError
from opencde.store.oauth2.tokens import Principal

PROJECT = "11111111-2222-4333-8444-555555555555"
OTHER = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
ROW = {"project_id": PROJECT, "name": "Building permit", "created_at": "2026-11-12T08:00:00Z"}


def test_a_project_is_local_unless_someone_chose_cloud() -> None:
    assert AI_POLICIES == ("local", "cloud") and DEFAULT_AI_POLICY == "local"
    assert _project(ROW).ai_policy == "local", "a project from an earlier release, which has none"
    assert _project({**ROW, "ai_policy": "cloud"}).ai_policy == "cloud"
    assert _project({**ROW, "ai_policy": "Cloud"}).ai_policy == "local", "anything else is local"
    assert Project(PROJECT, "Building permit", ROW["created_at"]).ai_policy == "local", "and so is a new project"


class OneRowGraph:
    """Keeps every statement and answers each with the same row."""

    def __init__(self, row: dict[str, Any]) -> None:
        self.row = row
        self.statements: list[tuple[str, dict[str, Any]]] = []

    async def one(self, cypher: str, **params: Any) -> dict[str, Any]:
        self.statements.append((cypher, params))
        return self.row


def test_the_policy_is_set_to_a_known_value_with_parameters_only() -> None:
    graph = OneRowGraph({"project": {**ROW, "ai_policy": "cloud"}})
    repository = ProjectRepository(graph)  # type: ignore[arg-type]
    with pytest.raises(AccountError, match="local or cloud"):
        asyncio.run(repository.set_ai_policy(PROJECT, "anywhere"))
    assert not graph.statements, "an unknown value never reaches the database"
    assert asyncio.run(repository.set_ai_policy(PROJECT, "cloud")).ai_policy == "cloud"
    [(cypher, params)] = graph.statements
    assert "SET p.ai_policy = $value" in cypher and "cloud" not in cypher
    assert params == {"id": PROJECT, "value": "cloud"}


class MemberProjects:
    """Answers ``list_for_user`` as the repository does for a viewer of one project."""

    def __init__(self, policy: str) -> None:
        self.project = Project(PROJECT, "Building permit", ROW["created_at"], ai_policy=policy)  # type: ignore[arg-type]
        self.asked: list[str] = []

    async def list_for_user(self, user_id: str) -> list[tuple[Project, Role]]:
        self.asked.append(user_id)
        return [(self.project, Role.VIEWER)]


def principal(*scopes: str) -> Principal:
    return Principal("u-1", "viewer", "Viewer", False, "client-1", scopes, "hash")


@pytest.fixture
def member(client: TestClient) -> Iterator[MemberProjects]:
    projects = MemberProjects("cloud")
    overrides = client.app.dependency_overrides  # type: ignore[attr-defined]
    overrides[current_principal] = lambda: principal("profile", "bcf", "documents")
    overrides[get_projects] = lambda: projects
    yield projects
    overrides.clear()


def test_every_member_reads_the_policy_in_the_documented_shape(client: TestClient, member: MemberProjects) -> None:
    answer = client.get(f"/documents/1.0/projects/{PROJECT.upper()}/ai-policy")
    assert answer.status_code == 200, answer.text
    assert answer.json() == {"project_id": PROJECT, "ai_policy": "cloud"}
    assert member.asked == ["u-1"], "found from the caller's own user node"
    schema = client.get("/openapi.json").json()["components"]["schemas"]["ProjectAiPolicy"]
    jsonschema.validate(answer.json(), schema)
    assert schema["properties"]["ai_policy"]["enum"] == ["local", "cloud"]

    member.project = Project(PROJECT, "Building permit", ROW["created_at"])
    assert client.get(f"/documents/1.0/projects/{PROJECT}/ai-policy").json()["ai_policy"] == "local"


def test_a_project_the_caller_is_not_in_is_not_there(client: TestClient, member: MemberProjects) -> None:
    for project_id in (OTHER, "not-a-project"):
        refused = client.get(f"/documents/1.0/projects/{project_id}/ai-policy")
        assert refused.status_code == 404, project_id
        jsonschema.validate(refused.json(), ERROR_SCHEMA)
        assert "cloud" not in refused.text, "nothing of a policy leaks"
    assert member.asked == ["u-1"], "an id that is no UUID never reaches the store"
    changed = client.put(f"/documents/1.0/projects/{PROJECT}/ai-policy", json={"ai_policy": "local"})
    assert changed.status_code == 405, "a manager or an administrator sets it, never a member here"


def test_the_policy_answers_to_the_documents_scope(client: TestClient, member: MemberProjects) -> None:
    client.app.dependency_overrides[current_principal] = lambda: principal("profile", "bcf")  # type: ignore[attr-defined]
    refused = client.get(f"/documents/1.0/projects/{PROJECT}/ai-policy")
    assert refused.status_code == 403 and refused.json()["code"] == "insufficient_scope"
    assert not member.asked, "refused before the project is looked up"
