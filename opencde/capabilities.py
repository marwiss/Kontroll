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
from opencde.foundation.routes import BCF_OLDER_VERSION, BCF_VERSION, DOCUMENTS_VERSION, FOUNDATION_VERSION
from opencde.ifcgraph.queries import MAX_ROWS as QUERIES_MAX_ROWS
from opencde.ifcgraph.queries import QUERIES
from opencde.settings import Settings

router = APIRouter(tags=["Capabilities (extension)"])

ADMIN_API_VERSION = 1  # counts breaking changes of the administration API


def offered_apis(settings: Settings) -> dict[str, str]:
    """Each API the server offers with its version (OPENCDE_APIS); for BCF, the newest version on offer."""
    bcf = next((version for version in (BCF_VERSION, BCF_OLDER_VERSION) if settings.offers(f"bcf-{version}")), None)
    apis = {"foundation": FOUNDATION_VERSION if settings.offers("foundation") else None, "bcf": bcf}
    apis["documents"] = DOCUMENTS_VERSION if settings.offers("documents") else None
    return {api: version for api, version in apis.items() if version}


def capabilities(settings: Settings) -> dict[str, Any]:
    return {
        "server": {"name": "Kontroll OpenCDE server", "version": __version__, "public_url": settings.public_url},
        "apis": offered_apis(settings),
        "bcf_versions": [version for version in (BCF_VERSION, BCF_OLDER_VERSION) if settings.offers(f"bcf-{version}")],
        "scopes": list(SCOPES),
        "extensions": {
            "dynamic_client_registration": {
                "enabled": settings.dynamic_client_registration,
                "public_clients": True,
                "initial_access_token": bool(settings.dynamic_client_registration_token.get_secret_value()),
                "approval": settings.dynamic_client_approval,
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
            "ifc_queries": (
                {
                    "enabled": True,
                    "url": "/documents/1.0/documents/{document_id}/versions/{version_index}/ifc-queries",
                    "names": list(QUERIES),
                    "max_rows": QUERIES_MAX_ROWS,
                }
                if settings.ifcgraph_enabled and settings.offers("documents")
                else {"enabled": False}
            ),
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
