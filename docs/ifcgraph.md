# IFC-graph

The optional IFC-graph module turns an uploaded IFC model into graph data, so
that a BCF viewpoint's components can be joined to the building elements they
point at, and so that questions about the model can be asked in Cypher next to
the issues and documents.

Turn it on with `OPENCDE_IFCGRAPH_ENABLED=true` and install the `ifcgraph`
extra (`uv sync --extra ifcgraph`). The Docker image includes the extra by
default (`ARG OPENCDE_EXTRAS` in the Dockerfile), which more than doubles its
size (about 680 MB against 300 MB); build with `--build-arg OPENCDE_EXTRAS=`
for a slimmer image without IfcOpenShell when the module stays off.

## What happens on upload

1. A Documents API upload completes (or a file is uploaded from the selection
   page, or a BCF project document is posted) with a `.ifc` or `.ifczip` name.
2. The server creates an `IfcModel` node (state `queued`) attached to the
   project and starts a conversion in the background, one at a time.
3. A separate worker process (`python -m opencde.ifcgraph.worker`) reads the
   file. It runs with a time limit
   (`OPENCDE_IFCGRAPH_TIMEOUT_SECONDS`, 15 minutes), an address-space limit on
   POSIX (`OPENCDE_IFCGRAPH_MEMORY_MB`, 4 GiB) and an entity cap
   (`OPENCDE_IFCGRAPH_MAX_ENTITIES`). A crash or a hang kills the worker, not
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

No nodes by default (`OPENCDE_IFCGRAPH_INCLUDE_GEOMETRY=false`): representation
items, representations, profiles, placements and styles; they are most of a
model and seldom what a CDE query needs, and they are kept as text in the graph,
as under Writing a model back. `IfcOwnerHistory` is a node for the `IfcProject`
only.

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

- Geometry is no nodes unless asked for. The article converts everything and
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

The article notes that its graph loses the order of lists, since a relationship
does not say where in a list its target stood. Here `position` says that.

## Writing a model back

The graph holds all of a model, and the file can be written back from it: the
same instances with the same ids, and the same values in the same order, so the
same geographic information too.

```sh
uv run opencde ifcgraph export <model id> model.ifc            # write the file and validate it
uv run opencde ifcgraph export <model id> model.ifc --verify   # and compare it with the uploaded one
```

The nodes are the ones queries need. What they leave out is written out as STEP
and compressed into text on `StepBlock` nodes that hang off the `IfcModel`: it is
in the graph, but out of Cypher's reach, and it cannot be changed there. It cannot
be properties of the products, since much of it is shared between them. With
`OPENCDE_IFCGRAPH_INCLUDE_GEOMETRY=true` every instance becomes a node instead, at
several times the size and the import time; queries took about as long in
[the measurements](adr/0010-a-lossless-graph-reads-and-writes-step-itself.md).

| In the file | In the graph |
|---|---|
| A reference | A relationship with `position`, `[row, column]` in a list of lists; inverse relationships have none |
| A reference to an instance in a block | Its id, as in `Representation__step: 1234` |
| A typed value, `IFCLABEL('3')` | `NominalValue: "3"`, and `NominalValue__type: "IFCLABEL"` beside it |
| A list of lists of numbers | JSON text |
| What has no plain form, such as a list of typed values | Tagged JSON, with `$json` as its type |
| The header | `ifc_header` on the `IfcModel` |
| An instance in a block | Text in a `StepBlock` |

The file is written from what the graph holds, not copied, so a property or a
relationship changed in the graph shows up in it. A graph database has no schema
to hold a change to, so the file is validated against the IFC standard with
IfcOpenShell's validator: the type and number of attributes, enumerations, inverse
attributes, GlobalIds, and the rules of the EXPRESS schema. Files in use often
break a rule already, so what counts is an issue the uploaded file does not have.
The command then lists it and ends with an error. `--no-validate` leaves this out.
An export also stops if a block has gone missing.

Project members get files through the Documents API, and there is no other way
out of the server. A written file that is to replace a model is uploaded as a new
version of its document, which also converts it.

This form is not read with IfcOpenShell, which takes only the schema here.
IfcOpenShell changes some values on reading (`.NULLENUM.` becomes `$`, and `($,$)`
becomes `()`), and files from Tekla and Archicad have them. So the worker reads the
file itself, and refuses what it cannot read. [ADR 0010](adr/0010-a-lossless-graph-reads-and-writes-step-itself.md) says why, and
[ADR 0011](adr/0011-a-file-written-from-the-graph-is-validated.md) how a file is validated.

`--verify` asks whether the two files hold the same model, by the definition in
[ADR 0009](adr/0009-what-makes-two-ifc-files-the-same-model.md): one to one, value by value and with no tolerance, georeference
named in the report. With `--geometry` it also builds every product's mesh, and
compares them bit for bit. Any two files can be compared with
`python -m opencde.ifcgraph.equivalence first.ifc second.ifc`.

With `OPENCDE_IFCGRAPH_LOSSLESS=false` a model is converted as before 3.0.0: read
with IfcOpenShell, and what is no node left out altogether. Such a model, like one
converted by an earlier version, cannot be written back.

## Housekeeping

Every upload of an IFC file adds an `IfcModel` with its entities, so a project
that receives new versions accumulates graphs nobody queries. The command line
lists and prunes them; the documents and their files always stay:

```sh
uv run opencde ifcgraph list --project <project id>
uv run opencde ifcgraph prune                   # failed models, and finished models superseded by a newer
                                                # finished version of the same document
uv run opencde ifcgraph prune --project <id> --all   # every model of one project (a test stack, for example)
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
(`OPENCDE_IFCGRAPH_GTIN_PROPERTY_SET=Reuse`, `OPENCDE_IFCGRAPH_GTIN_PROPERTY=GTIN`),
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
Its Kontroll workspace uses the patterns above (models, classes, components
through `SAME_AS`, the latest finished model per document); the queries live in
Dataspatium's documentation (`docs/grafer.md`), and the live runs are listed
in [acceptance.md](acceptance.md). A production server does not publish Bolt;
the administration API's graph query (`OPENCDE_GRAPH_QUERY_ENABLED`,
[client-guide.md §7](client-guide.md)) gives administrators read-only Cypher
without the port. The app also draws the graph, in
its card IFC graph, through that query or over Bolt.

## Limits and status

- One conversion at a time; large models queue. The example model (248
  entities) imports in about a second; a 200 MB architectural model takes
  minutes.
- The `IfcModel` node carries `state`, `entities`, `relationships`, `skipped`,
  `lossless`, `schema`, `ifc_project_guid`, timestamps and `error`. Administrators can
  inspect it in Neo4j Browser or Memgraph Lab:
  `MATCH (m:IfcModel) RETURN m.file_name, m.state, m.entities, m.error`.
- Deleting a project deletes its models' entities with it.
- A model comes back identical from both databases at up to 224,496 instances and 19 MB, in
  every form measured. Nothing larger has been tried.
