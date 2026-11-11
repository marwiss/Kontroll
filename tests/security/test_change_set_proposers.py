# This file was generated with the assistance of an AI coding tool.
"""Who proposes a change set (F35 a, ADR 0028): an editor or a manager of the project, through BCF API 3.0 and 2.1
alike, and a contributor is told why not before a byte is kept; snippets of other types are uploaded as before. No
database: the topic and the store of its links are stand-ins, and the route decides. The same way with a database is
in ``tests/integration/test_ifc_changes.py``."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from opencde.accounts.roles import Role
from opencde.bcf.access import ProjectContext
from opencde.bcf.schemas import BimSnippet, TopicGET
from opencde.bcf.topic_access import TopicContext, topic_context
from opencde.documents.changes import SNIPPET_TYPE
from opencde.store.accounts.projects import Project
from opencde.store.bcf.topic_links import link_repository
from opencde.store.oauth2.tokens import Principal
from tests.unit.test_ifc_changes import change_set

pytestmark = pytest.mark.security

PROJECT = "11111111-2222-4333-8444-555555555555"
TOPIC = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
NOW = "2026-11-12T08:00:00Z"
CHANGE_SET = json.dumps(change_set()).encode("utf-8")


class Links:
    """Keeps what the route stores, where ``TopicLinkRepository.set_snippet`` would write it to the graph."""

    def __init__(self) -> None:
        self.stored: list[dict[str, Any]] = []

    async def set_snippet(self, **fields: Any) -> None:
        self.stored.append(fields)


def topic(role: Role, snippet_type: str) -> TopicContext:
    """A topic of the caller's own, so that only the role and the snippet's type decide."""
    principal = Principal("u-1", "anna", "Anna", False, "client-1", ("bcf",), "hash")
    project = ProjectContext(project=Project(PROJECT, "Building permit", NOW), principal=principal, role=role)
    snippet = BimSnippet(snippet_type=snippet_type, is_external=False, reference="changes.json", reference_schema="x")
    return TopicContext(
        project=project,
        topic=TopicGET(
            guid=TOPIC,
            server_assigned_id="ISSUE-0001",
            title="Rename the wall",
            creation_date=NOW,
            creation_author="anna",
            bim_snippet=snippet,
        ),
    )


@pytest.fixture
def links(client: TestClient) -> Iterator[Links]:
    stand_in = Links()
    client.app.dependency_overrides[link_repository] = lambda: stand_in  # type: ignore[attr-defined]
    yield stand_in
    client.app.dependency_overrides.clear()  # type: ignore[attr-defined]


def put(client: TestClient, version: str, role: Role, snippet_type: str, body: bytes) -> Any:
    client.app.dependency_overrides[topic_context] = lambda: topic(role, snippet_type)  # type: ignore[attr-defined]
    return client.put(f"/bcf/{version}/projects/{PROJECT}/topics/{TOPIC}/snippet", content=body)


@pytest.mark.parametrize("version", ["3.0", "2.1"])
@pytest.mark.parametrize("role", [Role.CONTRIBUTOR, Role.VIEWER])
def test_below_an_editor_nobody_proposes_a_change_set(
    client: TestClient, links: Links, version: str, role: Role
) -> None:
    refused = put(client, version, role, SNIPPET_TYPE, CHANGE_SET)
    assert refused.status_code == 403 and refused.json()["code"] == "forbidden", refused.text
    if role is Role.CONTRIBUTOR:
        assert refused.json()["message"] == (
            "Your role 'contributor' does not allow proposing a change set here; that takes the role editor or manager"
        ), "it says why"
    storage = client.app.state.storage  # type: ignore[attr-defined]
    assert not links.stored and not storage.exists(f"snippets/{TOPIC}.bin"), "nothing was kept"


@pytest.mark.parametrize("version", ["3.0", "2.1"])
@pytest.mark.parametrize("role", [Role.EDITOR, Role.MANAGER])
def test_an_editor_or_a_manager_proposes_one(client: TestClient, links: Links, version: str, role: Role) -> None:
    stored = put(client, version, role, SNIPPET_TYPE, CHANGE_SET)
    assert stored.status_code == 200, stored.text
    assert [entry["author"] for entry in links.stored] == ["anna"]


def test_a_contributor_still_uploads_a_snippet_of_another_type(client: TestClient, links: Links) -> None:
    stored = put(client, "3.0", Role.CONTRIBUTOR, ".ifc", b"ISO-10303-21;")
    assert stored.status_code == 200, stored.text
    assert [entry["size"] for entry in links.stored] == [len(b"ISO-10303-21;")]
