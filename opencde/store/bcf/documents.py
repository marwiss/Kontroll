# This file was generated with the assistance of an AI coding tool.
"""Project documents of the BCF API (3.8) and the files information list (3.3.1).

A ``BcfDocument`` is a binary file uploaded to a project through the BCF API.
The bytes live in storage under ``bcf-documents/<guid>``; the node keeps the
client's file name (never used as a path) and who uploaded it when.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends, HTTPException

from opencde.bcf.schemas import DocumentGET, FileRef, ProjectFileDisplayInformation, ProjectFileInformation
from opencde.deps import GraphDep
from opencde.graph.graph import Graph, Tx
from opencde.store.protocols import BcfDocumentStore
from opencde.timeutil import now_iso

_SCOPE = (
    "MATCH (:User {id: $user_id})-[:MEMBER_OF]->(p:Project {project_id: $project_id})-[:HAS_DOCUMENT]->(d:BcfDocument)"
)


class BcfDocumentRepository:
    def __init__(self, graph: Graph) -> None:
        self.graph = graph

    async def search(self, *, user_id: str, project_id: str) -> list[DocumentGET]:
        rows = await self.graph.run(
            _SCOPE + " RETURN properties(d) AS document ORDER BY d.created_at, d.guid",
            user_id=user_id,
            project_id=project_id,
        )
        return [DocumentGET(guid=row["document"]["guid"], filename=row["document"]["filename"]) for row in rows]

    async def get(self, *, user_id: str, project_id: str, guid: str) -> dict[str, Any] | None:
        row = await self.graph.one(
            _SCOPE.replace("(d:BcfDocument)", "(d:BcfDocument {guid: $guid})") + " RETURN properties(d) AS document",
            user_id=user_id,
            project_id=project_id,
            guid=guid,
        )
        return row["document"] if row else None

    async def exists(self, guid: str) -> bool:
        row = await self.graph.one("MATCH (d:BcfDocument {guid: $guid}) RETURN count(d) AS n", guid=guid)
        return bool(row and row["n"])

    async def create(
        self, *, project_id: str, guid: str, filename: str, author: str, storage_key: str, size: int
    ) -> DocumentGET:
        async def work(tx: Tx) -> dict[str, Any]:
            if await tx.one("MATCH (d:BcfDocument {guid: $guid}) RETURN d.guid AS guid", guid=guid):
                raise HTTPException(409, "A document with this guid already exists")  # Foundation API 1.5.1
            row = await tx.one(
                """
                MATCH (p:Project {project_id: $project_id}), (u:User {username: $author})
                CREATE (p)-[:HAS_DOCUMENT]->(d:BcfDocument {
                    guid: $guid, filename: $filename, storage_key: $storage_key, size: $size,
                    created_at: $now, author: $author
                })
                CREATE (d)-[:UPLOADED_BY]->(u)
                RETURN properties(d) AS document
                """,
                project_id=project_id,
                author=author,
                guid=guid,
                filename=filename,
                storage_key=storage_key,
                size=size,
                now=now_iso(),
            )
            if row is None:
                raise HTTPException(404, "Project not found")
            return row["document"]

        node = await self.graph.write(work)
        return DocumentGET(guid=node["guid"], filename=node["filename"])

    async def files_information(self, *, user_id: str, project_id: str, base_url: str) -> list[ProjectFileInformation]:
        """One entry per file in the project (BCF documents and Documents API versions), with the same display
        fields for every entry (BCF 3.3.1)."""
        rows = await self.graph.run(
            _SCOPE + " RETURN properties(d) AS document ORDER BY d.created_at, d.guid",
            user_id=user_id,
            project_id=project_id,
        )
        entries = [
            _entry(
                filename=row["document"]["filename"],
                date=row["document"]["created_at"],
                author=row["document"]["author"],
                source="BCF API document",
                reference=f"{base_url}/bcf/3.0/projects/{project_id}/documents/{row['document']['guid']}",
                document_id=row["document"]["guid"],
            )
            for row in rows
        ]
        versions = await self.graph.run(
            """
            MATCH (:User {id: $user_id})-[:MEMBER_OF]->(:Project {project_id: $project_id})
                  -[:HAS_DOCUMENT]->(d:Document)-[:HAS_VERSION]->(v:DocumentVersion)
            WITH d, v ORDER BY v.version_index DESC
            WITH d, collect(v)[0] AS v
            OPTIONAL MATCH (m:Conversion {document_id: d.document_id, version_index: v.version_index, state: 'done'})
            RETURN d.document_id AS document_id, properties(v) AS version, m.ifc_project_guid AS ifc_project
            ORDER BY v.creation_date, d.document_id
            """,
            user_id=user_id,
            project_id=project_id,
        )
        entries.extend(
            _entry(
                filename=row["version"]["file_name"],
                date=row["version"]["creation_date"],
                author=row["version"]["author"],
                source="Documents API",
                reference=(
                    f"{base_url}/documents/1.0/documents/{row['document_id']}"
                    f"/versions/{row['version']['version_index']}/download"
                ),
                ifc_project=row.get("ifc_project"),
                document_id=row["document_id"],
                version_index=row["version"]["version_index"],
            )
            for row in versions
        )
        return entries


def _entry(
    *,
    filename: str,
    date: str,
    author: str,
    source: str,
    reference: str,
    document_id: str,
    version_index: int | None = None,
    ifc_project: str | None = None,
) -> ProjectFileInformation:
    # "Document id" and "Version index" let a client reach the Documents API version behind a file without
    # parsing the reference URL; a BCF API document has no version, so its index is empty.
    return ProjectFileInformation(
        display_information=[
            ProjectFileDisplayInformation(field_display_name="File name", field_value=filename),
            ProjectFileDisplayInformation(field_display_name="Uploaded", field_value=date),
            ProjectFileDisplayInformation(field_display_name="Uploaded by", field_value=author),
            ProjectFileDisplayInformation(field_display_name="Source", field_value=source),
            ProjectFileDisplayInformation(field_display_name="Document id", field_value=document_id),
            ProjectFileDisplayInformation(
                field_display_name="Version index", field_value="" if version_index is None else str(version_index)
            ),
        ],
        file=FileRef(filename=filename, date=date, reference=reference, ifc_project=ifc_project),
    )


def bcf_document_repository(graph: GraphDep) -> BcfDocumentStore:
    return BcfDocumentRepository(graph)


BcfDocumentsDep = Annotated[BcfDocumentStore, Depends(bcf_document_repository)]
