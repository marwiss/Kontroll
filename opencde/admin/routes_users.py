# This file was generated with the assistance of an AI coding tool.
"""Admin pages for users: list, create, edit, project roles, password reset, sessions, deletion."""

from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import APIRouter, Path, Query, Request
from fastapi.responses import Response

from opencde.accounts.projects import ProjectRepository
from opencde.accounts.roles import Role
from opencde.accounts.users import AccountError, User, UserRepository
from opencde.admin import queries
from opencde.admin.access import (
    AdminDep,
    AdminForm,
    admin_context,
    flag,
    not_found,
    password_confirmed,
    redirect_with_notice,
    text,
)
from opencde.auth.dependencies import TokensDep
from opencde.deps import GraphDep, ProjectsDep, UsersDep
from opencde.ids import is_uuid
from opencde.ui.i18n import tr
from opencde.ui.templating import render

router = APIRouter(prefix="/admin/users", include_in_schema=False)

UserId = Annotated[str, Path(alias="user_id", max_length=64)]
ROLES = [role.value for role in Role]


def generated_password() -> str:
    return secrets.token_urlsafe(18)


async def _user_page(
    request: Request,
    admin: AdminDep,
    user: User,
    users: UserRepository,
    projects: ProjectRepository,
    graph: GraphDep,
    error: str | None = None,
    status_code: int = 200,
) -> Response:
    form = AdminForm(request, admin, "admin-user", user.id)
    memberships = await users.memberships(user.id)
    member_of = {project_id for project_id, _, _ in memberships}
    return render(
        request,
        "admin/user.html",
        admin_context(
            request,
            admin,
            "users",
            user=user,
            memberships=memberships,
            other_projects=[p for p in await projects.all() if p.project_id not in member_of],
            roles=ROLES,
            web_sessions=await queries.web_sessions(graph, user.id),
            form_token=form.token(),
            is_self=user.id == admin.user.id,
            error=error,
        ),
        status_code=status_code,
    )


@router.get("")
async def users_list(
    request: Request, admin: AdminDep, users: UsersDep, graph: GraphDep, q: str | None = Query(None, max_length=100)
) -> Response:
    found = await users.search(query=(q or "").strip() or None)
    return render(
        request,
        "admin/users.html",
        admin_context(
            request, admin, "users", users=found, q=q or "", memberships=await queries.membership_counts(graph)
        ),
    )


@router.get("/new")
async def user_new(request: Request, admin: AdminDep) -> Response:
    form = AdminForm(request, admin, "admin-user-new")
    return render(
        request, "admin/user_new.html", admin_context(request, admin, "users", form_token=form.token(), error=None)
    )


@router.post("")
async def user_create(request: Request, admin: AdminDep, users: UsersDep, graph: GraphDep) -> Response:
    form = AdminForm(request, admin, "admin-user-new")
    data = await request.form()
    if not form.check(data.get("form_token")):
        return redirect_with_notice("/admin/users/new", "form_expired")
    password = text(data, "password", max_length=256)
    generated = not password
    if generated:
        password = generated_password()
    try:
        user = await users.create(
            text(data, "username", max_length=128),
            password,
            email=text(data, "email", max_length=200) or None,
            full_name=text(data, "full_name", max_length=200) or None,
            is_admin=flag(data, "is_admin"),
            must_change_password=flag(data, "must_change_password") or generated,
        )
    except AccountError as exc:
        return render(
            request,
            "admin/user_new.html",
            admin_context(request, admin, "users", form_token=form.token(), error=str(exc)),
            status_code=400,
        )
    await form.record(graph, "user.create", user_id=user.id, is_admin=user.is_admin)
    if generated:
        return render(
            request,
            "admin/secret.html",
            admin_context(
                request,
                admin,
                "users",
                title=tr(request, "admin.secret.password_for", user=user.username),
                lead=tr(request, "admin.secret.password_lead"),
                secret=password,
                back_url=f"/admin/users/{user.id}",
                back_text=tr(request, "admin.secret.open_user"),
            ),
        )
    return redirect_with_notice(f"/admin/users/{user.id}", "created")


@router.get("/{user_id}")
async def user_page(
    request: Request, admin: AdminDep, user_id: UserId, users: UsersDep, projects: ProjectsDep, graph: GraphDep
) -> Response:
    user = await users.get(user_id) if is_uuid(user_id) else None
    if user is None:
        raise not_found()
    return await _user_page(request, admin, user, users, projects, graph)


@router.post("/{user_id}")
async def user_action(
    request: Request,
    admin: AdminDep,
    user_id: UserId,
    users: UsersDep,
    projects: ProjectsDep,
    tokens: TokensDep,
    graph: GraphDep,
) -> Response:
    user = await users.get(user_id) if is_uuid(user_id) else None
    if user is None:
        raise not_found()
    form = AdminForm(request, admin, "admin-user", user.id)
    data = await request.form()
    page = f"/admin/users/{user.id}"
    if not form.check(data.get("form_token")):
        return redirect_with_notice(page, "form_expired")
    action = text(data, "action", max_length=32)
    is_self = user.id == admin.user.id

    if action == "update":
        wants_admin = flag(data, "is_admin")
        disabled = flag(data, "disabled")
        if is_self and (not wants_admin or disabled):
            return redirect_with_notice(page, "not_yourself")
        if wants_admin != user.is_admin and not await password_confirmed(users, admin, data.get("confirm_password")):
            return redirect_with_notice(page, "wrong_password")
        await users.update(
            user.id,
            full_name=text(data, "full_name", max_length=200) or None,
            email=text(data, "email", max_length=200) or None,
            is_admin=wants_admin,
            disabled=disabled,
        )
        if disabled and not user.disabled:
            await tokens.revoke_all_for_user(user.id)
        await form.record(graph, "user.update", user_id=user.id, is_admin=wants_admin, disabled=disabled)
        return redirect_with_notice(page, "saved")

    if action == "membership":
        project_id, role = text(data, "project_id", max_length=64), text(data, "role", max_length=32)
        if role not in ROLES or not is_uuid(project_id):
            return redirect_with_notice(page, "invalid")
        try:
            await projects.set_member(project_id, user.id, Role(role))
        except AccountError:
            return redirect_with_notice(page, "invalid")
        await form.record(graph, "membership.set", user_id=user.id, project_id=project_id, role=role)
        return redirect_with_notice(page, "member_saved")

    if action == "remove_membership":
        project_id = text(data, "project_id", max_length=64)
        if is_uuid(project_id):
            await projects.remove_member(project_id, user.id)
            await form.record(graph, "membership.remove", user_id=user.id, project_id=project_id)
        return redirect_with_notice(page, "member_removed")

    if action == "reset_password":
        if not await password_confirmed(users, admin, data.get("confirm_password")):
            return redirect_with_notice(page, "wrong_password")
        password = generated_password()
        await users.set_password(user.id, password, must_change=True)
        await tokens.revoke_all_for_user(user.id)
        await form.record(graph, "user.reset_password", user_id=user.id)
        return render(
            request,
            "admin/secret.html",
            admin_context(
                request,
                admin,
                "users",
                title=tr(request, "admin.secret.new_password_for", user=user.username),
                lead=tr(request, "admin.secret.new_password_lead"),
                secret=password,
                back_url=page,
                back_text=tr(request, "admin.secret.back_user"),
            ),
        )

    if action == "revoke_sessions":
        await tokens.revoke_all_for_user(user.id)
        await form.record(graph, "user.revoke_sessions", user_id=user.id)
        return redirect_with_notice(page, "revoked")

    if action == "delete":
        if is_self:
            return redirect_with_notice(page, "not_yourself")
        if not await password_confirmed(users, admin, data.get("confirm_password")):
            return redirect_with_notice(page, "wrong_password")
        await tokens.revoke_all_for_user(user.id)
        await users.delete(user.id)
        await form.record(graph, "user.delete", user_id=user.id, username=user.username)
        return redirect_with_notice("/admin/users", "deleted")

    return redirect_with_notice(page, "invalid")
