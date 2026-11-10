# IFC-LPG

The optional IFC-LPG module turns an uploaded IFC model into graph data, so
that a BCF viewpoint's components can be joined to the building elements they
point at, and so that questions about the model can be asked in Cypher next to
the issues and documents.

Turn it on with `OPENCDE_IFC_LPG_ENABLED=true` and install the `ifc-lpg`
extra (`uv sync --extra ifc-lpg`). The Docker image includes the extra by
default (`ARG OPENCDE_EXTRAS` in the Dockerfile), which more than doubles its
size (about 680 MB against 300 MB); build with `--build-arg OPENCDE_EXTRAS=`
for a slimmer image without IfcOpenShell when the module stays off.

Until November 2026 the module was named IFC-graph. Its settings were named
`OPENCDE_IFCGRAPH_*` and its command `opencde ifcgraph`, and both still work;
the server's log and `opencde doctor` name the old settings it is given.

## What happens on upload

1. A Documents API upload completes (or a file is uploaded from the selection
   page, or a BCF project document is posted) with a `.ifc` or `.ifczip` name.
2. The server creates an `IfcModel` node (state `queued`) attached to the
   project and starts a conversion in the background, one at a time.
3. A separate worker process (`python -m opencde.ifcgraph.worker`) parses the
   file with IfcOpenShell. It runs with a time limit
   (`OPENCDE_IFC_LPG_TIMEOUT_SECONDS`, 15 minutes), an address-space limit on
   POSIX (`OPENCDE_IFC_LPG_MEMORY_MB`, 4 GiB) and an entity cap
   (`OPENCDE_IFC_LPG_MAX_ENTITIES`). A crash or a hang kills the worker, not
   the server. `.ifczip` is unpacked with the upload size cap.
4. The records are imported in batches of `UNWIND … CREATE` (portable Cypher,
   no APOC). The `IfcModel` ends in state `done` with counts and the
   `IfcProject` guid, or `failed` with an error.
5. A conversion a stopped server left behind starts over: a queued one as soon as the server is back, a
   running one once twice the time limit has passed, since it could be running in another server process.

`opencde seed` converts the sample model the same way when the module is on.

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
attribute, written like every relationship type in the graph in upper case
with underscores at the word boundaries:
`(:IfcRelDefinesByProperties)-[:RELATING_PROPERTY_DEFINITION]->(:IfcPropertySet)-[:HAS_PROPERTIES]->(:IfcPropertySingleValue)`.
Inverse attributes become relationships too, so both directions read
naturally: `(:IfcWall)-[:IS_DEFINED_BY]->(:IfcRelDefinesByProperties)`.
Select values are unwrapped (`IfcLabel('3')` becomes `"3"`).

Left out by default (`OPENCDE_IFC_LPG_INCLUDE_GEOMETRY=false`): representation
items, representations, profiles, placements and styles; they are most of a
model and seldom what a CDE query needs. `IfcOwnerHistory` is kept for the
`IfcProject` only.

## Where the method comes from

The mapping follows the IFC-Graph method of Zhu, Wu and Lei: one node per
instance, the class hierarchy as labels, literal attributes as properties, and
attributes that point at other instances, inverse attributes included, as
relationships named after the attribute. The 2023 prototype used the article's
code. This server's conversion is written anew.

Junxiang Zhu, Peng Wu and Xiang Lei: "IFC-graph for facilitating building
information access and query". *Automation in Construction* 148 (2023), 104778.
[doi:10.1016/j.autcon.2023.104778](https://doi.org/10.1016/j.autcon.2023.104778),
open access under CC BY 4.0.

It differs from the article in these ways:

- Geometry is left out unless asked for. The article converts everything and
  names the size of the graph as a limitation.
- Records are written in batches with `CREATE`, from a separate process. The
  article merges every node and relationship, which checks the graph for
  duplicates and slows down as the graph grows.
- Select values become properties of their node. The article gives them nodes
  of their own with a generated identifier.
- Several models share one database, told apart by `model_id`. The article
  keeps one model per database.
- Relationship types are written in upper case, and `SAME_AS` and the copy of
  the GTIN are added here.

The order of lists is lost here too, as the article notes for its own graph: a
relationship does not say where in a list its target stood.

## Housekeeping

Every upload of an IFC file adds an `IfcModel` with its entities, so a project
that receives new versions accumulates graphs nobody queries. The command line
lists and prunes them; the documents and their files always stay:

```sh
uv run opencde ifc-lpg list --project <project id>
uv run opencde ifc-lpg prune                   # failed models, and finished models superseded by a newer
                                                # finished version of the same document
uv run opencde ifc-lpg prune --project <id> --all   # every model of one project (a test stack, for example)
```

Queued and running models are never pruned. Queries that want one graph per
document should pick the latest finished model themselves, since older
versions stay until pruned:

```cypher
MATCH (:Project {project_id: $project})-[:HAS_MODEL]->(m:IfcModel {state: 'done'})
WITH coalesce(m.document_id, m.bcf_document_guid) AS doc, m
ORDER BY m.version_index DESC, m.done_at DESC
WITH doc, collect(m)[0] AS latest
MATCH (e:IfcProduct {model_id: latest.id})
RETURN latest.file_name AS model, count(e) AS products
```

## Linking BCF components

When a viewpoint is created with components, every component whose `ifc_guid`
matches the `GlobalId` of an element in one of the project's imported models
gets a `SAME_AS` relationship to it. The same linking runs for every existing
component of the project when a model finishes importing, so viewpoints created
before the model was uploaded, or while it was still converting, are linked
too. If the element carries the configured property
(`OPENCDE_IFC_LPG_GTIN_PROPERTY_SET=Reuse`, `OPENCDE_IFC_LPG_GTIN_PROPERTY=GTIN`),
its value is copied to the component as `gtin`. This is the use case of the
2023 research report: an inspection (BCF topic) pointing at building products
identified by GTIN.

```cypher
// Which products does this viewpoint point at, and what are their GTINs?
MATCH (:Viewpoint {guid: $viewpoint})-[:HAS_COMPONENT]->(c:Component)-[:SAME_AS]->(e:IfcProduct)
RETURN c.ifc_guid, e.Name, c.gtin
```

```cypher
// The report's query, directly on the model: GTIN of every wall.
MATCH (w:IfcWall)-[:IS_DEFINED_BY]->(:IfcRelDefinesByProperties)-[:RELATING_PROPERTY_DEFINITION]
      ->(:IfcPropertySet {Name: 'Reuse'})-[:HAS_PROPERTIES]->(p:IfcPropertySingleValue {Name: 'GTIN'})
RETURN w.GlobalId, w.Name, p.NominalValue
```

```cypher
// Every issue that touches a given element.
MATCH (e:IfcEntity {GlobalId: $guid})<-[:SAME_AS]-(:Component)<-[:HAS_COMPONENT]-(v:Viewpoint)<-[:HAS_VIEWPOINT]-(t:Topic)
RETURN DISTINCT t.server_assigned_id, t.title, t.topic_status
```

The BCF `files_information` service shows the `IfcProject` guid of imported
models as `ifc_project`, which lets clients fill in the topic header's files.

## Querying from Dataspatium

[Dataspatium](https://github.com/marwiss/Dataspatium), the browser client
developed together with this server, runs Cypher against this graph through
its Neo4j source over Bolt (WebSocket on the Bolt port) when the operator
exposes the database, as the development overlay does on `127.0.0.1:7697`.
Its Dataregium workspace uses the patterns above (models, classes, components
through `SAME_AS`, the latest finished model per document); the queries live in
Dataspatium's documentation (`docs/grafer.md`), and the live runs are listed
in [acceptance.md](../acceptance.md). A production server does not publish Bolt;
the administration API's graph query (`OPENCDE_GRAPH_QUERY_ENABLED`,
[client-guide.md §7](client-guide.md)) gives administrators read-only Cypher
without the port. The app also draws the graph, in
its card IFC-LPG, through that query or over Bolt.

## Limits and status

- One conversion at a time; large models queue. The example model (248
  entities) imports in about a second; a 200 MB architectural model takes
  minutes.
- The `IfcModel` node carries `state`, `entities`, `relationships`, `skipped`,
  `schema`, `ifc_project_guid`, timestamps and `error`. Administrators can
  inspect it in Neo4j Browser or Memgraph Lab:
  `MATCH (m:IfcModel) RETURN m.file_name, m.state, m.entities, m.error`.
- Deleting a project deletes its models' entities with it.
