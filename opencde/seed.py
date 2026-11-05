# This file was generated with the assistance of an AI coding tool.
"""Demonstration data.

The seed tells the story the server was built for: a municipality's building
permit with the people around it. Five users named after their roles in a
Swedish building-permit process, two projects, OAuth2 clients to try the API
with, and (from stage 5) the sample model with three walls. It only runs into
an empty database, and it prints the generated passwords exactly once.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field

from opencde.accounts.projects import ProjectRepository
from opencde.accounts.roles import Role
from opencde.accounts.users import UserRepository
from opencde.auth.clients import ClientRepository
from opencde.graph.graph import Graph
from opencde.timeutil import now_iso

DEMO_USERS: tuple[tuple[str, str, str, bool], ...] = (
    # username, full name, e-mail, is_admin
    ("admin", "Server administrator", "admin@example.test", True),
    ("officer", "Municipal building officer", "officer@municipality.example.test", False),
    ("developer", "Building developer", "developer@builder.example.test", False),
    ("inspection_manager", "Certified inspection manager", "inspection.manager@consult.example.test", False),
    ("inspector", "Site inspector", "inspector@builder.example.test", False),
)

BUILDING_PERMIT_EXTENSIONS = {
    "topic_type": ["Issue", "Request", "Question", "Information", "Inspection"],
    "topic_status": ["Open", "In progress", "Resolved", "Closed", "Custom test status"],
    "topic_label": ["Architecture", "Structural", "MEP", "Safety", "Reuse"],
    "snippet_type": [".ifc", ".bcf", ".csv", ".json"],
    "priority": ["Low", "Medium", "High", "Critical"],
    "stage": ["Preliminary planning end", "Construction start", "Construction end"],
    "custom_information": ["Custom value 1", "Custom value 2"],
}


@dataclass
class SeedResult:
    passwords: dict[str, str] = field(default_factory=dict)
    projects: dict[str, str] = field(default_factory=dict)
    public_client_id: str = ""
    confidential_client_id: str = ""
    confidential_client_secret: str = ""


class SeedError(RuntimeError):
    pass


async def is_empty(graph: Graph) -> bool:
    row = await graph.one("MATCH (n) RETURN count(n) AS n")
    return not row or int(row["n"]) == 0


async def wipe(graph: Graph) -> None:
    """Delete every node and relationship, in batches. Only for development and tests."""
    while True:
        rows = await graph.run("MATCH (n) WITH n LIMIT 2000 DETACH DELETE n RETURN count(*) AS n")
        if not rows or int(rows[0]["n"]) == 0:
            break


async def seed(
    graph: Graph,
    *,
    shared_password: str | None = None,
    public_redirects: list[str] | None = None,
    allow_localhost_redirects: bool = False,
) -> SeedResult:
    if not await is_empty(graph):
        raise SeedError("the database is not empty; seeding only runs into an empty database")

    users = UserRepository(graph)
    projects = ProjectRepository(graph)
    clients = ClientRepository(graph, allow_localhost_redirects=allow_localhost_redirects)
    result = SeedResult()

    created = {}
    for username, full_name, email, is_admin in DEMO_USERS:
        password = shared_password or secrets.token_urlsafe(12)
        created[username] = await users.create(username, password, email=email, full_name=full_name, is_admin=is_admin)
        result.passwords[username] = password

    building_permit = await projects.create("Building permit", extensions=BUILDING_PERMIT_EXTENSIONS)
    demolition_permit = await projects.create("Demolition permit")
    result.projects = {
        building_permit.name: building_permit.project_id,
        demolition_permit.name: demolition_permit.project_id,
    }

    await projects.set_member(building_permit.project_id, created["officer"].id, Role.MANAGER)
    await projects.set_member(building_permit.project_id, created["developer"].id, Role.CONTRIBUTOR)
    await projects.set_member(building_permit.project_id, created["inspection_manager"].id, Role.EDITOR)
    await projects.set_member(building_permit.project_id, created["inspector"].id, Role.CONTRIBUTOR)
    await projects.set_member(demolition_permit.project_id, created["officer"].id, Role.MANAGER)
    await projects.set_member(demolition_permit.project_id, created["developer"].id, Role.CONTRIBUTOR)

    # Context nodes from the inspection-plan use case: the reviewing organisation (a municipality in the
    # original story, hence the name) that issues the permit, and the building it concerns.
    await graph.run(
        """
        MATCH (p:Project {project_id: $project_id})
        CREATE (r:Reviewer {id: $reviewer_id, name: 'Example Municipality', created_at: $now})
        CREATE (b:Building {id: $building_id, status: 'Under construction', created_at: $now})
        CREATE (r)-[:ISSUES]->(p)
        CREATE (p)-[:CONCERNS]->(b)
        """,
        project_id=building_permit.project_id,
        reviewer_id=secrets.token_hex(16),
        building_id=secrets.token_hex(16),
        now=now_iso(),
    )

    redirects = public_redirects or ["http://127.0.0.1/callback"]
    public_client, _ = await clients.create(
        "Demo public client",
        redirects,
        public=True,
        description="For native apps and scripts: PKCE, no secret. Loopback redirect, any port.",
        created_by=created["admin"].id,
    )
    confidential_client, secret = await clients.create(
        "Demo confidential client",
        ["https://client.example.test/callback", *redirects],
        public=False,
        description="For server-side applications that can keep a secret.",
        created_by=created["admin"].id,
    )
    result.public_client_id = public_client.client_id
    result.confidential_client_id = confidential_client.client_id
    result.confidential_client_secret = secret or ""
    return result
