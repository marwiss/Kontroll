# This file was generated with the assistance of an AI coding tool.
"""Topic and comment events (BCF API 3.9 and 3.10).

Every change to a topic or a comment is recorded as an ``Event`` node attached
to the project (so it survives the deletion of the topic) with the event
types the specification enumerates. One request can produce several actions
(for example a title and a status change); they are stored together as one
event with parallel ``action_types`` and ``action_values`` lists, which is
how the specification groups them in the response.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from opencde.graph.graph import Graph, Tx
from opencde.ids import new_id
from opencde.odata import Compiled, Field
from opencde.timeutil import now_iso

TOPIC_EVENT_TYPES = (
    "topic_created",
    "title_updated",
    "description_updated",
    "description_removed",
    "status_updated",
    "type_updated",
    "priority_updated",
    "priority_removed",
    "due_date_updated",
    "due_date_removed",
    "assigned_to_updated",
    "assigned_to_removed",
    "label_added",
    "label_removed",
    "stage_added",
    "stage_updated",
    "stage_removed",
)
COMMENT_EVENT_TYPES = (
    "comment_created",
    "comment_text_updated",
    "viewpoint_updated",
    "viewpoint_removed",
    "reply_to_comment_updated",
    "reply_to_comment_removed",
)
# Each version answers with the types it knows: stages came with 3.0, which took replies between comments away.
NOT_IN_30 = frozenset({"reply_to_comment_updated", "reply_to_comment_removed"})
NOT_IN_21 = frozenset({"stage_added", "stage_updated", "stage_removed"})

TITLE_VALUE_LIMIT = 128
TEXT_VALUE_LIMIT = 1024

EVENT_FIELDS = {
    "topic_guid": Field("e.topic_guid", "string"),
    "comment_guid": Field("e.comment_guid", "string"),
    "author": Field("e.author", "string"),
    "date": Field("e.date", "datetime"),
    "type": Field("e.action_types", "string_list"),
}
EVENT_ORDERABLE = ("date",)
EVENT_DEFAULT_ORDER = "e.date ASC"


@dataclass(frozen=True)
class Action:
    type: str
    value: str | None = None


def _clip(value: str | None, limit: int) -> str | None:
    return None if value is None else value[:limit]


def topic_diff(old: dict[str, Any], new: dict[str, Any]) -> list[Action]:
    """The event actions that describe going from ``old`` to ``new`` (both topic property maps)."""
    actions: list[Action] = []
    if old.get("title") != new.get("title"):
        actions.append(Action("title_updated", _clip(new.get("title"), TITLE_VALUE_LIMIT)))
    if old.get("description") != new.get("description"):
        if new.get("description") is None:
            actions.append(Action("description_removed"))
        else:
            actions.append(Action("description_updated", _clip(new.get("description"), TEXT_VALUE_LIMIT)))
    if old.get("topic_status") != new.get("topic_status"):
        actions.append(Action("status_updated", new.get("topic_status")))
    if old.get("topic_type") != new.get("topic_type"):
        actions.append(Action("type_updated", new.get("topic_type")))
    for field, updated, removed in (
        ("priority", "priority_updated", "priority_removed"),
        ("due_date", "due_date_updated", "due_date_removed"),
        ("assigned_to", "assigned_to_updated", "assigned_to_removed"),
    ):
        if old.get(field) != new.get(field):
            actions.append(Action(removed) if new.get(field) is None else Action(updated, new.get(field)))
    old_labels, new_labels = set(old.get("labels") or []), set(new.get("labels") or [])
    actions.extend(Action("label_added", label) for label in sorted(new_labels - old_labels))
    actions.extend(Action("label_removed", label) for label in sorted(old_labels - new_labels))
    if old.get("stage") != new.get("stage"):
        if new.get("stage") is None:
            actions.append(Action("stage_removed"))
        elif old.get("stage") is None:
            actions.append(Action("stage_added", new.get("stage")))
        else:
            actions.append(Action("stage_updated", new.get("stage")))
    return actions


async def record(
    tx: Tx,
    *,
    project_id: str,
    topic_guid: str,
    author: str,
    actions: list[Action],
    comment_guid: str | None = None,
    date: str | None = None,
) -> None:
    """Store one event with its actions inside the caller's transaction."""
    if not actions:
        return
    await tx.run(
        """
        MATCH (p:Project {project_id: $project_id})
        CREATE (p)-[:HAS_EVENT]->(e:Event {
            id: $id, kind: $kind, topic_guid: $topic_guid, comment_guid: $comment_guid, author: $author,
            date: $date, action_types: $types, action_values: $values
        })
        """,
        project_id=project_id,
        id=new_id(),
        kind="comment" if comment_guid else "topic",
        topic_guid=topic_guid,
        comment_guid=comment_guid,
        author=author,
        date=date or now_iso(),
        types=[action.type for action in actions],
        values=[action.value if action.value is not None else "" for action in actions],
    )


def _row_to_event(row: dict[str, Any], left_out: frozenset[str]) -> dict[str, Any]:
    event = row["event"]
    actions = [
        {"type": kind, "value": value or None}
        for kind, value in zip(event.get("action_types") or [], event.get("action_values") or [], strict=False)
        if kind not in left_out
    ]
    body: dict[str, Any] = {
        "topic_guid": event["topic_guid"],
        "date": event["date"],
        "author": event["author"],
        "actions": actions,
    }
    if event.get("comment_guid"):
        body["comment_guid"] = event["comment_guid"]
    return body


def _matching(compiled: Compiled) -> str:
    return f"""
        MATCH (:User {{id: $user_id}})-[:MEMBER_OF]->(p:Project {{project_id: $project_id}})-[:HAS_EVENT]->(e:Event)
        WHERE e.kind = $kind
          AND ($topic_guid IS NULL OR e.topic_guid = $topic_guid)
          AND ($comment_guid IS NULL OR e.comment_guid = $comment_guid)
          AND any(action IN e.action_types WHERE NOT action IN $left_out)
          {compiled.where_clause()}
        """


async def count(
    graph: Graph,
    *,
    user_id: str,
    project_id: str,
    kind: str,
    compiled: Compiled,
    topic_guid: str | None = None,
    comment_guid: str | None = None,
    left_out: frozenset[str] = frozenset(),
) -> int:
    """How many events ``query`` matches, before ``$top`` and ``$skip``."""
    row = await graph.one(
        _matching(compiled) + "RETURN count(e) AS total",
        user_id=user_id,
        project_id=project_id,
        kind=kind,
        topic_guid=topic_guid,
        comment_guid=comment_guid,
        left_out=sorted(left_out),
        **compiled.params,
    )
    return int(row["total"]) if row else 0


async def query(
    graph: Graph,
    *,
    user_id: str,
    project_id: str,
    kind: str,
    compiled: Compiled,
    topic_guid: str | None = None,
    comment_guid: str | None = None,
    left_out: frozenset[str] = frozenset(),
) -> list[dict[str, Any]]:
    """Events of a project (optionally one topic or comment), filtered and ordered by OData options, without the
    actions of ``left_out`` and without the events that then have none left."""
    rows = await graph.run(
        _matching(compiled)
        + f"""
        RETURN properties(e) AS event
        ORDER BY {compiled.order_by}
        SKIP $skip LIMIT $limit
        """,
        user_id=user_id,
        project_id=project_id,
        kind=kind,
        topic_guid=topic_guid,
        comment_guid=comment_guid,
        left_out=sorted(left_out),
        skip=compiled.skip,
        limit=compiled.limit,
        **compiled.params,
    )
    return [_row_to_event(row, left_out) for row in rows]
