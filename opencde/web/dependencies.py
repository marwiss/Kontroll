# This file was generated with the assistance of an AI coding tool.
"""What a page handler needs: the signed-in user (if any), CSRF checks and safe redirects."""

from __future__ import annotations

from typing import Annotated, Any
from urllib.parse import urlencode, urlsplit

from fastapi import Depends, HTTPException, Request
from fastapi.responses import RedirectResponse

from opencde.auth.forms import FormTokens
from opencde.web.sessions import COOKIE_NAME, WebSessionsDep, WebUser

NO_STORE = {"Cache-Control": "no-store", "Pragma": "no-cache"}
SIGNOUT_PURPOSE = "web-signout"
MAX_NEXT_LENGTH = 2000


def form_tokens(request: Request) -> FormTokens:
    settings = request.app.state.settings
    return FormTokens(settings.secret_key.get_secret_value(), settings.form_token_ttl_seconds)


async def current_web_user(request: Request, sessions: WebSessionsDep) -> WebUser | None:
    """The browser's signed-in user, or None. Never raises: pages decide how to ask for sign-in."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    web_user = await sessions.resolve(token)
    request.state.web_user = web_user
    return web_user


WebUserDep = Annotated[WebUser | None, Depends(current_web_user)]


def safe_next(value: str | None) -> str:
    """A path on this server to return to after sign-in; anything else becomes ``/`` (no open redirects)."""
    if (
        not value
        or len(value) > MAX_NEXT_LENGTH
        or not value.startswith("/")
        or value.startswith("//")
        or "\\" in value
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        return "/"
    return value


def signin_redirect(request: Request) -> RedirectResponse:
    """Send the browser to the sign-in page and back to the current page afterwards."""
    target = request.url.path + (f"?{request.url.query}" if request.url.query else "")
    return RedirectResponse("/signin?" + urlencode({"next": safe_next(target)}), status_code=302, headers=NO_STORE)


def _origins(request: Request) -> set[str]:
    origins = {urlsplit(request.app.state.settings.public_url)._replace(path="").geturl()}
    host = request.headers.get("host")
    if host:
        origins.add(f"{request.url.scheme}://{host}")
    return origins


def require_same_origin(request: Request) -> None:
    """Refuse cookie-authenticated form posts that a browser marks as cross-site (CSRF defence in depth).

    The signed form token is the primary protection; ``Sec-Fetch-Site`` and ``Origin`` are checked as well
    because they cost nothing and catch mistakes in pages that forget a token.
    """
    site = request.headers.get("sec-fetch-site")
    if site and site not in ("same-origin", "none"):
        raise HTTPException(403, "Cross-site request refused")
    origin = request.headers.get("origin")
    if origin and origin != "null" and origin not in _origins(request):
        raise HTTPException(403, "Cross-site request refused")


def page_context(request: Request, web_user: WebUser | None, **extra: Any) -> dict[str, Any]:
    """Context every signed-in page needs: who is signed in and a token for the sign-out form."""
    context: dict[str, Any] = {"web_user": web_user, "signout_token": None}
    if web_user is not None:
        context["signout_token"] = form_tokens(request).sign(SIGNOUT_PURPOSE, {"session": web_user.session_hash})
    context.update(extra)
    return context
