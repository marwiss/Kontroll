# This file was generated with the assistance of an AI coding tool.
"""Documents and their versions.

A ``Document`` belongs to a project and has one or more ``DocumentVersion``
nodes with increasing ``version_index``. The file bytes live in storage under
``documents/<version id>``; the node keeps name, size, SHA-256 and metadata.
Every read starts at the user and walks ``MEMBER_OF`` to the project, so a
document in a project the caller is not a member of does not exist (404).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, HTTPException

from opencde.deps import GraphDep
from opencde.documents.links import version_links
from opencde.documents.schemas import DocumentMetadataEntry, DocumentVersion, FileDescription
from opencde.graph.graph import Graph, Tx
from opencde.ids import new_id
from opencde.timeutil import now_iso


@dataclass(frozen=True)
class VersionRecord:
    document_id: str
    project_id: str
    project_name: str
    version_id: str
    version_index: int
    version_number: str
    creation_date: str
    title: str
    file_name: str
    size_in_bytes: int
    sha256: str
    storage_key: str
    author: str
    metadata: list[dict[str, Any]]

    @property
    def extension(self) -> str:
        name = self.file_name.lower()
        return name[name.rfind(".") :] if "." in name else ""

    def to_model(self, base: str) -> DocumentVersion:
        return DocumentVersion(
            links=version_links(base, self.document_id, self.version_index),
            version_number=self.version_number,
            version_index=self.version_index,
            creation_date=self.creation_date,
            title=self.title,
            file_description=FileDescription(name=self.file_name, size_in_bytes=self.size_in_bytes),
            document_id=self.document_id,
        )

    def metadata_entries(self) -> list[DocumentMetadataEntry]:
        return [DocumentMetadataEntry.model_validate(entry) for entry in self.metadata]


_RETURN = """
RETURN d.document_id AS document_id, p.project_id AS project_id, p.name AS project_name, properties(v) AS version
"""


def _record(row: dict[str, Any]) -> VersionRecord:
    version = row["version"]
    return VersionRecord(
        document_id=row["document_id"],
        project_id=row["project_id"],
        project_name=row["project_name"],
        version_id=version["id"],
        version_index=int(version["version_index"]),
        version_number=version["version_number"],
        creation_date=version["creation_date"],
        title=version["title"],
        file_name=version["file_name"],
        size_in_bytes=int(version["size_in_bytes"]),
        sha256=version["sha256"],
        storage_key=version["storage_key"],
        author=version["author"],
        metadata=json.loads(version.get("metadata") or "[]"),
    )


class DocumentRepository:
    def __init__(self, graph: Graph) -> None:
        self.graph = graph

    async def latest(self, *, user_id: str, document_id: str) -> VersionRecord | None:
        row = await self.graph.one(
            """
            MATCH (:User {id: $user_id})-[:MEMBER_OF]->(p:Project)-[:HAS_DOCUMENT]->(d:Document {document_id: $document_id})
                  -[:HAS_VERSION]->(v:DocumentVersion)
            WITH p, d, v ORDER BY v.version_index DESC LIMIT 1
            """
            + _RETURN,
            user_id=user_id,
            document_id=document_id,
        )
        return _record(row) if row else None

    async def version(self, *, user_id: str, document_id: str, version_index: int) -> VersionRecord | None:
        row = await self.graph.one(
            """
            MATCH (:User {id: $user_id})-[:MEMBER_OF]->(p:Project)-[:HAS_DOCUMENT]->(d:Document {document_id: $document_id})
                  -[:HAS_VERSION]->(v:DocumentVersion {version_index: $version_index})
            """
            + _RETURN,
            user_id=user_id,
            document_id=document_id,
            version_index=version_index,
        )
        return _record(row) if row else None

    async def versions(self, *, user_id: str, document_id: str) -> list[VersionRecord]:
        rows = await self.graph.run(
            """
            MATCH (:User {id: $user_id})-[:MEMBER_OF]->(p:Project)-[:HAS_DOCUMENT]->(d:Document {document_id: $document_id})
                  -[:HAS_VERSION]->(v:DocumentVersion)
            WITH p, d, v ORDER BY v.version_index
            """
            + _RETURN,
            user_id=user_id,
            document_id=document_id,
        )
        return [_record(row) for row in rows]

    async def latest_many(self, *, user_id: str, document_ids: list[str]) -> list[VersionRecord]:
        """The latest version of each listed document the user may see, in document id order."""
        rows = await self.graph.run(
            """
            MATCH (:User {id: $user_id})-[:MEMBER_OF]->(p:Project)-[:HAS_DOCUMENT]->(d:Document)
            WHERE d.document_id IN $document_ids
            MATCH (d)-[:HAS_VERSION]->(v:DocumentVersion)
            WITH p, d, v ORDER BY v.version_index DESC
            WITH p, d, collect(v)[0] AS v
            ORDER BY d.document_id
            """
            + _RETURN,
            user_id=user_id,
            document_ids=document_ids,
        )
        return [_record(row) for row in rows]

    async def latest_in_projects(self, *, user_id: str) -> list[VersionRecord]:
        """The latest version of every document in the user's projects (the selection page)."""
        rows = await self.graph.run(
            """
            MATCH (:User {id: $user_id})-[:MEMBER_OF]->(p:Project)-[:HAS_DOCUMENT]->(d:Document)-[:HAS_VERSION]->(v:DocumentVersion)
            WITH p, d, v ORDER BY v.version_index DESC
            WITH p, d, collect(v)[0] AS v
            ORDER BY p.name, p.project_id, v.title, d.document_id
            """
            + _RETURN,
            user_id=user_id,
        )
        return [_record(row) for row in rows]

    async def create_version(
        self,
        *,
        project_id: str,
        document_id: str | None,
        title: str,
        version_number: str,
        file_name: str,
        size_in_bytes: int,
        sha256: str,
        storage_key: str,
        author: str,
        metadata: list[DocumentMetadataEntry],
    ) -> VersionRecord:
        """A new document (``document_id`` None) or a new version of an existing one, in one transaction."""
        now = now_iso()
        version_id = new_id()
        new_document_id = document_id or new_id()
        metadata_json = json.dumps([entry.model_dump() for entry in metadata])

        async def work(tx: Tx) -> dict[str, Any]:
            if document_id is None:
                head = await tx.one(
                    """
                    MATCH (p:Project {project_id: $project_id})
                    CREATE (p)-[:HAS_DOCUMENT]->(d:Document {
                        document_id: $document_id, title: $title, created_at: $now, latest_index: 1
                    })
                    RETURN d.latest_index AS index
                    """,
                    project_id=project_id,
                    document_id=new_document_id,
                    title=title,
                    now=now,
                )
            else:
                head = await tx.one(
                    """
                    MATCH (:Project {project_id: $project_id})-[:HAS_DOCUMENT]->(d:Document {document_id: $document_id})
                    SET d.latest_index = coalesce(d.latest_index, 0) + 1, d.title = $title
                    RETURN d.latest_index AS index
                    """,
                    project_id=project_id,
                    document_id=document_id,
                    title=title,
                )
            if head is None:
                raise HTTPException(404, "Document not found")
            index = int(head["index"])
            row = await tx.one(
                """
                MATCH (p:Project {project_id: $project_id})-[:HAS_DOCUMENT]->(d:Document {document_id: $document_id}),
                      (u:User {username: $author})
                CREATE (d)-[:HAS_VERSION]->(v:DocumentVersion {
                    id: $id, version_index: $index, version_number: $version_number, creation_date: $now,
                    title: $title, file_name: $file_name, size_in_bytes: $size, sha256: $sha256,
                    storage_key: $storage_key, author: $author, metadata: $metadata
                })
                CREATE (v)-[:UPLOADED_BY]->(u)
                """
                + _RETURN,
                project_id=project_id,
                document_id=new_document_id,
                author=author,
                id=version_id,
                index=index,
                version_number=version_number or str(index),
                now=now,
                title=title,
                file_name=file_name,
                size=size_in_bytes,
                sha256=sha256,
                storage_key=storage_key,
                metadata=metadata_json,
            )
            if row is None:
                raise HTTPException(404, "Project not found")
            return row

        return _record(await self.graph.write(work))


def default_metadata(
    *, file_name: str, size_in_bytes: int, sha256: str, author: str, project_name: str
) -> list[DocumentMetadataEntry]:
    """The metadata every version carries (Documents API ``DocumentMetadata``)."""
    return [
        DocumentMetadataEntry(name="file_name", value=[file_name], data_type="string"),
        DocumentMetadataEntry(name="size_in_bytes", value=[str(size_in_bytes)], data_type="integer64"),
        DocumentMetadataEntry(name="sha256", value=[sha256], data_type="string"),
        DocumentMetadataEntry(name="uploaded_by", value=[author], data_type="string"),
        DocumentMetadataEntry(name="project", value=[project_name], data_type="string"),
    ]


def document_repository(graph: GraphDep) -> DocumentRepository:
    return DocumentRepository(graph)


DocumentsDep = Annotated[DocumentRepository, Depends(document_repository)]
