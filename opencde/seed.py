# This file was generated with the assistance of an AI coding tool.
"""Demonstration data.

The seed tells the story the server was built for: a municipality's building
permit with the people around it. Five users named after their roles in a
Swedish building-permit process, two projects, OAuth2 clients to try the API
with, the sample model with three walls as a document, and one topic with a
viewpoint on the first wall and a comment. It only runs into an empty
database, and it prints the generated passwords exactly once.

The ids of the seeded document, topic, viewpoint and comment are fixed
(``SEED_*`` below), so that clients and their test suites, Dataspatium's among
them, can refer to them; the model's wall GlobalIds and GTINs are in
``SAMPLE_MODEL_WALLS``.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from pathlib import Path

from opencde.accounts.projects import ProjectRepository
from opencde.accounts.roles import Role
from opencde.accounts.users import UserRepository
from opencde.auth.clients import ClientRepository
from opencde.bcf.comments import CommentRepository
from opencde.bcf.schemas import (
    CommentPOST,
    Component,
    Components,
    Direction,
    PerspectiveCamera,
    Point,
    TopicPOST,
    ViewpointPOST,
    Visibility,
)
from opencde.bcf.topics import TopicRepository
from opencde.bcf.viewpoints import ViewpointRepository
from opencde.documents.assembly import store_stream
from opencde.documents.repository import DocumentRepository, default_metadata
from opencde.graph.graph import Graph
from opencde.ids import new_id
from opencde.ifcgraph.service import IfcGraphService
from opencde.settings import Settings
from opencde.storage import LocalStorage, make_key
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

# Known ids, shared with client test suites (docs/client-guide.md §7).
SEED_DOCUMENT_ID = "6f5d3b2a-0000-4000-8000-000000000001"
SEED_TOPIC_GUID = "6f5d3b2a-0000-4000-8000-000000000002"
SEED_VIEWPOINT_GUID = "6f5d3b2a-0000-4000-8000-000000000003"
SEED_COMMENT_GUID = "6f5d3b2a-0000-4000-8000-000000000004"

# The sample model: an IFC2X3 Archicad export with three walls that carry property set Reuse / GTIN.
# tests/fixtures/three_walls_gtin.ifc is the same file; a test keeps the two identical.
SAMPLE_MODEL = Path(__file__).with_name("seed_data") / "three_walls_gtin.ifc"
SAMPLE_MODEL_FILE_NAME = "three_walls_gtin.ifc"
SAMPLE_MODEL_WALLS: dict[str, int] = {  # IfcWallStandardCase GlobalId -> GTIN
    "1Xezbq735AdBO_4DerG66G": 3,
    "3eT96F_cnDsOufCEsotwtp": 2,
    "3k3LbXmTfDWODxdSuyCGYE": 1,
}
SAMPLE_MODEL_MAX_BYTES = 1_048_576


@dataclass
class SeedResult:
    passwords: dict[str, str] = field(default_factory=dict)
    projects: dict[str, str] = field(default_factory=dict)
    public_client_id: str = ""
    confidential_client_id: str = ""
    confidential_client_secret: str = ""
    document_id: str = SEED_DOCUMENT_ID
    topic_guid: str = SEED_TOPIC_GUID
    viewpoint_guid: str = SEED_VIEWPOINT_GUID
    comment_guid: str = SEED_COMMENT_GUID
    sample_model_key: str = ""


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
    storage: LocalStorage,
    shared_password: str | None = None,
    public_redirects: list[str] | None = None,
    allow_localhost_redirects: bool = False,
    id_prefix: str = "ISSUE-",
    max_image_bytes: int = 10_485_760,
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

    result.sample_model_key = await _seed_content(
        graph, storage, building_permit.project_id, id_prefix=id_prefix, max_image_bytes=max_image_bytes
    )
    return result


async def build_sample_graph(graph: Graph, storage: LocalStorage, settings: Settings, result: SeedResult) -> dict:
    """The sample model as a graph, and checked against the IFC schema, as if it had been uploaded.

    Returns its ``IfcModel`` node's properties.
    """
    service = IfcGraphService(graph, storage, settings)
    project_id = result.projects["Building permit"]
    version = await graph.one(
        "MATCH (:Document {document_id: $id})-[:HAS_VERSION]->(v:DocumentVersion {version_index: 1}) RETURN v.id AS id",
        id=SEED_DOCUMENT_ID,
    )
    await service.schedule(
        project_id=project_id,
        storage_key=result.sample_model_key,
        file_name=SAMPLE_MODEL_FILE_NAME,
        document_id=SEED_DOCUMENT_ID,
        version_index=1,
        version_id=version["id"] if version else None,
    )
    await service.wait_idle()
    return (await service.status(project_id))[0]


async def _seed_content(
    graph: Graph, storage: LocalStorage, project_id: str, *, id_prefix: str, max_image_bytes: int
) -> str:
    """The sample model as a document, and a topic with a viewpoint on its first wall and a comment.

    Returns where the model is stored.
    """
    documents = DocumentRepository(graph)
    key = make_key("documents", new_id())
    with SAMPLE_MODEL.open("rb") as source:
        size, sha256 = store_stream(storage, source, key, SAMPLE_MODEL_MAX_BYTES)
    await documents.create_version(
        project_id=project_id,
        document_id=None,
        requested_document_id=SEED_DOCUMENT_ID,
        title="Three walls (sample model)",
        version_number="1",
        file_name=SAMPLE_MODEL_FILE_NAME,
        size_in_bytes=size,
        sha256=sha256,
        storage_key=key,
        author="officer",
        metadata=default_metadata(
            file_name=SAMPLE_MODEL_FILE_NAME,
            size_in_bytes=size,
            sha256=sha256,
            author="officer",
            project_name="Building permit",
        ),
    )

    topics = TopicRepository(graph, id_prefix=id_prefix)
    first_wall = next(iter(SAMPLE_MODEL_WALLS))
    await topics.create(
        project_id=project_id,
        author="officer",
        body=TopicPOST(
            guid=SEED_TOPIC_GUID,
            title="Check the reuse marking of the first wall",
            topic_type="Inspection",
            topic_status="Open",
            priority="Medium",
            labels=["Reuse"],
            assigned_to="inspector",
            description=f"The wall {first_wall} carries GTIN {SAMPLE_MODEL_WALLS[first_wall]} in property set "
            "Reuse. Confirm the marking on site before the inspection.",
        ),
    )
    viewpoints = ViewpointRepository(graph, storage, topics, max_image_bytes=max_image_bytes)
    await viewpoints.create(
        project_id=project_id,
        topic_guid=SEED_TOPIC_GUID,
        author="officer",
        body=ViewpointPOST(
            guid=SEED_VIEWPOINT_GUID,
            perspective_camera=PerspectiveCamera(
                camera_view_point=Point(x=8.0, y=-6.0, z=4.0),
                camera_direction=Direction(x=-0.6, y=0.7, z=-0.3),
                camera_up_vector=Direction(x=0.0, y=0.0, z=1.0),
                field_of_view=60.0,
                aspect_ratio=1.5,
            ),
            components=Components(
                selection=[Component(ifc_guid=first_wall, originating_system="Kontroll seed")],
                visibility=Visibility(default_visibility=True),
            ),
        ),
    )
    comments = CommentRepository(graph, topics)
    await comments.create(
        project_id=project_id,
        topic_guid=SEED_TOPIC_GUID,
        author="inspector",
        body=CommentPOST(
            guid=SEED_COMMENT_GUID,
            comment="Marking found on the wall, photo attached to the inspection plan.",
            viewpoint_guid=SEED_VIEWPOINT_GUID,
        ),
    )
    return key
