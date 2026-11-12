# This file was generated with the assistance of an AI coding tool.
"""The guards of the MCP endpoint's change sets (ADR 0028, F35 a): only an editor or a manager proposes, at every
call; a token without ``mcp:propose`` gets the step-up for every change-set tool and reads with ``mcp`` alone; an
outsider finds no document and no draft; the AI policy holds at every call; and the audit log keeps identifiers and
counts, never an argument or a text. The database is stood in for (``tests/mcp_drafts_support.py``).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from opencde.mcp import change_sets
from tests.mcp_drafts_support import TOPIC, DraftGraph, FakeProposing, FakeTopics, FakeTrials, trial
from tests.mcp_support import CLOUD, DOCUMENT, call, endpoint, principal, rpc
from tests.security.test_prompt_injection import INJECTIONS

pytestmark = pytest.mark.security

PROPOSER = principal(scopes=("mcp", "mcp:propose"))
READER = principal(scopes=("mcp",))
METADATA = "http://testserver/.well-known/oauth-protected-resource/mcp"
WALL = {"storey": None, "start": [0, 0], "end": [4, 0], "thickness": None, "height": None, "name": None,
        "type": None, "partition": None, "load_bearing": None, "status": None}  # fmt: skip
ROLE = "does not propose change sets; that takes the role editor or manager"


def _result(answer: Any) -> dict[str, Any]:
    assert answer.status_code == 200, answer.text
    return answer.json()["result"]


def _open(client: Any) -> dict[str, Any]:
    return _result(call(client, "open_changeset", {"document_id": DOCUMENT, "version_index": None}))


def _denials(graph: DraftGraph) -> list[dict[str, Any]]:
    return [event["details"] for event in graph.events() if event["type"] == "mcp.denied"]


@pytest.mark.parametrize("role", ["viewer", "contributor"])
def test_a_viewer_and_a_contributor_propose_no_change_set(tmp_path: Path, role: str) -> None:
    graph = DraftGraph(role)
    with endpoint(tmp_path, graph, PROPOSER, ifcgraph_enabled=True) as client:
        refused = _open(client)
    assert refused["isError"] is True and refused["content"][0]["text"] == f"Your role in this project, {role}, {ROLE}"
    assert not graph.drafts
    (denial,) = _denials(graph)
    assert denial["reason"] == "role" and denial["project_id"] == CLOUD and denial["tool"] == "open_changeset"


def test_the_role_is_checked_at_every_call_as_rest_checks_it(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(change_sets, "Proposing", FakeProposing)
    monkeypatch.setattr(change_sets, "TopicRepository", FakeTopics)
    FakeProposing.made = []
    graph = DraftGraph("editor")
    with endpoint(tmp_path, graph, PROPOSER, ifcgraph_enabled=True) as client:
        handle = _open(client)["structuredContent"]["changeset_id"]
        assert _result(call(client, "create_wall", {"changeset_id": handle, **WALL}))["isError"] is False
        graph.set_role("contributor")  # a manager made the editor a contributor
        asked = {
            "create_wall": {"changeset_id": handle, **WALL},
            "manage_changeset": {"changeset_id": handle, "action": "list"},
            "propose_changes": {"changeset_id": handle, "title": "A wall", "description": None, "ai_model": None},
        }
        answers = {name: _result(call(client, name, arguments)) for name, arguments in asked.items()}
    for name, answer in answers.items():
        assert answer["isError"] is True and ROLE in answer["content"][0]["text"], name
    assert [denial["tool"] for denial in _denials(graph)] == list(asked)
    assert not FakeProposing.made and json.loads(graph.drafts[handle]["steps"])[0]["tool"] == "create_wall"


@pytest.mark.parametrize("name", [tool.name for tool in change_sets.CHANGE_SET_TOOLS])
def test_a_token_without_mcp_propose_gets_the_step_up_for_every_change_set_tool(tmp_path: Path, name: str) -> None:
    graph = DraftGraph()
    with endpoint(tmp_path, graph, READER, ifcgraph_enabled=True) as client:
        answer = call(client, name, {"changeset_id": "x"})
    assert answer.status_code == 403 and answer.json()["code"] == "insufficient_scope"
    assert answer.headers["www-authenticate"] == (
        f'Bearer error="insufficient_scope", resource_metadata="{METADATA}", scope="mcp mcp:propose"'
    )
    (denial,) = _denials(graph)
    assert denial == {
        "reason": "scope",
        "scope": "mcp:propose",
        "tool": name,
        "client_info": {"name": "test-client", "version": "1.0"},
    }
    assert not graph.drafts and not graph.draft_queries(), "refused before any draft is touched"


def test_a_reader_reads_the_trials_and_the_proposals_with_mcp_alone(tmp_path: Path) -> None:
    with endpoint(tmp_path, DraftGraph("viewer"), READER, ifcgraph_enabled=True) as client:
        client.app.state.ifcgraph = FakeTrials(trial("clean"))  # ty: ignore[unresolved-attribute]
        got = _result(call(client, "get_proposal", {"project_id": CLOUD, "topic_guid": TOPIC, "wait_seconds": None}))
        listed = _result(call(client, "list_proposals", {"document_id": DOCUMENT, "limit": None}))
    assert got["isError"] is False and got["structuredContent"]["state"] == "clean"
    assert listed["isError"] is False and listed["structuredContent"] == {"proposals": [], "truncated": False}


def test_an_outsider_finds_no_document_no_draft_and_no_trial(tmp_path: Path) -> None:
    owner = DraftGraph()
    with endpoint(tmp_path, owner, PROPOSER, ifcgraph_enabled=True) as client:
        handle = _open(client)["structuredContent"]["changeset_id"]
    outsider = DraftGraph()
    outsider.memberships = []
    outsider.drafts = owner.drafts
    with endpoint(tmp_path, outsider, PROPOSER, ifcgraph_enabled=True) as client:
        client.app.state.ifcgraph = FakeTrials(trial("clean"))  # ty: ignore[unresolved-attribute]
        opened = _open(client)
        step = _result(call(client, "create_wall", {"changeset_id": handle, **WALL}))
        got = _result(call(client, "get_proposal", {"project_id": CLOUD, "topic_guid": TOPIC, "wait_seconds": None}))
    assert opened["content"][0]["text"] == change_sets.NO_DOCUMENT
    assert step["content"][0]["text"] == change_sets.UNKNOWN, "a handle is a name, not a permission"
    assert got["content"][0]["text"] == "There is no project with this id among your projects"
    assert json.loads(owner.drafts[handle]["steps"]) == [] and not _denials(outsider)


def test_a_local_project_is_refused_on_a_team_server_at_every_call(tmp_path: Path) -> None:
    graph = DraftGraph()
    with endpoint(tmp_path, graph, PROPOSER, ifcgraph_enabled=True) as client:
        handle = _open(client)["structuredContent"]["changeset_id"]
        graph.memberships = [({**found, "ai_policy": "local"}, role) for found, role in graph.memberships]
        step = _result(call(client, "create_wall", {"changeset_id": handle, **WALL}))
        opened = _open(client)
    for answer in (step, opened):
        assert answer["isError"] is True and "local only" in answer["content"][0]["text"]
    assert [(denial["reason"], denial["tool"]) for denial in _denials(graph)] == [
        ("policy", "create_wall"),
        ("policy", "open_changeset"),
    ]
    assert len(graph.drafts) == 1 and json.loads(graph.drafts[handle]["steps"]) == []


@pytest.mark.parametrize("text", INJECTIONS)
def test_texts_in_the_steps_and_the_proposal_never_reach_the_audit_log_or_the_tools(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, text: str
) -> None:
    monkeypatch.setattr(change_sets, "Proposing", FakeProposing)
    monkeypatch.setattr(change_sets, "TopicRepository", FakeTopics)
    FakeProposing.made = []
    graph = DraftGraph()
    with endpoint(tmp_path, graph, PROPOSER, ifcgraph_enabled=True) as client:
        listed_before = rpc(client, "tools/list").json()["result"]["tools"]
        handle = _open(client)["structuredContent"]["changeset_id"]
        wall = _result(call(client, "create_wall", {"changeset_id": handle, **WALL, "name": text[:200]}))
        asked = {"changeset_id": handle, "title": text[:200], "description": text, "ai_model": "claude-test"}
        proposed = _result(call(client, "propose_changes", asked))
        listed_after = rpc(client, "tools/list").json()["result"]["tools"]
    assert wall["isError"] is False and proposed["isError"] is False
    assert listed_before == listed_after, "the tools are the same whatever the steps hold"
    assert text[:40] not in json.dumps([event["details"] for event in graph.events()]), "identifiers and counts only"
    (made,) = FakeProposing.made
    assert made["title"] == text[:200], "the title goes to the topic as data, for the person to read"
    assert made["change_set"]["ops"][0]["name"] == text[:200]
    assert made["change_set"]["provenance"]["ai_model"] == "claude-test"
