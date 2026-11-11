# This file was generated with the assistance of an AI coding tool.
"""The named queries on the IFC graph of a document version, for members of its project (ADR 0016).

Reading a model is asking it questions by name with parameters, never with Cypher of one's own; free Cypher stays
with administrators (``admin/graph_query.py``). The catalogue and its statements are IFC-LPG's (``ifc_lpg.queries``,
F38 a): the library owns the graph's form and proves the queries on both databases, and a query added there appears
in the listing. The server finds the model through the member's project, chooses the archive or the working copy,
holds the limits, and adds ``changed-since``, answered from the versions' change sets without the graph
(``documents/routes_queries.py``).
"""

from __future__ import annotations

from ifc_lpg.queries import (
    MAX_ROWS,
    QUERIES,
    TIMEOUT_SECONDS,
    InvalidParameters,
    NamedQuery,
    UnknownQuery,
    catalogue,
    run_query,
)

#: The query on what changed since a version, answered from the versions' change sets, not from the graph; listed and
#: announced with the others.
CHANGED_SINCE = "changed-since"
CHANGED_SINCE_COLUMNS = (
    "version_index",
    "change_set_id",
    "author",
    "approved_by",
    "whole_file",
    "guid",
    "step_id",
    "path",
    "attribute",
    "op",
)

__all__ = [
    "CHANGED_SINCE",
    "CHANGED_SINCE_COLUMNS",
    "MAX_ROWS",
    "QUERIES",
    "TIMEOUT_SECONDS",
    "InvalidParameters",
    "NamedQuery",
    "UnknownQuery",
    "catalogue",
    "run_query",
]
