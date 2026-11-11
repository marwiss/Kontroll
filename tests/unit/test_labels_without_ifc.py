# This file was generated with the assistance of an AI coding tool.
"""A label that begins with Ifc is one of IFC's classes (F23 a): the server's own records are labelled without it."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ifcopenshell = pytest.importorskip("ifcopenshell")

ROOT = Path(__file__).resolve().parents[2]
#: A label in a Cypher pattern, such as ``(e:IfcWall)``; an annotation has a space after its colon.
LABEL = re.compile(r":(Ifc[A-Za-z0-9]+)")
SCHEMAS = ("IFC2X3", "IFC4", "IFC4X3_ADD2")


def _is_a_class(name: str) -> bool:
    wrapper = ifcopenshell.ifcopenshell_wrapper
    for schema in SCHEMAS:
        try:
            wrapper.schema_by_name(schema).declaration_by_name(name)
        except RuntimeError:
            continue
        return True
    return False


def test_every_label_that_begins_with_ifc_is_an_ifc_class() -> None:
    found: dict[str, set[str]] = {}
    for folder in ("opencde", "tests"):
        for path in (ROOT / folder).rglob("*.py"):
            for name in LABEL.findall(path.read_text(encoding="utf-8")):
                found.setdefault(name, set()).add(path.relative_to(ROOT).as_posix())
    assert found, "the named queries label IFC classes"
    strangers = {name: sorted(paths) for name, paths in found.items() if not _is_a_class(name)}
    assert not strangers, f"labels that begin with Ifc without being IFC classes: {strangers}"
