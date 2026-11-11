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
[IFC-LPG](https://github.com/marwiss/IFC-LPG), which Dataregium installs from its
repository at a fixed commit, and whose README describes how a model is kept in
the graph. The server's own process uses the part that needs no IfcOpenShell;
the `ifc-lpg` extra adds the worker processes that do.

## What happens on upload

1. A Documents API upload completes (or a file is uploaded from the selection
   page, or a BCF project document is posted) with a `.ifc` or `.ifczip` name.
2. The server creates a `Conversion` record (state `queued`) under the
   project and starts a conversion in the background, one at a time.
3. A separate worker process (`python -m ifc_lpg.worker`) reads the
   file. It runs with a time limit
   (`OPENCDE_IFC_LPG_TIMEOUT_SECONDS`, 15 minutes), an address-space limit on
   POSIX (`OPENCDE_IFC_LPG_MEMORY_MB`, 4 GiB) and an entity cap
   (`OPENCDE_IFC_LPG_MAX_ENTITIES`). A crash or a hang kills the worker, not
   the server. `.ifczip` is unpacked with the upload size cap.
4. The records are imported in batches of `UNWIND … CREATE` (portable Cypher,
   no APOC). The `Conversion` ends in state `done` with counts and the
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
worker process with the same limits. By default it never stops an upload: the file
is stored as it came, whatever the check finds; a project can choose
otherwise ([below](#refusing-files-with-errors-and-checking-a-file-first)). A BCF project document is not
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
    {"name": "schema", "state": "done", "ruleset": "IfcOpenShell 0.9.0.post1: schema and EXPRESS rules", "issue_count": 1, "rules_not_run": [], "documents": [], "specifications": []},
    {"name": "gherkin", "state": "done", "ruleset": "ifc-gherkin-rules 893f827 with IfcOpenShell 0.8.6", "issue_count": 1, "rules_not_run": [{"rule": "GEM004", "error": "FileNotFoundError"}], "documents": [], "specifications": []}
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
the schema (ADR 0012).
They run after the schema check, in the same kind of worker with the same
limits, and as the rule set's own tests run them: with behave and IfcOpenShell
0.8.6, which the rule set's CI uses. On the rule set's 722 test files this gives
the verdict its tests expect for every one.

The rules get an environment of their own, since one of their helpers does not
work with the IfcOpenShell 0.9 that Dataregium uses.
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

### Information Delivery Specifications (IDS)

An upload is also checked against every IDS document of its project: a
document whose latest version has a name ending in `.ids`, at most 50 of them
(ADR 0015).
IFC-LPG's check reads each IDS safely and gives it to IfcOpenShell's IfcTester,
the checker Dataspatium runs in the browser, so that the two give the same
verdict. It runs after the other checks, in the same kind of worker with the
same limits. A new version of an IDS document has the latest version of every IFC document
in the project checked again, at most 500, so that its report follows the
requirements as they are now; older versions keep the report they had.

Every requirement an element fails is an issue of the kind `ids`, with the
severity `error`, the specification's identifier or name in `rule`, and the IDS
document in `document_id`. So is a required specification that applies to
nothing in the file, and an element that a prohibited specification applies to.
The report's check `ids` lists the documents it used, each with its version,
and every specification with its usage, its verdict (`passed`, `failed` or
`not applicable`), how many elements it applies to and how many issues it gave.
An IDS document that cannot be read, such as one with a DTD, is listed under
`rules_not_run` with the reason, and the others are checked all the same. The
version's page shows the specifications in a table of their own.

### buildingSMART Data Dictionary (bSDD)

With `OPENCDE_BSDD_ENABLED=true`, an upload is also checked against buildingSMART's Data Dictionary, after the IDS
check. A worker reads the file's references to it: every `IfcClassificationReference` whose `Location` is a bSDD URI,
such as `https://identifier.buildingsmart.org/uri/molio/cciconstruction/1.0/class/L-BD`, or whose `Identification`
(`ItemReference` in IFC2X3) is a code in the dictionary whose URI its `Location` or its classification holds, with the
objects it is on; and the properties of every set named `Pset_…` or `Qto_…`. The server then asks bSDD's API at
`OPENCDE_BSDD_API_URL` (`https://api.bsdd.buildingsmart.org`) about each URI, with a time limit on each question
(`OPENCDE_BSDD_TIMEOUT_SECONDS`, 10 seconds) and two retries when bSDD answers 429 or 5xx, and keeps each answer in
memory for a day (`OPENCDE_BSDD_CACHE_SECONDS`, 86400; 0 asks every time). Nothing the file names is fetched: a URI
goes to bSDD's API as a parameter, and one on another host than `identifier.buildingsmart.org` is reported instead.
The check is off by default, since it sends the file's URIs and the names of its sets to bSDD; in production its
address must be https.

Everything it finds is a warning of the kind `bsdd`, with the classification reference or the set in `step_id`, the
GlobalId of one of the objects it is on in `global_id`, and that object's class in the message:

- a classification reference whose class or property bSDD does not know, with the dictionary in `rule` and the
  attribute that names it in `attribute`; a model may use a dictionary that bSDD has not published;
- in a file of IFC 4.3, a set that bSDD's IFC dictionary (`buildingsmart/ifc/4.3`) does not have, or a property that
  it does not list in that set, with the set and the property in `attribute`, as in `Pset_WallCommon.Colour`.

bSDD publishes that one IFC dictionary, so the sets of an IFC4 or IFC2X3 file, whose schemas define them otherwise,
are not checked; and `Reference`, which IFC 4.3 gives nearly every set and bSDD leaves out of all of them, is not
reported. The check's `ruleset` names bSDD's host and the dictionaries the file was checked against. It reads at most
1,000 references and 500 sets, and a warning says when a file has more. When bSDD cannot be reached, or does not
answer as its API does, the check is `failed` with the reason in its `error`, and the other checks stand: bSDD out of
reach is never an error of the model. The precheck and the trial of a change set make the check too, and the
capabilities document says whether it is on, as `bsdd` in `ifc_validation`.

### What the converted model shows

Once the model is converted, the report gets a check `graph` of its own, with two kinds of issues. An instance that
nothing with a GlobalId reaches, forward or backward, is a warning of the kind `reachability`, with its STEP id in
`step_id` and its class in the message: only that number names it, as with an unused placement, so a change set can
address it by its STEP id alone. A product whose shape the geometry pass could not build is an issue of the kind
`geometry`, with its GlobalId. Neither refuses the file: they come after the upload, and a warning leaves the status at
`warnings`. Until the model is converted, the report has no check `graph`.
An instance kept with the geometry in a STEP block, such as a loose point, is not
listed: the check sees the nodes only.

### Refusing files with errors, and checking a file first

An administrator can tick *Refuse uploads with validation errors* on the
project's page (`block_on_validation_errors` in the administration API). The
checks then run before the file becomes a version, in the upload's completion
and on the upload page, and a file with one or more errors is refused with
`422 ifc_validation_failed`; warnings pass. The refused file stays for a day as
a precheck, and `report` in the error names where its report is. A file that
could not be checked at all goes through, as `unknown`, so that a broken
validator never stops the work. A file that passes is checked once: the result
is the version's, as if the check had run afterwards.

Any editor or manager can also check a file without making it a version, with
the same bearer token and whatever the project's setting:

```http
POST /documents/1.0/projects/{project_id}/ifc-precheck
Content-Disposition: attachment; filename="model.ifc"
```

The body is the file. The answer is `202` with the report's `url`, `pending`
until the checks are done; then it has the form of a version's report, with the
file's name and when the precheck expires. Every member reads it, for a day.
The capabilities document announces the precheck as `ifc_precheck`.

## The graph

Every entity becomes an `Entity` node carrying its class and all its
supertypes as labels, for example `Entity:IfcWallStandardCase:IfcWall:
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
- Relationship types are written in upper case, and the copy of the GTIN onto
  BCF components is added here.

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
and compressed into text on `StepBlock` nodes that hang off the `Model`: it is
in the graph, but out of Cypher's reach, and it cannot be changed there. It cannot
be properties of the products, since much of it is shared between them. With
`OPENCDE_IFC_LPG_INCLUDE_GEOMETRY=true` every instance becomes a node instead, at
several times the size and the import time; queries took about as long in
the measurements.
A styled item (`IfcStyledItem`) is always a node, so that every style can be changed, and `form_version` on the `Model` says which shape the graph has (2 since IFC-LPG's release of 2026-11-10).

| In the file | In the graph |
|---|---|
| A reference | A relationship with `position`, `[row, column]` in a list of lists; inverse relationships have none |
| A reference to an instance in a block | Its id, as in `Representation__step: 1234` |
| A typed value, `IFCLABEL('3')` | `NominalValue: "3"`, and `NominalValue__type: "IFCLABEL"` beside it |
| A list of lists of numbers | JSON text |
| What has no plain form, such as a list of typed values | Tagged JSON, with `$json` as its type |
| The header | `ifc_header` on the `Model` |
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
file itself, and refuses what it cannot read. ADR 0010 says why, and
ADR 0011 how a file is validated.

`--verify` asks whether the two files hold the same model, by the definition in
ADR 0009: one to one, value by value and with no tolerance, georeference
named in the report. With `--geometry` it also builds every product's mesh, and
compares them bit for bit. Any two files can be compared with
`python -m ifc_lpg.equivalence first.ifc second.ifc`.

With `OPENCDE_IFC_LPG_LOSSLESS=false` a model is converted as before 3.0.0: read
with IfcOpenShell, and what is no node left out altogether. Such a model, like one
converted by an earlier version, cannot be written back.

## Housekeeping

Every upload of an IFC file adds a `Conversion` and a model with its entities, so a project
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
MATCH (:Project {project_id: $project})-[:HAS_CONVERSION]->(m:Conversion {state: 'done'})
WITH coalesce(m.document_id, m.bcf_document_guid) AS doc, m
ORDER BY m.version_index DESC, m.done_at DESC
WITH doc, collect(m)[0] AS latest
MATCH (e:IfcProduct {model_id: latest.id})
RETURN latest.file_name AS model, count(e) AS products
```

## Linking BCF components

When a viewpoint is created with components, every component whose `ifc_guid`
matches the `GlobalId` of an element in one of the project's imported models
gets the value of the configured property
(`OPENCDE_IFC_LPG_GTIN_PROPERTY_SET=Reuse`, `OPENCDE_IFC_LPG_GTIN_PROPERTY=GTIN`)
as `gtin`, when the element has one: the server looks the GlobalIds up in the
model through IFC-LPG's `property_values` and keeps the value on the component,
and makes no relationship into the model; the element is found by its
`GlobalId`. The same lookup runs for every existing component of the project
when a model finishes importing, so viewpoints created before the model was
uploaded, or while it was still converting, get their GTINs too. This is the
use case of the 2023 research report: an inspection (BCF topic) pointing at
building products identified by GTIN.

```cypher
// Which products does this viewpoint point at, and what are their GTINs?
MATCH (:Viewpoint {guid: $viewpoint})-[:HAS_COMPONENT]->(c:Component)
MATCH (e:IfcProduct {GlobalId: c.ifc_guid})
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
MATCH (:Component {ifc_guid: $guid})<-[:HAS_COMPONENT]-(v:Viewpoint)<-[:HAS_VIEWPOINT]-(t:Topic)
RETURN DISTINCT t.server_assigned_id, t.title, t.topic_status
```

The BCF `files_information` service shows the `IfcProject` guid of imported
models as `ifc_project`, which lets clients fill in the topic header's files.

## Named queries

A member of a project asks a version's model questions by name, with the same
bearer token as the Documents API; free Cypher stays with administrators
(ADR 0016).
The queries are IFC-LPG's catalogue (`ifc_lpg.queries`), so one added to the
library appears here.
`GET /documents/1.0/documents/{id}/versions/{index}/ifc-queries` lists the
queries with their parameters and columns, and says in `model_state` how far
the model's conversion has come. `GET …/ifc-queries/{name}` asks one, with its
parameters in the query string, and answers with the columns and the rows, each
row a list in the order of the columns:

```http
GET /documents/1.0/documents/{id}/versions/1/ifc-queries/property?pset=Reuse&property=GTIN
```

```json
{"name": "property", "columns": ["global_id", "class", "name", "value", "type"],
 "rows": [["1Xezbq735AdBO_4DerG66G", "IfcWallStandardCase", "YVT-A", "3", "IFCLABEL"]],
 "truncated": false}
```

| Query | Parameters | What it answers |
|---|---|---|
| `element-classes` | | How many elements the model has of each class |
| `elements` | `class` | The elements of a class, with the spatial structure that contains each |
| `storeys` | | The storeys, their elevation, and how many elements and spaces each holds |
| `spaces` | | The spaces, their storey, and their net and gross floor areas |
| `areas` | | The net floor area of each storey's spaces, added up |
| `materials` | `class` | The materials of each element: its own, or those of its layers, list or constituents |
| `property` | `pset`, `property`, `class` | The value of one property on every object that has it, with its IFC type |
| `entity` | `global_id` | One rooted entity: its class, every literal attribute, and what it refers to and is referred to by, each by IFC attribute, STEP id and class |
| `site` | | Where the building stands: the site's reference latitude, longitude and elevation, and the map conversion with its coordinate reference system (eastings, northings, height, rotation and scale) where the model has one |
| `changed-since` | `since` | What changed in the document since a version: one row per change of each version's change set up to this one, or one row with `whole_file` for a version uploaded as a whole file; answered from the versions, so it needs no graph |

`class` names an IFC class, such as `IfcWall`, and takes its subclasses with
it: required for `elements`, optional for the others. An answer holds at most
10,000 rows, and `truncated` says when there were more; a query stops after 10
seconds. Every query starts at the member and reaches the model through the
project, only reads, and takes its values as parameters. A version without a
model, or one the user may not see, answers 404, and one whose model is still
being converted answers 409. The capabilities document announces the queries in
`ifc_queries`.

## Change sets

A proposed change to a model travels as the `bim_snippet` of a BCF 3.0 topic
(ADR 0021): `snippet_type` is `DataregiumIfcChangeSet`, `reference_schema` is
`GET /documents/1.0/ifc-changes/schema`, which anyone may read, and the snippet
itself is uploaded with `PUT …/topics/{guid}/snippet`, where the server holds
it to the schema and answers `400` with what is wrong. A new project allows the
snippet type; an administrator adds it to an older project's values. A change
set names its base version, who proposed it, with the AI model and the tool
call where an AI did, and its changes, each on one attribute of one instance.
The instance is named by a GlobalId and a path from the rooted entity in
IFC's attribute names with indexes, and by its STEP id only where no GlobalId
reaches it. `set` gives the attribute
a value, `add` and `remove` change one member of an aggregate, and `copy` asks
for a copy of an instance that several share, which otherwise changes for all
of them. A value is a scalar, an instance (`{"step_id": 120}`, or a GlobalId
with a path), a typed value (`{"type": "IfcLengthMeasure", "value": 3.2}`), an
enumeration (`{"enum": "NOTDEFINED"}`) or a list of them. The capabilities
document announces the form as `ifc_changes`. What the changes do to the model
is checked when the proposal is tried, the next step; today the server keeps
the form.

```json
{
  "schema": "https://cde.example/documents/1.0/ifc-changes/schema",
  "base": {"document_id": "…", "version_index": 3},
  "provenance": {"user": "anna", "ai_model": "claude-opus-5-5", "tool_call": "rename_element"},
  "changes": [
    {"guid": "1Xezbq735AdBO_4DerG66G", "attribute": "Name", "op": "set", "old": "Wall 1", "new": "Wall 1b"},
    {"guid": "1Xezbq735AdBO_4DerG66G", "path": "IsDefinedBy[0].RelatingPropertyDefinition.HasProperties[2]",
     "attribute": "NominalValue", "op": "set", "new": {"type": "IfcLengthMeasure", "value": 3.2}}
  ]
}
```

`delete` removes an instance named by its STEP id that nothing refers to, such as one that no GlobalId reaches;
an instance something still refers to is skipped and named in the trial. The server proposes such a change set
itself with `POST /documents/1.0/projects/{id}/ifc-unreachable` and the version as `document_id` and
`version_index`: it makes a topic whose snippet deletes every instance that the version's check `graph` finds out of
reach, and the change set is tried and approved like any other, so the version it came from keeps the instances. The
answer names the topic, how many instances it deletes and where the trial is; `404` when the version has no
converted model, and `409` when nothing in it is out of reach. The capabilities document lists the operations
in `ifc_changes.ops` and the address as `ifc_changes.unreachable_url`.

A change set made with Dataspatium's write tools also carries their operations as `ops`, with `ops_form`
`dataspatium-tools/1`, so that new elements, deletions and relationships reach the proposal. Each operation names
its tool as `tool` and holds the tool's arguments beside it, lengths in metres: `create_storeys_and_grid`,
`create_wall`, `create_slab`, `create_roof`, `create_opening`, `set_properties`, `set_classification`, `assign`,
`transform_elements`, `delete_elements` and `set_site`. The server runs them with a copy of the app's own code
(`opencde/ifcgraph/ops.py`), so that the same operations give the same model in the app and on the server, in the
file's unit, with the proposer and the server in the owner histories that IfcOpenShell makes. What the wall, slab,
roof and opening operations create is named `new-1`, `new-2` … in their order. An operation names an element by its
GlobalId, by its STEP id only where no GlobalId reaches it, or by such a ref, and a storey by its name.
`changes` may then be empty: beside the operations they describe what the operations do to
existing instances, as the app found it, for the merge, and a change the operations made already counts as applied.
The capabilities document announces the form as `ifc_changes.ops_form` and the tools as `ifc_changes.ops_tools`.

```json
{
  "schema": "https://cde.example/documents/1.0/ifc-changes/schema",
  "base": {"document_id": "…", "version_index": 3},
  "provenance": {"user": "anna", "ai_model": "claude-opus-5-5", "tool_call": "create_wall,create_opening"},
  "ops_form": "dataspatium-tools/1",
  "ops": [
    {"tool": "create_wall", "storey": "Level 1", "start": [0, 0], "end": [6, 0], "thickness": 0.2, "height": 3},
    {"tool": "create_opening", "wall_id": "new-1", "offset": 1, "width": 0.9, "height": 2.1, "fill": "door"}
  ],
  "changes": []
}
```

The trial applies the operations first, then the changes, and counts both in `change_count`. An operation that
cannot be applied is a finding of kind `op` with its index (`op`) and `tool`, in the words of the app's code, which
may quote its arguments and the file; the operations after it and the changes are not applied, as in the app. The
trial also gives `created`, the GlobalId of each created element by its ref, so that the client can map its own,
and `notes`, what an operation could not do in the file's schema, such as the map conversion in IFC2X3.

When the IFC-LPG module is on, the server tries every change set as it is
uploaded: a worker applies the changes to the base version's file, the result
goes through the checks an upload gets (the IFC schema, buildingSMART's rules
and the project's IDS documents), and the trial is `clean` when every change
applied and no finding is new compared with the base version's report, else
`issues`. `GET /bcf/3.0/projects/{id}/topics/{guid}/ifc-proposal` gives the
state, how many changes applied and the new findings, each as in a version's
report; a change that could not be applied is a finding of kind `proposal`
that says why, without quoting the file. A new snippet replaces the trial, and
the trial goes with the topic. `ifc_changes` in the capabilities document says
whether change sets are tried (`tried`) and where the trial is (`proposal_url`).

`GET /documents/1.0/documents/{id}/ifc-proposals` lists the change sets tried
against a document, for a member of its project, newest first: per row the
topic's guid, title and the first 200 characters of its description, the
trial's state, the base version, how many changes the set holds, who proposed
it, when the trial ended, the version it became where it was approved, and
the addresses of the trial (`proposal_url`) and of its approval
(`approve_url`). A proposal names its base from the moment it is queued, so
the list holds it before the trial and when the trial failed. `$top` and
`$skip` page through the list as in the BCF lists; a list the server cut
carries `X-Total-Count` and `Link: <…>; rel="next"`. `404` for a document the
member may not see, and when the IFC-LPG module is off. The capabilities
document gives the address as `ifc_changes.ifc_proposals_url`.

A `manager` approves a clean trial with `POST …/ifc-proposal/approve`: the
applied file becomes the next version of the base document, with
`base_version_index`, `change_set_id` (the topic's guid), `proposed_by` and
`approved_by` in its metadata, and the AI model and tool call where an AI
proposed it; the answer is the new version as the Documents API gives it, and
it is converted and checked as an upload is. The topic gets a comment with the
version's address, a viewpoint that selects the changed elements, and the
status `Closed` where the project has that value.
`412 version_conflict` says the document has moved on since the base; `409`
that the trial is not clean, or was approved already. An AI only proposes:
approval is a person's.
Where the project has teams, the trial lists in `teams` those whose part of the
model the change set touches: what the specifications of a team's IDS document
apply to, in the base file or the changed one. A change set that touches the part
of one team is approved by that team's responsible alone, not by a `manager`; one
that touches the parts of several teams, or of none, by a `manager`, and so is one
whose parts could not be found (`teams_error`).

When the document has moved on since the base, the server merges: the
changes of the versions in between, each approved from a change set, are
compared attribute by attribute with the proposal's. When none collide, the
change set is tried again on the latest version, at once, and approved on it,
so that the new version's base is the latest. When some collide, or a version
in between was uploaded as a whole file, the answer is `412 version_conflict`
with the colliding attributes in `conflicts` (`#123.Name`, or the GlobalId, the
path and the attribute; `*` for a whole file), for the client to merge three
ways and send again.

The instances are compared, not the keys the clients wrote: each change is
resolved in the version it was made on and named by its canonical path
(IFC-LPG's `ifc_lpg.paths`), so that two changes that reach one shared
instance from different GlobalIds collide all the same, and `conflicts` names
the instance by that path. Beside it, `conflict_details` gives per conflict
`key`, the proposal's own `guid`, `path` or `step_id`, `attribute` and `op`,
what the base held (`base`), what the latest version holds (`theirs`), what
the proposal sets (`ours`), all in the change set's value form, and the
version in between that changed it (`version_index`); a value that could not
be read is `null`. The client lets a person choose per conflict, sends a new
snippet on the latest version and approves again. A client that cannot cut one
change out of its operations sends them again with the keys it gives up in
`keep_theirs`, as `conflicts` named them: the server then tries the change set
on the document's latest version and gives each of those attributes back the
latest version's value after the operations and the changes.

A version built on another is a node with its parent: `parent_version_index`
and a link to the parent version, on a version approved from a change set and
on an upload that named `base_version_index`. A version approved from a change
set also carries `approved_by`, `change_set_id` (the topic's guid) and the
changes themselves, which `GET /documents/1.0/documents/{id}/versions/{index}/ifc-changes`
gives in the form of the schema, with its base and who proposed and approved
it; a version uploaded as a whole file answers `404` there. Every version is
still a whole file, downloaded as before; `opencde ifc-lpg prune` removes the
graphs of older versions, since the head version and the chain of change sets
tell what changed.

## Comparing two versions

A member compares two IFC versions element by element, with the same bearer
token as the Documents API: a version with another of the same document, or
with `?other_document_id=` a version of another document of the project. The
worker pairs the rooted entities by GlobalId and answers with `added` (only
the other has them), `removed` (only this one has them) and `changed` (in
both, with attributes that differ), each element named by GlobalId, class,
name and storey, and for a changed one the paths that differ with the old and
the new value: a direct attribute by its name, a property as `Pset.Property`,
`ObjectPlacement` (the 4 by 4 matrix), `Representation` (a fingerprint of the
shape), `Container` (the storey) and `Type`. Relationships and property sets
are folded into the elements they belong to, and each list keeps at most
10,000 elements. The difference is computed on request and never stored; a
large model takes a while. The version's page offers the same comparison as
lists, and the capabilities document announces it as `ifc_diff`.

```http
GET /documents/1.0/documents/{document_id}/versions/{version_index}/ifc-diff/{other_index}
```

## Clash check

A member compares two IFC document versions of a project for clashes, with the
same bearer token as the Documents API: `POST /documents/1.0/projects/{project_id}/ifc-clash`
with the two versions, the mode (`intersection`: elements that go into each other
deeper than `tolerance`; `clearance`: elements closer to each other than
`clearance`, both in metres) and, if wanted, the IFC classes of each side. The
check runs in a worker process behind the conversion queue; the answer's `url`
gives the report, `done` or `failed` after a while. Each clash names both
elements (document, version, STEP id, GlobalId, class, name, storey), its kind,
the depth or distance and the point where it was measured, in the form
Dataspatium's own clash core writes, so the app shows the server's result as it
shows its own. `POST …/ifc-clash/{id}/topics` turns chosen clashes into BCF
topics with a viewpoint each, on request only. The capabilities document
announces the check as `ifc_clash` once the operator has set
`OPENCDE_IFC_LPG_CLASH_ENABLED=true`; a report keeps at most
`OPENCDE_IFC_LPG_CLASH_MAX_CLASHES` clashes.

```http
POST /documents/1.0/projects/{project_id}/ifc-clash
{"a": {"document_id": "…", "version_index": 1, "types": ["IfcWall"]},
 "b": {"document_id": "…", "version_index": 2},
 "mode": "intersection", "tolerance": 0.001}
```

## A building into another model

A building of one model comes into another project's model as the next version of
its document; the two models do not change. Model A is a version of this project,
model B a version of any project the caller is a member of, and both must be
converted, with the same schema and length unit.
`POST /documents/1.0/projects/{project_id}/ifc-merge/report` tells any member of
both projects what would happen: how many objects and instances come along, the
objects with a GlobalId that both have (`collisions`, with `same` and the `choice`
that holds), the relationships left out because they point outside the building
alone, and the contexts and placements of A that are used. Where the content of such
an object differs, a choice is made for it: `a` keeps A's, `b` puts B's in its
place, and `new` keeps both, B's with a new GlobalId; `default` gives one choice for
all of them.
A unit of a kind A has none of, such as an area unit, comes along into A's units
and is listed in `units_added`; a unit of a kind both have must be the same.

A `manager` of the project starts the merge with `POST …/ifc-merge` and the same
body. It runs as a job in the conversion queue, and the answer's `url` gives its
state: `conflict` with the objects that still lack a choice, `failed` with the
reason, or `done` with `version_index`, the new version of A's document. The merged
model is first checked against A and B and may have no issue that they lack; then it
is written out as the next version, with A's version as its parent and
`merged_from_document`, `merged_from_version` and `merged_building` in its metadata,
and converted and checked as an upload is. A's version must be the document's
latest (412 `version_conflict` otherwise). The capabilities document announces it as
`ifc_merge`.

Where B's schema or length unit is not A's, the report says so (422), and an
`editor` or a `manager` first prepares B with `POST …/ifc-merge/prepare` and `base`
and `other`: a job that makes a copy of B migrated to A's schema and with its lengths
in A's unit. When it is `done`, its `merge_id` given as `other.prepared` makes the
copy stand in for B in the report and the merge until `expires_at`, a day later;
then the server takes it out. Another unit that differs is not converted, and the
job fails with it.
What A's schema has no equivalent of, such as IFC2X3's IfcWindowStyle in
IFC4X3 or the owner histories IFC2X3 requires, ends the job in `conflict`:
`report.problems` lists each problem with its `key`, what it affects and its
`options` (`type`, `proxy`, `leave_out`, `polyline`, `owner`, `virtual`, `dated`,
`assignment`, `context`), and a new `POST …/ifc-merge/prepare` with `resolutions`, the chosen
option per key, makes the copy. The copy is then checked against B: one with an
issue B did not have is not made, and the job is `failed` with them in `report.new`.

```http
POST /documents/1.0/projects/{project_id}/ifc-merge
{"base": {"document_id": "…", "version_index": 3},
 "other": {"project_id": "…", "document_id": "…", "version_index": 1},
 "building": "3AMeTOOFsdVLZuNV0$27s5", "choices": {"1Xezbq735AdBO_4DerG66G": "b"}}
```

## The working copy

Beside the archive, the server can keep a working copy: a second graph,
Memgraph in memory, where the head model of every document is imported too
(ADR 0024). The archive keeps every version and stays the truth; the working
copy holds one model per document, the latest converted, and answers the named
queries for it, so that a large model is read from memory. `OPENCDE_WORKCOPY_GRAPH_URI`
names it (`OPENCDE_WORKCOPY_GRAPH_DIALECT`, `_USER`, `_PASSWORD` and `_DATABASE`
beside it); the overlay `docker/compose.workcopy.yaml` adds the Memgraph to
any stack, unpublished. A conversion imports the same records into both graphs
in IFC-LPG's dialect-neutral form, replaces the document's model from before
in the working copy, and never fails on the working copy's account: a copy
that could not be made is marked `failed` there and the archive is untouched. A
model the archive no longer has leaves the working copy at the next cleanup
round. `GET …/ifc-queries` says in `workcopy` whether the version's model is
there, `/readyz` reports the working copy's state without depending on it, and
the capabilities document says in `ifcgraph.workcopy` whether one is
configured.

```sh
# .env: COMPOSE_FILE=docker/compose.yaml:docker/compose.local.yaml:docker/compose.workcopy.yaml
docker compose up -d
```

## Where the products are, and the geometry

After a conversion the server runs IFC-LPG's geometry worker once over the
file (`python -m ifc_lpg.spatial`; `OPENCDE_IFC_LPG_SPATIAL`, on by default
with the extra): IfcOpenShell builds every product's shape, and the worker
writes a box per product in project coordinates and the meshes, each shared
mesh once. The boxes go into the graph as the points `bbox_min`, `bbox_max`
and `bbox_centre` on the product's `Entity`, with a point index on
`bbox_centre` in the archive and in the working copy, so that a query finds
what is near a point or inside a volume; the `Model` carries `spatial_at`,
`spatial_products` and `spatial_failed`. The records are kept in the storage,
and `GET …/ifc-geometry` builds a binary glTF from them the first time it is
asked for: every shared mesh once, a node per product that instances it with
the product's matrix, named by its GlobalId with its class, STEP id and storey
in `extras`, under a node per storey, and a root that turns the model from
IFC's Z up to glTF's Y up. `lod=box` gives the boxes instead, one cube that
every product instances, a few bytes each; `classes` (IFC classes,
comma-separated) and `storey` (a GlobalId) pick the products. The file is
kept, and comes with an `ETag` of the model and the filters, so
`If-None-Match` answers `304`. The geometry pass never fails a conversion:
when it fails, the model notes `spatial_error` and the route answers `404`;
while the version is still being converted, `409`. The capabilities document
announces it as `ifc_geometry`.

```http
GET /documents/1.0/documents/{document_id}/versions/{version_index}/ifc-geometry?lod=full&classes=IfcWall,IfcSlab
```

```cypher
// The products within two metres of a wall, in the same model
MATCH (w:Entity:IfcWall {GlobalId: $guid})
MATCH (e:Entity {model_id: w.model_id}) WHERE e.bbox_centre IS NOT NULL AND e <> w
  AND point.distance(e.bbox_centre, w.bbox_centre) < 2.0
RETURN e.GlobalId, e.ifc_class, point.distance(e.bbox_centre, w.bbox_centre) AS distance ORDER BY distance
```

## Querying from Dataspatium

[Dataspatium](https://github.com/marwiss/Dataspatium), the browser client
developed together with this server, runs Cypher against this graph through
its Neo4j source over Bolt (WebSocket on the Bolt port) when the operator
exposes the database, as the development overlay does on `127.0.0.1:7697`.
Its Dataregium workspace uses the patterns above (models, classes, components
by `GlobalId`, the latest finished model per document); the queries live in
Dataspatium's documentation (`docs/grafer.md`). A production server does not publish Bolt;
the administration API's graph query (`OPENCDE_GRAPH_QUERY_ENABLED`,
[client-guide.md §7](client-guide.md)) gives administrators read-only Cypher
without the port. The app also draws the graph, in
its card IFC-LPG, through that query or over Bolt.

## Limits and status

- One conversion at a time; large models queue. The example model (248
  entities) imports in about a second; a 200 MB architectural model takes
  minutes.
- The `Conversion` carries `state`, `entities`, `relationships`,
  `lossless`, `geometry`, `schema`, `ifc_project_guid`, timestamps and `error`. Administrators can
  inspect it in Neo4j Browser or Memgraph Lab:
  `MATCH (c:Conversion) RETURN c.file_name, c.state, c.entities, c.error`.
- Deleting a project deletes its models' entities with it.
- A model comes back identical from both databases at up to 224,496 instances and 19 MB, in
  every form measured. Nothing larger has been tried.
