# This file was generated with the assistance of an AI coding tool.
"""Turning uploaded parts (or a browser upload) into a stored document file.

Both functions are synchronous file work meant to run in a worker thread.
They write to a temporary name and rename at the end, so a half-written file
is never visible, and they compute the SHA-256 that the version records.
"""

from __future__ import annotations

import hashlib
import os
from typing import BinaryIO

from opencde.storage import LocalStorage, TooLargeError

CHUNK = 1024 * 1024


class AssemblyError(ValueError):
    """The parts do not add up to the announced file."""


def assemble(storage: LocalStorage, part_keys: list[str], target_key: str, expected_size: int) -> str:
    """Concatenate the parts into ``target_key``, delete them, return the SHA-256 hex digest."""
    digest = hashlib.sha256()
    total = 0
    target = storage.path(target_key)
    tmp = target.with_suffix(target.suffix + ".tmp")
    try:
        with tmp.open("wb") as out:
            for key in part_keys:
                with storage.open_read(key) as source:
                    while chunk := source.read(CHUNK):
                        out.write(chunk)
                        digest.update(chunk)
                        total += len(chunk)
        if total != expected_size:
            raise AssemblyError(f"uploaded {total} bytes, announced {expected_size}")
        os.replace(tmp, target)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    for key in part_keys:
        storage.delete(key)
    return digest.hexdigest()


def store_stream(storage: LocalStorage, source: BinaryIO, target_key: str, max_bytes: int) -> tuple[int, str]:
    """Copy a file object into storage with a size limit. Returns (size, sha256)."""
    digest = hashlib.sha256()
    total = 0
    target = storage.path(target_key)
    tmp = target.with_suffix(target.suffix + ".tmp")
    try:
        with tmp.open("wb") as out:
            while chunk := source.read(CHUNK):
                total += len(chunk)
                if total > max_bytes:
                    raise TooLargeError(f"file exceeds {max_bytes} bytes")
                out.write(chunk)
                digest.update(chunk)
        os.replace(tmp, target)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return total, digest.hexdigest()
