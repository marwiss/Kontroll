# This file was generated with the assistance of an AI coding tool.
"""Application factory.

``create_app()`` wires settings, logging, middleware, error handling and the
routers together. Routers for the Foundation, BCF and Documents APIs are
registered here as the stages of the plan deliver them.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from opencde import __version__, health
from opencde.errors import install_error_handlers
from opencde.graph.driver import create_driver
from opencde.logging import configure_logging, get_logger
from opencde.middleware import BodySizeLimitMiddleware, RequestIDMiddleware, SecurityHeadersMiddleware
from opencde.settings import Settings

DESCRIPTION = """\
Server implementation of the buildingSMART OpenCDE APIs:

* **Foundation API 1.0**: service discovery, OAuth2 authorization code with PKCE, current user.
* **BCF API 3.0**: projects, topics, comments, viewpoints, files, documents and events.
* **Documents API 1.0**: document selection, download, upload and version queries.

Data lives in a graph database (Neo4j or Memgraph). Source: https://github.com/marwiss/Kontroll
"""


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    configure_logging(settings.log_level, settings.log_json)
    log = get_logger(__name__)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        app.state.settings = settings
        app.state.driver = create_driver(settings)
        log.info(
            "server_starting",
            version=__version__,
            environment=settings.environment,
            public_url=settings.public_url,
            graph_dialect=settings.graph_dialect.value,
            graph_database=settings.database_name,
        )
        try:
            yield
        finally:
            await app.state.driver.close()
            log.info("server_stopped")

    app = FastAPI(
        title="Kontroll OpenCDE server",
        description=DESCRIPTION,
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url=None,
        license_info={"name": "AGPL-3.0-or-later", "url": "https://www.gnu.org/licenses/agpl-3.0.html"},
    )

    install_error_handlers(app)

    # Middleware runs outermost-last: request id first, then size limit, then CORS, then headers on the way out.
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Accept", "If-None-Match", "X-Request-ID"],
        expose_headers=["ETag", "Location", "X-Request-ID"],
        max_age=600,
    )
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.max_json_body_bytes)
    app.add_middleware(RequestIDMiddleware)

    app.include_router(health.router)

    @app.get("/", include_in_schema=False)
    async def index() -> dict[str, str]:
        return {
            "name": "Kontroll OpenCDE server",
            "version": __version__,
            "docs": "/docs",
            "versions": "/foundation/versions",
        }

    return app
