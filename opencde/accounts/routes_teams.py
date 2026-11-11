# This file was generated with the assistance of an AI coding tool.
"""The teams of a project, set up by its managers: an extension outside the OpenCDE specifications (F11 b, F19 a).

``/manage/1.0/projects/{id}/teams`` lists, makes, replaces and removes the teams of a project, with the same token and
the same checks as the project's members: the ``project`` scope, and the role ``manager`` in the project found from the
caller's own user node. A team has a name, a responsible member with at least the role ``editor``, its members, and an
IDS document of the project whose specifications point out the team's part of the model. Who approves a change set
follows from it (``bcf/routes_proposals.py``). Every write leaves an audit event, ``manage.team.set`` or
``manage.team.remove``.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from opencde.accounts.roles import Role, at_least
from opencde.accounts.routes_manage import IdPath, ProjectPrincipal, _managed, _record
from opencde.deps import GraphDep, ProjectsDep
from opencde.ids import is_uuid, normalize_guid
from opencde.store.accounts.teams import MAX_MEMBERS, MAX_TEAMS, TeamsDep

router = APIRouter(prefix="/manage/1.0", tags=["Project administration (extension)"])

IDS_SUFFIX = ".ids"


class TeamIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100, description="What the team is called, such as Structure.")
    responsible: str = Field(
        min_length=1, max_length=100, description="The user name of the member who approves changes to the team's part."
    )
    members: list[str] = Field(default_factory=list, max_length=MAX_MEMBERS, description="The members' user names.")
    ids_document_id: str = Field(
        max_length=64,
        description="An IDS document of the project: the elements its specifications apply to are the part.",
    )


async def _checked(graph: GraphDep, projects: ProjectsDep, project_id: str, body: TeamIn) -> dict[str, Any]:
    """The team's users and document, each held to the project: 400 with what is wrong."""
    members = {user.username: (user, role) for user, role in await projects.members(project_id)}
    responsible = members.get(body.responsible.strip())
    if responsible is None or not at_least(responsible[1], Role.EDITOR):
        raise HTTPException(400, "The responsible must be a member of the project with the role editor or manager")
    missing = [name for name in body.members if name.strip() not in members]
    if missing:
        raise HTTPException(400, f"Not members of the project: {', '.join(sorted(missing)[:10])}")
    if not is_uuid(body.ids_document_id):
        raise HTTPException(400, "ids_document_id names no IDS document of the project")
    document_id = normalize_guid(body.ids_document_id)
    row = await graph.one(
        """
        MATCH (:Project {project_id: $project_id})-[:HAS_DOCUMENT]->(:Document {document_id: $document_id})
              -[:HAS_VERSION]->(v:DocumentVersion)
        WITH v ORDER BY v.version_index DESC LIMIT 1
        RETURN v.file_name AS file_name
        """,
        project_id=project_id,
        document_id=document_id,
    )
    if row is None or not str(row["file_name"]).lower().endswith(IDS_SUFFIX):
        raise HTTPException(400, "ids_document_id names no IDS document of the project")
    return {
        "name": body.name.strip(),
        "responsible_user_id": responsible[0].id,
        "member_ids": [members[name.strip()][0].id for name in body.members],
        "ids_document_id": document_id,
    }


def _shown(team: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in team.items() if key != "responsible_user_id"}


@router.get("/projects/{project_id}/teams", summary="Project administration (extension): the teams and their parts")
async def list_teams(
    principal: ProjectPrincipal, project_id: IdPath, teams: TeamsDep, graph: GraphDep
) -> dict[str, Any]:
    await _managed(graph, principal, project_id)
    found = [_shown(team) for team in await teams.of_project(project_id)]
    return {"items": found, "total": len(found)}


@router.post("/projects/{project_id}/teams", status_code=201, summary="Project administration (extension): make a team")
async def add_team(
    request: Request,
    principal: ProjectPrincipal,
    project_id: IdPath,
    body: TeamIn,
    teams: TeamsDep,
    projects: ProjectsDep,
    graph: GraphDep,
) -> dict[str, Any]:
    await _managed(graph, principal, project_id)
    if len(await teams.of_project(project_id)) >= MAX_TEAMS:
        raise HTTPException(409, f"A project has at most {MAX_TEAMS} teams")
    fields = await _checked(graph, projects, project_id, body)
    team_id = await teams.save(project_id, team_id=None, **fields)
    if team_id is None:
        raise HTTPException(404, "No such project")
    await _record(request, graph, principal, "team.set", project_id=project_id, team_id=team_id)
    return _shown(await teams.get(project_id, team_id) or {})


@router.put("/projects/{project_id}/teams/{team_id}", summary="Project administration (extension): replace a team")
async def set_team(
    request: Request,
    principal: ProjectPrincipal,
    project_id: IdPath,
    team_id: IdPath,
    body: TeamIn,
    teams: TeamsDep,
    projects: ProjectsDep,
    graph: GraphDep,
) -> dict[str, Any]:
    await _managed(graph, principal, project_id)
    if await teams.get(project_id, team_id) is None:
        raise HTTPException(404, "No such team")
    fields = await _checked(graph, projects, project_id, body)
    await teams.save(project_id, team_id=team_id, **fields)
    await _record(request, graph, principal, "team.set", project_id=project_id, team_id=team_id)
    return _shown(await teams.get(project_id, team_id) or {})


@router.delete(
    "/projects/{project_id}/teams/{team_id}",
    status_code=204,
    summary="Project administration (extension): remove a team",
)
async def remove_team(
    request: Request, principal: ProjectPrincipal, project_id: IdPath, team_id: IdPath, teams: TeamsDep, graph: GraphDep
) -> Response:
    await _managed(graph, principal, project_id)
    if not await teams.delete(project_id, team_id):
        raise HTTPException(404, "No such team")
    await _record(request, graph, principal, "team.remove", project_id=project_id, team_id=team_id)
    return Response(status_code=204)
