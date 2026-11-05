# This file was generated with the assistance of an AI coding tool.
import pytest

from opencde.odata import Field, ODataError, compile_filter, compile_odata, compile_orderby, compile_paging

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
