# This file was generated with the assistance of an AI coding tool.
"""Documents API 1.0 (https://github.com/buildingSMART/documents-API).

The API is link-driven: the client starts a flow, the user finishes a step in
the browser, and the server hands the client URLs for the next steps. This
class follows the links it is given and never guesses server paths.
"""

from __future__ import annotations

import io
from typing import Any, BinaryIO

from opencde_client.http import ApiSession

JSON = dict[str, Any]


class DocumentsClient:
    def __init__(self, session: ApiSession, version: str = "1.0") -> None:
        self.session = session
        self.base = f"/documents/{version}"

    # -- upload flow -----------------------------------------------------------------------------

    def start_upload(
        self,
        files: list[JSON],
        *,
        callback_url: str,
        callback_expires_in: int = 600,
        server_context: str | None = None,
    ) -> JSON:
        """``POST /upload-documents``. ``files`` are ``{"file_name", "session_file_id"[, "document_id"]}``.

        Open ``upload_ui_url`` of the result in the user's browser; the browser is sent to
        ``callback_url`` with ``upload_documents_url`` (or ``user_cancelled_upload=true``).
        """
        body: JSON = {"callback": {"url": callback_url, "expires_in": callback_expires_in}, "files": files}
        if server_context:
            body["server_context"] = server_context
        return self.session.json("POST", f"{self.base}/upload-documents", json=body)

    def upload_instructions(self, upload_documents_url: str, sizes: dict[str, int]) -> JSON:
        """``POST`` to the ``upload_documents_url`` from the callback with the file sizes."""
        files = [{"session_file_id": file_id, "size_in_bytes": size} for file_id, size in sizes.items()]
        return self.session.json("POST", upload_documents_url, json={"files": files})

    def upload_file(self, instructions: JSON, data: bytes | BinaryIO) -> JSON:
        """Upload every part of one ``DocumentToUpload`` and complete it; returns the ``DocumentVersion``."""
        stream = io.BytesIO(data) if isinstance(data, bytes) else data
        for part in instructions["upload_file_parts"]:
            start, end = int(part["content_range_start"]), int(part["content_range_end"])
            stream.seek(start)
            chunk = stream.read(end - start + 1)
            form = part.get("multipart_form_data")
            if form:
                chunk = form["prefix"].encode("latin-1") + chunk + form["suffix"].encode("latin-1")
            headers = {"Content-Type": "application/octet-stream"}
            for header in (part.get("additional_headers") or {}).get("values", []):
                headers[header["name"]] = header["value"]
            self.session.request(
                part["http_method"],
                part["url"],
                content=chunk,
                headers=headers,
                include_authorization=bool(part.get("include_authorization", False)),
            )
        return self.session.json("POST", instructions["upload_completion"]["url"])

    def cancel_upload(self, instructions: JSON) -> None:
        self.session.post(instructions["upload_cancellation"]["url"])

    # -- download flow ---------------------------------------------------------------------------

    def start_selection(
        self,
        *,
        callback_url: str,
        callback_expires_in: int = 600,
        server_context: str | None = None,
        supported_file_extensions: list[str] | None = None,
    ) -> JSON:
        """``POST /select-documents``; open ``select_documents_url`` in the browser."""
        body: JSON = {"callback": {"url": callback_url, "expires_in": callback_expires_in}}
        if server_context:
            body["server_context"] = server_context
        if supported_file_extensions:
            body["supported_file_extensions"] = supported_file_extensions
        return self.session.json("POST", f"{self.base}/select-documents", json=body)

    def selected_documents(self, selected_documents_url: str) -> JSON:
        return self.session.json("GET", selected_documents_url)

    # -- links of a DocumentVersion ----------------------------------------------------------------

    def version(self, version: JSON) -> JSON:
        return self.session.json("GET", version["links"]["document_version"]["url"])

    def versions(self, version: JSON) -> JSON:
        return self.session.json("GET", version["links"]["document_versions"]["url"])

    def metadata(self, version: JSON) -> JSON:
        return self.session.json("GET", version["links"]["document_version_metadata"]["url"])

    def download(self, version: JSON) -> bytes:
        return self.session.get(version["links"]["document_version_download"]["url"]).content

    # -- query -------------------------------------------------------------------------------------

    def query_versions(self, document_ids: list[str], *, etag: str | None = None) -> tuple[JSON | None, str | None]:
        """Latest versions of the documents. With ``etag`` from an earlier call, ``(None, etag)`` means unchanged."""
        headers = {"If-None-Match": etag} if etag else {}
        response = self.session.post(
            f"{self.base}/document-versions", json={"document_ids": document_ids}, headers=headers, expected=(200, 304)
        )
        new_etag = response.headers.get("etag")
        if response.status_code == 304:
            return None, new_etag or etag
        return response.json(), new_etag
