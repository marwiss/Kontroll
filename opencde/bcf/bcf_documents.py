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
        """One entry per project document, with the same display fields for every entry (BCF 3.3.1)."""
        rows = await self.graph.run(
            _SCOPE + " RETURN properties(d) AS document ORDER BY d.created_at, d.guid",
            user_id=user_id,
            project_id=project_id,
        )
        result = []
        for row in rows:
            document = row["document"]
            result.append(
                ProjectFileInformation(
                    display_information=[
                        ProjectFileDisplayInformation(field_display_name="File name", field_value=document["filename"]),
                        ProjectFileDisplayInformation(
                            field_display_name="Uploaded", field_value=document["created_at"]
                        ),
                        ProjectFileDisplayInformation(field_display_name="Uploaded by", field_value=document["author"]),
                        ProjectFileDisplayInformation(field_display_name="Source", field_value="BCF API document"),
                    ],
                    file=FileRef(
                        filename=document["filename"],
                        date=document["created_at"],
                        reference=f"{base_url}/bcf/3.0/projects/{project_id}/documents/{document['guid']}",
                    ),
                )
            )
        return result


def bcf_document_repository(graph: GraphDep) -> BcfDocumentRepository:
    return BcfDocumentRepository(graph)


BcfDocumentsDep = Annotated[BcfDocumentRepository, Depends(bcf_document_repository)]
