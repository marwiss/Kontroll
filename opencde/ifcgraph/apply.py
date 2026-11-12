# This file was generated with the assistance of an AI coding tool.
"""Applying a change set to an IFC file, in a process of its own (ADR 0021).

``python -m opencde.ifcgraph.apply base.ifc changes.json out.ifc`` reads the base with IfcOpenShell, applies the
changes of a ``DataregiumIfcChangeSet`` (``opencde/documents/changes.py``) one by one, writes the result and answers
with one JSON document on stdout: how many changes were applied, the STEP ids they touched, and the problems, each
with the index of its change and why it could not be applied. A change that cannot be applied is skipped, never
guessed at; the proposal's report carries the problems as issues. Exit code 0 is an answer, 2 an error with a JSON
line on stderr. The caller sets the memory limit and the time limit. With ``--read`` and no ``out`` the worker
changes nothing and answers with what each change's attribute holds in the file, in the change set's value form,
for the conflicts of an approval.

An instance is named by its STEP id, or by a GlobalId and a path from the rooted entity in IFC's attribute names with
indexes, inverse attributes included. ``set`` gives an attribute a value, ``add`` and ``remove`` change one member of
an aggregate, and ``copy`` changes a copy of the instance, re-pointed from the last forward step of the path, so
that an instance several share stays as it was for the others. ``delete`` removes an instance named by its STEP id,
and only when nothing refers to it, so that no reference is left hanging.

A change set with ``ops`` has Dataspatium's write tools applied first, with the app's own code (``ops.py``), and the
answer says under ``ops`` what they created, touched and noted, and which one failed; the operations stop at one that
fails, as in the app, and then nothing more is applied. The changes come next and describe what the operations did
to existing instances, as the app found it: a change the operations already made counts as applied rather than being
made twice, and one they did not is applied as any. Last, each key of ``keep_theirs`` (``#170.NominalValue`` or
``<guid>/<path>.Name``, as the server's conflicts name them) gets back what the file held before: the latest
version's value, which the proposer gave up. ``--proposer`` names who the owner histories the operations make name.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any

from ifc_db.worker import keep_stdout_for_the_answer, limit_memory

STEP = re.compile(r"^([A-Z][A-Za-z0-9]*)(?:\[([0-9]+)\])?$")
GUID = re.compile(r"^[0-9A-Za-z_$]{22}$")
ATTRIBUTE = re.compile(r"^[A-Z][A-Za-z0-9]*$")
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
    if change["op"] == "delete":
        return _delete(model, entity)
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


def _holds(model: Any, value: Any, current: Any) -> bool:
    """Whether an attribute's value in the file is ``value`` in the change set's form, an instance by its identity."""
    if isinstance(value, dict):
        if "enum" in value:
            return current == value["enum"]
        if "type" in value:
            return (
                _is_typed(current) and current.is_a() == value["type"] and _same(value["value"], current.wrappedValue)
            )
        try:
            entity, _ = _find(model, value)
        except CannotApply:
            return False
        return _is_instance(current) and current.id() == entity.id()
    if isinstance(value, list):
        return (
            isinstance(current, (tuple, list))
            and len(current) == len(value)
            and all(_holds(model, item, member) for item, member in zip(value, current, strict=True))
        )
    if value is None or current is None:
        return value is None and current is None
    if _is_instance(current) or isinstance(current, (tuple, list)):
        return False
    return _same(value, current)


def _already(model: Any, change: dict[str, Any]) -> bool:
    """Whether the operations made the change already: a `set` whose attribute holds the new value, an `add` whose
    member is there, a `remove` whose member or instance is gone, a `delete` whose instance is."""
    try:
        entity, _ = _find(model, change)
    except CannotApply:
        return change["op"] in ("remove", "delete")
    if change["op"] == "delete":
        return False
    try:
        current = getattr(entity, str(change["attribute"]))
    except AttributeError:
        return False
    if change["op"] == "set":
        return _holds(model, change.get("new"), current)
    members = list(current) if isinstance(current, (tuple, list)) else []
    if change["op"] == "add":
        return any(_holds(model, change.get("new"), member) for member in members)
    if change.get("index") is not None:  # a member by its place: whether it went cannot be told
        return False
    return not any(_holds(model, change.get("old"), member) for member in members)


def key_locator(key: str) -> dict[str, Any]:
    """The instance and the attribute a key of ``keep_theirs`` names, in the form of the server's conflicts:
    ``#<step>.<attribute>``, or ``<guid>/<path>.<attribute>`` with an empty path for the rooted entity itself."""
    named, _, attribute = key.rpartition(".")
    if not ATTRIBUTE.match(attribute) or not named:
        raise CannotApply("the key does not end in an attribute")
    if named.startswith("#"):
        if not named[1:].isdigit():
            raise CannotApply("the key names no STEP id")
        return {"step_id": int(named[1:]), "attribute": attribute}
    guid, _, path = named.partition("/")
    if not GUID.match(guid):
        raise CannotApply("the key names no GlobalId")
    return {"guid": guid, "path": path or None, "attribute": attribute}


def _hold(model: Any, keys: list[str], problems: list[dict[str, Any]]) -> list[tuple[int, dict[str, Any], Any]]:
    """What each key of ``keep_theirs`` holds in the file before anything is applied: the latest version's value."""
    held: list[tuple[int, dict[str, Any], Any]] = []
    for index, key in enumerate(keys):
        try:
            locator = key_locator(str(key))
            entity, _ = _find(model, locator)
            if locator["attribute"] in _inverse_names(model, entity):
                raise CannotApply(f"{locator['attribute']} is an inverse attribute")
            try:
                held.append((index, locator, from_ifc(getattr(entity, locator["attribute"]))))
            except AttributeError:
                raise CannotApply(f"{entity.is_a()} has no attribute {locator['attribute']}") from None
        except CannotApply as exc:
            problems.append({"keep": index, "error": str(exc)[:300]})
    return held


def _restore(model: Any, held: list[tuple[int, dict[str, Any], Any]], problems: list[dict[str, Any]]) -> None:
    """Each key of ``keep_theirs`` set back to the latest version's value, on the instance its path leads to now: an
    operation may have put a new instance there, as a moved element gets a new point."""
    for index, locator, value in held:
        try:
            entity, _ = _find(model, locator)
            setattr(entity, locator["attribute"], to_ifc(model, value))
        except CannotApply as exc:
            problems.append({"keep": index, "error": str(exc)[:300]})
        except Exception as exc:
            problems.append(
                {"keep": index, "error": f"{locator['attribute']} does not take its value back: {type(exc).__name__}"}
            )


def _delete(model: Any, entity: Any) -> int:
    """Remove an instance that nothing refers to; one that is still referred to is skipped, as IFC-DB's
    ``delete_nodes`` refuses it in the graph."""
    step = int(entity.id())
    if model.get_inverse(entity):
        raise CannotApply(f"#{step} is still referred to; remove what refers to it first")
    model.remove(entity)
    return step


def value_of(entity: Any, attribute: str) -> Any:
    """What an attribute holds, in the change set's value form: an enumeration as ``{"enum"}``, an instance with a
    GlobalId as ``{"guid"}`` and any other as ``{"step_id"}``, a typed value as ``{"type", "value"}``."""
    value = getattr(entity, attribute)
    try:
        enumeration = isinstance(value, str) and "ENUMERATION" in str(entity.attribute_type(attribute))
    except Exception:
        enumeration = False
    if enumeration:
        return {"enum": value}

    def form(item: Any) -> Any:
        if _is_instance(item) and not _is_typed(item):
            guid = getattr(item, "GlobalId", None) if item.is_a("IfcRoot") else None
            return {"guid": guid} if guid else {"step_id": item.id()}
        if isinstance(item, (tuple, list)):
            return [form(member) for member in item]
        return from_ifc(item)

    return form(value)


def read_values(base: Path, changes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """What each change's attribute holds in ``base``: ``{"value": …}``, or ``{"error": …}`` where the instance or the
    attribute is not there."""
    import ifcopenshell

    model = ifcopenshell.open(str(base))
    values: list[dict[str, Any]] = []
    for change in changes:
        try:
            entity, _ = _find(model, change)
            if change.get("op") == "delete":  # what a deletion points at is the instance itself, while it is there
                values.append({"value": {"step_id": int(entity.id())}})
                continue
            values.append({"value": value_of(entity, str(change["attribute"]))})
        except CannotApply as exc:
            values.append({"error": str(exc)[:300]})
        except (AttributeError, RuntimeError, TypeError):
            values.append({"error": f"no attribute {change.get('attribute')}"})
    return values


def apply_all(
    base: Path,
    changes: list[dict[str, Any]],
    out: Path,
    *,
    ops: list[dict[str, Any]] | None = None,
    keep_theirs: list[str] | None = None,
    proposer: str = "",
) -> dict[str, Any]:
    import ifcopenshell

    model = ifcopenshell.open(str(base))
    touched: list[int] = []
    problems: list[dict[str, Any]] = []
    held = _hold(model, keep_theirs or [], problems)
    made = None
    if ops:
        from opencde.ifcgraph.ops import run

        made = run(model, ops, proposer=proposer)
    already = 0
    if made is None or made["failed"] is None:
        for index, change in enumerate(changes):
            try:
                if made is not None and _already(model, change):
                    already += 1
                    continue
                touched.append(apply_one(model, change))
            except CannotApply as exc:
                if len(problems) < MAX_PROBLEMS:
                    problems.append({"change": index, "error": str(exc)[:300]})
        _restore(model, held, problems)
    model.write(str(out))
    summary = {
        "applied": len(touched) + already,
        "touched": sorted(set(touched)),
        "problems": problems[:MAX_PROBLEMS],
        "count": len(changes),
    }
    if made is not None:
        summary["ops"] = made
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="opencde-apply")
    parser.add_argument("base", type=Path)
    parser.add_argument("changes", type=Path)
    parser.add_argument("out", type=Path, nargs="?")
    parser.add_argument("--read", action="store_true")
    parser.add_argument("--memory-mb", type=int, default=0)
    parser.add_argument("--proposer", default="")
    args = parser.parse_args(argv)
    if args.memory_mb:
        limit_memory(args.memory_mb)
    keep_stdout_for_the_answer()
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
    try:
        change_set = json.loads(args.changes.read_text(encoding="utf-8"))
        if args.read:
            summary: Any = {"values": read_values(args.base, list(change_set["changes"]))}
        elif args.out is None:
            raise ValueError("an out file is needed unless --read")
        else:
            summary = apply_all(
                args.base,
                list(change_set["changes"]),
                args.out,
                ops=change_set.get("ops"),
                keep_theirs=change_set.get("keep_theirs"),
                proposer=args.proposer,
            )
    except Exception as exc:  # the caller reads the last line of stderr
        sys.stderr.write(json.dumps({"error": f"{type(exc).__name__}: {exc}"[:300]}) + "\n")
        return 2
    sys.stdout.write(json.dumps(summary, separators=(",", ":")) + "\n")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
