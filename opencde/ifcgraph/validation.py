# This file was generated with the assistance of an AI coding tool.
"""Whether a file keeps to the IFC standard: ``python -m opencde.ifcgraph.validation FILE [--against OTHER]``.

A graph database has no schema to hold a change to, so a property or a relationship changed in the graph can make a file
that breaks the standard. IfcOpenShell's validator checks a file against the schema compiled from IFC's EXPRESS: the type
and number of every attribute, enumerations, the cardinality of inverse attributes, the form and uniqueness of GlobalIds,
and the schema's WHERE rules and global rules. It also says what its parser found wrong on the way in, such as a
reference to an instance the file does not have, which is what deleting a node that a block refers to would leave.

Files in use break rules already (12 of 26 samples, with up to 5,711 issues), which is no fault of the graph's. So what
counts for a file written from the graph is what it has that the file it came from does not. The two have the same ids, so
an issue can be told by its instance and its message. See ADR 0011.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from opencde.ifcgraph.worker import keep_stdout_for_the_answer, limit_memory

MAX_LISTED = 50
_INSTANCE_ID = re.compile(r"#(\d+)")
# The parser's complaints end with the line of the file, as it is written: layout and the spelling of REALs do not count.
_LINE_OF_THE_FILE = "\n\n"


class CannotValidate(RuntimeError):
    """The validator could not be run on this file, so nothing is known about it."""


def _instance_of(statement: Mapping[str, Any]) -> int | None:
    instance = statement.get("instance")
    if instance is None:
        return None
    if hasattr(instance, "id"):
        return instance.id()
    found = _INSTANCE_ID.search(str(instance))
    return int(found.group(1)) if found else None


def issues_of(path: Path) -> list[dict[str, Any]]:
    """Every issue in a file, in a form that can be compared and written as JSON."""
    try:
        import ifcopenshell.validate

        logger = ifcopenshell.validate.json_logger()
        ifcopenshell.validate.validate(str(path), logger, express_rules=True)
    except (ImportError, OSError, RuntimeError) as exc:
        raise CannotValidate(f"{type(exc).__name__}: {str(exc)[:300]}") from exc
    return [
        {
            "kind": statement.get("type"),
            "instance": _instance_of(statement),
            "attribute": None if statement.get("attribute") is None else str(statement["attribute"]),
            "message": statement["message"],
        }
        for statement in logger.statements
    ]


def _key(issue: dict[str, Any]) -> tuple[Any, ...]:
    return issue["kind"], issue["instance"], issue["attribute"], issue["message"].split(_LINE_OF_THE_FILE, 1)[0]


def compare_issues(ours: list[dict[str, Any]], theirs: list[dict[str, Any]]) -> dict[str, Any]:
    """What one file has that another does not, and how many issues the other had that are gone."""
    their_keys = {_key(issue) for issue in theirs}
    our_keys = {_key(issue) for issue in ours}
    new = [issue for issue in ours if _key(issue) not in their_keys]
    return {
        "issues": len(ours),
        "new_count": len(new),
        "new": new[:MAX_LISTED],
        "gone": len(their_keys - our_keys),
    }


def main(argv: list[str] | None = None) -> int:
    """Exit 0 for a file with no issues, or none the other file lacks, 1 for one with, 2 for what could not be validated.
    The answer is JSON on stdout."""
    parser = argparse.ArgumentParser(prog="opencde-ifcgraph-validation")
    parser.add_argument("file", type=Path)
    parser.add_argument("--against", type=Path)
    parser.add_argument("--memory-mb", type=int, default=0)
    args = parser.parse_args(argv)
    if args.memory_mb:
        limit_memory(args.memory_mb)
    try:
        ours = issues_of(args.file)
        theirs = issues_of(args.against) if args.against else []
    except CannotValidate as exc:
        sys.stderr.write(json.dumps({"error": str(exc)}) + "\n")
        return 2
    answer = compare_issues(ours, theirs)
    sys.stdout.write(json.dumps(answer, indent=2) + "\n")
    sys.stdout.flush()
    return 1 if answer["new_count"] else 0


if __name__ == "__main__":
    keep_stdout_for_the_answer()
    sys.exit(main())
