# This file was generated with the assistance of an AI coding tool.
"""Admin pages for projects: list, create, rename, members and roles, BCF extensions, deletion."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path, Request
from fastapi.responses import Response

from opencde.accounts.projects import EXTENSION_LISTS, AccountError, Project, ProjectRepository
from opencde.accounts.roles import Role
from opencde.admin import queries
from opencde.admin.access import (
    AdminDep,
    AdminForm,
    admin_context,
    lines,
    not_found,
    password_confirmed,
    redirect_with_notice,
    text,
)
from opencde.deps import GraphDep, ProjectsDep, StorageDep, UsersDep
from opencde.ids import is_uuid, normalize_guid
from opencde.ui.i18n import tr_error
from opencde.ui.links import dataspatium_link
from opencde.ui.templating import render

router = APIRouter(prefix="/admin/projects", include_in_schema=False)

ProjectId = Annotated[str, Path(alias="project_id", max_length=64)]
ROLES = [role.value for role in Role]


async def _project_page(
    request: Request,
    admin: AdminDep,
    project: Project,
    projects: ProjectRepository,
    users: UsersDep,
    error: str | None = None,
    status_code: int = 200,
) -> Response:
    form = AdminForm(request, admin, "admin-project", project.project_id)
    members = await projects.members(project.project_id)
    member_ids = {user.id for user, _ in members}
    extensions = await projects.extensions(project.project_id) or {}
    return render(
        request,
        "admin/project.html",
        admin_context(
            request,
            admin,
            "projects",
            project=project,
            members=members,
            other_users=[u for u in await users.search(limit=1000) if u.id not in member_ids],
            roles=ROLES,
            # (name, value); the page labels each list with t("admin.project.ext.<name>")
            extensions=[(name, "\n".join(extensions.get(name, []))) for name in EXTENSION_LISTS],
            form_token=form.token(),
            error=error,
            dataspatium_link=dataspatium_link(request.app.state.settings, project_id=project.project_id),
        ),
        status_code=status_code,
    )


@router.get("")
async def projects_list(request: Request, admin: AdminDep, projects: ProjectsDep, graph: GraphDep) -> Response:
    return render(
        request,
        "admin/projects.html",
        admin_context(
            request, admin, "projects", projects=await projects.all(), stats=await queries.project_stats(graph)
        ),
    )


@router.get("/new")
async def project_new(request: Request, admin: AdminDep) -> Response:
    form = AdminForm(request, admin, "admin-project-new")
    return render(
        request,
        "admin/project_new.html",
        admin_context(request, admin, "projects", form_token=form.token(), error=None),
    )


@router.post("")
async def project_create(request: Request, admin: AdminDep, projects: ProjectsDep, graph: GraphDep) -> Response:
    form = AdminForm(request, admin, "admin-project-new")
    data = await request.form()
    if not form.check(data.get("form_token")):
        return redirect_with_notice("/admin/projects/new", "form_expired")
    try:
        project = await projects.create(text(data, "name", max_length=200))
    except AccountError as exc:
        return render(
            request,
            "admin/project_new.html",
            admin_context(request, admin, "projects", form_token=form.token(), error=tr_error(request, exc)),
            status_code=400,
        )
    await form.record(graph, "project.create", project_id=project.project_id)
    return redirect_with_notice(f"/admin/projects/{project.project_id}", "created")


@router.get("/{project_id}")
async def project_page(
    request: Request, admin: AdminDep, project_id: ProjectId, projects: ProjectsDep, users: UsersDep
) -> Response:
    project = await projects.get(normalize_guid(project_id)) if is_uuid(project_id) else None
    if project is None:
        raise not_found()
    return await _project_page(request, admin, project, projects, users)


@router.post("/{project_id}")
async def project_action(
    request: Request,
    admin: AdminDep,
    project_id: ProjectId,
    projects: ProjectsDep,
    users: UsersDep,
    graph: GraphDep,
    storage: StorageDep,
) -> Response:
    project = await projects.get(normalize_guid(project_id)) if is_uuid(project_id) else None
    if project is None:
        raise not_found()
    form = AdminForm(request, admin, "admin-project", project.project_id)
    data = await request.form()
    page = f"/admin/projects/{project.project_id}"
    if not form.check(data.get("form_token")):
        return redirect_with_notice(page, "form_expired")
    action = text(data, "action", max_length=32)

    try:
        if action == "rename":
            await projects.rename(project.project_id, text(data, "name", max_length=200))
            await form.record(graph, "project.rename", project_id=project.project_id)
            return redirect_with_notice(page, "saved")

        if action == "member":
            user_id, role = text(data, "user_id", max_length=64), text(data, "role", max_length=32)
            if role not in ROLES or not is_uuid(user_id):
                return redirect_with_notice(page, "invalid")
            await projects.set_member(project.project_id, user_id, Role(role))
            await form.record(graph, "membership.set", user_id=user_id, project_id=project.project_id, role=role)
            return redirect_with_notice(page, "member_saved")

        if action == "remove_member":
            user_id = text(data, "user_id", max_length=64)
            if is_uuid(user_id):
                await projects.remove_member(project.project_id, user_id)
                await form.record(graph, "membership.remove", user_id=user_id, project_id=project.project_id)
            return redirect_with_notice(page, "member_removed")

        if action == "extensions":
            values = {name: lines(data, name, max_items=200, max_length=100) for name in EXTENSION_LISTS}
            await projects.set_extensions(project.project_id, values)
            await form.record(graph, "project.extensions", project_id=project.project_id)
            return redirect_with_notice(page, "extensions_saved")

        if action == "delete":
            if not await password_confirmed(users, admin, data.get("confirm_password")):
                return redirect_with_notice(page, "wrong_password")
            keys = await _storage_keys(graph, project.project_id)
            await projects.delete(project.project_id)
            for key in keys:
                try:
                    storage.delete(key)
                except ValueError:
                    pass
            await form.record(graph, "project.delete", project_id=project.project_id, name=project.name)
            return redirect_with_notice("/admin/projects", "deleted")
    except AccountError as exc:
        return await _project_page(
            request, admin, project, projects, users, error=tr_error(request, exc), status_code=400
        )

    return redirect_with_notice(page, "invalid")


async def _storage_keys(graph: GraphDep, project_id: str) -> list[str]:
    """Every stored file below a project, so deleting the project also frees the disk."""
    rows = await graph.run(
        """
        MATCH (p:Project {project_id: $id})-[*1..4]->(n)
        WHERE n.storage_key IS NOT NULL OR n.snippet_storage_key IS NOT NULL
        RETURN DISTINCT coalesce(n.storage_key, n.snippet_storage_key) AS key
        """,
        id=project_id,
    )
    return [row["key"] for row in rows if row["key"]]
