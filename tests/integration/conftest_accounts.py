# This file was generated with the assistance of an AI coding tool.
"""Account fixtures shared by API tests: a project with members, and OAuth2 clients.

Created synchronously through the app's own repositories in a short-lived
event loop *before* the TestClient starts, so the app's driver is untouched.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from fastapi.testclient import TestClient

from opencde.accounts.projects import ProjectRepository
from opencde.accounts.roles import Role
from opencde.accounts.users import UserRepository
from opencde.auth.clients import ClientRepository
from opencde.bootstrap import make_graph
from opencde.graph.schema import apply_schema
from opencde.settings import Settings
from tests.integration.helpers import Session, sign_in

PASSWORD = "a-long-and-strong-passphrase"
REDIRECT = "http://127.0.0.1/callback"


@dataclass
class World:
    project_id: str
    other_project_id: str
    public_client_id: str
    confidential_client_id: str
    confidential_secret: str
    users: dict[str, str]  # username -> user id

    @property
    def password(self) -> str:
        return PASSWORD

    @property
    def redirect(self) -> str:
        return REDIRECT


async def _build(settings: Settings) -> World:
    graph = make_graph(settings)
    try:
        await apply_schema(graph)
        users = UserRepository(graph)
        projects = ProjectRepository(graph)
        clients = ClientRepository(graph)
        ids = {}
        for name, admin in (
            ("admin", True),
            ("manager", False),
            ("editor", False),
            ("contributor", False),
            ("viewer", False),
            ("outsider", False),
        ):
            ids[name] = (await users.create(name, PASSWORD, full_name=name.title(), is_admin=admin)).id
        project = await projects.create("Building permit")
        other = await projects.create("Demolition permit")
        await projects.set_member(project.project_id, ids["manager"], Role.MANAGER)
        await projects.set_member(project.project_id, ids["editor"], Role.EDITOR)
        await projects.set_member(project.project_id, ids["contributor"], Role.CONTRIBUTOR)
        await projects.set_member(project.project_id, ids["viewer"], Role.VIEWER)
        await projects.set_member(other.project_id, ids["outsider"], Role.MANAGER)
        public, _ = await clients.create("Native app", [REDIRECT, "http://127.0.0.1/other"], public=True)
        confidential, secret = await clients.create("Server app", [REDIRECT], public=False)
        return World(
            project_id=project.project_id,
            other_project_id=other.project_id,
            public_client_id=public.client_id,
            confidential_client_id=confidential.client_id,
            confidential_secret=secret or "",
            users=ids,
        )
    finally:
        await graph.close()


def build_world(settings: Settings) -> World:
    return asyncio.run(_build(settings))


def login_as(client: TestClient, world: World, username: str) -> Session:
    """Sign ``username`` in through the public client and return the bearer session."""
    return sign_in(
        client,
        client_id=world.public_client_id,
        redirect_uri=world.redirect,
        username=username,
        password=world.password,
    )
