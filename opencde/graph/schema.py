# This file was generated with the assistance of an AI coding tool.
"""Graph schema: labels, unique constraints and indexes.

The database is schemaless; this module is the schema. Every node label used
by the server is listed here with its unique key, so a duplicate id can never
be stored and every lookup by id is an index seek. ``apply_schema`` runs at
startup and is idempotent on both Neo4j and Memgraph.
"""

from __future__ import annotations

from ifc_lpg.graph import UNIQUE as LIBRARY_UNIQUE
from ifc_lpg.graph import Dialect as LibraryDialect
from ifc_lpg.graph import ensure_schema

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
    ("Validation", "id"),
    ("UploadSession", "id"),
    ("UploadPart", "id"),
    ("SelectionSession", "id"),
    ("Event", "id"),
    ("AuditEvent", "id"),
)

#: Every label with a unique key, IFC-LPG's included (``ifc_lpg.graph.UNIQUE``): what the backup keys nodes by and
#: the doctor counts. The library makes its own constraints and indexes (``ensure_schema``).
KEYED: tuple[tuple[str, str], ...] = (*UNIQUE, *LIBRARY_UNIQUE)

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
    ("Component", "ifc_guid"),
    ("Model", "project_id"),
    ("RequestLog", "at"),
    ("RequestLog", "expires_at"),
)

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
    "Precheck",
)


#: A label that begins with Ifc is one of IFC's classes: IFC-LPG named its own labels without it on 2026-11-10 (its
#: 61a2d69), and the server's own records followed on 2026-11-11 (F23 a). What earlier releases made is relabelled
#: at startup, in batches, so that the queries and the exports find it. Idempotent and cheap once done.
RENAMED_LABELS: tuple[tuple[str, str], ...] = (
    ("IfcModel", "Model"),
    ("IfcEntity", "Entity"),
    ("IfcValidation", "Validation"),
    ("IfcPrecheck", "Precheck"),
    ("IfcProposal", "Proposal"),
    ("IfcClash", "Clash"),
    ("IfcMerge", "Merge"),
)
RELABEL_BATCH = 5000


async def relabel_after_the_rename(graph: Graph) -> int:
    """Give nodes made before the renames their new labels. Returns how many nodes changed."""
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


def library_dialect(graph: Graph) -> LibraryDialect:
    """The graph's dialect as IFC-LPG names it."""
    return graph.dialect.name.value


class SchemaGraph:
    """The graph to IFC-LPG's schema statements (its ``SchemaGraph`` protocol): one statement at a time, where one
    that exists already is no error, as :meth:`Graph.ddl` does it."""

    def __init__(self, graph: Graph) -> None:
        self.graph = graph

    async def ddl(self, statement: str) -> None:
        await self.graph.ddl(statement)


async def drop_same_as(graph: Graph) -> int:
    """Remove the ``SAME_AS`` relationships earlier releases made from a BCF component to the element it names: since
    2026-11-11 (step one of IFC-LPG's F38 a) the GTIN comes through the library's lookup and the element is found by
    the component's ``GlobalId``. In batches, idempotent and cheap once done. Returns how many went."""
    gone = 0
    while True:
        rows = await graph.run(
            "MATCH ()-[r:SAME_AS]->() WITH r LIMIT $batch DELETE r RETURN count(*) AS n", batch=RELABEL_BATCH
        )
        done = int(rows[0]["n"]) if rows else 0
        gone += done
        if done < RELABEL_BATCH:
            break
    if gone:
        log.info("same_as_removed", relationships=gone)
    return gone


async def apply_schema(graph: Graph) -> int:
    """Create missing constraints and indexes, the library's too, and relabel what the renames left behind.
    Returns how many of the server's own statements changed the schema."""
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
    await ensure_schema(SchemaGraph(graph), library_dialect(graph))
    (log.info if changed else log.debug)("schema_applied", dialect=dialect.name.value, changed=changed)
    await relabel_after_the_rename(graph)
    await drop_same_as(graph)
    return changed
