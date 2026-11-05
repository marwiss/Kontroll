# This file was generated with the assistance of an AI coding tool.
"""``/account``: every signed-in user's own page.

Change the password (the current one is required), see which applications
hold a refresh token and revoke them, see and end browser sessions.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import Response

from opencde import audit
from opencde.accounts.users import AccountError
from opencde.admin import queries
from opencde.admin.access import NOTICES, SignedInDep, redirect_with_notice, text
from opencde.auth.dependencies import TokensDep
from opencde.auth.forms import FormTokenError
from opencde.deps import GraphDep, UsersDep, client_ip
from opencde.ui.templating import render
from opencde.web.dependencies import form_tokens, page_context, require_same_origin
from opencde.web.sessions import WebSessionsDep

router = APIRouter(include_in_schema=False)

PURPOSE = "web-account"


async def _page(
    request: Request,
    web_user: SignedInDep,
    tokens: TokensDep,
    graph: GraphDep,
    error: str | None = None,
    status_code: int = 200,
) -> Response:
    notice = request.query_params.get("notice")
    return render(
        request,
        "web/account.html",
        page_context(
            request,
            web_user,
            apps=await tokens.sessions_for_user(web_user.user.id),
            web_sessions=await queries.web_sessions(graph, web_user.user.id),
            form_token=form_tokens(request).sign(PURPOSE, {"session": web_user.session_hash}),
            notice=NOTICES.get(notice or ""),
            notice_kind="error" if notice in ("wrong_password", "form_expired", "invalid") else "success",
            must_change=web_user.user.must_change_password,
            error=error,
        ),
        status_code=status_code,
    )


@router.get("/account")
async def account_page(request: Request, web_user: SignedInDep, tokens: TokensDep, graph: GraphDep) -> Response:
    return await _page(request, web_user, tokens, graph)


@router.post("/account")
async def account_action(
    request: Request,
    web_user: SignedInDep,
    users: UsersDep,
    tokens: TokensDep,
    sessions: WebSessionsDep,
    graph: GraphDep,
) -> Response:
    require_same_origin(request)
    data = await request.form()
    token = data.get("form_token")
    try:
        payload = form_tokens(request).load(token if isinstance(token, str) else None, PURPOSE)
    except FormTokenError:
        return redirect_with_notice("/account", "form_expired")
    if payload.get("session") != web_user.session_hash:
        return redirect_with_notice("/account", "form_expired")
    action = text(data, "action", max_length=32)
    ip = client_ip(request)

    if action == "change_password":
        current = text(data, "current_password", max_length=256)
        new, repeat = text(data, "new_password", max_length=256), text(data, "repeat_password", max_length=256)
        if await users.authenticate(web_user.user.username, current) is None:
            await audit.record(graph, "account.password.failed", actor=web_user.user.id, ip=ip)
            return redirect_with_notice("/account", "wrong_password")
        if new != repeat:
            return await _page(request, web_user, tokens, graph, error="The two new passwords differ.", status_code=400)
        try:
            await users.set_password(web_user.user.id, new, must_change=False)
        except AccountError as exc:
            return await _page(request, web_user, tokens, graph, error=str(exc), status_code=400)
        await audit.record(graph, "account.password.changed", actor=web_user.user.id, ip=ip)
        return redirect_with_notice("/account", "password_changed")

    if action == "revoke_app":
        await tokens.revoke_family(text(data, "family_id", max_length=64), user_id=web_user.user.id)
        await audit.record(graph, "account.app.revoked", actor=web_user.user.id, ip=ip)
        return redirect_with_notice("/account", "revoked")

    if action == "revoke_web":
        session_id = text(data, "session_id", max_length=128)
        if session_id != web_user.session_hash:
            owned = {row["id"] for row in await queries.web_sessions(graph, web_user.user.id)}
            if session_id in owned:
                await queries.delete_web_session(graph, session_id)
        return redirect_with_notice("/account", "revoked")

    if action == "sign_out_everywhere":
        await sessions.delete_for_user(web_user.user.id)
        await audit.record(graph, "account.sign_out_everywhere", actor=web_user.user.id, ip=ip)
        return redirect_with_notice("/signin", "revoked")

    return redirect_with_notice("/account", "invalid")
