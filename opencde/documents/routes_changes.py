# This file was generated with the assistance of an AI coding tool.
"""The published schema of a change set: an extension of the Documents API (ADR 0021).

``GET /documents/1.0/ifc-changes/schema`` is the ``reference_schema`` of a BCF topic whose ``bim_snippet`` carries a
change set (``documents/changes.py``). It is public and cacheable, as the capabilities document is, so that anyone who
reads a topic can read what its snippet means. The snippet itself is uploaded with BCF's ``PUT …/topics/{id}/snippet``,
which checks it against this schema when the topic's ``snippet_type`` is ``DataregiumIfcChangeSet``.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from opencde.deps import SettingsDep
from opencde.documents.changes import SCHEMA_PATH, change_set_schema

TAG = "IFC change sets (extension)"

router = APIRouter(tags=[TAG])


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
