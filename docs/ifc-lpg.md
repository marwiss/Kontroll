# IFC-LPG

The optional IFC-LPG module turns an uploaded IFC model into graph data, so
that a BCF viewpoint's components can be joined to the building elements they
point at, and so that questions about the model can be asked in Cypher next to
the issues and documents.

Turn it on with `OPENCDE_IFC_LPG_ENABLED=true` and install the `ifc-lpg`
extra (`uv sync --extra ifc-lpg`). The Docker image includes the extra by
default (`ARG OPENCDE_EXTRAS` in the Dockerfile), which more than doubles its
size (about 680 MB, or 1.1 GB with buildingSMART's rules, against 300 MB); build with `--build-arg OPENCDE_EXTRAS=`
for a slimmer image without IfcOpenShell when the module stays off.

Until November 2026 the module was named IFC-graph. Its settings were named
`OPENCDE_IFCGRAPH_*` and its command `opencde ifcgraph`, and both still work;
the server's log and `opencde doctor` name the old settings it is given.

The conversion, the writing of a file and the checks come from the library
[IFC-LPG](https://github.com/marwiss/IFC-LPG), which Kontroll installs from its
repository at a fixed commit, and whose README describes how a model is kept in
the graph. The server's own process uses the part that needs no IfcOpenShell;
the `ifc-lpg` extra adds the worker processes that do.

## What happens on upload

1. A Documents API upload completes (or a file is uploaded from the selection
   page, or a BCF project document is posted) with a `.ifc` or `.ifczip` name.
2. The server creates an `IfcModel` node (state `queued`) attached to the
   project and starts a conversion in the background, one at a time.
3. A separate worker process (`python -m ifc_lpg.worker`) reads the
   file. It runs with a time limit
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

## Checking uploads against the IFC schema

Every `.ifc` or `.ifczip` file uploaded as a document version is also checked
against the IFC schema, with the validator that checks a written file
([Writing a model back](#writing-a-model-back)): the type and number of
attributes, enumerations, inverse attributes, GlobalIds, and the rules of the
EXPRESS schema. The check runs in the background before the conversion, in a
worker process with the same limits. It never stops an upload: the file is
stored as it came, whatever the check finds. A BCF project document is not
checked, since it has no metadata. `OPENCDE_IFC_LPG_VALIDATE_UPLOADS=false`
turns the check off.

The result is in the version's metadata, which any Documents API client can read:

| Entry | Type | Value |
|---|---|---|
| `ifc_validation_status` | `string` | `pending` until the file is checked, then `passed`, `warnings` when every issue is a warning, `issues` when one or more is an error, or `unknown` when it could not be checked |
| `ifc_validation_issues` | `integer32` | How many issues the file has |
| `ifc_validation_checked_at` | `date-time` | When it was checked |
| `ifc_validation_ruleset` | `string` | What it was checked with, one value per check |
| `ifc_validation_report` | `url` | Where the report is |

The report is an extension of the Documents API. Every member of the project
gets it with the same Bearer token:

```http
GET /documents/1.0/documents/{document_id}/versions/{version_index}/ifc-validation
```

```json
{
  "status": "issues",
  "checked_at": "2026-11-07T10:05:25.123Z",
  "ruleset": "IfcOpenShell 0.9.0.post1: schema and EXPRESS rules; ifc-gherkin-rules 893f827 with IfcOpenShell 0.8.6",
  "issue_count": 2,
  "error_count": 1,
  "truncated": false,
  "checks": [
    {"name": "schema", "state": "done", "ruleset": "IfcOpenShell 0.9.0.post1: schema and EXPRESS rules", "issue_count": 1, "rules_not_run": []},
    {"name": "gherkin", "state": "done", "ruleset": "ifc-gherkin-rules 893f827 with IfcOpenShell 0.8.6", "issue_count": 1, "rules_not_run": [{"rule": "GEM004", "error": "FileNotFoundError"}]}
  ],
  "issues": [
    {
      "kind": "schema",
      "severity": "error",
      "message": "On instance:\n    #373=IfcWallStandardCase('1Xezbq735AdBO_4DerG66G',...)\n...\nRule IfcRoot.UR1:\n    The attribute GlobalId should be unique\n...",
      "step_id": 373,
      "global_id": "1Xezbq735AdBO_4DerG66G"
    },
    {
      "kind": "gherkin",
      "rule": "IFC106",
      "severity": "warning",
      "message": "IFC106 - Resource entities should be referenced by rooted entity. ...",
      "step_id": 99999
    }
  ]
}
```

It lists up to 10,000 issues, each with its instance and, for a rooted entity,
its GlobalId, so that a model view can find the element. `kind` says what found
the issue: `schema`, `entity_rule`, `simpletype_rule` or `global_rule` of the
IFC schema, or `gherkin` for one of buildingSMART's rules, whose code is in
`rule`. `checks` tells the checks apart. A message may quote a line of the file
and is cut at 1,000 characters. The version's page in the browser shows the
first 100 issues and offers the whole report as a file.

Many files break a rule already as they come from their program: 12 of 26
samples do, one from Tekla with 5,711 issues. Checking a sample and its written
copy took 3 to 66 seconds together.

### buildingSMART's ifc-gherkin-rules

When `OPENCDE_IFC_LPG_GHERKIN_ENV` names an environment for them, uploads are
also checked against buildingSMART's `ifc-gherkin-rules`: the normative rules
and the industry practice that buildingSMART's validation service checks beyond
the schema ([ADR 0012](adr/0012-buildingsmarts-rules-run-in-an-environment-of-their-own.md)).
They run after the schema check, in the same kind of worker with the same
limits, and as the rule set's own tests run them: with behave and IfcOpenShell
0.8.6, which the rule set's CI uses. On the rule set's 722 test files this gives
the verdict its tests expect for every one.

The rules get an environment of their own, since one of their helpers does not
work with the IfcOpenShell 0.9 that Kontroll uses.
`python -m ifc_lpg.gherkin_install <folder>` makes it from pinned
downloads, each checked against its SHA-256: the rule set at a fixed commit,
IfcOpenShell's build of 0.8.6 for the platform, and the Python packages with
their hashes. Two small files of IFC-LPG's own replace the rule set's Django
parts, which only write results into the validation service's database.
The published image leaves them out, since they add about 425 MB. The image
tagged `-gherkin`, such as `latest-gherkin` or `3.0.0-gherkin`, has the
environment in `/opt/gherkin` and points `OPENCDE_IFC_LPG_GHERKIN_ENV` at it,
as does an image built with `--build-arg OPENCDE_GHERKIN=1`. With docker
compose, `OPENCDE_IMAGE_TAG` or `OPENCDE_GHERKIN=1` in `.env` makes the choice.

A finding of a rule is an issue of the kind `gherkin`, with the code of the
rule, such as `IFC106`, and the severity `error` or `warning`. Rules of industry
practice only warn, and a file whose issues are all warnings gets the status
`warnings`, since buildingSMART's validation service holds such a file valid. A
rule that raised an exception, rather than finding something, has no verdict and
is listed under `rules_not_run` of its check. If the rules cannot run at all,
their check is `failed` and the schema's check stands alone.

The rules take longer than the schema check: on eight sample models from 5
seconds for the smallest to about 5 minutes for the largest, and between half a
minute and two minutes for most.

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

No nodes by default (`OPENCDE_IFC_LPG_INCLUDE_GEOMETRY=false`): representation
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
uv run opencde ifc-lpg export <model id> model.ifc            # write the file and validate it
uv run opencde ifc-lpg export <model id> model.ifc --verify   # and compare it with the uploaded one
```

The nodes are the ones queries need. What they leave out is written out as STEP
and compressed into text on `StepBlock` nodes that hang off the `IfcModel`: it is
in the graph, but out of Cypher's reach, and it cannot be changed there. It cannot
be properties of the products, since much of it is shared between them. With
`OPENCDE_IFC_LPG_INCLUDE_GEOMETRY=true` every instance becomes a node instead, at
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
`python -m ifc_lpg.equivalence first.ifc second.ifc`.

With `OPENCDE_IFC_LPG_LOSSLESS=false` a model is converted as before 3.0.0: read
with IfcOpenShell, and what is no node left out altogether. Such a model, like one
converted by an earlier version, cannot be written back.

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
Its Kontroll workspace uses the patterns above (models, classes, components
through `SAME_AS`, the latest finished model per document); the queries live in
Dataspatium's documentation (`docs/grafer.md`), and the live runs are listed
in [acceptance.md](acceptance.md). A production server does not publish Bolt;
the administration API's graph query (`OPENCDE_GRAPH_QUERY_ENABLED`,
[client-guide.md §7](client-guide.md)) gives administrators read-only Cypher
without the port. The app also draws the graph, in
its card IFC-LPG, through that query or over Bolt.

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
