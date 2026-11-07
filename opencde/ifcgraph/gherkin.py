# This file was generated with the assistance of an AI coding tool.
"""buildingSMART's ifc-gherkin-rules on one file: ``python -m opencde.ifcgraph.gherkin FILE --env DIR``.

ADR 0012. Runs behave in the environment ``gherkin_install.py`` made, with every rule that is not disabled, as the rule
set's own tests run a file, and reads the outcomes from its JSON report. An outcome with the severity error or warning
is an issue; the GlobalId of its instance is read from the file with Kontroll's own STEP reader. A rule that raised an
exception, rather than finding something, is listed apart, since its verdict is unknown. The answer is JSON on stdout in
the shape of ``validation.py``'s report, so that the service can put both checks in one report.

This process limits its own memory, which behave inherits, and stops behave at its own time limit, before the service's.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess  # nosec B404 - runs behave in the pinned environment
import sys
import tempfile
from pathlib import Path
from typing import Any

from opencde.ifcgraph.gherkin_install import MANIFEST, python_of
from opencde.ifcgraph.validation import MAX_MESSAGE, MAX_REPORTED
from opencde.ifcgraph.worker import keep_stdout_for_the_answer, limit_memory

# A step that fails because the rule found something is recorded with no exception type; only real ones are listed.
_NO_EXCEPTION = ("NoneType", "", None)


class CannotRun(RuntimeError):
    """The rules could not be run on this file, so nothing is known of what they would find."""


def manifest_of(env: Path) -> dict[str, str]:
    try:
        return json.loads((env / MANIFEST).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CannotRun(f"no environment for the rules in {env}") from exc


def run_rules(env: Path, path: Path, report: Path, timeout: float) -> None:
    command = [
        str(python_of(env / "venv")), "-m", "behave", "--tags=-disabled",
        "--define", f"input={path}",
        # As the rule set's own tests run a file (main.run in testing mode); the verdicts were checked that way.
        "--define", "execution_mode=ExecutionMode.TESTING",
        "--define", "max_outcomes_per_rule=0",
        "--define", "purepythonparser=False",
        "-f", "outcome_embedding_json", "-o", str(report),
    ]  # fmt: skip
    try:
        subprocess.run(  # noqa: S603  # nosec B603 - the pinned environment's interpreter, fixed arguments
            command, cwd=env / "run", capture_output=True, timeout=timeout, check=False, env=_clean_environment()
        )
    except subprocess.TimeoutExpired as exc:
        raise CannotRun(f"the rules took longer than {timeout:.0f} s") from exc


def _clean_environment() -> dict[str, str]:
    """The rules see neither the server's settings nor its secrets."""
    keep = ("PATH", "SYSTEMROOT", "TEMP", "TMP", "TMPDIR", "HOME", "LANG", "LC_ALL")
    return {key: value for key, value in os.environ.items() if key in keep}


def _decoded(element: dict[str, Any], key: str) -> list[Any]:
    entries = element.get(key)
    return json.loads(base64.b64decode(entries[0]["data"]).decode("utf-8")) if entries else []


def outcomes_of(report: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """The outcomes and the caught exceptions in behave's report, each with the rule it came from."""
    try:
        log = json.loads(report.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CannotRun("the rules left no report") from exc
    outcomes: list[dict[str, Any]] = []
    caught: list[dict[str, Any]] = []
    for feature in log:
        rule = str(feature.get("name", "")).split(" ", 1)[0]
        for element in feature.get("elements", []):
            outcomes.extend({**outcome, "rule": rule} for outcome in _decoded(element, "validation_outcomes"))
            caught.extend({**exc, "rule": rule} for exc in _decoded(element, "caught_exceptions"))
    return outcomes, caught


def _message(outcome: dict[str, Any]) -> str:
    parts = [str(outcome.get("feature") or outcome["rule"])]
    for key in ("scenario", "last_step"):
        if outcome.get(key):
            parts.append(str(outcome[key]))
    if outcome.get("expected") is not None:
        parts.append(f"Expected: {json.dumps(outcome['expected'], default=str)}")
    if outcome.get("observed") is not None:
        parts.append(f"Observed: {json.dumps(outcome['observed'], default=str)}")
    return ". ".join(parts)[:MAX_MESSAGE]


def global_ids(path: Path, step_ids: set[int]) -> dict[int, str]:
    """The GlobalId of every rooted instance among ``step_ids``, read with Kontroll's own STEP reader."""
    from opencde.ifcgraph.schema import Schema
    from opencde.ifcgraph.step import StepError, StepFile, string_of_atom

    try:
        step = StepFile(path.read_bytes())
        schema = Schema(step.schema)
    except (OSError, StepError):
        return {}
    found: dict[int, str] = {}
    for step_id in step_ids:
        if step_id not in step:
            continue
        keyword, parameters = step[step_id]
        if "IfcRoot" in schema.chain(keyword) and parameters and isinstance(parameters[0], bytes):
            found[step_id] = string_of_atom(parameters[0])
    return found


def report_of(path: Path, env: Path, timeout: float) -> dict[str, Any]:
    manifest = manifest_of(env)
    with tempfile.TemporaryDirectory(prefix="ifcgherkin-") as tmp:
        report = Path(tmp) / "report.json"
        run_rules(env, path, report, timeout)
        outcomes, caught = outcomes_of(report)
    found = [o for o in outcomes if str(o.get("severity", "")).lower() in ("error", "warning")]
    ids = {o["inst"] for o in found if isinstance(o.get("inst"), int)}
    names = global_ids(path, ids) if ids else {}
    issues = [
        {
            "kind": "gherkin",
            "rule": outcome["rule"],
            "severity": str(outcome["severity"]).lower(),
            "message": _message(outcome),
            "step_id": outcome.get("inst") if isinstance(outcome.get("inst"), int) else None,
            "global_id": names.get(outcome.get("inst")) if isinstance(outcome.get("inst"), int) else None,
            "attribute": None,
        }
        for outcome in found[:MAX_REPORTED]
    ]
    not_run = sorted(
        {(e["rule"], str(e.get("error_type"))) for e in caught if e.get("error_type") not in _NO_EXCEPTION}
    )
    return {
        "ruleset": manifest.get("ruleset", "ifc-gherkin-rules"),
        "issue_count": len(found),
        "error_count": sum(1 for outcome in found if str(outcome["severity"]).lower() == "error"),
        "truncated": len(found) > MAX_REPORTED,
        "issues": issues,
        "rules_not_run": [{"rule": rule, "error": error} for rule, error in not_run],
    }


def main(argv: list[str] | None = None) -> int:
    """Exit 0 for a file with no issues, 1 for one with, 2 when the rules could not be run. The answer is JSON on stdout."""
    parser = argparse.ArgumentParser(prog="opencde-ifcgraph-gherkin")
    parser.add_argument("file", type=Path)
    parser.add_argument("--env", type=Path, required=True, help="the folder gherkin_install made")
    parser.add_argument("--memory-mb", type=int, default=0)
    parser.add_argument("--timeout-seconds", type=float, default=840.0)
    args = parser.parse_args(argv)
    if args.memory_mb:
        limit_memory(args.memory_mb)
    try:
        report = report_of(args.file, args.env, args.timeout_seconds)
    except CannotRun as exc:
        sys.stderr.write(json.dumps({"error": str(exc)}) + "\n")
        return 2
    sys.stdout.write(json.dumps(report) + "\n")
    sys.stdout.flush()
    return 1 if report["issue_count"] else 0


if __name__ == "__main__":
    keep_stdout_for_the_answer()
    sys.exit(main())
