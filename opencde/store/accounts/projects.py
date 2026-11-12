# This file was generated with the assistance of an AI coding tool.
"""Projects, their members and their BCF extensions.

A ``Project`` node is the BCF project (BCF 3.1). Its ``Extensions`` node
holds the value lists clients may use for topic types, statuses, labels,
priorities and stages (BCF 3.1.4). The ``users`` list of the extensions is
not stored: it is the project's members at the time of the request.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from typing import Any, Literal, get_args

from opencde.accounts.roles import Role
from opencde.graph.graph import Graph
from opencde.ids import is_uuid, new_id, normalize_guid
from opencde.ifcgraph.maintenance import delete_geometry
from opencde.storage import LocalStorage
from opencde.store.accounts.users import PUBLIC_FIELDS, AccountError, User, _user
from opencde.timeutil import now_iso

MAX_NAME = 200
MAX_LIST_ITEMS = 200
MAX_ITEM_LENGTH = 100

# Where AI tools may take a project's data (F29 a, F30 a, ADR 0028): `local` only to the user's own computer, through
# the local engine or a local model, `cloud` to AI services in the cloud as well. Anything but `cloud` reads as
# `local`, so a project nobody has set, new or from an earlier release, stays local.
AiPolicy = Literal["local", "cloud"]
AI_POLICIES: tuple[str, ...] = get_args(AiPolicy)
DEFAULT_AI_POLICY: AiPolicy = "local"

# What a project owns: the relationships that deleting it follows, and no others. CREATED_BY and UPLOADED_BY lead to
# users, and from a user MEMBER_OF leads to every project the user is in. RELATED_TO and CONCERNS point at what need
# not be this project's alone. A new kind of node below a project needs its relationship here.
OWNED_RELATIONSHIPS = (
    "HAS_EXTENSIONS",
    "HAS_TOPIC",
    "HAS_PROPOSAL",
    "HAS_EVENT",
    "HAS_COMMENT",
    "HAS_VIEWPOINT",
    "HAS_COMPONENT",
    "HAS_BITMAP",
    "HAS_FILE",
    "HAS_DOCUMENT_REFERENCE",
    "HAS_DOCUMENT",
    "HAS_VERSION",
    "HAS_VALIDATION",
    "HAS_PRECHECK",
    "HAS_CONVERSION",
    "HAS_CLASH",
    "HAS_PUBLICATION",
    "HAS_MERGE",
    "HAS_TEAM",
    "HAS_DRAFT",
)

EXTENSION_LISTS = (
    "topic_type",
    "topic_status",
    "topic_label",
    "snippet_type",
    "priority",
    "stage",
    "custom_information",
)

DEFAULT_EXTENSIONS: dict[str, list[str]] = {
    "topic_type": ["Issue", "Request", "Question", "Information", "Inspection"],
    "topic_status": ["Open", "In progress", "Resolved", "Closed"],
    "topic_label": ["Architecture", "Structural", "MEP", "Safety", "Reuse"],
    "snippet_type": [".ifc", ".bcf", ".csv", ".json", "DataregiumIfcChangeSet"],
    "priority": ["Low", "Medium", "High", "Critical"],
    "stage": ["Design", "Construction", "Completion", "Operation"],
    "custom_information": [],
}


@dataclass(frozen=True)
class Project:
    project_id: str
    name: str
    created_at: str
    # Uploads with errors against the IFC schema or the project's rules are refused (ADR 0021).
    block_on_validation_errors: bool = False
    ai_policy: AiPolicy = DEFAULT_AI_POLICY


def _project(row: dict[str, Any]) -> Project:
    return Project(
        project_id=row["project_id"],
        name=row["name"],
        created_at=row["created_at"],
        block_on_validation_errors=bool(row.get("block_on_validation_errors")),
        ai_policy="cloud" if row.get("ai_policy") == "cloud" else DEFAULT_AI_POLICY,
    )


def _clean_list(name: str, values: list[str]) -> list[str]:
    cleaned: list[str] = []
    for value in values:
        if not isinstance(value, str):
            raise AccountError(f"{name}: values must be strings", key="error.project.values_strings", name=name)
        value = value.strip()
        if not value or len(value) > MAX_ITEM_LENGTH:
            raise AccountError(
                f"{name}: values must be 1-{MAX_ITEM_LENGTH} characters",
                key="error.project.values_length",
                name=name,
                max=MAX_ITEM_LENGTH,
            )
        if value not in cleaned:
            cleaned.append(value)
    if len(cleaned) > MAX_LIST_ITEMS:
        raise AccountError(
            f"{name}: at most {MAX_LIST_ITEMS} values",
            key="error.project.too_many_values",
            name=name,
            max=MAX_LIST_ITEMS,
        )
    return cleaned


class ProjectRepository:
    def __init__(self, graph: Graph) -> None:
        self.graph = graph

    async def create(
        self, name: str, *, project_id: str | None = None, extensions: dict[str, list[str]] | None = None
    ) -> Project:
        name = name.strip()
        if not name or len(name) > MAX_NAME:
            raise AccountError(f"project name: 1-{MAX_NAME} characters", key="error.project.name_length", max=MAX_NAME)
        if project_id is not None:
            if not is_uuid(project_id):
                raise AccountError("project_id must be a UUID", key="error.project.id_uuid")
            project_id = normalize_guid(project_id)
            if await self.get(project_id):
                raise AccountError("project_id already exists", key="error.project.id_exists")
        values = {
            key: _clean_list(key, (extensions or {}).get(key, DEFAULT_EXTENSIONS[key])) for key in EXTENSION_LISTS
        }
        row = await self.graph.one(
            """
            CREATE (p:Project {project_id: $project_id, name: $name, created_at: $now, topic_counter: 0})
            CREATE (p)-[:HAS_EXTENSIONS]->(e:Extensions {
                id: $ext_id, topic_type: $topic_type, topic_status: $topic_status, topic_label: $topic_label,
                snippet_type: $snippet_type, priority: $priority, stage: $stage, custom_information: $custom_information
            })
            RETURN properties(p) AS project
            """,
            project_id=project_id or new_id(),
            name=name,
            now=now_iso(),
            ext_id=new_id(),
            **values,
        )
        if row is None:  # CREATE always returns a row; this guards the type checker and a broken driver
            raise AccountError("project was not created", key="error.project.not_created")
        return _project(row["project"])

    async def get(self, project_id: str) -> Project | None:
        row = await self.graph.one("MATCH (p:Project {project_id: $id}) RETURN properties(p) AS project", id=project_id)
        return _project(row["project"]) if row else None

    async def all(self) -> list[Project]:
        rows = await self.graph.run("MATCH (p:Project) RETURN properties(p) AS project ORDER BY p.name")
        return [_project(row["project"]) for row in rows]

    async def list_for_user(self, user_id: str) -> list[tuple[Project, Role]]:
        rows = await self.graph.run(
            """
            MATCH (:User {id: $user_id})-[m:MEMBER_OF]->(p:Project)
            RETURN properties(p) AS project, m.role AS role
            ORDER BY p.name
            """,
            user_id=user_id,
        )
        return [(_project(row["project"]), Role(row["role"])) for row in rows]

    async def rename(self, project_id: str, name: str) -> Project:
        name = name.strip()
        if not name or len(name) > MAX_NAME:
            raise AccountError(f"project name: 1-{MAX_NAME} characters", key="error.project.name_length", max=MAX_NAME)
        row = await self.graph.one(
            "MATCH (p:Project {project_id: $id}) SET p.name = $name RETURN properties(p) AS project",
            id=project_id,
            name=name,
        )
        if row is None:
            raise AccountError("no such project", key="error.project.not_found")
        return _project(row["project"])

    async def set_block_on_validation_errors(self, project_id: str, value: bool) -> Project:
        row = await self.graph.one(
            "MATCH (p:Project {project_id: $id}) SET p.block_on_validation_errors = $value RETURN properties(p) AS project",
            id=project_id,
            value=bool(value),
        )
        if row is None:
            raise AccountError("no such project", key="error.project.not_found")
        return _project(row["project"])

    async def set_ai_policy(self, project_id: str, value: str) -> Project:
        if value not in AI_POLICIES:
            raise AccountError("ai_policy: local or cloud", key="error.project.ai_policy")
        row = await self.graph.one(
            "MATCH (p:Project {project_id: $id}) SET p.ai_policy = $value RETURN properties(p) AS project",
            id=project_id,
            value=value,
        )
        if row is None:
            raise AccountError("no such project", key="error.project.not_found")
        return _project(row["project"])

    async def model_ids(self, project_id: str) -> list[str]:
        """The ids of the project's IFC models, by its conversions. The models live in the IFC graph, apart from the
        store (ADR 0027), so the caller that has both deletes them first (``ifcgraph.maintenance.delete_project``)."""
        rows = await self.graph.run(
            "MATCH (:Project {project_id: $id})-[:HAS_CONVERSION]->(c:Conversion) RETURN c.model_id AS id",
            id=project_id,
        )
        return [str(row["id"]) for row in rows if row["id"]]

    async def delete(self, project_id: str) -> bool:
        """Delete the project and what it owns (``OWNED_RELATIONSHIPS``): topics, documents and their metadata.

        Its IFC models are not here but in the IFC graph, and go before it (``model_ids``).
        """

        async def work(tx: Any) -> int:
            counters = await tx.counters(
                """
                MATCH (p:Project {project_id: $id})
                OPTIONAL MATCH path = (p)-[*1..4]->(child)
                WHERE all(r IN relationships(path) WHERE type(r) IN $owned)
                WITH p, collect(DISTINCT child) AS children
                FOREACH (c IN children | DETACH DELETE c)
                DETACH DELETE p
                """,
                id=project_id,
                owned=list(OWNED_RELATIONSHIPS),
            )
            return counters.nodes_deleted

        return await self.graph.write(work) > 0

    async def delete_with_files(self, project_id: str, storage: LocalStorage) -> bool:
        """``delete``, and the stored files the project owned, so that deleting it frees the disk too."""
        keys = await self.storage_keys(project_id)
        models = await self.model_ids(project_id)
        deleted = await self.delete(project_id)
        for model_id in models:
            with contextlib.suppress(OSError):
                delete_geometry(storage, model_id)
        for key in keys:
            with contextlib.suppress(ValueError):  # a key the storage refuses was never one it wrote
                storage.delete(key)
        return deleted

    async def storage_keys(self, project_id: str) -> list[str]:
        """Every stored file the project owns, so that deleting the project frees the disk too."""
        rows = await self.graph.run(
            """
            MATCH path = (:Project {project_id: $id})-[*1..4]->(n)
            WHERE all(r IN relationships(path) WHERE type(r) IN $owned)
              AND (n.storage_key IS NOT NULL OR n.snippet_storage_key IS NOT NULL)
            RETURN DISTINCT coalesce(n.storage_key, n.snippet_storage_key) AS key
            """,
            id=project_id,
            owned=list(OWNED_RELATIONSHIPS),
        )
        return [row["key"] for row in rows if row["key"]]

    # -- members ----------------------------------------------------------------

    async def set_member(self, project_id: str, user_id: str, role: Role) -> None:
        row = await self.graph.one(
            """
            MATCH (u:User {id: $user_id}), (p:Project {project_id: $project_id})
            MERGE (u)-[m:MEMBER_OF]->(p)
            SET m.role = $role, m.since = coalesce(m.since, $now)
            RETURN m.role AS role
            """,
            user_id=user_id,
            project_id=project_id,
            role=role.value,
            now=now_iso(),
        )
        if row is None:
            raise AccountError("no such user or project", key="error.project.member_not_found")

    async def remove_member(self, project_id: str, user_id: str) -> bool:
        counters = await self.graph.write(
            lambda tx: tx.counters(
                "MATCH (:User {id: $user_id})-[m:MEMBER_OF]->(:Project {project_id: $project_id}) DELETE m",
                user_id=user_id,
                project_id=project_id,
            )
        )
        return counters.relationships_deleted > 0

    async def members(self, project_id: str) -> list[tuple[User, Role]]:
        rows = await self.graph.run(
            f"""
            MATCH (u:User)-[m:MEMBER_OF]->(:Project {{project_id: $project_id}})
            RETURN {PUBLIC_FIELDS} AS user, m.role AS role
            ORDER BY u.username
            """,
            project_id=project_id,
        )
        return [(_user(row["user"]), Role(row["role"])) for row in rows]

    # -- extensions ---------------------------------------------------------------

    async def extensions(self, project_id: str) -> dict[str, list[str]] | None:
        row = await self.graph.one(
            """
            MATCH (p:Project {project_id: $id})-[:HAS_EXTENSIONS]->(e:Extensions)
            OPTIONAL MATCH (u:User)-[:MEMBER_OF]->(p)
            WITH e, collect(u.username) AS users
            RETURN properties(e) AS ext, users
            """,
            id=project_id,
        )
        if row is None:
            return None
        ext = dict(row["ext"])
        ext.pop("id", None)
        ext["users"] = sorted(row["users"])
        return ext

    async def set_extensions(self, project_id: str, values: dict[str, list[str]]) -> dict[str, list[str]]:
        unknown = set(values) - set(EXTENSION_LISTS)
        if unknown:
            names = ", ".join(sorted(unknown))
            raise AccountError(f"unknown extension lists: {names}", key="error.project.unknown_extensions", names=names)
        cleaned = {key: _clean_list(key, value) for key, value in values.items()}
        assignments = ", ".join(f"e.{key} = ${key}" for key in cleaned)
        row = await self.graph.one(
            f"MATCH (:Project {{project_id: $id}})-[:HAS_EXTENSIONS]->(e:Extensions) SET {assignments} RETURN e.id AS id",
            id=project_id,
            **cleaned,
        )
        if row is None:
            raise AccountError("no such project", key="error.project.not_found")
        result = await self.extensions(project_id)
        if result is None:
            raise AccountError("no such project", key="error.project.not_found")
        return result
