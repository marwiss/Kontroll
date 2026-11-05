# This file was generated with the assistance of an AI coding tool.
"""BCF API 3.1 Project services and 3.1.4 extensions."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from opencde.accounts.roles import comment_actions, project_actions, topic_actions
from opencde.auth.dependencies import BcfPrincipal
from opencde.bcf.access import ProjectCtx
from opencde.bcf.schemas import ExtensionsGET, ProjectAuthorization, ProjectGET, ProjectPUT, dump
from opencde.deps import ProjectsDep

router = APIRouter(prefix="/bcf/3.0", tags=["BCF API"])

IncludeAuthorization = Annotated[bool, Query(alias="includeAuthorization")]


def _project_body(project_id: str, name: str, actions: list[str] | None, include: bool) -> dict[str, Any]:
    model = ProjectGET(project_id=project_id, name=name)
    if include:
        model.authorization = ProjectAuthorization(project_actions=actions or [])
    return dump(model)


@router.get("/projects", summary="3.1.1 GET Projects")
async def projects_get(
    principal: BcfPrincipal, projects: ProjectsDep, include_authorization: IncludeAuthorization = False
) -> list[dict[str, Any]]:
    """The projects the current user is a member of."""
    return [
        _project_body(project.project_id, project.name, project_actions(role), include_authorization)
        for project, role in await projects.list_for_user(principal.user_id)
    ]


@router.get("/projects/{project_id}", summary="3.1.2 GET Project")
async def project_get(ctx: ProjectCtx, include_authorization: IncludeAuthorization = False) -> dict[str, Any]:
    return _project_body(ctx.project_id, ctx.project.name, ctx.project_actions(), include_authorization)


@router.put("/projects/{project_id}", summary="3.1.3 PUT Project")
async def project_put(ctx: ProjectCtx, body: ProjectPUT, projects: ProjectsDep) -> dict[str, Any]:
    """Rename the project. Needs the ``update`` project action (managers)."""
    ctx.require(ctx.can("update", entity="project"), "update")
    project = await projects.rename(ctx.project_id, body.name)
    return _project_body(project.project_id, project.name, ctx.project_actions(), True)


@router.get("/projects/{project_id}/extensions", summary="3.1.4 GET Project Extensions")
async def extensions_get(ctx: ProjectCtx, projects: ProjectsDep) -> dict[str, Any]:
    """Allowed values for topics and comments, and the current user's default actions (3.1.5)."""
    values = await projects.extensions(ctx.project_id)
    if values is None:
        values = {}
    return dump(
        ExtensionsGET(
            topic_type=values.get("topic_type", []),
            topic_status=values.get("topic_status", []),
            topic_label=values.get("topic_label", []),
            snippet_type=values.get("snippet_type", []),
            priority=values.get("priority", []),
            users=values.get("users", []),
            stage=values.get("stage", []),
            custom_information=values.get("custom_information", []),
            project_actions=project_actions(ctx.role),
            topic_actions=topic_actions(ctx.role, is_author=False),
            comment_actions=comment_actions(ctx.role, is_author=False),
        )
    )


__all__ = ["Depends", "router"]
