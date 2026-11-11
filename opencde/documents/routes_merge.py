# This file was generated with the assistance of an AI coding tool.
"""A building of one model into another project's model: an extension of the Documents API (IFC-LPG F21 a and
F22 a, ADR 0025).

The building of model B, a version of any project the caller is a member of, comes into the project of model A, a
version of this project, as the next version of A's document; A and B do not change. ``POST …/ifc-merge/report``
says what that would do, for any member of both projects: what comes along, the objects with a GlobalId that both
have, whether their content is the same, and the choice that holds for each (``a`` keeps A's, ``b`` puts B's in its
place, ``new`` keeps both with a new GlobalId for B's). ``POST …/ifc-merge`` lets a ``manager`` of this project make
it, with a choice for each object that differs or one ``default`` for them all, as a job: the merged model is checked
against A and B, written out, made the next version of A's document with A's version as its parent, and converted
and checked as an upload is. ``GET …/ifc-merge/{id}`` follows the job.

Where B's schema or length unit is not A's, ``POST …/ifc-merge/prepare`` first makes a copy of B migrated to A's
schema and with its lengths in A's unit (IFC-LPG F25 a), as a job of its own; its id, given as ``other.prepared``,
makes that copy stand in for B in the report and the merge for a day. What A's schema has no equivalent of, such as
IFC2X3's IfcWindowStyle in IFC4X3, ends the preparation in ``conflict`` with the problems and the options for each;
the caller prepares again with ``resolutions`` (IFC-LPG F32). A copy with issues B did not have is refused (F33 a).
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Path, Request, Response
from ifc_lpg.merge import MergeError
from pydantic import BaseModel, Field, field_validator

from opencde.accounts.roles import Role, at_least
from opencde.auth.dependencies import DocumentsPrincipal
from opencde.deps import SettingsDep, UsersDep
from opencde.documents.changes import GUID
from opencde.errors import CODE_VERSION_CONFLICT, ApiError
from opencde.ids import is_uuid, normalize_guid
from opencde.ifcgraph import merging
from opencde.ifcgraph.service import IfcGraphDep, IfcGraphService
from opencde.store.documents.versions import DocumentsDep
from opencde.store.oauth2.tokens import Principal

TAG = "IFC merge (extension)"

router = APIRouter(prefix="/documents/1.0", tags=[TAG])

ProjectId = Annotated[str, Path(alias="project_id", max_length=64)]
MergeId = Annotated[str, Path(alias="merge_id", max_length=64)]
Choice = Literal["a", "b", "new"]
MAX_CHOICES = 100_000


class IfcMergeBase(BaseModel):
    document_id: str = Field(max_length=64, description="The document of model A, in this project.")
    version_index: int = Field(ge=1, le=1_000_000_000, description="A's version: the latest, for a merge.")


class IfcMergeOther(BaseModel):
    project_id: str = Field(max_length=64, description="The project of model B; this project or another of yours.")
    document_id: str = Field(max_length=64, description="The document of model B.")
    version_index: int = Field(ge=1, le=1_000_000_000, description="B's version.")
    prepared: str | None = Field(
        None,
        max_length=64,
        description="A preparation of this version of B for this base (`POST …/ifc-merge/prepare`), done: its copy of "
        "B, migrated to A's schema and with A's length unit, stands in for B.",
    )


MAX_RESOLUTIONS = 100


class IfcMergePrepareRequest(BaseModel):
    base: IfcMergeBase
    other: IfcMergeOther
    resolutions: dict[str, str] | None = Field(
        None,
        max_length=MAX_RESOLUTIONS,
        description="For each problem of an earlier `conflict`, by its `key`, one of its `options`: `type`, `proxy`, "
        "`leave_out`, `polyline`, `owner`, `virtual`, `dated`, `assignment` or `context`.",
    )

    @field_validator("resolutions")
    @classmethod
    def _known_resolutions(cls, value: dict[str, str] | None) -> dict[str, str] | None:
        for key, choice in (value or {}).items():
            if len(key) > 64 or choice not in merging.RESOLUTIONS:
                raise ValueError(f"a resolution is one of {', '.join(merging.RESOLUTIONS)}, not {choice!r}")
        return value


class IfcMergeRequest(BaseModel):
    base: IfcMergeBase
    other: IfcMergeOther
    building: str = Field(pattern=GUID, description="The GlobalId of B's building that comes into A's project.")
    site: str | None = Field(None, pattern=GUID, description="The GlobalId of A's site, when A has more than one.")
    choices: dict[str, Choice] = Field(
        default_factory=dict,
        max_length=MAX_CHOICES,
        description="For a GlobalId that both have and whose content differs: `a`, `b` or `new`.",
    )
    default: Choice | None = Field(None, description="The choice for every differing object `choices` does not name.")


class IfcMergeJob(BaseModel):
    merge_id: str
    kind: str = Field(description="`merge`, or `prepare` for a copy of B made ready for A.")
    state: str = Field(
        description="`queued`, `running`, `done`, `conflict` (a differing object has no choice), `failed`, or `expired` "
        "for a prepared copy whose day is over."
    )
    expires_at: str | None = Field(None, description="Until when a prepared copy stands in for B.")
    resolutions: dict[str, str] | None = Field(None, description="The choices a preparation was made with.")
    author: str | None = None
    created_at: str | None = None
    finished_at: str | None = None
    base: dict[str, Any] | None = None
    other: dict[str, Any] | None = None
    building: str | None = None
    version_index: int | None = Field(None, description="The version the merge became, when it is `done`.")
    error: str | None = None
    report: dict[str, Any] | None = Field(None, description="What the merge did, or the objects it lacks a choice for.")
    url: str


def _url(request: Request, project_id: str, merge_id: str) -> str:
    return str(request.base_url).rstrip("/") + f"/documents/1.0/projects/{project_id}/ifc-merge/{merge_id}"


async def _service(
    ifcgraph: IfcGraphService | None, settings: Any, users: Any, user_id: str, project_id: str
) -> tuple[IfcGraphService, str, Role]:
    """The service, the project id and the caller's role, for a member of the project with the module on."""
    if ifcgraph is None or not settings.ifcgraph_enabled:
        raise HTTPException(404, "The IFC-LPG module is off on this server")
    if not is_uuid(project_id):
        raise HTTPException(404, "Project not found")
    pid = normalize_guid(project_id)
    role = await users.project_role(user_id, pid)
    if role is None:
        raise HTTPException(404, "Project not found")
    return ifcgraph, pid, role


async def _resolved(
    service: IfcGraphService, principal: Principal, project_id: str, body: IfcMergeRequest | IfcMergePrepareRequest
) -> dict[str, Any]:
    """The request with the converted models of both versions, each found from the caller's own memberships, and a
    prepared copy of B in B's place where one is named."""
    spec = body.model_dump()
    sides = (("base", project_id), ("other", body.other.project_id))
    for side, side_project in sides:
        if not is_uuid(spec[side]["document_id"]) or not is_uuid(side_project):
            raise HTTPException(404, "No converted model of that version")
        spec[side]["document_id"] = normalize_guid(spec[side]["document_id"])
        model = await service.model_of_version(
            user_id=principal.user_id,
            project_id=normalize_guid(side_project),
            document_id=spec[side]["document_id"],
            version_index=spec[side]["version_index"],
        )
        if model is None:
            raise HTTPException(404, f"No converted model of the {side} version")
        spec[side]["model_id"] = model["id"]
    spec["other"]["project_id"] = normalize_guid(body.other.project_id)
    prepare_id = spec["other"].pop("prepared", None)
    if prepare_id is not None:
        found = (
            await merging.prepared(
                service, user_id=principal.user_id, project_id=project_id, prepare_id=normalize_guid(prepare_id)
            )
            if is_uuid(prepare_id)
            else None
        )
        same = found is not None and all(
            found["request"][side][key] == spec[side][key]
            for side, keys in (("base", ("document_id", "version_index")), ("other", ("document_id", "version_index")))
            for key in keys
        )
        if found is None or not same:
            raise HTTPException(404, "No prepared copy of that version of B for that base; prepare it again")
        spec["other"]["model_id"] = found["model_id"]
        spec["other"]["prepared"] = normalize_guid(prepare_id)
    return spec


def _public(report: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    """The report with the documents' versions where IFC-LPG names its models."""
    shown = {key: value for key, value in report.items() if key not in ("base", "other", "model")}
    shown["base"] = {key: spec["base"][key] for key in ("document_id", "version_index")}
    shown["other"] = {key: spec["other"][key] for key in ("project_id", "document_id", "version_index")}
    return shown


@router.post(
    "/projects/{project_id}/ifc-merge/report",
    summary="What bringing a building of one model into this project's model would do",
)
async def merge_report(
    principal: DocumentsPrincipal,
    project_id: ProjectId,
    body: IfcMergeRequest,
    ifcgraph: IfcGraphDep,
    settings: SettingsDep,
    users: UsersDep,
) -> dict[str, Any]:
    """`objects` and `instances` count what comes along; `collisions` lists the objects with a GlobalId that both
    have, with `same` and the `choice` that holds for each (`null` while none is made); `left_out` lists the
    relationships that point outside the building alone; `contexts` and `placements` say what A's stand in for.

    For a member of both projects. 404 when either version has no converted model, 422 when the building cannot be
    brought in at all, such as for a different schema or length unit, with the reason."""
    service, pid, _role = await _service(ifcgraph, settings, users, principal.user_id, project_id)
    spec = await _resolved(service, principal, pid, body)
    try:
        found = await merging.report(service, spec)
    except MergeError as exc:
        raise HTTPException(422, f"The building cannot be brought in: {exc}") from None
    return _public(found, spec)


@router.post(
    "/projects/{project_id}/ifc-merge",
    summary="Bring a building of one model into this project's model, as the next version of its document",
    response_model=IfcMergeJob,
    response_model_exclude_none=True,
    status_code=202,
)
async def start_merge(
    request: Request,
    response: Response,
    principal: DocumentsPrincipal,
    project_id: ProjectId,
    body: IfcMergeRequest,
    ifcgraph: IfcGraphDep,
    settings: SettingsDep,
    users: UsersDep,
    documents: DocumentsDep,
) -> IfcMergeJob:
    """A `manager` of this project makes the merge, which runs in the background; `GET` the answer's `url` until its
    state is `done` (with `version_index`), `conflict` (with the objects that lack a choice) or `failed`.

    A's version must be the document's latest: 412 `version_conflict` otherwise. 403 for other roles; 404 when either
    version has no converted model; 422 when the building cannot be brought in, with the reason."""
    service, pid, role = await _service(ifcgraph, settings, users, principal.user_id, project_id)
    if not at_least(role, Role.MANAGER):
        raise HTTPException(403, "Only a manager brings a building into the project")
    spec = await _resolved(service, principal, pid, body)
    latest = await documents.latest(user_id=principal.user_id, document_id=spec["base"]["document_id"])
    if latest is None or latest.project_id != pid:
        raise HTTPException(404, "No converted model of the base version")
    if latest.version_index != spec["base"]["version_index"]:
        raise ApiError(
            412,
            f"The merge builds on version {spec['base']['version_index']}, but the document's latest version is "
            f"{latest.version_index}; merge into the latest",
            code=CODE_VERSION_CONFLICT,
        )
    try:
        await merging.report(service, spec)  # what cannot be merged at all is refused now, not in the job
    except MergeError as exc:
        raise HTTPException(422, f"The building cannot be brought in: {exc}") from None
    merge_id = await merging.schedule(service, project_id=pid, author=principal.username, request=spec)
    found = await merging.job(service, user_id=principal.user_id, project_id=pid, merge_id=merge_id)
    if found is None:  # the project vanished under us
        raise HTTPException(404, "Project not found")
    response.headers["Location"] = _url(request, pid, merge_id)
    return IfcMergeJob(**found, url=_url(request, pid, merge_id))


@router.post(
    "/projects/{project_id}/ifc-merge/prepare",
    summary="Make a copy of B ready for a merge: migrated to A's schema, with its lengths in A's unit",
    response_model=IfcMergeJob,
    response_model_exclude_none=True,
    status_code=202,
)
async def start_prepare(
    request: Request,
    response: Response,
    principal: DocumentsPrincipal,
    project_id: ProjectId,
    body: IfcMergePrepareRequest,
    ifcgraph: IfcGraphDep,
    settings: SettingsDep,
    users: UsersDep,
) -> IfcMergeJob:
    """For an `editor` or a `manager` of this project who is a member of B's project. The copy is made in the
    background; when the answer's `url` says `done`, give its `merge_id` as `other.prepared` to the report and the
    merge, until `expires_at`. `conflict` lists in `report.problems` what A's schema has no equivalent of, each with
    its `key` and `options`: prepare again with `resolutions`. `failed` with `report.new` means the converted copy
    had issues B did not have, and it was not made; a unit of a kind both have that differs fails it too."""
    service, pid, role = await _service(ifcgraph, settings, users, principal.user_id, project_id)
    if not at_least(role, Role.EDITOR):
        raise HTTPException(403, "Only an editor or a manager prepares a model for a merge")
    if body.other.prepared is not None:
        raise HTTPException(400, "A prepared copy is not prepared again; name B's version")
    spec = await _resolved(service, principal, pid, body)
    job_id = await merging.schedule(
        service, project_id=pid, author=principal.username, request=spec, kind=merging.KIND_PREPARE
    )
    found = await merging.job(service, user_id=principal.user_id, project_id=pid, merge_id=job_id)
    if found is None:  # the project vanished under us
        raise HTTPException(404, "Project not found")
    response.headers["Location"] = _url(request, pid, job_id)
    return IfcMergeJob(**found, url=_url(request, pid, job_id))


@router.get(
    "/projects/{project_id}/ifc-merge/{merge_id}",
    summary="A merge into this project, and what it did",
    response_model=IfcMergeJob,
    response_model_exclude_none=True,
)
async def get_merge(
    request: Request,
    principal: DocumentsPrincipal,
    project_id: ProjectId,
    merge_id: MergeId,
    ifcgraph: IfcGraphDep,
    settings: SettingsDep,
    users: UsersDep,
) -> IfcMergeJob:
    """For every member of this project. 404 for a merge that is not this project's."""
    service, pid, _role = await _service(ifcgraph, settings, users, principal.user_id, project_id)
    if not is_uuid(merge_id):
        raise HTTPException(404, "Merge not found")
    found = await merging.job(service, user_id=principal.user_id, project_id=pid, merge_id=normalize_guid(merge_id))
    if found is None:
        raise HTTPException(404, "Merge not found")
    if found.get("report") is not None and found.get("base") is not None and found["kind"] == merging.KIND_MERGE:
        found["report"] = _public(found["report"], found)
    return IfcMergeJob(**found, url=_url(request, pid, found["merge_id"]))
