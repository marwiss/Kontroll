# This file was generated with the assistance of an AI coding tool.
"""Validate API responses against the pinned buildingSMART JSON schemas.

The BCF and Foundation schemas are JSON Schema draft-03 with relative
``$ref`` links between files. Each file is registered under its file URI and
given an ``id`` so those links resolve.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft3Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT3

from tests.conftest import SPEC_DIR

_SCHEMA_ROOT = SPEC_DIR.resolve()


def _load(path: Path) -> dict[str, Any]:
    schema = json.loads(path.read_text(encoding="utf-8"))
    schema["id"] = path.resolve().as_uri()
    return schema


def _retrieve(uri: str) -> Resource:
    path = Path(
        uri.removeprefix("file:///").replace("/", "\\")
        if uri.startswith("file:///") and ":" in uri[8:11]
        else uri.removeprefix("file://")
    )
    if not path.exists():  # POSIX form of the same URI
        from urllib.request import url2pathname

        path = Path(url2pathname(uri.removeprefix("file:")))
    resolved = path.resolve()
    if _SCHEMA_ROOT not in resolved.parents:
        raise LookupError(f"refusing to load schema outside spec/: {uri}")
    return Resource.from_contents(_load(resolved), default_specification=DRAFT3)


REGISTRY = Registry(retrieve=_retrieve)


def schema(relative_path: str, *, allow_documents_api_id: bool = False) -> dict[str, Any]:
    loaded = _load(SPEC_DIR / relative_path)
    if allow_documents_api_id:
        # Foundation API v1.0 lists only bcf and foundation here, but the Documents API
        # requires its own entry in the same list (see spec/SOURCES.md).
        loaded = copy.deepcopy(loaded)
        loaded["properties"]["versions"]["items"]["properties"]["api_id"]["enum"].append("documents")
    return loaded


def validate(instance: Any, relative_path: str, **options: Any) -> None:
    """Raise ``jsonschema.ValidationError`` if ``instance`` does not match the schema file."""
    validator = Draft3Validator(schema(relative_path, **options), registry=REGISTRY)
    validator.validate(instance)
