# This file was generated with the assistance of an AI coding tool.
"""The difference between two IFC document versions: an extension of the Documents API (ADR 0021, OB-30).

``GET /documents/1.0/documents/{id}/versions/{index}/ifc-diff/{other_index}`` compares two versions of a document, or
with ``?other_document_id=`` a version of another document of a project the member is in, element by element: what
the other has that this one lacks, what it lacks, and what differs, by GlobalId and path, as the worker
``opencde.ifcgraph.diff`` finds it. The difference is computed on request in a worker process and never stored. The
same bearer token as the Documents API.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Path, Query
from pydantic import BaseModel, ConfigDict, Field

from opencde.auth.dependencies import DocumentsPrincipal
from opencde.deps import SettingsDep
from opencde.ids import is_uuid, normalize_guid
from opencde.ifcgraph.service import IfcGraphDep, IfcGraphService
from opencde.store.documents.versions import DocumentsDep, VersionRecord

TAG = "IFC diff (extension)"

router = APIRouter(prefix="/documents/1.0", tags=[TAG])

DocumentId = Annotated[str, Path(alias="document_id", max_length=64)]
VersionIndex = Annotated[int, Path(alias="version_index", ge=1, le=1_000_000_000)]
OtherIndex = Annotated[int, Path(alias="other_index", ge=1, le=1_000_000_000)]
OtherDocument = Annotated[str | None, Query(alias="other_document_id", max_length=64)]


class IfcDiffElement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    guid: str
    type: str
    name: str | None = None
    storey: str | None = None


class IfcDiffAttribute(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(
        description="A direct attribute by its name, a property as `Pset.Property`, `ObjectPlacement` (the 4 by 4 "
        "matrix), `Representation` (a fingerprint of the shape), `Container` (the storey's GlobalId), `Type` (the "
        "type object's GlobalId), or `type` when the class changed."
    )
    old: Any = None
    new: Any = None


class IfcDiffChanged(IfcDiffElement):
    attributes: list[IfcDiffAttribute]


class IfcDiffSide(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str
    version_index: int


class IfcDiff(BaseModel):
    model_config = ConfigDict(extra="forbid")

    a: IfcDiffSide = Field(description="This version.")
    b: IfcDiffSide = Field(description="The version compared with.")
    added: list[IfcDiffElement] = Field(description="Rooted entities only `b` has.")
    removed: list[IfcDiffElement] = Field(description="Rooted entities only `a` has.")
    changed: list[IfcDiffChanged] = Field(description="Rooted entities in both whose attributes differ.")
    same: int = Field(description="How many rooted entities are in both and the same.")
    truncated: bool = Field(description="True when a list had more than the server keeps (10,000).")


async def _version(documents: Any, user_id: str, document_id: str, version_index: int) -> VersionRecord:
    if not is_uuid(document_id):
        raise HTTPException(404, "Document version not found")
    record = await documents.version(
        user_id=user_id, document_id=normalize_guid(document_id), version_index=version_index
    )
    if record is None:
        raise HTTPException(404, "Document version not found")
    if not IfcGraphService.wants(record.file_name):
        raise HTTPException(400, f"Version {version_index} of {record.title} is not an IFC file")
    return record


@router.get(
    "/documents/{document_id}/versions/{version_index}/ifc-diff/{other_index}",
    summary="Compare two IFC document versions element by element",
    response_model=IfcDiff,
    response_model_exclude_none=True,
)
async def ifc_diff(
    principal: DocumentsPrincipal,
    document_id: DocumentId,
    version_index: VersionIndex,
    other_index: OtherIndex,
    documents: DocumentsDep,
    ifcgraph: IfcGraphDep,
    settings: SettingsDep,
    other_document_id: OtherDocument = None,
) -> IfcDiff:
    """What `other_index` (of this document, or of `other_document_id`) has that this version lacks, what it lacks,
    and what differs, by GlobalId and path. Computed on request; a large model takes a while. 404 when the IFC-DB
    module is off or a version is not yours, 400 when a version is not an IFC file."""
    if ifcgraph is None or not settings.ifcgraph_enabled:
        raise HTTPException(404, "The IFC-DB module is off on this server")
    a = await _version(documents, principal.user_id, document_id, version_index)
    b = await _version(documents, principal.user_id, other_document_id or document_id, other_index)
    if a.document_id == b.document_id and a.version_index == b.version_index:
        raise HTTPException(400, "A version is compared with another one")
    try:
        report = await ifcgraph.diff(a=(a.storage_key, a.file_name), b=(b.storage_key, b.file_name))
    except RuntimeError as exc:
        raise HTTPException(400, f"The comparison could not be made: {exc}") from None
    return IfcDiff(
        a=IfcDiffSide(document_id=a.document_id, version_index=a.version_index),
        b=IfcDiffSide(document_id=b.document_id, version_index=b.version_index),
        **report,
    )
