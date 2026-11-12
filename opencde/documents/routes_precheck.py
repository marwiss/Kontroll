# This file was generated with the assistance of an AI coding tool.
"""Checking an IFC file without making it a version: an extension of the Documents API (ADR 0021).

``POST /documents/1.0/projects/{project_id}/ifc-precheck`` takes the file as the request body, as the BCF API takes a
document, and runs the checks an upload gets: the IFC schema, buildingSMART's rules where installed and the project's
IDS documents. ``GET …/ifc-precheck/{id}`` gives the report in the form of a version's report, with the file's name
and when the precheck expires: a day after it was made, when the cleanup job deletes it and the file. An upload a
project refused for its errors is kept the same way, so that its report can be read. The same bearer token as the
Documents API; starting a precheck needs the ``createDocument`` action, reading one needs membership.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Path, Request, Response
from pydantic import Field

from opencde.accounts.roles import project_actions
from opencde.auth.dependencies import DocumentsPrincipal
from opencde.bcf.binary import filename_from_content_disposition, receive_upload
from opencde.deps import SettingsDep, StorageDep, UsersDep
from opencde.documents.links import api_base, precheck_url
from opencde.documents.validation import IfcValidationReport, Validation, report
from opencde.ids import is_uuid, new_id, normalize_guid
from opencde.ifcgraph.service import IfcGraphDep, IfcGraphService
from opencde.ratelimit import RATE_UPLOAD, limiter
from opencde.storage import make_key

TAG = "IFC validation (extension)"

router = APIRouter(prefix="/documents/1.0", tags=[TAG])

ProjectId = Annotated[str, Path(alias="project_id", max_length=64)]
PrecheckId = Annotated[str, Path(alias="precheck_id", max_length=64)]
DEFAULT_FILENAME = "model.ifc"


class IfcPrecheckReport(IfcValidationReport):
    id: str
    file_name: str
    created_at: str = Field(description="When the file was received, ISO 8601 in UTC.")
    expires_at: str = Field(description="When the precheck and its file are deleted: a day after `created_at`.")
    url: str


def _report(settings: Any, node: dict[str, Any]) -> IfcPrecheckReport:
    validation = Validation(
        state=str(node["state"]),
        issue_count=None if node.get("issue_count") is None else int(node["issue_count"]),
        error_count=None if node.get("error_count") is None else int(node["error_count"]),
        truncated=bool(node.get("truncated")),
        checked_at=node.get("checked_at"),
        ruleset=node.get("ruleset"),
        issues=node["issues"],
        checks=node["checks"],
        rooms=node.get("rooms"),
    )
    return IfcPrecheckReport(
        **report(validation).model_dump(),
        id=str(node["id"]),
        file_name=str(node["file_name"]),
        created_at=str(node["created_at"]),
        expires_at=str(node["expires_at"]),
        url=precheck_url(api_base(settings), str(node["project_id"]), str(node["id"])),
    )


async def _service(
    ifcgraph: IfcGraphService | None, settings: Any, users: Any, user_id: str, project_id: str, *, to_start: bool
) -> tuple[IfcGraphService, str]:
    """The service and the project id, for a member of the project on a server that checks uploads."""
    if ifcgraph is None or not settings.ifcgraph_enabled or not settings.ifcgraph_validate_uploads:
        raise HTTPException(404, "Checking IFC files is off on this server")
    if not is_uuid(project_id):
        raise HTTPException(404, "Project not found")
    pid = normalize_guid(project_id)
    role = await users.project_role(user_id, pid)
    if role is None:
        raise HTTPException(404, "Project not found")
    if to_start and "createDocument" not in project_actions(role):
        raise HTTPException(403, "You may not add documents to this project")
    return ifcgraph, pid


@router.post(
    "/projects/{project_id}/ifc-precheck",
    summary="Check an IFC file against the schema and the project's rules without making it a version",
    response_model=IfcPrecheckReport,
    response_model_exclude_none=True,
    status_code=202,
)
@limiter.limit(RATE_UPLOAD)
async def start_precheck(
    request: Request,
    response: Response,
    principal: DocumentsPrincipal,
    project_id: ProjectId,
    ifcgraph: IfcGraphDep,
    settings: SettingsDep,
    users: UsersDep,
    storage: StorageDep,
) -> IfcPrecheckReport:
    """The file is the request body and its name is in `Content-Disposition`; `.ifc`, `.ifczip` and `.ifcxml`.

    The checks run in the background; `GET` the answer's `url` until its status is no longer `pending`. Needs the
    `createDocument` action. 404 when the project is not yours or the server does not check uploads.
    """
    service, pid = await _service(ifcgraph, settings, users, principal.user_id, project_id, to_start=True)
    file_name = filename_from_content_disposition(request.headers.get("content-disposition")) or DEFAULT_FILENAME
    if not service.wants(file_name):
        raise HTTPException(400, "Only .ifc, .ifczip and .ifcxml files are checked")
    precheck_id = new_id()
    key = make_key("prechecks", precheck_id)
    size = await receive_upload(request, storage, key, settings.max_upload_bytes)
    if size == 0:
        storage.delete(key)
        raise HTTPException(400, "The file is empty")
    try:
        await service.schedule_precheck(
            precheck_id=precheck_id, project_id=pid, storage_key=key, file_name=file_name, author=principal.username
        )
    except BaseException:
        storage.delete(key)
        raise
    node = await service.precheck(user_id=principal.user_id, project_id=pid, precheck_id=precheck_id)
    if node is None:  # the project vanished under us
        raise HTTPException(404, "Project not found")
    response.headers["Location"] = precheck_url(api_base(settings), pid, precheck_id)
    return _report(settings, node)


@router.get(
    "/projects/{project_id}/ifc-precheck/{precheck_id}",
    summary="Get the report of a precheck",
    response_model=IfcPrecheckReport,
    response_model_exclude_none=True,
)
async def get_precheck(
    principal: DocumentsPrincipal,
    project_id: ProjectId,
    precheck_id: PrecheckId,
    ifcgraph: IfcGraphDep,
    settings: SettingsDep,
    users: UsersDep,
) -> IfcPrecheckReport:
    """Every issue the checks found, as for a version; `pending` until they are done. 404 once it has expired."""
    service, pid = await _service(ifcgraph, settings, users, principal.user_id, project_id, to_start=False)
    if not is_uuid(precheck_id):
        raise HTTPException(404, "Precheck not found")
    node = await service.precheck(user_id=principal.user_id, project_id=pid, precheck_id=normalize_guid(precheck_id))
    if node is None:
        raise HTTPException(404, "Precheck not found")
    return _report(settings, node)
