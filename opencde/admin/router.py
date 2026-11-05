# This file was generated with the assistance of an AI coding tool.
"""All admin routers, mounted under ``/admin`` when ``OPENCDE_ADMIN_UI_ENABLED`` is true."""

from __future__ import annotations

from fastapi import APIRouter

from opencde.admin import routes_clients, routes_overview, routes_projects, routes_users

router = APIRouter()
router.include_router(routes_overview.router)
router.include_router(routes_users.router)
router.include_router(routes_projects.router)
router.include_router(routes_clients.router)
