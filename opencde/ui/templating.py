# This file was generated with the assistance of an AI coding tool.
"""Rendering HTML pages.

Every page is rendered from ``opencde/ui/templates`` with autoescaping and
sent with a strict Content-Security-Policy: styles and scripts only from our
own origin, no inline code, no framing. Pages are never cached.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape

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


def render(
    request: Request,
    template: str,
    context: dict[str, Any] | None = None,
    *,
    status_code: int = 200,
    headers: dict[str, str] | None = None,
) -> HTMLResponse:
    settings = request.app.state.settings
    base_context: dict[str, Any] = {
        "request": request,
        "product": "OpenCDE server",
        "server_host": settings.public_url.removeprefix("https://").removeprefix("http://"),
    }
    base_context.update(context or {})
    html = _env.get_template(template).render(base_context)
    response_headers = {"Content-Security-Policy": PAGE_CSP, "Cache-Control": "no-store"}
    response_headers.update(headers or {})
    return HTMLResponse(html, status_code=status_code, headers=response_headers)
