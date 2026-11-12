# This file was generated with the assistance of an AI coding tool.
"""FastAPI dependencies that hand routes the shared application objects."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from opencde.graph.graph import Graph
from opencde.postgres.database import Postgres
from opencde.settings import Settings
from opencde.storage import LocalStorage
from opencde.store.oauth2.postgres import client_store
from opencde.store.protocols import ClientStore, ProjectStore, UserStore


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_graph(request: Request) -> Graph:
    """The graph of the server's own data; the IFC graph is the IFC-DB service's (F24 a)."""
    return request.app.state.store


def get_model_graph(request: Request) -> Graph:
    """The IFC graph, IFC-DB's models apart from the server's own data (ADR 0027): for the models that go when a
    project goes, which a route asks of it through the library alone."""
    return request.app.state.graph


def get_postgres(request: Request) -> Postgres | None:
    """The server's own data in PostgreSQL, when ``OPENCDE_STORE_URL`` names it (ADR 0029): the areas that have
    followed are read there, the others in the graph of ``get_graph``."""
    return getattr(request.app.state, "postgres", None)


def get_storage(request: Request) -> LocalStorage:
    return request.app.state.storage


def get_users(
    graph: Annotated[Graph, Depends(get_graph)], postgres: Annotated[Postgres | None, Depends(get_postgres)]
) -> UserStore:
    from opencde.store.accounts.postgres import user_store  # it imports the modules that import this one

    return user_store(graph, postgres)


def get_projects(
    graph: Annotated[Graph, Depends(get_graph)], postgres: Annotated[Postgres | None, Depends(get_postgres)]
) -> ProjectStore:
    from opencde.store.accounts.postgres import project_store  # it imports the modules that import this one

    return project_store(graph, postgres)


def get_clients(
    graph: Annotated[Graph, Depends(get_graph)],
    postgres: Annotated[Postgres | None, Depends(get_postgres)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ClientStore:
    return client_store(graph, postgres, settings)


def client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


SettingsDep = Annotated[Settings, Depends(get_settings)]
GraphDep = Annotated[Graph, Depends(get_graph)]
PostgresDep = Annotated[Postgres | None, Depends(get_postgres)]
ModelGraphDep = Annotated[Graph, Depends(get_model_graph)]
StorageDep = Annotated[LocalStorage, Depends(get_storage)]
UsersDep = Annotated[UserStore, Depends(get_users)]
ProjectsDep = Annotated[ProjectStore, Depends(get_projects)]
ClientsDep = Annotated[ClientStore, Depends(get_clients)]
