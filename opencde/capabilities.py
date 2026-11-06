# This file was generated with the assistance of an AI coding tool.
"""The capabilities document: what this server offers beyond the OpenCDE specifications.

``GET /.well-known/kontroll`` (no authentication, CORS as for the API, cacheable
for a few minutes) tells a client which extensions are on, so that it can
adapt instead of probing: dynamic client registration, the request log, the
administration API, the IFC graph and whether its database is published, and
the limits a client must respect. Nothing in it is secret. A server without
the document answers 404, which a client reads as "no extensions". Unknown
keys are to be treated as absent. Agreed with Dataspatium (docs/dataspatium-
coordination.md, "The capabilities document").
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from opencde import __version__
from opencde.auth.scopes import SCOPES
from opencde.deps import SettingsDep
from opencde.foundation.routes import BCF_VERSION, DOCUMENTS_VERSION, FOUNDATION_VERSION
from opencde.settings import Settings

router = APIRouter(tags=["Capabilities (extension)"])

ADMIN_API_VERSION = 1  # counts breaking changes of the administration API


def capabilities(settings: Settings) -> dict[str, Any]:
    return {
        "server": {"name": "Kontroll OpenCDE server", "version": __version__, "public_url": settings.public_url},
        "apis": {"foundation": FOUNDATION_VERSION, "bcf": BCF_VERSION, "documents": DOCUMENTS_VERSION},
        "scopes": list(SCOPES),
        "extensions": {
            "dynamic_client_registration": {
                "enabled": settings.dynamic_client_registration,
                "public_clients": True,
                "unused_days": settings.dynamic_client_unused_days,
                "url": "/foundation/oauth2/reg",
            },
            "request_log": {
                "enabled": settings.request_log_enabled,
                "retention_hours": settings.request_log_retention_hours,
                "url": "/admin/api/requests",
            },
            "admin_api": {
                "enabled": settings.admin_api_enabled,
                "version": ADMIN_API_VERSION,
                "url": "/admin/api",
                "scope": "admin",
            },
            "ifcgraph": {"enabled": settings.ifcgraph_enabled, "bolt": settings.graph_public_bolt_url or None},
            "graph_query": (
                {
                    "enabled": True,
                    "url": "/admin/api/graph/query",
                    "max_rows": settings.graph_query_max_rows,
                    "timeout_seconds": settings.graph_query_timeout_seconds,
                }
                if settings.admin_api_enabled and settings.graph_query_enabled
                else {"enabled": False}
            ),
        },
        "limits": {
            "max_upload_bytes": settings.max_upload_bytes,
            "max_image_bytes": settings.max_image_bytes,
            "access_token_ttl_seconds": settings.access_token_ttl_seconds,
        },
        "links": {"dataspatium": settings.dataspatium_url or None},
    }


@router.get("/.well-known/kontroll", summary="Capabilities (extension): what this server offers beyond the specs")
async def well_known_kontroll(settings: SettingsDep) -> JSONResponse:
    """The server's extensions, limits and links, for clients that adapt to them. Never anything secret."""
    return JSONResponse(capabilities(settings), headers={"Cache-Control": "public, max-age=300"})
