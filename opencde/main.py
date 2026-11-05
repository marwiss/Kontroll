# This file was generated with the assistance of an AI coding tool.
"""Application factory.

``create_app()`` wires settings, logging, middleware, error handling, the
graph database and the routers together. Routers for the Foundation, BCF and
Documents APIs and the admin UI are registered here as the stages of the plan
deliver them.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from opencde import __version__, health
from opencde.auth import routes as oauth2_routes
from opencde.bcf import router as bcf_router
from opencde.bootstrap import make_graph, make_storage, wait_for_graph
from opencde.errors import install_error_handlers
from opencde.etag import ETagMiddleware
from opencde.foundation import routes as foundation_routes
from opencde.graph.cleanup import ExpiryCleaner
from opencde.graph.schema import apply_schema
from opencde.logging import configure_logging, get_logger
from opencde.middleware import BodySizeLimitMiddleware, RequestIDMiddleware, SecurityHeadersMiddleware
from opencde.ratelimit import install_rate_limiting
from opencde.settings import Settings
from opencde.ui.templating import STATIC_DIR, render

DESCRIPTION = """\
Server implementation of the buildingSMART OpenCDE APIs:

* **Foundation API 1.0**: service discovery, OAuth2 authorization code with PKCE, current user.
* **BCF API 3.0**: projects, topics, comments, viewpoints, files, documents and events.
* **Documents API 1.0**: document selection, download, upload and version queries.

Data lives in a graph database (Neo4j or Memgraph). Source: https://github.com/marwiss/Kontroll
"""

OPENAPI_TAGS = [
    {"name": "Foundation API", "description": "Service discovery and authentication (Foundation API 1.0)."},
    {"name": "BCF API", "description": "Issue management (BCF API 3.0)."},
    {"name": "Documents API", "description": "Document exchange (Documents API 1.0)."},
    {"name": "operations", "description": "Health endpoints for containers and monitoring."},
]


def create_app(settings: Settings | None = None, *, startup_wait_seconds: float = 60.0) -> FastAPI:
    settings = settings or Settings()
    configure_logging(settings.log_level, settings.log_json)
    log = get_logger(__name__)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        app.state.settings = settings
        app.state.graph = make_graph(settings)
        app.state.storage = make_storage(settings)
        cleaner = ExpiryCleaner(app.state.graph, settings.cleanup_interval_seconds)
        log.info(
            "server_starting",
            version=__version__,
            environment=settings.environment,
            public_url=settings.public_url,
            graph_dialect=settings.graph_dialect.value,
            graph_database=settings.database_name,
        )
        if startup_wait_seconds > 0:
            await wait_for_graph(app.state.graph, startup_wait_seconds)
            await apply_schema(app.state.graph)
            cleaner.start()
        try:
            yield
        finally:
            await cleaner.stop()
            await app.state.graph.close()
            log.info("server_stopped")

    app = FastAPI(
        title="Kontroll OpenCDE server",
        description=DESCRIPTION,
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url=None,
        openapi_tags=OPENAPI_TAGS,
        license_info={"name": "AGPL-3.0-or-later", "url": "https://www.gnu.org/licenses/agpl-3.0.html"},
    )

    install_error_handlers(app)
    install_rate_limiting(app, settings.rate_limits_enabled)

    # Middleware runs outermost-last: request id first, then size limit, CORS, ETag, headers on the way out.
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(ETagMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Accept", "If-None-Match", "X-Request-ID"],
        expose_headers=["ETag", "Location", "X-Request-ID"],
        max_age=600,
    )
    app.add_middleware(
        BodySizeLimitMiddleware,
        max_bytes=settings.max_json_body_bytes,
        exempt_prefixes=("/documents/1.0/upload-part/", "/bcf/3.0/projects/"),
    )
    app.add_middleware(RequestIDMiddleware)

    app.include_router(health.router)
    app.include_router(foundation_routes.router)
    app.include_router(foundation_routes.alias_router)
    app.include_router(oauth2_routes.router)
    app.include_router(bcf_router.router)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/", include_in_schema=False, response_class=HTMLResponse)
    async def index(request: Request) -> HTMLResponse:
        return render(request, "index.html", {"version": __version__, "admin_enabled": settings.admin_ui_enabled})

    return app
