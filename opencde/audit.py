# This file was generated with the assistance of an AI coding tool.
"""Audit log of security-relevant events.

Sign-ins, issued codes and tokens, revocations, client registrations and
every administrative change are recorded as ``AuditEvent`` nodes: who, what,
when, from which address. Details are stored as a JSON string so the record
is a flat node on every graph product. Nothing secret is ever written here.
"""

from __future__ import annotations

import json
from typing import Any

import structlog

from opencde.graph.graph import Graph, Tx
from opencde.ids import new_id
from opencde.logging import get_logger, redact_secrets
from opencde.timeutil import now_iso

log = get_logger(__name__)

CREATE = """
CREATE (e:AuditEvent {
    id: $id, type: $type, at: $at, actor_user_id: $actor, client_id: $client_id, ip: $ip, details: $details,
    request_id: $request_id
})
"""


def _payload(
    type: str, actor: str | None, client_id: str | None, ip: str | None, details: dict[str, Any] | None
) -> dict:
    safe = redact_secrets(None, "audit", dict(details or {}))
    # The request id the middleware bound to the log context, so an event can be matched with the request log
    # and with a client's own log (the administration API returns it).
    request_id = structlog.contextvars.get_contextvars().get("request_id")
    return {
        "id": new_id(),
        "type": type,
        "at": now_iso(),
        "actor": actor,
        "client_id": client_id,
        "ip": ip,
        "details": json.dumps(safe, sort_keys=True, default=str),
        "request_id": request_id if isinstance(request_id, str) else None,
    }


async def record(
    graph: Graph,
    type: str,
    *,
    actor: str | None = None,
    client_id: str | None = None,
    ip: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    payload = _payload(type, actor, client_id, ip, details)
    await graph.run(CREATE, **payload)
    log.info("audit", audit_type=type, actor=actor, client_id=client_id)


async def record_in(
    tx: Tx,
    type: str,
    *,
    actor: str | None = None,
    client_id: str | None = None,
    ip: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Record inside an existing transaction so the event and the change commit together."""
    await tx.run(CREATE, **_payload(type, actor, client_id, ip, details))


async def recent(
    graph: Graph, limit: int = 100, type_prefix: str | None = None, since: str | None = None
) -> list[dict[str, Any]]:
    """The newest events, optionally of one type prefix and at or after ``since`` (ISO 8601 UTC)."""
    rows = await graph.run(
        """
        MATCH (e:AuditEvent)
        WHERE ($prefix IS NULL OR e.type STARTS WITH $prefix) AND ($since IS NULL OR e.at >= $since)
        RETURN properties(e) AS event
        ORDER BY e.at DESC
        LIMIT $limit
        """,
        prefix=type_prefix,
        since=since,
        limit=limit,
    )
    events = []
    for row in rows:
        event = dict(row["event"])
        event["details"] = json.loads(event.get("details") or "{}")
        events.append(event)
    return events
