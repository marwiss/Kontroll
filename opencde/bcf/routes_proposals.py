# This file was generated with the assistance of an AI coding tool.
"""The trial of a topic's change set: an extension of the BCF API (ADR 0021).

When a topic's ``bim_snippet`` of the type ``DataregiumIfcChangeSet`` is uploaded and the IFC-LPG module is on, the
server applies the changes to the base version's file in a worker process, runs the checks an upload gets on the
result and compares the findings with the base version's: the proposal is ``clean`` when every change applied and no
finding is new, else ``issues``. ``GET /bcf/3.0/projects/{id}/topics/{guid}/ifc-proposal`` gives the trial to every
member of the project, with the same bearer token as the topic. ``POST …/ifc-proposal/approve`` lets a ``manager``
make a clean trial the next version of the base document: the applied file becomes the version, with the base,
the change set and who proposed and approved it in its metadata; the topic gets a comment with the version's
address and the status ``Closed`` where the project has it. An AI only proposes: approval is a person's.

When the document has moved on since the base, the server merges (ADR 0021): the changes of the versions in
between, each approved from a change set, are compared attribute by attribute with the proposal's; when none
collide, the change set is tried again on the latest version, at once, and approved on it; when some collide, or
a version in between was uploaded as a whole file, the answer is 412 with the colliding attributes, for the
client to merge three ways and send again.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import anyio
from fastapi import APIRouter, HTTPException
from ifc_lpg.validation import pack_report
from pydantic import BaseModel, ConfigDict, Field

from opencde.accounts.roles import Role, at_least
from opencde.bcf.comments import CommentsDep
from opencde.bcf.schemas import CommentPOST, TopicPUT
from opencde.bcf.topic_access import TopicCtx, TopicsDep
from opencde.deps import ProjectsDep, SettingsDep, StorageDep
from opencde.documents.links import api_base
from opencde.documents.repository import DocumentsDep, default_metadata
from opencde.documents.schemas import DocumentMetadataEntry, DocumentVersion
from opencde.documents.validation import IfcValidationCheck, IfcValidationIssue
from opencde.errors import CODE_VERSION_CONFLICT, ApiError
from opencde.ids import new_id
from opencde.ifcgraph.service import STATE_CLEAN, IfcGraphDep, IfcGraphService
from opencde.storage import LocalStorage, make_key

TAG = "IFC change sets (extension)"

router = APIRouter(prefix="/projects/{project_id}/topics/{topic_id}", tags=[TAG])

CLOSED = "Closed"  # the topic's status after the approval, where the project's values have it
MAX_CONFLICTS = 100
EVERYTHING = "*"  # a version in between came as a whole file: anything may have changed


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
    approved_by: str | None = Field(None, description="Who approved it, when it is `approved`.")
    version_index: int | None = Field(None, description="The version it became, when it is `approved`.")


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
        approved_by=node.get("approved_by"),
        version_index=None if node.get("version_index") is None else int(node["version_index"]),
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


def _copy_hashed(storage: LocalStorage, source: Path, key: str) -> tuple[int, str]:
    """The applied file copied into the documents, with its size and SHA-256 as an upload has them."""
    digest = hashlib.sha256()
    with source.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return storage.copy_in(source, key), digest.hexdigest()


def _change_set(storage: LocalStorage, snippet_key: str) -> dict[str, Any]:
    with storage.open_read(snippet_key) as handle:
        return dict(json.loads(handle.read().decode("utf-8")))


@router.post(
    "/ifc-proposal/approve",
    summary="Approve the topic's change set: its applied file becomes the next version of the base document",
    response_model=DocumentVersion,
    response_model_exclude_none=True,
    status_code=201,
)
async def proposal_approve(
    topic: TopicCtx,
    ifcgraph: IfcGraphDep,
    documents: DocumentsDep,
    comments: CommentsDep,
    topics: TopicsDep,
    projects: ProjectsDep,
    storage: StorageDep,
    settings: SettingsDep,
) -> DocumentVersion:
    """A `manager` approves a `clean` trial: the answer is the new version as the Documents API gives it, with
    `base_version_index`, `change_set_id`, `proposed_by`, `approved_by` and, where an AI proposed it, `ai_model` and
    `tool_call` in its metadata. When the document has moved on since the base, the change set is tried again on
    the latest version and approved on it, unless one of its attributes was changed in between: then 412
    `version_conflict` with the colliding attributes in `conflicts`. 403 for other roles, 409 when the trial is not
    clean or was approved already."""
    if not at_least(topic.role, Role.MANAGER):
        raise HTTPException(403, "Only a manager approves a change set")
    if ifcgraph is None:
        raise HTTPException(404, "Change sets are not tried on this server: the IFC-LPG module is off")
    node = await ifcgraph.proposal(user_id=topic.user_id, project_id=topic.project_id, topic_guid=topic.guid)
    if node is None:
        raise HTTPException(404, "This topic has no change set that was tried")
    if node["state"] != STATE_CLEAN:
        raise HTTPException(409, f"The trial is {node['state']}; only a clean one is approved")
    document_id, base_index = str(node["base_document_id"]), int(node["base_version_index"])
    latest = await documents.latest(user_id=topic.user_id, document_id=document_id)
    if latest is None:
        raise HTTPException(404, "The base document is gone")
    if latest.version_index != base_index:
        colliding = await _collisions(ifcgraph, documents, topic.user_id, topic.project_id, latest, base_index, node)
        if colliding:
            raise ApiError(
                412,
                f"The change set builds on version {base_index}, but the document's latest version is "
                f"{latest.version_index}, and {len(colliding)} of its changes collide with what came between",
                code=CODE_VERSION_CONFLICT,
                details={"conflicts": colliding[:MAX_CONFLICTS]},
            )
        state = await ifcgraph.retry_proposal(proposal_id=str(node["id"]), base_version_index=latest.version_index)
        if state != STATE_CLEAN:
            raise HTTPException(409, f"On version {latest.version_index} the trial is {state}; see the trial")
        node = await ifcgraph.proposal(user_id=topic.user_id, project_id=topic.project_id, topic_guid=topic.guid)
        if node is None:
            raise HTTPException(404, "This topic has no change set that was tried")
        base_index = latest.version_index
    key = make_key("documents", new_id())
    size, sha256 = await anyio.to_thread.run_sync(_copy_hashed, storage, storage.path(str(node["storage_key"])), key)
    change_set = await anyio.to_thread.run_sync(_change_set, storage, str(node["snippet_key"]))
    provenance = dict(change_set.get("provenance") or {})
    proposer = str(node["author"])
    metadata = default_metadata(
        file_name=latest.file_name,
        size_in_bytes=size,
        sha256=sha256,
        author=proposer,
        project_name=latest.project_name,
    )
    metadata += [
        DocumentMetadataEntry(name="base_version_index", value=[str(base_index)], data_type="integer32"),
        DocumentMetadataEntry(name="change_set_id", value=[topic.guid], data_type="string"),
        DocumentMetadataEntry(name="proposed_by", value=[proposer], data_type="string"),
        DocumentMetadataEntry(name="approved_by", value=[topic.username], data_type="string"),
    ]
    for name in ("ai_model", "tool_call"):
        if provenance.get(name):
            metadata.append(DocumentMetadataEntry(name=name, value=[str(provenance[name])], data_type="string"))
    try:
        record = await documents.create_version(
            project_id=topic.project_id,
            document_id=document_id,
            title=latest.title,
            version_number=str(base_index + 1),
            file_name=latest.file_name,
            size_in_bytes=size,
            sha256=sha256,
            storage_key=key,
            author=proposer,
            metadata=metadata,
            parent_version_index=base_index,
            approved_by=topic.username,
            change_set_id=topic.guid,
            change_set=pack_report(list(change_set.get("changes") or [])),
        )
    except BaseException:
        storage.delete(key)
        raise
    await ifcgraph.approve(proposal_id=str(node["id"]), approved_by=topic.username, version_index=record.version_index)
    await _schedule(ifcgraph, topic.project_id, record.storage_key, record.file_name, record)
    version = record.to_model(api_base(settings))
    await comments.create(
        project_id=topic.project_id,
        topic_guid=topic.guid,
        author=topic.username,
        body=CommentPOST(
            comment=f"Approved as version {record.version_index} of {latest.title}: {version.links.document_version.url}"
        ),
    )
    statuses = (await projects.extensions(topic.project_id) or {}).get("topic_status") or []
    if CLOSED in statuses and topic.topic.topic_status != CLOSED:
        fields = topic.topic.model_dump(include=set(TopicPUT.model_fields))
        body = TopicPUT.model_validate({**fields, "topic_status": CLOSED})
        await topics.update(project_id=topic.project_id, guid=topic.guid, author=topic.username, body=body)
    return version


def _touched(change_set: dict[str, Any]) -> set[str]:
    """The attributes a change set changes, each as one string: `#123.Name` or `<guid>/<path>.Name`."""
    keys = set()
    for change in change_set.get("changes") or []:
        if change.get("step_id") is not None:
            keys.add(f"#{change['step_id']}.{change.get('attribute')}")
        else:
            keys.add(f"{change.get('guid')}/{change.get('path') or ''}.{change.get('attribute')}")
    return keys


async def _collisions(
    ifcgraph: IfcGraphService,
    documents: Any,
    user_id: str,
    project_id: str,
    latest: Any,
    base_index: int,
    node: dict[str, Any],
) -> list[str]:
    """What the change set changes that a version since its base changed too; `*` for a whole-file upload."""
    mine = await anyio.to_thread.run_sync(_change_set, ifcgraph.storage, str(node["snippet_key"]))
    touched: set[str] = set()
    for version in await documents.versions(user_id=user_id, document_id=latest.document_id):
        if not base_index < version.version_index <= latest.version_index:
            continue
        change_set_id = next(
            (entry["value"][0] for entry in version.metadata if entry.get("name") == "change_set_id"), None
        )
        other = await ifcgraph.change_set_of(project_id=project_id, topic_guid=change_set_id) if change_set_id else None
        if other is None:
            return [EVERYTHING]
        touched |= _touched(other)
    return sorted(key for key in _touched(mine) if key in touched)


async def _schedule(ifcgraph: IfcGraphService, project_id: str, key: str, file_name: str, record: Any) -> None:
    """The new version is converted and checked as an upload is."""
    await ifcgraph.schedule(
        project_id=project_id,
        storage_key=key,
        file_name=file_name,
        document_id=record.document_id,
        version_index=record.version_index,
        version_id=record.version_id,
    )
