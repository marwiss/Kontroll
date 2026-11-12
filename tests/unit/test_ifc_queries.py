# This file was generated with the assistance of an AI coding tool.
"""The named queries come from IFC-DB: each passes the administrators' read-only fence, and the listing is whole."""

from __future__ import annotations

import pytest

from opencde.admin.graph_query import check_statement
from opencde.ifcgraph.queries import CHANGED_SINCE, CHANGED_SINCE_COLUMNS, QUERIES, catalogue


@pytest.mark.parametrize("name", list(QUERIES))
def test_a_query_only_reads(name: str) -> None:
    check_statement(QUERIES[name].cypher)  # the fence the administrators' free Cypher goes through


@pytest.mark.parametrize("name", list(QUERIES))
def test_a_query_names_its_model_by_id_and_takes_values_as_parameters(name: str) -> None:
    query = QUERIES[name]
    assert "MATCH (m:Model {id: $model_id})" in query.cypher
    assert "{model_id: m.id}" in query.body, "it reads the model's own instances"
    assert "$row_limit" in query.cypher


def test_the_listing_is_the_librarys_catalogue_and_the_change_sets() -> None:
    listed = catalogue()
    assert [entry["name"] for entry in listed] == list(QUERIES)
    assert len(listed) >= 8 and listed[0]["name"] == "entity", "the questions a member asks, entity first"
    for entry in listed:
        assert entry["columns"] == list(QUERIES[entry["name"]].columns)
        for parameter in entry["parameters"]:
            assert parameter["kind"] in ("text", "class", "global_id")
    assert CHANGED_SINCE not in QUERIES, "answered from the versions, not the graph"
    assert CHANGED_SINCE_COLUMNS[0] == "version_index"
