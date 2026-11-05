# This file was generated with the assistance of an AI coding tool.
"""Relationship types of the IFC graph follow the graph's convention: upper case with underscores."""

import pytest

from opencde.ifcgraph.importer import relationship_type


@pytest.mark.parametrize(
    ("attribute", "expected"),
    [
        ("IsDefinedBy", "IS_DEFINED_BY"),
        ("HasProperties", "HAS_PROPERTIES"),
        ("RelatingPropertyDefinition", "RELATING_PROPERTY_DEFINITION"),
        ("ContainedInStructure", "CONTAINED_IN_STRUCTURE"),
        ("ObjectPlacement", "OBJECT_PLACEMENT"),
        ("Items", "ITEMS"),
        ("HasAssignments", "HAS_ASSIGNMENTS"),
        ("RelatedObjects", "RELATED_OBJECTS"),
        ("IFCData", "IFC_DATA"),  # an acronym stays one word
        ("Axis2Placement", "AXIS2_PLACEMENT"),
    ],
)
def test_attribute_names_become_upper_snake_case(attribute: str, expected: str) -> None:
    assert relationship_type(attribute) == expected


def test_unsafe_names_are_refused() -> None:
    with pytest.raises(ValueError):
        relationship_type("Is-Defined By")
