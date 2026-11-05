# This file was generated with the assistance of an AI coding tool.
"""The JSON administration API, an extension outside the OpenCDE specifications.

What the administration pages show, for an administration client such as
Dataspatium: a bearer token holding the ``admin`` scope and an administrator
account (``AdminPrincipal``) reads the overview, users, projects, clients,
sessions, the audit log, the settings and the health checks. Lists answer
``{"items": [...], "total": n}`` with ``limit`` (200 by default, at most
1000) and ``q``/``since`` where they apply. Errors use the Foundation body
with a ``code``. Writes come with the second step of the API and need an
authentication from the last ten minutes (``FreshAdminPrincipal``). Agreed
with Dataspatium in docs/dataspatium-coordination.md (item 12).
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Path, Query

from opencde import __version__, audit
from opencde.accounts.projects import Project
from opencde.accounts.users import User
from opencde.admin import queries
from opencde.admin.doctor import run_checks
from opencde.admin.routes_overview import SAFE_SETTINGS
from opencde.auth.clients import Client
from opencde.auth.dependencies import AdminPrincipal
from opencde.deps import ClientsDep, GraphDep, ProjectsDep, SettingsDep, StorageDep, UsersDep
from opencde.graph.driver import ping_within

router = APIRouter(prefix="/admin/api", tags=["Administration (extension)"])

DEFAULT_LIMIT = 200
MAX_LIMIT = 1000
LimitQuery = Annotated[int, Query(ge=1, le=MAX_LIMIT, description="At most this many items (default 200)")]
SearchQuery = Annotated[str | None, Query(max_length=100, description="Substring of user name, name or e-mail")]
TypeQuery = Annotated[str | None, Query(max_length=64, description="Event type prefix, e.g. auth. or admin.user")]
SinceQuery = Annotated[str | None, Query(max_length=40, description="ISO 8601 UTC; items at or after it")]
IdPath = Annotated[str, Path(max_length=64)]


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


@router.get("/overview", summary="Administration (extension): counts and the state of the database")
async def overview(principal: AdminPrincipal, graph: GraphDep, settings: SettingsDep) -> dict[str, Any]:
    reachable = await ping_within(graph.driver, graph.database, settings.graph_connect_timeout_seconds)
    counts = await queries.counts(graph) if reachable else {}
    return {
        "version": __version__,
        "dialect": graph.dialect.name.value,
        "graph_ok": reachable,
        "counts": counts,
    }


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


@router.get("/projects/{project_id}", summary="Administration (extension): one project with members and extensions")
async def get_project(
    principal: AdminPrincipal, project_id: IdPath, projects: ProjectsDep, graph: GraphDep
) -> dict[str, Any]:
    project = await projects.get(project_id)
    if project is None:
        raise HTTPException(404, "No such project")
    stats = await queries.project_stats(graph)
    data = _project(project, stats.get(project.project_id, {}))
    data["members"] = [
        {"user_id": user.id, "username": user.username, "full_name": user.full_name, "role": role.value}
        for user, role in await projects.members(project.project_id)
    ]
    data["extensions"] = await projects.extensions(project.project_id) or {}
    return data


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
