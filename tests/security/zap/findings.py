# This file was generated with the assistance of an AI coding tool.
"""Read the authenticated scan's report and fail on what matters.

Everything is listed; medium and high risks fail the job unless ``tests/security/zap/rules.tsv`` ignores them with its reason:

    uv run python tests/security/zap/findings.py tests/security/zap/zap-authenticated.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

RULES = Path(__file__).with_name("rules.tsv")
FAILS_FROM_RISK = 2  # 0 informational, 1 low, 2 medium, 3 high


def ignored_rules() -> set[str]:
    lines = RULES.read_text(encoding="utf-8").splitlines()
    return {line.split("\t")[0] for line in lines if "\tIGNORE\t" in line}


def main(report: str) -> int:
    ignored = ignored_rules()
    failures = 0
    data = json.loads(Path(report).read_text(encoding="utf-8"))
    for site in data.get("site", []):
        for alert in sorted(site.get("alerts", []), key=lambda found: -int(found["riskcode"])):
            risk = int(alert["riskcode"])
            verdict = "ignored" if alert["pluginid"] in ignored else ("FAIL" if risk >= FAILS_FROM_RISK else "noted")
            failures += verdict == "FAIL"
            print(f"{verdict:8} {alert['riskdesc']:22} {alert['pluginid']:>6} x{alert['count']:>4}  {alert['alert']}")
            if verdict == "FAIL":
                for instance in alert.get("instances", [])[:5]:
                    print(f"           {instance.get('method', '')} {instance.get('uri', '')}")
    print(f"{failures} finding(s) that fail the job")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
