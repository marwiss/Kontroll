# This file was generated with the assistance of an AI coding tool.
"""The server's own storage apart from the IFC graph (F24 a): one connection by default, its own when configured."""

from __future__ import annotations

from pathlib import Path

from opencde.bootstrap import make_store
from opencde.graph.dialect import GraphDialect
from tests.conftest import test_settings as make_settings


def test_the_store_shares_the_ifc_graphs_connection_unless_configured(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    assert not settings.has_store and make_store(settings) is None

    own = make_settings(tmp_path, store_graph_uri="bolt://127.0.0.1:9", store_graph_dialect=GraphDialect.MEMGRAPH)
    assert own.has_store and own.store_database_name == "memgraph"
    store = make_store(own)
    assert store is not None and store.dialect.name is GraphDialect.MEMGRAPH
