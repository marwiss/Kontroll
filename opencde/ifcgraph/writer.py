# This file was generated with the assistance of an AI coding tool.
"""Write a file back from what the graph holds: ``python -m opencde.ifcgraph.writer RECORDS OUT [--memory-mb N]``.

``RECORDS`` holds one JSON object per line: first ``{"schema", "ifc_header"}``, then one per instance, in the order the
file should have. That is ``{"step", "props", "references"}`` for a node, with ``references`` as ``[relationship type,
position, target]``, or ``{"step", "line"}`` for an instance that was kept as text, with its bytes as Latin-1.
A line is written as it is read, so the file's size does not decide how much memory this takes.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from opencde.ifcgraph.lossless import decode_header, decode_instance
from opencde.ifcgraph.schema import Schema
from opencde.ifcgraph.step import StepError, statement_text, write_exchange
from opencde.ifcgraph.worker import limit_memory


def _instance_lines(lines: Iterator[str], schema: Schema) -> Iterator[bytes]:
    for line in lines:
        record = json.loads(line)
        if "line" in record:
            yield record["line"].encode("latin-1") + b"\n"
            continue
        properties: dict[str, Any] = record["props"]
        keyword = str(properties["ifc_class"]).upper().encode("ascii")
        parameters = decode_instance(keyword, properties, record["references"], schema)
        yield b"#%d=%s;\n" % (record["step"], statement_text(keyword, parameters))


def write_records(records: Path, out: Path) -> None:
    """Turn a records file into an exchange file."""
    with records.open(encoding="utf-8") as lines, out.open("wb") as handle:
        first = json.loads(next(lines))
        schema = Schema(first["schema"])
        write_exchange(handle, decode_header(first["ifc_header"]), _instance_lines(lines, schema))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="opencde-ifcgraph-writer")
    parser.add_argument("records", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--memory-mb", type=int, default=0)
    args = parser.parse_args(argv)
    if args.memory_mb:
        limit_memory(args.memory_mb)
    try:
        write_records(args.records, args.out)
    except (StepError, ValueError, KeyError, StopIteration, OSError) as exc:
        sys.stderr.write(json.dumps({"error": f"{type(exc).__name__}: {str(exc)[:500]}"}) + "\n")
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
