# This file was generated with the assistance of an AI coding tool.
"""Projects, their members and their BCF extensions.

A ``Project`` node is the BCF project (BCF 3.1). Its ``Extensions`` node
holds the value lists clients may use for topic types, statuses, labels,
priorities and stages (BCF 3.1.4). The ``users`` list of the extensions is
not stored: it is the project's members at the time of the request.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from opencde.accounts.roles import Role
from opencde.accounts.users import PUBLIC_FIELDS, AccountError, User, _user
from opencde.graph.graph import Graph
from opencde.ids import is_uuid, new_id, normalize_guid
from opencde.timeutil import now_iso

MAX_NAME = 200
MAX_LIST_ITEMS = 200
MAX_ITEM_LENGTH = 100

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
    "snippet_type": [".ifc", ".bcf", ".csv", ".json"],
    "priority": ["Low", "Medium", "High", "Critical"],
    "stage": ["Design", "Construction", "Completion", "Operation"],
    "custom_information": [],
}


@dataclass(frozen=True)
class Project:
    project_id: str
    name: str
    created_at: str


def _project(row: dict[str, Any]) -> Project:
    return Project(project_id=row["project_id"], name=row["name"], created_at=row["created_at"])


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

    async def delete(self, project_id: str) -> bool:
        """Delete the project and everything hanging off it (topics, documents metadata, sessions)."""

        async def work(tx: Any) -> int:
            counters = await tx.counters(
                """
                MATCH (p:Project {project_id: $id})
                OPTIONAL MATCH (p)-[*1..4]->(child)
                WITH p, collect(DISTINCT child) AS children
                FOREACH (c IN children | DETACH DELETE c)
                DETACH DELETE p
                """,
                id=project_id,
            )
            return counters.nodes_deleted

        return await self.graph.write(work) > 0

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
