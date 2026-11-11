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
from ifc_lpg.validation import unpack_report

from opencde import audit
from opencde.deps import GraphDep
from opencde.documents.links import version_links
from opencde.documents.schemas import DocumentMetadataEntry, DocumentVersion, FileDescription
from opencde.documents.validation import Validation, with_graph_findings
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

    async def validation(
        self, *, user_id: str, document_id: str, version_index: int, with_issues: bool = False
    ) -> Validation | None:
        """The check of a version against the IFC schema, if it has one (``documents/validation.py``), with what the
        graph of its model shows once it is converted: the check ``graph``, with the instances no GlobalId reaches
        and the shapes the geometry pass could not build."""
        row = await self.graph.one(
            """
            MATCH (:User {id: $user_id})-[:MEMBER_OF]->(p:Project)-[:HAS_DOCUMENT]->(:Document {document_id: $document_id})
                  -[:HAS_VERSION]->(:DocumentVersion {version_index: $version_index})-[:HAS_VALIDATION]->(r:Validation)
            WITH p, r ORDER BY r.created_at DESC LIMIT 1
            OPTIONAL MATCH (p)-[:HAS_CONVERSION]->(m:Conversion {document_id: $document_id, version_index: $version_index})
            WHERE m.graph_checked_at IS NOT NULL
            WITH r, m ORDER BY m.created_at DESC LIMIT 1
            RETURN r.state AS state, r.issue_count AS issue_count, r.error_count AS error_count,
                   r.truncated AS truncated, r.checked_at AS checked_at, r.ruleset AS ruleset, r.checks AS checks,
                   CASE WHEN $with_issues THEN r.report ELSE null END AS report,
                   m.graph_issue_count AS graph_issue_count, m.graph_error_count AS graph_error_count,
                   m.graph_ruleset AS graph_ruleset, CASE WHEN $with_issues THEN m.graph_report ELSE null END AS graph_report
            """,
            user_id=user_id,
            document_id=document_id,
            version_index=version_index,
            with_issues=with_issues,
        )
        if row is None:
            return None
        validation = Validation(
            state=str(row["state"]),
            issue_count=None if row["issue_count"] is None else int(row["issue_count"]),
            error_count=None if row["error_count"] is None else int(row["error_count"]),
            truncated=bool(row["truncated"]),
            checked_at=row["checked_at"],
            ruleset=row["ruleset"],
            issues=unpack_report(row["report"]),
            checks=json.loads(row["checks"]) if row["checks"] else [],
        )
        return with_graph_findings(
            validation,
            issue_count=row["graph_issue_count"],
            error_count=row["graph_error_count"],
            ruleset=row["graph_ruleset"],
            issues=unpack_report(row["graph_report"]),
        )

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
        requested_document_id: str | None = None,
        parent_version_index: int | None = None,
        approved_by: str | None = None,
        change_set_id: str | None = None,
        change_set: str | None = None,
    ) -> VersionRecord:
        """A new document (``document_id`` None) or a new version of an existing one, in one transaction.

        ``requested_document_id`` gives a new document a known id (the seed uses it); it is ignored when
        ``document_id`` names an existing document. A version built on another names it in
        ``parent_version_index`` and is linked to it (``DERIVED_FROM``); one approved from a change set carries
        ``approved_by``, ``change_set_id`` (the topic's guid) and ``change_set`` (the changes, packed) (ADR 0021).
        """
        now = now_iso()
        version_id = new_id()
        new_document_id = document_id or requested_document_id or new_id()
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
            if parent_version_index is not None:
                await tx.run(
                    """
                    MATCH (d:Document {document_id: $document_id})-[:HAS_VERSION]->(v:DocumentVersion {id: $id})
                    SET v += $lineage
                    WITH d, v
                    MATCH (d)-[:HAS_VERSION]->(parent:DocumentVersion {version_index: $parent_index})
                    CREATE (v)-[:DERIVED_FROM]->(parent)
                    """,
                    document_id=new_document_id,
                    id=version_id,
                    parent_index=parent_version_index,
                    lineage={
                        key: value
                        for key, value in {
                            "parent_version_index": parent_version_index,
                            "approved_by": approved_by,
                            "change_set_id": change_set_id,
                            "change_set": change_set,
                        }.items()
                        if value is not None
                    },
                )
            return row

        return _record(await self.graph.write(work))

    async def versions_since(self, *, user_id: str, document_id: str, since: int, until: int) -> list[dict[str, Any]]:
        """The versions after `since` up to `until`, each with its change set unpacked, or none for a whole file."""
        rows = await self.graph.run(
            """
            MATCH (:User {id: $user_id})-[:MEMBER_OF]->(:Project)-[:HAS_DOCUMENT]->(:Document {document_id: $document_id})
                  -[:HAS_VERSION]->(v:DocumentVersion)
            WHERE v.version_index > $since AND v.version_index <= $until
            RETURN v.version_index AS version_index, v.author AS author, v.approved_by AS approved_by,
                   v.change_set_id AS change_set_id, v.change_set AS change_set
            ORDER BY v.version_index
            """,
            user_id=user_id,
            document_id=document_id,
            since=since,
            until=until,
        )
        return [
            {
                "version_index": int(row["version_index"]),
                "author": row["author"],
                "approved_by": row["approved_by"],
                "change_set_id": row["change_set_id"],
                "changes": unpack_report(row["change_set"]) if row["change_set"] else None,
            }
            for row in rows
        ]

    async def change_set(self, *, user_id: str, document_id: str, version_index: int) -> dict[str, Any] | None:
        """The change set a version was approved from (ADR 0021), unpacked; None when it has none."""
        row = await self.graph.one(
            """
            MATCH (:User {id: $user_id})-[:MEMBER_OF]->(:Project)-[:HAS_DOCUMENT]->(:Document {document_id: $document_id})
                  -[:HAS_VERSION]->(v:DocumentVersion {version_index: $version_index})
            RETURN v.change_set AS change_set, v.change_set_id AS change_set_id, v.parent_version_index AS parent,
                   v.approved_by AS approved_by, v.author AS author
            """,
            user_id=user_id,
            document_id=document_id,
            version_index=version_index,
        )
        if row is None or not row["change_set"]:
            return None
        return {
            "change_set_id": row["change_set_id"],
            "base": {"document_id": document_id, "version_index": int(row["parent"])},
            "proposed_by": row["author"],
            "approved_by": row["approved_by"],
            "changes": unpack_report(row["change_set"]),
        }

    async def publication(self, *, user_id: str, document_id: str, version_index: int) -> dict[str, Any] | None:
        """The publication of a version (F9 a), or None while it is not published."""
        row = await self.graph.one(
            """
            MATCH (:User {id: $user_id})-[:MEMBER_OF]->(:Project)-[:HAS_DOCUMENT]->(:Document {document_id: $document_id})
                  -[:HAS_VERSION]->(:DocumentVersion {version_index: $version_index})-[:HAS_PUBLICATION]->(pub:Publication)
            WITH pub ORDER BY pub.published_at LIMIT 1
            RETURN properties(pub) AS publication
            """,
            user_id=user_id,
            document_id=document_id,
            version_index=version_index,
        )
        return dict(row["publication"]) if row else None

    async def publish(
        self,
        *,
        user_id: str,
        document_id: str,
        version_index: int,
        publication: dict[str, Any],
        audit_event: dict[str, Any],
    ) -> bool:
        """Mark a version published with its stored archive (``id``, ``storage_key``, ``file_name``,
        ``size_in_bytes``, ``sha256``, ``published_at``, ``published_by``), and the audit event with it in the same
        transaction; False when it already was."""

        async def work(tx: Tx) -> bool:
            rows = await tx.run(
                """
                MATCH (:User {id: $user_id})-[:MEMBER_OF]->(:Project)-[:HAS_DOCUMENT]->(:Document {document_id: $document_id})
                      -[:HAS_VERSION]->(v:DocumentVersion {version_index: $version_index})
                OPTIONAL MATCH (v)-[:HAS_PUBLICATION]->(old:Publication)
                WITH v, old WHERE old IS NULL
                CREATE (v)-[:HAS_PUBLICATION]->(:Publication {
                    id: $id, storage_key: $storage_key, file_name: $file_name, size_in_bytes: $size_in_bytes,
                    sha256: $sha256, published_at: $published_at, published_by: $published_by
                })
                RETURN v.id AS id
                """,
                user_id=user_id,
                document_id=document_id,
                version_index=version_index,
                **publication,
            )
            if not rows:
                return False
            await audit.record_in(tx, **audit_event)
            return True

        return await self.graph.write(work)


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


def publication_metadata(publication: dict[str, Any], url: str) -> list[DocumentMetadataEntry]:
    """The entries a published version adds to its metadata (F9 a): when, by whom, and where the publication is."""
    return [
        DocumentMetadataEntry(name="published_at", value=[str(publication["published_at"])], data_type="date-time"),
        DocumentMetadataEntry(name="published_by", value=[str(publication["published_by"])], data_type="string"),
        DocumentMetadataEntry(name="publication", value=[url], data_type="url"),
    ]


def document_repository(graph: GraphDep) -> DocumentRepository:
    return DocumentRepository(graph)


DocumentsDep = Annotated[DocumentRepository, Depends(document_repository)]
