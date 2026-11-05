# This file was generated with the assistance of an AI coding tool.
"""Snapshot and bitmap images (BCF API 3.5): base64 in, verified bytes out.

The declared type (``png`` or ``jpg``) must match the file's magic bytes, so a
client cannot store an HTML file or a script under an image name, and the
decoded size is bounded before the base64 text is even decoded.
"""

from __future__ import annotations

import base64
import binascii
import re

from fastapi import HTTPException

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC = b"\xff\xd8\xff"

IMAGE_TYPES = ("png", "jpg")
CONTENT_TYPES = {"png": "image/png", "jpg": "image/jpeg"}

_DATA_URL_PREFIX = re.compile(r"^data:image/[a-z]+;base64,", re.IGNORECASE)
_WHITESPACE = re.compile(r"\s+")


def sniff(data: bytes) -> str | None:
    if data.startswith(PNG_MAGIC):
        return "png"
    if data.startswith(JPEG_MAGIC):
        return "jpg"
    return None


def decode_image(encoded: str, declared: str, max_bytes: int, what: str = "image") -> bytes:
    """Decode ``encoded`` and check that it is the declared kind of image and not too large."""
    if declared not in IMAGE_TYPES:
        raise HTTPException(400, f"{what}: type must be one of {', '.join(IMAGE_TYPES)}")
    text = _WHITESPACE.sub("", _DATA_URL_PREFIX.sub("", encoded))
    if len(text) > max_bytes * 4 // 3 + 8:
        raise HTTPException(400, f"{what}: image exceeds {max_bytes} bytes")
    try:
        data = base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(400, f"{what}: data is not valid base64") from None
    if len(data) > max_bytes:
        raise HTTPException(400, f"{what}: image exceeds {max_bytes} bytes")
    if sniff(data) != declared:
        raise HTTPException(400, f"{what}: data is not a {declared} image")
    return data
