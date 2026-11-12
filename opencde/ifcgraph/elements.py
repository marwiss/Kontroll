# This file was generated with the assistance of an AI coding tool.
"""The element a finding names, read from the file in a worker process.

    python -m opencde.ifcgraph.elements FILE STEPS [--memory-mb N]

``STEPS`` is a JSON list of STEP ids, which the server wrote. Answers with one JSON document on stdout,
``{"elements": {"<step id>": {"ifc_class": …, "root_global_id": …}}}``, for every id that is an instance of the file:
its class, and the GlobalId of the nearest rooted entity that reaches it, its own when it is one. A rooted entity
reaches an instance as IFC-LPG's paths do (``ifc_db.paths``): forward through explicit attributes and backward
through inverse ones, within ``MAX_STEPS`` steps. Of the nearest, the one is taken whose path comes first as IFC-LPG
orders them: forward steps before inverse ones, the attribute names in alphabetical order, the lowest position, then
the lowest GlobalId. IFC-LPG orders an inverse set by its members' content in the graph; here every inverse step counts
as position 0, so that only the GlobalId tells such paths apart. ``root_global_id`` is None for an instance that none
reaches, or whose search would take more than ``MAX_VISITED`` steps, or more than ``MAX_SEARCHED`` with those of the
instances before it, so that a file with many findings is answered in time. Exit code 0 is an
answer, 2 an error with a JSON line on stderr. The caller sets the memory and time limits.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from ifc_db.paths import MAX_STEPS
from ifc_db.validation import MAX_REPORTED
from ifc_db.worker import keep_stdout_for_the_answer, limit_memory

MAX_VISITED = 20_000  # steps searched back from one instance before it is left without its element
MAX_SEARCHED = 1_000_000  # and from all of them together, each kept in memory once read
MAX_TEXT = 100  # a GlobalId is what the file says
MAX_ERROR = 300
Key = tuple[Any, ...]  # the steps of a path from its rooted entity, each (inverse, attribute, positions)


def _global_id(instance: Any) -> str | None:
    """The GlobalId of a rooted entity; None for anything else, or for one too broken to read."""
    try:
        value = instance.GlobalId if instance.is_a("IfcRoot") else None
    except (AttributeError, RuntimeError):
        return None
    return value[:MAX_TEXT] if isinstance(value, str) and value else None


def _attributes(instance: Any) -> Iterator[tuple[str, Any]]:
    """The attributes of an instance by name; a derived one is None. One that cannot be read is left out."""
    for index in range(len(instance)):
        try:
            yield instance.attribute_name(index), instance[index]
        except (AttributeError, RuntimeError, IndexError):
            continue


def _references(value: Any, positions: tuple[int, ...] = ()) -> Iterator[tuple[tuple[int, ...], Any]]:
    """The instances a value refers to, each with its positions in the value's lists. A typed value, which has no
    STEP id, refers to nothing."""
    if isinstance(value, (tuple, list)):
        for index, item in enumerate(value):
            yield from _references(item, (*positions, index))
    elif hasattr(value, "is_a") and value.id():
        yield positions, value


def _keyword(instance: Any) -> bytes:
    return instance.is_a().upper().encode("ascii")


def _last_steps(model: Any, schema: Any, item: Any) -> Iterator[tuple[tuple[Any, ...], Any]]:
    """Where a path can take its last step to ``item`` from: an instance that refers to it, forward, and one that it
    refers to through an attribute that the other's class has an inverse attribute for."""
    for source in model.get_inverse(item):
        for name, value in _attributes(source):
            for positions, target in _references(value):
                if target.id() == item.id():
                    yield (0, name, positions or (0,)), source
    keyword = _keyword(item)
    for name, value in _attributes(item):
        for _positions, target in _references(value):
            for inverse in schema.refers_back(keyword, name, _keyword(target)):
                yield (1, inverse, (0,)), target


class Search:
    """The searches in one file, which share what they learn of each instance and ``MAX_SEARCHED`` steps."""

    def __init__(self, model: Any, schema: Any) -> None:
        self.model = model
        self.schema = schema
        self.left = MAX_SEARCHED
        self._known: dict[int, tuple[list[tuple[Key, str]], list[tuple[Key, Any]]]] = {}

    def _last_steps(self, item: Any) -> tuple[list[tuple[Key, str]], list[tuple[Key, Any]]]:
        """Where a path takes its last step to ``item`` from: the rooted entities by GlobalId, and the rest. A shared
        instance, such as a representation context that every shape refers to, is read once."""
        known = self._known.get(item.id())
        if known is None:
            known = self._known[item.id()] = ([], [])
            for step, source in _last_steps(self.model, self.schema, item):
                self.left -= 1
                global_id = _global_id(source)
                if global_id is not None:
                    known[0].append((step, global_id))
                else:
                    known[1].append((step, source))
        return known

    def root_of(self, instance: Any) -> str | None:
        """The GlobalId of the nearest rooted entity that reaches ``instance``, breadth first and backwards. The rest
        of a level is only searched when no rooted entity is in it, so that a shared instance costs little."""
        own = _global_id(instance)
        if own is not None:
            return own
        start = self.left
        best: dict[int, Key] = {instance.id(): ()}
        frontier = [instance]
        for _ in range(MAX_STEPS):
            if self.left <= 0 or start - self.left > MAX_VISITED:
                return None
            levels = [(best[item.id()], self._last_steps(item)) for item in frontier]
            rooted = [((*step, *tail), global_id) for tail, (named, _) in levels for step, global_id in named]
            if rooted:
                return min(rooted)[1]
            found: dict[int, tuple[Key, Any]] = {}
            for tail, (_, others) in levels:
                self.left -= len(others)
                for step, source in others:
                    key = (*step, *tail)
                    if source.id() not in best and (source.id() not in found or key < found[source.id()][0]):
                        found[source.id()] = (key, source)
            if not found:
                return None
            best.update((step_id, key) for step_id, (key, _source) in found.items())
            frontier = [source for _key, source in found.values()]
        return None


def answer(path: Path, steps: list[int]) -> dict[str, Any]:
    import ifcopenshell
    from ifc_db.schema import Schema

    model = ifcopenshell.open(str(path))
    search = Search(model, Schema(model.schema_identifier))
    elements: dict[str, dict[str, str | None]] = {}
    for step in steps[:MAX_REPORTED]:
        try:
            instance = model.by_id(step)
        except RuntimeError:  # no such instance in the file
            continue
        elements[str(step)] = {"ifc_class": instance.is_a(), "root_global_id": search.root_of(instance)}
    return {"elements": elements}


def steps_of(path: Path) -> list[int]:
    """The STEP ids the server asks for, each once, in order."""
    listed = json.loads(path.read_text(encoding="utf-8"))
    return sorted({step for step in listed if isinstance(step, int) and not isinstance(step, bool) and step > 0})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="opencde-elements")
    parser.add_argument("ifc", type=Path)
    parser.add_argument("steps", type=Path, help="a JSON list of STEP ids")
    parser.add_argument("--memory-mb", type=int, default=0)
    args = parser.parse_args(argv)
    if args.memory_mb:
        limit_memory(args.memory_mb)
    try:
        result = answer(args.ifc, steps_of(args.steps))
    except Exception as exc:
        sys.stderr.write(json.dumps({"error": f"{type(exc).__name__}: {exc}"[:MAX_ERROR]}) + "\n")
        return 2
    sys.stdout.write(json.dumps(result, separators=(",", ":")) + "\n")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    keep_stdout_for_the_answer()
    sys.exit(main())
