# This file was generated with the assistance of an AI coding tool.
"""Resolving ``/topics/{topic_id}`` for the services that live under a topic."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Path

from opencde.accounts.roles import Role
from opencde.bcf.access import ProjectContext, ProjectCtx, parse_guid
from opencde.bcf.schemas import TopicGET
from opencde.bcf.topics import TopicRepository
from opencde.deps import GraphDep, SettingsDep

TopicId = Annotated[str, Path(alias="topic_id", max_length=64)]


def topic_repository(graph: GraphDep, settings: SettingsDep) -> TopicRepository:
    return TopicRepository(graph, id_prefix=settings.server_assigned_id_prefix)


TopicsDep = Annotated[TopicRepository, Depends(topic_repository)]


@dataclass(frozen=True)
class TopicContext:
    """The project context plus the topic the request addresses (404 when the caller cannot see it)."""

    project: ProjectContext
    topic: TopicGET

    @property
    def guid(self) -> str:
        return self.topic.guid

    @property
    def project_id(self) -> str:
        return self.project.project_id

    @property
    def user_id(self) -> str:
        return self.project.user_id

    @property
    def username(self) -> str:
        return self.project.username

    @property
    def role(self) -> Role:
        return self.project.role

    def require_topic_action(self, action: str) -> None:
        self.project.require(self.project.can(action, self.topic.creation_author), action)


async def topic_context(ctx: ProjectCtx, topic_id: TopicId, topics: TopicsDep) -> TopicContext:
    guid = parse_guid(topic_id, "Topic")
    topic = await topics.get(user_id=ctx.user_id, project_id=ctx.project_id, guid=guid)
    if topic is None:
        raise HTTPException(404, "Topic not found")
    return TopicContext(project=ctx, topic=topic)


TopicCtx = Annotated[TopicContext, Depends(topic_context)]
