# This file was generated with the assistance of an AI coding tool.
"""The JSON administration API, an extension outside the OpenCDE specifications.

What the administration pages show and do, for an administration client
such as Dataspatium: a bearer token holding the ``admin`` scope and an
administrator account (``AdminPrincipal``) reads the overview, users,
projects, clients, sessions, the audit log, the settings and the health
checks, and changes users, projects and their members, clients and their
secrets, and sessions. Lists answer ``{"items": [...], "total": n}`` with
``limit`` (200 by default, at most 1000) and ``q``, ``user`` or ``since``
where they apply. Errors use the Foundation body with a ``code``, like the
rest of the server. Dangerous writes (deleting, resetting passwords, rotating
secrets, granting or dropping the administrator role) need an authentication
from the last ten minutes (``FreshAdminPrincipal``: ``403
reauthentication_required`` otherwise), one-time values (an initial
password, a client secret) are returned exactly once, and every write
leaves an audit event with the caller, its client and the request id. The
resource shapes were agreed with Dataspatium
(docs/dataspatium-coordination.md, "The administration API"; docs/en/client-guide.md §7).
"""

from __future__ import annotations

import secrets
import time
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
from opencde.auth.clients import MAX_DESCRIPTION, Client, ClientError
from opencde.auth.dependencies import AdminPrincipal, FreshAdminPrincipal, TokensDep, fresh_admin_principal
from opencde.auth.tokens import Principal
from opencde.deps import ClientsDep, GraphDep, ProjectsDep, SettingsDep, StorageDep, UsersDep, client_ip
from opencde.graph.driver import ping_within
from opencde.graph.graph import Graph
from opencde.settings import Settings, env_name
from opencde.web.sessions import WebSessionsDep

router = APIRouter(prefix="/admin/api", tags=["Administration (extension)"])

DEFAULT_LIMIT = 200
MAX_LIMIT = 1000
LimitQuery = Annotated[int, Query(ge=1, le=MAX_LIMIT, description="At most this many items (default 200)")]
SearchQuery = Annotated[str | None, Query(max_length=100, description="Substring to search for")]
UserQuery = Annotated[str | None, Query(max_length=128, description="A user id or user name")]
TypeQuery = Annotated[str | None, Query(max_length=64, description="Event type prefix, e.g. auth. or admin.user")]
SinceQuery = Annotated[str | None, Query(max_length=40, description="ISO 8601 UTC; items at or after it")]
IdPath = Annotated[str, Path(max_length=64)]

NO_CONTENT = Response(status_code=204)


# ---------------------------------------------------------------------------- shapes


def _listing(items: list[dict[str, Any]], total: int | None = None) -> dict[str, Any]:
    return {"items": items, "total": len(items) if total is None else total}


def _user(user: User, projects: list[dict[str, str]] | None = None) -> dict[str, Any]:
    return {
        "id": user.id,
        "username": user.username,
        "name": user.full_name,
        "email": user.email,
        "is_admin": user.is_admin,
        "disabled": user.disabled,
        "must_change_password": user.must_change_password,
        "created_at": user.created_at,
        "last_sign_in_at": user.last_sign_in_at,
        "projects": projects or [],
    }


def _project(project: Project, stats: dict[str, int], members: list[dict[str, str]], models: int) -> dict[str, Any]:
    return {
        "project_id": project.project_id,
        "name": project.name,
        "created_at": project.created_at,
        "members": members,
        "topics": stats.get("topics", 0),
        "documents": stats.get("documents", 0),
        "models": models,
    }


def _client(client: Client) -> dict[str, Any]:
    return {
        "client_id": client.client_id,
        "name": client.name,
        "description": client.description,
        "url": client.url,
        "public": client.is_public,
        "dynamic": client.dynamic,
        "redirect_uris": list(client.redirect_uris),
        "disabled": client.disabled,
        "pending": client.pending,
        "created_at": client.created_at,
        "expires_at": client.expires_at,
        "last_used_at": client.last_used_at,
        "software_id": client.software_id,
        "software_version": client.software_version,
        "pkce_optional": client.pkce_optional,
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


@router.get("/overview", summary="Administration (extension): counts and the state of the server")
async def overview(
    request: Request, principal: AdminPrincipal, graph: GraphDep, settings: SettingsDep
) -> dict[str, Any]:
    reachable = await ping_within(graph.driver, graph.database, settings.graph_connect_timeout_seconds)
    counts = await queries.counts(graph) if reachable else {}
    models = (await queries.model_counts(graph)).get("", 0) if reachable else 0
    rows = await queries.request_log_rows(graph) if reachable else 0
    started = getattr(request.app.state, "started_at", None)
    return {
        "version": __version__,
        "uptime_s": int(time.monotonic() - started) if started is not None else None,
        "dialect": graph.dialect.name.value,
        "graph_ok": reachable,
        "users": counts.get("users", 0),
        "projects": counts.get("projects", 0),
        "clients": counts.get("clients", 0),
        "sessions": counts.get("sessions", 0),
        "topics": counts.get("topics", 0),
        "documents": counts.get("documents", 0) + counts.get("bcf_documents", 0),
        "models": models,
        "request_log": {"enabled": settings.request_log_enabled, "rows": rows},
    }


@router.get("/users", summary="Administration (extension): users with their project roles")
async def list_users(
    principal: AdminPrincipal,
    users: UsersDep,
    graph: GraphDep,
    q: SearchQuery = None,
    limit: LimitQuery = DEFAULT_LIMIT,
) -> dict[str, Any]:
    found = await users.search(query=q, limit=limit)
    memberships = await queries.memberships_by_user(graph)
    total = len(found) if q else await users.count()
    return _listing([_user(user, memberships.get(user.id)) for user in found], total)


@router.get("/users/{user_id}", summary="Administration (extension): one user with project roles")
async def get_user(principal: AdminPrincipal, user_id: IdPath, users: UsersDep) -> dict[str, Any]:
    user = await users.get(user_id)
    if user is None:
        raise HTTPException(404, "No such user")
    return _user(
        user,
        [
            {"project_id": project_id, "name": name, "role": role.value}
            for project_id, name, role in await users.memberships(user.id)
        ],
    )


async def _project_rows(projects: ProjectsDep, graph: Graph, selection: list[Project]) -> list[dict[str, Any]]:
    stats = await queries.project_stats(graph)
    members = await queries.members_by_project(graph)
    models = await queries.model_counts(graph)
    return [
        _project(
            project,
            stats.get(project.project_id, {}),
            members.get(project.project_id, []),
            models.get(project.project_id, 0),
        )
        for project in selection
    ]


@router.get("/projects", summary="Administration (extension): projects with members and counts")
async def list_projects(
    principal: AdminPrincipal, projects: ProjectsDep, graph: GraphDep, q: SearchQuery = None
) -> dict[str, Any]:
    selection = [p for p in await projects.all() if not q or q.lower() in p.name.lower()]
    return _listing(await _project_rows(projects, graph, selection))


async def _project_detail(project: Project, projects: ProjectsDep, graph: Graph) -> dict[str, Any]:
    data = (await _project_rows(projects, graph, [project]))[0]
    data["extensions"] = await projects.extensions(project.project_id) or {}
    return data


@router.get("/projects/{project_id}", summary="Administration (extension): one project with its extensions")
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


def _session_rows(families: list[dict[str, Any]], browsers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = [
        {
            "kind": "oauth2",
            "id": row["family_id"],
            "user_id": row["user_id"],
            "username": row["username"],
            "client_id": row["client_id"],
            "client_name": row["client_name"],
            "scope": row["scope"],
            "created_at": row["created_at"],
            "expires_at": row["expires_at"],
            "ip": None,
            "user_agent": None,
        }
        for row in families
    ] + [
        {
            "kind": "web",
            "id": row["id"],
            "user_id": row["user_id"],
            "username": row["username"],
            "client_id": None,
            "client_name": None,
            "scope": None,
            "created_at": row["created_at"],
            "expires_at": row["idle_expires_at"],
            "ip": row.get("ip"),
            "user_agent": None,
        }
        for row in browsers
    ]
    return sorted(rows, key=lambda item: str(item["created_at"]), reverse=True)


@router.get("/sessions", summary="Administration (extension): application and browser sessions")
async def list_sessions(
    principal: AdminPrincipal, graph: GraphDep, user: UserQuery = None, limit: LimitQuery = DEFAULT_LIMIT
) -> dict[str, Any]:
    rows = _session_rows(
        await queries.active_families(graph, limit=limit), await queries.web_sessions(graph, limit=limit)
    )
    if user:
        rows = [row for row in rows if user in (row["user_id"], row["username"])]
    return _listing(rows[:limit], len(rows))


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


def _settings_payload(settings: Settings) -> dict[str, Any]:
    raw: dict[str, Any] = {}
    for name in SAFE_SETTINGS:
        value = getattr(settings, name)
        raw[env_name(name)] = value.value if hasattr(value, "value") else value
    modules = [
        name
        for name, enabled in (
            ("admin_ui", settings.admin_ui_enabled),
            ("admin_api", settings.admin_api_enabled),
            ("api_docs", settings.api_docs_on),
            ("dynamic_client_registration", settings.dynamic_client_registration),
            ("request_log", settings.request_log_enabled),
            ("ifcgraph", settings.ifcgraph_enabled),
        )
        if enabled
    ]
    return {
        "public_url": settings.public_url,
        "environment": settings.environment,
        "apis": list(settings.apis),
        "dynamic_client_registration": settings.dynamic_client_registration,
        "request_log": {
            "enabled": settings.request_log_enabled,
            "retention_hours": settings.request_log_retention_hours,
        },
        "ifcgraph": {
            "enabled": settings.ifcgraph_enabled,
            "timeout_seconds": settings.ifcgraph_timeout_seconds,
            "memory_mb": settings.ifcgraph_memory_mb,
            "max_entities": settings.ifcgraph_max_entities,
            "include_geometry": settings.ifcgraph_include_geometry,
            "gtin_property_set": settings.ifcgraph_gtin_property_set,
            "gtin_property": settings.ifcgraph_gtin_property,
        },
        "cors_origins": list(settings.cors_origins),
        "dataspatium_url": settings.dataspatium_url,
        "graph_public_bolt_url": settings.graph_public_bolt_url,
        "modules": modules,
        "raw": raw,
    }


@router.get("/settings", summary="Administration (extension): the configuration, secrets left out")
async def get_settings(principal: AdminPrincipal, settings: SettingsDep) -> dict[str, Any]:
    return _settings_payload(settings)


@router.get("/health", summary="Administration (extension): the health checks of the settings page")
async def get_health(
    principal: AdminPrincipal, settings: SettingsDep, graph: GraphDep, storage: StorageDep
) -> dict[str, Any]:
    checks = [{"name": c.name, "ok": c.ok, "detail": c.detail} for c in await run_checks(settings, graph, storage)]
    return {"ok": all(check["ok"] for check in checks), "checks": checks, "total": len(checks)}


# ---------------------------------------------------------------------------- writes: users


class UserCreate(BaseModel):
    username: str = Field(max_length=128)
    password: str | None = Field(None, max_length=256, description="Omit to have one generated and returned once")
    name: str | None = Field(None, max_length=200, description="Full name")
    full_name: str | None = Field(None, max_length=200, description="Alias of name")
    email: str | None = Field(None, max_length=200)
    is_admin: bool = False
    must_change_password: bool = True


class UserUpdate(BaseModel):
    name: str | None = Field(None, max_length=200)
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
            full_name=body.name or body.full_name,
            is_admin=body.is_admin,
            must_change_password=body.must_change_password,
        )
    except AccountError as exc:
        raise _bad_request(exc) from None
    await _record(request, graph, principal, "user.create", user_id=user.id, is_admin=user.is_admin)
    data = _user(user)
    if generated:
        data["initial_password"] = password  # returned once; the server keeps only the hash
    return data


async def _update_user(
    request: Request,
    principal: Principal,
    user_id: str,
    body: UserUpdate,
    users: UsersDep,
    tokens: TokensDep,
    graph: Graph,
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
            user.id,
            email=body.email,
            full_name=body.name or body.full_name,
            is_admin=body.is_admin,
            disabled=body.disabled,
        )
    except AccountError as exc:
        raise _bad_request(exc) from None
    if body.disabled and not user.disabled:
        await tokens.revoke_all_for_user(user.id)
    await _record(
        request, graph, principal, "user.update", user_id=user.id, is_admin=body.is_admin, disabled=body.disabled
    )
    return _user(updated)


@router.put("/users/{user_id}", summary="Administration (extension): change a user")
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
    return await _update_user(request, principal, user_id, body, users, tokens, graph)


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


@router.post("/users/{user_id}/reset-password", summary="Administration (extension): reset a password, returned once")
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
    reset = {"id": user.id, "username": user.username, "must_change_password": True}  # nosec B105  # a flag
    reset["password"] = password  # generated above and returned once; the server keeps only the hash
    return reset


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


@router.put("/projects/{project_id}", summary="Administration (extension): rename a project or set its extensions")
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
    request: Request,
    principal: FreshAdminPrincipal,
    project_id: IdPath,
    projects: ProjectsDep,
    graph: GraphDep,
    storage: StorageDep,
) -> Response:
    """The project, what it owns and its stored files. Its members stay, and so do their other projects."""
    project = await projects.get(project_id)
    if project is None:
        raise HTTPException(404, "No such project")
    await projects.delete_with_files(project.project_id, storage)
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
    description: str | None = Field(None, max_length=MAX_DESCRIPTION)
    url: str | None = Field(None, max_length=2000)
    pkce_optional: bool = False


class ClientUpdate(BaseModel):
    name: str | None = Field(None, max_length=200)
    description: str | None = Field(None, max_length=MAX_DESCRIPTION)
    url: str | None = Field(None, max_length=2000)
    redirect_uris: list[str] | None = Field(None, max_length=10)
    disabled: bool | None = None
    pkce_optional: bool | None = None


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
            pkce_optional=body.pkce_optional,
        )
    except ClientError as exc:
        raise _bad_request(exc) from None
    await _record(request, graph, principal, "client.create", client_id=client.client_id, public=body.public)
    data = _client(client)
    if secret:
        data["client_secret"] = secret  # returned once
    return data


@router.put("/clients/{client_id}", summary="Administration (extension): change a client")
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
            pkce_optional=body.pkce_optional,
        )
    except ClientError as exc:
        raise _bad_request(exc) from None
    if body.disabled and not client.disabled:
        await tokens.revoke_all_for_client(client.client_id)
    await _record(request, graph, principal, "client.update", client_id=client.client_id, disabled=body.disabled)
    return _client(updated)


@router.post("/clients/{client_id}/rotate-secret", summary="Administration (extension): rotate a secret, returned once")
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


@router.delete("/sessions", status_code=204, summary="Administration (extension): end every session of a user")
async def revoke_user_sessions(
    request: Request,
    principal: AdminPrincipal,
    users: UsersDep,
    tokens: TokensDep,
    sessions: WebSessionsDep,
    graph: GraphDep,
    user: Annotated[str, Query(max_length=128, description="A user id or user name")],
) -> Response:
    target = await users.get(user) or await users.get_by_username(user)
    if target is None:
        raise HTTPException(404, "No such user")
    await tokens.revoke_all_for_user(target.id)
    await sessions.delete_for_user(target.id)
    await _record(request, graph, principal, "user.revoke_sessions", user_id=target.id)
    return NO_CONTENT


@router.delete("/sessions/{session_id}", status_code=204, summary="Administration (extension): end one session")
async def revoke_session(
    request: Request, principal: AdminPrincipal, session_id: IdPath, tokens: TokensDep, graph: GraphDep
) -> Response:
    """``session_id`` is the ``id`` of the listing: a refresh-token family or a browser session."""
    user_id = await queries.family_user(graph, session_id)
    if user_id is not None and await tokens.revoke_family(session_id, user_id=user_id):
        await _record(request, graph, principal, "session.revoke_family", user_id=user_id, family_id=session_id)
        return NO_CONTENT
    if await queries.delete_web_session(graph, session_id):
        await _record(request, graph, principal, "session.revoke_web", session_id=session_id)
        return NO_CONTENT
    raise HTTPException(404, "No such session")
