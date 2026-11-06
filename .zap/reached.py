# This file was generated with the assistance of an AI coding tool.
"""Read the server's access log after the signed-in scan: a scan that never got past the sign-in proves nothing.

Prints how the requests were answered, per area, and fails unless the scan's own session and tokens worked:

    docker compose -f compose.yaml -f compose.dev.yaml logs api | uv run python .zap/reached.py
"""

from __future__ import annotations

import re
import sys
from collections import Counter

ANSWER = re.compile(r'"(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS) (/[^ ?"]*)[^"]* HTTP/[\d.]+" (\d{3})')
# Only someone signed in gets these, and each by its own means: the session, the manager's token, the admin token.
MUST_ANSWER = (
    ("GET", "/admin/users", "200"),
    ("GET", "/bcf/3.0/projects", "200"),
    ("GET", "/admin/api/users", "200"),
)


def main() -> int:
    seen: set[tuple[str, str, str]] = set()
    areas: Counter[tuple[str, str]] = Counter()
    for line in sys.stdin:
        match = ANSWER.search(line)
        if match is None:
            continue
        method, path, status = match.groups()
        seen.add((method, path, status))
        area = "/" + "/".join(path.split("/")[1:3])
        areas[(area, status)] += 1
    for (area, status), count in sorted(areas.items()):
        print(f"{count:7} {status} {area}")
    missing = [" ".join(answer) for answer in MUST_ANSWER if answer not in seen]
    if missing:
        print(f"The scan never got: {', '.join(missing)}")
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
