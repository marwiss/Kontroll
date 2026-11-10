# This file was generated with the assistance of an AI coding tool.
"""The trial of a topic's change set: an extension of the BCF API (ADR 0021).

When a topic's ``bim_snippet`` of the type ``DataregiumIfcChangeSet`` is uploaded and the IFC-LPG module is on, the
server applies the changes to the base version's file in a worker process, runs the checks an upload gets on the
result and compares the findings with the base version's: the proposal is ``clean`` when every change applied and no
finding is new, else ``issues``. ``GET /bcf/3.0/projects/{id}/topics/{guid}/ifc-proposal`` gives the trial to every
member of the project, with the same bearer token as the topic.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from opencde.bcf.topic_access import TopicCtx
from opencde.documents.validation import IfcValidationCheck, IfcValidationIssue
from opencde.ifcgraph.service import IfcGraphDep

TAG = "IFC change sets (extension)"

router = APIRouter(prefix="/projects/{project_id}/topics/{topic_id}", tags=[TAG])


class IfcProposalBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str
    version_index: int


class IfcProposalReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: str = Field(
        description="`queued` or `running` until the trial is over; then `clean` when every change applied and no "
        "finding is new compared with the base version, `issues` otherwise, or `failed` when the trial could not run."
    )
    created_at: str = Field(description="When the change set was received, ISO 8601 in UTC.")
    checked_at: str | None = Field(None, description="When the trial ended.")
    base: IfcProposalBase | None = Field(None, description="The document version the changes were applied to.")
    change_count: int | None = Field(None, description="How many changes the set holds.")
    applied: int | None = Field(None, description="How many of them applied; the rest are issues of kind `proposal`.")
    issue_count: int | None = Field(None, description="The new findings and the changes that did not apply.")
    error_count: int | None = Field(None, description="How many of the issues are errors.")
    truncated: bool = Field(False, description="True when the checks found more issues than are listed.")
    ruleset: str | None = Field(None, description="What the result was checked with.")
    checks: list[IfcValidationCheck] = Field(default_factory=list)
    issues: list[IfcValidationIssue] = Field(
        default_factory=list,
        description="The findings the base version lacks, as in a version's report, and a `proposal` issue per change "
        "that could not be applied, which says why without quoting the file.",
    )
    error: str | None = Field(None, description="Why the trial could not run, when it `failed`.")


def _report(node: dict[str, Any]) -> IfcProposalReport:
    base = None
    if node.get("base_document_id"):
        base = IfcProposalBase(document_id=str(node["base_document_id"]), version_index=int(node["base_version_index"]))
    return IfcProposalReport(
        state=str(node["state"]),
        created_at=str(node["created_at"]),
        checked_at=node.get("checked_at"),
        base=base,
        change_count=None if node.get("change_count") is None else int(node["change_count"]),
        applied=None if node.get("applied") is None else int(node["applied"]),
        issue_count=None if node.get("issue_count") is None else int(node["issue_count"]),
        error_count=None if node.get("error_count") is None else int(node["error_count"]),
        truncated=bool(node.get("truncated")),
        ruleset=node.get("ruleset"),
        checks=[IfcValidationCheck.model_validate(check) for check in node["checks"]],
        issues=[IfcValidationIssue.model_validate(issue) for issue in node["issues"]],
        error=node.get("error"),
    )


@router.get(
    "/ifc-proposal",
    summary="Get the trial of the topic's change set against its base version",
    response_model=IfcProposalReport,
    response_model_exclude_none=True,
)
async def proposal_get(topic: TopicCtx, ifcgraph: IfcGraphDep) -> IfcProposalReport:
    """The state of the trial and its findings. 404 when the topic's snippet is not a change set that was tried, or
    the IFC-LPG module is off."""
    if ifcgraph is None:
        raise HTTPException(404, "Change sets are not tried on this server: the IFC-LPG module is off")
    node = await ifcgraph.proposal(user_id=topic.user_id, project_id=topic.project_id, topic_guid=topic.guid)
    if node is None:
        raise HTTPException(404, "This topic has no change set that was tried")
    return _report(node)
