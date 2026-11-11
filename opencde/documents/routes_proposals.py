# This file was generated with the assistance of an AI coding tool.
"""The proposals against a document: an extension of the Documents API (ADR 0021).

``GET /documents/1.0/documents/{id}/ifc-proposals`` lists, for a member of the document's project, every change
set tried against the document, newest first: the topic that carries it, the trial's state and where the trial
and its approval are (``bcf/routes_proposals.py``). The same bearer token as the Documents API reaches it; the
list is cut at the server's limit and says so with ``X-Total-Count`` and ``Link``, as the BCF lists are.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Path, Request
from pydantic import BaseModel, ConfigDict, Field

from opencde.auth.dependencies import DocumentsPrincipal
from opencde.bcf.odata_params import ODataDep
from opencde.deps import SettingsDep
from opencde.ids import is_uuid, normalize_guid
from opencde.store.documents.versions import DocumentsDep
from opencde.store.jobs.proposals import DEFAULT_ORDER, FIELDS, ORDERABLE, ProposalsDep

TAG = "IFC change sets (extension)"

router = APIRouter(prefix="/documents/1.0", tags=[TAG])

DocumentId = Annotated[str, Path(alias="document_id", max_length=64)]
MAX_DESCRIPTION = 200  # the characters of the topic's description a row keeps


class IfcProposalEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic_guid: str = Field(description="The topic whose snippet is the change set.")
    title: str = Field(description="The topic's title.")
    description: str | None = Field(
        None, description=f"The topic's description, cut to {MAX_DESCRIPTION} characters; null when it has none."
    )
    state: str = Field(
        description="`queued` or `running` until the trial is over; then `clean`, `issues` or `failed`, and "
        "`approved` once a clean trial became a version."
    )
    base_version_index: int = Field(description="The version of the document the change set was tried on.")
    change_count: int | None = Field(None, description="How many changes the set holds; null until the trial ran.")
    author: str = Field(description="Who proposed the change set.")
    checked_at: str | None = Field(None, description="When the trial ended, ISO 8601 in UTC; null until then.")
    version_index: int | None = Field(None, description="The version it became, when it is `approved`; else null.")
    proposal_url: str = Field(
        description="The trial: `GET /bcf/3.0/projects/{project_id}/topics/{topic_guid}/ifc-proposal`."
    )
    approve_url: str = Field(description="Its approval: `POST …/ifc-proposal/approve`, for those who may.")


def _entry(base_url: str, row: dict[str, Any]) -> IfcProposalEntry:
    """A row of the listing from the repository's columns; ``base_url`` is the server's, without a trailing slash."""
    proposal_url = f"{base_url}/bcf/3.0/projects/{row['project_id']}/topics/{row['topic_guid']}/ifc-proposal"
    description = row.get("description")
    return IfcProposalEntry(
        topic_guid=str(row["topic_guid"]),
        title=str(row["title"]),
        description=str(description)[:MAX_DESCRIPTION] if description else None,
        state=str(row["state"]),
        base_version_index=int(row["base_version_index"]),
        change_count=None if row.get("change_count") is None else int(row["change_count"]),
        author=str(row["author"]),
        checked_at=row.get("checked_at"),
        version_index=None if row.get("version_index") is None else int(row["version_index"]),
        proposal_url=proposal_url,
        approve_url=proposal_url + "/approve",
    )


@router.get(
    "/documents/{document_id}/ifc-proposals",
    summary="List the change sets tried against a document, newest first",
    response_model=list[IfcProposalEntry],
)
async def ifc_proposals(
    request: Request,
    principal: DocumentsPrincipal,
    document_id: DocumentId,
    documents: DocumentsDep,
    proposals: ProposalsDep,
    settings: SettingsDep,
    odata: ODataDep,
) -> list[IfcProposalEntry]:
    """One row per proposal: the topic, the trial's state, the base version, who proposed it, the version an
    approved one became, and the addresses of the trial and its approval. `$top` and `$skip` as in the BCF lists;
    a list the server cut carries `X-Total-Count` and `Link: <…>; rel="next"`. 404 for a document the member may
    not see, and when the IFC-LPG module is off."""
    if not settings.ifcgraph_enabled:
        raise HTTPException(404, "Change sets are not tried on this server: the IFC-LPG module is off")
    if not is_uuid(document_id):
        raise HTTPException(404, "Document not found")
    document_id = normalize_guid(document_id)
    if await documents.latest(user_id=principal.user_id, document_id=document_id) is None:
        raise HTTPException(404, "Document not found")
    compiled = odata.compile(FIELDS, ORDERABLE, DEFAULT_ORDER)
    rows = await proposals.of_document(user_id=principal.user_id, document_id=document_id, compiled=compiled)
    await odata.say_if_cut(
        compiled,
        len(rows),
        lambda: proposals.count(user_id=principal.user_id, document_id=document_id, compiled=compiled),
    )
    base_url = str(request.base_url).rstrip("/")
    return [_entry(base_url, row) for row in rows]
