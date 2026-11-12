# This file was generated with the assistance of an AI coding tool.
"""How the check of an uploaded IFC file is shown: in the version's metadata, and as a report (an extension).

The IFC module checks every IFC file uploaded as a document version against the IFC schema, in the background, and
keeps the result on an ``Validation`` node below the version (``IfcGraphService``, ADR 0011). The upload is never
held back by it. The metadata of the version, which any Documents API client can read, carries a summary and the address
of the report; the report lists the issues, each with the GlobalId of its element where it has one, and, where the
server finds them, the rooms of each storey as a section of their own, which never counts as an issue (F38 a).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from opencde.documents.schemas import DocumentMetadataEntry

Status = Literal["pending", "passed", "warnings", "issues", "unknown"]
Facing = Literal["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
MAX_ISSUES = 10_000  # as many issues as a report lists


@dataclass(frozen=True)
class Validation:
    """What an ``Validation`` node says; ``issues`` only when they were asked for."""

    state: str
    issue_count: int | None = None
    error_count: int | None = None
    truncated: bool = False
    checked_at: str | None = None
    ruleset: str | None = None
    issues: list[dict[str, Any]] = field(default_factory=list)
    checks: list[dict[str, Any]] = field(default_factory=list)
    rooms: dict[str, Any] | None = None  # the section of the rooms (``IfcRooms``), when they were found

    @property
    def rulesets(self) -> list[str]:
        """What the file was checked with, one entry per check that ran: the schema and, where installed, the rules."""
        if self.checks:
            return [str(check["ruleset"]) for check in self.checks if check.get("state") == "done"]
        return [self.ruleset] if self.ruleset else []

    @property
    def failed_checks(self) -> list[str]:
        """What could not check the file at all, while another check did."""
        return [str(check["ruleset"]) for check in self.checks if check.get("state") == "failed"]

    @property
    def rules_not_run(self) -> list[str]:
        """The gherkin rules that raised an exception on the file, so that their verdict is unknown."""
        return sorted(
            {
                str(rule["rule"])
                for check in self.checks
                if check.get("name") != "ids"
                for rule in check.get("rules_not_run", [])
            }
        )

    @property
    def ids_check(self) -> dict[str, Any] | None:
        """The check against the IDS documents of the version's project, when it has any (ADR 0015)."""
        return next((check for check in self.checks if check.get("name") == "ids"), None)

    @property
    def ids_specifications(self) -> list[dict[str, Any]]:
        """Each specification of the IDS check, with the title of its document."""
        check = self.ids_check or {}
        titles = {document["document_id"]: document.get("title") for document in check.get("documents", [])}
        return [
            {**specification, "document_title": titles.get(specification.get("document_id"))}
            for specification in check.get("specifications", [])
        ]

    @property
    def ids_not_read(self) -> list[dict[str, Any]]:
        """The IDS documents that could not be read, each with the reason."""
        return list((self.ids_check or {}).get("rules_not_run", []))

    @property
    def room_storeys(self) -> list[dict[str, Any]]:
        """The storeys of the section of the rooms that hold walls, as the version's page lists them."""
        return [storey for storey in (self.rooms or {}).get("storeys", []) if storey.get("walls")]

    @property
    def status(self) -> Status:
        """``pending`` until checked, ``unknown`` when the check could not be made.

        ``warnings`` when every issue is a warning, as buildingSMART's validation service holds such a file valid: the
        IFC schema has only errors, while some of the gherkin rules (industry practice) only warn.
        """
        if self.state == "done":
            if not self.issue_count:
                return "passed"
            return "warnings" if self.error_count == 0 else "issues"
        if self.state == "failed":
            return "unknown"
        return "pending"


def with_graph_findings(
    validation: Validation,
    *,
    issue_count: int | None,
    error_count: int | None,
    ruleset: str | None,
    issues: list[dict[str, Any]],
) -> Validation:
    """A version's check with what the graph of its model shows added as the check ``graph``: the instances that no
    GlobalId reaches, as warnings, and the products the geometry pass could not build. Nothing is added before the
    file is checked or the model converted, so that the status stays ``pending`` until both are done."""
    if issue_count is None or validation.state != "done":
        return validation
    total = (validation.issue_count or 0) + int(issue_count)
    return replace(
        validation,
        issue_count=total,
        error_count=(validation.error_count or 0) + int(error_count or 0),
        truncated=validation.truncated or total > MAX_ISSUES,
        issues=[*validation.issues, *issues][:MAX_ISSUES],
        checks=[
            *validation.checks,
            {"name": "graph", "state": "done", "ruleset": ruleset or "IFC-LPG", "issue_count": int(issue_count)},
        ],
    )


def metadata_entries(validation: Validation, report_url: str) -> list[DocumentMetadataEntry]:
    """The entries of the version's metadata (Documents API ``DocumentMetadataEntry``)."""
    entries = [DocumentMetadataEntry(name="ifc_validation_status", value=[validation.status], data_type="string")]
    if validation.status in ("passed", "warnings", "issues"):
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
    if validation.rulesets:
        entries.append(
            DocumentMetadataEntry(name="ifc_validation_ruleset", value=validation.rulesets, data_type="string")
        )
    entries.append(DocumentMetadataEntry(name="ifc_validation_report", value=[report_url], data_type="url"))
    return entries


class _Report(BaseModel):
    # A response only: the validator's words are passed on as they are, spaces included.
    model_config = ConfigDict(extra="forbid")


class IfcValidationIssue(_Report):
    kind: str = Field(
        description="What found it: `schema`, `entity_rule`, `simpletype_rule` or `global_rule` of the IFC schema, "
        "`gherkin` for one of buildingSMART's ifc-gherkin-rules, `ids` for a specification of one of the project's "
        "IDS documents, `bsdd` for a classification reference that buildingSMART's Data Dictionary does not know, or "
        "a set or a property that its IFC dictionary does not list, `reachability` for an instance that no GlobalId "
        "reaches, or `geometry` for a product whose shape the geometry pass could not build."
    )
    rule: str | None = Field(
        None,
        description="The code of the gherkin rule, as in `GRP001`, or the identifier of the IDS specification, or "
        "else its name; for `bsdd`, the dictionary, as in `buildingsmart/ifc/4.3`.",
    )
    severity: str = Field(description="`error` or `warning`.")
    message: str = Field(description="The validator's words, which may quote the file; at most 1,000 characters.")
    step_id: int | None = Field(
        None,
        description="The number of the instance in the file, as in `#123`; for `bsdd`, the classification "
        "reference or the property set.",
    )
    global_id: str | None = Field(
        None,
        description="The GlobalId of the instance, when it is a rooted entity; for `bsdd`, of an object the "
        "reference or set is on, whose class the message names.",
    )
    attribute: str | None = Field(
        None,
        description="The attribute the issue is about, when the validator says; for `bsdd`, the reference's "
        "attribute that names the URI, or the set and its property, as in `Pset_WallCommon.Colour`.",
    )
    document_id: str | None = Field(None, description="For `ids`: the IDS document whose specification found it.")


class IfcValidationRuleNotRun(_Report):
    rule: str = Field(description="The code of the gherkin rule, or the title of the IDS document.")
    error: str = Field(description="What the rule raised, by type, or why the IDS document could not be read.")
    document_id: str | None = Field(None, description="For `ids`: the IDS document that could not be read.")


class IfcValidationIdsDocument(_Report):
    document_id: str = Field(description="An IDS document of the project.")
    version_index: int = Field(description="The version checked against, the latest when the file was checked.")
    title: str | None = Field(None, description="The document's title.")


class IfcValidationSpecification(_Report):
    document_id: str = Field(description="The IDS document the specification is in.")
    name: str = Field(description="The specification's name.")
    identifier: str | None = Field(None, description="The specification's identifier, when it has one.")
    usage: Literal["required", "optional", "prohibited"] = Field(description="As IDS 1.0 has it.")
    ifc_versions: list[str] = Field(description="The IFC versions the specification names.")
    for_this_schema: bool = Field(
        description="Whether those include the file's. The specification is checked either way, as IfcTester does."
    )
    status: Literal["passed", "failed", "not applicable"] = Field(
        description="`not applicable` for an optional specification that applies to nothing in the file."
    )
    applicable: int = Field(description="How many elements of the file the specification applies to.")
    issues: int = Field(description="How many issues it gave.")


class IfcValidationCheck(_Report):
    name: str = Field(
        description="`schema`, `gherkin`, `ids`, `bsdd` for buildingSMART's Data Dictionary, or `graph` for what "
        "the converted model shows."
    )
    state: Literal["done", "failed"] = Field(description="`failed` when the check could not be made at all.")
    ruleset: str = Field(description="What the check ran, and which version of it.")
    issue_count: int = Field(description="How many issues this check found.")
    error: str | None = Field(
        None, description="For a `failed` check that says why, as `bsdd` does: how bSDD was out of reach."
    )
    rules_not_run: list[IfcValidationRuleNotRun] = Field(
        default_factory=list,
        description="Rules that raised an exception, so their verdict is unknown, or IDS documents that could not be "
        "read.",
    )
    documents: list[IfcValidationIdsDocument] = Field(
        default_factory=list, description="For `ids`: the IDS documents the file was checked against."
    )
    specifications: list[IfcValidationSpecification] = Field(
        default_factory=list, description="For `ids`: every specification of those documents, with its verdict."
    )


class IfcRoom(_Report):
    index: int = Field(
        description="The room's number on its storey, from 1, in the order of its centre: by the model's y to the "
        "metre, then by its x."
    )
    area: float = Field(description="Its area in m², inside the walls' centre lines, to two decimals.")
    perimeter: float = Field(description="Its perimeter in metres, along the centre lines, to two decimals.")
    walls: list[str] = Field(default_factory=list, description="The GlobalIds of the walls along its boundary.")
    neighbours: list[int] = Field(
        default_factory=list, description="The rooms that share a stretch of boundary with it, by `index`."
    )


class IfcRoomsWall(_Report):
    global_id: str = Field(description="The external wall's GlobalId.")
    name: str | None = Field(None, description="Its name, as the file has it.")
    facing: Facing = Field(
        description="The compass sector its outside faces, `N`, `NE`, `E`, `SE`, `S`, `SW`, `W` or `NW`, with north "
        "as the storey's `north` says."
    )
    length: float = Field(description="How far it runs along the outside of the rooms, in metres, to two decimals.")


class IfcRoomsStorey(_Report):
    storey: str | None = Field(None, description="The storey's name, as the file has it.")
    elevation: float = Field(description="Its elevation in metres.")
    closed: bool = Field(description="True when its walls enclose at least one room and no wall end is open.")
    rooms: list[IfcRoom] = Field(
        default_factory=list,
        description="The rooms its walls' centre lines enclose, each at least 0.5 m² and 0.5 m across.",
    )
    external: list[IfcRoomsWall] = Field(
        default_factory=list, description="The walls along the outside of its rooms, in the order of their facing."
    )
    dangles: list[list[float]] = Field(
        default_factory=list, description="The open wall ends, each `[x, y]` in metres in the model's plan."
    )
    dangling_walls: list[str] = Field(default_factory=list, description="The GlobalIds of the walls with an open end.")
    walls: int = Field(description="How many walls the storey contains.")
    unread: int = Field(description="How many of them gave no centre line, from their `Axis` or their body.")
    unread_walls: list[str] = Field(default_factory=list, description="The GlobalIds of those walls.")
    tolerance: float = Field(
        description="How far, in metres, a wall end may be from another wall and still be joined to it: half the "
        "storey's thickest wall up to a metre (0.2 m when no wall says) plus 0.05 m."
    )
    north: Literal["map", "true_north", "model"] = Field(
        description="Where north comes from: the map conversion (`map`), the model context's `TrueNorth`, or the "
        "model's y axis when the file says neither (`model`)."
    )


class IfcRooms(_Report):
    storeys: list[IfcRoomsStorey] = Field(default_factory=list, description="Every storey, by elevation.")
    cut: bool = Field(
        False,
        description="True when a list was longer than it is here: at most 100 storeys, 500 rooms a storey, and 200 "
        "entries in every other list.",
    )


class IfcValidationReport(_Report):
    status: Status = Field(
        description="`pending`, `passed`, `warnings` when every issue is a warning, `issues` when one or more is an "
        "error, or `unknown` when the file could not be checked."
    )
    checked_at: str | None = Field(None, description="When the file was checked, ISO 8601 in UTC.")
    ruleset: str | None = Field(None, description="What the file was checked with, and which version of it.")
    issue_count: int | None = Field(None, description="How many issues the file has, all of them.")
    error_count: int | None = Field(None, description="How many of the issues are errors; the rest are warnings.")
    truncated: bool = Field(False, description="True when the file has more issues than are listed (10,000).")
    checks: list[IfcValidationCheck] = Field(default_factory=list, description="Each check on its own.")
    issues: list[IfcValidationIssue] = Field(default_factory=list)
    rooms: IfcRooms | None = Field(
        None,
        description="The rooms of each storey, found from the walls' centre lines as Dataspatium finds them, when the "
        "server is set to (`rooms` in the capabilities' `ifc_validation`). A section of its own that only informs: it "
        "changes neither the status nor the counts. Left out when it is off or the rooms could not be found.",
    )


def rooms_of(section: dict[str, Any] | None) -> IfcRooms | None:
    """The kept section of the rooms, as the reports give it."""
    return IfcRooms.model_validate(section) if section else None


def report(validation: Validation) -> IfcValidationReport:
    return IfcValidationReport(
        status=validation.status,
        checked_at=validation.checked_at,
        ruleset=validation.ruleset,
        issue_count=validation.issue_count,
        error_count=validation.error_count,
        truncated=validation.truncated,
        checks=[IfcValidationCheck.model_validate(check) for check in validation.checks],
        issues=[IfcValidationIssue.model_validate(issue) for issue in validation.issues],
        rooms=rooms_of(validation.rooms),
    )
