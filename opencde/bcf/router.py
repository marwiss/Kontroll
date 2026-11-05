# This file was generated with the assistance of an AI coding tool.
"""All BCF API routers in one place.

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
    routes_topic_links,
    routes_topics,
    routes_viewpoints,
)

# Routes whose request body is a file rather than JSON: they stream and count bytes themselves
# (``opencde.bcf.binary.receive_upload``) and are exempt from the JSON body size limit.
BINARY_UPLOAD_PATHS = (
    r"^/bcf/3\.0/projects/[^/]+/documents$",
    r"^/bcf/3\.0/projects/[^/]+/topics/[^/]+/snippet$",
)

router = APIRouter()
router.include_router(routes_projects.router)
router.include_router(routes_events.router)
router.include_router(routes_topics.router)
router.include_router(routes_comments.router)
router.include_router(routes_viewpoints.router)
router.include_router(routes_topic_links.router)
router.include_router(routes_documents.router)
