# This file was generated with the assistance of an AI coding tool.
"""Named queries on the IFC graph of a document version, for members of its project (ADR 0016).

Reading a model is asking it questions: how many elements of each class it has, which storeys and spaces, how large
they are, what the walls are made of, which value a property has. A member asks by name with parameters, never with
Cypher of their own; free Cypher stays with administrators (``admin/graph_query.py``). Every statement here starts at
the user's node and reaches the model through ``MEMBER_OF`` and ``HAS_MODEL``, takes values only as parameters, and
only reads; ``tests/unit/test_ifc_queries.py`` holds each to that, with the administrators' own check.

The queries follow the graph as IFC-LPG makes it: an ``IfcEntity`` with its class and supertypes as labels,
``model_id`` and the literal attributes as properties, and every reference a relationship named after its attribute.
They use the forward relationships, which every form of the graph has.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field

#: At most this many rows in an answer, and at most this long for a query to run.
MAX_ROWS = 10_000
TIMEOUT_SECONDS = 10.0

#: The model of one document version that the user may read: the newest one converted, when there are several.
MODEL = """
MATCH (:User {id: $user_id})-[:MEMBER_OF]->(:Project)-[:HAS_MODEL]->(m:IfcModel)
WHERE m.document_id = $document_id AND m.version_index = $version_index AND m.state = 'done'
WITH m ORDER BY m.created_at DESC LIMIT 1
"""

#: The same model in the working copy, by the id the archive gave it (ADR 0024).
WORKCOPY_MODEL = """
MATCH (m:IfcModel {id: $model_id, state: 'done'})
"""

_CLASS = re.compile(r"^Ifc[A-Za-z0-9]{1,64}$")
_GUID = re.compile(r"^[0-9A-Za-z_$]{22}$")

#: The query on what changed since a version, answered from the versions' change sets, not from the graph
#: (``documents/routes_queries.py``); listed and announced with the others.
CHANGED_SINCE = "changed-since"
CHANGED_SINCE_COLUMNS = (
    "version_index",
    "change_set_id",
    "author",
    "approved_by",
    "whole_file",
    "guid",
    "step_id",
    "path",
    "attribute",
    "op",
)
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


class InvalidParameters(ValueError):
    """The parameters do not fit the query; the message says which and why."""


@dataclass(frozen=True)
class Parameter:
    name: str
    description: str
    required: bool = False
    is_class: bool = False
    is_guid: bool = False

    def value_of(self, raw: str) -> str:
        if self.is_class:
            if not _CLASS.match(raw):
                raise InvalidParameters(f"{self.name} must be the name of an IFC class, such as IfcWall")
            return raw
        if self.is_guid:
            if not _GUID.match(raw):
                raise InvalidParameters(f"{self.name} must be a GlobalId: 22 characters of IFC's base 64")
            return raw
        if not 1 <= len(raw) <= 255 or _CONTROL.search(raw):
            raise InvalidParameters(f"{self.name} must be 1 to 255 characters, with no control characters")
        return raw


@dataclass(frozen=True)
class NamedQuery:
    name: str
    description: str
    columns: tuple[str, ...]
    body: str
    parameters: tuple[Parameter, ...] = field(default=())

    @property
    def cypher(self) -> str:
        return MODEL + self.body

    @property
    def cypher_in_workcopy(self) -> str:
        """The same query on the working copy (ADR 0024), where the archive has already found the model and
        checked the membership: it names the model by id and holds no accounts."""
        return WORKCOPY_MODEL + self.body

    def bind(self, raw: Mapping[str, str]) -> dict[str, str | None]:
        """The query's parameters from what a client sent; raises :class:`InvalidParameters`."""
        known = {parameter.name for parameter in self.parameters}
        unknown = sorted(set(raw) - known)
        if unknown:
            raise InvalidParameters(f"{self.name} takes no parameter {', '.join(unknown)}")
        values: dict[str, str | None] = {}
        for parameter in self.parameters:
            given = raw.get(parameter.name)
            if given is None or given == "":
                if parameter.required:
                    raise InvalidParameters(f"{self.name} needs the parameter {parameter.name}")
                values[parameter.name] = None
            else:
                values[parameter.name] = parameter.value_of(given)
        return values


_OF_CLASS = Parameter("class", "Only elements of this IFC class or its subclasses, such as IfcWall", is_class=True)

QUERIES: dict[str, NamedQuery] = {
    query.name: query
    for query in (
        NamedQuery(
            "entity",
            "One rooted entity by its GlobalId: its class, every literal attribute, and the instances it refers to and "
            "is referred to by, each by the IFC attribute, STEP id and class, with the GlobalId where it has one.",
            ("global_id", "class", "step_id", "attributes", "references", "referenced_by"),
            """
            MATCH (e:IfcRoot {model_id: m.id})
            WHERE e.GlobalId = $global_id
            OPTIONAL MATCH (e)-[r]->(t:IfcEntity)
            WITH e, collect(CASE WHEN r IS NULL THEN NULL ELSE
                 {attribute: type(r), step_id: t.step_id, global_id: t.GlobalId, class: t.ifc_class} END) AS references
            OPTIONAL MATCH (e)<-[r2]-(s:IfcEntity)
            WITH e, references, collect(CASE WHEN r2 IS NULL THEN NULL ELSE
                 {attribute: type(r2), step_id: s.step_id, global_id: s.GlobalId, class: s.ifc_class} END) AS referenced_by
            RETURN e.GlobalId AS global_id, e.ifc_class AS class, e.step_id AS step_id, properties(e) AS attributes,
                   references, referenced_by
            """,
            (
                Parameter(
                    "global_id", "The GlobalId of a rooted entity, such as a wall or a storey", True, is_guid=True
                ),
            ),
        ),
        NamedQuery(
            "element-classes",
            "How many elements the model has of each class.",
            ("class", "count"),
            """
            MATCH (e:IfcElement {model_id: m.id})
            RETURN e.ifc_class AS class, count(e) AS count
            ORDER BY count DESC, class
            """,
        ),
        NamedQuery(
            "elements",
            "The elements of a class, with the spatial structure that contains each.",
            ("global_id", "class", "name", "container"),
            """
            MATCH (e:IfcRoot {model_id: m.id})
            WHERE $class IN labels(e)
            OPTIONAL MATCH (e)<-[:RELATED_ELEMENTS]-(:IfcRelContainedInSpatialStructure)-[:RELATING_STRUCTURE]->(s)
            RETURN e.GlobalId AS global_id, e.ifc_class AS class, e.Name AS name, s.Name AS container
            ORDER BY name, global_id
            """,
            (Parameter("class", "The IFC class, such as IfcWall; its subclasses count too", True, True),),
        ),
        NamedQuery(
            "storeys",
            "The building storeys, with their elevation and how many elements and spaces each holds.",
            ("global_id", "name", "elevation", "elements", "spaces"),
            """
            MATCH (s:IfcBuildingStorey {model_id: m.id})
            OPTIONAL MATCH (s)<-[:RELATING_STRUCTURE]-(:IfcRelContainedInSpatialStructure)-[:RELATED_ELEMENTS]->(e)
            WITH s, count(DISTINCT e) AS elements
            OPTIONAL MATCH (s)<-[:RELATING_OBJECT]-(:IfcRelAggregates)-[:RELATED_OBJECTS]->(sp:IfcSpace)
            RETURN s.GlobalId AS global_id, s.Name AS name, s.Elevation AS elevation, elements,
                   count(DISTINCT sp) AS spaces
            ORDER BY elevation, name
            """,
        ),
        NamedQuery(
            "spaces",
            "The spaces, with their storey and their net and gross floor areas where the model gives them.",
            ("global_id", "name", "long_name", "storey", "net_floor_area", "gross_floor_area"),
            """
            MATCH (sp:IfcSpace {model_id: m.id})
            OPTIONAL MATCH (sp)<-[:RELATED_OBJECTS]-(:IfcRelAggregates)-[:RELATING_OBJECT]->(s:IfcBuildingStorey)
            OPTIONAL MATCH (sp)<-[:RELATED_OBJECTS]-(:IfcRelDefinesByProperties)-[:RELATING_PROPERTY_DEFINITION]
                  ->(:IfcElementQuantity)-[:QUANTITIES]->(q:IfcQuantityArea)
            WHERE q.Name IN ['NetFloorArea', 'GrossFloorArea']
            WITH sp, s, collect(q) AS areas
            RETURN sp.GlobalId AS global_id, sp.Name AS name, sp.LongName AS long_name, s.Name AS storey,
                   head([a IN areas WHERE a.Name = 'NetFloorArea' | a.AreaValue]) AS net_floor_area,
                   head([a IN areas WHERE a.Name = 'GrossFloorArea' | a.AreaValue]) AS gross_floor_area
            ORDER BY storey, name, global_id
            """,
        ),
        NamedQuery(
            "areas",
            "The net floor area of each storey's spaces, added up; a building's area is the sum of its storeys'.",
            ("storey", "elevation", "spaces", "net_floor_area"),
            """
            MATCH (s:IfcBuildingStorey {model_id: m.id})
            OPTIONAL MATCH (s)<-[:RELATING_OBJECT]-(:IfcRelAggregates)-[:RELATED_OBJECTS]->(sp:IfcSpace)
            OPTIONAL MATCH (sp)<-[:RELATED_OBJECTS]-(:IfcRelDefinesByProperties)-[:RELATING_PROPERTY_DEFINITION]
                  ->(:IfcElementQuantity)-[:QUANTITIES]->(q:IfcQuantityArea {Name: 'NetFloorArea'})
            RETURN s.Name AS storey, s.Elevation AS elevation, count(DISTINCT sp) AS spaces,
                   sum(q.AreaValue) AS net_floor_area
            ORDER BY elevation, storey
            """,
        ),
        NamedQuery(
            "materials",
            "The materials of each element: a material of its own, or those of its layers, list or constituents.",
            ("global_id", "class", "name", "materials"),
            """
            MATCH (e:IfcElement {model_id: m.id})
            WHERE $class IS NULL OR $class IN labels(e)
            OPTIONAL MATCH (e)<-[:RELATED_OBJECTS]-(:IfcRelAssociatesMaterial)-[:RELATING_MATERIAL]->(r)
            OPTIONAL MATCH (r)-[:FOR_LAYER_SET]->(:IfcMaterialLayerSet)-[:MATERIAL_LAYERS]->(:IfcMaterialLayer)
                  -[:MATERIAL]->(usage:IfcMaterial)
            OPTIONAL MATCH (r)-[:MATERIAL_LAYERS]->(:IfcMaterialLayer)-[:MATERIAL]->(layer:IfcMaterial)
            OPTIONAL MATCH (r)-[:MATERIALS]->(listed:IfcMaterial)
            OPTIONAL MATCH (r)-[:MATERIAL_CONSTITUENTS]->(:IfcMaterialConstituent)-[:MATERIAL]->(part:IfcMaterial)
            WITH e,
                 collect(DISTINCT CASE WHEN 'IfcMaterial' IN labels(r) THEN r.Name END)
                 + collect(DISTINCT usage.Name) + collect(DISTINCT layer.Name)
                 + collect(DISTINCT listed.Name) + collect(DISTINCT part.Name) AS materials
            RETURN e.GlobalId AS global_id, e.ifc_class AS class, e.Name AS name, materials
            ORDER BY name, global_id
            """,
            (_OF_CLASS,),
        ),
        NamedQuery(
            "property",
            "The value of one property of a property set on every object that has it, with the value's IFC type.",
            ("global_id", "class", "name", "value", "type"),
            """
            MATCH (e:IfcObject {model_id: m.id})
            WHERE $class IS NULL OR $class IN labels(e)
            MATCH (e)<-[:RELATED_OBJECTS]-(:IfcRelDefinesByProperties)-[:RELATING_PROPERTY_DEFINITION]
                  ->(:IfcPropertySet {Name: $pset})-[:HAS_PROPERTIES]->(v:IfcPropertySingleValue {Name: $property})
            RETURN e.GlobalId AS global_id, e.ifc_class AS class, e.Name AS name, v.NominalValue AS value,
                   v.NominalValue__type AS type
            ORDER BY name, global_id
            """,
            (
                Parameter("pset", "The property set, such as Pset_WallCommon", True),
                Parameter("property", "The property, such as FireRating", True),
                _OF_CLASS,
            ),
        ),
    )
}
