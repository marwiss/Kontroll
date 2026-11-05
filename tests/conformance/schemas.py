# This file was generated with the assistance of an AI coding tool.
"""Validate API responses against the pinned buildingSMART JSON schemas.

The BCF and Foundation schemas are JSON Schema draft-03 with relative
``$ref`` links between files. Each file is registered under its file URI and
given an ``id`` so those links resolve.
"""

from __future__ import annotations

import copy
import json
from functools import cache
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft3Validator, Draft7Validator
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


def _openapi_to_jsonschema(node: Any) -> Any:
    """OpenAPI 3.0 schema objects as JSON Schema: ``nullable: true`` becomes a ``null`` type alternative."""
    if isinstance(node, list):
        return [_openapi_to_jsonschema(item) for item in node]
    if not isinstance(node, dict):
        return node
    converted = {key: _openapi_to_jsonschema(value) for key, value in node.items() if key != "nullable"}
    if node.get("nullable") and isinstance(converted.get("type"), str):
        converted["type"] = [converted["type"], "null"]
    return converted


def _relax_all_of(node: Any, components: dict[str, Any]) -> Any:
    """Inline ``allOf`` branches and drop their ``additionalProperties: false``.

    ``UploadFilePartInstruction`` is ``allOf: [LinkData, {...}]`` where ``LinkData`` forbids additional
    properties; read literally (JSON Schema) no instance could ever satisfy it. OpenAPI tooling treats
    ``allOf`` as composition, which is what the specification means, so the test validator does too.
    """
    if isinstance(node, list):
        return [_relax_all_of(item, components) for item in node]
    if not isinstance(node, dict):
        return node
    result = {key: _relax_all_of(value, components) for key, value in node.items()}
    if isinstance(result.get("allOf"), list):
        branches = []
        for branch in result["allOf"]:
            if isinstance(branch, dict) and "$ref" in branch:
                branch = copy.deepcopy(components["schemas"][branch["$ref"].rsplit("/", 1)[-1]])
            branch = dict(branch)
            branch.pop("additionalProperties", None)
            branches.append(branch)
        result["allOf"] = branches
    return result


@cache
def _documents_components() -> dict[str, Any]:
    document = yaml.safe_load((SPEC_DIR / "documents-api" / "swagger.yaml").read_text(encoding="utf-8"))
    components = _openapi_to_jsonschema(document["components"])
    return _relax_all_of(components, components)


def validate_documents(instance: Any, component: str) -> None:
    """Validate against a component schema of the Documents API ``swagger.yaml`` (OpenAPI 3.0)."""
    root = {"$ref": f"#/components/schemas/{component}", "components": _documents_components()}
    Draft7Validator(root).validate(instance)
