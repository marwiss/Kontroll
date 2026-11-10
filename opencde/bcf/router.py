# This file was generated with the assistance of an AI coding tool.
"""All BCF API routers in one place: 3.0 under ``/bcf/3.0`` and 2.1 under ``/bcf/2.1``, on the same data.

The events router goes first so that ``/topics/events`` and
``/topics/comments/events`` are matched before ``/topics/{topic_id}``.
"""

from __future__ import annotations

from fastapi import APIRouter

from opencde.bcf import (
    routes_comments,
    routes_documents,
    routes_events,
    routes_projects,
    routes_proposals,
    routes_topic_links,
    routes_topics,
    routes_v21,
    routes_viewpoints,
)

# Routes whose request body is a file rather than JSON: they stream and count bytes themselves
# (``opencde.bcf.binary.receive_upload``) and are exempt from the JSON body size limit.
BINARY_UPLOAD_PATHS = (
    r"^/bcf/(?:3\.0|2\.1)/projects/[^/]+/documents$",
    r"^/bcf/(?:3\.0|2\.1)/projects/[^/]+/topics/[^/]+/snippet$",
)

v30 = APIRouter(prefix="/bcf/3.0")
v30.include_router(routes_projects.router)
v30.include_router(routes_events.router)
v30.include_router(routes_topics.router)
v30.include_router(routes_comments.router)
v30.include_router(routes_viewpoints.router)
v30.include_router(routes_topic_links.router)
v30.include_router(routes_proposals.router)
v30.include_router(routes_documents.router)

v21 = routes_v21.router
versions = routes_v21.public_router  # GET /bcf/versions, served when either version is (OPENCDE_APIS)

router = APIRouter()
router.include_router(v30)
router.include_router(v21)
router.include_router(versions)
