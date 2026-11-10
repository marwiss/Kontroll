# This file was generated with the assistance of an AI coding tool.
"""The capabilities document: what this server offers beyond the OpenCDE specifications.

``GET /.well-known/dataregium`` (no authentication, CORS as for the API, cacheable
for a few minutes) tells a client which extensions are on, so that it can
adapt instead of probing: dynamic client registration, the request log, the
administration API, the IFC graph and whether its database is published, and
the limits a client must respect. Nothing in it is secret. A server without
the document answers 404, which a client reads as "no extensions". Unknown
keys are to be treated as absent. Agreed with Dataspatium.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from opencde import __version__
from opencde.accounts.routes_manage import ROLES as MANAGE_ROLES
from opencde.auth.scopes import SCOPES
from opencde.deps import SettingsDep
from opencde.documents.changes import MAX_CHANGES, SCHEMA_PATH, SNIPPET_TYPE
from opencde.foundation.routes import BCF_OLDER_VERSION, BCF_VERSION, DOCUMENTS_VERSION, FOUNDATION_VERSION
from opencde.ifcgraph.diff import MAX_ENTRIES as DIFF_MAX_ENTRIES
from opencde.ifcgraph.gltf import LODS
from opencde.ifcgraph.queries import CHANGED_SINCE, QUERIES
from opencde.ifcgraph.queries import MAX_ROWS as QUERIES_MAX_ROWS
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
        "server": {"name": "Dataregium OpenCDE server", "version": __version__, "public_url": settings.public_url},
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
            "ifcgraph": {
                "enabled": settings.ifcgraph_enabled,
                "bolt": settings.graph_public_bolt_url or None,
                "workcopy": settings.has_workcopy,
            },
            "ifc_queries": (
                {
                    "enabled": True,
                    "url": "/documents/1.0/documents/{document_id}/versions/{version_index}/ifc-queries",
                    "names": [*QUERIES, CHANGED_SINCE],
                    "max_rows": QUERIES_MAX_ROWS,
                }
                if settings.ifcgraph_enabled and settings.offers("documents")
                else {"enabled": False}
            ),
            "ifc_clash": (
                {
                    "enabled": True,
                    "url": "/documents/1.0/projects/{project_id}/ifc-clash",
                    "modes": ["intersection", "clearance"],
                    "max_clashes": settings.ifcgraph_clash_max_clashes,
                }
                if settings.ifcgraph_enabled and settings.ifcgraph_clash_enabled and settings.offers("documents")
                else {"enabled": False}
            ),
            "project_administration": {
                "enabled": True,
                "url": "/manage/1.0/projects",
                "scope": "project",
                "roles": list(MANAGE_ROLES),
                "for": "managers of a project",
            },
            "publication": (
                {
                    "enabled": True,
                    "url": "/documents/1.0/documents/{document_id}/versions/{version_index}/publication",
                    "roles": ["manager"],
                    "formats": ["ifczip", "zip"],
                }
                if settings.offers("documents")
                else {"enabled": False}
            ),
            "headless_uploads": {
                "enabled": settings.offers("documents"),
                "url": "/documents/1.0/upload-documents",
                "for": "confidential clients an administrator approved",
            },
            "ifc_diff": (
                {
                    "enabled": True,
                    "url": "/documents/1.0/documents/{document_id}/versions/{version_index}/ifc-diff/{other_index}",
                    "max_entries": DIFF_MAX_ENTRIES,
                }
                if settings.ifcgraph_enabled and settings.offers("documents")
                else {"enabled": False}
            ),
            "ifc_geometry": (
                {
                    "enabled": True,
                    "url": "/documents/1.0/documents/{document_id}/versions/{version_index}/ifc-geometry",
                    "format": "model/gltf-binary",
                    "lods": list(LODS),
                }
                if settings.ifcgraph_enabled and settings.ifcgraph_spatial and settings.offers("documents")
                else {"enabled": False}
            ),
            "ifc_precheck": (
                {"enabled": True, "url": "/documents/1.0/projects/{project_id}/ifc-precheck"}
                if settings.ifcgraph_enabled and settings.ifcgraph_validate_uploads and settings.offers("documents")
                else {"enabled": False}
            ),
            "ifc_changes": (
                {
                    "enabled": True,
                    "schema": SCHEMA_PATH,
                    "snippet_type": SNIPPET_TYPE,
                    "max_changes": MAX_CHANGES,
                    "tried": settings.ifcgraph_enabled,
                    "proposal_url": "/bcf/3.0/projects/{project_id}/topics/{topic_guid}/ifc-proposal",
                    "approve_url": "/bcf/3.0/projects/{project_id}/topics/{topic_guid}/ifc-proposal/approve",
                    "ops": ["set", "add", "remove", "delete"],
                    "unreachable_url": "/documents/1.0/projects/{project_id}/ifc-unreachable"
                    if settings.ifcgraph_enabled
                    else None,
                }
                if settings.offers("documents") and settings.offers("bcf-3.0")
                else {"enabled": False}
            ),
            "ifc_merge": (
                {
                    "enabled": True,
                    "url": "/documents/1.0/projects/{project_id}/ifc-merge",
                    "report_url": "/documents/1.0/projects/{project_id}/ifc-merge/report",
                    "prepare_url": "/documents/1.0/projects/{project_id}/ifc-merge/prepare",
                    "choices": ["a", "b", "new"],
                    "roles": ["manager"],
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


@router.get("/.well-known/dataregium", summary="Capabilities (extension): what this server offers beyond the specs")
@router.get(
    "/.well-known/kontroll",
    summary="Capabilities (extension): the same document under the former name",
    deprecated=True,
)
async def well_known_dataregium(settings: SettingsDep) -> JSONResponse:
    """The server's extensions, limits and links, for clients that adapt to them. Never anything secret.

    ``/.well-known/kontroll`` is the path from before the rename of 2026-11-08 and answers the same.
    """
    return JSONResponse(capabilities(settings), headers={"Cache-Control": "public, max-age=300"})
