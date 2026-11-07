# This file was generated with the assistance of an AI coding tool.
"""Between the values of a STEP instance and what a node of the graph holds, in both directions and without loss.

A value goes where a query would look for it. A number, a string or an enumeration is a property named after its
attribute, a flat list of them a list property, and a nested list JSON text, since Neo4j has no nested lists. A
reference is a relationship named after its attribute, and the relationship's ``position`` says where in the attribute
it stands, ``[row, column]`` in a nested list. A typed value such as ``IFCLABEL('x')`` is its value, with the keyword in
``<attribute>__type``. What the file leaves out (``$``, and ``*`` where the schema derives the attribute) is left out.

Anything that does not come back the same from that form goes in tagged JSON instead, under the property of the
attribute with ``$json`` as its type: lists of typed values, a mix of values and references in one SET, a string that
stands where the schema has an enumeration, raw bytes. Every attribute is read back as it is written, so which values
those are is not a list to keep up to date. An instance the schema does not know, or that has another number of
attributes than the schema says, has all of it in ``ifc_args`` in the same form.

A reference to what is no node, an instance in a block or one the file does not have, is its id in
``<attribute>__step``, or a list of ids if every reference in a flat list is one. In tagged JSON a reference stands for
the relationship at that position, so that the relationships are the one place that says what refers to what between
nodes, and only a reference to what is no node stays in the text.

Geometry is kept in blocks, unless it is asked to be nodes. It is most of a model and a graph of its own: 17-94% of it
in the samples belongs to more than one product, so it cannot be properties of the products. So every instance below a
line drawn by class is written out as STEP, in order of id, and compressed into blocks of text on ``StepBlock`` nodes
that hang off the ``IfcModel``. Those instances are in the graph, but out of Cypher's reach.
"""

from __future__ import annotations

import base64
import json
import math
import zlib
from collections.abc import Container, Iterable, Mapping, Sequence
from typing import Any

from opencde.ifcgraph.schema import Attribute, Schema
from opencde.ifcgraph.step import string_atom, string_of_atom

TYPE_SUFFIX = "__type"
STEP_SUFFIX = "__step"
TAGGED = "$json"
ALL_ARGUMENTS = "ifc_args"
ARGUMENT_RELATIONSHIP = "ARGUMENT"
_NEO4J_INTEGER = 2**63


class _NotNatural(Exception):
    """This value has no form as an ordinary property."""


def _natural_atom(atom: Any, leaf: str) -> Any:
    if not isinstance(atom, bytes):
        raise _NotNatural
    first = atom[:1]
    if first == b"r":
        number = float.fromhex(atom[1:].decode("ascii"))
        if math.isfinite(number):
            return number
    elif first == b"i":
        integer = int(atom[1:])
        if -_NEO4J_INTEGER <= integer < _NEO4J_INTEGER:
            return integer
    elif first == b"s":
        if leaf == "string":
            text = string_of_atom(atom)
            if text.isprintable() or not any(_unstorable(character) for character in text):
                return text
    elif first == b".":
        if leaf == "enumeration":
            return atom[1:-1].decode("ascii")
        if leaf in ("logical", "boolean") and atom in (b".T.", b".F."):
            return atom == b".T."
        if leaf == "logical" and atom == b".U.":
            return "UNKNOWN"
    elif first == b'"' and leaf == "binary":
        return atom[1:-1].decode("ascii")
    raise _NotNatural


def _unstorable(character: str) -> bool:
    """A character the database's strings cannot be trusted with: NUL, and half of a surrogate pair."""
    code = ord(character)
    return code == 0 or 0xD800 <= code <= 0xDFFF


def _atom_of(value: Any, leaf: str) -> bytes:
    if isinstance(value, bool):
        return b".T." if value else b".F."
    if isinstance(value, int):
        return b"i%d" % value
    if isinstance(value, float):
        return b"r%s" % value.hex().encode("ascii")
    if isinstance(value, str):
        if leaf == "string":
            return string_atom(value)
        if leaf == "enumeration":
            return b".%s." % value.encode("ascii")
        if leaf == "logical" and value == "UNKNOWN":
            return b".U."
        if leaf == "binary":
            return b'"%s"' % value.encode("ascii")
    raise _NotNatural


def _natural(value: Any, kinds: tuple[str, ...], leaf: str, known: Container[int]) -> tuple[Any, list[tuple[Any, int]]]:
    """A value as a property and as references, by position. Raises when it has no such form."""
    if isinstance(value, int):
        if kinds or value not in known:
            raise _NotNatural
        return None, [(0, value)]
    if not isinstance(value, list):
        if kinds:
            raise _NotNatural
        return _natural_atom(value, leaf), []
    if not kinds:
        raise _NotNatural
    if not value:
        return [], []
    if len(kinds) == 1:
        if all(isinstance(item, int) for item in value):
            if not all(item in known for item in value):
                raise _NotNatural
            return None, list(enumerate(value))
        items = [_natural_atom(item, leaf) for item in value]
        if len({type(item) for item in items}) != 1:
            raise _NotNatural
        return items, []
    if len(kinds) != 2 or not all(isinstance(row, list) and row for row in value):
        raise _NotNatural
    if all(isinstance(item, int) for row in value for item in row):
        if not all(item in known for row in value for item in row):
            raise _NotNatural
        return None, [([row, column], item) for row, items in enumerate(value) for column, item in enumerate(items)]
    return json.dumps([[_natural_atom(item, leaf) for item in row] for row in value]), []


def _from_natural(prop: Any, references: Sequence[tuple[Any, int]], kinds: tuple[str, ...], leaf: str) -> Any:
    if references:
        ordered = sorted(references, key=lambda reference: reference[0])
        if not kinds:
            if len(ordered) != 1:
                raise _NotNatural
            return ordered[0][1]
        if len(kinds) == 1:
            return [target for _position, target in ordered]
        rows: list[list[int]] = []
        current = None
        for (row, _column), target in ordered:
            if row != current:
                rows.append([])
                current = row
            rows[-1].append(target)
        return rows
    if not kinds:
        return _atom_of(prop, leaf)
    if isinstance(prop, list):
        return [_atom_of(item, leaf) for item in prop]
    if isinstance(prop, str):
        return [[_atom_of(item, leaf) for item in row] for row in json.loads(prop)]
    raise _NotNatural


def _tagged(value: Any, known: Container[int], references: list[tuple[Any, int]]) -> Any:
    """Any value as JSON, with its references taken out."""
    if isinstance(value, int):
        if value not in known:
            return {"d": value}
        references.append((len(references), value))
        return {"r": len(references) - 1}
    if isinstance(value, list):
        return [_tagged(item, known, references) for item in value]
    if isinstance(value, tuple):
        return {"t": value[0].decode("ascii"), "v": [_tagged(item, known, references) for item in value[1]]}
    first = value[:1]
    if value == b"$":
        return None
    if value == b"*":
        return {"a": "*"}
    if first == b"r":
        number = float.fromhex(value[1:].decode("ascii"))
        return number if math.isfinite(number) else {"f": value[1:].decode("ascii")}
    if first == b"i":
        return int(value[1:])
    if first == b"s":
        return string_of_atom(value)
    if first == b"x":
        return {"x": value.split(b":", 1)[1].decode("latin-1")}
    if first == b".":
        return {"e": value[1:-1].decode("ascii")}
    return {"b": value[1:-1].decode("ascii")}


def _from_tagged(value: Any, references: Mapping[int, int]) -> Any:
    if value is None:
        return b"$"
    if isinstance(value, str):
        return string_atom(value)
    if isinstance(value, int):
        return b"i%d" % value
    if isinstance(value, float):
        return b"r%s" % value.hex().encode("ascii")
    if isinstance(value, list):
        return [_from_tagged(item, references) for item in value]
    if "r" in value:
        return references[value["r"]]
    if "d" in value:
        return value["d"]
    if "t" in value:
        return (value["t"].encode("ascii"), [_from_tagged(item, references) for item in value["v"]])
    if "a" in value:
        return b"*"
    if "f" in value:
        return b"r%s" % value["f"].encode("ascii")
    if "x" in value:
        raw = value["x"].encode("latin-1")
        return b"x%d:%s" % (len(raw), raw)
    if "e" in value:
        return b".%s." % value["e"].encode("ascii")
    return b'"%s"' % value["b"].encode("ascii")


def _ids_outside_the_nodes(value: Any, kinds: tuple[str, ...], known: Container[int]) -> Any:
    """What an attribute holds that refers only to what is no node: one id, or a flat list of them. Otherwise None."""
    if isinstance(value, int):
        return value if not kinds and value not in known else None
    if isinstance(value, list) and value and len(kinds) == 1:
        if all(isinstance(item, int) and item not in known for item in value):
            return value
    return None


def _absent(attribute: Attribute) -> bytes:
    return b"*" if attribute.derived else b"$"


def _encode_natural(
    value: Any, attribute: Attribute, schema: Schema, known: Container[int]
) -> tuple[Any, str | None, list[tuple[Any, int]]]:
    """A value's property, its type's name and its references, when it comes back the same from them."""
    kinds, leaf, type_name = attribute.kinds, attribute.leaf, None
    inner = value
    if isinstance(value, tuple):
        shape = schema.defined_type(value[0])
        if shape is None or len(value[1]) != 1:
            raise _NotNatural
        kinds, leaf = shape
        type_name, inner = value[0].decode("ascii"), value[1][0]
    prop, references = _natural(inner, kinds, leaf, known)
    if _from_natural(prop, references, kinds, leaf) != inner:
        raise _NotNatural
    return prop, type_name, references


def encode_block(lines: bytes) -> str:
    """Instances as a block's text. A string, for it is the one thing both databases store the same way."""
    return base64.b64encode(zlib.compress(lines, 6)).decode("ascii")


def decode_block(text: str) -> bytes:
    return zlib.decompress(base64.b64decode(text))


def encode_header(header: Iterable[tuple[bytes, list[Any]]]) -> str:
    """A file's header, as JSON text. It has no references."""
    return json.dumps(
        [[keyword.decode("ascii"), [_tagged(value, (), []) for value in values]] for keyword, values in header]
    )


def decode_header(text: str) -> list[tuple[bytes, list[Any]]]:
    return [
        (keyword.encode("ascii"), [_from_tagged(value, {}) for value in values]) for keyword, values in json.loads(text)
    ]


def encode_instance(
    keyword: bytes, parameters: list[Any], schema: Schema, known: Container[int]
) -> tuple[dict[str, Any], list[tuple[str, Any, int]]]:
    """The properties of an instance, and its references as ``(attribute name, position, target)``."""
    attributes = schema.attributes(keyword)
    properties: dict[str, Any] = {}
    references: list[tuple[str, Any, int]] = []
    if attributes is None or len(attributes) != len(parameters):
        found: list[tuple[Any, int]] = []
        properties[ALL_ARGUMENTS] = json.dumps([_tagged(value, known, found) for value in parameters])
        references.extend((ARGUMENT_RELATIONSHIP, position, target) for position, target in found)
        return properties, references
    for attribute, value in zip(attributes, parameters, strict=True):
        if value == _absent(attribute):
            continue
        name = attribute.name
        outside = _ids_outside_the_nodes(value, attribute.kinds, known)
        if outside is not None:
            properties[name + STEP_SUFFIX] = outside
            continue
        try:
            prop, type_name, found = _encode_natural(value, attribute, schema, known)
        except _NotNatural:
            found = []
            properties[name] = json.dumps(_tagged(value, known, found))
            properties[name + TYPE_SUFFIX] = TAGGED
        else:
            if prop is not None:
                properties[name] = prop
            if type_name is not None:
                properties[name + TYPE_SUFFIX] = type_name
        references.extend((name, position, target) for position, target in found)
    return properties, references


def decode_instance(
    keyword: bytes,
    properties: Mapping[str, Any],
    references: Iterable[tuple[str, Any, int]],
    schema: Schema,
) -> list[Any]:
    """The parameters of an instance. Inverse relationships and whatever else a node has picked up are not read:
    only what the schema says is an attribute of the class, or what ``encode_instance`` wrote for one it does not know.

    ``references`` holds relationship types (``HAS_PROPERTIES``), as the graph has them.
    """
    by_type: dict[str, list[tuple[Any, int]]] = {}
    for relationship, position, target in references:
        by_type.setdefault(relationship, []).append((position, target))
    if ALL_ARGUMENTS in properties:
        found = dict(by_type.get(ARGUMENT_RELATIONSHIP, ()))
        return [_from_tagged(value, found) for value in json.loads(properties[ALL_ARGUMENTS])]
    parameters: list[Any] = []
    attributes = schema.attributes(keyword)
    if attributes is None:
        raise ValueError(f"{keyword!r} is no class of the schema, and the node does not hold its arguments")
    for attribute in attributes:
        outside = properties.get(attribute.name + STEP_SUFFIX)
        if outside is not None:
            parameters.append(outside)
            continue
        prop = properties.get(attribute.name)
        type_name = properties.get(attribute.name + TYPE_SUFFIX)
        found_here = by_type.get(attribute.relationship, ())
        if type_name == TAGGED:
            parameters.append(_from_tagged(json.loads(str(prop)), dict(found_here)))
        elif prop is None and not found_here:
            parameters.append(_absent(attribute))
        elif type_name is not None:
            shape = schema.defined_type(type_name.encode("ascii"))
            if shape is None:
                raise ValueError(f"{type_name!r} is no type of the schema")
            parameters.append((type_name.encode("ascii"), [_from_natural(prop, found_here, *shape)]))
        else:
            parameters.append(_from_natural(prop, found_here, attribute.kinds, attribute.leaf))
    return parameters
