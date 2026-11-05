# This file was generated with the assistance of an AI coding tool.
"""Request and response bodies of the BCF API, mirroring ``spec/bcf-api/Schemas``.

Field names and optionality follow the JSON schemas one to one; the comments
give the schema file. Lengths are bounded so a client cannot store megabytes
in a title. Unknown fields are ignored on input (Foundation API 1.8) and
``None`` fields are left out of responses, except where the schema requires
them.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from opencde.timeutil import canonical_iso

TITLE_MAX = 512
TEXT_MAX = 10_000
VALUE_MAX = 200
LIST_MAX = 100
URL_MAX = 2000


class BcfModel(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


def _optional_datetime(value: str | None) -> str | None:
    if value is None or value == "":
        return None
    try:
        return canonical_iso(value)
    except ValueError as exc:
        raise ValueError("must be an ISO 8601 date-time") from exc


# ---------------------------------------------------------------------------- projects (3.1)


class ProjectAuthorization(BcfModel):
    project_actions: list[str] | None = None


class ProjectGET(BcfModel):
    """``Project/project_GET.json``"""

    project_id: str
    name: str
    authorization: ProjectAuthorization | None = None


class ProjectPUT(BcfModel):
    """``Project/project_PUT.json``"""

    name: str = Field(min_length=1, max_length=VALUE_MAX)


class ExtensionsGET(BcfModel):
    """``Project/extensions_GET.json`` plus ``custom_information`` (additional property)."""

    topic_type: list[str]
    topic_status: list[str]
    topic_label: list[str]
    snippet_type: list[str]
    priority: list[str]
    users: list[str]
    stage: list[str]
    custom_information: list[str] = []
    project_actions: list[str] = []
    topic_actions: list[str] = []
    comment_actions: list[str] = []


# ---------------------------------------------------------------------------- topics (3.2)


class BimSnippet(BcfModel):
    """``Topic/bim_snippet.json``"""

    snippet_type: str = Field(min_length=1, max_length=VALUE_MAX)
    is_external: bool
    reference: str = Field(min_length=1, max_length=URL_MAX)
    reference_schema: str = Field(min_length=1, max_length=URL_MAX)


class TopicFields(BcfModel):
    """Fields shared by ``topic_POST.json`` and ``topic_PUT.json``."""

    topic_type: str | None = Field(None, max_length=VALUE_MAX)
    topic_status: str | None = Field(None, max_length=VALUE_MAX)
    reference_links: list[str] | None = Field(None, max_length=LIST_MAX)
    title: str = Field(min_length=1, max_length=TITLE_MAX)
    priority: str | None = Field(None, max_length=VALUE_MAX)
    index: int | None = Field(None, ge=0, le=1_000_000_000)
    labels: list[str] | None = Field(None, max_length=LIST_MAX)
    assigned_to: str | None = Field(None, max_length=VALUE_MAX)
    stage: str | None = Field(None, max_length=VALUE_MAX)
    description: str | None = Field(None, max_length=TEXT_MAX)
    bim_snippet: BimSnippet | None = None
    due_date: str | None = Field(None, max_length=64)

    @field_validator("due_date")
    @classmethod
    def _due_date(cls, value: str | None) -> str | None:
        return _optional_datetime(value)

    @field_validator("reference_links", "labels")
    @classmethod
    def _string_items(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        cleaned = []
        for item in value:
            if not isinstance(item, str) or not item.strip() or len(item) > URL_MAX:
                raise ValueError("items must be non-empty strings")
            if item not in cleaned:
                cleaned.append(item.strip())
        return cleaned


class TopicPOST(TopicFields):
    """``Topic/topic_POST.json``"""

    guid: str | None = Field(None, max_length=64)


class TopicPUT(TopicFields):
    """``Topic/topic_PUT.json``"""


class TopicAuthorization(BcfModel):
    topic_actions: list[str] | None = None
    topic_status: list[str] | None = None


class TopicGET(BcfModel):
    """``Topic/topic_GET.json``"""

    guid: str
    server_assigned_id: str
    topic_type: str | None = None
    topic_status: str | None = None
    reference_links: list[str] | None = None
    title: str
    priority: str | None = None
    index: int | None = None
    labels: list[str] | None = None
    creation_date: str
    creation_author: str
    modified_date: str | None = None
    modified_author: str | None = None
    assigned_to: str | None = None
    stage: str | None = None
    description: str | None = None
    bim_snippet: BimSnippet | None = None
    due_date: str | None = None
    authorization: TopicAuthorization | None = None


# ---------------------------------------------------------------------------- events (3.9, 3.10)


class EventAction(BcfModel):
    """``Events/event_action.json``"""

    type: str
    value: str | None = None


class TopicEventGET(BcfModel):
    """``Events/topic_event_GET.json``"""

    topic_guid: str
    date: str
    author: str
    actions: list[EventAction]


class CommentEventGET(BcfModel):
    """``Events/comment_event_GET.json``"""

    comment_guid: str
    topic_guid: str
    date: str
    author: str
    actions: list[EventAction]


def dump(model: BaseModel) -> dict[str, Any]:
    """Response body without ``None`` fields (lists stay, even when empty)."""
    return model.model_dump(exclude_none=True)
