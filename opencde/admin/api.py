# This file was generated with the assistance of an AI coding tool.
"""The JSON administration API, an extension outside the OpenCDE specifications.

What the administration pages show and do, for an administration client
such as Dataspatium: a bearer token holding the ``admin`` scope and an
administrator account (``AdminPrincipal``) reads the overview, users,
projects, clients, sessions, the audit log, the settings and the health
checks, and changes users, projects and their members, clients and their
secrets, and sessions. Lists answer ``{"items": [...], "total": n}`` with
``limit`` (200 by default, at most 1000) and ``q``/``since`` where they
apply. Errors use the Foundation body with a ``code``. Dangerous writes
(deleting, resetting passwords, rotating secrets, granting or dropping the
administrator role) need an authentication from the last ten minutes
(``FreshAdminPrincipal``: ``403 reauthentication_required`` otherwise), and
every write leaves an audit event with the caller, its client and the
request id. Agreed with Dataspatium in docs/dataspatium-coordination.md
(item 12).
"""

from __future__ import annotations

import secrets
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Path, Query, Request, Response
from pydantic import BaseModel, Field

from opencde import __version__, audit
from opencde.accounts.projects import Project
from opencde.accounts.roles import Role
from opencde.accounts.users import AccountError, User
from opencde.admin import queries
from opencde.admin.doctor import run_checks
from opencde.admin.routes_overview import SAFE_SETTINGS
from opencde.auth.clients import Client, ClientError
from opencde.auth.dependencies import AdminPrincipal, FreshAdminPrincipal, TokensDep, fresh_admin_principal
from opencde.auth.tokens import Principal
from opencde.deps import ClientsDep, GraphDep, ProjectsDep, SettingsDep, StorageDep, UsersDep, client_ip
from opencde.graph.driver import ping_within
from opencde.graph.graph import Graph
from opencde.web.sessions import WebSessionsDep

router = APIRouter(prefix="/admin/api", tags=["Administration (extension)"])

DEFAULT_LIMIT = 200
MAX_LIMIT = 1000
LimitQuery = Annotated[int, Query(ge=1, le=MAX_LIMIT, description="At most this many items (default 200)")]
SearchQuery = Annotated[str | None, Query(max_length=100, description="Substring of user name, name or e-mail")]
TypeQuery = Annotated[str | None, Query(max_length=64, description="Event type prefix, e.g. auth. or admin.user")]
SinceQuery = Annotated[str | None, Query(max_length=40, description="ISO 8601 UTC; items at or after it")]
IdPath = Annotated[str, Path(max_length=64)]

NO_CONTENT = Response(status_code=204)


# ---------------------------------------------------------------------------- shapes


def _listing(items: list[dict[str, Any]], total: int | None = None) -> dict[str, Any]:
    return {"items": items, "total": len(items) if total is None else total}


def _user(user: User, projects: int | None = None) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": user.id,
        "username": user.username,
        "full_name": user.full_name,
        "email": user.email,
        "is_admin": user.is_admin,
        "disabled": user.disabled,
        "must_change_password": user.must_change_password,
        "created_at": user.created_at,
        "last_sign_in_at": user.last_sign_in_at,
    }
    if projects is not None:
        data["projects"] = projects
    return data


def _project(project: Project, stats: dict[str, int] | None = None) -> dict[str, Any]:
    data: dict[str, Any] = {"project_id": project.project_id, "name": project.name, "created_at": project.created_at}
    if stats is not None:
        data.update(members=stats.get("members", 0), topics=stats.get("topics", 0), documents=stats.get("documents", 0))
    return data


def _client(client: Client) -> dict[str, Any]:
    return {
        "client_id": client.client_id,
        "name": client.name,
        "description": client.description,
        "url": client.url,
        "redirect_uris": list(client.redirect_uris),
        "is_public": client.is_public,
        "disabled": client.disabled,
        "created_at": client.created_at,
        "dynamic": client.dynamic,
        "expires_at": client.expires_at,
        "software_id": client.software_id,
        "software_version": client.software_version,
        "last_used_at": client.last_used_at,
    }


async def _record(request: Request, graph: Graph, principal: Principal, action: str, **details: Any) -> None:
    """Every write leaves an audit event: who, through which client, from where (the request id comes along)."""
    await audit.record(
        graph,
        f"admin.{action}",
        actor=principal.user_id,
        client_id=principal.client_id,
        ip=client_ip(request),
        details={key: value for key, value in details.items() if value is not None},
    )


def _bad_request(exc: Exception) -> HTTPException:
    return HTTPException(400, str(exc))


# ---------------------------------------------------------------------------- reads


@router.get("/overview", summary="Administration (extension): counts and the state of the database")
async def overview(principal: AdminPrincipal, graph: GraphDep, settings: SettingsDep) -> dict[str, Any]:
    reachable = await ping_within(graph.driver, graph.database, settings.graph_connect_timeout_seconds)
    counts = await queries.counts(graph) if reachable else {}
    return {"version": __version__, "dialect": graph.dialect.name.value, "graph_ok": reachable, "counts": counts}


@router.get("/users", summary="Administration (extension): users")
async def list_users(
    principal: AdminPrincipal,
    users: UsersDep,
    graph: GraphDep,
    q: SearchQuery = None,
    limit: LimitQuery = DEFAULT_LIMIT,
) -> dict[str, Any]:
    found = await users.search(query=q, limit=limit)
    memberships = await queries.membership_counts(graph)
    total = len(found) if q else await users.count()
    return _listing([_user(user, memberships.get(user.id, 0)) for user in found], total)


@router.get("/users/{user_id}", summary="Administration (extension): one user with project roles")
async def get_user(principal: AdminPrincipal, user_id: IdPath, users: UsersDep) -> dict[str, Any]:
    user = await users.get(user_id)
    if user is None:
        raise HTTPException(404, "No such user")
    data = _user(user)
    data["memberships"] = [
        {"project_id": project_id, "name": name, "role": role.value}
        for project_id, name, role in await users.memberships(user.id)
    ]
    return data


@router.get("/projects", summary="Administration (extension): projects with counts")
async def list_projects(principal: AdminPrincipal, projects: ProjectsDep, graph: GraphDep) -> dict[str, Any]:
    stats = await queries.project_stats(graph)
    return _listing([_project(project, stats.get(project.project_id, {})) for project in await projects.all()])


async def _project_detail(project: Project, projects: ProjectsDep, graph: Graph) -> dict[str, Any]:
    stats = await queries.project_stats(graph)
    data = _project(project, stats.get(project.project_id, {}))
    data["members"] = [
        {"user_id": user.id, "username": user.username, "full_name": user.full_name, "role": role.value}
        for user, role in await projects.members(project.project_id)
    ]
    data["extensions"] = await projects.extensions(project.project_id) or {}
    return data


@router.get("/projects/{project_id}", summary="Administration (extension): one project with members and extensions")
async def get_project(
    principal: AdminPrincipal, project_id: IdPath, projects: ProjectsDep, graph: GraphDep
) -> dict[str, Any]:
    project = await projects.get(project_id)
    if project is None:
        raise HTTPException(404, "No such project")
    return await _project_detail(project, projects, graph)


@router.get("/clients", summary="Administration (extension): OAuth2 clients")
async def list_clients(principal: AdminPrincipal, clients: ClientsDep) -> dict[str, Any]:
    return _listing([_client(client) for client in await clients.all()])


@router.get("/clients/{client_id}", summary="Administration (extension): one OAuth2 client")
async def get_client(principal: AdminPrincipal, client_id: IdPath, clients: ClientsDep) -> dict[str, Any]:
    client = await clients.get(client_id)
    if client is None:
        raise HTTPException(404, "No such client")
    return _client(client)


@router.get("/sessions", summary="Administration (extension): application and browser sessions")
async def list_sessions(
    principal: AdminPrincipal, graph: GraphDep, limit: LimitQuery = DEFAULT_LIMIT
) -> dict[str, Any]:
    families = [
        {
            "kind": "oauth2",
            "family_id": row["family_id"],
            "user_id": row["user_id"],
            "username": row["username"],
            "client_id": row["client_id"],
            "client_name": row["client_name"],
            "scope": row["scope"],
            "created_at": row["created_at"],
            "expires_at": row["expires_at"],
        }
        for row in await queries.active_families(graph, limit=limit)
    ]
    browsers = [
        {
            "kind": "web",
            "id": row["id"],
            "user_id": row["user_id"],
            "username": row["username"],
            "created_at": row["created_at"],
            "expires_at": row["expires_at"],
            "idle_expires_at": row["idle_expires_at"],
            "ip": row.get("ip"),
        }
        for row in await queries.web_sessions(graph, limit=limit)
    ]
    items = sorted(families + browsers, key=lambda item: str(item["created_at"]), reverse=True)[:limit]
    return _listing(items, len(families) + len(browsers))


@router.get("/audit", summary="Administration (extension): the audit log")
async def list_audit(
    principal: AdminPrincipal,
    graph: GraphDep,
    type: TypeQuery = None,
    since: SinceQuery = None,
    limit: LimitQuery = DEFAULT_LIMIT,
) -> dict[str, Any]:
    events = await audit.recent(graph, limit=limit, type_prefix=(type or "").strip() or None, since=since)
    items = [
        {
            "id": event.get("id"),
            "at": event.get("at"),
            "type": event.get("type"),
            "actor": event.get("actor_user_id"),
            "client_id": event.get("client_id"),
            "ip": event.get("ip"),
            "request_id": event.get("request_id"),
            "details": event.get("details") or {},
        }
        for event in events
    ]
    return _listing(items)


@router.get("/settings", summary="Administration (extension): the configuration, secrets left out")
async def get_settings(principal: AdminPrincipal, settings: SettingsDep) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for name in SAFE_SETTINGS:
        value = getattr(settings, name)
        values[f"OPENCDE_{name.upper()}"] = value.value if hasattr(value, "value") else value
    return {"settings": values}


@router.get("/health", summary="Administration (extension): the health checks of the settings page")
async def get_health(
    principal: AdminPrincipal, settings: SettingsDep, graph: GraphDep, storage: StorageDep
) -> dict[str, Any]:
    checks = await run_checks(settings, graph, storage)
    items = [{"name": check.name, "ok": check.ok, "detail": check.detail} for check in checks]
    return {"ok": all(check.ok for check in checks), "items": items, "total": len(items)}


# ---------------------------------------------------------------------------- writes: users


class UserCreate(BaseModel):
    username: str = Field(max_length=128)
    password: str | None = Field(None, max_length=256, description="Omit to have one generated and returned once")
    full_name: str | None = Field(None, max_length=200)
    email: str | None = Field(None, max_length=200)
    is_admin: bool = False
    must_change_password: bool = True


class UserUpdate(BaseModel):
    full_name: str | None = Field(None, max_length=200)
    email: str | None = Field(None, max_length=200)
    disabled: bool | None = None
    is_admin: bool | None = None


class MemberBody(BaseModel):
    role: str = Field(max_length=32, description="viewer, contributor, editor or manager")


def _generated_password() -> str:
    return secrets.token_urlsafe(12)


@router.post("/users", status_code=201, summary="Administration (extension): create a user")
async def create_user(
    request: Request, principal: AdminPrincipal, body: UserCreate, users: UsersDep, graph: GraphDep
) -> dict[str, Any]:
    if body.is_admin:
        fresh_admin_principal(principal)  # granting the administrator role is dangerous
    generated = body.password is None
    password = body.password or _generated_password()
    try:
        user = await users.create(
            body.username,
            password,
            email=body.email,
            full_name=body.full_name,
            is_admin=body.is_admin,
            must_change_password=body.must_change_password,
        )
    except AccountError as exc:
        raise _bad_request(exc) from None
    await _record(request, graph, principal, "user.create", user_id=user.id, is_admin=user.is_admin)
    data = _user(user, 0)
    if generated:
        data["password"] = password  # shown once; the server keeps only the hash
    return data


@router.patch("/users/{user_id}", summary="Administration (extension): change a user")
async def update_user(
    request: Request,
    principal: AdminPrincipal,
    user_id: IdPath,
    body: UserUpdate,
    users: UsersDep,
    tokens: TokensDep,
    graph: GraphDep,
) -> dict[str, Any]:
    user = await users.get(user_id)
    if user is None:
        raise HTTPException(404, "No such user")
    is_self = user.id == principal.user_id
    if is_self and (body.disabled or body.is_admin is False):
        raise HTTPException(400, "You cannot disable your own account or drop your own administrator role")
    if body.is_admin is not None and body.is_admin != user.is_admin:
        fresh_admin_principal(principal)
    try:
        updated = await users.update(
            user.id, email=body.email, full_name=body.full_name, is_admin=body.is_admin, disabled=body.disabled
        )
    except AccountError as exc:
        raise _bad_request(exc) from None
    if body.disabled and not user.disabled:
        await tokens.revoke_all_for_user(user.id)
    await _record(
        request, graph, principal, "user.update", user_id=user.id, is_admin=body.is_admin, disabled=body.disabled
    )
    return _user(updated)


@router.delete("/users/{user_id}", status_code=204, summary="Administration (extension): delete a user")
async def delete_user(
    request: Request,
    principal: FreshAdminPrincipal,
    user_id: IdPath,
    users: UsersDep,
    tokens: TokensDep,
    sessions: WebSessionsDep,
    graph: GraphDep,
) -> Response:
    user = await users.get(user_id)
    if user is None:
        raise HTTPException(404, "No such user")
    if user.id == principal.user_id:
        raise HTTPException(400, "You cannot delete your own account")
    await tokens.revoke_all_for_user(user.id)
    await sessions.delete_for_user(user.id)
    await users.delete(user.id)
    await _record(request, graph, principal, "user.delete", user_id=user.id, username=user.username)
    return NO_CONTENT


@router.post("/users/{user_id}/password", summary="Administration (extension): reset a password, shown once")
async def reset_password(
    request: Request,
    principal: FreshAdminPrincipal,
    user_id: IdPath,
    users: UsersDep,
    tokens: TokensDep,
    sessions: WebSessionsDep,
    graph: GraphDep,
) -> dict[str, Any]:
    user = await users.get(user_id)
    if user is None:
        raise HTTPException(404, "No such user")
    password = _generated_password()
    await users.set_password(user.id, password, must_change=True)
    await tokens.revoke_all_for_user(user.id)
    await sessions.delete_for_user(user.id)
    await _record(request, graph, principal, "user.reset_password", user_id=user.id)
    return {"id": user.id, "username": user.username, "password": password, "must_change_password": True}


@router.post("/users/{user_id}/revoke", status_code=204, summary="Administration (extension): end a user's sessions")
async def revoke_user(
    request: Request,
    principal: AdminPrincipal,
    user_id: IdPath,
    users: UsersDep,
    tokens: TokensDep,
    sessions: WebSessionsDep,
    graph: GraphDep,
) -> Response:
    user = await users.get(user_id)
    if user is None:
        raise HTTPException(404, "No such user")
    await tokens.revoke_all_for_user(user.id)
    await sessions.delete_for_user(user.id)
    await _record(request, graph, principal, "user.revoke_sessions", user_id=user.id)
    return NO_CONTENT


# ---------------------------------------------------------------------------- writes: projects and members


class ProjectCreate(BaseModel):
    name: str = Field(max_length=200)
    extensions: dict[str, list[str]] | None = None


class ProjectUpdate(BaseModel):
    name: str | None = Field(None, max_length=200)
    extensions: dict[str, list[str]] | None = None


@router.post("/projects", status_code=201, summary="Administration (extension): create a project")
async def create_project(
    request: Request, principal: AdminPrincipal, body: ProjectCreate, projects: ProjectsDep, graph: GraphDep
) -> dict[str, Any]:
    try:
        project = await projects.create(body.name, extensions=body.extensions)
    except AccountError as exc:
        raise _bad_request(exc) from None
    await _record(request, graph, principal, "project.create", project_id=project.project_id, name=project.name)
    return await _project_detail(project, projects, graph)


@router.patch("/projects/{project_id}", summary="Administration (extension): rename a project or set its extensions")
async def update_project(
    request: Request,
    principal: AdminPrincipal,
    project_id: IdPath,
    body: ProjectUpdate,
    projects: ProjectsDep,
    graph: GraphDep,
) -> dict[str, Any]:
    project = await projects.get(project_id)
    if project is None:
        raise HTTPException(404, "No such project")
    try:
        if body.name is not None:
            project = await projects.rename(project.project_id, body.name)
        if body.extensions is not None:
            await projects.set_extensions(project.project_id, body.extensions)
    except AccountError as exc:
        raise _bad_request(exc) from None
    await _record(
        request,
        graph,
        principal,
        "project.update",
        project_id=project.project_id,
        name=body.name,
        extensions=sorted(body.extensions) if body.extensions else None,
    )
    return await _project_detail(project, projects, graph)


@router.delete("/projects/{project_id}", status_code=204, summary="Administration (extension): delete a project")
async def delete_project(
    request: Request, principal: FreshAdminPrincipal, project_id: IdPath, projects: ProjectsDep, graph: GraphDep
) -> Response:
    project = await projects.get(project_id)
    if project is None:
        raise HTTPException(404, "No such project")
    await projects.delete(project.project_id)
    await _record(request, graph, principal, "project.delete", project_id=project.project_id, name=project.name)
    return NO_CONTENT


@router.put("/projects/{project_id}/members/{user_id}", summary="Administration (extension): set a member's role")
async def set_member(
    request: Request,
    principal: AdminPrincipal,
    project_id: IdPath,
    user_id: IdPath,
    body: MemberBody,
    projects: ProjectsDep,
    users: UsersDep,
    graph: GraphDep,
) -> dict[str, Any]:
    if await projects.get(project_id) is None:
        raise HTTPException(404, "No such project")
    if await users.get(user_id) is None:
        raise HTTPException(404, "No such user")
    try:
        role = Role(body.role)
    except ValueError:
        raise HTTPException(400, "role must be viewer, contributor, editor or manager") from None
    try:
        await projects.set_member(project_id, user_id, role)
    except AccountError as exc:
        raise _bad_request(exc) from None
    await _record(request, graph, principal, "membership.set", user_id=user_id, project_id=project_id, role=role.value)
    return {"user_id": user_id, "role": role.value}


@router.delete(
    "/projects/{project_id}/members/{user_id}", status_code=204, summary="Administration (extension): remove a member"
)
async def remove_member(
    request: Request,
    principal: AdminPrincipal,
    project_id: IdPath,
    user_id: IdPath,
    projects: ProjectsDep,
    graph: GraphDep,
) -> Response:
    if not await projects.remove_member(project_id, user_id):
        raise HTTPException(404, "No such membership")
    await _record(request, graph, principal, "membership.remove", user_id=user_id, project_id=project_id)
    return NO_CONTENT


# ---------------------------------------------------------------------------- writes: clients


class ClientCreate(BaseModel):
    name: str = Field(max_length=200)
    redirect_uris: list[str] = Field(max_length=10)
    public: bool = True
    description: str | None = Field(None, max_length=1000)
    url: str | None = Field(None, max_length=2000)


class ClientUpdate(BaseModel):
    name: str | None = Field(None, max_length=200)
    description: str | None = Field(None, max_length=1000)
    url: str | None = Field(None, max_length=2000)
    redirect_uris: list[str] | None = Field(None, max_length=10)
    disabled: bool | None = None


@router.post("/clients", status_code=201, summary="Administration (extension): register a client")
async def create_client(
    request: Request, principal: AdminPrincipal, body: ClientCreate, clients: ClientsDep, graph: GraphDep
) -> dict[str, Any]:
    try:
        client, secret = await clients.create(
            body.name,
            body.redirect_uris,
            public=body.public,
            description=body.description,
            url=body.url,
            created_by=principal.user_id,
        )
    except ClientError as exc:
        raise _bad_request(exc) from None
    await _record(request, graph, principal, "client.create", client_id=client.client_id, public=body.public)
    data = _client(client)
    if secret:
        data["client_secret"] = secret  # shown once
    return data


@router.patch("/clients/{client_id}", summary="Administration (extension): change a client")
async def update_client(
    request: Request,
    principal: AdminPrincipal,
    client_id: IdPath,
    body: ClientUpdate,
    clients: ClientsDep,
    tokens: TokensDep,
    graph: GraphDep,
) -> dict[str, Any]:
    client = await clients.get(client_id)
    if client is None:
        raise HTTPException(404, "No such client")
    try:
        updated = await clients.update(
            client.client_id,
            name=body.name,
            description=body.description,
            url=body.url,
            redirect_uris=body.redirect_uris,
            disabled=body.disabled,
        )
    except ClientError as exc:
        raise _bad_request(exc) from None
    if body.disabled and not client.disabled:
        await tokens.revoke_all_for_client(client.client_id)
    await _record(request, graph, principal, "client.update", client_id=client.client_id, disabled=body.disabled)
    return _client(updated)


@router.post("/clients/{client_id}/secret", summary="Administration (extension): rotate a client secret, shown once")
async def rotate_client_secret(
    request: Request, principal: FreshAdminPrincipal, client_id: IdPath, clients: ClientsDep, graph: GraphDep
) -> dict[str, Any]:
    client = await clients.get(client_id)
    if client is None:
        raise HTTPException(404, "No such client")
    try:
        secret = await clients.rotate_secret(client.client_id)
    except ClientError as exc:
        raise _bad_request(exc) from None
    await _record(request, graph, principal, "client.rotate_secret", client_id=client.client_id)
    return {"client_id": client.client_id, "client_secret": secret}


@router.post("/clients/{client_id}/revoke", status_code=204, summary="Administration (extension): revoke all tokens")
async def revoke_client(
    request: Request,
    principal: AdminPrincipal,
    client_id: IdPath,
    clients: ClientsDep,
    tokens: TokensDep,
    graph: GraphDep,
) -> Response:
    client = await clients.get(client_id)
    if client is None:
        raise HTTPException(404, "No such client")
    await tokens.revoke_all_for_client(client.client_id)
    await _record(request, graph, principal, "client.revoke_tokens", client_id=client.client_id)
    return NO_CONTENT


@router.delete("/clients/{client_id}", status_code=204, summary="Administration (extension): delete a client")
async def delete_client(
    request: Request, principal: FreshAdminPrincipal, client_id: IdPath, clients: ClientsDep, graph: GraphDep
) -> Response:
    client = await clients.get(client_id)
    if client is None:
        raise HTTPException(404, "No such client")
    await clients.delete(client.client_id)
    await _record(request, graph, principal, "client.delete", client_id=client.client_id, name=client.name)
    return NO_CONTENT


# ---------------------------------------------------------------------------- writes: sessions


@router.delete(
    "/sessions/oauth2/{family_id}", status_code=204, summary="Administration (extension): end an app session"
)
async def revoke_family(
    request: Request,
    principal: AdminPrincipal,
    family_id: IdPath,
    tokens: TokensDep,
    graph: GraphDep,
    user_id: Annotated[str, Query(max_length=64, description="The user of the session, as the listing shows")],
) -> Response:
    if not await tokens.revoke_family(family_id, user_id=user_id):
        raise HTTPException(404, "No such session")
    await _record(request, graph, principal, "session.revoke_family", user_id=user_id, family_id=family_id)
    return NO_CONTENT


@router.delete(
    "/sessions/web/{session_id}", status_code=204, summary="Administration (extension): end a browser session"
)
async def revoke_web_session(
    request: Request, principal: AdminPrincipal, session_id: IdPath, graph: GraphDep
) -> Response:
    if not await queries.delete_web_session(graph, session_id):
        raise HTTPException(404, "No such session")
    await _record(request, graph, principal, "session.revoke_web", session_id=session_id)
    return NO_CONTENT
