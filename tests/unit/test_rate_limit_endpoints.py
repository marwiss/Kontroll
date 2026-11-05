# This file was generated with the assistance of an AI coding tool.
"""Every rate-limited endpoint gives slowapi a Response to write its headers into.

With ``headers_enabled=True`` slowapi needs either the returned Response or a
``response: Response`` parameter; an endpoint returning a dict without one fails
with a 500 as soon as the limiter is on, which the test settings never are. A
real deployment found that on 3.8.2 POST Document, hence this static check.
"""

import ast
from pathlib import Path

from tests.conftest import REPO_ROOT


def _is_limit_decorator(node: ast.expr) -> bool:
    call = node if isinstance(node, ast.Call) else None
    target = call.func if call else node
    return isinstance(target, ast.Attribute) and target.attr == "limit" and getattr(target.value, "id", "") == "limiter"


def _returns_response(function: ast.AsyncFunctionDef | ast.FunctionDef) -> bool:
    annotation = function.returns
    name = annotation.id if isinstance(annotation, ast.Name) else getattr(annotation, "attr", "")
    return name.endswith("Response")


def test_rate_limited_endpoints_can_carry_the_limit_headers() -> None:
    offenders: list[str] = []
    for path in sorted(Path(REPO_ROOT, "opencde").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef):
                continue
            if not any(_is_limit_decorator(decorator) for decorator in node.decorator_list):
                continue
            parameters = {arg.arg for arg in node.args.args + node.args.kwonlyargs}
            if "response" not in parameters and not _returns_response(node):
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno} {node.name}")
    assert offenders == [], "add `response: Response` or return a Response: " + ", ".join(offenders)
