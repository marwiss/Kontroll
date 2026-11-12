# This file was generated with the assistance of an AI coding tool.
"""A change set as a topic's BIM snippet: the public schema, and the upload held to it (ADR 0021)."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from opencde.documents.changes import OPS_FORM, OPS_TOOLS, SCHEMA_PATH, SNIPPET_TYPE
from opencde.settings import Settings
from tests.integration.conftest_accounts import World, build_world, login_as
from tests.integration.test_bcf_links_documents import make_topic
from tests.unit.test_ifc_changes import change_set

pytestmark = pytest.mark.integration


@pytest.fixture
def world(settings: Settings, clean_database: None) -> World:
    return build_world(settings)


def test_the_schema_is_public_and_the_snippet_is_held_to_it(client: TestClient, world: World) -> None:
    schema = client.get(SCHEMA_PATH)
    assert schema.status_code == 200 and schema.headers["content-type"].startswith("application/schema+json")
    assert schema.json()["$id"] == f"http://testserver{SCHEMA_PATH}" and "public" in schema.headers["cache-control"]
    capabilities = client.get("/.well-known/dataregium").json()["extensions"]["ifc_changes"]
    assert capabilities == {
        "enabled": True,
        "schema": SCHEMA_PATH,
        "snippet_type": SNIPPET_TYPE,
        "max_changes": 10_000,
        "tried": False,
        "proposal_url": "/bcf/3.0/projects/{project_id}/topics/{topic_guid}/ifc-proposal",
        "approve_url": "/bcf/3.0/projects/{project_id}/topics/{topic_guid}/ifc-proposal/approve",
        "ifc_proposals_url": "/documents/1.0/documents/{document_id}/ifc-proposals",
        "ops": ["set", "add", "remove", "delete"],
        "ops_form": OPS_FORM,
        "ops_tools": list(OPS_TOOLS),
        "unreachable_url": None,
    }, "the server proposes no removal without the IFC-LPG module"

    editor = login_as(client, world, "editor")
    viewer = login_as(client, world, "viewer")
    elsewhere = "/documents/1.0/documents/11111111-2222-4333-8444-555555555555/ifc-proposals"
    assert client.get(elsewhere, headers=viewer.headers).status_code == 404, "no trials without the module"
    topics = f"/bcf/3.0/projects/{world.project_id}/topics"
    extensions = client.get(f"/bcf/3.0/projects/{world.project_id}/extensions", headers=viewer.headers).json()
    assert SNIPPET_TYPE in extensions["snippet_type"], "a new project allows the snippet type"
    topic = make_topic(
        client,
        world,
        editor,
        bim_snippet={
            "snippet_type": SNIPPET_TYPE,
            "is_external": False,
            "reference": "changes.json",
            "reference_schema": schema.json()["$id"],
        },
    )
    url = f"{topics}/{topic['guid']}/snippet"
    not_json = client.put(url, content=b"<snippet/>", headers=editor.headers)
    assert not_json.status_code == 400 and "not JSON" in not_json.json()["message"]
    wrong = client.put(url, content=json.dumps({"schema": "x"}).encode(), headers=editor.headers)
    assert wrong.status_code == 400 and "base: Field required" in wrong.json()["message"]
    assert client.get(url, headers=editor.headers).status_code == 404, "nothing was kept"
    good = change_set()
    stored = client.put(url, content=json.dumps(good).encode(), headers=editor.headers)
    assert stored.status_code == 200, stored.text
    assert client.get(url, headers=viewer.headers).json() == good

    # A snippet of another type is stored as it comes.
    other = make_topic(
        client,
        world,
        editor,
        bim_snippet={"snippet_type": ".ifc", "is_external": False, "reference": "m.ifc", "reference_schema": "x"},
    )
    assert (
        client.put(f"{topics}/{other['guid']}/snippet", content=b"ISO-10303-21;", headers=editor.headers).status_code
        == 200
    )
