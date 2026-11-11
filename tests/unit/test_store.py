# This file was generated with the assistance of an AI coding tool.
"""The server's own storage apart from the IFC graph (F24 a): one connection by default, its own when configured."""

from __future__ import annotations

from pathlib import Path

from opencde.bootstrap import make_store
from opencde.graph.dialect import GraphDialect
from opencde.settings import Settings


def test_the_store_shares_the_ifc_graphs_connection_unless_configured(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, secret_key="x" * 32, graph_password="pw")
    assert not settings.has_store and make_store(settings) is None

    own = Settings(
        data_dir=tmp_path,
        secret_key="x" * 32,
        graph_password="pw",
        store_graph_uri="bolt://localhost:7699",
        store_graph_dialect=GraphDialect.MEMGRAPH,
    )
    assert own.has_store and own.store_database_name == "memgraph"
    store = make_store(own)
    assert store is not None and store.dialect.name is GraphDialect.MEMGRAPH
