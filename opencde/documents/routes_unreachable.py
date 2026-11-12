# This file was generated with the assistance of an AI coding tool.
"""Removing what no GlobalId reaches, as a proposal (an extension; IFC-LPG F13 a, OB-10.4, Dataregium F10 a).

The report of a converted version warns of the instances that nothing with a GlobalId reaches, forward or backward
(the check ``graph``). Here the server proposes their removal: a BCF topic whose ``bim_snippet`` is a change set
(``DataregiumIfcChangeSet``) with one ``delete`` per instance, named by its STEP id. The change set is then tried on
its base version and approved by a ``manager`` like any other (``…/ifc-proposal``), so the removal is a version of its
own and the version it came from keeps the instances.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from opencde.bcf.access import ProjectCtx
from opencde.bcf.topic_access import TopicsDep
from opencde.deps import ProjectsDep, SettingsDep, StorageDep
from opencde.documents.changes import MAX_CHANGES, SCHEMA_PATH, problems
from opencde.documents.proposing import Proposing
from opencde.ids import is_uuid
from opencde.ifcgraph.service import IfcGraphDep
from opencde.store.bcf.topic_links import LinksDep
from opencde.timeutil import now_iso

TAG = "IFC change sets (extension)"

router = APIRouter(prefix="/documents/1.0", tags=[TAG])

TOOL_CALL = "ifc-unreachable"  # the provenance of a change set the server proposes here


class IfcUnreachableRequest(BaseModel):
    document_id: str = Field(description="The document whose version has instances no GlobalId reaches.")
    version_index: int = Field(ge=1, le=1_000_000_000, description="The version, the base of the change set.")


class IfcUnreachableProposal(BaseModel):
    topic_guid: str = Field(description="The BCF topic that carries the change set as its `bim_snippet`.")
    title: str = Field(description="The topic's title.")
    changes: int = Field(description="How many instances the change set deletes, one `delete` each.")
    proposal_url: str = Field(description="Where the trial of the change set is reported (`GET …/ifc-proposal`).")


@router.post(
    "/projects/{project_id}/ifc-unreachable",
    summary="Propose removing the instances of a version that no GlobalId reaches",
    response_model=IfcUnreachableProposal,
    status_code=201,
)
async def unreachable_proposal(
    ctx: ProjectCtx,
    body: IfcUnreachableRequest,
    ifcgraph: IfcGraphDep,
    settings: SettingsDep,
    projects: ProjectsDep,
    topics: TopicsDep,
    links: LinksDep,
    storage: StorageDep,
) -> IfcUnreachableProposal:
    """A topic with a change set that deletes, by STEP id, every instance of the version that nothing with a GlobalId
    reaches, tried on the version like any change set; a `manager` approves it into the next version.

    Needs the `bcf` scope and the `createTopic` action, and the role `editor` or `manager`, who propose change sets.
    404 when the version has no converted model, 409 when nothing in it is out of reach.
    """
    if ifcgraph is None or not settings.ifcgraph_enabled:
        raise HTTPException(404, "The IFC-LPG module is off on this server")
    ctx.require(ctx.can("createTopic", entity="project"), "createTopic")
    ctx.require_proposer()
    if not is_uuid(body.document_id):
        raise HTTPException(404, "No converted model of that version")
    model = await ifcgraph.model_of_version(
        user_id=ctx.user_id, project_id=ctx.project_id, document_id=body.document_id, version_index=body.version_index
    )
    if model is None:
        raise HTTPException(404, "No converted model of that version")
    steps = sorted({int(node["step"]) for node in await ifcgraph.unreached(model["id"])})
    if not steps:
        raise HTTPException(409, "Every instance of this version is reached from a GlobalId")
    steps = steps[:MAX_CHANGES]
    base_url = settings.public_url
    change_set = {
        "schema": f"{base_url}{SCHEMA_PATH}",
        "base": {"document_id": body.document_id, "version_index": body.version_index},
        "provenance": {"user": ctx.username, "tool_call": TOOL_CALL, "created_at": now_iso()},
        "changes": [{"step_id": step, "op": "delete"} for step in steps],
    }
    found = problems(change_set)
    if found:  # the server's own change set: a mistake here is the server's, never the caller's
        raise HTTPException(500, "The proposed change set is not one: " + "; ".join(found))
    proposing = Proposing(
        topics=topics, links=links, projects=projects, storage=storage, ifcgraph=ifcgraph, public_url=base_url
    )
    topic = await proposing.topic(
        project_id=ctx.project_id,
        author=ctx.username,
        title=f"Remove what no GlobalId reaches in {model.get('file_name') or 'the model'}, version {body.version_index}",
        description=(
            f"{len(steps)} instances of version {body.version_index} that nothing with a GlobalId reaches, forward "
            "or backward, each deleted by its STEP id. Proposed by the server from the report's check graph; the "
            "version they came from keeps them."
        ),
        change_set=change_set,
        reference="ifc-unreachable.json",
    )
    return IfcUnreachableProposal(
        topic_guid=topic.guid,
        title=topic.title,
        changes=len(steps),
        proposal_url=f"{base_url}/bcf/3.0/projects/{ctx.project_id}/topics/{topic.guid}/ifc-proposal",
    )
