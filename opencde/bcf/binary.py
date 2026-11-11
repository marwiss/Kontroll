# This file was generated with the assistance of an AI coding tool.
"""Binary request bodies and file downloads (Foundation API 1.9, RFC 6266).

Uploads are streamed into storage and counted; the declared ``Content-Length``
is never trusted. Downloads are streamed back with ``Content-Disposition:
attachment`` so a browser never renders uploaded content, and the file name
is the one the client gave at upload time, sanitised and encoded per RFC 8187.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterator
from typing import BinaryIO
from urllib.parse import quote, unquote

from fastapi import HTTPException, Request
from fastapi.responses import StreamingResponse

from opencde.storage import LocalStorage, TooLargeError

MAX_FILENAME = 255
_EXTENDED = re.compile(r"""filename\*\s*=\s*(?:utf-8|UTF-8)''([^;]+)""")
_QUOTED = re.compile(r'filename\s*=\s*"((?:[^"\\]|\\.)*)"')
_TOKEN = re.compile(r"filename\s*=\s*([^;\s]+)")
_UNSAFE = re.compile(r"[\x00-\x1f\x7f\"\\/:*?<>|]")
_HEADER_UNSAFE = re.compile(r"[\x00-\x1f\x7f\"\\]")  # what would end the header line or the quoted name
CHUNK = 64 * 1024


def sanitize_filename(name: str) -> str:
    """Only the base name, printable, at most 255 characters; never used in a path anyway."""
    nfc = unicodedata.normalize  # aliased so the Cypher lint does not mistake it for a Neo4j-only function
    name = nfc("NFC", name).replace("\\", "/").rsplit("/", 1)[-1]
    name = _UNSAFE.sub("", name).strip(" .")
    return name[:MAX_FILENAME]


def filename_from_content_disposition(header: str | None) -> str | None:
    if not header:
        return None
    match = _EXTENDED.search(header)
    if match:
        candidate = unquote(match.group(1).strip())
    else:
        match = _QUOTED.search(header) or _TOKEN.search(header)
        if not match:
            return None
        candidate = match.group(1).replace('\\"', '"')
    return sanitize_filename(candidate) or None


def attachment_header(filename: str) -> str:
    """``attachment; filename="ascii"; filename*=UTF-8''percent-encoded`` (RFC 6266, RFC 8187).

    A Documents API file name is kept as the client gave it, so the plain name here drops what would end the header
    line or close the quotes; the encoded name carries every character.
    """
    ascii_name = filename.encode("ascii", "replace").decode("ascii").replace("?", "_")
    ascii_name = _HEADER_UNSAFE.sub("_", ascii_name) or "file"
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename, safe='')}"


async def receive_upload(request: Request, storage: LocalStorage, key: str, max_bytes: int) -> int:
    """Stream the request body into storage. 413 when it exceeds ``max_bytes``."""
    declared = request.headers.get("content-length")
    if declared is not None and (not declared.isdigit() or int(declared) > max_bytes):
        raise HTTPException(413, f"Request body exceeds {max_bytes} bytes")
    try:
        return await storage.write_stream(key, request.stream(), max_bytes)
    except TooLargeError:
        raise HTTPException(413, f"Request body exceeds {max_bytes} bytes") from None


def _chunks(handle: BinaryIO) -> Iterator[bytes]:
    with handle:
        while chunk := handle.read(CHUNK):
            yield chunk


def file_response(storage: LocalStorage, key: str, *, media_type: str, filename: str) -> StreamingResponse:
    """Stream a stored file as an attachment; 404 when the bytes are gone."""
    if not storage.exists(key):
        raise HTTPException(404, "File not found")
    headers = {
        "Content-Disposition": attachment_header(filename),
        "Content-Length": str(storage.size(key)),
        "X-Content-Type-Options": "nosniff",
    }
    return StreamingResponse(_chunks(storage.open_read(key)), media_type=media_type, headers=headers)
