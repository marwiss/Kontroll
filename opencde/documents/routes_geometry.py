# This file was generated with the assistance of an AI coding tool.
"""The geometry of an IFC document version as glTF: an extension of the Documents API (OB-37).

``GET /documents/1.0/documents/{id}/versions/{index}/ifc-geometry`` answers with a binary glTF (``.glb``) of the
version's products, built from the geometry records IFC-LPG's worker wrote when the version was converted: every
shared mesh once and a node per product that instances it, under one node per storey. ``lod=box`` gives the
products' boxes instead, a few bytes each; ``classes`` (IFC classes, comma-separated) and ``storey`` (a GlobalId)
pick the products. The file is built the first time it is asked for and kept; the ``ETag`` names the model and the
filters, so a client that sends ``If-None-Match`` gets ``304`` when it already has it. The same bearer token as the
Documents API; a member of the project reads it.
"""

from __future__ import annotations

import re
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query, Request, Response
from fastapi.responses import FileResponse

from opencde.auth.dependencies import DocumentsPrincipal
from opencde.deps import GraphDep, SettingsDep
from opencde.documents.repository import DocumentsDep
from opencde.ids import is_uuid
from opencde.ifcgraph.gltf import LODS
from opencde.ifcgraph.service import STATE_DONE, STATE_FAILED, IfcGraphDep

TAG = "IFC geometry (extension)"
MEDIA_TYPE = "model/gltf-binary"
MAX_CLASSES = 50
_CLASS = re.compile(r"^Ifc[A-Za-z0-9]{1,60}$")
_GUID = re.compile(r"^[0-9A-Za-z_$]{22}$")

router = APIRouter(prefix="/documents/1.0", tags=[TAG])

DocumentId = Annotated[str, Path(alias="document_id", max_length=64)]
VersionIndex = Annotated[int, Path(alias="version_index", ge=1, le=1_000_000_000)]
Lod = Annotated[str, Query(description="`full` (the meshes) or `box` (a box per product).", max_length=8)]
Classes = Annotated[
    str | None, Query(description="IFC classes to keep, comma-separated, such as `IfcWall,IfcSlab`.", max_length=2000)
]
Storey = Annotated[str | None, Query(description="The GlobalId of the storey whose products to keep.", max_length=22)]


def _classes(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    names = tuple(sorted({name.strip() for name in value.split(",") if name.strip()}))
    if len(names) > MAX_CLASSES or any(not _CLASS.match(name) for name in names):
        raise HTTPException(400, f"classes is up to {MAX_CLASSES} IFC class names, comma-separated")
    return names


@router.get(
    "/documents/{document_id}/versions/{version_index}/ifc-geometry",
    summary="The geometry of an IFC document version as binary glTF",
    response_class=FileResponse,
    responses={
        200: {"content": {MEDIA_TYPE: {}}, "description": "The `.glb`; `ETag` names the model and the filters."},
        304: {"description": "The client's `If-None-Match` matches."},
        404: {
            "description": "Not a version of yours, not an IFC file, the module off, or no geometry for it "
            "(the geometry pass failed, or the version was converted before the pass existed)."
        },
        409: {"description": "The version is still being converted; try again shortly."},
    },
)
async def ifc_geometry(
    request: Request,
    principal: DocumentsPrincipal,
    document_id: DocumentId,
    version_index: VersionIndex,
    graph: GraphDep,
    documents: DocumentsDep,
    ifcgraph: IfcGraphDep,
    settings: SettingsDep,
    lod: Lod = "full",
    classes: Classes = None,
    storey: Storey = None,
) -> Response:
    """The products of the version as glTF 2.0 binary, in metres, with the model turned Y up (IFC's Z up is kept in
    each product's own matrix). Every node is named by its product's GlobalId and carries its class, STEP id and
    storey in `extras`; the storey nodes are named by the storey's GlobalId."""
    if ifcgraph is None or not settings.ifcgraph_enabled or not settings.ifcgraph_spatial:
        raise HTTPException(404, "The IFC-LPG module is off on this server, or its spatial layer is")
    if lod not in LODS:
        raise HTTPException(400, f"lod is one of {', '.join(LODS)}")
    if storey is not None and not _GUID.match(storey):
        raise HTTPException(400, "storey is a GlobalId of 22 characters")
    chosen = _classes(classes)
    if not is_uuid(document_id):
        raise HTTPException(404, "Document version not found")
    rows = await graph.run(
        """
        MATCH (:User {id: $user_id})-[:MEMBER_OF]->(:Project)-[:HAS_MODEL]->(m:Model)
        WHERE m.document_id = $document_id AND m.version_index = $version_index
        RETURN m.state AS state, m.id AS id, m.geometry_key AS geometry_key, m.spatial_pending AS pending
        ORDER BY m.created_at DESC LIMIT 1
        """,
        user_id=principal.user_id,
        document_id=document_id,
        version_index=version_index,
    )
    if not rows:
        if await documents.version(user_id=principal.user_id, document_id=document_id, version_index=version_index):
            raise HTTPException(404, "This version has no IFC graph: it is not an IFC file, or came before the module")
        raise HTTPException(404, "Document version not found")
    model = rows[0]
    if model["state"] == STATE_FAILED:
        raise HTTPException(404, "This version has no geometry: its conversion failed")
    if model["state"] != STATE_DONE or model["pending"]:
        raise HTTPException(409, "The version is still being converted; try again shortly")
    if not model["geometry_key"]:
        raise HTTPException(404, "This version has no geometry: its geometry pass failed, or came before it")
    try:
        built = await ifcgraph.geometry(model_id=str(model["id"]), lod=lod, classes=chosen, storey=storey)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None
    if built is None:
        raise HTTPException(404, "This version has no geometry")
    path, tag = built
    etag = f'"{model["id"]}-{tag}"'
    headers = {"ETag": etag, "Cache-Control": "private, max-age=3600", "Vary": "Authorization"}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    return FileResponse(
        path, media_type=MEDIA_TYPE, filename=f"{document_id}-v{version_index}-{lod}.glb", headers=headers
    )
