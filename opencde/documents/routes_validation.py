# This file was generated with the assistance of an AI coding tool.
"""The report of checking an uploaded IFC file against the IFC schema: an extension of the Documents API.

``GET /documents/1.0/documents/{id}/versions/{index}/ifc-validation`` answers a member of the project with the same
bearer token as the Documents API, so a client on the API's origin reads it the way it reads the version. The version's
metadata gives its address in ``ifc_validation_report`` (``documents/validation.py``).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Path

from opencde.auth.dependencies import DocumentsPrincipal
from opencde.documents.validation import IfcValidationReport, report
from opencde.ids import is_uuid, normalize_guid
from opencde.store.documents.versions import DocumentsDep

TAG = "IFC validation (extension)"

router = APIRouter(prefix="/documents/1.0", tags=[TAG])

DocumentId = Annotated[str, Path(alias="document_id", max_length=64)]
VersionIndex = Annotated[int, Path(alias="version_index", ge=1, le=1_000_000_000)]


@router.get(
    "/documents/{document_id}/versions/{version_index}/ifc-validation",
    summary="Get the result of checking an IFC document version against the IFC schema",
    response_model=IfcValidationReport,
    response_model_exclude_none=True,
)
async def ifc_validation_report(
    principal: DocumentsPrincipal, document_id: DocumentId, version_index: VersionIndex, documents: DocumentsDep
) -> IfcValidationReport:
    """Every issue the check found, up to 10,000, each with the GlobalId of its element where it has one.

    The status is `pending` until the file has been checked. 404 for a version that is not an IFC file, or that was
    uploaded while checking was off.
    """
    if not is_uuid(document_id):
        raise HTTPException(404, "Document version not found")
    document_id = normalize_guid(document_id)
    found = await documents.validation(
        user_id=principal.user_id, document_id=document_id, version_index=version_index, with_issues=True
    )
    if found is not None:
        return report(found)
    if await documents.version(user_id=principal.user_id, document_id=document_id, version_index=version_index):
        raise HTTPException(404, "This version has not been checked against the IFC schema")
    raise HTTPException(404, "Document version not found")
