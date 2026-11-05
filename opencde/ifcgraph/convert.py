# This file was generated with the assistance of an AI coding tool.
"""Convert an IFC file into node and edge records (runs inside the worker process).

Every entity becomes a node labelled with its class and all its supertypes
(``IfcWallStandardCase``, ``IfcWall``, ``IfcBuildingElement``, …, ``IfcRoot``)
plus ``IfcEntity``. Literal attributes become properties; attributes that point
at other entities become relationships named after the attribute, and so do
inverse attributes (``IsDefinedBy``, ``ContainsElements``), which is what makes
queries such as the GTIN lookup readable. Geometry (representation items,
profiles, placements, styles) is left out unless asked for; it is most of a
model and rarely what a CDE query needs. ``IfcOwnerHistory`` is kept only for
the ``IfcProject``.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

GEOMETRY_ROOTS = (
    "IfcRepresentationItem",
    "IfcRepresentation",
    "IfcProductRepresentation",
    "IfcRepresentationContext",
    "IfcProfileDef",
    "IfcPresentationStyle",
    "IfcPresentationStyleAssignment",
    "IfcPresentationLayerAssignment",
    "IfcObjectPlacement",
    "IfcPlacement",
    "IfcPresentationItem",
)
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass
class Summary:
    schema: str = ""
    entities: int = 0
    relationships: int = 0
    skipped: int = 0
    ifc_project_guid: str | None = None
    classes: dict[str, int] = field(default_factory=dict)


class ConversionError(RuntimeError):
    pass


def _literal(value: Any) -> Any:
    """A JSON-storable scalar or list, or ``None`` when the value is an entity (handled as an edge)."""
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if hasattr(value, "wrappedValue"):  # a select type such as IfcLabel('3')
        return _literal(value.wrappedValue)
    if isinstance(value, tuple | list):
        items = [_literal(item) for item in value]
        if any(item is None for item in items):
            return None
        if all(isinstance(item, bool | int | float | str) for item in items):
            return items
        return json.dumps(items)  # nested lists (e.g. coordinate lists) as JSON text
    return None


def convert(path: Path, *, include_geometry: bool = False, max_entities: int = 5_000_000) -> Iterator[dict[str, Any]]:
    """Yield a header record, then node records, then edge records."""
    try:
        import ifcopenshell
    except ImportError as exc:  # pragma: no cover - depends on the optional extra
        raise ConversionError("IfcOpenShell is not installed; install the 'ifcgraph' extra") from exc

    model = ifcopenshell.open(str(path))
    schema = ifcopenshell.schema_by_name(model.schema)
    summary = Summary(schema=model.schema)
    label_cache: dict[str, list[str]] = {}

    def labels_of(class_name: str) -> list[str]:
        if class_name not in label_cache:
            chain = []
            declaration: Any = schema.declaration_by_name(class_name)
            while declaration is not None:
                chain.append(declaration.name())
                declaration = declaration.supertype()
            label_cache[class_name] = [name for name in chain if _IDENTIFIER.match(name)]
        return label_cache[class_name]

    def skipped(entity: Any) -> bool:
        if entity.is_a("IfcOwnerHistory"):
            return True
        return not include_geometry and any(entity.is_a(root) for root in GEOMETRY_ROOTS)

    kept: set[int] = set()
    edges: list[dict[str, Any]] = []
    total = 0
    unreadable = 0
    for entity in model:
        total += 1
        if total > max_entities:
            raise ConversionError(f"the model has more than {max_entities} entities")
        if skipped(entity):
            summary.skipped += 1
            continue
        kept.add(entity.id())

    project = next(iter(model.by_type("IfcProject")), None)
    owner_history_id = project.OwnerHistory.id() if project is not None and project.OwnerHistory else None
    if owner_history_id is not None:
        kept.add(owner_history_id)
    summary.ifc_project_guid = project.GlobalId if project is not None else None

    for entity in model:
        step = entity.id()
        if step not in kept:
            continue
        class_name = entity.is_a()
        props: dict[str, Any] = {"ifc_class": class_name}
        for index, name in enumerate(entity.get_attribute_names()):
            if not _IDENTIFIER.match(name):
                continue
            try:
                value = entity[index]
            except Exception:
                unreadable += 1
                continue
            if value is None:
                continue
            literal = _literal(value)
            if literal is not None:
                props[name] = literal
                continue
            for target in value if isinstance(value, tuple | list) else (value,):
                if hasattr(target, "id") and target.id() in kept:
                    edges.append({"t": "e", "a": step, "b": target.id(), "type": name})
        try:
            inverse_names = entity.get_inverse_attribute_names()
        except Exception:
            inverse_names = ()
        for name in inverse_names:
            if not _IDENTIFIER.match(name):
                continue
            try:
                targets = getattr(entity, name) or ()
            except Exception:
                unreadable += 1
                continue
            for target in targets:
                if hasattr(target, "id") and target.id() in kept:
                    edges.append({"t": "e", "a": step, "b": target.id(), "type": name})
        summary.entities += 1
        summary.classes[class_name] = summary.classes.get(class_name, 0) + 1
        yield {"t": "n", "step": step, "labels": labels_of(class_name), "props": props}

    summary.relationships = len(edges)
    yield {
        "t": "h",
        "schema": summary.schema,
        "entities": summary.entities,
        "relationships": summary.relationships,
        "skipped": summary.skipped,
        "ifc_project_guid": summary.ifc_project_guid,
        "classes": summary.classes,
    }
    yield from edges


def write_jsonl(path: Path, out: Path, **options: Any) -> dict[str, Any]:
    """Run :func:`convert` and write the records to ``out``; returns the header record."""
    header: dict[str, Any] = {}
    with out.open("w", encoding="utf-8") as handle:
        for record in convert(path, **options):
            if record["t"] == "h":
                header = record
            handle.write(json.dumps(record) + "\n")
    return header
