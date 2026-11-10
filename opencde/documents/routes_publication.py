# This file was generated with the assistance of an AI coding tool.
"""Publishing a version: an extension of the Documents API (F9 a, OB-23.3).

A ``manager`` of the project publishes a version, as ISO 19650 gives a document the status published: the server
keeps the version's file as one whole archive beside it, an IFC file as ``.ifczip`` (the IFC file zipped, as
buildingSMART defines it) and any other file as ``.zip``. A version is published once. One whose check against the IFC
schema is still running, or found errors, is not published; the errors are mended in a new version.

``POST …/versions/{index}/publication`` publishes, ``GET …/publication`` says who published it and when, and
``GET …/publication/download`` hands out the archive. The version's metadata names the publication too.
"""

from __future__ import annotations

import hashlib
import os
import zipfile
from pathlib import PureWindowsPath
from typing import Annotated, Any

import anyio
from fastapi import APIRouter, HTTPException, Path, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from opencde.accounts.roles import Role, at_least
from opencde.auth.dependencies import DocumentsPrincipal
from opencde.bcf.binary import file_response
from opencde.deps import SettingsDep, StorageDep, UsersDep, client_ip
from opencde.documents.links import api_base, publication_url
from opencde.documents.repository import DocumentsDep, VersionRecord
from opencde.ids import is_uuid, new_id, normalize_guid
from opencde.storage import LocalStorage, make_key
from opencde.timeutil import now_iso

TAG = "Publication (extension)"

router = APIRouter(prefix="/documents/1.0", tags=[TAG])

DocumentId = Annotated[str, Path(alias="document_id", max_length=64)]
VersionIndex = Annotated[int, Path(alias="version_index", ge=1, le=1_000_000_000)]

PUBLISHABLE = ("passed", "warnings")  # the statuses of a check that let a version be published


class Publication(BaseModel):
    published_at: str = Field(description="When the version was published, ISO 8601 in UTC.")
    published_by: str = Field(description="The user name of the manager who published it.")
    file_name: str = Field(description="The archive's name: the file's own with `.ifczip`, or `.zip` for another file.")
    size_in_bytes: int = Field(description="The archive's size.")
    sha256: str = Field(description="The archive's SHA-256, in hexadecimal.")
    download_url: str = Field(description="Where the archive is downloaded (`GET …/publication/download`).")


def archive_names(file_name: str) -> tuple[str, str]:
    """The name of the file inside the archive, its last part only, and the archive's own name."""
    inner = PureWindowsPath(file_name).name or "document"  # a name with a folder or a drive never reaches the archive
    if inner.lower().endswith(".ifc"):
        return inner, inner[: -len(".ifc")] + ".ifczip"
    return inner, inner + ".zip"


def write_archive(storage: LocalStorage, source_key: str, key: str, inner: str) -> tuple[int, str]:
    """The version's file zipped into storage under ``key``, with the archive's size and SHA-256."""
    target = storage.path(key)
    tmp = target.with_suffix(target.suffix + ".tmp")
    try:
        with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(storage.path(source_key), arcname=inner)
        digest = hashlib.sha256()
        with tmp.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
        os.replace(tmp, target)
    finally:
        tmp.unlink(missing_ok=True)
    return target.stat().st_size, digest.hexdigest()


def _answer(publication: dict[str, Any], url: str) -> Publication:
    return Publication(
        published_at=str(publication["published_at"]),
        published_by=str(publication["published_by"]),
        file_name=str(publication["file_name"]),
        size_in_bytes=int(publication["size_in_bytes"]),
        sha256=str(publication["sha256"]),
        download_url=f"{url}/download",
    )


async def _version(documents: DocumentsDep, user_id: str, document_id: str, version_index: int) -> VersionRecord:
    record = (
        await documents.version(user_id=user_id, document_id=normalize_guid(document_id), version_index=version_index)
        if is_uuid(document_id)
        else None
    )
    if record is None:
        raise HTTPException(404, "Document version not found")
    return record


@router.post(
    "/documents/{document_id}/versions/{version_index}/publication",
    summary="Publish a document version",
    response_model=Publication,
    status_code=201,
)
async def publish_version(
    request: Request,
    principal: DocumentsPrincipal,
    document_id: DocumentId,
    version_index: VersionIndex,
    documents: DocumentsDep,
    users: UsersDep,
    storage: StorageDep,
    settings: SettingsDep,
) -> Publication:
    """A `manager` publishes the version: the server keeps its file as one archive, `.ifczip` for an IFC file and
    `.zip` for another, and the version's metadata names it. 403 for other roles; 409 when the version is published
    already, or when its check against the IFC schema is still running or found errors."""
    record = await _version(documents, principal.user_id, document_id, version_index)
    if not at_least(await users.project_role(principal.user_id, record.project_id), Role.MANAGER):
        raise HTTPException(403, "Only a manager publishes a version")
    if await documents.publication(
        user_id=principal.user_id, document_id=record.document_id, version_index=record.version_index
    ):
        raise HTTPException(409, "This version is published already")
    validation = await documents.validation(
        user_id=principal.user_id, document_id=record.document_id, version_index=record.version_index
    )
    if validation is not None and validation.status not in PUBLISHABLE:
        if validation.status == "pending":
            raise HTTPException(409, "The version is still being checked; publish it when the check is done")
        raise HTTPException(409, f"The version's check is {validation.status}; mend it in a new version first")
    publication_id = new_id()
    inner, file_name = archive_names(record.file_name)
    key = make_key("published", publication_id, "ifczip" if file_name.endswith(".ifczip") else "zip")
    size, sha256 = await anyio.to_thread.run_sync(write_archive, storage, record.storage_key, key, inner)
    published = {
        "id": publication_id,
        "storage_key": key,
        "file_name": file_name,
        "size_in_bytes": size,
        "sha256": sha256,
        "published_at": now_iso(),
        "published_by": principal.username,
    }
    event = {
        "type": "documents.publish",
        "actor": principal.user_id,
        "client_id": principal.client_id,
        "ip": client_ip(request),
        "details": {"document_id": record.document_id, "version_index": record.version_index},
    }
    if not await documents.publish(
        user_id=principal.user_id,
        document_id=record.document_id,
        version_index=record.version_index,
        publication=published,
        audit_event=event,
    ):
        storage.delete(key)  # another request published it meanwhile
        raise HTTPException(409, "This version is published already")
    return _answer(published, publication_url(api_base(settings), record.document_id, record.version_index))


@router.get(
    "/documents/{document_id}/versions/{version_index}/publication",
    summary="Who published a document version, and when",
    response_model=Publication,
)
async def version_publication(
    principal: DocumentsPrincipal,
    document_id: DocumentId,
    version_index: VersionIndex,
    documents: DocumentsDep,
    settings: SettingsDep,
) -> Publication:
    """The publication of the version, for every member of the project. 404 when it is not published."""
    record = await _version(documents, principal.user_id, document_id, version_index)
    found = await documents.publication(
        user_id=principal.user_id, document_id=record.document_id, version_index=record.version_index
    )
    if found is None:
        raise HTTPException(404, "This version is not published")
    return _answer(found, publication_url(api_base(settings), record.document_id, record.version_index))


@router.get(
    "/documents/{document_id}/versions/{version_index}/publication/download",
    summary="Download the archive of a published document version",
    response_class=StreamingResponse,
)
async def publication_download(
    principal: DocumentsPrincipal,
    document_id: DocumentId,
    version_index: VersionIndex,
    documents: DocumentsDep,
    storage: StorageDep,
) -> StreamingResponse:
    """The `.ifczip` or `.zip` of a published version. 404 when it is not published."""
    record = await _version(documents, principal.user_id, document_id, version_index)
    found = await documents.publication(
        user_id=principal.user_id, document_id=record.document_id, version_index=record.version_index
    )
    if found is None:
        raise HTTPException(404, "This version is not published")
    return file_response(storage, str(found["storage_key"]), media_type="application/zip", filename=found["file_name"])
