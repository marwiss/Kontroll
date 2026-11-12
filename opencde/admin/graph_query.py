# This file was generated with the assistance of an AI coding tool.
"""Read-only Cypher for administrators: ``POST /admin/api/graph/query``.

An extension outside the OpenCDE specifications, off by default
(``OPENCDE_GRAPH_QUERY_ENABLED``), announced in the capabilities document
and meant for an administration client such as Dataspatium's "Graph query"
card: a bearer token holding the ``admin`` scope and an administrator
account send ``{"cypher": "...", "params": {...}}`` and get back
``{"columns": [...], "rows": [[...]], "truncated": bool}``.

This is the one place besides ``admin/queries.py`` where a statement does
not start at a user node, which is why the module keeps several fences:

* the statement runs in a read transaction and must not contain a writing
  clause or a procedure call other than the schema procedures (checked on
  the text with comments, strings and backticked names removed);
* protected properties (password, secret, token and code hashes) may not be
  named in the statement or in a parameter, are dropped from every map,
  node and relationship in the answer, and an Argon2 hash reaching the
  answer by another route is redacted;
* the answer stops after ``graph_query_max_rows`` rows (``truncated``) and
  the statement after ``graph_query_timeout_seconds``;
* every call, refused or not, leaves an audit event with the statement's
  first characters, never the parameters.

Nodes come back as ``{"identity", "labels", "properties"}``, relationships as
``{"identity", "type", "start", "end", "properties"}`` and paths as
``{"nodes", "relationships", "length"}``; temporal values as ISO 8601
strings, points as ``{"srid", "x", "y", "z"}``, bytes as base64. Agreed with
Dataspatium.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import math
import re
import time
from typing import Any, LiteralString, cast

from fastapi import APIRouter, HTTPException, Request
from neo4j import READ_ACCESS
from neo4j.exceptions import Neo4jError
from neo4j.graph import Node, Path, Relationship
from neo4j.spatial import Point
from neo4j.time import Date, DateTime, Duration, Time
from pydantic import BaseModel, Field

from opencde import audit
from opencde.auth.dependencies import AdminPrincipal
from opencde.deps import GraphDep, SettingsDep, client_ip
from opencde.graph.graph import Graph
from opencde.ids import new_id
from opencde.logging import get_logger
from opencde.settings import GraphDialect

router = APIRouter(prefix="/admin/api/graph", tags=["Administration (extension)"])

log = get_logger(__name__)

MAX_STATEMENT_LENGTH = 20_000
QUERY_MARKER = "opencde_graph_query"  # in a query's transaction metadata, so that it can be found and stopped
AUDIT_STATEMENT_LENGTH = 500

#: Properties that hold hashes of credentials. Never named in a statement, never in an answer.
PROTECTED_PROPERTIES = frozenset({"password_hash", "secret_hash", "token_hash", "code_hash"})
#: Argon2 hashes (passwords) start like this; anything that looks like one is redacted.
HASH_PREFIX = "$argon2"
REDACTED = "<redacted>"

#: Keywords that write, change the schema, administer the database or leave the data: refused anywhere
#: outside strings, comments and backticked names, unless they follow ``:``, ``.`` or ``$`` (labels,
#: relationship types, properties and parameters may carry any name).
FORBIDDEN_WORDS = frozenset(
    {
        "alter",
        "analyze",
        "assign",
        "auth",
        "commit",
        "create",
        "delete",
        "deny",
        "detach",
        "disable",
        "drop",
        "dump",
        "enable",
        "export",
        "foreach",
        "free",
        "grant",
        "import",
        "kill",
        "load",
        "lock",
        "merge",
        "periodic",
        "remove",
        "rename",
        "replica",
        "replicate",
        "replication",
        "revoke",
        "set",
        "show",
        "snapshot",
        "start",
        "stop",
        "storage",
        "stream",
        "terminate",
        "transactions",
        "trigger",
        "unlock",
        "use",
    }
)
#: The only procedures a statement may call: they describe the schema and change nothing.
ALLOWED_PROCEDURES = frozenset(
    {
        "db.labels",
        "db.relationshiptypes",
        "db.propertykeys",
        "db.schema.visualization",
        "db.schema.nodetypeproperties",
        "db.schema.reltypeproperties",
    }
)

_LINE_COMMENT = re.compile(r"//[^\n]*")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_STRING = re.compile(r"'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"")
_BACKTICKED = re.compile(r"`[^`]*`")
_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_PROCEDURE = re.compile(r"\s*([A-Za-z_][A-Za-z0-9_.]*)")


class QueryRejected(ValueError):
    """The statement or its parameters are not allowed here; the message says why."""


def bare_statement(cypher: str) -> str:
    """The statement with comments removed and strings and backticked names emptied, for inspection."""
    bare = _BLOCK_COMMENT.sub(" ", cypher)
    bare = _LINE_COMMENT.sub(" ", bare)
    bare = _STRING.sub("''", bare)
    return _BACKTICKED.sub("``", bare)


def _preceding_char(text: str, index: int) -> str:
    cursor = index - 1
    while cursor >= 0 and text[cursor] in " \t\r\n":
        cursor -= 1
    return text[cursor] if cursor >= 0 else ""


def check_statement(cypher: str) -> None:
    """Raise :class:`QueryRejected` unless the statement only reads and names no protected property."""
    if not cypher.strip():
        raise QueryRejected("The statement is empty")
    bare = bare_statement(cypher)
    for match in _WORD.finditer(bare):
        word = match.group(0).lower()
        if word in PROTECTED_PROPERTIES:
            raise QueryRejected(f"The statement names a protected property ({match.group(0)})")
        if _preceding_char(bare, match.start()) in (":", ".", "$"):
            continue  # a label, relationship type, property or parameter name
        if word in FORBIDDEN_WORDS:
            raise QueryRejected(f"Only reading statements are allowed here ({match.group(0).upper()} is not)")
        if word == "call":
            rest = bare[match.end() :]
            if rest.lstrip().startswith("{"):
                continue  # a subquery; its clauses are checked like the rest
            procedure = _PROCEDURE.match(rest)
            name = procedure.group(1).lower() if procedure else ""
            if name not in ALLOWED_PROCEDURES:
                raise QueryRejected(
                    "Only the schema procedures may be called here "
                    "(db.labels, db.relationshipTypes, db.propertyKeys, db.schema.*)"
                )


def check_parameters(params: dict[str, Any]) -> None:
    """Raise :class:`QueryRejected` when a parameter value names a protected property (``u[$key]``)."""

    def walk(value: Any) -> None:
        if isinstance(value, str):
            if value.lower() in PROTECTED_PROPERTIES:
                raise QueryRejected(f"A parameter names a protected property ({value})")
        elif isinstance(value, dict):
            for key, item in value.items():
                if str(key).lower() in PROTECTED_PROPERTIES:
                    raise QueryRejected(f"A parameter names a protected property ({key})")
                walk(item)
        elif isinstance(value, list | tuple):
            for item in value:
                walk(item)

    walk(params)


# ---------------------------------------------------------------------------- answer values


def _properties(items: Any) -> dict[str, Any]:
    return {key: json_value(value) for key, value in dict(items).items() if key not in PROTECTED_PROPERTIES}


def _node(node: Node) -> dict[str, Any]:
    return {"identity": node.element_id, "labels": sorted(node.labels), "properties": _properties(node)}


def _relationship(relationship: Relationship) -> dict[str, Any]:
    start = relationship.start_node
    end = relationship.end_node
    return {
        "identity": relationship.element_id,
        "type": relationship.type,
        "start": start.element_id if start is not None else None,
        "end": end.element_id if end is not None else None,
        "properties": _properties(relationship),
    }


def json_value(value: Any) -> Any:
    """A JSON-serialisable rendering of a Bolt value, protected properties and hashes left out."""
    if value is None or isinstance(value, bool | int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, str):
        return REDACTED if value.startswith(HASH_PREFIX) else value
    if isinstance(value, Node):
        return _node(value)
    if isinstance(value, Relationship):
        return _relationship(value)
    if isinstance(value, Path):
        return {
            "nodes": [_node(node) for node in value.nodes],
            "relationships": [_relationship(rel) for rel in value.relationships],
            "length": len(value),
        }
    if isinstance(value, DateTime | Date | Time | Duration):  # before the sequences: a Duration is a tuple
        return value.iso_format()
    if isinstance(value, Point):  # so is a Point
        coordinates = dict(zip(("x", "y", "z"), value, strict=False))
        return {"srid": getattr(value, "srid", None), **coordinates}
    if isinstance(value, dict):
        return _properties(value)
    if isinstance(value, list | tuple | frozenset | set):
        return [json_value(item) for item in value]
    if isinstance(value, bytes | bytearray):
        return base64.b64encode(bytes(value)).decode("ascii")
    return str(value)


# ---------------------------------------------------------------------------- running


class QueryResult(BaseModel):
    columns: list[str]
    rows: list[list[Any]]
    truncated: bool


async def read_records(
    graph: Graph, cypher: str, params: dict[str, Any], *, timeout_seconds: float, max_rows: int | None = None
) -> tuple[list[str], list[dict[str, Any]], bool]:
    """Run one reading statement in a read transaction and stop at the time limit: the columns, the records as
    the driver gives them (at most ``max_rows`` when given), and whether there were more.

    Neo4j is told the transaction timeout and stops the statement itself; Memgraph is not (it does not
    take the Bolt transaction timeout), so a client-side limit a second later covers both. Memgraph also
    goes on running a statement after the client has gone, for up to ten minutes, and holds its storage
    meanwhile, so that no schema statement gets through; the transaction carries a marker in its metadata,
    and at the limit the server is told to stop it.
    """
    tx_timeout = timeout_seconds if graph.dialect.name is GraphDialect.NEO4J else None
    marker = new_id()

    async def work() -> tuple[list[str], list[dict[str, Any]], bool]:
        async with graph.driver.session(database=graph.database, default_access_mode=READ_ACCESS) as session:
            tx = await session.begin_transaction(timeout=tx_timeout, metadata={QUERY_MARKER: marker})
            try:
                result = await tx.run(cast("LiteralString", cypher), params)
                columns = list(result.keys())
                records: list[dict[str, Any]] = []
                truncated = False
                async for record in result:
                    if max_rows is not None and len(records) >= max_rows:
                        truncated = True
                        break
                    records.append(dict(record.items()))
                return columns, records, truncated
            finally:
                with contextlib.suppress(Exception):
                    await tx.close()  # a rollback: nothing was written, and the rest of the stream is dropped

    try:
        return await asyncio.wait_for(work(), timeout_seconds + 1.0)
    except TimeoutError:
        await stop_on_the_server(graph, marker)
        raise


async def run_read_query(
    graph: Graph, cypher: str, params: dict[str, Any], *, max_rows: int, timeout_seconds: float
) -> QueryResult:
    """The administrators' form of :func:`read_records`: at most ``max_rows`` rows, as lists of JSON values."""
    columns, records, truncated = await read_records(
        graph, cypher, params, timeout_seconds=timeout_seconds, max_rows=max_rows
    )
    rows = [[json_value(record[column]) for column in columns] for record in records]
    return QueryResult(columns=columns, rows=rows, truncated=truncated)


class ReadingGraph:
    """A graph to IFC-LPG's named queries (``ifc_db.queries``): ``run`` as the library's ``Graph`` protocol, and
    ``read`` for its reading statements through :func:`read_records`, with the read transaction, the time limit
    and the stop on the server. The server's own :class:`Graph` is not handed over as it is: its ``read`` runs a
    transaction function and means something else."""

    def __init__(self, graph: Graph) -> None:
        self.graph = graph

    async def run(self, query: str, /, **params: Any) -> list[dict[str, Any]]:
        return await self.graph.run(query, **params)

    async def read_rows(
        self, statement: str, params: dict[str, Any], *, timeout_seconds: float
    ) -> list[dict[str, Any]]:
        _columns, records, _truncated = await read_records(
            self.graph, statement, params, timeout_seconds=timeout_seconds
        )
        return records


async def stop_on_the_server(graph: Graph, marker: str) -> int:
    """Stop the transactions that carry ``marker`` where the server would go on running them (Memgraph). Returns how
    many were stopped; a failure here is logged and leaves the time limit's answer as it is."""
    statement = graph.dialect.show_transactions
    if statement is None:
        return 0
    stopped = 0
    try:
        for row in await graph.schema_rows(statement):
            if (row.get("metadata") or {}).get(QUERY_MARKER) == marker:
                await graph.schema_rows(graph.dialect.terminate_transaction(str(row.get("transaction_id"))))
                stopped += 1
    except Exception as exc:
        log.warning("graph_query_not_stopped", error=type(exc).__name__)
    return stopped


# ---------------------------------------------------------------------------- the route


class GraphQuery(BaseModel):
    cypher: str = Field(min_length=1, max_length=MAX_STATEMENT_LENGTH, description="One reading Cypher statement")
    params: dict[str, Any] = Field(default_factory=dict, description="Parameters the statement refers to as $name")


@router.post("/query", summary="Administration (extension): run one read-only Cypher statement")
async def graph_query(
    request: Request, principal: AdminPrincipal, body: GraphQuery, graph: GraphDep, settings: SettingsDep
) -> QueryResult:
    """Read-only Cypher against the whole graph for administrators; see the module documentation for the fences."""
    statement = body.cypher.strip()
    started = time.monotonic()

    async def trace(**details: Any) -> None:
        await audit.record(
            graph,
            "admin.graph.query",
            actor=principal.user_id,
            client_id=principal.client_id,
            ip=client_ip(request),
            details={"statement": statement[:AUDIT_STATEMENT_LENGTH], **details},
        )

    try:
        check_statement(statement)
        check_parameters(body.params)
    except QueryRejected as exc:
        await trace(refused=str(exc))
        raise HTTPException(400, str(exc)) from None
    try:
        result = await run_read_query(
            graph,
            statement,
            body.params,
            max_rows=settings.graph_query_max_rows,
            timeout_seconds=settings.graph_query_timeout_seconds,
        )
    except (TimeoutError, Neo4jError) as exc:
        code = getattr(exc, "code", None) or "timeout"
        await trace(failed=code)
        if isinstance(exc, TimeoutError) or "TimedOut" in code:  # Neo4j's own verdict or the client-side limit
            raise HTTPException(
                400, f"The query exceeded the time limit of {settings.graph_query_timeout_seconds:g} seconds"
            ) from None
        raise HTTPException(400, f"The database rejected the query: {exc.message}") from None
    await trace(rows=len(result.rows), truncated=result.truncated, ms=int((time.monotonic() - started) * 1000))
    return result
