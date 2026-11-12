# This file was generated with the assistance of an AI coding tool.
"""``get_publication`` through the MCP endpoint (ADR 0028): whether a version is published, when, by whom and its
archive, as ``GET …/publication`` says it, and never where the archive is downloaded. The database is stood in for
(``tests/mcp_read_support.py``)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests.mcp_read_support import PUBLISHED, DocumentsGraph, tools, version
from tests.mcp_support import DOCUMENT, call


def publication(client: Any, **arguments: Any) -> dict[str, Any]:
    answer = call(client, "get_publication", {"document_id": DOCUMENT, "version_index": 3, **arguments})
    assert answer.status_code == 200, answer.text
    return answer.json()["result"]


def test_a_published_version_says_when_by_whom_and_its_archive_but_not_where_it_is(tmp_path: Path) -> None:
    with tools(tmp_path, DocumentsGraph(publications={3: PUBLISHED})) as client:
        result = publication(client)
    assert result["isError"] is False
    assert result["structuredContent"] == {
        "published": True,
        "published_at": "2026-11-12T09:30:00.000Z",
        "published_by": "bo",
        "file_name": "walls.ifczip",
        "size_in_bytes": 1234,
        "sha256": "a" * 64,
    }
    text = result["content"][0]["text"]
    assert json.loads(text) == result["structuredContent"]
    assert "download" not in text and "http" not in text and "storage_key" not in text and "published/" not in text


def test_a_version_that_is_not_published_says_so_with_every_field_null(tmp_path: Path) -> None:
    graph = DocumentsGraph(versions=[version(2), version(3)], publications={3: PUBLISHED})
    with tools(tmp_path, graph) as client:
        answer = publication(client, version_index=2)["structuredContent"]
    assert answer == dict.fromkeys(("published_at", "published_by", "file_name", "size_in_bytes", "sha256")) | {
        "published": False
    }


def test_the_publication_is_read_without_the_ifc_db_module(tmp_path: Path) -> None:
    with tools(tmp_path, DocumentsGraph(publications={3: PUBLISHED}), ifcgraph_enabled=False) as client:
        assert publication(client)["structuredContent"]["published"] is True


@pytest.mark.parametrize(
    ("arguments", "expected"),
    [
        ({"document_id": "not a document"}, "There is no such document version among your projects"),
        ({"version_index": 7}, "There is no such document version among your projects"),
        ({"version_index": None}, "Invalid arguments: version_index: Input should be a valid integer"),
        ({"version_index": 0}, "Invalid arguments: version_index: Input should be greater than or equal to 1"),
        ({"download": True}, "Invalid arguments: an argument the tool does not take"),
    ],
)
def test_a_refusal_names_no_value(tmp_path: Path, arguments: dict[str, Any], expected: str) -> None:
    with tools(tmp_path, DocumentsGraph(publications={3: PUBLISHED})) as client:
        result = publication(client, **arguments)
    assert result["isError"] is True and result["content"][0]["text"] == expected


def test_a_project_that_is_not_the_users_has_no_publication_to_give(tmp_path: Path) -> None:
    with tools(tmp_path, DocumentsGraph(memberships=[], publications={3: PUBLISHED})) as client:
        result = publication(client)
    assert result["content"][0]["text"] == "There is no such document version among your projects"
