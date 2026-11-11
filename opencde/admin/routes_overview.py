# This file was generated with the assistance of an AI coding tool.
"""Admin overview, sessions, audit log and settings pages."""

from __future__ import annotations

import csv
import io
import json
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response

from opencde import audit
from opencde.admin import queries
from opencde.admin.access import AdminDep, AdminForm, admin_context, redirect_with_notice, text
from opencde.admin.doctor import run_checks
from opencde.auth.dependencies import TokensDep
from opencde.deps import GraphDep, SettingsDep, StorageDep
from opencde.graph.driver import ping_within
from opencde.settings import env_name
from opencde.ui.templating import render

router = APIRouter(prefix="/admin", include_in_schema=False)

AUDIT_LIMIT = 200
SAFE_SETTINGS = (
    "environment",
    "public_url",
    "graph_dialect",
    "graph_uri",
    "graph_user",
    "graph_database",
    "graph_public_bolt_url",
    "graph_query_enabled",
    "graph_query_max_rows",
    "graph_query_timeout_seconds",
    "mcp_enabled",
    "dataspatium_url",
    "admin_api_enabled",
    "data_dir",
    "max_upload_bytes",
    "upload_part_bytes",
    "max_image_bytes",
    "max_json_body_bytes",
    "authorization_code_ttl_seconds",
    "access_token_ttl_seconds",
    "refresh_token_ttl_seconds",
    "web_session_ttl_seconds",
    "web_session_idle_seconds",
    "form_token_ttl_seconds",
    "documents_session_ttl_seconds",
    "upload_session_ttl_seconds",
    "dynamic_client_registration",
    "allow_localhost_redirects",
    "rate_limits_enabled",
    "admin_ui_enabled",
    "server_assigned_id_prefix",
    "ifcgraph_enabled",
    "bsdd_enabled",
    "bsdd_api_url",
    "request_log_enabled",
    "request_log_retention_hours",
    "cors_origins",
    "trusted_proxies",
    "cleanup_interval_seconds",
    "log_level",
    "log_json",
)


@router.get("")
async def overview(request: Request, admin: AdminDep, graph: GraphDep, settings: SettingsDep) -> Response:
    reachable = await ping_within(graph.driver, graph.database, settings.graph_connect_timeout_seconds)
    counts = await queries.counts(graph) if reachable else {}
    recent = await audit.recent(graph, limit=10) if reachable else []
    return render(
        request,
        "admin/overview.html",
        admin_context(
            request,
            admin,
            "overview",
            counts=counts,
            recent=recent,
            graph_ok=reachable,
            dialect=graph.dialect.name.value,
        ),
    )


# ---------------------------------------------------------------------------- sessions


@router.get("/sessions")
async def sessions_page(request: Request, admin: AdminDep, graph: GraphDep) -> Response:
    form = AdminForm(request, admin, "admin-sessions")
    return render(
        request,
        "admin/sessions.html",
        admin_context(
            request,
            admin,
            "sessions",
            families=await queries.active_families(graph),
            web_sessions=await queries.web_sessions(graph),
            form_token=form.token(),
        ),
    )


@router.post("/sessions")
async def sessions_action(request: Request, admin: AdminDep, graph: GraphDep, tokens: TokensDep) -> Response:
    form = AdminForm(request, admin, "admin-sessions")
    data = await request.form()
    if not form.check(data.get("form_token")):
        return redirect_with_notice("/admin/sessions", "form_expired")
    action = text(data, "action", max_length=32)
    if action == "revoke_family":
        user_id, family_id = text(data, "user_id", max_length=64), text(data, "family_id", max_length=64)
        await tokens.revoke_family(family_id, user_id=user_id)
        await form.record(graph, "session.revoke_family", user_id=user_id)
    elif action == "revoke_web":
        session_id = text(data, "session_id", max_length=128)
        await queries.delete_web_session(graph, session_id)
        await form.record(graph, "session.revoke_web")
    elif action == "revoke_user":
        user_id = text(data, "user_id", max_length=64)
        await tokens.revoke_all_for_user(user_id)
        await form.record(graph, "session.revoke_user", user_id=user_id)
    else:
        return redirect_with_notice("/admin/sessions", "invalid")
    return redirect_with_notice("/admin/sessions", "revoked")


# ---------------------------------------------------------------------------- audit log


def _details_text(details: Any) -> str:
    """An event's details as the JSON they were stored as, for the page and the CSV: never Python's own repr."""
    if not details:
        return ""
    if isinstance(details, str):
        return details
    return json.dumps(details, sort_keys=True, ensure_ascii=False, default=str)


def _audit_rows(graph_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "at": row.get("at"),
            "type": row.get("type"),
            "actor": row.get("actor") or "",
            "client_id": row.get("client_id") or "",
            "ip": row.get("ip") or "",
            "details": _details_text(row.get("details")),
        }
        for row in graph_rows
    ]


@router.get("/audit")
async def audit_page(
    request: Request,
    admin: AdminDep,
    graph: GraphDep,
    type: str | None = Query(None, max_length=64),
) -> Response:
    prefix = (type or "").strip()[:64] or None
    rows = _audit_rows(await audit.recent(graph, limit=AUDIT_LIMIT, type_prefix=prefix))
    return render(
        request,
        "admin/audit.html",
        admin_context(request, admin, "audit", rows=rows, type_prefix=prefix or "", limit=AUDIT_LIMIT),
    )


@router.get("/audit.csv")
async def audit_csv(
    request: Request,
    admin: AdminDep,
    graph: GraphDep,
    type: str | None = Query(None, max_length=64),
) -> Response:
    prefix = (type or "").strip()[:64] or None
    rows = _audit_rows(await audit.recent(graph, limit=10_000, type_prefix=prefix))
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["at", "type", "actor", "client_id", "ip", "details"])
    for row in rows:
        writer.writerow([row["at"], row["type"], row["actor"], row["client_id"], row["ip"], row["details"]])
    return Response(
        buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="audit.csv"', "Cache-Control": "no-store"},
    )


# ---------------------------------------------------------------------------- settings


@router.get("/settings")
async def settings_page(
    request: Request, admin: AdminDep, graph: GraphDep, settings: SettingsDep, storage: StorageDep
) -> Response:
    values = [(env_name(name), getattr(settings, name)) for name in SAFE_SETTINGS]
    shown = [(name, value.value if hasattr(value, "value") else value) for name, value in values]
    return render(
        request,
        "admin/settings.html",
        admin_context(request, admin, "settings", values=shown, checks=await run_checks(settings, graph, storage)),
    )
