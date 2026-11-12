# This file was generated with the assistance of an AI coding tool.
"""The open change sets of the MCP endpoint (ADR 0028, F28 a): a draft under its project, owned by its user.

An AI fills a change set step by step through the endpoint's tools, and between the calls it lives here: a
``ChangeSetDraft`` under its project (``HAS_DRAFT``), named by ``changeset_id``, the handle the AI holds. The handle is
a name, not a permission: every statement starts at the user and reaches the draft through ``MEMBER_OF``, and a draft
is its user's alone. It holds its base (the document and the version the changes build on), its steps in the order of
the calls (the write tools' operations with their refs, and the posts in ``changes``; ``mcp/write_tools.py`` reads
them), how many refs it has given out, the topic it was proposed on, ``created_at`` and ``expires_at``: 24 hours
after its last use, after which the server's cleaner deletes it (``EXPIRING_LABELS``). A user has at most 10 open
drafts, and a draft at most 200 steps in 2 MB.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

from opencde.graph.graph import Graph, Tx
from opencde.ids import new_id
from opencde.timeutil import later_iso, now_iso

MAX_OPEN = 10  # open drafts per user
MAX_STEPS = 200  # steps per draft: Dataspatium's MAX_OPS
MAX_BYTES = 2 * 1024 * 1024  # a draft's steps as JSON
LIFETIME_SECONDS = 24 * 3600  # after the last use

#: The caller's draft, unexpired, reached from the user through MEMBER_OF.
_DRAFT = """
MATCH (:User {id: $user_id})-[:MEMBER_OF]->(:Project)-[:HAS_DRAFT]->(d:ChangeSetDraft {changeset_id: $changeset_id})
WHERE d.user_id = $user_id AND d.expires_at > $now
"""

OPEN = """
MATCH (u:User {id: $user_id})-[:MEMBER_OF]->(p:Project {project_id: $project_id})
      -[:HAS_DOCUMENT]->(:Document {document_id: $document_id})
OPTIONAL MATCH (u)-[:MEMBER_OF]->(:Project)-[:HAS_DRAFT]->(o:ChangeSetDraft {user_id: $user_id})
WHERE o.expires_at > $now
WITH p, count(o) AS open
WHERE open < $max_open
CREATE (p)-[:HAS_DRAFT]->(d:ChangeSetDraft {
    changeset_id: $changeset_id, user_id: $user_id, project_id: $project_id, document_id: $document_id,
    version_index: $version_index, steps: '[]', refs: 0, created_at: $now, expires_at: $expires_at
})
RETURN properties(d) AS draft
"""

GET = _DRAFT + "RETURN properties(d) AS draft"

# Writing first takes the draft's lock, so that two calls at once add their steps one after the other; the read
# that follows sees what the other call wrote.
TAKE = _DRAFT + "SET d.expires_at = $expires_at RETURN properties(d) AS draft"

SAVE = (
    _DRAFT
    + """
SET d.steps = $steps, d.refs = $refs, d.topic_guid = $topic_guid
RETURN d.changeset_id AS changeset_id
"""
)


class DraftRefused(ValueError):
    """A change the draft cannot hold, in fixed words the AI can read."""


@dataclass(frozen=True)
class ChangeSetDraft:
    changeset_id: str
    user_id: str
    project_id: str
    document_id: str
    version_index: int
    steps: list[dict[str, Any]]
    refs: int
    topic_guid: str | None
    created_at: str
    expires_at: str

    @property
    def base(self) -> dict[str, Any]:
        """The change set's base, as its schema writes it."""
        return {"document_id": self.document_id, "version_index": self.version_index}


def _draft(node: dict[str, Any]) -> ChangeSetDraft:
    return ChangeSetDraft(
        changeset_id=str(node["changeset_id"]),
        user_id=str(node["user_id"]),
        project_id=str(node["project_id"]),
        document_id=str(node["document_id"]),
        version_index=int(node["version_index"]),
        steps=list(json.loads(node.get("steps") or "[]")),
        refs=int(node.get("refs") or 0),
        topic_guid=node.get("topic_guid"),
        created_at=str(node["created_at"]),
        expires_at=str(node["expires_at"]),
    )


def _steps(draft: ChangeSetDraft) -> str:
    """The steps as the node keeps them: JSON, at most ``MAX_STEPS`` of them in ``MAX_BYTES``."""
    if len(draft.steps) > MAX_STEPS:
        raise DraftRefused(f"A change set holds at most {MAX_STEPS} steps")
    try:
        text = json.dumps(draft.steps, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    except ValueError:
        raise DraftRefused("A number is too large for JSON; give it as an ordinary number") from None
    if len(text.encode("utf-8")) > MAX_BYTES:
        raise DraftRefused(f"A change set holds at most {MAX_BYTES // (1024 * 1024)} MB; propose it as it is")
    return text


class ChangeSetDraftRepository:
    """The caller's open change sets, each reached from the user through ``MEMBER_OF``."""

    def __init__(self, graph: Graph) -> None:
        self.graph = graph

    async def open(
        self, *, user_id: str, project_id: str, document_id: str, version_index: int
    ) -> ChangeSetDraft | None:
        """A new, empty draft on a version of a document of one of the user's projects; None when the user has
        ``MAX_OPEN`` open already (or the document is not there)."""
        row = await self.graph.one(
            OPEN,
            user_id=user_id,
            project_id=project_id,
            document_id=document_id,
            version_index=version_index,
            changeset_id=new_id(),
            now=now_iso(),
            expires_at=later_iso(LIFETIME_SECONDS),
            max_open=MAX_OPEN,
        )
        return _draft(row["draft"]) if row else None

    async def get(self, *, user_id: str, changeset_id: str) -> ChangeSetDraft | None:
        """The user's draft as it is; None when it is unknown, someone else's or expired."""
        row = await self.graph.one(GET, user_id=user_id, changeset_id=changeset_id, now=now_iso())
        return _draft(row["draft"]) if row else None

    async def update(
        self, *, user_id: str, changeset_id: str, change: Callable[[ChangeSetDraft], ChangeSetDraft]
    ) -> ChangeSetDraft | None:
        """The user's draft changed by ``change`` in one transaction, which keeps it open 24 hours more; None when it
        is unknown, someone else's or expired. ``change`` gets the draft as it is and may be called again when the
        database retries the transaction; what it raises rolls the transaction back and reaches the caller, and
        :class:`DraftRefused` says that the draft could not hold the change."""

        async def work(tx: Tx) -> ChangeSetDraft | None:
            now = now_iso()
            row = await tx.one(
                TAKE, user_id=user_id, changeset_id=changeset_id, now=now, expires_at=later_iso(LIFETIME_SECONDS)
            )
            if row is None:
                return None
            found = _draft(row["draft"])
            changed = change(found)
            saved = replace(found, steps=changed.steps, refs=changed.refs, topic_guid=changed.topic_guid)
            await tx.run(
                SAVE,
                user_id=user_id,
                changeset_id=changeset_id,
                now=now,
                steps=_steps(saved),
                refs=saved.refs,
                topic_guid=saved.topic_guid,
            )
            return saved

        return await self.graph.write(work)
