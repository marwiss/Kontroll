# This file was generated with the assistance of an AI coding tool.
"""How the check of an uploaded IFC file shows in a version's metadata and in its report."""

from __future__ import annotations

import pytest

from opencde.documents.validation import Validation, metadata_entries, report
from tests.conformance.schemas import validate_documents

URL = "https://cde.example.test/documents/1.0/documents/d/versions/1/ifc-validation"
RULESET = "IfcOpenShell 0.9.0: schema and EXPRESS rules"


@pytest.mark.parametrize(
    ("state", "count", "status"),
    [
        ("queued", None, "pending"),
        ("running", None, "pending"),
        ("done", 0, "passed"),
        ("done", 3, "issues"),
        ("failed", None, "unknown"),
    ],
)
def test_the_status_follows_the_check(state: str, count: int | None, status: str) -> None:
    assert Validation(state=state, issue_count=count).status == status


def test_the_metadata_entries_keep_to_the_documents_api() -> None:
    pending = metadata_entries(Validation(state="queued"), URL)
    assert [(entry.name, entry.value) for entry in pending] == [
        ("ifc_validation_status", ["pending"]),
        ("ifc_validation_report", [URL]),
    ]
    done = Validation(state="done", issue_count=2, checked_at="2026-11-07T10:00:00Z", ruleset=RULESET)
    entries = metadata_entries(done, URL)
    assert {entry.name: (entry.value, entry.data_type) for entry in entries} == {
        "ifc_validation_status": (["issues"], "string"),
        "ifc_validation_issues": (["2"], "integer32"),
        "ifc_validation_checked_at": (["2026-11-07T10:00:00Z"], "date-time"),
        "ifc_validation_ruleset": ([RULESET], "string"),
        "ifc_validation_report": ([URL], "url"),
    }
    failed = metadata_entries(Validation(state="failed", checked_at="2026-11-07T10:00:00Z"), URL)
    assert "ifc_validation_issues" not in {entry.name for entry in failed}, "nothing is known of a file not checked"
    for each in (pending, entries, failed):
        validate_documents({"metadata": [entry.model_dump() for entry in each]}, "DocumentMetadata")


def test_the_report_passes_the_validators_words_on_as_they_are() -> None:
    issue = {
        "kind": "schema",
        "severity": "error",
        "message": "On instance:\n    #9=IFCWALL(...)\n               ^^^^  ",
        "step_id": 9,
        "global_id": "0KhR8hr7H8eewFRKm6V1bJ",
        "attribute": None,
    }
    body = report(Validation(state="done", issue_count=1, ruleset=RULESET, issues=[issue])).model_dump(
        exclude_none=True
    )
    assert body["status"] == "issues" and body["issue_count"] == 1 and body["truncated"] is False
    assert body["issues"] == [{key: value for key, value in issue.items() if value is not None}]
