# This file was generated with the assistance of an AI coding tool.
"""Rendering HTML pages.

Every page is rendered from ``opencde/ui/templates`` with autoescaping and
sent with a strict Content-Security-Policy: styles and scripts only from our
own origin, no inline code, no framing. Pages are never cached. The language
of the page is chosen per request (``opencde.ui.i18n``) and remembered in a
cookie when the visitor picks one.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from fastapi import Request
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape

from opencde.ui import i18n

UI_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = UI_DIR / "templates"
STATIC_DIR = UI_DIR / "static"

PAGE_CSP = (
    "default-src 'none'; style-src 'self'; script-src 'self'; img-src 'self' data:; font-src 'self'; "
    "connect-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'"
)

_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(["html", "xml"], default=True),
    trim_blocks=True,
    lstrip_blocks=True,
)
_env.filters["zip"] = lambda left, right: list(zip(left, right, strict=False))
_env.globals["t"] = cast(Any, i18n.t)  # the page's language comes from a context variable set in render()


def _register_macros(template: str) -> None:
    """Make a macro file's macros available in every template, including blocks of child templates."""
    module = _env.get_template(template).module
    for name in dir(module):
        if not name.startswith("_"):
            _env.globals[name] = getattr(module, name)


_register_macros("components.html")
_register_macros("admin/_macros.html")


def render(
    request: Request,
    template: str,
    context: dict[str, Any] | None = None,
    *,
    status_code: int = 200,
    headers: dict[str, str] | None = None,
) -> HTMLResponse:
    settings = request.app.state.settings
    lang = i18n.negotiate(request)
    base_context: dict[str, Any] = {
        "request": request,
        "lang": lang,
        "language_links": i18n.language_links(request),
        "product": i18n.translate(lang, "product.name"),
        "server_host": settings.public_url.removeprefix("https://").removeprefix("http://"),
        "docs_enabled": settings.api_docs_on,
    }
    base_context.update(context or {})
    token = i18n.current_language.set(lang)
    try:
        html = _env.get_template(template).render(base_context)
    finally:
        i18n.current_language.reset(token)
    response_headers = {"Content-Security-Policy": PAGE_CSP, "Cache-Control": "no-store"}
    response_headers.update(headers or {})
    response = HTMLResponse(html, status_code=status_code, headers=response_headers)
    if i18n.requested_explicitly(request) and request.cookies.get(i18n.COOKIE_NAME) != lang:
        response.set_cookie(
            i18n.COOKIE_NAME,
            lang,
            max_age=i18n.COOKIE_MAX_AGE,
            path="/",
            secure=settings.public_url.startswith("https://"),
            httponly=False,
            samesite="lax",
        )
    return response
