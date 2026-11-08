# This file was generated with the assistance of an AI coding tool.
"""The named queries on the IFC graph: each starts at the user, only reads, and takes its values as parameters."""

from __future__ import annotations

import re

import pytest

from opencde.admin.graph_query import check_statement
from opencde.ifcgraph.queries import QUERIES, InvalidParameters, NamedQuery

SCOPE = "MATCH (:User {id: $user_id})-[:MEMBER_OF]->(:Project)-[:HAS_MODEL]->(m:IfcModel)"
GIVEN = {"user_id", "document_id", "version_index"}


def _returned(query: NamedQuery) -> list[str]:
    """The names the last RETURN gives its columns: an alias, or a variable passed on as it is."""
    clause = query.body.rsplit("RETURN", 1)[1].split("ORDER BY", 1)[0]
    items, depth, current = [], 0, ""
    for char in clause:
        depth += char in "([{"
        depth -= char in ")]}"
        if char == "," and depth == 0:
            items.append(current)
            current = ""
        else:
            current += char
    items.append(current)
    return [item.split(" AS ")[-1].strip() for item in items]


@pytest.mark.parametrize("name", list(QUERIES))
def test_a_query_reaches_the_model_through_the_users_membership(name: str) -> None:
    query = QUERIES[name]
    assert query.cypher.lstrip().startswith(SCOPE)
    assert "{model_id: m.id}" in query.body, "it reads the model's own instances"


@pytest.mark.parametrize("name", list(QUERIES))
def test_a_query_only_reads(name: str) -> None:
    check_statement(QUERIES[name].cypher)  # the fence the administrators' free Cypher goes through


@pytest.mark.parametrize("name", list(QUERIES))
def test_a_query_uses_the_parameters_it_declares_and_no_others(name: str) -> None:
    query = QUERIES[name]
    used = set(re.findall(r"\$([a-z_]+)", query.cypher)) - GIVEN
    assert used == {parameter.name for parameter in query.parameters}


@pytest.mark.parametrize("name", list(QUERIES))
def test_a_query_returns_the_columns_it_declares(name: str) -> None:
    assert tuple(_returned(QUERIES[name])) == QUERIES[name].columns


def test_a_class_must_be_the_name_of_one() -> None:
    elements = QUERIES["elements"]
    assert elements.bind({"class": "IfcWall"}) == {"class": "IfcWall"}
    for wrong in ("wall", "IfcWall) DETACH DELETE (n", "Ifc", "IfcWall`", f"Ifc{'A' * 65}"):
        with pytest.raises(InvalidParameters, match="IFC class"):
            elements.bind({"class": wrong})


def test_a_required_parameter_must_be_given_and_an_unknown_one_is_refused() -> None:
    with pytest.raises(InvalidParameters, match="needs the parameter class"):
        QUERIES["elements"].bind({})
    with pytest.raises(InvalidParameters, match="needs the parameter class"):
        QUERIES["elements"].bind({"class": ""})
    with pytest.raises(InvalidParameters, match="takes no parameter limit"):
        QUERIES["storeys"].bind({"limit": "5"})
    assert QUERIES["materials"].bind({}) == {"class": None}, "an optional one may be left out"


def test_a_text_parameter_is_bounded_and_has_no_control_characters() -> None:
    query = QUERIES["property"]
    assert query.bind({"pset": "Pset_WallCommon", "property": "FireRating"})["pset"] == "Pset_WallCommon"
    assert query.bind({"pset": "Reuse", "property": "Ändrad 'av' \"någon\""})["property"].startswith("Ändrad")
    for wrong in ("x" * 256, "line\nbreak", "nul\x00"):
        with pytest.raises(InvalidParameters, match="255 characters"):
            query.bind({"pset": wrong, "property": "GTIN"})
