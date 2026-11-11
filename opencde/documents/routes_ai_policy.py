# This file was generated with the assistance of an AI coding tool.
"""A project's AI policy for its members: an extension of the Documents API (F29 a, F30 a, ADR 0028).

``GET /documents/1.0/projects/{project_id}/ai-policy`` tells every member where AI tools may take the project's data:
``local``, only to programs on the user's own computer, or ``cloud``, to AI services in the cloud as well. A client
such as Dataspatium refuses AI services in the cloud for a ``local`` project. The policy is a manager's or an
administrator's to set (``/manage/1.0/projects/{id}``, ``/admin/api/projects/{id}``), never through here. The same
bearer token as the Documents API; 404 for a project the caller is not a member of.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Path
from pydantic import BaseModel, Field

from opencde.auth.dependencies import DocumentsPrincipal
from opencde.deps import ProjectsDep
from opencde.ids import is_uuid, normalize_guid
from opencde.store.accounts.projects import AiPolicy

TAG = "AI policy (extension)"

router = APIRouter(prefix="/documents/1.0", tags=[TAG])

ProjectId = Annotated[str, Path(alias="project_id", max_length=64)]


class ProjectAiPolicy(BaseModel):
    project_id: str
    ai_policy: AiPolicy = Field(
        description="`local`: AI tools get the project's data only on the user's own computer, through the local "
        "engine or a local model. `cloud`: AI services in the cloud may get it too. A project nobody has set is "
        "`local`."
    )


@router.get(
    "/projects/{project_id}/ai-policy",
    summary="Get where AI tools may take the project's data",
    response_model=ProjectAiPolicy,
)
async def ai_policy(principal: DocumentsPrincipal, project_id: ProjectId, projects: ProjectsDep) -> ProjectAiPolicy:
    """For every member of the project, whatever the role. 404 when the project is not yours."""
    if not is_uuid(project_id):
        raise HTTPException(404, "Project not found")
    pid = normalize_guid(project_id)
    # From the caller's own user node through MEMBER_OF: a project the caller is not in is not there.
    found = [project for project, _ in await projects.list_for_user(principal.user_id) if project.project_id == pid]
    if not found:
        raise HTTPException(404, "Project not found")
    return ProjectAiPolicy(project_id=pid, ai_policy=found[0].ai_policy)
