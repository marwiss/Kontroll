# This file was generated with the assistance of an AI coding tool.
"""FastAPI dependencies that hand routes the shared application objects."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from opencde.graph.graph import Graph
from opencde.settings import Settings
from opencde.storage import LocalStorage
from opencde.store.accounts.projects import ProjectRepository
from opencde.store.accounts.users import UserRepository
from opencde.store.oauth2.clients import ClientRepository
from opencde.store.protocols import ClientStore, ProjectStore, UserStore


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_graph(request: Request) -> Graph:
    """The graph of the server's own data; the IFC graph is the IFC-LPG service's (F24 a)."""
    return request.app.state.store


def get_storage(request: Request) -> LocalStorage:
    return request.app.state.storage


def get_users(graph: Annotated[Graph, Depends(get_graph)]) -> UserStore:
    return UserRepository(graph)


def get_projects(graph: Annotated[Graph, Depends(get_graph)]) -> ProjectStore:
    return ProjectRepository(graph)


def get_clients(
    graph: Annotated[Graph, Depends(get_graph)], settings: Annotated[Settings, Depends(get_settings)]
) -> ClientStore:
    return ClientRepository(graph, allow_localhost_redirects=settings.allow_localhost_redirects)


def client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


SettingsDep = Annotated[Settings, Depends(get_settings)]
GraphDep = Annotated[Graph, Depends(get_graph)]
StorageDep = Annotated[LocalStorage, Depends(get_storage)]
UsersDep = Annotated[UserStore, Depends(get_users)]
ProjectsDep = Annotated[ProjectStore, Depends(get_projects)]
ClientsDep = Annotated[ClientStore, Depends(get_clients)]
