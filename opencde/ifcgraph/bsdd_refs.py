# This file was generated with the assistance of an AI coding tool.
"""The references of an IFC file to buildingSMART's Data Dictionary, read in a worker process (OB-42).

    python -m opencde.ifcgraph.bsdd_refs FILE [--memory-mb N]

Answers with one JSON document on stdout: the file's schema; every ``IfcClassificationReference`` whose URI is
bSDD's, in its ``Location`` or made of its identification under the dictionary URI of its ``Location`` or its
classification, with the objects it is associated with; and every property set or quantity set named ``Pset_…`` or
``Qto_…`` with the names of its properties and the objects it is on, so that they can be checked against bSDD's IFC
dictionary. The answer is bounded: at most ``MAX_REFERENCES`` references, ``MAX_SETS`` sets and ``MAX_PROPERTIES``
names a set, with ``cut`` saying when there were more, and ``MAX_OBJECTS`` objects an entry beside their number.
Exit code 0 is an answer, 2 an error with a JSON line on stderr. The caller sets the memory and time limits.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from ifc_lpg.worker import keep_stdout_for_the_answer, limit_memory

from opencde.ifcgraph.bsdd import parse_uri

MAX_REFERENCES = 1_000  # each is a question to bSDD the first time
MAX_SETS = 500
MAX_PROPERTIES = 500  # names a set
MAX_OBJECTS = 20  # an entry, beside the count of all of them
MAX_TEXT = 200
MAX_ERROR = 300
SOURCE_DEPTH = 8  # how far a reference's ReferencedSource is followed to its classification
SET_PREFIXES = ("Pset_", "Qto_")
IDENTIFICATION = ("Identification", "ItemReference")  # IFC4 and later, IFC2X3


def _text(value: Any) -> str | None:
    return value[:MAX_TEXT] if isinstance(value, str) and value.strip() else None


def _objects(entities: Iterable[Any]) -> tuple[list[dict[str, str]], int]:
    """The first few of the objects, each by GlobalId and class, and how many there are."""
    listed: list[dict[str, str]] = []
    count = 0
    for entity in entities:
        guid = getattr(entity, "GlobalId", None)
        if not guid:
            continue
        count += 1
        if len(listed) < MAX_OBJECTS:
            listed.append({"global_id": str(guid), "ifc_class": entity.is_a()})
    return listed, count


def classification_of(reference: Any) -> Any | None:
    """The ``IfcClassification`` a reference leads to through ``ReferencedSource``, a few steps at most."""
    source = reference
    for _ in range(SOURCE_DEPTH):
        source = getattr(source, "ReferencedSource", None)
        if source is None:
            return None
        if source.is_a("IfcClassification"):
            return source
    return None


def identification_of(reference: Any) -> tuple[str, str] | None:
    """The class code a reference carries and the attribute that carries it: ``Identification``, or ``ItemReference``
    in IFC2X3."""
    for attribute in IDENTIFICATION:
        text = _text(getattr(reference, attribute, None))
        if text is not None:
            return text, attribute
    return None


def dictionary_uri_of(classification: Any) -> str | None:
    """The bSDD dictionary URI a classification carries: ``Location`` in IFC4, ``Specification`` in IFC 4.3, and
    ``Source`` in an IFC2X3 file, whose classification has neither."""
    for attribute in ("Specification", "Location", "Source"):
        parsed = parse_uri(getattr(classification, attribute, None))
        if parsed is not None and parsed.kind is None:
            return parsed.uri
    return None


def uri_of(reference: Any, classification: Any | None) -> tuple[str, str] | None:
    """The bSDD URI a reference names, and the attribute that names it; None when it names none. The URI is its
    ``Location``, or its identification when that is a URI, or else the identification under the dictionary URI of
    its ``Location`` or of its classification."""
    location = parse_uri(getattr(reference, "Location", None))
    if location is not None and location.kind:
        return location.uri, "Location"
    identification = identification_of(reference)
    if identification is None:
        return None
    code, attribute = identification
    named = parse_uri(code)
    if named is not None and named.kind:
        return named.uri, attribute
    dictionary = location.uri if location is not None else None
    if dictionary is None and classification is not None:
        dictionary = dictionary_uri_of(classification)
    return (f"{dictionary}/class/{code.strip()}", attribute) if dictionary else None


def references_of(model: Any) -> tuple[list[dict[str, Any]], bool]:
    """Every classification reference with a bSDD URI, with the objects it is associated with; and whether there
    were more than are listed."""
    associated: dict[int, list[Any]] = {}
    for rel in model.by_type("IfcRelAssociatesClassification"):
        target = rel.RelatingClassification
        if target is not None and target.is_a("IfcClassificationReference"):
            associated.setdefault(target.id(), []).extend(rel.RelatedObjects or ())
    references: list[dict[str, Any]] = []
    for reference in model.by_type("IfcClassificationReference"):
        classification = classification_of(reference)
        named = uri_of(reference, classification)
        if named is None:
            continue
        if len(references) >= MAX_REFERENCES:
            return references, True
        objects, count = _objects(associated.get(reference.id(), ()))
        identification = identification_of(reference)
        references.append(
            {
                "step_id": reference.id(),
                "uri": named[0],
                "attribute": named[1],
                "identification": identification[0] if identification else None,
                "name": _text(reference.Name),
                "location": _text(reference.Location),
                "classification": None
                if classification is None
                else {
                    "name": _text(classification.Name),
                    "source": _text(classification.Source),
                    "location": _text(
                        getattr(classification, "Specification", None) or getattr(classification, "Location", None)
                    ),
                },
                "objects": objects,
                "object_count": count,
            }
        )
    return references, False


def _definitions(value: Any) -> tuple[Any, ...]:
    """What a ``RelatingPropertyDefinition`` holds: one set, or a set of sets in IFC4."""
    if value is None:
        return ()
    if isinstance(value, (tuple, list)):
        return tuple(value)
    wrapped = getattr(value, "wrappedValue", None)
    if isinstance(wrapped, (tuple, list)):
        return tuple(wrapped)
    return (value,)


def property_sets_of(model: Any) -> tuple[dict[str, dict[str, Any]], bool]:
    """Every ``Pset_`` and ``Qto_`` set by name, with its property names and the objects it is on; and whether there
    were more sets or names than are listed."""
    objects_of: dict[int, list[Any]] = {}
    for rel in model.by_type("IfcRelDefinesByProperties"):
        for definition in _definitions(rel.RelatingPropertyDefinition):
            objects_of.setdefault(definition.id(), []).extend(rel.RelatedObjects or ())
    for type_object in model.by_type("IfcTypeObject"):
        for definition in type_object.HasPropertySets or ():
            objects_of.setdefault(definition.id(), []).append(type_object)
    sets: dict[str, dict[str, Any]] = {}
    cut = False
    for ifc_class, attribute in (("IfcPropertySet", "HasProperties"), ("IfcElementQuantity", "Quantities")):
        for definition in model.by_type(ifc_class):
            name = definition.Name
            if not isinstance(name, str) or not name.startswith(SET_PREFIXES):
                continue
            if name not in sets:
                if len(sets) >= MAX_SETS:
                    cut = True
                    continue
                sets[name] = {"step_id": definition.id(), "properties": [], "objects": [], "object_count": 0}
            entry = sets[name]
            names: list[str] = entry["properties"]
            for prop in getattr(definition, attribute, None) or ():
                prop_name = _text(getattr(prop, "Name", None))
                if prop_name is None or prop_name in names:
                    continue
                if len(names) >= MAX_PROPERTIES:
                    cut = True
                    break
                names.append(prop_name)
            objects, count = _objects(objects_of.get(definition.id(), ()))
            entry["object_count"] = int(entry["object_count"]) + count
            entry["objects"] = [*entry["objects"], *objects][:MAX_OBJECTS]
    for entry in sets.values():
        entry["properties"].sort()
    return sets, cut


def answer(path: Path) -> dict[str, Any]:
    import ifcopenshell

    model = ifcopenshell.open(str(path))
    references, references_cut = references_of(model)
    sets, sets_cut = property_sets_of(model)
    return {
        "schema": str(model.schema),
        "references": references,
        "property_sets": sets,
        "cut": references_cut or sets_cut,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="opencde-bsdd-refs")
    parser.add_argument("ifc", type=Path)
    parser.add_argument("--memory-mb", type=int, default=0)
    args = parser.parse_args(argv)
    if args.memory_mb:
        limit_memory(args.memory_mb)
    try:
        result = answer(args.ifc)
    except Exception as exc:
        sys.stderr.write(json.dumps({"error": f"{type(exc).__name__}: {exc}"[:MAX_ERROR]}) + "\n")
        return 2
    sys.stdout.write(json.dumps(result, separators=(",", ":")) + "\n")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    keep_stdout_for_the_answer()
    sys.exit(main())
