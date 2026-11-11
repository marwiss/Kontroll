# This file was generated with the assistance of an AI coding tool.
"""Project administration by its managers: an extension outside the OpenCDE specifications (OB-41).

A ``manager`` of a project manages its members and their roles; its name changes through the BCF API's PUT Project,
which a manager may already do. Nothing here deletes a project or touches the server's own roles: that stays with the
administrators. The routes need a bearer token with the ``project`` scope, which a client asks for explicitly, and
every request first finds the caller's role in the project from the caller's own user node. A member is added by exact
user name, so that a manager never lists the server's users, and a member is shown with user name, name and role, not
e-mail. A project keeps at least one manager. Every write leaves an audit event.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from opencde import audit
from opencde.accounts.roles import Role
from opencde.auth.dependencies import require_scope
from opencde.deps import GraphDep, ProjectsDep, UsersDep, client_ip
from opencde.errors import CODE_CONFLICT, ApiError
from opencde.graph.graph import Graph
from opencde.store.oauth2.tokens import Principal

router = APIRouter(prefix="/manage/1.0", tags=["Project administration (extension)"])

ProjectPrincipal = Annotated[Principal, Depends(require_scope("project"))]
IdPath = Annotated[str, Path(max_length=64)]
RoleName = Literal["viewer", "contributor", "editor", "manager"]
ROLES: tuple[str, ...] = ("viewer", "contributor", "editor", "manager")


class MemberAdd(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=100, description="The exact user name of the member to add.")
    role: RoleName


class MemberRole(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: RoleName


async def _managed(graph: Graph, principal: Principal, project_id: str) -> None:
    """404 unless the caller is a member of the project, 403 unless a manager of it."""
    row = await graph.one(
        "MATCH (:User {id: $user_id})-[m:MEMBER_OF]->(:Project {project_id: $project_id}) RETURN m.role AS role",
        user_id=principal.user_id,
        project_id=project_id,
    )
    if row is None:
        raise HTTPException(404, "No such project")
    if row["role"] != Role.MANAGER.value:
        raise HTTPException(403, "Only a manager of the project manages its members")


async def _keeps_a_manager(projects: ProjectsDep, project_id: str, user_id: str, role: str | None) -> None:
    """409 when the change would leave the project without a manager."""
    members = await projects.members(project_id)
    managers = [user.id for user, member_role in members if member_role is Role.MANAGER]
    if managers == [user_id] and role != Role.MANAGER.value:
        raise ApiError(409, "A project keeps at least one manager", code=CODE_CONFLICT)


async def _record(request: Request, graph: Graph, principal: Principal, action: str, **details: Any) -> None:
    await audit.record(
        graph,
        f"manage.{action}",
        actor=principal.user_id,
        client_id=principal.client_id,
        ip=client_ip(request),
        details={key: value for key, value in details.items() if value is not None},
    )


@router.get("/projects", summary="Project administration (extension): the projects you manage")
async def managed_projects(principal: ProjectPrincipal, projects: ProjectsDep) -> dict[str, Any]:
    managed = [
        {"project_id": project.project_id, "name": project.name}
        for project, role in await projects.list_for_user(principal.user_id)
        if role is Role.MANAGER
    ]
    return {"items": managed, "total": len(managed)}


@router.get("/projects/{project_id}/members", summary="Project administration (extension): the members and roles")
async def list_members(
    principal: ProjectPrincipal, project_id: IdPath, projects: ProjectsDep, graph: GraphDep
) -> dict[str, Any]:
    await _managed(graph, principal, project_id)
    members = [
        {"user_id": user.id, "username": user.username, "name": user.full_name, "role": role.value}
        for user, role in await projects.members(project_id)
    ]
    return {"items": members, "total": len(members)}


@router.post(
    "/projects/{project_id}/members",
    status_code=201,
    summary="Project administration (extension): add a member by user name, or set their role",
    responses={200: {"description": "Already a member; the role was set."}, 404: {"description": "No such user."}},
)
async def add_member(
    request: Request,
    response: Response,
    principal: ProjectPrincipal,
    project_id: IdPath,
    body: MemberAdd,
    projects: ProjectsDep,
    users: UsersDep,
    graph: GraphDep,
) -> dict[str, Any]:
    await _managed(graph, principal, project_id)
    user = await users.get_by_username(body.username.strip())
    if user is None:
        raise HTTPException(404, "No such user")
    current = {member.id: role for member, role in await projects.members(project_id)}
    if user.id in current:
        await _keeps_a_manager(projects, project_id, user.id, body.role)
        response.status_code = 200
    await projects.set_member(project_id, user.id, Role(body.role))
    await _record(request, graph, principal, "membership.set", project_id=project_id, user_id=user.id, role=body.role)
    return {"user_id": user.id, "username": user.username, "name": user.full_name, "role": body.role}


@router.put("/projects/{project_id}/members/{user_id}", summary="Project administration (extension): set a role")
async def set_role(
    request: Request,
    principal: ProjectPrincipal,
    project_id: IdPath,
    user_id: IdPath,
    body: MemberRole,
    projects: ProjectsDep,
    graph: GraphDep,
) -> dict[str, Any]:
    await _managed(graph, principal, project_id)
    if user_id not in {member.id for member, _ in await projects.members(project_id)}:
        raise HTTPException(404, "No such member")
    await _keeps_a_manager(projects, project_id, user_id, body.role)
    await projects.set_member(project_id, user_id, Role(body.role))
    await _record(request, graph, principal, "membership.set", project_id=project_id, user_id=user_id, role=body.role)
    return {"user_id": user_id, "role": body.role}


@router.delete(
    "/projects/{project_id}/members/{user_id}",
    status_code=204,
    summary="Project administration (extension): remove a member",
)
async def remove_member(
    request: Request,
    principal: ProjectPrincipal,
    project_id: IdPath,
    user_id: IdPath,
    projects: ProjectsDep,
    graph: GraphDep,
) -> Response:
    await _managed(graph, principal, project_id)
    if user_id not in {member.id for member, _ in await projects.members(project_id)}:
        raise HTTPException(404, "No such member")
    await _keeps_a_manager(projects, project_id, user_id, None)
    await projects.remove_member(project_id, user_id)
    await _record(request, graph, principal, "membership.remove", project_id=project_id, user_id=user_id)
    return Response(status_code=204)
