# This file was generated with the assistance of an AI coding tool.
"""Project roles and how they map to the actions the BCF API advertises.

BCF API 3.0 tells a client what the current user may do through
``project_actions``, ``topic_actions``, ``comment_actions`` and
``viewpoint_actions`` (BCF 1.2, 3.1.5). The server derives those lists from
one project role per user plus authorship of the entity:

* ``viewer``: read everything in the project.
* ``contributor``: create topics, comments and viewpoints; edit and delete
  what they created themselves, but propose no change set.
* ``editor``: everything a contributor can, on all entities; also upload
  documents, edit file references and propose change sets.
* ``manager``: everything, including renaming the project, deleting topics
  and managing members.

Administrators (``User.is_admin``) manage the server but have no implicit
project access; they add themselves as members when they need it.
"""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    VIEWER = "viewer"
    CONTRIBUTOR = "contributor"
    EDITOR = "editor"
    MANAGER = "manager"


_RANK = {Role.VIEWER: 0, Role.CONTRIBUTOR: 1, Role.EDITOR: 2, Role.MANAGER: 3}
# The least role that proposes a change set (F35 a, ADR 0028): a contributor reports, an editor proposes.
PROPOSER = Role.EDITOR

PROJECT_ACTIONS_ALL = ("update", "createTopic", "createDocument")
TOPIC_ACTIONS_ALL = (
    "update",
    "updateBimSnippet",
    "updateRelatedTopics",
    "updateDocumentReferences",
    "updateFiles",
    "createComment",
    "createViewpoint",
    "delete",
)
COMMENT_ACTIONS_ALL = ("update", "delete")
VIEWPOINT_ACTIONS_ALL = ("delete",)

_TOPIC_EDIT = ("update", "updateBimSnippet", "updateRelatedTopics", "updateDocumentReferences", "updateFiles")
_TOPIC_ADD = ("createComment", "createViewpoint")


def at_least(role: Role | None, minimum: Role) -> bool:
    return role is not None and _RANK[role] >= _RANK[minimum]


def project_actions(role: Role | None) -> list[str]:
    if role is None or role is Role.VIEWER:
        return []
    if role is Role.CONTRIBUTOR:
        return ["createTopic"]
    if role is Role.EDITOR:
        return ["createTopic", "createDocument"]
    return list(PROJECT_ACTIONS_ALL)


def topic_actions(role: Role | None, is_author: bool) -> list[str]:
    if role is None or role is Role.VIEWER:
        return []
    if role is Role.CONTRIBUTOR:
        return [*_TOPIC_ADD, *(_TOPIC_EDIT if is_author else ()), *(("delete",) if is_author else ())]
    if role is Role.EDITOR:
        return [*_TOPIC_EDIT, *_TOPIC_ADD, *(("delete",) if is_author else ())]
    return list(TOPIC_ACTIONS_ALL)


def comment_actions(role: Role | None, is_author: bool) -> list[str]:
    if role is None or role is Role.VIEWER:
        return []
    if role is Role.CONTRIBUTOR:
        return list(COMMENT_ACTIONS_ALL) if is_author else []
    return list(COMMENT_ACTIONS_ALL)


def viewpoint_actions(role: Role | None, is_author: bool) -> list[str]:
    if role is None or role is Role.VIEWER:
        return []
    if role is Role.CONTRIBUTOR:
        return list(VIEWPOINT_ACTIONS_ALL) if is_author else []
    return list(VIEWPOINT_ACTIONS_ALL)
