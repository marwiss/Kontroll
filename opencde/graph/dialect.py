# This file was generated with the assistance of an AI coding tool.
"""Differences between the supported graph databases, in one place.

Application code writes dialect-neutral Cypher (see ``docs/adr/0003``). The
few statements that differ, mainly schema DDL, come from the dialect object
chosen by ``OPENCDE_GRAPH_DIALECT``. Stage 1 adds the DDL templates; this
module starts with the identity of each dialect.
"""

from __future__ import annotations

from dataclasses import dataclass

from opencde.settings import GraphDialect


@dataclass(frozen=True, slots=True)
class Dialect:
    """What the server needs to know about one graph database product."""

    name: GraphDialect
    default_database: str
    product: str


NEO4J = Dialect(name=GraphDialect.NEO4J, default_database="neo4j", product="Neo4j 5.26 LTS")
MEMGRAPH = Dialect(name=GraphDialect.MEMGRAPH, default_database="memgraph", product="Memgraph 3.x")

DIALECTS: dict[GraphDialect, Dialect] = {NEO4J.name: NEO4J, MEMGRAPH.name: MEMGRAPH}


def get_dialect(name: GraphDialect) -> Dialect:
    return DIALECTS[name]
