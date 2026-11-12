# This file was generated with the assistance of an AI coding tool.
"""Proposing a change set: a BCF topic that carries it as its snippet, and its trial (ADR 0021).

What the server's own proposals (``POST …/ifc-unreachable``) and the MCP endpoint's ``propose_changes`` (ADR 0028)
share, so that a change set reaches the trial the same way whoever makes it: the topic with the change set as its
``bim_snippet`` (``DataregiumIfcChangeSet``, the schema at ``GET /documents/1.0/ifc-changes/schema``), a ``Request``
and ``Open`` where the project has them; the change set stored as the topic's snippet; and its trial queued on its
base version. A change set put again on its topic replaces the snippet and the trial, as ``PUT …/snippet`` does.
The callers check the change set with ``changes.problems`` first, and the role of the one who proposes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from opencde.bcf.schemas import BimSnippet, TopicGET, TopicPOST
from opencde.documents.changes import SCHEMA_PATH, SNIPPET_TYPE
from opencde.ifcgraph.service import IfcGraphService
from opencde.storage import LocalStorage, make_key
from opencde.store.bcf.topics import validate_against_extensions
from opencde.store.protocols import ProjectStore, TopicLinkStore, TopicStore

MAX_TITLE = 200  # a topic's title as the server proposes it


@dataclass(frozen=True)
class Proposing:
    """The stores a proposal is made with, and the trial's service."""

    topics: TopicStore
    links: TopicLinkStore
    projects: ProjectStore
    storage: LocalStorage
    ifcgraph: IfcGraphService
    public_url: str

    async def topic(
        self,
        *,
        project_id: str,
        author: str,
        title: str,
        description: str | None,
        change_set: dict[str, Any],
        reference: str,
    ) -> TopicGET:
        """A new topic that carries ``change_set`` as its snippet, named ``reference``, with its trial queued. The
        project's values must allow the snippet's type (400 otherwise, as for any topic)."""
        extensions = await self.projects.extensions(project_id) or {}
        body = TopicPOST(
            title=title[:MAX_TITLE],
            description=description,
            topic_type="Request" if "Request" in (extensions.get("topic_type") or []) else None,
            topic_status="Open" if "Open" in (extensions.get("topic_status") or []) else None,
            bim_snippet=BimSnippet(
                snippet_type=SNIPPET_TYPE,
                is_external=False,
                reference=reference,
                reference_schema=f"{self.public_url}{SCHEMA_PATH}",
            ),
        )
        validate_against_extensions(body, extensions)
        topic = await self.topics.create(project_id=project_id, author=author, body=body)
        await self.snippet(
            project_id=project_id, topic_guid=topic.guid, author=author, change_set=change_set, reference=reference
        )
        return topic

    async def snippet(
        self, *, project_id: str, topic_guid: str, author: str, change_set: dict[str, Any], reference: str
    ) -> None:
        """``change_set`` as the topic's snippet, in place of the one before, and its trial queued in place of the
        one before."""
        key = make_key("snippets", topic_guid, "bin")
        data = json.dumps(change_set, separators=(",", ":")).encode("utf-8")
        self.storage.write_bytes(key, data)
        await self.links.set_snippet(
            project_id=project_id,
            topic_guid=topic_guid,
            author=author,
            storage_key=key,
            filename=reference,
            size=len(data),
        )
        await self.ifcgraph.schedule_proposal(
            project_id=project_id, topic_guid=topic_guid, snippet_key=key, author=author
        )
