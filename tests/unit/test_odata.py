# This file was generated with the assistance of an AI coding tool.
import pytest

from opencde.odata import (
    Field,
    ODataError,
    compile_filter,
    compile_odata,
    compile_orderby,
    compile_paging,
    compile_sql_filter,
)

TOPIC_FIELDS = {
    "topic_status": Field("t.topic_status", "string"),
    "topic_type": Field("t.topic_type", "string"),
    "assigned_to": Field("t.assigned_to", "string"),
    "creation_date": Field("t.creation_date", "datetime"),
    "modified_date": Field("t.modified_date", "datetime"),
    "index": Field("t.index", "integer"),
    "labels": Field("t.labels", "string_list"),
    "resolved": Field("t.resolved", "boolean"),
}


def test_spec_example_filter_from_bcf_3_2_1() -> None:
    where, params = compile_filter(
        "assigned_to eq 'Architect@example.com' and topic_status eq 'Open' and creation_date gt 2015-12-05T00:00:00+01:00",
        TOPIC_FIELDS,
    )
    assert where == "((t.assigned_to = $od0 AND t.topic_status = $od1) AND t.creation_date > $od2)"
    assert params == {"od0": "Architect@example.com", "od1": "Open", "od2": "2015-12-04T23:00:00.000Z"}


def test_labels_any_lambda_from_bcf_3_2_1() -> None:
    where, params = compile_filter(
        "labels/any(label: label eq 'Architecture') or labels/any(label: label eq 'Structural')", TOPIC_FIELDS
    )
    assert (
        where
        == "(any(lv1 IN coalesce(t.labels, []) WHERE lv1 = $od0) OR any(lv2 IN coalesce(t.labels, []) WHERE lv2 = $od1))"
    )
    assert params == {"od0": "Architecture", "od1": "Structural"}


def test_null_in_not_and_functions() -> None:
    where, params = compile_filter(
        "assigned_to eq null and not (topic_type ne null) and index in (1, 2) and contains(tolower(topic_status), 'open')",
        TOPIC_FIELDS,
    )
    assert "t.assigned_to IS NULL" in where
    assert "(NOT t.topic_type IS NOT NULL)" in where
    assert "t.index IN $od0" in where and params["od0"] == [1, 2]
    assert "toLower(t.topic_status) CONTAINS $od1" in where and params["od1"] == "open"


def test_datetime_without_timezone_is_utc_and_dates_expand() -> None:
    where, params = compile_filter("modified_date ge 2026-01-02T03:04:05 and creation_date lt 2026-02-01", TOPIC_FIELDS)
    assert params == {"od0": "2026-01-02T03:04:05.000Z", "od1": "2026-02-01T00:00:00.000Z"}
    assert where == "(t.modified_date >= $od0 AND t.creation_date < $od1)"


@pytest.mark.parametrize(
    "expression",
    [
        "secret eq 'x'",  # unknown field
        "topic_status eq 'a' or 1 eq 1",  # literal vs literal
        "index eq 'text'",  # wrong type
        "creation_date gt 'not a date'",
        "labels gt 'Architecture'",  # lists support eq, ne and any/all only
        "topic_status/any(x: x eq 'a')",  # any on a scalar
        "length(topic_status) gt 3",  # unsupported function
        "topic_status eq 'a' and",  # syntax error
        "resolved eq 'yes'",
        "index add 1 eq 2",  # arithmetic
    ],
)
def test_rejected_filters(expression: str) -> None:
    with pytest.raises(ODataError):
        compile_filter(expression, TOPIC_FIELDS)


def test_list_membership_with_eq_and_ne() -> None:
    where, params = compile_filter("labels eq 'Safety' and labels ne 'Reuse'", TOPIC_FIELDS)
    assert params == {"od0": "Safety", "od1": "Reuse"}
    assert where == "($od0 IN coalesce(t.labels, []) AND NOT $od1 IN coalesce(t.labels, []))"


def test_filter_length_limit() -> None:
    with pytest.raises(ODataError, match="too long"):
        compile_filter("topic_status eq '" + "a" * 2100 + "'", TOPIC_FIELDS)


def test_orderby_and_paging() -> None:
    orderable = {"creation_date": "t.creation_date", "modified_date": "t.modified_date"}
    assert compile_orderby("modified_date desc, creation_date", orderable, "t.creation_date ASC") == (
        "t.modified_date DESC, t.creation_date ASC"
    )
    assert compile_orderby(None, orderable, "t.creation_date ASC") == "t.creation_date ASC"
    with pytest.raises(ODataError):
        compile_orderby("title", orderable, "t.creation_date ASC")
    with pytest.raises(ODataError):
        compile_orderby("creation_date sideways", orderable, "t.creation_date ASC")
    assert compile_paging(None, None, 1000) == (0, 1000)
    assert compile_paging(5000, 10, 1000) == (10, 1000)
    with pytest.raises(ODataError):
        compile_paging(-1, 0, 1000)
    with pytest.raises(ODataError):
        compile_paging(10, -1, 1000)


def test_compile_odata_bundles_everything() -> None:
    compiled = compile_odata(
        filter_="topic_status eq 'Open'",
        orderby="creation_date desc",
        top=5,
        skip=10,
        fields=TOPIC_FIELDS,
        orderable=["creation_date"],
        default_order="t.creation_date ASC",
    )
    assert compiled.where == "t.topic_status = $od0"
    assert compiled.where_clause() == "AND t.topic_status = $od0"
    assert compiled.order_by == "t.creation_date DESC"
    assert (compiled.skip, compiled.limit) == (10, 5)
    assert (
        compile_odata(
            filter_=None, orderby=None, top=None, skip=None, fields=TOPIC_FIELDS, orderable=[], default_order="x"
        ).where_clause()
        == ""
    )


def test_contains_on_a_list_field_asks_whether_it_is_in_the_list() -> None:
    """How BCF API 2.1 writes it (its section 4.2.1); 3.0 writes ``labels/any(l: l eq 'x')``."""
    clause, params = compile_filter("contains(labels, 'Architecture')", {"labels": Field("t.labels", "string_list")})
    assert clause is not None and "IN coalesce(t.labels, [])" in clause and "CONTAINS" not in clause
    assert list(params.values()) == ["Architecture"]
    with pytest.raises(ODataError):
        compile_filter("startswith(labels, 'A')", {"labels": Field("t.labels", "string_list")})


# -- the SQL target (ADR 0029) --------------------------------------------------------------------------------------

REFUSED = [
    "secret eq 'x'",
    "topic_status eq 'a' or 1 eq 1",
    "index eq 'text'",
    "creation_date gt 'not a date'",
    "labels gt 'Architecture'",
    "topic_status/any(x: x eq 'a')",
    "length(topic_status) gt 3",
    "topic_status eq 'a' and",
    "resolved eq 'yes'",
    "index add 1 eq 2",
    "startswith(labels, 'A')",
    "tolower(index) eq 'a'",
    "contains(topic_status, 1)",
    "index gt null",
    "topic_status in 'Open'",
    "topic_status has 'x'",
    "-index eq 1",
    "topic_status",
    "topic_status eq '" + "a" * 2100 + "'",
    "labels/any(l: l/any(m: m eq 'a'))",
    "labels/any(l: secret eq l)",
]


@pytest.mark.parametrize("expression", REFUSED)
def test_what_cypher_refuses_sql_refuses_in_the_same_words(expression: str) -> None:
    with pytest.raises(ODataError) as cypher:
        compile_filter(expression, TOPIC_FIELDS)
    with pytest.raises(ODataError) as sql:
        compile_sql_filter(expression, TOPIC_FIELDS)
    assert str(sql.value) == str(cypher.value)


def test_the_sql_of_bcf_3_2_1s_example_has_numbered_typed_parameters() -> None:
    where, params = compile_sql_filter(
        "assigned_to eq 'Architect@example.com' and topic_status eq 'Open' and creation_date gt 2015-12-05T00:00:00+01:00",
        TOPIC_FIELDS,
    )
    assert where == (
        '((t.assigned_to = $1::text AND t.topic_status = $2::text) AND t.creation_date COLLATE "C" > $3::text)'
    )
    assert params == ["Architect@example.com", "Open", "2015-12-04T23:00:00.000Z"]


def test_the_sql_of_lists_functions_and_null() -> None:
    where, params = compile_sql_filter(
        "assigned_to eq null and not (topic_type ne null) and index in (1, 2) and contains(tolower(topic_status), 'open')"
        " and labels eq 'Safety' and labels ne 'Reuse' and startswith(topic_type, 'Is') and endswith(topic_type, 'ue')",
        TOPIC_FIELDS,
    )
    assert where is not None
    assert "t.assigned_to IS NULL" in where and "(NOT t.topic_type IS NOT NULL)" in where
    assert "t.index = ANY($1::bigint[])" in where
    assert 'strpos(lower(t.topic_status COLLATE "default"), $2::text) > 0' in where
    assert "$3::text = ANY(coalesce(t.labels, ARRAY[]::text[]))" in where
    assert "NOT $4::text = ANY(coalesce(t.labels, ARRAY[]::text[]))" in where
    assert "starts_with(t.topic_type, $5::text)" in where
    assert "right(t.topic_type, char_length($6::text)) = $6::text" in where
    assert params == [[1, 2], "open", "Safety", "Reuse", "Is", "ue"]
    assert "LIKE" not in where, "no wildcards to escape"


def test_the_sql_of_any_and_all_is_three_valued_as_cyphers() -> None:
    where, params = compile_sql_filter("labels/any(l: l eq 'Architecture') and labels/all(l: l ne 'x')", TOPIC_FIELDS)
    assert where is not None and params == ["Architecture", "x"]
    assert "FROM unnest(coalesce(t.labels, ARRAY[]::text[])) AS lv1s(lv1)) AS lv1q)" in where
    assert "WHEN bool_or(lv1q.v) THEN true" in where and "WHEN NOT bool_and(lv2q.v) THEN false" in where
    assert compile_sql_filter("labels/any()", TOPIC_FIELDS)[0] == "cardinality(t.labels) > 0"
    assert compile_sql_filter("resolved", TOPIC_FIELDS)[0] == "t.resolved = true"


def test_a_value_never_becomes_sql() -> None:
    hostile = "x') OR 1=1; DROP TABLE topics; --"
    where, params = compile_sql_filter(f"topic_status eq '{hostile.replace(chr(39), chr(39) * 2)}'", TOPIC_FIELDS)
    assert where == "t.topic_status = $1::text" and params == [hostile]


def test_a_statement_takes_the_filter_and_the_order_after_its_own_parameters() -> None:
    compiled = compile_odata(
        filter_="topic_status eq 'Open' and index in (1, 2)",
        orderby="modified_date desc, index",
        top=5,
        skip=10,
        fields=TOPIC_FIELDS,
        orderable=["modified_date", "index"],
        default_order="t.creation_date ASC",
    )
    assert compiled.sql_params == ["Open", [1, 2]]
    assert compiled.sql_order_by == 't.modified_date COLLATE "C" DESC, t.index ASC'
    statement = "SELECT 1 FROM t WHERE t.p = $1 AND $filter ORDER BY $orderby OFFSET $2 LIMIT $3"
    assert compiled.sql(statement) == (
        "SELECT 1 FROM t WHERE t.p = $1 AND ((t.topic_status = $4::text AND t.index = ANY($5::bigint[])))"
        ' ORDER BY t.modified_date COLLATE "C" DESC, t.index ASC OFFSET $2 LIMIT $3'
    )
    plain = compile_odata(
        filter_=None, orderby=None, top=None, skip=None, fields=TOPIC_FIELDS, orderable=[], default_order="t.x DESC"
    )
    assert plain.sql("SELECT count(*) FROM t WHERE $filter") == "SELECT count(*) FROM t WHERE (true)"
    assert plain.sql_order_by == "t.x DESC", "a plain default order is the same in both"
    for wrong in ("SELECT 1", "SELECT 1 WHERE $filter AND $filter"):
        with pytest.raises(ValueError, match="takes"):
            plain.sql(wrong)
    odd = compile_odata(
        filter_=None, orderby=None, top=None, skip=None, fields=TOPIC_FIELDS, orderable=[], default_order="toLower(x)"
    )
    with pytest.raises(ValueError, match="no order in SQL"):
        odd.sql("SELECT 1 WHERE $filter ORDER BY $orderby")


def test_a_field_whose_cypher_is_not_plain_names_its_sql() -> None:
    with pytest.raises(ValueError, match="needs its SQL"):
        Field("toLower(t.title)", "string")
    assert Field("toLower(t.title)", "string", sql="lower(t.title)").sql_expression == "lower(t.title)"
