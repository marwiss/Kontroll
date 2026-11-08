# This file was generated with the assistance of an AI coding tool.
"""Application factory.

``create_app()`` wires settings, logging, middleware, error handling, the
graph database and the routers together. Routers for the Foundation, BCF and
Documents APIs and the admin UI are registered here as the stages of the plan
deliver them.
"""

from __future__ import annotations

import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from opencde import __version__, capabilities, health
from opencde.admin import api as admin_api
from opencde.admin import graph_query, routes_requests
from opencde.admin import router as admin_router
from opencde.admin.access import install_page_handlers
from opencde.auth import routes as oauth2_routes
from opencde.bcf import router as bcf_router
from opencde.bootstrap import make_graph, make_storage, wait_for_graph
from opencde.documents import routes_api as documents_api
from opencde.documents import routes_queries as documents_queries
from opencde.documents import routes_ui as documents_ui
from opencde.documents import routes_validation as documents_validation
from opencde.errors import install_error_handlers
from opencde.etag import ETagMiddleware
from opencde.foundation import routes as foundation_routes
from opencde.graph.cleanup import ExpiryCleaner
from opencde.graph.schema import apply_schema
from opencde.ifcgraph.service import IfcGraphService
from opencde.logging import configure_logging, get_logger
from opencde.middleware import (
    ApiCORSMiddleware,
    BodySizeLimitMiddleware,
    ForeignWorkerMiddleware,
    RequestIDMiddleware,
    SecurityHeadersMiddleware,
    UnhandledErrorMiddleware,
)
from opencde.ratelimit import PathRateLimitMiddleware, install_rate_limiting
from opencde.requestlog import RequestLogMiddleware, RequestLogWriter
from opencde.settings import Settings
from opencde.ui.templating import STATIC_DIR, render
from opencde.web import account as account_routes
from opencde.web import routes as web_routes

DESCRIPTION = """\
Server implementation of the buildingSMART OpenCDE APIs:

* **Foundation API 1.0**: service discovery, OAuth2 authorization code with PKCE, current user.
* **BCF API 3.0**: projects, topics, comments, viewpoints, files, documents and events.
* **BCF API 2.1**: the same on the same data, for clients that know nothing newer.
* **Documents API 1.0**: document selection, download, upload and version queries.

Data lives in a graph database (Neo4j or Memgraph). Source: https://github.com/marwiss/Dataregium
"""

OPENAPI_TAGS = [
    {"name": "Foundation API", "description": "Service discovery and authentication (Foundation API 1.0)."},
    {"name": "BCF API", "description": "Issue management (BCF API 3.0)."},
    {"name": "BCF API 2.1", "description": "Issue management for clients that know nothing newer than 2.1."},
    {"name": "Documents API", "description": "Document exchange (Documents API 1.0)."},
    {"name": "operations", "description": "Health endpoints for containers and monitoring."},
    {
        "name": "Administration (extension)",
        "description": "Outside the OpenCDE specifications: administration for clients holding the `admin` scope.",
    },
    {
        "name": "Capabilities (extension)",
        "description": "Outside the OpenCDE specifications: which extensions and limits this server has.",
    },
    {
        "name": "IFC validation (extension)",
        "description": "Outside the OpenCDE specifications: the result of checking an uploaded IFC file against the IFC "
        "schema. The version's metadata carries a summary and the address of this report.",
    },
]


def create_app(settings: Settings | None = None, *, startup_wait_seconds: float = 60.0) -> FastAPI:
    settings = settings or Settings()
    configure_logging(settings.log_level, settings.log_json)
    log = get_logger(__name__)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        app.state.settings = settings
        app.state.started_at = time.monotonic()  # the administration API reports the uptime from it
        app.state.graph = make_graph(settings)
        app.state.storage = make_storage(settings)
        app.state.ifcgraph = (
            IfcGraphService(app.state.graph, app.state.storage, settings) if settings.ifcgraph_enabled else None
        )
        cleaner = ExpiryCleaner(
            app.state.graph,
            settings.cleanup_interval_seconds,
            app.state.storage,
            each_round=app.state.ifcgraph.resume_interrupted if app.state.ifcgraph else None,
        )
        app.state.requestlog = (
            RequestLogWriter(app.state.graph, settings.request_log_retention_hours)
            if settings.request_log_enabled
            else None
        )
        log.info(
            "server_starting",
            version=__version__,
            environment=settings.environment,
            public_url=settings.public_url,
            graph_dialect=settings.graph_dialect.value,
            graph_database=settings.database_name,
        )
        for old, new in settings.renamed_settings:  # names only: a setting's value can be a secret
            log.warning("setting_renamed", old=old, new=new)
        if startup_wait_seconds > 0:
            await wait_for_graph(app.state.graph, startup_wait_seconds)
            await apply_schema(app.state.graph)
            cleaner.start()
        try:
            yield
        finally:
            await cleaner.stop()
            if app.state.ifcgraph is not None:
                await app.state.ifcgraph.shutdown()
            if app.state.requestlog is not None:
                await app.state.requestlog.close()
            await app.state.graph.close()
            log.info("server_stopped")

    app = FastAPI(
        title="Kontroll OpenCDE server",
        description=DESCRIPTION,
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs" if settings.api_docs_on else None,  # Swagger UI from a CDN: off in production by default
        redoc_url=None,
        openapi_tags=OPENAPI_TAGS,
        license_info={"name": "AGPL-3.0-or-later", "url": "https://www.gnu.org/licenses/agpl-3.0.html"},
    )

    install_error_handlers(app)
    install_page_handlers(app)
    install_rate_limiting(
        app,
        settings.rate_limits_enabled,
        production=settings.is_production,
        storage_uri=settings.rate_limit_storage.get_secret_value(),
        sign_in=settings.rate_limit_sign_in,
    )

    # Middleware runs outermost-last: request id first, then size limit, CORS, ETag, headers on the way out.
    # Unhandled errors are turned into the spec 500 innermost, so CORS and the security headers still apply.
    app.add_middleware(UnhandledErrorMiddleware)
    app.add_middleware(PathRateLimitMiddleware, api_limit=settings.rate_limit_api)
    app.add_middleware(ForeignWorkerMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(ETagMiddleware)
    app.add_middleware(
        ApiCORSMiddleware,
        include_prefixes=("/foundation/", "/bcf/", "/documents/1.0/", "/admin/api/", "/.well-known/"),
        exclude_patterns=documents_ui.PAGE_PATHS,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        # Content-Disposition carries the file name of binary uploads (Foundation API 1.9) and downloads.
        allow_headers=[
            "Authorization",
            "Content-Type",
            "Content-Disposition",
            "Accept",
            "If-None-Match",
            "X-Request-ID",
        ],
        expose_headers=["ETag", "Location", "Content-Disposition", "X-Request-ID"],
        max_age=600,
    )
    app.add_middleware(
        BodySizeLimitMiddleware,
        max_bytes=settings.max_json_body_bytes,
        exempt_prefixes=("/documents/1.0/upload-part/",),
        exempt_patterns=(*bcf_router.BINARY_UPLOAD_PATHS, *documents_ui.BROWSER_UPLOAD_PATHS),
    )
    app.add_middleware(RequestLogMiddleware)  # sees the final status; inside the request id so it can record it
    app.add_middleware(RequestIDMiddleware)

    app.include_router(health.router)
    # Only the APIs the server offers are mounted (OPENCDE_APIS); sign-in under /foundation/oauth2 serves them all.
    if settings.offers("foundation"):
        app.include_router(foundation_routes.router)
    if settings.offers("bcf-3.0"):
        app.include_router(foundation_routes.alias_router)
    app.include_router(oauth2_routes.router)
    if settings.offers("bcf-3.0"):
        app.include_router(bcf_router.v30)
    if settings.offers("bcf-2.1"):
        app.include_router(bcf_router.v21)
    if settings.offers("bcf-3.0") or settings.offers("bcf-2.1"):
        app.include_router(bcf_router.versions)
    if settings.offers("documents"):
        app.include_router(documents_api.router)
        app.include_router(documents_validation.router)
        app.include_router(documents_queries.router)
        app.include_router(documents_ui.router)
    app.include_router(web_routes.router)
    app.include_router(account_routes.router)
    if settings.admin_ui_enabled:
        app.include_router(admin_router.router)
    if settings.admin_api_enabled:
        app.include_router(routes_requests.api_router)
        app.include_router(admin_api.router)
        if settings.graph_query_enabled:
            app.include_router(graph_query.router)
    app.include_router(capabilities.router)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/", include_in_schema=False, response_class=HTMLResponse)
    async def index(request: Request) -> HTMLResponse:
        return render(
            request,
            "index.html",
            {
                "version": __version__,
                "admin_enabled": settings.admin_ui_enabled,
                "foundation": settings.offers("foundation"),
            },
        )

    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon() -> FileResponse:
        """Browsers ask for this path unprompted; the pages themselves link the SVG and PNG icons."""
        return FileResponse(
            STATIC_DIR / "favicon.ico", media_type="image/x-icon", headers={"Cache-Control": "public, max-age=86400"}
        )

    return app
