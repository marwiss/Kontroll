# This file was generated with the assistance of an AI coding tool.
"""The conversion worker: ``python -m opencde.ifcgraph.worker IFC OUT [--memory-mb N] [--max-entities N]
[--include-geometry] [--lossless]``.

IfcOpenShell parses untrusted files, so it runs here, in its own process:
a crash, a hang or a memory explosion ends this process, not the server.
The parent enforces the time limit; the memory limit is applied here where
the platform supports it (POSIX ``RLIMIT_AS``).
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
from pathlib import Path
from typing import Any


def limit_memory(megabytes: int) -> None:
    try:
        resource: Any = importlib.import_module("resource")  # POSIX only
    except ImportError:  # Windows
        return
    limit = megabytes * 1024 * 1024
    _soft, hard = resource.getrlimit(resource.RLIMIT_AS)
    if hard != resource.RLIM_INFINITY:
        limit = min(limit, hard)
    resource.setrlimit(resource.RLIMIT_AS, (limit, hard))


def keep_stdout_for_the_answer() -> None:
    """Send what anything else writes to stdout to stderr instead. The geometry kernel and the parser write to it from
    C++, past ``sys.stdout`` and at times of their own, and the answer on stdout has to stand alone to be read."""
    answer = os.fdopen(os.dup(1), "w", encoding="utf-8")
    os.dup2(2, 1)
    sys.stdout = answer


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="opencde-ifcgraph-worker")
    parser.add_argument("ifc", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--memory-mb", type=int, default=0)
    parser.add_argument("--max-entities", type=int, default=5_000_000)
    parser.add_argument("--include-geometry", action="store_true")
    parser.add_argument("--lossless", action="store_true")
    args = parser.parse_args(argv)
    if args.memory_mb:
        limit_memory(args.memory_mb)

    from opencde.ifcgraph.convert import ConversionError, write_jsonl

    try:
        header = write_jsonl(
            args.ifc,
            args.out,
            lossless=args.lossless,
            include_geometry=args.include_geometry,
            max_entities=args.max_entities,
        )
    except ConversionError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 3
    except Exception as exc:
        print(json.dumps({"error": f"{type(exc).__name__}: {str(exc)[:500]}"}), file=sys.stderr)
        return 4
    print(json.dumps(header))
    return 0


if __name__ == "__main__":
    sys.exit(main())
