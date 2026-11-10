# This file was generated with the assistance of an AI coding tool.
"""Graph schema: labels, unique constraints and indexes.

The database is schemaless; this module is the schema. Every node label used
by the server is listed here with its unique key, so a duplicate id can never
be stored and every lookup by id is an index seek. ``apply_schema`` runs at
startup and is idempotent on both Neo4j and Memgraph.
"""

from __future__ import annotations

import contextlib

from opencde.graph.dialect import GraphDialect
from opencde.graph.graph import Graph
from opencde.logging import get_logger

log = get_logger(__name__)

# (label, property) pairs that must be unique.
UNIQUE: tuple[tuple[str, str], ...] = (
    ("User", "id"),
    ("User", "username"),
    ("Client", "client_id"),
    ("AuthorizationCode", "code_hash"),
    ("AccessToken", "token_hash"),
    ("RefreshToken", "token_hash"),
    ("WebSession", "id"),
    ("SignInThrottle", "key"),
    ("Project", "project_id"),
    ("Extensions", "id"),
    ("Topic", "guid"),
    ("Comment", "guid"),
    ("Viewpoint", "guid"),
    ("Bitmap", "guid"),
    ("FileRef", "id"),
    ("DocumentReference", "guid"),
    ("BcfDocument", "guid"),
    ("Document", "document_id"),
    ("DocumentVersion", "id"),
    ("IfcValidation", "id"),
    ("UploadSession", "id"),
    ("UploadPart", "id"),
    ("SelectionSession", "id"),
    ("Event", "id"),
    ("AuditEvent", "id"),
    ("Model", "id"),
    ("Entity", "id"),
    ("StepBlock", "id"),
)

# Additional lookup and sort indexes.
INDEXES: tuple[tuple[str, str], ...] = (
    ("User", "email"),
    ("Topic", "creation_date"),
    ("Topic", "modified_date"),
    ("Topic", "server_assigned_id"),
    ("Comment", "date"),
    ("Event", "date"),
    ("AuditEvent", "at"),
    ("AuthorizationCode", "expires_at"),
    ("AccessToken", "expires_at"),
    ("RefreshToken", "expires_at"),
    ("RefreshToken", "family_id"),
    ("WebSession", "expires_at"),
    ("UploadSession", "expires_at"),
    ("UploadSession", "token_hash"),
    ("UploadPart", "expires_at"),
    ("SelectionSession", "expires_at"),
    ("SelectionSession", "token_hash"),
    ("DocumentVersion", "version_index"),
    ("Entity", "GlobalId"),
    ("Entity", "model_id"),
    ("Model", "project_id"),
    ("RequestLog", "at"),
    ("RequestLog", "expires_at"),
)

# Point indexes: where the products are (IFC-LPG's spatial layer, ``bbox_centre`` on every product with a shape).
POINT_INDEXES: tuple[tuple[str, str], ...] = (("Entity", "bbox_centre"),)

# Labels whose nodes carry ``expires_at`` and may be deleted once it has passed. Only self-registered
# clients carry it (unused ones expire); manually created clients have no ``expires_at`` and stay.
EXPIRING_LABELS: tuple[str, ...] = (
    "AuthorizationCode",
    "AccessToken",
    "RefreshToken",
    "WebSession",
    "SignInThrottle",
    "UploadSession",
    "UploadPart",
    "SelectionSession",
    "Client",
    "RequestLog",
    "IfcPrecheck",
)


#: IFC-LPG named its own labels without Ifc on 2026-11-10 (its 61a2d69): what was converted before is relabelled
#: at startup, in batches, so that the queries and the exports find it. Idempotent and cheap once done.
RENAMED_LABELS: tuple[tuple[str, str], ...] = (("IfcModel", "Model"), ("IfcEntity", "Entity"))
RELABEL_BATCH = 5000


async def relabel_after_the_rename(graph: Graph) -> int:
    """Give nodes converted before IFC-LPG's rename their new labels. Returns how many nodes changed."""
    changed = 0
    for old, new in RENAMED_LABELS:
        while True:
            rows = await graph.run(
                f"MATCH (n:{old}) WITH n LIMIT $batch SET n:{new} REMOVE n:{old} RETURN count(n) AS n",
                batch=RELABEL_BATCH,
            )
            done = int(rows[0]["n"]) if rows else 0
            changed += done
            if done < RELABEL_BATCH:
                break
    if changed:
        log.info("labels_renamed", nodes=changed)
    return changed


async def rebuild_point_indexes(graph: Graph) -> None:
    """Make the point indexes anew after points were set. Memgraph 3.14 does not keep a point index current (a
    point set after the index was made is not found through it), so there the index is dropped and made again;
    Neo4j keeps its indexes up to date and nothing is done."""
    if graph.dialect.name is not GraphDialect.MEMGRAPH:
        return
    for label, prop in POINT_INDEXES:
        with contextlib.suppress(Exception):  # there was none yet
            await graph.ddl(graph.dialect.drop_point_index(label, prop))
        await graph.ddl(graph.dialect.point_index(label, prop))


async def apply_schema(graph: Graph) -> int:
    """Create missing constraints and indexes, and relabel what IFC-LPG's rename left behind. Returns how many
    statements changed the schema."""
    changed = 0
    dialect = graph.dialect
    for label, prop in UNIQUE:
        if await graph.ddl(dialect.unique_constraint(label, prop)):
            changed += 1
        if not dialect.constraint_implies_index and await graph.ddl(dialect.index(label, prop)):
            changed += 1
    for label, prop in INDEXES:
        if await graph.ddl(dialect.index(label, prop)):
            changed += 1
    for label, prop in POINT_INDEXES:
        if await graph.ddl(dialect.point_index(label, prop)):
            changed += 1
    (log.info if changed else log.debug)("schema_applied", dialect=dialect.name.value, changed=changed)
    await relabel_after_the_rename(graph)
    return changed
