# This file was generated with the assistance of an AI coding tool.
"""A list the server cuts at its own limit says so (F14 a, S-13): ``X-Total-Count`` with every match and ``Link:
rel="next"`` with the rest, for topics, comments and events in BCF 3.0 and 2.1; a whole list, or one the caller cut
with ``$top``, has neither."""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from opencde.bcf import odata_params
from opencde.settings import Settings
from tests.integration.conftest_accounts import World, build_world, login_as
from tests.integration.test_bcf_links_documents import make_topic

pytestmark = pytest.mark.integration


@pytest.fixture
def world(settings: Settings, clean_database: None) -> World:
    return build_world(settings)


def next_of(link: str) -> str:
    found = re.fullmatch(r'<(?P<url>[^>]+)>; rel="next"', link)
    assert found, link
    return found["url"].removeprefix("http://testserver")


def test_a_list_cut_at_the_servers_limit_names_the_total_and_the_rest(
    client: TestClient, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(odata_params, "MAX_TOP", 2)
    editor = login_as(client, world, "editor")
    guids = [make_topic(client, world, editor, title=f"Topic {n}")["guid"] for n in range(5)]
    topics = f"/bcf/3.0/projects/{world.project_id}/topics"

    first = client.get(topics, headers=editor.headers)
    assert first.status_code == 200 and len(first.json()) == 2
    assert first.headers["x-total-count"] == "5"
    second = client.get(next_of(first.headers["link"]), headers=editor.headers)
    assert len(second.json()) == 2 and second.headers["x-total-count"] == "5"
    last = client.get(next_of(second.headers["link"]), headers=editor.headers)
    assert len(last.json()) == 1 and "link" not in last.headers and "x-total-count" not in last.headers
    seen = [topic["guid"] for page in (first, second, last) for topic in page.json()]
    assert sorted(seen) == sorted(guids), "the pages together hold every topic once"

    asked = client.get(topics, params={"$top": "2"}, headers=editor.headers)
    assert len(asked.json()) == 2 and "link" not in asked.headers, "a $top of the caller's is not the server's cut"
    filtered = client.get(topics, params={"$filter": "title eq 'Topic 3'"}, headers=editor.headers)
    assert len(filtered.json()) == 1 and "x-total-count" not in filtered.headers

    events = client.get(f"/bcf/3.0/projects/{world.project_id}/topics/events", headers=editor.headers)
    assert len(events.json()) == 2 and int(events.headers["x-total-count"]) >= 5
    older = client.get(f"/bcf/2.1/projects/{world.project_id}/topics", headers=editor.headers)
    assert len(older.json()) == 2 and older.headers["x-total-count"] == "5" and 'rel="next"' in older.headers["link"]

    topic = f"{topics}/{guids[0]}/comments"
    for n in range(3):
        assert client.post(topic, json={"comment": f"Comment {n}"}, headers=editor.headers).status_code == 201
    comments = client.get(topic, headers=editor.headers)
    assert len(comments.json()) == 2 and comments.headers["x-total-count"] == "3"
