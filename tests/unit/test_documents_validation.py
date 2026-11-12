# This file was generated with the assistance of an AI coding tool.
"""How the check of an uploaded IFC file shows in a version's metadata and in its report."""

from __future__ import annotations

from pathlib import Path

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
    assert body["issues"][0]["ifc_class"] is None and body["issues"][0]["root_global_id"] is None, (
        "a report kept before the findings named their elements reads as it did"
    )


def test_a_rules_finding_carries_the_class_of_its_instance_and_the_element_it_is_in() -> None:
    issue = {
        "kind": "gherkin",
        "rule": "GEM111",
        "severity": "error",
        "message": "GEM111 - No duplicated points within a polyloop or polyline.",
        "step_id": 202,
        "global_id": None,
        "attribute": None,
        "ifc_class": "IfcPolyline",
        "root_global_id": "1Xezbq735AdBO_4DerG66G",
    }
    checked = Validation(state="done", issue_count=1, error_count=1, ruleset=RULES, issues=[issue])
    body = report(checked).model_dump(mode="json", exclude_none=True)
    assert body["issues"] == [{key: value for key, value in issue.items() if value is not None}]


def test_the_versions_page_shows_the_class_and_the_element_a_finding_is_in(tmp_path: Path) -> None:
    from opencde.ui.templating import render
    from tests.conftest import test_settings as make_settings
    from tests.security.test_prompt_injection import _contexts, _request

    reached = {"kind": "gherkin", "rule": "GEM111", "severity": "error", "message": "m", "step_id": 202}
    reached |= {"ifc_class": "IfcPolyline", "root_global_id": "1Xezbq735AdBO_4DerG66G"}
    own = {"kind": "gherkin", "rule": "GEM004", "severity": "error", "message": "m", "step_id": 242}
    own |= {"global_id": "3eT96F_cnDsOufCEsotwtp", "ifc_class": "IfcWallStandardCase"}
    own["root_global_id"] = own["global_id"]
    validation = Validation(state="done", issue_count=2, error_count=2, ruleset=RULES, issues=[reached, own])
    context = {
        **_contexts("x")["documents/details.html"],
        "validation": validation,
        "validation_issues": [reached, own],
    }
    html = render(_request(make_settings(tmp_path)), "documents/details.html", context).body.decode("utf-8")
    first, second = html.split("<td><code>GEM111</code></td>", 1)[1].split("<td><code>GEM004</code></td>", 1)
    assert "<code>#202</code> IfcPolyline" in first and "<code>1Xezbq735AdBO_4DerG66G</code>" in first
    assert "Nearest element that reaches the instance" in first
    assert "<code>#242</code> IfcWallStandardCase" in second and "<code>3eT96F_cnDsOufCEsotwtp</code>" in second
    assert "Nearest element" not in second, "a rooted instance is its own element"


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


def test_the_graph_adds_its_findings_as_a_check_of_their_own() -> None:
    from opencde.documents.validation import Validation, with_graph_findings

    checked = Validation(
        state="done",
        issue_count=0,
        error_count=0,
        checks=[{"name": "schema", "state": "done", "ruleset": "IfcOpenShell", "issue_count": 0}],
    )
    warning = {"kind": "reachability", "severity": "warning", "message": "No GlobalId reaches it", "step_id": 9001}
    found = with_graph_findings(checked, issue_count=1, error_count=0, ruleset="IFC-LPG", issues=[warning])
    assert found.status == "warnings" and found.issue_count == 1 and found.error_count == 0
    assert [check["name"] for check in found.checks] == ["schema", "graph"] and found.issues == [warning]
    assert found.rulesets == ["IfcOpenShell", "IFC-LPG"]


def test_the_graph_adds_nothing_before_the_file_is_checked_or_the_model_converted() -> None:
    from opencde.documents.validation import Validation, with_graph_findings

    pending = Validation(state="pending")
    assert with_graph_findings(pending, issue_count=3, error_count=0, ruleset="IFC-LPG", issues=[]) is pending
    done = Validation(state="done", issue_count=0, error_count=0)
    assert with_graph_findings(done, issue_count=None, error_count=None, ruleset=None, issues=[]) is done


def test_a_long_list_of_graph_findings_marks_the_report_cut() -> None:
    from opencde.documents.validation import MAX_ISSUES, Validation, with_graph_findings

    done = Validation(state="done", issue_count=5, error_count=5)
    found = with_graph_findings(done, issue_count=MAX_ISSUES, error_count=0, ruleset="IFC-LPG", issues=[])
    assert found.truncated and found.issue_count == MAX_ISSUES + 5 and found.status == "issues"
