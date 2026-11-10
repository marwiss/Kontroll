# This file was generated with the assistance of an AI coding tool.
"""The difference between two IFC files, element by element, in a process of its own (ADR 0021).

``python -m opencde.ifcgraph.diff A.ifc B.ifc`` pairs the rooted entities of the two files by GlobalId and writes one
JSON document to stdout: the elements only B has (``added``), only A has (``removed``) and those in both whose
attributes differ (``changed``), each named by GlobalId, class, name and storey, and for a changed one the paths that
differ with the old and the new value: a direct attribute by its name, a property as ``Pset.Property``, the placement
as ``ObjectPlacement`` (the 4 by 4 matrix), the shape as ``Representation`` (a fingerprint), the storey as
``Container`` and the type as ``Type``. References to rooted entities compare by GlobalId, other instances by their
structure a few steps deep. Relationships and property sets are folded into the elements they belong to. Nothing
else reaches stdout. Exit code 0 is an answer, 2 an error with a JSON line on stderr.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from pathlib import Path
from typing import Any

from ifc_lpg.worker import keep_stdout_for_the_answer, limit_memory

MAX_ENTRIES = 10_000
DEPTH = 4
# Attributes compared another way, or not at all: the identity and the ownership, the placement and the shape.
SKIPPED = ("type", "GlobalId", "OwnerHistory", "ObjectPlacement", "Representation")
# Rooted entities compared through the elements they describe, not on their own.
FOLDED = ("IfcRelationship", "IfcPropertySetDefinition", "IfcPropertyDefinition")


def _is_instance(value: Any) -> bool:
    return hasattr(value, "is_a") and hasattr(value, "id") and not hasattr(value, "wrappedValue")


def _plain(value: Any, depth: int = DEPTH) -> Any:
    """A value as JSON: a rooted instance by its GlobalId, another by its structure, a typed value by its value."""
    if hasattr(value, "wrappedValue"):
        return _plain(value.wrappedValue, depth)
    if _is_instance(value):
        info = value.get_info(recursive=False, include_identifier=False)
        if info.get("GlobalId"):
            return {"guid": info["GlobalId"]}
        if depth <= 0:
            return {"type": value.is_a()}
        return {
            "type": value.is_a(),
            **{k: _plain(v, depth - 1) for k, v in info.items() if k != "type" and v is not None},
        }
    if isinstance(value, (tuple, list)):
        return [_plain(item, depth) for item in value]
    if isinstance(value, float):
        return round(value, 9)
    return value


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(json.dumps(_plain(value, DEPTH + 4), sort_keys=True).encode("utf-8")).hexdigest()[:16]


def _who(element: Any) -> dict[str, Any]:
    import ifcopenshell.util.element

    container = ifcopenshell.util.element.get_container(element) if element.is_a("IfcProduct") else None
    return {
        "guid": element.GlobalId,
        "type": element.is_a(),
        "name": getattr(element, "Name", None),
        "storey": container.Name if container is not None and container.is_a("IfcBuildingStorey") else None,
    }


def _paths(element: Any) -> dict[str, Any]:
    """Everything compared about one element, by path."""
    import ifcopenshell.util.element
    import ifcopenshell.util.placement

    paths: dict[str, Any] = {}
    info = element.get_info(recursive=False, include_identifier=False)
    for name, value in info.items():
        if name in SKIPPED:
            continue
        paths[name] = _plain(value)
    if element.is_a("IfcObject"):
        for pset, properties in ifcopenshell.util.element.get_psets(element).items():
            for prop, value in properties.items():
                if prop != "id":
                    paths[f"{pset}.{prop}"] = _plain(value)
        type_object = ifcopenshell.util.element.get_type(element)
        paths["Type"] = type_object.GlobalId if type_object is not None else None
    if element.is_a("IfcProduct"):
        placement = getattr(element, "ObjectPlacement", None)
        if placement is not None and placement.is_a("IfcLocalPlacement"):
            matrix = ifcopenshell.util.placement.get_local_placement(placement)
            paths["ObjectPlacement"] = [[round(float(x), 6) for x in row] for row in matrix.tolist()]
        representation = getattr(element, "Representation", None)
        paths["Representation"] = _fingerprint(representation) if representation is not None else None
        container = ifcopenshell.util.element.get_container(element)
        paths["Container"] = container.GlobalId if container is not None else None
    return paths


def _elements(model: Any) -> dict[str, Any]:
    return {
        entity.GlobalId: entity
        for entity in model.by_type("IfcRoot")
        if not any(entity.is_a(folded) for folded in FOLDED)
    }


def compare(a: Path, b: Path, *, max_entries: int = MAX_ENTRIES) -> dict[str, Any]:
    import ifcopenshell

    before, after = ifcopenshell.open(str(a)), ifcopenshell.open(str(b))
    old, new = _elements(before), _elements(after)
    added = [_who(new[guid]) for guid in sorted(set(new) - set(old))]
    removed = [_who(old[guid]) for guid in sorted(set(old) - set(new))]
    changed: list[dict[str, Any]] = []
    same = 0
    for guid in sorted(set(old) & set(new)):
        if old[guid].is_a() != new[guid].is_a():
            changed.append(
                {**_who(new[guid]), "attributes": [{"path": "type", "old": old[guid].is_a(), "new": new[guid].is_a()}]}
            )
            continue
        left, right = _paths(old[guid]), _paths(new[guid])
        differences = [
            {"path": path, "old": left.get(path), "new": right.get(path)}
            for path in sorted(set(left) | set(right))
            if left.get(path) != right.get(path)
        ]
        if differences:
            changed.append({**_who(new[guid]), "attributes": differences})
        else:
            same += 1
    truncated = any(len(entries) > max_entries for entries in (added, removed, changed))
    return {
        "added": added[:max_entries],
        "removed": removed[:max_entries],
        "changed": changed[:max_entries],
        "same": same,
        "truncated": truncated,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="opencde-diff")
    parser.add_argument("a", type=Path)
    parser.add_argument("b", type=Path)
    parser.add_argument("--max-entries", type=int, default=MAX_ENTRIES)
    parser.add_argument("--memory-mb", type=int, default=0)
    args = parser.parse_args(argv)
    if args.memory_mb:
        limit_memory(args.memory_mb)
    keep_stdout_for_the_answer()
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
    try:
        report = compare(args.a, args.b, max_entries=args.max_entries)
    except Exception as exc:  # the caller reads the last line of stderr
        sys.stderr.write(json.dumps({"error": f"{type(exc).__name__}: {exc}"[:300]}) + "\n")
        return 2
    sys.stdout.write(json.dumps(report, separators=(",", ":")) + "\n")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
