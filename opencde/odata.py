# This file was generated with the assistance of an AI coding tool.
"""OData query options compiled to parameterised Cypher (Foundation API 1.1).

Collections accept ``$filter``, ``$orderby``, ``$top`` and ``$skip``. The
filter is parsed by ``odata-query`` into a syntax tree; this module walks the
tree and emits Cypher for exactly the fields, operators and functions each
resource allows (a whitelist), with every literal as a query parameter. Any
other construct is rejected with a 400, never passed through. Dates are
normalised to the stored ISO 8601 UTC form so string comparison is correct.

Supported: comparisons (``eq ne gt ge lt le in``), ``and or not``,
parentheses, ``null``, string, integer, boolean, GUID and datetime literals,
``contains/startswith/endswith(field, 'text')``, ``tolower/toupper(field)``,
and ``labels/any(l: l eq 'Architecture')`` on list fields (BCF 3.2.1).
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


class ODataError(ValueError):
    """The query options are not acceptable; the message is safe to return to the client."""


@dataclass(frozen=True)
class Field:
    """One filterable property: its Cypher expression and value type."""

    cypher: str
    kind: Kind


@dataclass
class Compiled:
    where: str | None
    params: dict[str, Any]
    order_by: str
    skip: int
    limit: int

    def where_clause(self, prefix: str = "AND") -> str:
        return f"{prefix} {self.where}" if self.where else ""


@dataclass(frozen=True)
class _Ref:
    cypher: str
    kind: Kind


@dataclass(frozen=True)
class _Lit:
    value: Any


@dataclass(frozen=True)
class _Clause:
    cypher: str


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
    params: dict[str, Any] = field(default_factory=dict)
    lambda_vars: dict[str, _Ref] = field(default_factory=dict)
    counter: int = 0


class _CypherVisitor(NodeVisitor):
    def __init__(self, fields: Mapping[str, Field]) -> None:
        self.scope = _Scope(fields=fields)

    # -- helpers --------------------------------------------------------------

    def _param(self, value: Any) -> str:
        name = f"od{len(self.scope.params)}"
        self.scope.params[name] = value
        return f"${name}"

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
            return result.cypher
        if isinstance(result, _Ref) and result.kind == "boolean":
            return f"{result.cypher} = true"
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
        return _Ref(spec.cypher, spec.kind)

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
            return _Clause(f"{left.cypher} IN {self._param(values)}")

        operator = _COMPARATORS.get(type(node.comparator))
        if operator is None:
            raise ODataError("unsupported comparison operator")
        if right.value is None:
            if operator == "=":
                return _Clause(f"{left.cypher} IS NULL")
            if operator == "<>":
                return _Clause(f"{left.cypher} IS NOT NULL")
            raise ODataError("null can only be compared with eq or ne")
        if left.kind == "string_list":
            # ``labels eq 'x'`` reads as "contains x", which is what event ``type`` filters need (BCF 3.9.1).
            member = f"{self._param(self._coerce(left, right.value))} IN coalesce({left.cypher}, [])"
            if operator == "=":
                return _Clause(member)
            if operator == "<>":
                return _Clause(f"NOT {member}")
            raise ODataError("list fields support eq, ne and any/all only")
        return _Clause(f"{left.cypher} {operator} {self._param(self._coerce(left, right.value))}")

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
            function = "toLower" if name == "tolower" else "toUpper"
            return _Ref(f"{function}({args[0].cypher})", "string")
        if name in ("contains", "startswith", "endswith"):
            if len(args) != 2 or not isinstance(args[0], _Ref) or not isinstance(args[1], _Lit):
                raise ODataError(f"{name}() takes a string field and a string literal")
            if args[0].kind != "string" or not isinstance(args[1].value, str):
                raise ODataError(f"{name}() works on string fields only")
            operator = {"contains": "CONTAINS", "startswith": "STARTS WITH", "endswith": "ENDS WITH"}[name]
            return _Clause(f"{args[0].cypher} {operator} {self._param(args[1].value)}")
        raise ODataError(f"unsupported function '{node.func.name}'")

    def visit_CollectionLambda(self, node: oast.CollectionLambda) -> _Clause:
        owner = self.visit(node.owner)
        if not isinstance(owner, _Ref) or owner.kind != "string_list":
            raise ODataError("any/all applies to list fields only")
        quantifier = "any" if isinstance(node.operator, oast.Any) else "all"
        if node.lambda_ is None:
            return _Clause(f"size({owner.cypher}) > 0" if quantifier == "any" else "true")
        self.scope.counter += 1
        variable = f"lv{self.scope.counter}"
        name = node.lambda_.identifier.name
        self.scope.lambda_vars[name] = _Ref(variable, "string")
        try:
            body = self._as_clause(node.lambda_.expression)
        finally:
            del self.scope.lambda_vars[name]
        return _Clause(f"{quantifier}({variable} IN coalesce({owner.cypher}, []) WHERE {body})")


def compile_filter(expression: str | None, fields: Mapping[str, Field]) -> tuple[str | None, dict[str, Any]]:
    """Return a Cypher boolean expression and its parameters, or (None, {}) for no filter."""
    if expression is None or not expression.strip():
        return None, {}
    if len(expression) > MAX_FILTER_LENGTH:
        raise ODataError("$filter is too long")
    try:
        tree = ODataParser().parse(ODataLexer().tokenize(expression))
    except ODataException as exc:
        raise ODataError(f"invalid $filter: {exc.__class__.__name__}") from exc
    visitor = _CypherVisitor(fields)
    return visitor._as_clause(tree), visitor.scope.params


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
) -> Compiled:
    where, params = compile_filter(filter_, fields)
    order_fields = {name: fields[name].cypher for name in orderable}
    order_by = compile_orderby(orderby, order_fields, default_order)
    offset, limit = compile_paging(top, skip, max_top)
    return Compiled(where=where, params=params, order_by=order_by, skip=offset, limit=limit)
