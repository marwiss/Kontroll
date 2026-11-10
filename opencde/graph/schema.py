# This file was generated with the assistance of an AI coding tool.
"""Graph schema: labels, unique constraints and indexes.

The database is schemaless; this module is the schema. Every node label used
by the server is listed here with its unique key, so a duplicate id can never
be stored and every lookup by id is an index seek. ``apply_schema`` runs at
startup and is idempotent on both Neo4j and Memgraph.
"""

from __future__ import annotations

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
    ("IfcModel", "id"),
    ("IfcEntity", "id"),
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
    ("IfcEntity", "GlobalId"),
    ("IfcEntity", "model_id"),
    ("IfcModel", "project_id"),
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
    "IfcPrecheck",
)


async def apply_schema(graph: Graph) -> int:
    """Create missing constraints and indexes. Returns how many statements changed the schema."""
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
    (log.info if changed else log.debug)("schema_applied", dialect=dialect.name.value, changed=changed)
    return changed
