# This file was generated with the assistance of an AI coding tool.
"""The named queries on the IFC graph of a document version, for members of its project (ADR 0016).

Reading a model is asking it questions by name with parameters, never with Cypher of one's own; free Cypher stays
with administrators (``admin/graph_query.py``). The catalogue and its statements are IFC-DB's (``ifc_db.queries``,
F38 a): the library owns the graph's form and proves the queries on both databases, and a query added there appears
in the listing. The server finds the model through the member's project, chooses the archive or the working copy,
holds the limits, and adds ``changed-since``, answered from the versions' change sets without the graph. Those are
the functions here, which the Documents API's routes (``documents/routes_queries.py``) and the MCP tool
``server_query`` (``mcp/queries.py``) both answer from; they refuse as the routes do, with fixed texts that never
quote the request.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from fastapi import HTTPException
from ifc_db.queries import (
    MAX_ROWS,
    QUERIES,
    TIMEOUT_SECONDS,
    InvalidParameters,
    NamedQuery,
    UnknownQuery,
    catalogue,
    run_query,
)
from neo4j.exceptions import Neo4jError

from opencde.admin.graph_query import ReadingGraph
from opencde.ids import is_uuid

if TYPE_CHECKING:
    from opencde.graph.graph import Graph
    from opencde.ifcgraph.service import IfcGraphService
    from opencde.settings import Settings
    from opencde.store.protocols import DocumentStore

#: The query on what changed since a version, answered from the versions' change sets, not from the graph; listed and
#: announced with the others.
CHANGED_SINCE = "changed-since"
CHANGED_SINCE_COLUMNS = (
    "version_index",
    "change_set_id",
    "author",
    "approved_by",
    "whole_file",
    "guid",
    "step_id",
    "path",
    "attribute",
    "op",
)
_CHANGED_SINCE_DESCRIPTION = (
    "What changed in the document since a version: one row per change of each version's change set up to this one, "
    "or one row with `whole_file` for a version uploaded as a whole file."
)
#: The kind of ``since``, beside the library's ``text``, ``class`` and ``global_id``: a version index, 0 and up.
VERSION_INDEX = "version_index"


def named_queries() -> list[dict[str, Any]]:
    """Every query a member may ask of a version, as plain data: the library's catalogue, then ``changed-since``,
    each with its name, description, parameters (name, description, required, kind) and columns."""
    since = {"name": "since", "description": "The version index to count from", "required": True, "kind": VERSION_INDEX}
    changes = {
        "name": CHANGED_SINCE,
        "description": _CHANGED_SINCE_DESCRIPTION,
        "parameters": [since],
        "columns": list(CHANGED_SINCE_COLUMNS),
    }
    return [*catalogue(), changes]


async def model_state(
    graph: Graph, documents: DocumentStore, settings: Settings, user_id: str, document_id: str, version_index: int
) -> tuple[str, str]:
    """How far the version's model has come, and its id; 404 when the user may not see the version or it has no
    model."""
    if not settings.ifcgraph_enabled:
        raise HTTPException(404, "The IFC-DB module is off on this server")
    if not is_uuid(document_id):
        raise HTTPException(404, "Document version not found")
    rows = await graph.run(
        """
        MATCH (:User {id: $user_id})-[:MEMBER_OF]->(:Project)-[:HAS_CONVERSION]->(m:Conversion)
        WHERE m.document_id = $document_id AND m.version_index = $version_index
        RETURN m.state AS state, m.id AS id ORDER BY m.created_at DESC LIMIT 1
        """,
        user_id=user_id,
        document_id=document_id,
        version_index=version_index,
    )
    if rows:
        return str(rows[0]["state"]), str(rows[0]["id"])
    if await documents.version(user_id=user_id, document_id=document_id, version_index=version_index):
        raise HTTPException(404, "This version has no IFC graph: it is not an IFC file, or came before the module")
    raise HTTPException(404, "Document version not found")


async def list_queries(
    graph: Graph,
    documents: DocumentStore,
    settings: Settings,
    ifcgraph: IfcGraphService | None,
    *,
    user_id: str,
    document_id: str,
    version_index: int,
) -> dict[str, Any]:
    """The queries a member may ask of the version, with how far its model has come and whether the working copy
    holds it (ADR 0024); 404 as :func:`model_state`."""
    state, model_id = await model_state(graph, documents, settings, user_id, document_id, version_index)
    return {
        "workcopy": ifcgraph is not None and await ifcgraph.in_workcopy(model_id),
        "model_state": state,
        "queries": named_queries(),
    }


async def ask_query(
    graph: Graph,
    documents: DocumentStore,
    settings: Settings,
    ifcgraph: IfcGraphService | None,
    *,
    user_id: str,
    document_id: str,
    version_index: int,
    name: str,
    parameters: Mapping[str, str | None],
) -> dict[str, Any]:
    """One named query of the version's model: ``{"name", "columns", "rows", "truncated"}`` with at most
    :data:`MAX_ROWS` rows, within :data:`TIMEOUT_SECONDS`, asked of the working copy when it holds the model (ADR
    0024) and else of the IFC graph, apart from the server's own (F24 a). 404 as :func:`model_state` and for a name
    that is no query, 400 for parameters that do not fit and for a query past its time, 409 while the model is still
    being converted."""
    query = QUERIES.get(name)
    state, model_id = await model_state(graph, documents, settings, user_id, document_id, version_index)
    if query is None:
        raise HTTPException(404, f"There is no named query {name}")
    try:
        values = query.bind(parameters)
    except InvalidParameters as exc:
        raise HTTPException(400, str(exc)) from None
    if state != "done":
        raise HTTPException(409, f"The IFC graph of this version is {state}, not done")
    target = ifcgraph.graph if ifcgraph is not None else graph
    if ifcgraph is not None and ifcgraph.workcopy is not None and await ifcgraph.in_workcopy(model_id):
        target = ifcgraph.workcopy
    try:
        return await run_query(
            ReadingGraph(target), model_id, name, values, max_rows=MAX_ROWS, timeout_seconds=TIMEOUT_SECONDS
        )
    except TimeoutError:
        raise HTTPException(400, f"The query exceeded the time limit of {TIMEOUT_SECONDS:g} seconds") from None
    except Neo4jError as exc:
        if "TimedOut" in (exc.code or ""):
            raise HTTPException(400, f"The query exceeded the time limit of {TIMEOUT_SECONDS:g} seconds") from None
        raise


async def changed_since(
    documents: DocumentStore, settings: Settings, *, user_id: str, document_id: str, version_index: int, since: int
) -> dict[str, Any]:
    """What changed in the document after version ``since`` up to this one: one row per change of every version's
    change set, as it names it, and one row with ``whole_file`` true for a version uploaded as a whole file, at most
    :data:`MAX_ROWS` of them. Answered from the versions, so it needs no graph. 404 when the user may not see the
    version, 400 when ``since`` is not an earlier version."""
    if not settings.ifcgraph_enabled:
        raise HTTPException(404, "The IFC-DB module is off on this server")
    if not is_uuid(document_id):
        raise HTTPException(404, "Document version not found")
    if await documents.version(user_id=user_id, document_id=document_id, version_index=version_index) is None:
        raise HTTPException(404, "Document version not found")
    if since >= version_index:
        raise HTTPException(400, "since must be an earlier version than this one")
    rows: list[list[Any]] = []
    truncated = False
    for version in await documents.versions_since(
        user_id=user_id, document_id=document_id, since=since, until=version_index
    ):
        head = [version["version_index"], version["change_set_id"], version["author"], version["approved_by"]]
        if version["changes"] is None:
            rows.append([*head, True, None, None, None, None, None])
            continue
        for change in version["changes"]:
            if len(rows) >= MAX_ROWS:
                truncated = True
                break
            rows.append(
                [
                    *head,
                    False,
                    change.get("guid"),
                    change.get("step_id"),
                    change.get("path"),
                    change.get("attribute"),
                    change.get("op"),
                ]
            )
    return {"name": CHANGED_SINCE, "columns": list(CHANGED_SINCE_COLUMNS), "rows": rows, "truncated": truncated}


__all__ = [
    "CHANGED_SINCE",
    "CHANGED_SINCE_COLUMNS",
    "MAX_ROWS",
    "QUERIES",
    "TIMEOUT_SECONDS",
    "VERSION_INDEX",
    "InvalidParameters",
    "NamedQuery",
    "UnknownQuery",
    "ask_query",
    "catalogue",
    "changed_since",
    "list_queries",
    "model_state",
    "named_queries",
    "run_query",
]
