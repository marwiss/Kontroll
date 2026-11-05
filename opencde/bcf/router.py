# This file was generated with the assistance of an AI coding tool.
"""All BCF API routers in one place, in the order the specification lists the services."""

from __future__ import annotations

from fastapi import APIRouter

from opencde.bcf import routes_projects, routes_topics

router = APIRouter()
router.include_router(routes_projects.router)
router.include_router(routes_topics.router)
