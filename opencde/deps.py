# This file was generated with the assistance of an AI coding tool.
"""FastAPI dependencies that hand routes the shared application objects."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from opencde.accounts.projects import ProjectRepository
from opencde.accounts.users import UserRepository
from opencde.auth.clients import ClientRepository
from opencde.graph.graph import Graph
from opencde.settings import Settings
from opencde.storage import LocalStorage


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_graph(request: Request) -> Graph:
    return request.app.state.graph


def get_storage(request: Request) -> LocalStorage:
    return request.app.state.storage


def get_users(graph: Annotated[Graph, Depends(get_graph)]) -> UserRepository:
    return UserRepository(graph)


def get_projects(graph: Annotated[Graph, Depends(get_graph)]) -> ProjectRepository:
    return ProjectRepository(graph)


def get_clients(
    graph: Annotated[Graph, Depends(get_graph)], settings: Annotated[Settings, Depends(get_settings)]
) -> ClientRepository:
    return ClientRepository(graph, allow_localhost_redirects=settings.allow_localhost_redirects)


def client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


SettingsDep = Annotated[Settings, Depends(get_settings)]
GraphDep = Annotated[Graph, Depends(get_graph)]
StorageDep = Annotated[LocalStorage, Depends(get_storage)]
UsersDep = Annotated[UserRepository, Depends(get_users)]
ProjectsDep = Annotated[ProjectRepository, Depends(get_projects)]
ClientsDep = Annotated[ClientRepository, Depends(get_clients)]
