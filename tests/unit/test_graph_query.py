# This file was generated with the assistance of an AI coding tool.
"""The fences of the read-only graph query: what a statement may say, and what an answer may carry."""

import pytest
from neo4j.spatial import CartesianPoint
from neo4j.time import Date, DateTime, Duration

from opencde.admin.graph_query import REDACTED, QueryRejected, check_parameters, check_statement, json_value

ACCEPTED = [
    "MATCH (u:User)-[:MEMBER_OF]->(p:Project) RETURN u.username, p.name ORDER BY p.name LIMIT 10",
    "MATCH (n) WHERE n.name = 'CREATE something' OR n.name = \"DELETE it\" RETURN count(n)",  # strings are data
    "MATCH (n:`create`) RETURN n.set, n.delete, n.`remove` // DELETE in a comment\n",  # names, not clauses
    "/* SET nothing\n   MERGE nothing */ MATCH (c:Client) RETURN c{.name, .is_public}",
    "MATCH (n:Set)-[:DROP]->(m:Merge) RETURN n, m",  # labels and types carry any name
    "UNWIND $set AS x RETURN x",  # so do parameters
    "CALL db.labels() YIELD label RETURN label",
    "CALL db.schema.visualization()",
    "CALL { MATCH (n) RETURN n LIMIT 1 } RETURN n",
    "MATCH (e:IfcWall) RETURN e.GlobalId, e.Name, startNode(e) IS NOT NULL",
    "match (u:User) return u.username, u.created_at order by u.created_at desc",
]

REJECTED = [
    ("CREATE (n:Evil) RETURN n", "CREATE"),
    ("MATCH (u:User) SET u.disabled = true RETURN u", "SET"),
    ("MATCH (n) DETACH DELETE n", "DETACH"),
    ("merge (n:X) return n", "MERGE"),
    ("MATCH (n) REMOVE n.x RETURN n", "REMOVE"),
    ("DROP INDEX wall_guid", "DROP"),
    ("LOAD CSV FROM 'file:///etc/passwd' AS row RETURN row", "LOAD"),
    ("MATCH (n) CALL { WITH n SET n.x = 1 } RETURN n", "SET"),
    ("MATCH (n) CALL { WITH n CREATE (n)-[:X]->(:Y) } IN TRANSACTIONS RETURN n", "CREATE"),
    ("CALL dbms.components() YIELD name RETURN name", "schema procedures"),
    ("CALL apoc.load.json('https://x') YIELD value RETURN value", "schema procedures"),
    ("CALL db.labels() YIELD label CALL dbms.killQueries(['x']) YIELD queryId RETURN 1", "schema procedures"),
    ("SHOW USERS", "SHOW"),
    ("USE system MATCH (n) RETURN n", "USE"),
    ("RETURN 1; CREATE (n)", "CREATE"),
    ("WITH 1 AS x\nCREATE (n {x: x})", "CREATE"),
    ("MATCH (u:User) RETURN u.password_hash", "protected property"),
    ("MATCH (c:Client) RETURN c.SECRET_HASH", "protected property"),
    ("MATCH (t:RefreshToken) RETURN t.token_hash", "protected property"),
    ("MATCH (c:AuthorizationCode) RETURN c.code_hash", "protected property"),
    ("   \n ", "empty"),
]


@pytest.mark.parametrize("statement", ACCEPTED)
def test_reading_statements_pass(statement: str) -> None:
    check_statement(statement)


@pytest.mark.parametrize(("statement", "reason"), REJECTED)
def test_writing_and_prying_statements_are_refused(statement: str, reason: str) -> None:
    with pytest.raises(QueryRejected, match=reason):
        check_statement(statement)


def test_parameters_may_not_name_a_protected_property() -> None:
    check_parameters({"name": "editor", "keys": ["username", "email"], "nested": {"deep": {"x": 1}}})
    for params in (
        {"key": "password_hash"},
        {"keys": ["username", "secret_hash"]},
        {"nested": {"deep": {"x": "Token_Hash"}}},
        {"code_hash": 1},
    ):
        with pytest.raises(QueryRejected, match="protected property"):
            check_parameters(params)


def test_answer_values_are_json_with_hashes_left_out() -> None:
    assert json_value(5) == 5 and json_value(True) is True and json_value(None) is None
    assert json_value(1.5) == 1.5 and json_value(float("nan")) is None and json_value(float("inf")) is None
    assert json_value("text") == "text"
    assert json_value("$argon2id$v=19$m=65536,t=3,p=4$abc$def") == REDACTED
    assert json_value({"name": "x", "password_hash": "$argon2id$...", "token_hash": "ab", "n": 1}) == {
        "name": "x",
        "n": 1,
    }
    assert json_value([1, {"secret_hash": "x", "a": 2}, ("t",)]) == [1, {"a": 2}, ["t"]]
    assert json_value(DateTime(2026, 1, 1, 12, 30, 0)) == "2026-01-01T12:30:00.000000000"
    assert json_value(Date(2026, 1, 1)) == "2026-01-01"
    assert json_value(Duration(hours=1, minutes=30)) == "PT1H30M"
    assert json_value(CartesianPoint((1.0, 2.0))) == {"srid": 7203, "x": 1.0, "y": 2.0}
    assert json_value(CartesianPoint((1.0, 2.0, 3.0))) == {"srid": 9157, "x": 1.0, "y": 2.0, "z": 3.0}
    assert json_value(b"\x00\x01") == "AAE="
    assert json_value(frozenset({"a"})) == ["a"]
