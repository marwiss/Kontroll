# This file was generated with the assistance of an AI coding tool.
"""OData query options compiled to parameterised Cypher and SQL (Foundation API 1.1, ADR 0029).

Collections accept ``$filter``, ``$orderby``, ``$top`` and ``$skip``. The
filter is parsed by ``odata-query`` into a syntax tree; this module walks the
tree and emits Cypher, and SQL for PostgreSQL, for exactly the fields,
operators and functions each resource allows (a whitelist), with every literal
as a query parameter. Any other construct is rejected with a 400, never passed
through. Dates are normalised to the stored ISO 8601 UTC form so string
comparison is correct.

Supported: comparisons (``eq ne gt ge lt le in``), ``and or not``,
parentheses, ``null``, string, integer, boolean, GUID and datetime literals,
``contains/startswith/endswith(field, 'text')``, ``tolower/toupper(field)``,
and ``labels/any(l: l eq 'Architecture')`` on list fields (BCF 3.2.1).

The two languages share one visitor's checks, so what one refuses the other refuses with the same words; only the
writing differs. The SQL keeps Cypher's answers: text is compared and ordered by code point (``COLLATE "C"``), a
list field is a ``text[]``, ``any`` and ``all`` keep Cypher's three-valued logic, and ``contains``, ``startswith``
and ``endswith`` are ``strpos``, ``starts_with`` and ``right``, so no ``LIKE`` wildcard needs escaping. Its
parameters are ``$1`` to ``$n``, which :meth:`Compiled.sql` numbers after the statement's own.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from odata_query import ast as oast
from odata_query.exceptions import ODataException
from odata_query.grammar import ODataLexer, ODataParser
from odata_query.visitor import NodeVisitor

from opencde.timeutil import canonical_iso

Kind = Literal["string", "datetime", "integer", "boolean", "string_list"]

MAX_FILTER_LENGTH = 2000
MAX_SKIP = 1_000_000

#: Where a statement of the store's takes the filter and the order (:meth:`Compiled.sql`).
FILTER_MARK = "$filter"
ORDER_MARK = "$orderby"

_PLAIN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*$")
_PLAIN_ORDER = re.compile(
    r"^[A-Za-z_]\w*\.[A-Za-z_]\w*(\s+(ASC|DESC))?(\s*,\s*[A-Za-z_]\w*\.[A-Za-z_]\w*(\s+(ASC|DESC))?)*$", re.IGNORECASE
)
_PLACEHOLDER = re.compile(r"\$(\d+)")
_SQL_TYPES: dict[str, str] = {
    "string": "text",
    "datetime": "text",
    "integer": "bigint",
    "boolean": "boolean",
    "string_list": "text",
}
_ORDERED_TEXT = ("string", "datetime")  # compared and ordered by code point, as the graphs do


class ODataError(ValueError):
    """The query options are not acceptable; the message is safe to return to the client."""


@dataclass(frozen=True)
class Field:
    """One filterable property: its Cypher expression, its value type, and its SQL expression, which is the Cypher
    one when that is a plain ``alias.property``, written alike in both languages."""

    cypher: str
    kind: Kind
    sql: str | None = None

    def __post_init__(self) -> None:
        if self.sql is None and not _PLAIN.match(self.cypher):
            raise ValueError(f"field {self.cypher!r} needs its SQL expression")

    @property
    def sql_expression(self) -> str:
        return self.sql if self.sql is not None else self.cypher


@dataclass
class Compiled:
    where: str | None
    params: dict[str, Any]
    order_by: str
    skip: int
    limit: int
    capped: bool = False  # the server's limit holds, not a $top of the caller's
    sql_where: str | None = None  # the same filter in SQL, its parameters $1 to $n
    sql_params: list[Any] = field(default_factory=list)
    sql_order_by: str | None = None

    def where_clause(self, prefix: str = "AND") -> str:
        return f"{prefix} {self.where}" if self.where else ""

    def sql(self, query: str) -> str:
        """The store's statement ``query`` with the filter where it says ``$filter`` and the order where it says
        ``$orderby``. The filter's parameters are numbered after the statement's own, so they follow its arguments:
        ``postgres.run(compiled.sql(QUERY), *arguments, *compiled.sql_params)``. Nothing of the caller's request
        becomes part of the text: the filter and the order are made of the whitelist's expressions alone."""
        if query.count(FILTER_MARK) != 1 or query.count(ORDER_MARK) > 1:
            raise ValueError("a statement takes $filter once and $orderby at most once")
        base = max((int(number) for number in _PLACEHOLDER.findall(query)), default=0)
        where = _PLACEHOLDER.sub(lambda m: f"${int(m[1]) + base}", self.sql_where) if self.sql_where else "true"
        statement = query.replace(FILTER_MARK, f"({where})")
        if ORDER_MARK in query:
            if self.sql_order_by is None:
                raise ValueError("these options have no order in SQL")
            statement = statement.replace(ORDER_MARK, self.sql_order_by)
        return statement


@dataclass(frozen=True)
class _Ref:
    text: str
    kind: Kind


@dataclass(frozen=True)
class _Lit:
    value: Any


@dataclass(frozen=True)
class _Clause:
    text: str


_COMPARATORS: dict[type, str] = {
    oast.Eq: "=",
    oast.NotEq: "<>",
    oast.Lt: "<",
    oast.LtE: "<=",
    oast.Gt: ">",
    oast.GtE: ">=",
}

_ORDER_ITEM = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)(?:\s+(asc|desc))?\s*$", re.IGNORECASE)


@dataclass
class _Scope:
    fields: Mapping[str, Field]
    lambda_vars: dict[str, _Ref] = field(default_factory=dict)
    counter: int = 0


class _Visitor(NodeVisitor):
    """The whitelist and its checks, the same for both languages; the subclasses write each construct."""

    def __init__(self, fields: Mapping[str, Field]) -> None:
        self.scope = _Scope(fields=fields)

    # -- the writing, per language ------------------------------------------------

    def _param(self, value: Any, kind: Kind, *, many: bool = False) -> str:
        raise NotImplementedError

    def _field(self, spec: Field) -> str:
        raise NotImplementedError

    def _in(self, ref: _Ref, values: str) -> str:
        raise NotImplementedError

    def _member(self, value: str, ref: _Ref) -> str:
        """The value is one of the list field's."""
        raise NotImplementedError

    def _compare(self, ref: _Ref, operator: str, value: str) -> str:
        raise NotImplementedError

    def _case(self, name: str, ref: _Ref) -> str:
        raise NotImplementedError

    def _match(self, name: str, ref: _Ref, value: str) -> str:
        """``contains``, ``startswith`` or ``endswith``."""
        raise NotImplementedError

    def _non_empty(self, ref: _Ref) -> str:
        raise NotImplementedError

    def _quantified(self, quantifier: str, variable: str, ref: _Ref, body: str) -> str:
        raise NotImplementedError

    # -- helpers --------------------------------------------------------------

    def _coerce(self, ref: _Ref, value: Any) -> Any:
        """Make a literal comparable with the stored representation of the field."""
        if value is None:
            return None
        kind = ref.kind
        if kind == "datetime":
            try:
                return canonical_iso(str(value))
            except ValueError as exc:
                raise ODataError(f"invalid datetime literal {value!r}") from exc
        if kind in ("string", "string_list"):
            return str(value)
        if kind == "integer":
            if isinstance(value, bool) or not isinstance(value, int):
                raise ODataError("integer field compared with a non-integer")
            return value
        if kind == "boolean":
            if not isinstance(value, bool):
                raise ODataError("boolean field compared with a non-boolean")
            return value
        raise ODataError("unsupported field type")

    def _as_clause(self, node: oast._Node) -> str:
        result = self.visit(node)
        if isinstance(result, _Clause):
            return result.text
        if isinstance(result, _Ref) and result.kind == "boolean":
            return f"{result.text} = true"
        raise ODataError("expression does not evaluate to a condition")

    # -- generic --------------------------------------------------------------

    def generic_visit(self, node: oast._Node) -> Any:
        raise ODataError(f"unsupported expression: {type(node).__name__}")

    # -- leaves ---------------------------------------------------------------

    def visit_Identifier(self, node: oast.Identifier) -> _Ref:
        if node.name in self.scope.lambda_vars:
            return self.scope.lambda_vars[node.name]
        try:
            spec = self.scope.fields[node.name]
        except KeyError:
            raise ODataError(f"unknown field '{node.name}'") from None
        return _Ref(self._field(spec), spec.kind)

    def visit_Null(self, _node: oast.Null) -> _Lit:
        return _Lit(None)

    def visit_String(self, node: oast.String) -> _Lit:
        return _Lit(node.py_val)

    def visit_Integer(self, node: oast.Integer) -> _Lit:
        return _Lit(node.py_val)

    def visit_Float(self, node: oast.Float) -> _Lit:
        return _Lit(node.py_val)

    def visit_Boolean(self, node: oast.Boolean) -> _Lit:
        return _Lit(node.py_val)

    def visit_GUID(self, node: oast.GUID) -> _Lit:
        return _Lit(str(node.val).lower())

    def visit_DateTime(self, node: oast.DateTime) -> _Lit:
        return _Lit(node.val)

    def visit_Date(self, node: oast.Date) -> _Lit:
        return _Lit(node.val + "T00:00:00Z")

    def visit_List(self, node: oast.List) -> _Lit:
        return _Lit([self.visit(item).value for item in node.val])

    # -- operators ------------------------------------------------------------

    def visit_Compare(self, node: oast.Compare) -> _Clause:
        left = self.visit(node.left)
        right = self.visit(node.right)
        if isinstance(left, _Lit) and isinstance(right, _Ref):
            left, right = right, left
        if not isinstance(left, _Ref) or not isinstance(right, _Lit):
            raise ODataError("comparisons must compare a field with a literal")

        if isinstance(node.comparator, oast.In):
            if not isinstance(right.value, list):
                raise ODataError("'in' needs a list literal")
            values = [self._coerce(left, item) for item in right.value]
            return _Clause(self._in(left, self._param(values, left.kind, many=True)))

        operator = _COMPARATORS.get(type(node.comparator))
        if operator is None:
            raise ODataError("unsupported comparison operator")
        if right.value is None:
            if operator == "=":
                return _Clause(f"{left.text} IS NULL")
            if operator == "<>":
                return _Clause(f"{left.text} IS NOT NULL")
            raise ODataError("null can only be compared with eq or ne")
        if left.kind == "string_list":
            # ``labels eq 'x'`` reads as "contains x", which is what event ``type`` filters need (BCF 3.9.1).
            member = self._member(self._param(self._coerce(left, right.value), left.kind), left)
            if operator == "=":
                return _Clause(member)
            if operator == "<>":
                return _Clause(f"NOT {member}")
            raise ODataError("list fields support eq, ne and any/all only")
        return _Clause(self._compare(left, operator, self._param(self._coerce(left, right.value), left.kind)))

    def visit_BoolOp(self, node: oast.BoolOp) -> _Clause:
        joiner = "AND" if isinstance(node.op, oast.And) else "OR"
        return _Clause(f"({self._as_clause(node.left)} {joiner} {self._as_clause(node.right)})")

    def visit_UnaryOp(self, node: oast.UnaryOp) -> _Clause:
        if not isinstance(node.op, oast.Not):
            raise ODataError("unsupported unary operator")
        return _Clause(f"(NOT {self._as_clause(node.operand)})")

    def visit_Call(self, node: oast.Call) -> Any:
        name = node.func.name.lower()
        args = [self.visit(arg) for arg in node.args]
        if name in ("tolower", "toupper"):
            if len(args) != 1 or not isinstance(args[0], _Ref) or args[0].kind != "string":
                raise ODataError(f"{name}() takes one string field")
            return _Ref(self._case(name, args[0]), "string")
        if name in ("contains", "startswith", "endswith"):
            if len(args) != 2 or not isinstance(args[0], _Ref) or not isinstance(args[1], _Lit):
                raise ODataError(f"{name}() takes a string field and a string literal")
            if name == "contains" and args[0].kind == "string_list" and isinstance(args[1].value, str):
                # The way BCF API 2.1 asks after a label: ``contains(labels, 'Architecture')`` (its section 4.2.1).
                return _Clause(self._member(self._param(args[1].value, "string_list"), args[0]))
            if args[0].kind != "string" or not isinstance(args[1].value, str):
                raise ODataError(f"{name}() works on string fields only")
            return _Clause(self._match(name, args[0], self._param(args[1].value, "string")))
        raise ODataError(f"unsupported function '{node.func.name}'")

    def visit_CollectionLambda(self, node: oast.CollectionLambda) -> _Clause:
        owner = self.visit(node.owner)
        if not isinstance(owner, _Ref) or owner.kind != "string_list":
            raise ODataError("any/all applies to list fields only")
        quantifier = "any" if isinstance(node.operator, oast.Any) else "all"
        if node.lambda_ is None:
            return _Clause(self._non_empty(owner) if quantifier == "any" else "true")
        self.scope.counter += 1
        variable = f"lv{self.scope.counter}"
        name = node.lambda_.identifier.name
        self.scope.lambda_vars[name] = _Ref(variable, "string")
        try:
            body = self._as_clause(node.lambda_.expression)
        finally:
            del self.scope.lambda_vars[name]
        return _Clause(self._quantified(quantifier, variable, owner, body))


class _CypherVisitor(_Visitor):
    def __init__(self, fields: Mapping[str, Field]) -> None:
        super().__init__(fields)
        self.params: dict[str, Any] = {}

    def _param(self, value: Any, kind: Kind, *, many: bool = False) -> str:
        name = f"od{len(self.params)}"
        self.params[name] = value
        return f"${name}"

    def _field(self, spec: Field) -> str:
        return spec.cypher

    def _in(self, ref: _Ref, values: str) -> str:
        return f"{ref.text} IN {values}"

    def _member(self, value: str, ref: _Ref) -> str:
        return f"{value} IN coalesce({ref.text}, [])"

    def _compare(self, ref: _Ref, operator: str, value: str) -> str:
        return f"{ref.text} {operator} {value}"

    def _case(self, name: str, ref: _Ref) -> str:
        return f"{'toLower' if name == 'tolower' else 'toUpper'}({ref.text})"

    def _match(self, name: str, ref: _Ref, value: str) -> str:
        operator = {"contains": "CONTAINS", "startswith": "STARTS WITH", "endswith": "ENDS WITH"}[name]
        return f"{ref.text} {operator} {value}"

    def _non_empty(self, ref: _Ref) -> str:
        return f"size({ref.text}) > 0"

    def _quantified(self, quantifier: str, variable: str, ref: _Ref, body: str) -> str:
        return f"{quantifier}({variable} IN coalesce({ref.text}, []) WHERE {body})"


class _SqlVisitor(_Visitor):
    """PostgreSQL, with Cypher's answers (the module's docstring says how)."""

    def __init__(self, fields: Mapping[str, Field]) -> None:
        super().__init__(fields)
        self.params: list[Any] = []

    def _param(self, value: Any, kind: Kind, *, many: bool = False) -> str:
        self.params.append(value)
        return f"${len(self.params)}::{_SQL_TYPES[kind]}{'[]' if many else ''}"

    def _field(self, spec: Field) -> str:
        return spec.sql_expression

    def _in(self, ref: _Ref, values: str) -> str:
        if ref.kind == "string_list":
            # Cypher compares the list with each value, which a list never equals: false, or null where the list
            # or a value is null, and false for no values at all.
            return (
                f"(CASE WHEN cardinality({values}) = 0 THEN false"
                f" WHEN {ref.text} IS NULL OR array_position({values}, NULL) IS NOT NULL THEN NULL ELSE false END)"
            )
        return f"{ref.text} = ANY({values})"

    def _member(self, value: str, ref: _Ref) -> str:
        return f"{value} = ANY(coalesce({ref.text}, ARRAY[]::text[]))"

    def _compare(self, ref: _Ref, operator: str, value: str) -> str:
        if ref.kind in _ORDERED_TEXT and operator not in ("=", "<>"):
            return f'{ref.text} COLLATE "C" {operator} {value}'
        return f"{ref.text} {operator} {value}"

    def _case(self, name: str, ref: _Ref) -> str:
        # The database's own case mapping, as Neo4j maps every letter and not only ASCII's, which "C" alone would.
        return f'{"lower" if name == "tolower" else "upper"}({ref.text} COLLATE "default")'

    def _match(self, name: str, ref: _Ref, value: str) -> str:
        if name == "contains":
            return f"strpos({ref.text}, {value}) > 0"
        if name == "startswith":
            return f"starts_with({ref.text}, {value})"
        return f"right({ref.text}, char_length({value})) = {value}"

    def _non_empty(self, ref: _Ref) -> str:
        return f"cardinality({ref.text}) > 0"

    def _quantified(self, quantifier: str, variable: str, ref: _Ref, body: str) -> str:
        # Cypher's any and all are three-valued, as and and or are: null where no element decides and one is null.
        rows = f"{variable}q"
        if quantifier == "any":
            verdict = (
                f"CASE WHEN count(*) = 0 THEN false WHEN bool_or({rows}.v) THEN true"
                f" WHEN count({rows}.v) < count(*) THEN NULL ELSE false END"
            )
        else:
            verdict = (
                f"CASE WHEN count(*) = 0 THEN true WHEN NOT bool_and({rows}.v) THEN false"
                f" WHEN count({rows}.v) < count(*) THEN NULL ELSE true END"
            )
        # Made of the whitelist's expressions and the visitor's own names; every value is a parameter.
        return (
            f"(SELECT {verdict} FROM (SELECT ({body}) AS v"  # noqa: S608  # nosec B608
            f" FROM unnest(coalesce({ref.text}, ARRAY[]::text[])) AS {variable}s({variable})) AS {rows})"
        )


def _parse(expression: str | None) -> oast._Node | None:
    if expression is None or not expression.strip():
        return None
    if len(expression) > MAX_FILTER_LENGTH:
        raise ODataError("$filter is too long")
    try:
        return ODataParser().parse(ODataLexer().tokenize(expression))
    except ODataException as exc:
        raise ODataError(f"invalid $filter: {exc.__class__.__name__}") from exc


def compile_filter(expression: str | None, fields: Mapping[str, Field]) -> tuple[str | None, dict[str, Any]]:
    """Return a Cypher boolean expression and its parameters, or (None, {}) for no filter."""
    tree = _parse(expression)
    if tree is None:
        return None, {}
    visitor = _CypherVisitor(fields)
    return visitor._as_clause(tree), visitor.params


def compile_sql_filter(expression: str | None, fields: Mapping[str, Field]) -> tuple[str | None, list[Any]]:
    """Return an SQL boolean expression with the parameters ``$1`` to ``$n`` and their values, or (None, [])."""
    tree = _parse(expression)
    if tree is None:
        return None, []
    visitor = _SqlVisitor(fields)
    return visitor._as_clause(tree), visitor.params


def compile_orderby(expression: str | None, orderable: Mapping[str, str], default: str) -> str:
    """``'modified_date desc, title'`` → ``'t.modified_date DESC, t.title ASC'`` using the whitelist."""
    if expression is None or not expression.strip():
        return default
    parts = []
    for item in expression.split(","):
        match = _ORDER_ITEM.match(item)
        if not match:
            raise ODataError("invalid $orderby")
        name, direction = match.group(1), (match.group(2) or "asc").upper()
        if name not in orderable:
            raise ODataError(f"cannot order by '{name}'")
        parts.append(f"{orderable[name]} {direction}")
    return ", ".join(parts)


def compile_paging(top: int | None, skip: int | None, max_top: int) -> tuple[int, int]:
    if skip is not None and (skip < 0 or skip > MAX_SKIP):
        raise ODataError("$skip out of range")
    if top is not None and top < 0:
        raise ODataError("$top out of range")
    limit = max_top if top is None else min(top, max_top)
    return skip or 0, limit


def _sql_order(spec: Field) -> str:
    return f'{spec.sql_expression} COLLATE "C"' if spec.kind in _ORDERED_TEXT else spec.sql_expression


def compile_odata(
    *,
    filter_: str | None,
    orderby: str | None,
    top: int | None,
    skip: int | None,
    fields: Mapping[str, Field],
    orderable: Iterable[str],
    default_order: str,
    max_top: int = 1000,
    default_sql_order: str | None = None,
) -> Compiled:
    """Both languages at once, so that a refusal comes before either store is asked. ``default_sql_order`` is the
    default order in SQL, which is ``default_order`` when that is a list of plain ``alias.property``."""
    where, params = compile_filter(filter_, fields)
    sql_where, sql_params = compile_sql_filter(filter_, fields)
    names = list(orderable)
    order_by = compile_orderby(orderby, {name: fields[name].cypher for name in names}, default_order)
    if default_sql_order is None and _PLAIN_ORDER.match(default_order.strip()):
        default_sql_order = default_order
    sql_order_by = (
        compile_orderby(orderby, {name: _sql_order(fields[name]) for name in names}, default_sql_order)
        if default_sql_order is not None
        else None
    )
    offset, limit = compile_paging(top, skip, max_top)
    capped = top is None or top > max_top
    return Compiled(
        where=where,
        params=params,
        order_by=order_by,
        skip=offset,
        limit=limit,
        capped=capped,
        sql_where=sql_where,
        sql_params=sql_params,
        sql_order_by=sql_order_by,
    )
