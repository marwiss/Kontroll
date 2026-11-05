# This file was generated with the assistance of an AI coding tool.
"""Request and response bodies of the Documents API, one class per schema in ``swagger.yaml``.

Response schemas there carry ``additionalProperties: false``, so the models
contain exactly the specified fields and nothing internal (no storage keys,
no hashes). Inputs ignore unknown fields (Foundation API 1.8).
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_URL = 2000
MAX_NAME = 255
MAX_ID = 128
MAX_FILES = 100
MAX_QUERY_IDS = 1000
_HTTP_URL = re.compile(r"^https?://[^\s]+$", re.IGNORECASE)
_EXTENSION = re.compile(r"^\.[A-Za-z0-9]{1,16}$")


class DocumentsModel(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


# ---------------------------------------------------------------------------- shared


class LinkData(DocumentsModel):
    url: str = Field(min_length=1)


class CallbackLink(DocumentsModel):
    """The client's URL the browser is sent back to; http(s) only, with its own expiry."""

    url: str = Field(min_length=1, max_length=MAX_URL)
    expires_in: int = Field(ge=1, le=7 * 24 * 3600)

    @field_validator("url")
    @classmethod
    def _http(cls, value: str) -> str:
        if not _HTTP_URL.match(value):
            raise ValueError("callback url must be an http(s) URL")
        return value


class FileDescription(DocumentsModel):
    name: str = Field(min_length=1)
    size_in_bytes: int


class DocumentVersionLinks(DocumentsModel):
    document_version: LinkData
    document_version_metadata: LinkData
    document_version_download: LinkData
    document_versions: LinkData
    document_details: LinkData


class DocumentVersion(DocumentsModel):
    links: DocumentVersionLinks
    version_number: str = Field(min_length=1)
    version_index: int
    creation_date: str = Field(min_length=1)
    title: str = Field(min_length=1)
    file_description: FileDescription
    document_id: str = Field(min_length=1)


class DocumentVersions(DocumentsModel):
    documents: list[DocumentVersion]


DataType = Literal["string", "boolean", "date-time", "date", "integer32", "integer64", "number", "url"]


class DocumentMetadataEntry(DocumentsModel):
    name: str = Field(min_length=1)
    value: list[str]
    data_type: DataType


class DocumentMetadata(DocumentsModel):
    metadata: list[DocumentMetadataEntry]


# ---------------------------------------------------------------------------- download flow


class SelectDocuments(DocumentsModel):
    callback: CallbackLink
    server_context: str | None = Field(None, max_length=MAX_ID)
    supported_file_extensions: list[str] | None = Field(None, max_length=50)

    @field_validator("supported_file_extensions")
    @classmethod
    def _extensions(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        cleaned = []
        for item in value:
            item = item.strip().lower()
            if not _EXTENSION.match(item):
                raise ValueError("file extensions must look like '.ifc'")
            if item not in cleaned:
                cleaned.append(item)
        return cleaned


class DocumentDiscoverySessionInitialization(DocumentsModel):
    select_documents_url: str = Field(min_length=1)
    expires_in: int


class SelectedDocuments(DocumentsModel):
    server_context: str | None = None
    documents: list[DocumentVersion]


# ---------------------------------------------------------------------------- upload flow


class FileToUpload(DocumentsModel):
    file_name: str = Field(min_length=1, max_length=MAX_NAME)
    session_file_id: str = Field(min_length=1, max_length=MAX_ID)
    document_id: str | None = Field(None, min_length=1, max_length=MAX_ID)


class UploadDocuments(DocumentsModel):
    callback: CallbackLink
    server_context: str | None = Field(None, max_length=MAX_ID)
    files: list[FileToUpload] = Field(min_length=1, max_length=MAX_FILES)


class DocumentUploadSessionInitialization(DocumentsModel):
    upload_ui_url: str = Field(min_length=1)
    expires_in: int
    max_size_in_bytes: int


class UploadFileDetail(DocumentsModel):
    size_in_bytes: int = Field(ge=0)
    session_file_id: str = Field(min_length=1, max_length=MAX_ID)


class UploadFileDetails(DocumentsModel):
    files: list[UploadFileDetail] = Field(min_length=1, max_length=MAX_FILES)


class HeaderValue(DocumentsModel):
    name: str = Field(min_length=1)
    value: str = Field(min_length=1)


class Headers(DocumentsModel):
    values: list[HeaderValue]


class MultipartFormData(DocumentsModel):
    prefix: str
    suffix: str


class UploadFilePartInstruction(DocumentsModel):
    url: str = Field(min_length=1)
    http_method: Literal["POST", "PUT"]
    additional_headers: Headers | None = None
    include_authorization: bool = False
    multipart_form_data: MultipartFormData | None = None
    content_range_start: int
    content_range_end: int


class DocumentToUpload(DocumentsModel):
    session_file_id: str = Field(min_length=1)
    upload_file_parts: list[UploadFilePartInstruction]
    upload_completion: LinkData
    upload_cancellation: LinkData


class DocumentsToUpload(DocumentsModel):
    server_context: str | None = None
    documents_to_upload: list[DocumentToUpload]


# ---------------------------------------------------------------------------- query


class DocumentQuery(DocumentsModel):
    document_ids: list[str] = Field(max_length=MAX_QUERY_IDS)


class DocumentQueryResult(DocumentsModel):
    versions: list[DocumentVersion]
