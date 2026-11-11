# This file was generated with the assistance of an AI coding tool.
"""Who may do what in a project.

Every BCF route takes a :class:`ProjectContext`: the project, the caller and
the caller's role in it. A caller without a role gets ``404 Not Found`` for
the project and everything under it, so the existence of other people's
projects is not revealed. Actions a role does not allow give ``403``
(Foundation API 1.5).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Path

from opencde.accounts.roles import (
    PROPOSER,
    Role,
    at_least,
    comment_actions,
    project_actions,
    topic_actions,
    viewpoint_actions,
)
from opencde.auth.dependencies import BcfPrincipal
from opencde.deps import ProjectsDep, UsersDep
from opencde.ids import is_uuid, normalize_guid
from opencde.store.accounts.projects import Project
from opencde.store.oauth2.tokens import Principal

NOT_FOUND = "Project not found"


@dataclass(frozen=True)
class ProjectContext:
    project: Project
    principal: Principal
    role: Role

    @property
    def project_id(self) -> str:
        return self.project.project_id

    @property
    def user_id(self) -> str:
        return self.principal.user_id

    @property
    def username(self) -> str:
        return self.principal.username

    # -- capability checks (raise 403) -------------------------------------------

    def require(self, allowed: bool, action: str) -> None:
        if not allowed:
            raise HTTPException(403, f"Your role '{self.role.value}' does not allow '{action}' here")

    def require_role(self, minimum: Role, action: str) -> None:
        self.require(at_least(self.role, minimum), action)

    def require_proposer(self) -> None:
        """A change set is an ``editor``'s or a ``manager``'s to propose (F35 a); 403 says so to anyone else."""
        if not at_least(self.role, PROPOSER):
            raise HTTPException(
                403,
                f"Your role '{self.role.value}' does not allow proposing a change set here; that takes the role "
                "editor or manager",
            )

    def project_actions(self) -> list[str]:
        return project_actions(self.role)

    def topic_actions(self, author: str | None) -> list[str]:
        return topic_actions(self.role, author == self.username)

    def comment_actions(self, author: str | None) -> list[str]:
        return comment_actions(self.role, author == self.username)

    def viewpoint_actions(self, author: str | None) -> list[str]:
        return viewpoint_actions(self.role, author == self.username)

    def can(self, action: str, author: str | None = None, *, entity: str = "topic") -> bool:
        if entity == "project":
            return action in self.project_actions()
        if entity == "comment":
            return action in self.comment_actions(author)
        if entity == "viewpoint":
            return action in self.viewpoint_actions(author)
        return action in self.topic_actions(author)


def parse_guid(value: str, what: str = "identifier") -> str:
    if not is_uuid(value):
        raise HTTPException(404, f"{what} not found")
    return normalize_guid(value)


async def project_context(
    project_id: Annotated[str, Path(max_length=64)],
    principal: BcfPrincipal,
    users: UsersDep,
    projects: ProjectsDep,
) -> ProjectContext:
    if not is_uuid(project_id):
        raise HTTPException(404, NOT_FOUND)
    pid = normalize_guid(project_id)
    role = await users.project_role(principal.user_id, pid)
    if role is None:
        raise HTTPException(404, NOT_FOUND)
    project = await projects.get(pid)
    if project is None:
        raise HTTPException(404, NOT_FOUND)
    return ProjectContext(project=project, principal=principal, role=role)


ProjectCtx = Annotated[ProjectContext, Depends(project_context)]
