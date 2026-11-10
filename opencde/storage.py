# This file was generated with the assistance of an AI coding tool.
"""Binary storage for documents, snapshots, bitmaps and BIM snippets.

Keys are built by the server from UUIDs and a fixed category, never from
anything a client sent, so a key can only ever point inside the storage root.
The local file system is the first backend; an object store can implement the
same small interface later.
"""

from __future__ import annotations

import os
import re
import shutil
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import BinaryIO, Protocol

import anyio

from opencde.ids import is_uuid

CATEGORIES = frozenset(
    {
        "documents",
        "parts",
        "prechecks",
        "proposals",
        "geometry",
        "snapshots",
        "bitmaps",
        "snippets",
        "bcf-documents",
        "backups",
        "published",
    }
)
_SUFFIX = re.compile(r"^[a-z0-9]{1,8}$")


def make_key(category: str, object_id: str, suffix: str = "") -> str:
    """``snapshots/<uuid>.png``; raises if any part is not of the expected shape."""
    if category not in CATEGORIES:
        raise ValueError(f"unknown storage category {category!r}")
    if not is_uuid(object_id):
        raise ValueError("storage keys are built from UUIDs only")
    if suffix and not _SUFFIX.match(suffix):
        raise ValueError(f"unsafe suffix {suffix!r}")
    return f"{category}/{object_id}" + (f".{suffix}" if suffix else "")


class Storage(Protocol):
    def exists(self, key: str) -> bool: ...
    def size(self, key: str) -> int: ...
    def open_read(self, key: str) -> BinaryIO: ...
    def write_bytes(self, key: str, data: bytes) -> None: ...
    async def write_stream(self, key: str, chunks: AsyncIterator[bytes], max_bytes: int) -> int: ...
    def delete(self, key: str) -> None: ...
    def iter_keys(self, category: str) -> Iterator[str]: ...


class TooLargeError(ValueError):
    """The stream exceeded the allowed number of bytes."""


class LocalStorage:
    """Files under one root directory, one sub-directory per category."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        for category in CATEGORIES:
            (self.root / category).mkdir(parents=True, exist_ok=True)

    def path(self, key: str) -> Path:
        category, _, name = key.partition("/")
        if category not in CATEGORIES or "/" in name or "\\" in name or ".." in name or not name:
            raise ValueError(f"invalid storage key {key!r}")
        return self.root / category / name

    def exists(self, key: str) -> bool:
        return self.path(key).is_file()

    def size(self, key: str) -> int:
        return self.path(key).stat().st_size

    def open_read(self, key: str) -> BinaryIO:
        return self.path(key).open("rb")

    def write_bytes(self, key: str, data: bytes) -> None:
        target = self.path(key)
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, target)

    async def write_stream(self, key: str, chunks: AsyncIterator[bytes], max_bytes: int) -> int:
        """Write a request body chunk by chunk, counting bytes; never trusts Content-Length."""
        target = self.path(key)
        tmp = target.with_suffix(target.suffix + ".tmp")
        written = 0
        try:
            async with await anyio.open_file(tmp, "wb") as handle:
                async for chunk in chunks:
                    written += len(chunk)
                    if written > max_bytes:
                        raise TooLargeError(f"body exceeds {max_bytes} bytes")
                    await handle.write(chunk)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
        os.replace(tmp, target)
        return written

    def delete(self, key: str) -> None:
        self.path(key).unlink(missing_ok=True)

    def iter_keys(self, category: str) -> Iterator[str]:
        if category not in CATEGORIES:
            raise ValueError(f"unknown storage category {category!r}")
        for entry in sorted((self.root / category).iterdir()):
            if entry.is_file() and not entry.name.endswith(".tmp"):
                yield f"{category}/{entry.name}"

    def copy_in(self, source: Path, key: str) -> int:
        """Copy an existing file (seed data) into storage; returns its size."""
        target = self.path(key)
        shutil.copyfile(source, target)
        return target.stat().st_size
