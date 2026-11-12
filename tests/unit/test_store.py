# This file was generated with the assistance of an AI coding tool.
"""The server's own storage apart from the IFC graph (ADR 0027): one connection by default, its own when configured,
and a protocol per repository that says what each area answers for, which the graph's repositories and those of
PostgreSQL (ADR 0029) both answer to."""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest
from pydantic import ValidationError

from opencde.bootstrap import make_store
from opencde.graph.dialect import GraphDialect
from opencde.store import protocols
from opencde.store.accounts.postgres import (
    PostgresProjectRepository,
    PostgresTeamRepository,
    PostgresUserRepository,
    PostgresWebSessionRepository,
)
from opencde.store.accounts.projects import ProjectRepository
from opencde.store.accounts.sessions import WebSessionRepository
from opencde.store.accounts.teams import TeamRepository
from opencde.store.accounts.users import UserRepository
from opencde.store.bcf.comments import CommentRepository
from opencde.store.bcf.documents import BcfDocumentRepository
from opencde.store.bcf.topic_links import TopicLinkRepository
from opencde.store.bcf.topics import TopicRepository
from opencde.store.bcf.viewpoints import ViewpointRepository
from opencde.store.documents.sessions import SelectionSessionRepository, UploadSessionRepository
from opencde.store.documents.versions import DocumentRepository
from opencde.store.jobs.conversions import ConversionRepository
from opencde.store.jobs.drafts import ChangeSetDraftRepository
from opencde.store.jobs.proposals import ProposalRepository
from opencde.store.oauth2.clients import ClientRepository
from opencde.store.oauth2.postgres import PostgresClientRepository, PostgresTokenRepository
from opencde.store.oauth2.tokens import TokenRepository
from tests.conftest import test_settings as make_settings

REPOSITORIES = (
    UserRepository,
    ProjectRepository,
    TeamRepository,
    WebSessionRepository,
    ClientRepository,
    TokenRepository,
    TopicRepository,
    CommentRepository,
    ViewpointRepository,
    TopicLinkRepository,
    BcfDocumentRepository,
    DocumentRepository,
    UploadSessionRepository,
    SelectionSessionRepository,
    ConversionRepository,
    ProposalRepository,
    ChangeSetDraftRepository,
    PostgresUserRepository,
    PostgresProjectRepository,
    PostgresTeamRepository,
    PostgresWebSessionRepository,
    PostgresClientRepository,
    PostgresTokenRepository,
)


def test_the_store_shares_the_ifc_graphs_connection_unless_configured(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    assert not settings.has_store and make_store(settings) is None
    assert not make_settings(tmp_path, store_graph_uri="  ").has_store, "an empty value is none"

    own = make_settings(tmp_path, store_graph_uri="bolt://127.0.0.1:9", store_graph_dialect=GraphDialect.MEMGRAPH)
    assert own.has_store and own.store_database_name == "memgraph"
    store = make_store(own)
    assert store is not None and store.dialect.name is GraphDialect.MEMGRAPH and store.database == "memgraph"
    named = make_settings(tmp_path, store_graph_uri="neo4j://127.0.0.1:9", store_graph_database="cde")
    assert named.store_database_name == "cde", "another database of the same product"

    with pytest.raises(ValidationError, match="OPENCDE_STORE_GRAPH_URI must use one of"):
        make_settings(tmp_path, store_graph_uri="http://127.0.0.1:9")


def test_production_wants_the_stores_password_too(tmp_path: Path) -> None:
    production = {"environment": "production", "public_url": "https://cde.example.org", "graph_password": "x" * 20}
    with pytest.raises(ValidationError, match="OPENCDE_STORE_GRAPH_PASSWORD is required"):
        make_settings(tmp_path, store_graph_uri="bolt://store:7687", **production)
    settings = make_settings(tmp_path, store_graph_uri="bolt://store:7687", store_graph_password="y" * 20, **production)
    assert settings.has_store


@pytest.mark.parametrize("repository", REPOSITORIES, ids=lambda cls: cls.__name__)
def test_a_protocol_names_every_public_method_of_its_repository_as_it_is(repository: type) -> None:
    """The protocols are generated from the repositories; a method added, renamed or given another parameter shows
    up here until the protocol is made anew."""
    protocol = getattr(protocols, repository.__name__.removeprefix("Postgres").replace("Repository", "Store"))
    public = {name: fn for name, fn in vars(repository).items() if not name.startswith("_") and inspect.isfunction(fn)}
    declared = {name: fn for name, fn in vars(protocol).items() if not name.startswith("_") and inspect.isfunction(fn)}
    assert set(declared) == set(public), "the same methods"
    for name, fn in public.items():
        assert list(inspect.signature(fn).parameters) == list(inspect.signature(declared[name]).parameters), name
        assert inspect.iscoroutinefunction(fn) == inspect.iscoroutinefunction(declared[name]), name


def test_the_store_can_be_postgresql_alone_and_only_in_the_tests_for_now(tmp_path: Path) -> None:
    """``OPENCDE_STORE_URL`` (ADR 0029): a PostgreSQL URL without the password, not beside a graph of its own, and
    refused outside the tests until every area has followed."""
    settings = make_settings(tmp_path, store_url=" postgresql://cde@db:5432/cde ", store_password="p" * 20)
    assert settings.store_url == "postgresql://cde@db:5432/cde" and not settings.has_store
    assert make_settings(tmp_path, store_url="  ").store_url is None, "an empty value is none"
    for url, words in (
        ("mysql://cde@db/cde", "OPENCDE_STORE_URL must use one of"),
        ("postgresql://cde:secret@db/cde", "must not hold the password"),
        ("postgres://cde@db/cde?password=secret", "must not hold the password"),
    ):
        with pytest.raises(ValidationError, match=words) as refused:
            make_settings(tmp_path, store_url=url)
        assert "secret" not in str(refused.value), "a refused value is never repeated"
    with pytest.raises(ValidationError, match="exclude each other"):
        make_settings(tmp_path, store_url="postgresql://cde@db/cde", store_graph_uri="bolt://store:7687")
    with pytest.raises(ValidationError, match="not supported yet"):
        make_settings(tmp_path, store_url="postgresql://cde@db/cde", environment="development")
