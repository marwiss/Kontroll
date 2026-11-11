# This file was generated with the assistance of an AI coding tool.
"""Sign-in and sign-out pages for the server's own UI.

``GET /signin`` shows the form, ``POST /signin`` starts a session and sets the
cookie, ``POST /signout`` deletes the session. The form carries a signed token
(CSRF), the password never appears in a URL, and failures say only that the
user name or password is wrong.
"""

from __future__ import annotations

from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse, Response

from opencde import audit
from opencde.auth import throttle
from opencde.auth.forms import FormTokenError
from opencde.deps import GraphDep, SettingsDep, UsersDep, client_ip
from opencde.ratelimit import limiter, sign_in_limit
from opencde.store.accounts.sessions import COOKIE_NAME, WebSessionsDep, clear_session_cookie, set_session_cookie
from opencde.ui.i18n import tr
from opencde.ui.templating import render
from opencde.web.dependencies import (
    NO_STORE,
    SIGNOUT_PURPOSE,
    WebUserDep,
    change_password_url,
    form_tokens,
    page_context,
    require_same_origin,
    safe_next,
)

router = APIRouter(tags=["Web UI"], include_in_schema=False)

SIGNIN_PURPOSE = "web-signin"


def _signin_page(request: Request, target: str, error: str | None, status_code: int = 200) -> Response:
    token = form_tokens(request).sign(SIGNIN_PURPOSE, {"next": target})
    return render(request, "web/signin.html", {"form_token": token, "error": error}, status_code=status_code)


@router.get("/signin", summary="Sign-in page")
async def signin_page(request: Request, web_user: WebUserDep, next: str | None = None) -> Response:
    target = safe_next(next)
    if web_user is not None:
        return RedirectResponse(target, status_code=302, headers=NO_STORE)
    return _signin_page(request, target, None)


@router.post("/signin", summary="Sign in")
@limiter.limit(sign_in_limit)
async def signin_submit(
    request: Request,
    users: UsersDep,
    sessions: WebSessionsDep,
    graph: GraphDep,
    settings: SettingsDep,
    form_token: Annotated[str | None, Form()] = None,
    username: Annotated[str, Form(max_length=128)] = "",
    password: Annotated[str, Form(max_length=256)] = "",
) -> Response:
    require_same_origin(request)
    try:
        data = form_tokens(request).load(form_token, SIGNIN_PURPOSE)
    except FormTokenError:
        return _signin_page(request, "/", tr(request, "signin.error.expired"), status_code=400)
    target = safe_next(data.get("next"))
    ip = client_ip(request)

    try:
        user = await throttle.authenticate(users, graph, settings, username, password)
    except throttle.SignInThrottled as exc:
        await audit.record(graph, "web.sign_in.throttled", ip=ip, details={"username": username[:128]})
        error = tr(request, "signin.error.throttled", seconds=exc.seconds)
        return _signin_page(request, target, error, status_code=429)
    if user is None:
        await audit.record(graph, "web.sign_in.failed", ip=ip, details={"username": username[:128]})
        return _signin_page(request, target, tr(request, "signin.error.credentials"))

    token = await sessions.create(user.id, ip)
    await users.touch_sign_in(user.id)
    await audit.record(graph, "web.sign_in", actor=user.id, ip=ip)
    if user.must_change_password:
        target = change_password_url(target)
    response = RedirectResponse(target, status_code=302, headers=NO_STORE)
    set_session_cookie(response, token, settings)
    return response


@router.post("/signout", summary="Sign out")
async def signout(
    request: Request,
    sessions: WebSessionsDep,
    web_user: WebUserDep,
    graph: GraphDep,
    signout_token: Annotated[str | None, Form()] = None,
    next_page: Annotated[str | None, Form(alias="next")] = None,
) -> Response:
    require_same_origin(request)
    target = safe_next(next_page)
    after = "/" if target == "/" else f"/signin?{urlencode({'next': target})}"
    response = RedirectResponse(after, status_code=302, headers=NO_STORE)
    if web_user is not None:
        try:
            form_tokens(request).load(signout_token, SIGNOUT_PURPOSE)
        except FormTokenError:
            return render(
                request,
                "web/message.html",
                page_context(
                    request,
                    web_user,
                    title=tr(request, "signout.error.title"),
                    message=tr(request, "signout.error.expired"),
                ),
                status_code=400,
            )
        cookie = request.cookies.get(COOKIE_NAME)
        if cookie:
            await sessions.delete(cookie)
        await audit.record(graph, "web.sign_out", actor=web_user.user.id, ip=client_ip(request))
    clear_session_cookie(response)
    return response
