# This file was generated with the assistance of an AI coding tool.
"""How the check of an uploaded IFC file is shown: in the version's metadata, and as a report (an extension).

The IFC module checks every IFC file uploaded as a document version against the IFC schema, in the background, and
keeps the result on an ``IfcValidation`` node below the version (``IfcGraphService``, ADR 0011). The upload is never
held back by it. The metadata of the version, which any Documents API client can read, carries a summary and the address
of the report; the report lists the issues, each with the GlobalId of its element where it has one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from opencde.documents.schemas import DocumentMetadataEntry

Status = Literal["pending", "passed", "issues", "unknown"]


@dataclass(frozen=True)
class Validation:
    """What an ``IfcValidation`` node says; ``issues`` only when they were asked for."""

    state: str
    issue_count: int | None = None
    truncated: bool = False
    checked_at: str | None = None
    ruleset: str | None = None
    issues: list[dict[str, Any]] = field(default_factory=list)

    @property
    def status(self) -> Status:
        """``pending`` until checked, ``unknown`` when the check could not be made."""
        if self.state == "done":
            return "issues" if self.issue_count else "passed"
        if self.state == "failed":
            return "unknown"
        return "pending"


def metadata_entries(validation: Validation, report_url: str) -> list[DocumentMetadataEntry]:
    """The entries of the version's metadata (Documents API ``DocumentMetadataEntry``)."""
    entries = [DocumentMetadataEntry(name="ifc_validation_status", value=[validation.status], data_type="string")]
    if validation.status in ("passed", "issues"):
        entries.append(
            DocumentMetadataEntry(
                name="ifc_validation_issues", value=[str(validation.issue_count or 0)], data_type="integer32"
            )
        )
    if validation.checked_at:
        entries.append(
            DocumentMetadataEntry(
                name="ifc_validation_checked_at", value=[validation.checked_at], data_type="date-time"
            )
        )
    if validation.ruleset:
        entries.append(
            DocumentMetadataEntry(name="ifc_validation_ruleset", value=[validation.ruleset], data_type="string")
        )
    entries.append(DocumentMetadataEntry(name="ifc_validation_report", value=[report_url], data_type="url"))
    return entries


class _Report(BaseModel):
    # A response only: the validator's words are passed on as they are, spaces included.
    model_config = ConfigDict(extra="forbid")


class IfcValidationIssue(_Report):
    kind: str = Field(description="What found it: `schema`, `entity_rule`, `simpletype_rule` or `global_rule`.")
    severity: str = Field(description="`error` or `warning`.")
    message: str = Field(description="The validator's words, which may quote the file; at most 1,000 characters.")
    step_id: int | None = Field(None, description="The number of the instance in the file, as in `#123`.")
    global_id: str | None = Field(None, description="The GlobalId of the instance, when it is a rooted entity.")
    attribute: str | None = Field(None, description="The attribute the issue is about, when the validator says.")


class IfcValidationReport(_Report):
    status: Status = Field(
        description="`pending`, `passed`, `issues`, or `unknown` when the file could not be checked."
    )
    checked_at: str | None = Field(None, description="When the file was checked, ISO 8601 in UTC.")
    ruleset: str | None = Field(None, description="What the file was checked with, and which version of it.")
    issue_count: int | None = Field(None, description="How many issues the file has, all of them.")
    truncated: bool = Field(False, description="True when the file has more issues than are listed (10,000).")
    issues: list[IfcValidationIssue] = Field(default_factory=list)


def report(validation: Validation) -> IfcValidationReport:
    return IfcValidationReport(
        status=validation.status,
        checked_at=validation.checked_at,
        ruleset=validation.ruleset,
        issue_count=validation.issue_count,
        truncated=validation.truncated,
        issues=[IfcValidationIssue.model_validate(issue) for issue in validation.issues],
    )
