# This file was generated with the assistance of an AI coding tool.
"""The clash check between two IFC files, in a process of its own (ADR 0019).

``python -m opencde.ifcgraph.clash A.ifc B.ifc --mode intersection --tolerance 0.001`` lets IfcClash (IfcOpenShell's
clash library) compare the elements of the two files and writes one JSON document to stdout: the counts, the time
taken and the clashes, each with both elements (STEP id, GlobalId, class, name, storey), its kind, the depth or
distance in metres and the point where it was measured, in the form Dataspatium's own clash core writes. Nothing else
reaches stdout; the geometry kernel's chatter goes to stderr. Exit code 0 is an answer, 2 an error with a JSON line on
stderr. The caller sets the memory limit and the time limit.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

from ifc_lpg.worker import keep_stdout_for_the_answer, limit_memory

MODES = ("intersection", "clearance")
# IfcClash's types, as Dataspatium names them: everything that goes into something is an intersection.
KINDS = {"protrusion": "intersection", "pierce": "intersection", "collision": "intersection", "clearance": "clearance"}
# Elements without a body of their own, left out of a check as Dataspatium leaves them out.
EXCLUDED = ("IfcOpeningElement", "IfcOpeningStandardCase", "IfcVirtualElement", "IfcAnnotation")


def _selected(ifc: Any, types: list[str]) -> set[Any]:
    """The elements of a file a side of the check covers: the listed classes, or every element with a body."""
    import ifcopenshell.util.selector

    if types:
        return set(ifcopenshell.util.selector.filter_elements(ifc, ", ".join(types)))
    elements = set(ifc.by_type("IfcElement")) - set(ifc.by_type("IfcFeatureElement"))
    return {e for e in elements if not e.is_a("IfcVirtualElement")}


def _side(ifc: Any, guid: str, document: dict[str, Any]) -> dict[str, Any]:
    """One element of a clash: where it comes from, its STEP id, GlobalId, class, name and storey."""
    import ifcopenshell.util.element

    element = ifc.by_guid(guid)
    storey = ifcopenshell.util.element.get_container(element)
    return {
        **document,
        "id": element.id(),
        "guid": guid,
        "type": element.is_a(),
        "name": element.Name,
        "storey": storey.Name if storey is not None and storey.is_a("IfcBuildingStorey") else None,
    }


def check(
    a: Path,
    b: Path,
    *,
    mode: str,
    tolerance: float,
    clearance: float,
    types_a: list[str],
    types_b: list[str],
    max_clashes: int,
    document_a: dict[str, Any] | None = None,
    document_b: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run IfcClash over the two files and shape its results."""
    from ifcclash.ifcclash import Clasher, ClashSet, ClashSettings, ClashSource

    if mode not in MODES:
        raise ValueError(f"mode must be one of {', '.join(MODES)}")
    settings = ClashSettings()
    settings.logger = logging.getLogger("ifcclash")
    clasher = Clasher(settings)
    sources: list[ClashSource] = []
    for path, types in ((a, types_a), (b, types_b)):
        source: ClashSource = {"file": str(path)}
        if types:
            source["mode"] = "i"
            source["selector"] = ", ".join(types)
        sources.append(source)
    clash_set: ClashSet = {
        "name": "a-b",
        "a": [sources[0]],
        "b": [sources[1]],
        "mode": "intersection" if mode == "intersection" else "clearance",
        "check_all": True,
        "tolerance": tolerance,
        "clearance": clearance,
        "allow_touching": False,
    }
    started = time.monotonic()
    clasher.clash_sets = [clash_set]
    clasher.clash()
    seconds = round(time.monotonic() - started, 3)

    ifc_a, ifc_b = clasher.ifcs[str(a)], clasher.ifcs[str(b)]
    selected_a, selected_b = _selected(ifc_a, types_a), _selected(ifc_b, types_b)
    with_shape_a, with_shape_b = len(clasher.groups["a"]["elements"]), len(clasher.groups["b"]["elements"])
    document_a, document_b = document_a or {}, document_b or {}

    def in_a(guid: str) -> bool:
        """Whether a GlobalId belongs to file A; IfcClash may hand a pair back with the sides swapped."""
        try:
            ifc_a.by_guid(guid)
        except RuntimeError:
            return False
        return True

    clashes: list[dict[str, Any]] = []
    truncated = False
    for result in clash_set.get("clashes", {}).values():
        if result["a_ifc_class"] in EXCLUDED or result["b_ifc_class"] in EXCLUDED:
            continue
        if len(clashes) >= max_clashes:
            truncated = True
            break
        kind = KINDS.get(result["type"], "intersection")
        point = [round((p + q) / 2, 4) for p, q in zip(result["p1"], result["p2"], strict=True)]
        distance = float(result["distance"])
        first, second = result["a_global_id"], result["b_global_id"]
        if not in_a(first):
            first, second = second, first
        clashes.append(
            {
                "a": _side(ifc_a, first, document_a),
                "b": _side(ifc_b, second, document_b),
                "kind": kind,
                "depth": round(distance, 4) if kind == "intersection" else None,
                "distance": round(distance, 4) if kind == "clearance" else 0.0,
                "point": point,
                "extent": None,
            }
        )
    return {
        "mode": mode,
        "tolerance": tolerance,
        "clearance": clearance,
        "set_a": len(selected_a),
        "set_b": len(selected_b),
        "missing": (len(selected_a) - with_shape_a) + (len(selected_b) - with_shape_b),
        "seconds": seconds,
        "count": len(clashes),
        "truncated": truncated,
        "clashes": clashes,
    }


def _types(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="opencde-clash")
    parser.add_argument("a", type=Path)
    parser.add_argument("b", type=Path)
    parser.add_argument("--mode", choices=MODES, default="intersection")
    parser.add_argument("--tolerance", type=float, default=0.001)
    parser.add_argument("--clearance", type=float, default=0.05)
    parser.add_argument("--types-a", type=_types, default=[])
    parser.add_argument("--types-b", type=_types, default=[])
    parser.add_argument("--max-clashes", type=int, default=10_000)
    parser.add_argument("--memory-mb", type=int, default=0)
    args = parser.parse_args(argv)
    if args.memory_mb:
        limit_memory(args.memory_mb)
    keep_stdout_for_the_answer()
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
    try:
        report = check(
            args.a,
            args.b,
            mode=args.mode,
            tolerance=args.tolerance,
            clearance=args.clearance,
            types_a=args.types_a,
            types_b=args.types_b,
            max_clashes=args.max_clashes,
        )
    except Exception as exc:  # the caller reads the last line of stderr
        sys.stderr.write(json.dumps({"error": f"{type(exc).__name__}: {exc}"[:300]}) + "\n")
        return 2
    sys.stdout.write(json.dumps(report, separators=(",", ":")) + "\n")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
