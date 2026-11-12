# This file was generated with the assistance of an AI coding tool.
"""Documents API 1.0: the endpoints clients call with a bearer token.

The paths the specification leaves to the server ("server-provided-path-…")
are fixed here and handed to clients inside the responses, never guessed:

* ``POST /upload-documents`` → ``upload_ui_url`` (browser), later
  ``upload_documents_url`` = ``POST /upload-sessions/{id}/instructions``,
  ``PUT|POST /upload-part/{part_id}``, ``POST …/files/{n}/complete`` and
  ``…/cancel``.
* ``POST /select-documents`` → ``select_documents_url`` (browser), later
  ``selected_documents_url`` = ``GET /selection-sessions/{id}/documents``.
* ``GET /documents/{id}/versions[/{index}[/metadata|/download]]`` and
  ``POST /document-versions`` with ``ETag``/``If-None-Match``.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Annotated, Any

import anyio
from fastapi import APIRouter, HTTPException, Path, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

from opencde import audit
from opencde.accounts.roles import may_upload
from opencde.auth.dependencies import DocumentsPrincipal
from opencde.bcf.binary import file_response, receive_upload
from opencde.deps import ClientsDep, GraphDep, ProjectsDep, SettingsDep, StorageDep, UsersDep, client_ip
from opencde.documents.assembly import AssemblyError, assemble
from opencde.documents.links import api_base, part_ranges, precheck_url, publication_url, validation_report_url
from opencde.documents.schemas import (
    DocumentDiscoverySessionInitialization,
    DocumentMetadata,
    DocumentMetadataEntry,
    DocumentQuery,
    DocumentQueryResult,
    DocumentsToUpload,
    DocumentToUpload,
    DocumentUploadSessionInitialization,
    DocumentVersion,
    DocumentVersions,
    LinkData,
    SelectDocuments,
    SelectedDocuments,
    UploadDocuments,
    UploadFileDetails,
    UploadFilePartInstruction,
)
from opencde.documents.validation import metadata_entries as validation_metadata
from opencde.errors import (
    CODE_IFC_VALIDATION_FAILED,
    CODE_UPLOAD_TOO_LARGE,
    CODE_VERSION_CONFLICT,
    ApiError,
    error_body,
)
from opencde.etag import etag_for, matches
from opencde.ids import is_uuid, new_id, normalize_guid
from opencde.ifcgraph.service import IfcGraphDep, IfcGraphService
from opencde.ratelimit import RATE_UPLOAD, limiter
from opencde.storage import make_key
from opencde.store.documents.sessions import (
    FILE_CANCELLED,
    FILE_DONE,
    FILE_PARTS,
    STATE_CANCELLED,
    STATE_METADATA,
    STATE_NEW,
    STATE_SELECTED,
    STATE_UPLOADING,
    SelectionSessionsDep,
    UploadSession,
    UploadSessionsDep,
)
from opencde.store.documents.versions import DocumentsDep, VersionRecord, default_metadata, publication_metadata
from opencde.store.oauth2.tokens import Principal

router = APIRouter(prefix="/documents/1.0", tags=["Documents API"])

SessionId = Annotated[str, Path(alias="session_id", max_length=64)]
PartId = Annotated[str, Path(alias="part_id", max_length=64)]
DocumentId = Annotated[str, Path(alias="document_id", max_length=64)]
VersionIndex = Annotated[int, Path(alias="version_index", ge=1, le=1_000_000_000)]
FileIndex = Annotated[int, Path(alias="file_index", ge=0, le=1000)]

KEEPALIVE_AFTER_SECONDS = 15.0
KEEPALIVE_INTERVAL_SECONDS = 1.0


# ---------------------------------------------------------------------------- helpers


def _document_id(value: str) -> str:
    if not is_uuid(value):
        raise HTTPException(404, "Document not found")
    return normalize_guid(value)


async def _own_upload_session(sessions: UploadSessionsDep, session_id: str, principal: Principal) -> UploadSession:
    session = await sessions.by_id(session_id) if is_uuid(session_id) else None
    if session is None or session.user_id != principal.user_id:
        raise HTTPException(404, "Upload session not found or expired")
    return session


async def _may_upload(users: UsersDep, user_id: str, project_id: str | None) -> None:
    role = await users.project_role(user_id, project_id) if project_id else None
    if not may_upload(role):
        raise HTTPException(403, "You may not add documents to this project")


def _versions_payload(records: list[VersionRecord], base: str) -> list[DocumentVersion]:
    return [record.to_model(base) for record in records]


# ---------------------------------------------------------------------------- upload flow


@router.post(
    "/upload-documents",
    summary="Initiate the upload flow",
    response_model=DocumentUploadSessionInitialization,
    response_model_exclude_none=True,
)
async def upload_documents(
    request: Request,
    principal: DocumentsPrincipal,
    body: UploadDocuments,
    sessions: UploadSessionsDep,
    documents: DocumentsDep,
    settings: SettingsDep,
    users: UsersDep,
    clients: ClientsDep,
    graph: GraphDep,
) -> DocumentUploadSessionInitialization:
    """The client names the files and its callback; the user continues in the browser at ``upload_ui_url``.

    With `project_id` (an extension) a confidential client an administrator approved for headless uploads names
    the project and the titles itself: the page is skipped, the session is ready for the instructions, and the
    upload is in the audit log. 403 for any other client.
    """
    headless = body.project_id is not None
    if headless:
        await _may_upload_headless(clients, users, principal, body)
    ids = [item.session_file_id for item in body.files]
    if len(set(ids)) != len(ids):
        raise HTTPException(400, "session_file_id values must be unique")
    files: list[dict[str, Any]] = []
    for item in body.files:
        entry: dict[str, Any] = {
            "session_file_id": item.session_file_id,
            "file_name": item.file_name,
            "document_id": None,
            "existing_title": None,
            "title": item.file_name,
            "version_number": "1",
            "size_in_bytes": None,
            "state": "pending",
            "version_index": None,
            "base_version_index": item.base_version_index,
        }
        if headless:
            entry.update(
                title=item.title or item.file_name,
                version_number=item.version_number or "1",
                project_id=body.project_id,
            )
        if item.base_version_index is not None and not item.document_id:
            raise HTTPException(400, f"base_version_index of '{item.session_file_id}' needs a document_id")
        if item.document_id:
            latest = await documents.latest(user_id=principal.user_id, document_id=_document_id(item.document_id))
            if latest is None:
                raise HTTPException(400, f"document_id of '{item.session_file_id}' is not a document you can see")
            entry.update(
                document_id=latest.document_id,
                existing_title=latest.title,
                title=latest.title,
                version_number=str(latest.version_index + 1),
                project_id=latest.project_id,
            )
            if headless and latest.project_id != body.project_id:
                raise HTTPException(400, f"document_id of '{item.session_file_id}' belongs to another project")
        files.append(entry)
    session_id, token = await sessions.create(
        user_id=principal.user_id,
        username=principal.username,
        callback_url=body.callback.url,
        callback_expires_in=body.callback.expires_in,
        server_context=body.server_context,
        files=files,
    )
    if headless:
        await sessions.update(session_id, state=STATE_METADATA, project_id=body.project_id, files=files)
        await audit.record(
            graph,
            "documents.headless_upload",
            actor=principal.user_id,
            client_id=principal.client_id,
            ip=client_ip(request),
            details={"project_id": body.project_id, "files": [item.file_name for item in body.files]},
        )
    return DocumentUploadSessionInitialization(
        upload_ui_url=f"{api_base(settings)}/upload-ui/{token}",
        expires_in=settings.documents_session_ttl_seconds,
        max_size_in_bytes=settings.max_upload_bytes,
    )


@router.post(
    "/upload-sessions/{session_id}/instructions",
    summary="Upload instructions (the server-provided upload_documents_url)",
    response_model=DocumentsToUpload,
    response_model_exclude_none=True,
)
async def upload_instructions(
    principal: DocumentsPrincipal,
    session_id: SessionId,
    body: UploadFileDetails,
    sessions: UploadSessionsDep,
    storage: StorageDep,
    settings: SettingsDep,
) -> DocumentsToUpload:
    """Given the file sizes, how to upload each file in parts, and where to complete or cancel it."""
    session = await _own_upload_session(sessions, session_id, principal)
    if session.state == STATE_NEW:
        raise HTTPException(400, "The document metadata has not been saved in the browser yet")
    if session.state == STATE_CANCELLED:
        raise HTTPException(400, "The upload was cancelled")
    base = api_base(settings)
    files = list(session.files)
    by_id = {item["session_file_id"]: index for index, item in enumerate(files)}
    result: list[DocumentToUpload] = []
    for detail in body.files:
        index = by_id.get(detail.session_file_id)
        if index is None:
            raise HTTPException(400, f"'{detail.session_file_id}' is not a file of this upload")
        if detail.size_in_bytes > settings.max_upload_bytes:
            raise ApiError(
                413,
                f"'{detail.session_file_id}' exceeds the maximum of {settings.max_upload_bytes} bytes",
                code=CODE_UPLOAD_TOO_LARGE,
            )
        if detail.size_in_bytes == 0:
            raise HTTPException(400, f"'{detail.session_file_id}' is empty")
        if files[index]["state"] == FILE_DONE:
            raise HTTPException(400, f"'{detail.session_file_id}' has already been uploaded")
        ranges = part_ranges(detail.size_in_bytes, settings.upload_part_bytes)
        for key in await sessions.delete_parts(session.id, index):  # instructions asked for again: start over
            storage.delete(key)
        part_ids = await sessions.create_parts(session.id, index, ranges)
        files[index].update(size_in_bytes=detail.size_in_bytes, state=FILE_PARTS)
        result.append(
            DocumentToUpload(
                session_file_id=detail.session_file_id,
                upload_file_parts=[
                    UploadFilePartInstruction(
                        url=f"{base}/upload-part/{part_id}",
                        http_method="PUT",
                        include_authorization=True,
                        content_range_start=start,
                        content_range_end=end,
                    )
                    for part_id, (start, end) in zip(part_ids, ranges, strict=True)
                ],
                upload_completion=LinkData(url=f"{base}/upload-sessions/{session.id}/files/{index}/complete"),
                upload_cancellation=LinkData(url=f"{base}/upload-sessions/{session.id}/files/{index}/cancel"),
            )
        )
    await sessions.update(session.id, state=STATE_UPLOADING, files=files, extend=True)
    return DocumentsToUpload(server_context=session.server_context, documents_to_upload=result)


@limiter.limit(RATE_UPLOAD)
async def upload_part(
    request: Request,
    principal: DocumentsPrincipal,
    part_id: PartId,
    sessions: UploadSessionsDep,
    storage: StorageDep,
) -> Response:
    """The body is the bytes of exactly the announced range; parts may arrive in any order."""
    part = await sessions.part(part_id) if is_uuid(part_id) else None
    if part is None or part["user_id"] != principal.user_id:
        raise HTTPException(404, "Upload part not found or expired")
    expected = int(part["range_end"]) - int(part["range_start"]) + 1
    key = make_key("parts", part_id)
    size = await receive_upload(request, storage, key, expected)
    if size != expected:
        storage.delete(key)
        raise HTTPException(400, f"The part has {size} bytes; {expected} were announced")
    await sessions.mark_received(part_id, key, size)
    return Response(status_code=200)


# The specification lets the server choose PUT or POST per part; both are served by the same handler.
for _method in ("PUT", "POST"):
    router.add_api_route(
        "/upload-part/{part_id}",
        upload_part,
        methods=[_method],
        summary=f"Upload a single file part ({_method})",
        status_code=200,
        response_class=Response,
        operation_id=f"upload_part_{_method.lower()}",
    )


async def _complete(
    session: UploadSession,
    file_index: int,
    *,
    sessions: UploadSessionsDep,
    documents: DocumentsDep,
    projects: ProjectsDep,
    storage: StorageDep,
    base: str,
    ifcgraph: IfcGraphService | None = None,
) -> DocumentVersion:
    files = list(session.files)
    item = files[file_index]
    parts = await sessions.parts(session.id, file_index)
    missing = [str(part["part_index"]) for part in parts if not part.get("received")]
    if not parts or missing:
        raise HTTPException(
            400, "Not every part has been uploaded" + (f" (missing: {', '.join(missing)})" if missing else "")
        )
    project_id = session.project_id or item.get("project_id")
    if not project_id:
        raise HTTPException(400, "No project was chosen for this upload")
    base_version = item.get("base_version_index")
    if base_version is not None:
        # The upload builds on a version: it is refused when someone else has added one since (412).
        latest = await documents.latest(user_id=session.user_id, document_id=str(item["document_id"]))
        if latest is None or latest.version_index != int(base_version):
            raise ApiError(
                412,
                f"The upload builds on version {base_version}, but the document's latest version is "
                f"{latest.version_index if latest else 'unknown'}",
                code=CODE_VERSION_CONFLICT,
            )
    version_id = new_id()
    target = make_key("documents", version_id)
    try:
        sha256 = await anyio.to_thread.run_sync(
            assemble, storage, [part["storage_key"] for part in parts], target, int(item["size_in_bytes"])
        )
    except AssemblyError as exc:
        raise HTTPException(400, str(exc)) from None
    try:
        project = await _project(projects, project_id)
        checked = await _check_first(ifcgraph, project, project_id, target, item["file_name"])
    except BaseException:
        storage.delete(target)
        raise
    if ifcgraph is not None and checked is not None and checked.get("error_count"):
        # The project refuses a file with errors (ADR 0021). The parts are gone; the file stays a day as a
        # precheck, so that the report can be read at the address the error gives.
        await sessions.delete_parts(session.id, file_index)
        item.update(state=FILE_CANCELLED)
        await sessions.update(session.id, files=files)
        precheck_id = await ifcgraph.keep_as_precheck(
            project_id=project_id,
            storage_key=target,
            file_name=item["file_name"],
            author=session.username,
            checked=checked,
        )
        raise ApiError(
            422,
            f"The file has {checked['error_count']} errors against the IFC schema or the project's rules, and the "
            "project does not accept such a file",
            code=CODE_IFC_VALIDATION_FAILED,
            details={"report": precheck_url(base, project_id, precheck_id)},
        )
    try:
        record = await documents.create_version(
            project_id=project_id,
            document_id=item.get("document_id"),
            title=item["title"],
            version_number=item["version_number"],
            file_name=item["file_name"],
            size_in_bytes=int(item["size_in_bytes"]),
            sha256=sha256,
            storage_key=target,
            author=session.username,
            metadata=default_metadata(
                file_name=item["file_name"],
                size_in_bytes=int(item["size_in_bytes"]),
                sha256=sha256,
                author=session.username,
                project_name=project["name"],
            )
            + (
                [DocumentMetadataEntry(name="base_version_index", value=[str(base_version)], data_type="integer32")]
                if base_version is not None
                else []
            ),
            parent_version_index=None if base_version is None else int(base_version),
        )
    except BaseException:
        storage.delete(target)
        raise
    await sessions.delete_parts(session.id, file_index)
    item.update(state=FILE_DONE, document_id=record.document_id, version_index=record.version_index)
    await sessions.update(session.id, files=files)
    if ifcgraph is not None:
        await ifcgraph.schedule(
            project_id=project_id,
            storage_key=target,
            file_name=record.file_name,
            document_id=record.document_id,
            version_index=record.version_index,
            version_id=record.version_id,
            checked=checked,
        )
    return record.to_model(base)


async def _may_upload_headless(clients: Any, users: Any, principal: Principal, body: UploadDocuments) -> None:
    """Only a confidential client an administrator approved, for a member who may add documents (OB-39)."""
    client = await clients.get(principal.client_id)
    if client is None or client.is_public or not client.headless_uploads:
        raise HTTPException(403, "This client may not upload without the browser page")
    if not is_uuid(body.project_id or ""):
        raise HTTPException(400, "project_id must be a UUID")
    body.project_id = normalize_guid(body.project_id or "")
    await _may_upload(users, principal.user_id, body.project_id)


async def _project(projects: ProjectsDep, project_id: str) -> dict[str, Any]:
    project = await projects.get(project_id)
    if project is None:
        raise HTTPException(404, "Project not found")
    return {"name": project.name, "block": project.block_on_validation_errors}


async def _check_first(
    ifcgraph: IfcGraphService | None, project: dict[str, Any], project_id: str, storage_key: str, file_name: str
) -> dict[str, Any] | None:
    """The checks before the version exists, for a project that refuses uploads with errors (ADR 0021)."""
    if ifcgraph is None or not project["block"]:
        return None
    return await ifcgraph.check_now(project_id=project_id, storage_key=storage_key, file_name=file_name)


@router.post(
    "/upload-sessions/{session_id}/files/{file_index}/complete",
    summary="Complete a file upload after all the parts have been uploaded",
    response_model=DocumentVersion,
    response_model_exclude_none=True,
)
async def upload_completion(
    principal: DocumentsPrincipal,
    session_id: SessionId,
    file_index: FileIndex,
    sessions: UploadSessionsDep,
    documents: DocumentsDep,
    projects: ProjectsDep,
    users: UsersDep,
    storage: StorageDep,
    settings: SettingsDep,
    ifcgraph: IfcGraphDep,
) -> Response:
    """Assemble the parts, verify the size, store the file and create the version.

    Large files take a while; after a few seconds the response starts with whitespace to keep the connection
    alive and ends with the JSON (a JSON parser skips leading whitespace).
    """
    session = await _own_upload_session(sessions, session_id, principal)
    if file_index >= len(session.files):
        raise HTTPException(404, "No such file in this upload")
    item = session.files[file_index]
    base = api_base(settings)
    if item["state"] == FILE_DONE and item.get("document_id") and item.get("version_index"):
        existing = await documents.version(
            user_id=principal.user_id, document_id=item["document_id"], version_index=int(item["version_index"])
        )
        if existing is not None:
            return JSONResponse(existing.to_model(base).model_dump(exclude_none=True))
    if item["state"] != FILE_PARTS:
        raise HTTPException(400, "This file is not being uploaded")
    await _may_upload(users, principal.user_id, session.project_id or item.get("project_id"))

    task = asyncio.ensure_future(
        _complete(
            session,
            file_index,
            sessions=sessions,
            documents=documents,
            projects=projects,
            storage=storage,
            base=base,
            ifcgraph=ifcgraph,
        )
    )
    done, _ = await asyncio.wait({task}, timeout=KEEPALIVE_AFTER_SECONDS)
    if done:
        return JSONResponse(task.result().model_dump(exclude_none=True))

    async def keep_alive() -> AsyncIterator[bytes]:
        while True:
            finished, _ = await asyncio.wait({task}, timeout=KEEPALIVE_INTERVAL_SECONDS)
            if finished:
                break
            yield b" "
        try:
            yield json.dumps(task.result().model_dump(exclude_none=True)).encode("utf-8")
        except HTTPException as exc:
            body = error_body(
                exc.status_code, str(exc.detail), getattr(exc, "code", None), getattr(exc, "details", None)
            )
            yield json.dumps(body).encode("utf-8")

    return StreamingResponse(keep_alive(), media_type="application/json")


@router.post(
    "/upload-sessions/{session_id}/files/{file_index}/cancel",
    summary="Cancel the upload of a single file",
    status_code=204,
)
async def upload_cancellation(
    principal: DocumentsPrincipal,
    session_id: SessionId,
    file_index: FileIndex,
    sessions: UploadSessionsDep,
    storage: StorageDep,
) -> Response:
    session = await _own_upload_session(sessions, session_id, principal)
    if file_index >= len(session.files):
        raise HTTPException(404, "No such file in this upload")
    for key in await sessions.delete_parts(session.id, file_index):
        storage.delete(key)
    files = list(session.files)
    if files[file_index]["state"] != FILE_DONE:
        files[file_index]["state"] = FILE_CANCELLED
    await sessions.update(session.id, files=files)
    return Response(status_code=204)


# ---------------------------------------------------------------------------- download flow


@router.post(
    "/select-documents",
    summary="Initiate document selection and download flow",
    response_model=DocumentDiscoverySessionInitialization,
    response_model_exclude_none=True,
)
async def select_documents(
    principal: DocumentsPrincipal, body: SelectDocuments, sessions: SelectionSessionsDep, settings: SettingsDep
) -> DocumentDiscoverySessionInitialization:
    _, token = await sessions.create(
        user_id=principal.user_id,
        callback_url=body.callback.url,
        callback_expires_in=body.callback.expires_in,
        server_context=body.server_context,
        extensions=body.supported_file_extensions or [],
    )
    return DocumentDiscoverySessionInitialization(
        select_documents_url=f"{api_base(settings)}/select-ui/{token}",
        expires_in=settings.documents_session_ttl_seconds,
    )


@router.get(
    "/selection-sessions/{session_id}/documents",
    summary="Retrieve the user's selection (the server-provided selected_documents_url)",
    response_model=SelectedDocuments,
    response_model_exclude_none=True,
)
async def selected_documents(
    principal: DocumentsPrincipal,
    session_id: SessionId,
    sessions: SelectionSessionsDep,
    documents: DocumentsDep,
    settings: SettingsDep,
) -> SelectedDocuments:
    session = await sessions.by_id(session_id) if is_uuid(session_id) else None
    if session is None or session.user_id != principal.user_id:
        raise HTTPException(404, "Selection session not found or expired")
    if session.state != STATE_SELECTED:
        raise HTTPException(400, "The selection has not been completed in the browser")
    base = api_base(settings)
    records: list[VersionRecord] = []
    for entry in session.selected:
        document_id, _, index = entry.partition(":")
        record = await documents.version(user_id=principal.user_id, document_id=document_id, version_index=int(index))
        if record is not None:
            records.append(record)
    return SelectedDocuments(server_context=session.server_context, documents=_versions_payload(records, base))


@router.get(
    "/documents/{document_id}/versions",
    summary="Get the versions of a single document",
    response_model=DocumentVersions,
    response_model_exclude_none=True,
)
async def document_versions(
    principal: DocumentsPrincipal, document_id: DocumentId, documents: DocumentsDep, settings: SettingsDep
) -> DocumentVersions:
    records = await documents.versions(user_id=principal.user_id, document_id=_document_id(document_id))
    if not records:
        raise HTTPException(404, "Document not found")
    return DocumentVersions(documents=_versions_payload(records, api_base(settings)))


async def _version(
    principal: Principal, documents: DocumentsDep, document_id: str, version_index: int
) -> VersionRecord:
    record = await documents.version(
        user_id=principal.user_id, document_id=_document_id(document_id), version_index=version_index
    )
    if record is None:
        raise HTTPException(404, "Document version not found")
    return record


@router.get(
    "/documents/{document_id}/versions/{version_index}",
    summary="Get the information for a single document version",
    response_model=DocumentVersion,
    response_model_exclude_none=True,
)
async def document_version(
    principal: DocumentsPrincipal,
    document_id: DocumentId,
    version_index: VersionIndex,
    documents: DocumentsDep,
    settings: SettingsDep,
) -> DocumentVersion:
    record = await _version(principal, documents, document_id, version_index)
    return record.to_model(api_base(settings))


@router.get(
    "/documents/{document_id}/versions/{version_index}/metadata",
    summary="Get document metadata for a single document version",
    response_model=DocumentMetadata,
    response_model_exclude_none=True,
)
async def document_metadata(
    principal: DocumentsPrincipal,
    document_id: DocumentId,
    version_index: VersionIndex,
    documents: DocumentsDep,
    settings: SettingsDep,
) -> DocumentMetadata:
    """The metadata given at upload, for an IFC file the result of checking it (``ifc_validation_*``), and for a
    published version when and by whom (``published_*``, ``publication``)."""
    record = await _version(principal, documents, document_id, version_index)
    entries = record.metadata_entries()
    validation = await documents.validation(
        user_id=principal.user_id, document_id=record.document_id, version_index=record.version_index
    )
    if validation is not None:
        url = validation_report_url(api_base(settings), record.document_id, record.version_index)
        entries += validation_metadata(validation, url)
    published = await documents.publication(
        user_id=principal.user_id, document_id=record.document_id, version_index=record.version_index
    )
    if published is not None:
        url = publication_url(api_base(settings), record.document_id, record.version_index)
        entries += publication_metadata(published, url)
    return DocumentMetadata(metadata=entries)


@router.get(
    "/documents/{document_id}/versions/{version_index}/download",
    summary="Download the document",
    response_class=StreamingResponse,
)
async def document_download(
    principal: DocumentsPrincipal,
    document_id: DocumentId,
    version_index: VersionIndex,
    documents: DocumentsDep,
    storage: StorageDep,
) -> StreamingResponse:
    record = await _version(principal, documents, document_id, version_index)
    return file_response(storage, record.storage_key, media_type="application/octet-stream", filename=record.file_name)


# ---------------------------------------------------------------------------- query


@router.post(
    "/document-versions",
    summary="Query for the latest versions of multiple documents",
    response_model=DocumentQueryResult,
    response_model_exclude_none=True,
)
async def query_document_versions(
    request: Request,
    principal: DocumentsPrincipal,
    body: DocumentQuery,
    documents: DocumentsDep,
    settings: SettingsDep,
) -> Response:
    """Latest version of each listed document the caller may see. ``ETag`` and ``If-None-Match`` give 304."""
    ids = sorted({normalize_guid(value) for value in body.document_ids if is_uuid(value)})
    records = await documents.latest_many(user_id=principal.user_id, document_ids=ids)
    payload = DocumentQueryResult(versions=_versions_payload(records, api_base(settings))).model_dump(exclude_none=True)
    body_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    etag = etag_for(body_bytes)
    if matches(request.headers.get("if-none-match"), etag):
        return Response(status_code=304, headers={"ETag": etag})
    return Response(body_bytes, media_type="application/json", headers={"ETag": etag})
