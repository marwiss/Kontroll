# This file was generated with the assistance of an AI coding tool.
"""The server's own storage apart from the IFC graph (ADR 0027): one connection by default, its own when configured,
and a protocol per repository that says what each area answers for."""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest
from pydantic import ValidationError

from opencde.bootstrap import make_store
from opencde.graph.dialect import GraphDialect
from opencde.store import protocols
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
)


def test_the_store_shares_the_ifc_graphs_connection_unless_configured(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    assert not settings.has_store and make_store(settings) is None

    with pytest.raises(ValidationError, match="not supported yet"):  # until the split is whole (ADR 0027)
        make_settings(tmp_path, store_graph_uri="bolt://127.0.0.1:9", store_graph_dialect=GraphDialect.MEMGRAPH)


@pytest.mark.parametrize("repository", REPOSITORIES, ids=lambda cls: cls.__name__)
def test_a_protocol_names_every_public_method_of_its_repository_as_it_is(repository: type) -> None:
    """The protocols are generated from the repositories; a method added, renamed or given another parameter shows
    up here until the protocol is made anew."""
    protocol = getattr(protocols, repository.__name__.replace("Repository", "Store"))
    public = {name: fn for name, fn in vars(repository).items() if not name.startswith("_") and inspect.isfunction(fn)}
    declared = {name: fn for name, fn in vars(protocol).items() if not name.startswith("_") and inspect.isfunction(fn)}
    assert set(declared) == set(public), "the same methods"
    for name, fn in public.items():
        assert list(inspect.signature(fn).parameters) == list(inspect.signature(declared[name]).parameters), name
        assert inspect.iscoroutinefunction(fn) == inspect.iscoroutinefunction(declared[name]), name
