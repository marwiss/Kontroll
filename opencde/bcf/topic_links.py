# This file was generated with the assistance of an AI coding tool.
"""What a topic points at: header files (3.3), related topics (3.6), document references (3.7), BIM snippet (3.2.6).

All of these are replaced or appended under the topic in one transaction, and
each change moves the topic's ``modified_date``.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends, HTTPException

from opencde.bcf.schemas import (
    DocumentReferenceFields,
    DocumentReferenceGET,
    DocumentReferencePOST,
    DocumentReferencePUT,
    FileRef,
)
from opencde.bcf.topic_access import TopicsDep
from opencde.bcf.topics import TopicRepository
from opencde.deps import GraphDep
from opencde.graph.graph import Graph, Tx
from opencde.ids import is_uuid, new_id, normalize_guid
from opencde.timeutil import now_iso

_TOPIC = "MATCH (:User {id: $user_id})-[:MEMBER_OF]->(:Project {project_id: $project_id})-[:HAS_TOPIC]->(t:Topic {guid: $topic_guid})"


def _reference(node: dict[str, Any]) -> DocumentReferenceGET:
    return DocumentReferenceGET(
        guid=node["guid"],
        document_guid=node.get("document_guid"),
        url=node.get("url"),
        description=node.get("description"),
    )


def _file(node: dict[str, Any]) -> FileRef:
    return FileRef(
        ifc_project=node.get("ifc_project"),
        ifc_spatial_structure_element=node.get("ifc_spatial_structure_element"),
        filename=node.get("filename"),
        date=node.get("date"),
        reference=node.get("reference"),
    )


class TopicLinkRepository:
    def __init__(self, graph: Graph, topics: TopicRepository) -> None:
        self.graph = graph
        self.topics = topics

    # -- related topics (3.6) -------------------------------------------------------------------

    async def related(self, *, user_id: str, project_id: str, topic_guid: str) -> list[str]:
        rows = await self.graph.run(
            _TOPIC + "-[:RELATED_TO]->(o:Topic) RETURN o.guid AS guid ORDER BY o.creation_date, o.guid",
            user_id=user_id,
            project_id=project_id,
            topic_guid=topic_guid,
        )
        return [row["guid"] for row in rows]

    async def set_related(self, *, project_id: str, topic_guid: str, author: str, guids: list[str]) -> list[str]:
        wanted: list[str] = []
        for value in guids:
            if not is_uuid(value):
                raise HTTPException(400, "related_topic_guid must be a UUID")
            normalized = normalize_guid(value)
            if normalized == topic_guid:
                raise HTTPException(400, "a topic cannot be related to itself")
            if normalized not in wanted:
                wanted.append(normalized)

        async def work(tx: Tx) -> list[str]:
            found = await tx.run(
                "MATCH (:Project {project_id: $project_id})-[:HAS_TOPIC]->(o:Topic) WHERE o.guid IN $guids RETURN o.guid AS guid",
                project_id=project_id,
                guids=wanted,
            )
            missing = set(wanted) - {row["guid"] for row in found}
            if missing:
                raise HTTPException(400, f"not topics of this project: {', '.join(sorted(missing))}")
            await tx.run(
                "MATCH (:Project {project_id: $project_id})-[:HAS_TOPIC]->(:Topic {guid: $topic_guid})-[r:RELATED_TO]->() DELETE r",
                project_id=project_id,
                topic_guid=topic_guid,
            )
            await tx.run(
                """
                MATCH (:Project {project_id: $project_id})-[:HAS_TOPIC]->(t:Topic {guid: $topic_guid})
                UNWIND $guids AS guid
                MATCH (o:Topic {guid: guid})
                CREATE (t)-[:RELATED_TO]->(o)
                """,
                project_id=project_id,
                topic_guid=topic_guid,
                guids=wanted,
            )
            await self.topics.touch(tx, guid=topic_guid, author=author)
            return wanted

        return await self.graph.write(work)

    # -- document references (3.7) -------------------------------------------------------------

    async def references(self, *, user_id: str, project_id: str, topic_guid: str) -> list[DocumentReferenceGET]:
        rows = await self.graph.run(
            _TOPIC
            + "-[:HAS_DOCUMENT_REFERENCE]->(r:DocumentReference) RETURN properties(r) AS ref ORDER BY r.created_at, r.guid",
            user_id=user_id,
            project_id=project_id,
            topic_guid=topic_guid,
        )
        return [_reference(row["ref"]) for row in rows]

    async def _check_document(self, tx: Tx, project_id: str, fields: DocumentReferenceFields) -> str | None:
        if fields.document_guid is None:
            return None
        if not is_uuid(fields.document_guid):
            raise HTTPException(400, "document_guid must be a UUID")
        guid = normalize_guid(fields.document_guid)
        row = await tx.one(
            """
            MATCH (:Project {project_id: $project_id})-[:HAS_DOCUMENT]->(d)
            WHERE (d:BcfDocument AND d.guid = $guid) OR (d:Document AND d.document_id = $guid)
            RETURN count(d) AS n
            """,
            project_id=project_id,
            guid=guid,
        )
        if row is None or not row["n"]:
            raise HTTPException(400, "document_guid does not match a document of this project")  # BCF 3.7.2
        return guid

    async def add_reference(
        self, *, project_id: str, topic_guid: str, author: str, body: DocumentReferencePOST
    ) -> DocumentReferenceGET:
        if body.guid and not is_uuid(body.guid):
            raise HTTPException(400, "guid must be a UUID")
        guid = normalize_guid(body.guid) if body.guid else new_id()

        async def work(tx: Tx) -> dict[str, Any]:
            if await tx.one("MATCH (r:DocumentReference {guid: $guid}) RETURN r.guid AS guid", guid=guid):
                raise HTTPException(409, "A document reference with this guid already exists")
            document_guid = await self._check_document(tx, project_id, body)
            row = await tx.one(
                """
                MATCH (:Project {project_id: $project_id})-[:HAS_TOPIC]->(t:Topic {guid: $topic_guid})
                CREATE (t)-[:HAS_DOCUMENT_REFERENCE]->(r:DocumentReference {
                    guid: $guid, document_guid: $document_guid, url: $url, description: $description, created_at: $now
                })
                RETURN properties(r) AS ref
                """,
                project_id=project_id,
                topic_guid=topic_guid,
                guid=guid,
                document_guid=document_guid,
                url=body.url,
                description=body.description,
                now=now_iso(),
            )
            if row is None:
                raise HTTPException(404, "Topic not found")
            await self.topics.touch(tx, guid=topic_guid, author=author)
            return row["ref"]

        return _reference(await self.graph.write(work))

    async def update_reference(
        self, *, project_id: str, topic_guid: str, guid: str, author: str, body: DocumentReferencePUT
    ) -> DocumentReferenceGET | None:
        async def work(tx: Tx) -> dict[str, Any] | None:
            document_guid = await self._check_document(tx, project_id, body)
            row = await tx.one(
                """
                MATCH (:Project {project_id: $project_id})-[:HAS_TOPIC]->(t:Topic {guid: $topic_guid})
                      -[:HAS_DOCUMENT_REFERENCE]->(r:DocumentReference {guid: $guid})
                SET r.document_guid = $document_guid, r.url = $url, r.description = $description
                RETURN properties(r) AS ref
                """,
                project_id=project_id,
                topic_guid=topic_guid,
                guid=guid,
                document_guid=document_guid,
                url=body.url,
                description=body.description,
            )
            if row is None:
                return None
            await self.topics.touch(tx, guid=topic_guid, author=author)
            return row["ref"]

        result = await self.graph.write(work)
        return _reference(result) if result else None

    # -- header files (3.3.2, 3.3.3) -----------------------------------------------------------

    async def files(self, *, user_id: str, project_id: str, topic_guid: str) -> list[FileRef]:
        rows = await self.graph.run(
            _TOPIC + "-[:HAS_FILE]->(f:FileRef) RETURN properties(f) AS file ORDER BY f.position",
            user_id=user_id,
            project_id=project_id,
            topic_guid=topic_guid,
        )
        return [_file(row["file"]) for row in rows]

    async def set_files(self, *, project_id: str, topic_guid: str, author: str, files: list[FileRef]) -> list[FileRef]:
        rows = [{"id": new_id(), "position": position, **item.model_dump()} for position, item in enumerate(files)]

        async def work(tx: Tx) -> None:
            await tx.run(
                "MATCH (:Project {project_id: $project_id})-[:HAS_TOPIC]->(:Topic {guid: $topic_guid})-[:HAS_FILE]->(f:FileRef) DETACH DELETE f",
                project_id=project_id,
                topic_guid=topic_guid,
            )
            await tx.run(
                """
                MATCH (:Project {project_id: $project_id})-[:HAS_TOPIC]->(t:Topic {guid: $topic_guid})
                UNWIND $rows AS row
                CREATE (t)-[:HAS_FILE]->(:FileRef {
                    id: row.id, position: row.position, ifc_project: row.ifc_project,
                    ifc_spatial_structure_element: row.ifc_spatial_structure_element,
                    filename: row.filename, date: row.date, reference: row.reference
                })
                """,
                project_id=project_id,
                topic_guid=topic_guid,
                rows=rows,
            )
            await self.topics.touch(tx, guid=topic_guid, author=author)

        await self.graph.write(work)
        return files

    # -- BIM snippet file (3.2.6, 3.2.7) -------------------------------------------------------

    async def snippet(self, *, user_id: str, project_id: str, topic_guid: str) -> dict[str, Any] | None:
        """Storage key and file name of the stored snippet, or None when the topic has none."""
        row = await self.graph.one(
            _TOPIC
            + """
            WHERE t.snippet_storage_key IS NOT NULL AND t.snippet_type IS NOT NULL AND t.snippet_is_external = false
            RETURN t.snippet_storage_key AS storage_key,
                   coalesce(t.snippet_filename, t.snippet_reference, 'snippet') AS filename
            """,
            user_id=user_id,
            project_id=project_id,
            topic_guid=topic_guid,
        )
        return dict(row) if row else None

    async def set_snippet(
        self, *, project_id: str, topic_guid: str, author: str, storage_key: str, filename: str | None, size: int
    ) -> None:
        """Record an uploaded snippet file: the snippet becomes internal and its reference the file name (3.2.7)."""
        await self.graph.write(
            lambda tx: tx.run(
                """
                MATCH (:Project {project_id: $project_id})-[:HAS_TOPIC]->(t:Topic {guid: $topic_guid})
                SET t.snippet_storage_key = $storage_key, t.snippet_is_external = false,
                    t.snippet_reference = coalesce($filename, t.snippet_reference), t.snippet_filename = $filename,
                    t.snippet_size = $size, t.modified_date = $now, t.modified_author = $author
                """,
                project_id=project_id,
                topic_guid=topic_guid,
                storage_key=storage_key,
                filename=filename,
                size=size,
                now=now_iso(),
                author=author,
            )
        )


def link_repository(graph: GraphDep, topics: TopicsDep) -> TopicLinkRepository:
    return TopicLinkRepository(graph, topics)


LinksDep = Annotated[TopicLinkRepository, Depends(link_repository)]
