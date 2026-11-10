# This file was generated with the assistance of an AI coding tool.
"""Named queries on the IFC graph of a document version: an extension of the Documents API (ADR 0016).

``GET /documents/1.0/documents/{id}/versions/{index}/ifc-queries`` lists the queries a member may ask of the version's
model, with their parameters and columns, and says how far the model's conversion has come. ``GET …/ifc-queries/{name}``
asks one, with its parameters in the query string, and answers ``{"name", "columns", "rows", "truncated"}``, rows as
lists in the order of the columns, as the administrators' graph query does. The same bearer token as the Documents API
reaches both; the statements are in ``ifcgraph/queries.py``.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Path, Query, Request
from neo4j.exceptions import Neo4jError
from pydantic import BaseModel, Field

from opencde.admin.graph_query import run_read_query
from opencde.auth.dependencies import DocumentsPrincipal
from opencde.deps import GraphDep, SettingsDep
from opencde.documents.repository import DocumentsDep
from opencde.graph.graph import Graph
from opencde.ids import is_uuid, normalize_guid
from opencde.ifcgraph.queries import (
    CHANGED_SINCE,
    CHANGED_SINCE_COLUMNS,
    MAX_ROWS,
    QUERIES,
    TIMEOUT_SECONDS,
    InvalidParameters,
)
from opencde.settings import Settings

TAG = "IFC queries (extension)"

router = APIRouter(prefix="/documents/1.0", tags=[TAG])

DocumentId = Annotated[str, Path(alias="document_id", max_length=64)]
VersionIndex = Annotated[int, Path(alias="version_index", ge=1, le=1_000_000_000)]
QueryName = Annotated[str, Path(alias="name", max_length=64, pattern=r"^[a-z][a-z-]*$")]


class IfcQueryParameter(BaseModel):
    name: str
    description: str
    required: bool


class IfcQuery(BaseModel):
    name: str = Field(description="What the query is asked by, in the path.")
    description: str
    parameters: list[IfcQueryParameter] = Field(description="Given in the query string; the rest are left out.")
    columns: list[str] = Field(description="The columns of every row, in order.")


class IfcQueries(BaseModel):
    model_state: str = Field(
        description="`done` when the queries can be asked; `queued`, `running` or `failed` before or instead."
    )
    max_rows: int = Field(description="The most rows an answer holds; `truncated` says when there were more.")
    queries: list[IfcQuery]


class IfcQueryAnswer(BaseModel):
    name: str
    columns: list[str]
    rows: list[list[Any]] = Field(description="Each row's values in the order of the columns.")
    truncated: bool = Field(description="True when the model had more rows than an answer holds.")


async def _model_state(
    graph: Graph, documents: Any, settings: Settings, user_id: str, document_id: str, version_index: int
) -> str:
    """How far the version's model has come; 404 when the user may not see the version or it has no model."""
    if not settings.ifcgraph_enabled:
        raise HTTPException(404, "The IFC-LPG module is off on this server")
    if not is_uuid(document_id):
        raise HTTPException(404, "Document version not found")
    rows = await graph.run(
        """
        MATCH (:User {id: $user_id})-[:MEMBER_OF]->(:Project)-[:HAS_MODEL]->(m:IfcModel)
        WHERE m.document_id = $document_id AND m.version_index = $version_index
        RETURN m.state AS state ORDER BY m.created_at DESC LIMIT 1
        """,
        user_id=user_id,
        document_id=document_id,
        version_index=version_index,
    )
    if rows:
        return str(rows[0]["state"])
    if await documents.version(user_id=user_id, document_id=document_id, version_index=version_index):
        raise HTTPException(404, "This version has no IFC graph: it is not an IFC file, or came before the module")
    raise HTTPException(404, "Document version not found")


@router.get(
    "/documents/{document_id}/versions/{version_index}/ifc-queries",
    summary="List the named queries that can be asked of an IFC document version's graph",
    response_model=IfcQueries,
)
async def ifc_queries(
    principal: DocumentsPrincipal,
    document_id: DocumentId,
    version_index: VersionIndex,
    documents: DocumentsDep,
    graph: GraphDep,
    settings: SettingsDep,
) -> IfcQueries:
    """The queries, their parameters and columns, and how far the model's conversion has come."""
    document_id = normalize_guid(document_id) if is_uuid(document_id) else document_id
    state = await _model_state(graph, documents, settings, principal.user_id, document_id, version_index)
    return IfcQueries(
        model_state=state,
        max_rows=MAX_ROWS,
        queries=[
            IfcQuery(
                name=query.name,
                description=query.description,
                parameters=[
                    IfcQueryParameter(name=p.name, description=p.description, required=p.required)
                    for p in query.parameters
                ],
                columns=list(query.columns),
            )
            for query in QUERIES.values()
        ]
        + [
            IfcQuery(
                name=CHANGED_SINCE,
                description="What changed in the document since a version: one row per change of each version's "
                "change set up to this one, or one row with `whole_file` for a version uploaded as a whole file.",
                parameters=[
                    IfcQueryParameter(name="since", description="The version index to count from", required=True)
                ],
                columns=list(CHANGED_SINCE_COLUMNS),
            )
        ],
    )


@router.get(
    "/documents/{document_id}/versions/{version_index}/ifc-queries/" + CHANGED_SINCE,
    summary="What changed in the document since a version, from the change sets of the versions between",
    response_model=IfcQueryAnswer,
)
async def ifc_changed_since(
    principal: DocumentsPrincipal,
    document_id: DocumentId,
    version_index: VersionIndex,
    documents: DocumentsDep,
    settings: SettingsDep,
    since: Annotated[int, Query(ge=0, le=1_000_000_000)],
) -> IfcQueryAnswer:
    """One row per change of every version after `since` up to this one, as its change set names it (by GlobalId or
    STEP id, path, attribute and operation); a version uploaded as a whole file gives one row with `whole_file` true,
    since anything may have changed in it. Answered from the versions, so it needs no graph."""
    if not settings.ifcgraph_enabled:
        raise HTTPException(404, "The IFC-LPG module is off on this server")
    if not is_uuid(document_id):
        raise HTTPException(404, "Document version not found")
    document_id = normalize_guid(document_id)
    if await documents.version(user_id=principal.user_id, document_id=document_id, version_index=version_index) is None:
        raise HTTPException(404, "Document version not found")
    if since >= version_index:
        raise HTTPException(400, "since must be an earlier version than this one")
    rows: list[list[Any]] = []
    truncated = False
    for version in await documents.versions_since(
        user_id=principal.user_id, document_id=document_id, since=since, until=version_index
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
    return IfcQueryAnswer(name=CHANGED_SINCE, columns=list(CHANGED_SINCE_COLUMNS), rows=rows, truncated=truncated)


@router.get(
    "/documents/{document_id}/versions/{version_index}/ifc-queries/{name}",
    summary="Ask one named query of an IFC document version's graph",
    response_model=IfcQueryAnswer,
)
async def ifc_query(
    request: Request,
    principal: DocumentsPrincipal,
    document_id: DocumentId,
    version_index: VersionIndex,
    name: QueryName,
    documents: DocumentsDep,
    graph: GraphDep,
    settings: SettingsDep,
) -> IfcQueryAnswer:
    """The rows the query finds, at most `max_rows` of them. 409 while the model is still being converted."""
    query = QUERIES.get(name)
    document_id = normalize_guid(document_id) if is_uuid(document_id) else document_id
    state = await _model_state(graph, documents, settings, principal.user_id, document_id, version_index)
    if query is None:
        raise HTTPException(404, f"There is no named query {name}")
    try:
        values = query.bind(dict(request.query_params))
    except InvalidParameters as exc:
        raise HTTPException(400, str(exc)) from None
    if state != "done":
        raise HTTPException(409, f"The IFC graph of this version is {state}, not done")
    params = {**values, "user_id": principal.user_id, "document_id": document_id, "version_index": version_index}
    try:
        result = await run_read_query(graph, query.cypher, params, max_rows=MAX_ROWS, timeout_seconds=TIMEOUT_SECONDS)
    except TimeoutError:
        raise HTTPException(400, f"The query exceeded the time limit of {TIMEOUT_SECONDS:g} seconds") from None
    except Neo4jError as exc:
        if "TimedOut" in (exc.code or ""):
            raise HTTPException(400, f"The query exceeded the time limit of {TIMEOUT_SECONDS:g} seconds") from None
        raise
    return IfcQueryAnswer(name=query.name, columns=result.columns, rows=result.rows, truncated=result.truncated)
