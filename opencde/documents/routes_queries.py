# This file was generated with the assistance of an AI coding tool.
"""Named queries on the IFC graph of a document version: an extension of the Documents API (ADR 0016).

``GET /documents/1.0/documents/{id}/versions/{index}/ifc-queries`` lists the queries a member may ask of the version's
model, with their parameters and columns, and says how far the model's conversion has come. ``GET …/ifc-queries/{name}``
asks one, with its parameters in the query string, and answers ``{"name", "columns", "rows", "truncated"}``, rows as
lists in the order of the columns, as the administrators' graph query does. The same bearer token as the Documents API
reaches both; the statements are IFC-DB's (``ifc_db.queries``), and the answers come from the functions of
``ifcgraph/queries.py``, which the MCP tool ``server_query`` answers from too.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Path, Query, Request
from pydantic import BaseModel, Field

from opencde.auth.dependencies import DocumentsPrincipal
from opencde.deps import GraphDep, SettingsDep
from opencde.ids import is_uuid, normalize_guid
from opencde.ifcgraph.queries import CHANGED_SINCE, MAX_ROWS, ask_query, changed_since, list_queries
from opencde.ifcgraph.service import IfcGraphDep
from opencde.store.documents.versions import DocumentsDep

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
    workcopy: bool = Field(
        False, description="True when the version's model is in the working copy, which answers the queries (ADR 0024)."
    )
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
    ifcgraph: IfcGraphDep,
) -> IfcQueries:
    """The queries, their parameters and columns, and how far the model's conversion has come."""
    document_id = normalize_guid(document_id) if is_uuid(document_id) else document_id
    listed = await list_queries(
        graph,
        documents,
        settings,
        ifcgraph,
        user_id=principal.user_id,
        document_id=document_id,
        version_index=version_index,
    )
    return IfcQueries(
        workcopy=listed["workcopy"],
        model_state=listed["model_state"],
        max_rows=MAX_ROWS,
        queries=[IfcQuery.model_validate(query) for query in listed["queries"]],
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
    document_id = normalize_guid(document_id) if is_uuid(document_id) else document_id
    answer = await changed_since(
        documents,
        settings,
        user_id=principal.user_id,
        document_id=document_id,
        version_index=version_index,
        since=since,
    )
    return IfcQueryAnswer(**answer)


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
    ifcgraph: IfcGraphDep,
) -> IfcQueryAnswer:
    """The rows the query finds, at most `max_rows` of them. 409 while the model is still being converted. The
    working copy answers when it holds the model (ADR 0024)."""
    document_id = normalize_guid(document_id) if is_uuid(document_id) else document_id
    answer = await ask_query(
        graph,
        documents,
        settings,
        ifcgraph,
        user_id=principal.user_id,
        document_id=document_id,
        version_index=version_index,
        name=name,
        parameters=dict(request.query_params),
    )
    return IfcQueryAnswer(**answer)
