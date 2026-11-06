# This file was generated with the assistance of an AI coding tool.
"""BCF API 2.1 (https://github.com/buildingSMART/BCF-API/tree/release_2_1), next to 3.0 on the same data.

Most of 2.1 is 3.0: thirty-eight of its forty-one services have the same address, and most of those the same bodies.
A route of 3.0 that answers 2.1's request as it stands is mounted here as well. The others are here as a thin layer
that calls the route of 3.0, which holds the checks of who may do what, and turns the answer into what 2.1 says. This
way the two versions cannot come to disagree about permissions.

What only 2.1 has is the versions, authentication and user services, which 3.0 moved to the Foundation API, and what
only 3.0 has (the files information and deleting a viewpoint) is left out.
"""

from __future__ import annotations

import re
from copy import copy
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response
from fastapi.routing import APIRoute

from opencde.auth.dependencies import PrincipalDep
from opencde.auth.routes import RegistrationRequest, registered
from opencde.bcf import (
    events,
    routes_comments,
    routes_documents,
    routes_events,
    routes_projects,
    routes_topic_links,
    routes_topics,
    routes_viewpoints,
)
from opencde.bcf.access import ProjectContext, ProjectCtx
from opencde.bcf.comments import CommentsDep
from opencde.bcf.odata_params import ODataDep
from opencde.bcf.routes_comments import CommentId
from opencde.bcf.routes_topics import TopicId
from opencde.bcf.routes_viewpoints import ViewpointId
from opencde.bcf.schemas import CommentGET, dump
from opencde.bcf.schemas_v21 import (
    CommentPOST21,
    CommentPUT21,
    DocumentReferencePOST21,
    FileRef21,
    TopicPOST21,
    ViewpointPOST21,
)
from opencde.bcf.topic_access import TopicCtx, TopicsDep
from opencde.bcf.topic_links import LinksDep
from opencde.bcf.viewpoints import ViewpointsDep
from opencde.deps import ClientsDep, GraphDep, ProjectsDep, SettingsDep
from opencde.foundation.routes import CurrentUser, auth_payload_v21, versions_payload
from opencde.ifcgraph.service import IfcGraphDep
from opencde.ratelimit import limiter, registration_limit

TAG = "BCF API 2.1"
PROJECT = "/projects/{project_id}"
TOPIC = f"{PROJECT}/topics/{{topic_id}}"

router = APIRouter(prefix="/bcf/2.1", tags=[TAG])
# The versions service is public and has no version in its address.
public_router = APIRouter(tags=[TAG])

IncludeAuthorization = Annotated[bool, Query(alias="includeAuthorization")]


@public_router.get("/bcf/versions", summary="3.1 Versions Service")
async def versions(settings: SettingsDep) -> dict[str, Any]:
    """Every version of the BCF API on this server. ``GET /foundation/versions`` says the same with the other APIs."""
    return {"versions": [item for item in versions_payload(settings)["versions"] if item["api_id"] == "bcf"]}


@router.get("/auth", summary="3.2.1 Obtaining Authentication Information")
async def auth(settings: SettingsDep) -> dict[str, Any]:
    return auth_payload_v21(settings)


@router.post("/oauth2/reg", summary="3.2.3 Dynamic Client Registration", status_code=201)
@limiter.limit(registration_limit)
async def register_client(
    request: Request, body: RegistrationRequest, clients: ClientsDep, settings: SettingsDep, graph: GraphDep
) -> Response:
    """Register a client, as ``oauth2_dynamic_client_reg_url`` in ``auth`` says. A confidential client registered here
    may sign in as 2.1's example does, without PKCE. Available only when ``OPENCDE_DYNAMIC_CLIENT_REGISTRATION`` is on."""
    return await registered(request, body, clients, settings, graph, without_pkce=True)


@router.get("/current-user", summary="3.3.1 Get current user", response_model=CurrentUser)
async def current_user(principal: PrincipalDep) -> CurrentUser:
    return CurrentUser(id=principal.username, name=principal.display_name)


# -- events first, so that /topics/events is not taken for a topic -------------------------------


@router.get(f"{PROJECT}/topics/events", summary="4.9.1 GET Topics Events")
async def topics_events_get(ctx: ProjectCtx, graph: GraphDep, odata: ODataDep) -> list[dict[str, Any]]:
    return await routes_events.of_project(ctx, graph, odata, "topic", events.NOT_IN_21)


@router.get(f"{PROJECT}/topics/comments/events", summary="4.10.1 GET Comments Events")
async def comments_events_get(ctx: ProjectCtx, graph: GraphDep, odata: ODataDep) -> list[dict[str, Any]]:
    return await routes_events.of_project(ctx, graph, odata, "comment", events.NOT_IN_21)


@router.get(f"{TOPIC}/events", summary="4.9.2 GET Topic Events")
async def topic_events_get(topic: TopicCtx, graph: GraphDep, odata: ODataDep) -> list[dict[str, Any]]:
    return await routes_events.of_topic(topic, graph, odata, events.NOT_IN_21)


@router.get(f"{TOPIC}/comments/{{comment_id}}/events", summary="4.10.2 GET Comment Events")
async def comment_events_get(
    topic: TopicCtx, comment_id: CommentId, graph: GraphDep, comments: CommentsDep, odata: ODataDep
) -> list[dict[str, Any]]:
    return await routes_events.of_comment(topic, comment_id, graph, comments, odata, events.NOT_IN_21)


# -- project extensions ---------------------------------------------------------------------------


@router.get(f"{PROJECT}/extensions", summary="4.1.4 GET Project Extension Service")
async def extensions_get(ctx: ProjectCtx, projects: ProjectsDep) -> dict[str, Any]:
    body = await routes_projects.extensions_get(ctx, projects)
    body["user_id_type"] = body.pop("users")
    return body


# -- topics ---------------------------------------------------------------------------------------


def _topic(body: dict[str, Any]) -> dict[str, Any]:
    """``server_assigned_id`` came with 3.0."""
    body.pop("server_assigned_id", None)
    return body


@router.get(f"{PROJECT}/topics", summary="4.2.1 GET Topics Service")
async def topics_get(
    ctx: ProjectCtx,
    topics: TopicsDep,
    projects: ProjectsDep,
    odata: ODataDep,
    include_authorization: IncludeAuthorization = False,
) -> list[dict[str, Any]]:
    found = await routes_topics.topics_get(ctx, topics, projects, odata, include_authorization)
    return [_topic(body) for body in found]


@router.post(f"{PROJECT}/topics", summary="4.2.2 POST Topic Service", status_code=201)
async def topic_post(ctx: ProjectCtx, body: TopicPOST21, topics: TopicsDep, projects: ProjectsDep) -> dict[str, Any]:
    return _topic(await routes_topics.topic_post(ctx, body, topics, projects))


@router.get(TOPIC, summary="4.2.3 GET Topic Service")
async def topic_get(
    ctx: ProjectCtx,
    topic_id: TopicId,
    topics: TopicsDep,
    projects: ProjectsDep,
    include_authorization: IncludeAuthorization = False,
) -> dict[str, Any]:
    return _topic(await routes_topics.topic_get(ctx, topic_id, topics, projects, include_authorization))


@router.put(TOPIC, summary="4.2.4 PUT Topic Service")
async def topic_put(
    ctx: ProjectCtx, topic_id: TopicId, body: routes_topics.TopicPUT, topics: TopicsDep, projects: ProjectsDep
) -> dict[str, Any]:
    return _topic(await routes_topics.topic_put(ctx, topic_id, body, topics, projects))


# -- header files --------------------------------------------------------------------------------


def _file(body: dict[str, Any]) -> dict[str, Any]:
    return {"file_name" if name == "filename" else name: value for name, value in body.items()}


@router.get(f"{TOPIC}/files", summary="4.3.1 GET Files (Header) Service")
async def files_get(topic: TopicCtx, links: LinksDep) -> list[dict[str, Any]]:
    return [_file(body) for body in await routes_topic_links.files_get(topic, links)]


@router.put(f"{TOPIC}/files", summary="4.3.2 PUT Files (Header) Service")
async def files_put(topic: TopicCtx, body: list[FileRef21], links: LinksDep) -> list[dict[str, Any]]:
    return [_file(item) for item in await routes_topic_links.files_put(topic, list(body), links)]


# -- comments: 2.1 has replies, and the routes of 3.0 leave them out of what they answer -----------


def _comment(comment: CommentGET, ctx: ProjectContext, include: bool) -> dict[str, Any]:
    return dump(routes_comments.authorized(comment, ctx, include))


@router.get(f"{TOPIC}/comments", summary="4.4.1 GET Comments Service")
async def comments_get(
    topic: TopicCtx, comments: CommentsDep, odata: ODataDep, include_authorization: IncludeAuthorization = False
) -> list[dict[str, Any]]:
    found = await routes_comments.found_comments(topic, comments, odata)
    return [_comment(comment, topic.project, include_authorization) for comment in found]


@router.post(f"{TOPIC}/comments", summary="4.4.2 POST Comment Service", status_code=201)
async def comment_post(topic: TopicCtx, body: CommentPOST21, comments: CommentsDep) -> dict[str, Any]:
    comment = await routes_comments.create_comment(topic, body, comments, reply_to=body.reply_to_comment_guid)
    return _comment(comment, topic.project, True)


@router.get(f"{TOPIC}/comments/{{comment_id}}", summary="4.4.3 GET Comment Service")
async def comment_get(
    topic: TopicCtx, comment_id: CommentId, comments: CommentsDep, include_authorization: IncludeAuthorization = False
) -> dict[str, Any]:
    comment = await routes_comments.found_comment(topic, comment_id, comments)
    return _comment(comment, topic.project, include_authorization)


@router.put(f"{TOPIC}/comments/{{comment_id}}", summary="4.4.4 PUT Comment Service")
async def comment_put(
    topic: TopicCtx, comment_id: CommentId, body: CommentPUT21, comments: CommentsDep
) -> dict[str, Any]:
    comment = await routes_comments.update_comment(
        topic, comment_id, body, comments, change_reply=True, reply_to=body.reply_to_comment_guid
    )
    return _comment(comment, topic.project, True)


# -- viewpoints -----------------------------------------------------------------------------------


def _viewpoint(body: dict[str, Any]) -> dict[str, Any]:
    """A viewpoint's ``authorization`` and a camera's ``aspect_ratio`` came with 3.0."""
    body.pop("authorization", None)
    for camera in ("orthogonal_camera", "perspective_camera"):
        if camera in body:
            body[camera].pop("aspect_ratio", None)
    return body


@router.get(f"{TOPIC}/viewpoints", summary="4.5.1 GET Viewpoints Service")
async def viewpoints_get(topic: TopicCtx, viewpoints: ViewpointsDep) -> list[dict[str, Any]]:
    return [_viewpoint(body) for body in await routes_viewpoints.viewpoints_get(topic, viewpoints, False)]


@router.post(f"{TOPIC}/viewpoints", summary="4.5.2 POST Viewpoint Service", status_code=201)
async def viewpoint_post(
    topic: TopicCtx, body: ViewpointPOST21, viewpoints: ViewpointsDep, ifcgraph: IfcGraphDep
) -> dict[str, Any]:
    return _viewpoint(await routes_viewpoints.viewpoint_post(topic, body, viewpoints, ifcgraph))


@router.get(f"{TOPIC}/viewpoints/{{viewpoint_id}}", summary="4.5.3 GET Viewpoint Service")
async def viewpoint_get(topic: TopicCtx, viewpoint_id: ViewpointId, viewpoints: ViewpointsDep) -> dict[str, Any]:
    return _viewpoint(await routes_viewpoints.viewpoint_get(topic, viewpoint_id, viewpoints, False))


# -- document references -------------------------------------------------------------------------


@router.post(f"{TOPIC}/document_references", summary="4.7.2 POST Document Reference Service", status_code=201)
async def document_reference_post(topic: TopicCtx, body: DocumentReferencePOST21, links: LinksDep) -> dict[str, Any]:
    return await routes_topic_links.document_reference_post(topic, body, links)


# -- the routes of 3.0 that answer 2.1 as they stand -----------------------------------------------


def _as_they_stand(source: APIRouter, *besides: str) -> APIRouter:
    """A copy of the routes of a module of 3.0, as 2.1 calls them: its section 3 is section 4 in 2.1, since 3.0 moved
    2.1's section 3 to the Foundation API."""
    shared = APIRouter()
    for route in source.routes:
        if isinstance(route, APIRoute) and route.name not in besides:
            twin = copy(route)
            twin.tags = []
            twin.summary = re.sub(r"^3\.", "4.", route.summary or "")
            shared.routes.append(twin)
    return shared


for _source, _besides in (
    (routes_projects.router, ("extensions_get",)),
    (routes_topics.router, ("topics_get", "topic_post", "topic_get", "topic_put")),
    (routes_comments.router, ("comments_get", "comment_post", "comment_get", "comment_put")),
    (routes_viewpoints.router, ("viewpoints_get", "viewpoint_post", "viewpoint_get", "viewpoint_delete")),
    (routes_topic_links.router, ("files_get", "files_put", "document_reference_post")),
    (routes_documents.router, ("files_information_get",)),
):
    router.include_router(_as_they_stand(_source, *_besides))
