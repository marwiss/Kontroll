# This file was generated with the assistance of an AI coding tool.
"""Which teams' parts of the model a change set touches (F11 b, F19 a), in a worker process.

The objects a change set touches are those its changes name by GlobalId, and for a change named by STEP id the nearest
objects that refer to the instance. A team's part is what the specifications of its IDS document apply to, as
IfcTester finds it; it is looked up in the base file and in the changed one, so that a change that moves an element
into a part or out of it touches the part too. The answer is the positions of the IDS files whose part the objects
meet, and the IDS files that could not be read.

    python -m opencde.ifcgraph.parts BASE CHANGED CHANGES.json IDS... [--memory-mb N]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from ifc_lpg.worker import keep_stdout_for_the_answer, limit_memory

INVERSE_DEPTH = 4  # how far back from an instance named by its STEP id the objects that refer to it are looked for
MAX_ERROR = 300


def owning_objects(model: Any, entity: Any, depth: int = INVERSE_DEPTH) -> set[str]:
    """The GlobalIds of the nearest objects that refer to ``entity``, a few steps back; its own when it is one."""
    found: set[str] = set()
    seen: set[int] = set()
    frontier = [entity]
    for _ in range(depth + 1):
        next_frontier = []
        for item in frontier:
            if item.id() in seen:
                continue
            seen.add(item.id())
            if item.is_a("IfcObjectDefinition"):
                found.add(item.GlobalId)
                continue
            next_frontier.extend(model.get_inverse(item))
        if found or not next_frontier:
            break
        frontier = next_frontier
    return found


def touched(models: list[Any], changes: list[dict[str, Any]]) -> set[str]:
    """The objects the changes touch, in whichever of the files has the instance a change names."""
    guids: set[str] = set()
    for change in changes:
        if change.get("guid"):
            guids.add(str(change["guid"]))
            continue
        if change.get("step_id") is None:
            continue
        for model in models:
            try:
                guids.update(owning_objects(model, model.by_id(int(change["step_id"]))))
            except RuntimeError:
                continue
    return guids


def part(model: Any, ids_path: Path) -> set[str]:
    """The GlobalIds of what the specifications of the IDS file apply to in the model."""
    from ifc_lpg.ids import read_ids

    requirements = read_ids(ids_path.read_bytes())
    requirements.validate(model)
    return {
        str(element.GlobalId)
        for specification in requirements.specifications
        for element in specification.applicable_entities
        if getattr(element, "GlobalId", None)
    }


def answer(base: Path, changed: Path, changes: list[dict[str, Any]], sources: list[Path]) -> dict[str, Any]:
    import ifcopenshell

    models = [ifcopenshell.open(str(base)), ifcopenshell.open(str(changed))]
    objects = touched(models, changes)
    met: list[int] = []
    errors: list[dict[str, Any]] = []
    for index, source in enumerate(sources):
        try:
            if any(objects & part(model, source) for model in models):
                met.append(index)
        except Exception as exc:  # an IDS that cannot be read touches nothing, and says so
            errors.append({"ids": index, "error": f"{type(exc).__name__}: {exc}"[:MAX_ERROR]})
    return {"objects": len(objects), "teams": met, "errors": errors}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="opencde-parts")
    parser.add_argument("base", type=Path)
    parser.add_argument("changed", type=Path)
    parser.add_argument("changes", type=Path)
    parser.add_argument("ids", type=Path, nargs="*")
    parser.add_argument("--memory-mb", type=int, default=0)
    args = parser.parse_args(argv)
    if args.memory_mb:
        limit_memory(args.memory_mb)
    try:
        changes = list(json.loads(args.changes.read_text(encoding="utf-8")).get("changes") or [])
        result = answer(args.base, args.changed, changes, args.ids)
    except Exception as exc:
        sys.stderr.write(json.dumps({"error": f"{type(exc).__name__}: {exc}"[:MAX_ERROR]}) + "\n")
        return 2
    sys.stdout.write(json.dumps(result) + "\n")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    keep_stdout_for_the_answer()
    sys.exit(main())
