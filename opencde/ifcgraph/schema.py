# This file was generated with the assistance of an AI coding tool.
"""What an IFC schema says about a class: its attributes by position, what they hold, and what refers back.

Only IfcOpenShell's schema tables are used here, which do not read any file. The keywords are the upper case ones of
a STEP file (``IFCWALL``); the names that come back are the schema's (``IfcWall``).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from opencde.ifcgraph.step import StepError

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")


def safe_identifier(name: str) -> str:
    """A name that came from a file and is about to become part of a query's text."""
    if not _IDENTIFIER.match(name):
        raise ValueError(f"unsafe identifier from converter: {name!r}")
    return name


def relationship_type(attribute: str) -> str:
    """The relationship type for an IFC attribute: upper case with underscores, as every relationship in the
    graph is written (``IsDefinedBy`` becomes ``IS_DEFINED_BY``, ``HasProperties`` ``HAS_PROPERTIES``)."""
    return safe_identifier(_CAMEL_BOUNDARY.sub("_", safe_identifier(attribute)).upper())


@dataclass(frozen=True, slots=True)
class Attribute:
    """One attribute of a class. ``kinds`` are its aggregates, outermost first (``("list", "list")``), and ``leaf``
    what they hold: ``entity``, ``select``, ``enumeration``, or a simple type such as ``real`` or ``string``."""

    name: str
    kinds: tuple[str, ...]
    leaf: str
    derived: bool
    relationship: str


@dataclass(frozen=True, slots=True)
class Inverse:
    """An attribute of a class that says who refers to it, through ``attribute`` of the class ``source``."""

    name: str
    attribute: str
    source: bytes


def _shape(declared: Any) -> tuple[tuple[str, ...], str]:
    aggregate = declared.as_aggregation_type()
    if aggregate:
        kinds, leaf = _shape(aggregate.type_of_element())
        return (aggregate.type_of_aggregation_string(), *kinds), leaf
    named = declared.as_named_type()
    if named:
        declaration = named.declared_type()
        definition = declaration.as_type_declaration()
        if definition:
            return _shape(definition.declared_type())
        if declaration.as_enumeration_type():
            return (), "enumeration"
        if declaration.as_select_type():
            return (), "select"
        return (), "entity"
    return (), declared.as_simple_type().declared_type()


class Schema:
    def __init__(self, name: str) -> None:
        try:
            from ifcopenshell import ifcopenshell_wrapper
        except ImportError as exc:  # pragma: no cover - depends on the optional extra
            raise StepError("IfcOpenShell is not installed; install the 'ifcgraph' extra") from exc
        try:
            self._schema: Any = ifcopenshell_wrapper.schema_by_name(name)
        except RuntimeError as exc:
            raise StepError(f"IfcOpenShell knows no schema named {name[:40]!r}") from exc
        self._attributes: dict[bytes, tuple[Attribute, ...] | None] = {}
        self._types: dict[bytes, tuple[tuple[str, ...], str] | None] = {}
        self._chains: dict[bytes, tuple[str, ...]] = {}
        self._inverses: dict[bytes, Mapping[str, tuple[Inverse, ...]]] = {}

    def _declaration(self, keyword: bytes) -> Any:
        try:
            return self._schema.declaration_by_name(keyword.decode("ascii"))
        except (RuntimeError, UnicodeDecodeError):
            return None

    def _entity(self, keyword: bytes) -> Any:
        declaration = self._declaration(keyword)
        return declaration.as_entity() if declaration is not None else None

    def attributes(self, keyword: bytes) -> tuple[Attribute, ...] | None:
        """The attributes of a class by position, or None for what is no class of this schema."""
        if keyword not in self._attributes:
            entity = self._entity(keyword)
            if entity:
                derived = entity.derived()
                attributes = []
                for position, attribute in enumerate(entity.all_attributes()):
                    kinds, leaf = _shape(attribute.type_of_attribute())
                    name = attribute.name()
                    attributes.append(Attribute(name, kinds, leaf, bool(derived[position]), relationship_type(name)))
                self._attributes[keyword] = tuple(attributes)
            else:
                self._attributes[keyword] = None
        return self._attributes[keyword]

    def defined_type(self, keyword: bytes) -> tuple[tuple[str, ...], str] | None:
        """The aggregates and the leaf of a typed value such as ``IFCLABEL``, or None for what is no such type."""
        if keyword not in self._types:
            declaration = self._declaration(keyword)
            definition = declaration.as_type_declaration() if declaration is not None else None
            self._types[keyword] = _shape(definition.declared_type()) if definition else None
        return self._types[keyword]

    def chain(self, keyword: bytes) -> tuple[str, ...]:
        """The class and its supertypes, nearest first, by the schema's names. Empty for what is no class."""
        known = self._chains.get(keyword)
        if known is None:
            names = []
            entity = self._entity(keyword)
            while entity:
                names.append(entity.name())
                entity = entity.supertype()
            known = self._chains[keyword] = tuple(names)
        return known

    def inverses(self, keyword: bytes) -> Mapping[str, tuple[Inverse, ...]]:
        """What refers back to a class, by the attribute that does the referring."""
        known = self._inverses.get(keyword)
        if known is None:
            found: dict[str, list[Inverse]] = {}
            entity = self._entity(keyword)
            if entity:
                for inverse in entity.all_inverse_attributes():
                    attribute = inverse.attribute_reference().name()
                    source = inverse.entity_reference().name().upper().encode("ascii")
                    found.setdefault(attribute, []).append(Inverse(inverse.name(), attribute, source))
            known = self._inverses[keyword] = {name: tuple(items) for name, items in found.items()}
        return known

    def refers_back(self, source: bytes, attribute: str, target: bytes) -> list[str]:
        """The inverse attributes of ``target`` that an instance of ``source`` shows up in through ``attribute``."""
        inverses = self.inverses(target).get(attribute)
        if not inverses:
            return []
        ancestors = {name.upper().encode("ascii") for name in self.chain(source)}
        return [inverse.name for inverse in inverses if inverse.source in ancestors]
