# IFC-graph

The optional IFC-graph module turns an uploaded IFC model into graph data, so
that a BCF viewpoint's components can be joined to the building elements they
point at, and so that questions about the model can be asked in Cypher next to
the issues and documents.

Turn it on with `OPENCDE_IFCGRAPH_ENABLED=true` and install the `ifcgraph`
extra (`uv sync --extra ifcgraph`; the Docker image includes it).

## What happens on upload

1. A Documents API upload completes (or a file is uploaded from the selection
   page, or a BCF project document is posted) with a `.ifc` or `.ifczip` name.
2. The server creates an `IfcModel` node (state `queued`) attached to the
   project and starts a conversion in the background, one at a time.
3. A separate worker process (`python -m opencde.ifcgraph.worker`) parses the
   file with IfcOpenShell. It runs with a time limit
   (`OPENCDE_IFCGRAPH_TIMEOUT_SECONDS`, 15 minutes), an address-space limit on
   POSIX (`OPENCDE_IFCGRAPH_MEMORY_MB`, 4 GiB) and an entity cap
   (`OPENCDE_IFCGRAPH_MAX_ENTITIES`). A crash or a hang kills the worker, not
   the server. `.ifczip` is unpacked with the upload size cap.
4. The records are imported in batches of `UNWIND … CREATE` (portable Cypher,
   no APOC). The `IfcModel` ends in state `done` with counts and the
   `IfcProject` guid, or `failed` with an error.

## The graph

Every entity becomes an `IfcEntity` node carrying its class and all its
supertypes as labels, for example `IfcEntity:IfcWallStandardCase:IfcWall:
IfcBuildingElement:IfcElement:IfcProduct:IfcObject:IfcObjectDefinition:IfcRoot`.

| Property | Meaning |
|---|---|
| `id` | `<model id>:<STEP id>`, unique |
| `model_id`, `step_id` | the model and the `#123` number in the file |
| `ifc_class` | the concrete class |
| `GlobalId`, `Name`, `Description`, `Tag`, … | every literal attribute of the entity, by its IFC name |

Attributes that point at other entities become relationships named after the
attribute: `(:IfcRelDefinesByProperties)-[:RelatingPropertyDefinition]->(:IfcPropertySet)-[:HasProperties]->(:IfcPropertySingleValue)`.
Inverse attributes become relationships too, so both directions read
naturally: `(:IfcWall)-[:IsDefinedBy]->(:IfcRelDefinesByProperties)`.
Select values are unwrapped (`IfcLabel('3')` becomes `"3"`).

Left out by default (`OPENCDE_IFCGRAPH_INCLUDE_GEOMETRY=false`): representation
items, representations, profiles, placements and styles; they are most of a
model and seldom what a CDE query needs. `IfcOwnerHistory` is kept for the
`IfcProject` only.

## Linking BCF components

When a viewpoint is created with components, every component whose `ifc_guid`
matches the `GlobalId` of an element in one of the project's imported models
gets a `SAME_AS` relationship to it. If the element carries the configured
property (`OPENCDE_IFCGRAPH_GTIN_PROPERTY_SET=Reuse`,
`OPENCDE_IFCGRAPH_GTIN_PROPERTY=GTIN`), its value is copied to the component as
`gtin`. This is the use case of the 2023 research report: an inspection
(BCF topic) pointing at building products identified by GTIN.

```cypher
// Which products does this viewpoint point at, and what are their GTINs?
MATCH (:Viewpoint {guid: $viewpoint})-[:HAS_COMPONENT]->(c:Component)-[:SAME_AS]->(e:IfcProduct)
RETURN c.ifc_guid, e.Name, c.gtin
```

```cypher
// The report's query, directly on the model: GTIN of every wall.
MATCH (w:IfcWall)-[:IsDefinedBy]->(:IfcRelDefinesByProperties)-[:RelatingPropertyDefinition]
      ->(:IfcPropertySet {Name: 'Reuse'})-[:HasProperties]->(p:IfcPropertySingleValue {Name: 'GTIN'})
RETURN w.GlobalId, w.Name, p.NominalValue
```

```cypher
// Every issue that touches a given element.
MATCH (e:IfcEntity {GlobalId: $guid})<-[:SAME_AS]-(:Component)<-[:HAS_COMPONENT]-(v:Viewpoint)<-[:HAS_VIEWPOINT]-(t:Topic)
RETURN DISTINCT t.server_assigned_id, t.title, t.topic_status
```

The BCF `files_information` service shows the `IfcProject` guid of imported
models as `ifc_project`, which lets clients fill in the topic header's files.

## Limits and status

- One conversion at a time; large models queue. The example model (248
  entities) imports in about a second; a 200 MB architectural model takes
  minutes.
- The `IfcModel` node carries `state`, `entities`, `relationships`, `skipped`,
  `schema`, `ifc_project_guid`, timestamps and `error`. Administrators can
  inspect it in Neo4j Browser or Memgraph Lab:
  `MATCH (m:IfcModel) RETURN m.file_name, m.state, m.entities, m.error`.
- Deleting a project deletes its models' entities with it.
