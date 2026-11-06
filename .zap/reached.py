# This file was generated with the assistance of an AI coding tool.
"""Read the server's access log after the signed-in scan: a scan that lost its sign-in proves little.

Prints how the requests were answered, per area, and fails unless the session and tokens worked and went on working:

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
    ("GET", "/bcf/2.1/projects", "200"),
    ("GET", "/admin/api/users", "200"),
)
# Attacks are refused in many ways, but never with "who are you?" as long as the token holds.
TOKEN_AREAS = ("/bcf/3.0", "/bcf/2.1", "/documents/1.0", "/admin/api")
MOST_REFUSED = 0.1


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

    problems = [f"never got {' '.join(answer)}" for answer in MUST_ANSWER if answer not in seen]
    for area in TOKEN_AREAS:
        total = sum(count for (name, _), count in areas.items() if name == area)
        refused = areas[(area, "401")]
        if refused > MOST_REFUSED * total:
            problems.append(f"{area} answered 401 to {refused} of {total}, so the token stopped working")
    pages = {
        status: count for (name, status), count in areas.items() if name.startswith("/admin/") and name != "/admin/api"
    }
    sent_to_sign_in = pages.get("302", 0)
    if sent_to_sign_in > MOST_REFUSED * sum(pages.values()):
        problems.append(
            f"was sent to the sign-in {sent_to_sign_in} times of {sum(pages.values())}, so the session ended"
        )
    for problem in problems:
        print(f"The scan {problem}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
