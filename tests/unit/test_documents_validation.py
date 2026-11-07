# This file was generated with the assistance of an AI coding tool.
"""How the check of an uploaded IFC file shows in a version's metadata and in its report."""

from __future__ import annotations

import pytest

from opencde.documents.validation import Validation, metadata_entries, report
from tests.conformance.schemas import validate_documents

URL = "https://cde.example.test/documents/1.0/documents/d/versions/1/ifc-validation"
RULESET = "IfcOpenShell 0.9.0: schema and EXPRESS rules"


@pytest.mark.parametrize(
    ("state", "count", "errors", "status"),
    [
        ("queued", None, None, "pending"),
        ("running", None, None, "pending"),
        ("done", 0, 0, "passed"),
        ("done", 3, 1, "issues"),
        ("done", 3, 0, "warnings"),
        ("done", 3, None, "issues"),  # checked before warnings were counted apart: the schema only has errors
        ("failed", None, None, "unknown"),
    ],
)
def test_the_status_follows_the_check(state: str, count: int | None, errors: int | None, status: str) -> None:
    assert Validation(state=state, issue_count=count, error_count=errors).status == status


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


RULES = "ifc-gherkin-rules 893f827 with IfcOpenShell 0.8.6"
SCHEMA_CHECK = {"name": "schema", "state": "done", "ruleset": RULESET, "issue_count": 0}


def test_each_check_that_ran_is_named_in_the_metadata() -> None:
    rules = {"name": "gherkin", "state": "done", "ruleset": RULES, "issue_count": 1, "rules_not_run": []}
    both = Validation(state="done", issue_count=1, ruleset=f"{RULESET}; {RULES}", checks=[SCHEMA_CHECK, rules])
    named = {entry.name: entry.value for entry in metadata_entries(both, URL)}
    assert named["ifc_validation_ruleset"] == [RULESET, RULES]
    failed = Validation(
        state="done", issue_count=0, ruleset=RULESET, checks=[SCHEMA_CHECK, {**rules, "state": "failed"}]
    )
    named = {entry.name: entry.value for entry in metadata_entries(failed, URL)}
    assert named["ifc_validation_ruleset"] == [RULESET], "rules that could not run checked nothing"
    assert named["ifc_validation_status"] == ["passed"], "the schema's check stands on its own"
    warned = Validation(state="done", issue_count=4, error_count=0, ruleset=RULESET, checks=[SCHEMA_CHECK, rules])
    named = {entry.name: entry.value for entry in metadata_entries(warned, URL)}
    assert (named["ifc_validation_status"], named["ifc_validation_issues"]) == (["warnings"], ["4"])
    validate_documents({"metadata": [e.model_dump() for e in metadata_entries(warned, URL)]}, "DocumentMetadata")


def test_the_report_tells_each_check_apart_with_the_rules_it_could_not_run() -> None:
    not_run = [{"rule": "GEM004", "error": "FileNotFoundError"}]
    rules = {"name": "gherkin", "state": "done", "ruleset": RULES, "issue_count": 1, "rules_not_run": not_run}
    issue = {
        "kind": "gherkin",
        "rule": "IFC106",
        "severity": "warning",
        "message": "IFC106 - Resource entities should be referenced by rooted entity",
        "step_id": 99999,
        "global_id": None,
        "attribute": None,
    }
    checked = Validation(state="done", issue_count=1, ruleset=RULES, checks=[SCHEMA_CHECK, rules], issues=[issue])
    body = report(checked).model_dump(mode="json")
    assert [check["name"] for check in body["checks"]] == ["schema", "gherkin"]
    assert body["checks"][1]["rules_not_run"] == [{**not_run[0], "document_id": None}]
    assert body["checks"][0]["rules_not_run"] == [] and body["checks"][0]["specifications"] == []
    assert body["issues"][0]["rule"] == "IFC106"


IDS_CHECK = {
    "name": "ids",
    "state": "done",
    "ruleset": "IfcTester 0.9.0: IDS 1.0",
    "issue_count": 1,
    "rules_not_run": [{"rule": "Broken", "error": "it has a DTD or an entity", "document_id": "ids-b"}],
    "documents": [
        {"document_id": "ids-a", "version_index": 2, "title": "Walls for reuse"},
        {"document_id": "ids-b", "version_index": 1, "title": "Broken"},
    ],
    "specifications": [
        {
            "document_id": "ids-a",
            "name": "Walls have a fire rating",
            "identifier": "W-1",
            "usage": "optional",
            "ifc_versions": ["IFC4"],
            "for_this_schema": False,
            "status": "failed",
            "applicable": 3,
            "issues": 1,
        }
    ],
}


def test_the_report_carries_the_ids_check_and_ties_each_finding_to_its_document() -> None:
    issue = {
        "kind": "ids",
        "rule": "W-1",
        "severity": "error",
        "message": "Walls have a fire rating: FireRating data shall be provided in the dataset Pset_WallCommon",
        "step_id": 242,
        "global_id": "1Xezbq735AdBO_4DerG66G",
        "attribute": None,
        "document_id": "ids-a",
    }
    checked = Validation(state="done", issue_count=1, error_count=1, checks=[SCHEMA_CHECK, IDS_CHECK], issues=[issue])
    body = report(checked).model_dump(mode="json")
    assert body["status"] == "issues", "an IDS finding is an error"
    assert body["checks"][1]["specifications"][0]["status"] == "failed"
    assert body["checks"][1]["documents"][1]["title"] == "Broken"
    assert body["issues"][0]["document_id"] == "ids-a"
    assert checked.rules_not_run == [], "an IDS document that could not be read is no rule that did not run"
    assert checked.ids_not_read == IDS_CHECK["rules_not_run"]
    assert checked.ids_specifications[0]["document_title"] == "Walls for reuse"
    assert "IfcTester 0.9.0: IDS 1.0" in checked.rulesets
