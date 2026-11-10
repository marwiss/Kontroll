# This file was generated with the assistance of an AI coding tool.
"""Applying a change set to an IFC file, in a process of its own (ADR 0021).

``python -m opencde.ifcgraph.apply base.ifc changes.json out.ifc`` reads the base with IfcOpenShell, applies the
changes of a ``DataregiumIfcChangeSet`` (``opencde/documents/changes.py``) one by one, writes the result and answers
with one JSON document on stdout: how many changes were applied, the STEP ids they touched, and the problems, each
with the index of its change and why it could not be applied. A change that cannot be applied is skipped, never
guessed at; the proposal's report carries the problems as issues. Exit code 0 is an answer, 2 an error with a JSON
line on stderr. The caller sets the memory limit and the time limit.

An instance is named by its STEP id, or by a GlobalId and a path from the rooted entity in IFC's attribute names with
indexes, inverse attributes included. ``set`` gives an attribute a value, ``add`` and ``remove`` change one member of
an aggregate, and ``copy`` changes a copy of the instance, re-pointed from the last forward step of the path, so
that an instance several share stays as it was for the others.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any

from ifc_lpg.worker import keep_stdout_for_the_answer, limit_memory

STEP = re.compile(r"^([A-Z][A-Za-z0-9]*)(?:\[([0-9]+)\])?$")
MAX_PROBLEMS = 1_000


class CannotApply(ValueError):
    """Why a change is skipped, in words that name the change and never quote the file."""


def _walk(model: Any, start: Any, path: str | None) -> tuple[Any, tuple[Any, str, int | None] | None]:
    """Follow a path from an instance; returns the instance reached and the last forward step (parent, name, index)."""
    entity = start
    last: tuple[Any, str, int | None] | None = None
    for piece in (path or "").split(".") if path else []:
        match = STEP.match(piece)
        if not match:
            raise CannotApply(f"the path step '{piece}' is not an attribute name with an optional index")
        name, index = match.group(1), (int(match.group(2)) if match.group(2) is not None else None)
        try:
            value = getattr(entity, name)
        except AttributeError:
            raise CannotApply(f"{entity.is_a()} has no attribute {name}") from None
        inverse = name in _inverse_names(model, entity)
        if index is not None:
            if not isinstance(value, (tuple, list)) or index >= len(value):
                raise CannotApply(f"{name} has no member {index}")
            value = value[index]
        if not _is_instance(value):
            raise CannotApply(f"{name} does not lead to an instance")
        last = None if inverse else (entity, name, index)
        entity = value
    return entity, last


def _inverse_names(model: Any, entity: Any) -> set[str]:
    import ifcopenshell

    declaration: Any = ifcopenshell.schema_by_name(model.schema).declaration_by_name(entity.is_a())
    return {a.name() for a in declaration.all_inverse_attributes()}


def _is_instance(value: Any) -> bool:
    return hasattr(value, "is_a") and hasattr(value, "id") and not hasattr(value, "wrappedValue")


def _is_typed(value: Any) -> bool:
    return hasattr(value, "wrappedValue")


def _find(model: Any, change: dict[str, Any]) -> tuple[Any, tuple[Any, str, int | None] | None]:
    """The instance a change names, by STEP id or by GlobalId and path."""
    if change.get("step_id") is not None:
        try:
            return model.by_id(int(change["step_id"])), None
        except RuntimeError:
            raise CannotApply(f"no instance #{change['step_id']}") from None
    try:
        rooted = model.by_guid(str(change["guid"]))
    except RuntimeError:
        raise CannotApply(f"no instance with GlobalId {change['guid']}") from None
    return _walk(model, rooted, change.get("path"))


def to_ifc(model: Any, value: Any) -> Any:
    """A value of the change set as IfcOpenShell wants it: instances, typed values, enumerations and aggregates."""
    if isinstance(value, dict):
        if "enum" in value:
            return str(value["enum"])
        if "type" in value:
            return model.create_entity(str(value["type"]), to_ifc(model, value["value"]))
        entity, _ = _find(model, value)
        return entity
    if isinstance(value, list):
        return tuple(to_ifc(model, item) for item in value)
    return value


def from_ifc(value: Any) -> Any:
    """An attribute's value in the change set's form, to compare with what the proposer saw."""
    if _is_typed(value):
        return {"type": value.is_a(), "value": from_ifc(value.wrappedValue)}
    if _is_instance(value):
        return {"step_id": value.id()}
    if isinstance(value, (tuple, list)):
        return [from_ifc(item) for item in value]
    return value


def _same(expected: Any, current: Any) -> bool:
    """Whether the proposer's `old` is what the file holds; an enumeration is a string in the file."""
    if isinstance(expected, dict) and "enum" in expected:
        return current == expected["enum"]
    if isinstance(expected, dict) and "guid" in expected and isinstance(current, dict):
        return True  # a GlobalId with a path names an instance; its identity is checked when the value is set
    if isinstance(expected, float) or isinstance(current, float):
        try:
            return abs(float(expected) - float(current)) <= 1e-9 * max(1.0, abs(float(current)))
        except (TypeError, ValueError):
            return False
    return expected == current


def _copied(model: Any, entity: Any, last: tuple[Any, str, int | None] | None) -> Any:
    """A copy of the instance, re-pointed from the last forward step of the path."""
    import ifcopenshell.util.element

    if last is None:
        raise CannotApply("copy needs a path whose last step is a forward attribute")
    parent, name, index = last
    copy = ifcopenshell.util.element.copy(model, entity)
    if index is None:
        setattr(parent, name, copy)
    else:
        members = list(getattr(parent, name))
        members[index] = copy
        setattr(parent, name, tuple(members))
    return copy


def apply_one(model: Any, change: dict[str, Any]) -> int:
    """Apply one change; returns the STEP id of the instance changed."""
    entity, last = _find(model, change)
    attribute = str(change["attribute"])
    if attribute in _inverse_names(model, entity):
        raise CannotApply(f"{attribute} is an inverse attribute; change the relationship instead")
    try:
        current = getattr(entity, attribute)
    except AttributeError:
        raise CannotApply(f"{entity.is_a()} has no attribute {attribute}") from None
    if change.get("old") is not None and not _same(change["old"], from_ifc(current)):
        raise CannotApply(f"{attribute} no longer holds the old value")
    if change.get("copy"):
        entity = _copied(model, entity, last)
    op = change["op"]
    try:
        if op == "set":
            setattr(entity, attribute, to_ifc(model, change.get("new")))
        else:
            members = list(current) if isinstance(current, (tuple, list)) else []
            if op == "add":
                index = change.get("index")
                members.insert(
                    len(members) if index is None else min(int(index), len(members)), to_ifc(model, change.get("new"))
                )
            else:
                index = change.get("index")
                if index is None:
                    wanted = change.get("old")
                    index = next((i for i, m in enumerate(members) if _same(wanted, from_ifc(m))), None)
                    if index is None:
                        raise CannotApply(f"{attribute} has no member equal to the old value")
                if int(index) >= len(members):
                    raise CannotApply(f"{attribute} has no member {index}")
                del members[int(index)]
            setattr(entity, attribute, tuple(members) if members else None)
    except CannotApply:
        raise
    except Exception as exc:
        raise CannotApply(f"{attribute} does not take the value: {type(exc).__name__}") from None
    return int(entity.id())


def apply_all(base: Path, changes: list[dict[str, Any]], out: Path) -> dict[str, Any]:
    import ifcopenshell

    model = ifcopenshell.open(str(base))
    touched: list[int] = []
    problems: list[dict[str, Any]] = []
    for index, change in enumerate(changes):
        try:
            touched.append(apply_one(model, change))
        except CannotApply as exc:
            if len(problems) < MAX_PROBLEMS:
                problems.append({"change": index, "error": str(exc)[:300]})
    model.write(str(out))
    return {"applied": len(touched), "touched": sorted(set(touched)), "problems": problems, "count": len(changes)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="opencde-apply")
    parser.add_argument("base", type=Path)
    parser.add_argument("changes", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--memory-mb", type=int, default=0)
    args = parser.parse_args(argv)
    if args.memory_mb:
        limit_memory(args.memory_mb)
    keep_stdout_for_the_answer()
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
    try:
        change_set = json.loads(args.changes.read_text(encoding="utf-8"))
        summary = apply_all(args.base, list(change_set["changes"]), args.out)
    except Exception as exc:  # the caller reads the last line of stderr
        sys.stderr.write(json.dumps({"error": f"{type(exc).__name__}: {exc}"[:300]}) + "\n")
        return 2
    sys.stdout.write(json.dumps(summary, separators=(",", ":")) + "\n")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
