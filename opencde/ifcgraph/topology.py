# This file was generated with the assistance of an AI coding tool.
"""The rooms of each storey, found from its walls with Dataspatium's own code, in a worker process (F36 a).

The owner's decision F36 a has the server make the client's light room check: Dataspatium's ``_ifc_topology``, which
the copy of the app's code in ``ops.py`` holds beside the change set, since ``create_spaces`` builds on it. Per
storey, a wall's centre line is its ``Axis`` representation, which the app's ``create_wall`` writes, or else the long
axis of its body's footprint, which the geometry kernel builds; the ends are snapped to each other within a
tolerance, and shapely nodes the lines and polygonizes them into rooms of at least 0.5 m² and 0.5 m across. A storey
gets its rooms with their area, perimeter, walls and neighbours, the external walls with the compass sector they
face (from the map conversion before TrueNorth, else the model's +y), the open wall ends with their walls, whether it
is closed (a room and no open end) and the walls that could not be read. They are the report's own section, which
never stops anything (F38 a: the rooms only warn).

    python -m opencde.ifcgraph.topology FILE [--memory-mb N]

Answers with one JSON document on stdout, exit code 0: the section (:func:`section`), with the walls named by
GlobalId, at most ``MAX_STOREYS`` storeys, ``MAX_ROOMS`` rooms a storey and ``MAX_LISTED`` entries in every other
list, and ``cut`` saying when there were more; or ``{"error"}`` with the copy's own words, such as its limit of
2,000 walls, or else with the class of what was raised alone, since IfcOpenShell's words may quote the file. The
caller sets the memory and time limits.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from ifc_db.worker import keep_stdout_for_the_answer, limit_memory

from opencde.ifcgraph.ops import DataspatiumError, _ifc_topology

MAX_STOREYS = 100
MAX_ROOMS = 500  # a storey
MAX_LISTED = 200  # the walls and neighbours of a room; the external walls, open ends and unread walls of a storey
MAX_TEXT = 200
MAX_ERROR = 300


def _text(value: Any) -> str | None:
    return value[:MAX_TEXT] if isinstance(value, str) else None


def section(model: Any, topology: list[dict[str, Any]]) -> dict[str, Any]:
    """The report's section ``rooms`` from the copy's answer: a storey per entry, in the order of elevation, with the
    walls named by GlobalId, the names cut at ``MAX_TEXT`` characters and the lists at their limits, and ``cut``
    saying whether a list was."""
    cut = False

    def first(items: Any, limit: int = MAX_LISTED) -> list[Any]:
        nonlocal cut
        listed = list(items or ())
        cut = cut or len(listed) > limit
        return listed[:limit]

    def global_ids(step_ids: Any) -> list[str]:
        return first(sorted({str(model.by_id(int(step)).GlobalId) for step in step_ids}))

    storeys = [
        {
            "storey": _text(found["storey"]),
            "elevation": float(found["elevation"]),
            "closed": bool(found["closed"]),
            "rooms": [
                {
                    "index": int(room["index"]),
                    "area": float(room["area"]),
                    "perimeter": float(room["perimeter"]),
                    "walls": global_ids(room["walls"]),
                    "neighbours": [int(index) for index in first(room["neighbours"])],
                }
                for room in first(found["rooms"], MAX_ROOMS)
            ],
            "external": [
                {
                    "global_id": str(wall["guid"]),
                    "name": _text(wall["name"]),
                    "facing": str(wall["facing"]),
                    "length": float(wall["length"]),
                }
                for wall in first(found["external"])
            ],
            "dangles": [[float(x), float(y)] for x, y in first(found["dangles"])],
            "dangling_walls": [str(guid) for guid in first(found["dangling"])],
            "walls": int(found["walls"]),
            "unread": int(found["unread"]),
            "unread_walls": [str(guid) for guid in first(found["unread_walls"]) if guid],
            "tolerance": float(found["tolerance"]),
            "north": str(found["north"]),
        }
        for found in first(topology, MAX_STOREYS)
    ]
    return {"storeys": storeys, "cut": cut}


def answer(path: Path) -> dict[str, Any]:
    import ifcopenshell

    model = ifcopenshell.open(str(path))
    return section(model, _ifc_topology(model))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="opencde-topology")
    parser.add_argument("ifc", type=Path)
    parser.add_argument("--memory-mb", type=int, default=0)
    args = parser.parse_args(argv)
    if args.memory_mb:
        limit_memory(args.memory_mb)
    try:
        result = answer(args.ifc)
    except DataspatiumError as exc:  # the copy's own words, such as its limit on walls
        result = {"error": str(exc)[:MAX_ERROR]}
    except Exception as exc:  # IfcOpenShell's words may quote the file: only what was raised
        result = {"error": type(exc).__name__}
    sys.stdout.write(json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    keep_stdout_for_the_answer()
    sys.exit(main())
