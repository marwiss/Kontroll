# This file was generated with the assistance of an AI coding tool.
"""Who may use the admin pages, and the protections every admin form shares.

* Only signed-in users with ``is_admin`` get anything but ``404`` under
  ``/admin``; anonymous browsers are sent to the sign-in page.
* Every POST carries a signed token bound to the admin's session and to the
  object it changes, and must look same-origin to the browser.
* Dangerous actions (resetting someone's password, granting the admin role,
  rotating a client secret, deleting) also need the admin's own password.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, Response

from opencde import audit
from opencde.accounts.users import UserRepository
from opencde.auth.forms import FormTokenError
from opencde.deps import client_ip
from opencde.graph.graph import Graph
from opencde.ui.i18n import tr
from opencde.ui.templating import render
from opencde.web.dependencies import (
    NO_STORE,
    WebUserDep,
    form_tokens,
    page_context,
    require_same_origin,
    signin_redirect,
)
from opencde.web.sessions import WebUser

# ``?notice=<name>`` after a redirect; the page translates the catalogue key (opencde/ui/i18n/<lang>.json).
NOTICES = {
    name: f"notice.{name}"
    for name in (
        "saved",
        "created",
        "deleted",
        "revoked",
        "member_saved",
        "member_removed",
        "extensions_saved",
        "password_changed",
        "change_password",
        "wrong_password",
        "form_expired",
        "not_yourself",
        "invalid",
    )
}


class SignInRequired(Exception):
    """Raised by page dependencies when the browser has no session; the handler redirects to /signin."""


class PageNotFound(Exception):
    """Raised for pages that must not reveal their existence (non-admins under /admin)."""


async def current_admin(web_user: WebUserDep) -> WebUser:
    if web_user is None:
        raise SignInRequired
    if not web_user.user.is_admin:
        raise PageNotFound
    return web_user


AdminDep = Annotated[WebUser, Depends(current_admin)]


async def signed_in_user(web_user: WebUserDep) -> WebUser:
    if web_user is None:
        raise SignInRequired
    return web_user


SignedInDep = Annotated[WebUser, Depends(signed_in_user)]


def install_page_handlers(app: Any) -> None:
    """Turn the two page exceptions into a redirect and an HTML 404."""

    async def _sign_in(request: Request, _exc: SignInRequired) -> Response:
        return signin_redirect(request)

    async def _not_found(request: Request, _exc: PageNotFound) -> Response:
        return render(
            request,
            "web/message.html",
            page_context(
                request,
                getattr(request.state, "web_user", None),
                title=tr(request, "page.not_found.title"),
                message=tr(request, "page.not_found.message"),
            ),
            status_code=404,
        )

    app.add_exception_handler(SignInRequired, _sign_in)
    app.add_exception_handler(PageNotFound, _not_found)


@dataclass(frozen=True)
class AdminForm:
    """The checks a POST to an admin page runs before anything changes."""

    request: Request
    admin: WebUser
    purpose: str
    subject: str = ""

    def token(self) -> str:
        return form_tokens(self.request).sign(
            self.purpose, {"session": self.admin.session_hash, "subject": self.subject}
        )

    def check(self, token: Any) -> bool:
        require_same_origin(self.request)
        try:
            data = form_tokens(self.request).load(token if isinstance(token, str) else None, self.purpose)
        except FormTokenError:
            return False
        return data.get("session") == self.admin.session_hash and data.get("subject") == self.subject

    async def record(self, graph: Graph, action: str, **details: Any) -> None:
        await audit.record(
            graph,
            f"admin.{action}",
            actor=self.admin.user.id,
            ip=client_ip(self.request),
            details={key: value for key, value in details.items() if value is not None},
        )


async def password_confirmed(users: UserRepository, admin: WebUser, password: Any) -> bool:
    """Re-authentication for dangerous actions: the admin's own password, right now."""
    if not isinstance(password, str) or not password:
        return False
    return await users.authenticate(admin.user.username, password) is not None


def redirect_with_notice(path: str, notice: str) -> RedirectResponse:
    return RedirectResponse(f"{path}?notice={notice}", status_code=303, headers=NO_STORE)


def admin_context(request: Request, admin: WebUser, active: str, **extra: Any) -> dict[str, Any]:
    notice = request.query_params.get("notice")
    return page_context(
        request,
        admin,
        active=active,
        notice=NOTICES.get(notice or ""),
        notice_kind="error" if notice in ("wrong_password", "form_expired", "not_yourself", "invalid") else "success",
        **extra,
    )


def text(form: Any, name: str, *, max_length: int = 200, default: str = "") -> str:
    value = form.get(name)
    if not isinstance(value, str):
        return default
    return value.strip()[:max_length]


def lines(form: Any, name: str, *, max_items: int = 200, max_length: int = 2000) -> list[str]:
    """A textarea with one value per line, trimmed, de-duplicated, bounded."""
    raw = text(form, name, max_length=max_items * max_length)
    result: list[str] = []
    for line in raw.replace("\r", "").split("\n"):
        value = line.strip()[:max_length]
        if value and value not in result:
            result.append(value)
    return result[:max_items]


def flag(form: Any, name: str) -> bool:
    return form.get(name) in ("on", "true", "1", "yes")


def not_found() -> HTTPException:
    return HTTPException(404, "Not found")
