# This file was generated with the assistance of an AI coding tool.
"""The published schema of a change set: an extension of the Documents API (ADR 0021).

``GET /documents/1.0/ifc-changes/schema`` is the ``reference_schema`` of a BCF topic whose ``bim_snippet`` carries a
change set (``documents/changes.py``). It is public and cacheable, as the capabilities document is, so that anyone who
reads a topic can read what its snippet means. The snippet itself is uploaded with BCF's ``PUT …/topics/{id}/snippet``,
which checks it against this schema when the topic's ``snippet_type`` is ``DataregiumIfcChangeSet``.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Path
from fastapi.responses import JSONResponse

from opencde.auth.dependencies import DocumentsPrincipal
from opencde.deps import SettingsDep
from opencde.documents.changes import SCHEMA_PATH, change_set_schema
from opencde.ids import is_uuid, normalize_guid
from opencde.store.documents.versions import DocumentsDep

TAG = "IFC change sets (extension)"

router = APIRouter(tags=[TAG])

DocumentId = Annotated[str, Path(alias="document_id", max_length=64)]
VersionIndex = Annotated[int, Path(alias="version_index", ge=1, le=1_000_000_000)]


@router.get(
    SCHEMA_PATH,
    summary="The schema of a change set carried by a BCF topic's bim_snippet",
    response_class=JSONResponse,
)
async def ifc_change_set_schema(settings: SettingsDep) -> JSONResponse:
    """JSON Schema 2020-12 of the `DataregiumIfcChangeSet` snippet type: the base version, the provenance and the
    changes, each on one attribute of one instance. No authentication: the schema says nothing about any project."""
    return JSONResponse(
        change_set_schema(settings.public_url),
        media_type="application/schema+json",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.get(
    "/documents/1.0/documents/{document_id}/versions/{version_index}/ifc-changes",
    summary="The change set a document version was approved from",
)
async def ifc_changes_of_version(
    principal: DocumentsPrincipal, document_id: DocumentId, version_index: VersionIndex, documents: DocumentsDep
) -> dict[str, Any]:
    """The changes the version makes against its parent, as its topic proposed them (ADR 0021): `base`, who proposed
    and approved it, and `changes` in the form of the schema. 404 for a version that was uploaded as a whole file."""
    if not is_uuid(document_id):
        raise HTTPException(404, "Document version not found")
    found = await documents.change_set(
        user_id=principal.user_id, document_id=normalize_guid(document_id), version_index=version_index
    )
    if found is None:
        raise HTTPException(404, "This version was not approved from a change set")
    return found
