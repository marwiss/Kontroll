# This file was generated with the assistance of an AI coding tool.
"""Convert an IFC file into node and edge records (runs inside the worker process).

Two forms come out of here. :func:`convert_lossless` is the default, and a file can be written back from what it gives.
:func:`convert` is the ordinary form, ``OPENCDE_IFC_LPG_LOSSLESS=false``, which the rest of this text is about, and whose
nodes, relationships and values are all in the other one too.

Every entity becomes a node labelled with its class and all its supertypes
(``IfcWallStandardCase``, ``IfcWall``, ``IfcBuildingElement``, …, ``IfcRoot``)
plus ``IfcEntity``. Literal attributes become properties; attributes that point
at other entities become relationships named after the attribute, and so do
inverse attributes (``IsDefinedBy``, ``ContainsElements``), which is what makes
queries such as the GTIN lookup readable. Geometry (representation items,
profiles, placements, styles) is left out unless asked for; it is most of a
model and rarely what a CDE query needs. ``IfcOwnerHistory`` is kept only for
the ``IfcProject``.

The mapping follows Zhu, Wu and Lei, "IFC-graph for facilitating building
information access and query", Automation in Construction 148 (2023), 104778,
https://doi.org/10.1016/j.autcon.2023.104778; ``docs/ifc-lpg.md`` says where
this code differs from the article.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from opencde.ifcgraph.lossless import encode_block, encode_header, encode_instance
from opencde.ifcgraph.schema import Schema
from opencde.ifcgraph.step import StepError, StepFile, statement_text

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
BLOCK_BYTES = 256 * 1024  # before compression; what a read of one instance's geometry would have to unpack


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
        raise ConversionError("IfcOpenShell is not installed; install the 'ifc-lpg' extra") from exc

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
    project_id = project.id() if project is not None else None

    def linked(source: int, target: Any) -> bool:
        """Whether an edge goes in the graph. Every ``IfcRoot`` usually shares the project's owner history, and an
        edge from each of them would make that one node the centre of the graph."""
        if not hasattr(target, "id") or target.id() not in kept:
            return False
        return target.id() != owner_history_id or source == project_id

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
                if linked(step, target):
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
                if linked(step, target):
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


def convert_lossless(
    path: Path, *, include_geometry: bool = False, max_entities: int = 5_000_000
) -> Iterator[dict[str, Any]]:
    """Yield the records of a graph a file can be written back from: nothing the file says is left out.

    It reads the file itself and uses IfcOpenShell only for the schema, because IfcOpenShell's reading changes some
    values (``step.py``) and its API cannot make all of them (``IFCPROPERTYSETDEFINITIONSET`` ends the process). See
    ``lossless.py`` for where each value goes, and ADR 0010. Inverse attributes are here for the queries' sake; they
    are worked out from the schema, and the writer does not read them.

    The nodes are those of the ordinary form, with the rest in blocks, unless geometry is asked to be nodes too. An
    owner history is linked from its project alone in both, since every ``IfcRoot`` usually shares it, and an edge from
    each of them would make that one node the centre of the graph.
    """
    try:
        file = StepFile(path.read_bytes())
        if len(file) > max_entities:
            raise ConversionError(f"the model has more than {max_entities} entities")
        schema = Schema(file.schema)
        keywords = {step: file.keyword_of(step) for step in file.ids()}
        project = next((step for step, keyword in keywords.items() if keyword == b"IFCPROJECT"), None)
        project_history = _second_parameter(file, project)
    except StepError as exc:
        raise ConversionError(str(exc)) from exc

    classes = set(keywords.values())
    geometry_classes = {keyword for keyword in classes if set(schema.chain(keyword)) & set(GEOMETRY_ROOTS)}
    history_classes = {keyword for keyword in classes if "IfcOwnerHistory" in schema.chain(keyword)}
    histories = {step for step, keyword in keywords.items() if keyword in history_classes}
    in_blocks: set[int] = set()
    if not include_geometry:
        in_blocks = {step for step, keyword in keywords.items() if keyword in geometry_classes}
        in_blocks |= histories - {project_history}
    nodes = keywords.keys() - in_blocks
    targets = nodes - histories
    project_targets = targets | ({project_history} & nodes)

    summary = Summary(schema=file.schema, skipped=len(in_blocks))
    references: list[tuple[int, str, Any, int]] = []
    try:
        for step, keyword, parameters in file:
            if step in in_blocks:
                continue
            known = project_targets if step == project else targets
            properties, found = encode_instance(keyword, parameters, schema, known)
            chain = schema.chain(keyword)
            class_name = chain[0] if chain else keyword.decode("ascii")
            references.extend((step, attribute, position, target) for attribute, position, target in found)
            summary.entities += 1
            summary.classes[class_name] = summary.classes.get(class_name, 0) + 1
            if step == project:
                summary.ifc_project_guid = properties.get("GlobalId")
            yield {
                "t": "n",
                "step": step,
                "labels": [name for name in chain if _IDENTIFIER.match(name)],
                "props": {"ifc_class": class_name, **properties},
            }
        yield from _blocks(file, sorted(in_blocks))
    except StepError as exc:
        raise ConversionError(str(exc)) from exc
    inverses: dict[tuple[int, str, int], None] = {}
    for step, attribute, _position, target in references:
        for inverse in schema.refers_back(keywords[step], attribute, keywords[target]):
            inverses[(target, inverse, step)] = None
    summary.relationships = len(references) + len(inverses)
    yield {
        "t": "h",
        "schema": summary.schema,
        "entities": summary.entities,
        "relationships": summary.relationships,
        "skipped": summary.skipped,
        "ifc_project_guid": summary.ifc_project_guid,
        "classes": summary.classes,
        "lossless": True,
        "ifc_header": encode_header(file.header_values),
    }
    for step, attribute, position, target in references:
        yield {"t": "e", "a": step, "b": target, "type": attribute, "position": position}
    for target, inverse, step in inverses:
        yield {"t": "e", "a": target, "b": step, "type": inverse}


def _second_parameter(file: StepFile, project: int | None) -> int | None:
    """The owner history of a project: its second attribute, if that is a reference at all."""
    if project is None:
        return None
    parameters = file[project][1]
    value = parameters[1] if len(parameters) > 1 else None
    return value if isinstance(value, int) else None


def _blocks(file: StepFile, steps: list[int]) -> Iterator[dict[str, Any]]:
    """The instances that are no nodes, as blocks of text in order of id."""
    lines: list[bytes] = []
    size = 0
    first = 0

    def block() -> dict[str, Any]:
        return {"t": "g", "first": first, "instances": len(lines), "text": encode_block(b"".join(lines))}

    for step in steps:
        keyword, parameters = file[step]
        line = b"#%d=%s;\n" % (step, statement_text(keyword, parameters))
        if not lines:
            first = step
        lines.append(line)
        size += len(line)
        if size >= BLOCK_BYTES:
            yield block()
            lines, size = [], 0
    if lines:
        yield block()


def write_jsonl(path: Path, out: Path, *, lossless: bool = False, **options: Any) -> dict[str, Any]:
    """Run a conversion and write the records to ``out``; returns the header record."""
    header: dict[str, Any] = {}
    records = convert_lossless(path, **options) if lossless else convert(path, **options)
    with out.open("w", encoding="utf-8") as handle:
        for record in records:
            if record["t"] == "h":
                header = record
            handle.write(json.dumps(record) + "\n")
    return header
