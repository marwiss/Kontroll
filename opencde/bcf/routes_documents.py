# This file was generated with the assistance of an AI coding tool.
"""BCF API 3.3.1 Project files information and 3.8 Document services."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Path, Query, Request, Response
from fastapi.responses import StreamingResponse

from opencde.bcf.access import ProjectCtx, parse_guid
from opencde.bcf.binary import file_response, filename_from_content_disposition, receive_upload
from opencde.bcf.schemas import dump
from opencde.deps import SettingsDep, StorageDep
from opencde.ids import is_uuid, new_id, normalize_guid
from opencde.ifcgraph.service import IfcGraphDep
from opencde.ratelimit import RATE_UPLOAD, limiter
from opencde.storage import make_key
from opencde.store.bcf.documents import BcfDocumentsDep

router = APIRouter(prefix="/projects/{project_id}", tags=["BCF API"])

DocumentId = Annotated[str, Path(alias="document_id", max_length=64)]
DEFAULT_FILENAME = "document"


@router.get("/files_information", summary="3.3.1 GET Project Files Information")
async def files_information_get(
    ctx: ProjectCtx, documents: BcfDocumentsDep, settings: SettingsDep
) -> list[dict[str, Any]]:
    """The project's files a topic header may reference, with display fields for a picker."""
    base_url = str(settings.public_url).rstrip("/")
    found = await documents.files_information(user_id=ctx.user_id, project_id=ctx.project_id, base_url=base_url)
    return [dump(item) for item in found]


@router.get("/documents", summary="3.8.1 GET Documents")
async def documents_get(ctx: ProjectCtx, documents: BcfDocumentsDep) -> list[dict[str, Any]]:
    return [dump(item) for item in await documents.search(user_id=ctx.user_id, project_id=ctx.project_id)]


@router.post("/documents", summary="3.8.2 POST Document", status_code=201)
@limiter.limit(RATE_UPLOAD)
async def document_post(
    request: Request,
    response: Response,  # slowapi writes its rate-limit headers here, since the endpoint returns a dict
    ctx: ProjectCtx,
    documents: BcfDocumentsDep,
    storage: StorageDep,
    settings: SettingsDep,
    ifcgraph: IfcGraphDep,
    guid: Annotated[str | None, Query(max_length=64)] = None,
) -> dict[str, Any]:
    """Upload a document as the request body (Foundation API 1.9); the file name comes from
    ``Content-Disposition``. Needs ``createDocument``; ``409`` when ``?guid=`` already exists."""
    ctx.require(ctx.can("createDocument", entity="project"), "createDocument")
    if guid is not None and not is_uuid(guid):
        raise HTTPException(400, "guid must be a UUID")
    document_guid = normalize_guid(guid) if guid else new_id()
    if await documents.exists(document_guid):
        raise HTTPException(409, "A document with this guid already exists")  # Foundation API 1.5.1
    filename = filename_from_content_disposition(request.headers.get("content-disposition")) or DEFAULT_FILENAME
    key = make_key("bcf-documents", document_guid)
    size = await receive_upload(request, storage, key, settings.max_upload_bytes)
    try:
        created = await documents.create(
            project_id=ctx.project_id,
            guid=document_guid,
            filename=filename,
            author=ctx.username,
            storage_key=key,
            size=size,
        )
    except BaseException:
        storage.delete(key)
        raise
    if ifcgraph is not None:
        await ifcgraph.schedule(
            project_id=ctx.project_id, storage_key=key, file_name=filename, bcf_document_guid=document_guid
        )
    return dump(created)


@router.get("/documents/{document_id}", summary="3.8.3 GET Document", response_class=StreamingResponse)
async def document_get(
    ctx: ProjectCtx, document_id: DocumentId, documents: BcfDocumentsDep, storage: StorageDep
) -> StreamingResponse:
    """The document as a download; always ``application/octet-stream``, never rendered."""
    guid = parse_guid(document_id, "Document")
    document = await documents.get(user_id=ctx.user_id, project_id=ctx.project_id, guid=guid)
    if document is None:
        raise HTTPException(404, "Document not found")
    return file_response(
        storage, document["storage_key"], media_type="application/octet-stream", filename=document["filename"]
    )
