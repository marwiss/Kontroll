# Changelog

Dataregium takes the same release numbers as [Dataspatium](https://github.com/marwiss/Dataspatium):
the same number on both means they work together. Each major number has one
release, numbered X.0.0: 2.0.0 for the 2 series and 3.0.0 for the 3 series.
A change to a series is released again under the same number; the release
before it is withdrawn (its commits remain) and its notes are folded into the
new one. Every release lists what a client can see; internal changes are in
the commit history.

## 3.0.0 — 2026-11-12

Released again on 2026-11-12 (the fourteenth time) in step with Dataspatium 3.0.0; the releases of 2026-11-08,
2026-11-10, 2026-11-11 and earlier on 2026-11-12 are withdrawn and their notes are folded in here. The first release of the 3 series: everything in 2.0.0, and the IFC graph as a lossless model that
can be written back as a file, every upload checked against the IFC schema, buildingSMART's rules
and the IDS documents of its project, named queries for members, IFC-LPG as a library, the clash check between two versions, the base version of an
upload, the refusal of uploads with validation errors, the precheck of a file, the schema of a change set and its trial on its base version, the approval of a trial as a new version with
the merge, the version nodes and the diff between two versions, the local engine, the working copy, headless
uploads, IFC-LPG's labels without Ifc, the geometry as glTF with a box per element in the graph, the merge by
instance with the three values of a conflict, the check graph in the report with the removal of what no GlobalId reaches, the publication of a version as a whole archive, the building of one model brought into another project's model, the administration of a project by its managers, a server in a
cloud region of one's own or beside an nginx, the operations of Dataspatium's write tools in a change set, an MCP
endpoint through which AI tools read the models and propose change sets that a person approves, the rooms of each
storey, the check against bSDD, the element of each rules finding, and the server's own data in a database of its
own. Works with Dataspatium 3.0.0.

- The IFC library IFC-LPG is now IFC-DB ([IFC-DB](https://github.com/marwiss/IFC-DB), package `ifc-db`, module
  `ifc_db`), with the same calls and the same form of the graph. The module's extra is now `ifc-db`, its settings
  `OPENCDE_IFC_DB_*`, its command `opencde ifc-db` and its page [docs/en/ifc-db.md](docs/en/ifc-db.md). The old
  extras `ifc-lpg` and `ifcgraph`, the old settings `OPENCDE_IFC_LPG_*` and `OPENCDE_IFCGRAPH_*` and the old commands
  still work, and the log and `opencde doctor` name the old settings a server is given; `raw` in
  `GET /admin/api/settings` names the settings by their new names.
- A change set's operations take Dataspatium's new write tools: `define_type` makes wall, slab, roof and covering
  types with their material layers and column, beam, footing, railing, door and window types, `create_element` makes
  columns, beams, members, footings, piles, coverings, railings, chimneys, shading devices, sanitary terminals,
  furniture and straight stairs, and `edit_element` changes a wall, slab, opening or roof in place and keeps its
  GlobalId. The other tools take a type, `load_bearing`, `status`, a storey's description and long name, a room's
  number and type, a material's category and a vertical datum. After the operations the trial joins the walls that
  meet, writes base quantities and sets IsExternal from the topology, with a note where it cannot; a site's map
  conversion is in metres with the file's unit as its Scale. `set_properties` holds IFC's own sets to IfcOpenShell's
  templates and refuses a unit in a value, and `transform_elements` moves a door or window with its opening and never
  the site, the building or a storey. The capabilities document lists the three tools in `ifc_changes.ops_tools`,
  and the MCP endpoint offers them with the app's schemas.
- A finding of buildingSMART's rules that names an instance carries its class in `ifc_class` and, in
  `root_global_id`, the GlobalId of the nearest rooted entity that reaches it, forward through attributes and
  backward through inverse ones as IFC-LPG's paths do: the instance's own, or for a polyline in a wall's outline
  (GEM111) the wall's. A worker reads both from the file, so a precheck and a trial have them too. `global_id` stays
  the instance's own and both fields are optional, so a report kept before reads as it did. The version's page shows
  the class beside the instance, and the element's GlobalId where the instance has none.
- The check `bsdd` also warns of a property whose `Specification` (IFC 4.3), or `Description` in an earlier schema,
  names a bSDD property that bSDD does not know, with the property in `step_id` and its set and name in `attribute`;
  and of a bSDD URI in a classification or property facet of one of the project's IDS documents that bSDD does not
  know, with the document in `document_id` and its specification named in the message, in the report of every file
  checked against that document. Each IDS version is read once, the lookups share the check's cache, and a trial of a
  change set never counts such a URI among its own findings.
- While the MCP endpoint is on, a client may register `http://localhost` with any port as its way back, as several
  MCP programs do, and the server sends a sign-in there only when it is for the MCP endpoint alone; every other
  sign-in to localhost is refused on a page, as before, unless `OPENCDE_ALLOW_LOCALHOST_REDIRECTS` is on.
- The MCP page says how an AI program is connected: the address on the local engine and on a team server, and
  examples for Claude Code, VS Code and Cursor (`docs/en/mcp.md`).
- The capabilities' `ifcgraph` names the store the models are in, `graph_store` (`neo4j` or `memgraph`), so that a
  client offers only the queries that store answers.
- The administration's project page offers Praxi's six statuses of a Swedish review (Ny kommentar, Ska åtgärdas,
  Ny granskning, Har åtgärdats, Avvisad, Godkänd) as a ready set for the project's `topic_status`.
- A contributor has the `createDocument` project action and attaches documents through the BCF API's documents
  service, referred to from their own topics; adding documents and versions through the Documents API, and a
  precheck, stay with an editor or a manager.
- IFC-LPG at d3ccc5f: the named queries `storeys` and `areas` give each storey's height in metres, `elevation_m`,
  and where it comes from, `elevation_source` (`attribute`, or `placement` for a storey without `Elevation`, as
  in IFC4X3), beside `elevation` as the file has it; and an IDS document that restricts a value with
  `xs:restriction` is read and checked instead of refused.
- On the MCP endpoint `server_query` and the two clash tools are listed only while the IFC-LPG module is on, as
  the change sets are; a user has at most two clash checks waiting or running in all their projects together, and
  makes at most 120 tool calls a minute whatever the token; an answer holding NaN or an infinity is a tool error.
- An error in the JSON log (`OPENCDE_LOG_JSON`, the default) carries its traceback without the frames' local
  variables, which held a request's body, its arguments and the caller's token.
- The MCP endpoint proposes change sets while the IFC-LPG module is on (ADR 0028, step 2): `open_changeset` opens a
  draft on a version of an IFC document and answers its `changeset_id`; Dataspatium's write tools
  (`create_storeys_and_grid`, `create_wall`, `create_slab`, `create_roof`, `create_opening`, `create_spaces`,
  `set_properties`, `set_classification`, `assign`, `transform_elements`, `delete_elements`, `set_site`), with the
  app's schemas unchanged and `changeset_id` first, each add one operation to `ops` exactly as the app makes it, with
  the refs `new-1` … and elements named by GlobalId, STEP id or ref; `manage_changeset` lists the steps and removes
  the last or all; `change_attribute` adds a post in `changes`; `propose_changes` makes the BCF topic with the change
  set as its snippet and queues its trial, and a later call with the same handle puts the change set on the same
  topic again; `get_proposal` gives the trial, waiting up to 20 seconds, with at most 50 findings, and
  `list_proposals` the proposals against a document. The change-set tools need `mcp:propose` and the role `editor`
  or `manager` at every call (`mcp.denied` with the reason `role` otherwise); no tool approves. A draft is its user's,
  closes 24 hours after its last use and is deleted by the server; a user has at most 10 open, a draft at most 200
  steps. The audit log records `mcp.changeset.opened` and `mcp.changeset.proposed` with identifiers and counts
  (`docs/en/mcp.md`).
- The operations of a change set (`ops`) give the model Dataspatium 3.0.0 gives: every class and enumeration value
  they set is checked against the file's schema, and a value the release deprecates (bSI rule IFC102) is never
  written. A wall is `SOLIDWALL`, or `PARTITIONING` with `"partition": true`, never `STANDARD`; in IFC4X3 a storey
  has its height in its placement alone, without `Elevation`, and the lowest and the highest storey are found by
  placement, and a room is `SPACE` with `Pset_SpaceCommon.IsExternal` false instead of `INTERNAL`. Outlines close
  on their first point (GEM111). `set_classification` takes the system's `edition`, `source` and `dictionary_uri`
  (as `Location` in IFC4, `Specification` in IFC4X3), and reuses a reference only for the same system, code and
  `uri`, and without a code the same name.
- The MCP endpoint has four more tools (ADR 0028), each for every member of a project the server may give to AI
  tools, with the same refusals as the REST routes. `server_query` asks the named queries of a version's model, by
  `document_id` and `version_index` (null for the latest), with `name` an enumeration of the catalogue and a field
  for each of its parameters, both built when the server starts, so a query IFC-LPG adds appears without code here;
  `name` null lists the queries with `model_state` and `workcopy`, and a query answers at most 500 rows with `count`
  and `truncated`. `get_publication` says whether a version is published, when, by whom and the archive's name,
  size and SHA-256, never where it is downloaded. `start_clash_check` starts a clash check of two versions of a
  project, recorded in the audit log as `mcp.clash.started`, and `get_clash_check` waits at most 20 seconds for its
  report, with at most 200 clashes; both refuse while the clash check is off (`docs/en/mcp.md`).
- The MCP endpoint answers at `POST /mcp` while `OPENCDE_MCP_ENABLED` is true, which `opencde init --local` now
  sets (ADR 0028): Streamable HTTP with JSON answers only, revision 2026-07-28 with `server/discover`, `tools/list`
  and `tools/call`, its `_meta` and the headers `MCP-Protocol-Version`, `Mcp-Method` and `Mcp-Name` checked against
  the body (`-32602`, `-32020`, `-32022`, and `404` with `-32601` for a method it does not have), and the handshake
  revisions 2025-11-25, 2025-06-18 and 2025-03-26 through `initialize` and `ping`, without a session. GET and
  DELETE answer 405; a batch, and a browser origin that is neither the server's own nor named in
  `OPENCDE_CORS_ORIGINS`, are refused; every request needs a token bound to the endpoint. The first tool,
  `list_models`, gives the IFC documents of the caller's projects with the latest version, the model's state and
  its schema; a server other than the local engine does not list a `local` project and refuses it by its id, which
  the audit log records as `mcp.denied`. A body is at most 1 MB and an answer 256 kB, and a token makes at most 120
  tool calls a minute; the request log keeps the method and the tool, never the body (`docs/en/mcp.md`).
- With `OPENCDE_ROOMS_ENABLED=true` (off by default), the report of an upload, a precheck and a trial also has the
  rooms of each storey as a section of its own, `rooms`, found from the walls with a copy of Dataspatium's code: per
  storey the rooms with their area, perimeter, walls and neighbours, the external walls with the compass sector they
  face, the open wall ends with their walls, whether the storey is closed, and the walls that could not be read, every
  wall by GlobalId. The rooms are never issues: no status, refusal or state of a trial depends on them. The version's
  page shows a row per storey, the capabilities document announces them as `rooms` in `ifc_validation`, and the
  `ifc-lpg` extra declares shapely 2.
- A token can be bound to the MCP endpoint for AI tools, which is off unless `OPENCDE_MCP_ENABLED` is true:
  `resource` (RFC 8707) on the authorization and the token request accepts `<public_url>/mcp` alone, anything else
  is `invalid_target`, and the code and its token family keep it through every refresh. Such a token holds `mcp`
  (the read tools) and, when asked for, `mcp:propose` (change sets), both asked for explicitly and only with the
  resource, and every REST API refuses it with `401 invalid_token`, so that an AI's token never reaches an approval
  or a publication. `GET /.well-known/oauth-authorization-server` (RFC 8414) describes the authorization server,
  its `issuer` the `iss` of every authorization response, and while the endpoint is on
  `GET /.well-known/oauth-protected-resource/mcp` (RFC 9728) describes the endpoint as a protected resource; the
  two scopes are listed in the metadata and the capabilities document only then.
- A project has an AI policy, `ai_policy` (ADR 0028): `local`, the policy of every project until someone changes
  it, lets AI tools have the project's data only on the user's own computer, and `cloud` lets AI services in the
  cloud have it too. A project's manager sets it with `PUT /manage/1.0/projects/{id}`, whose `GET` gives the
  project, and an administrator on the project's page or with `ai_policy` in the administration API; every change
  is audited. Every member reads it with `GET /documents/1.0/projects/{id}/ai-policy` (an extension); the answers
  the OpenCDE specifications define do not carry it. `OPENCDE_MCP_ENABLED`, off by default, announces the MCP
  endpoint for AI programs as `mcp` in the capabilities document: `/mcp`, the revisions of the protocol, newest
  first, the scopes `mcp` and `mcp:propose`, `default_ai_policy` and the policy's address as `ai_policy_url`. A
  change set is proposed by an `editor` or a `manager` alone: a `contributor` who uploads one with
  `PUT …/topics/{guid}/snippet`, through BCF API 3.0 or 2.1, or asks for one with `POST …/ifc-unreachable` gets
  `403` with the reason; snippets of other types are uploaded as before.
  first, the scopes `mcp` and `mcp:propose`, `default_ai_policy` and the policy's address as `ai_policy_url`.
  the OpenCDE specifications define do not carry it.
- A change set carries Dataspatium's write tools as `ops` in the form `ops_form` `dataspatium-tools/1`:
  `create_storeys_and_grid`, `create_wall`, `create_slab`, `create_roof`, `create_opening`, `create_spaces`,
  `set_properties`, `set_classification`, `assign`, `transform_elements`, `delete_elements` and `set_site`, lengths
  in metres, an element named by its GlobalId (its STEP id where no GlobalId reaches it) and a created one by its ref
  `new-1`, `new-2` …; `create_wall` gives a wall its centre line as an `Axis`, and `create_spaces` makes the rooms the
  walls enclose spaces with their quantities and boundaries, a ref for each room it lists. The trial applies them to
  the base version with a copy of the app's own code before the changes, which may then be empty, and a change the
  operations made already counts as applied; an operation that fails is an issue of kind `op` with its index and
  tool, and the trial gives `created` (the GlobalId of each ref) and `notes`.
  `keep_theirs` lists the conflicts the proposer gave up: the change set is then tried on the latest version and
  those attributes keep its values. The capabilities document announces `ifc_changes.ops_form` and
  `ifc_changes.ops_tools`.
- With `OPENCDE_BSDD_ENABLED=true`, an upload is also checked against buildingSMART's Data Dictionary: the check
  `bsdd` of its report warns of a classification reference whose class bSDD does not know, and, in a file of IFC 4.3,
  of a `Pset_` or `Qto_` set or a property of one that bSDD's IFC dictionary does not list, each with the STEP id of
  the reference or set and the GlobalId of an object it is on. bSDD out of reach fails the check with the reason in
  its new `error`, never the file. Off by default; `OPENCDE_BSDD_API_URL`, `OPENCDE_BSDD_TIMEOUT_SECONDS` and
  `OPENCDE_BSDD_CACHE_SECONDS` tune it, and the capabilities document announces it as `bsdd` in the new
  `ifc_validation`.
- `GET /documents/1.0/documents/{id}/ifc-proposals` lists the change sets tried against a document for a member
  of its project, newest first: the topic, the trial's state, the base version, who proposed it, the version an
  approved one became, and the addresses of the trial (`proposal_url`) and of its approval (`approve_url`); cut
  at 1000 rows with `X-Total-Count` and `Link` as the BCF lists are. The capabilities document announces it as
  `ifc_changes.ifc_proposals_url` beside `proposal_url` and `approve_url`. A proposal names its base from the
  moment it is queued, so the list holds it before the trial and when the trial failed.
- The server's record of a conversion is its own node, `Conversion`, under the project (`HAS_CONVERSION`): the
  file, the lifecycle, the geometry key, the graph check and a copy of the import's facts; `Model` is IFC-LPG's
  alone, written by the library and marked whole with `imported_at`. The models of earlier releases get their
  `Conversion` when the server starts. Cypher of one's own that read `Model.state` or walked `HAS_MODEL` reads
  `Conversion` and `HAS_CONVERSION` instead, joined to the model by `model_id`.
- The server's own data can live in a graph of its own, apart from the IFC graph (ADR 0027):
  `OPENCDE_STORE_GRAPH_URI` with `OPENCDE_STORE_GRAPH_DIALECT`, `_USER`, `_PASSWORD` (required in production) and
  `_DATABASE`, another database of the same product or of another product; by default it shares the IFC graph's
  connection. The IFC-LPG service writes the models to the IFC graph and its records to the store; the command
  line, the seed, the doctor and the Settings page open both where they need both, and `/readyz` says in `store`
  whether the store is `shared`, `ok` or `unavailable` and is ready only when both answer. A backup holds both
  graphs in the same files and a restore puts each node where its label belongs, so a backup of one database
  restores into two; a user's relationships are no longer written twice into a backup.

- The named queries, the GTIN of a viewpoint's components and the constraints of the IFC graph come from IFC-LPG
  1.0.0 at 6f6d05b: a query added to the library's catalogue appears in `GET …/ifc-queries` as it is, and the
  relationship `SAME_AS` is no longer made, and the ones earlier releases made are removed when the server
  starts; the GTIN is on the component as before, and an element is found by the component's `GlobalId`,
  which is indexed. Cypher of one's own that walked `SAME_AS` joins on `GlobalId` instead.
- The server's own records in the graph are labelled `Validation`, `Precheck`, `Proposal`, `Clash` and `Merge`,
  without `Ifc`, so that a label that begins with `Ifc` is always one of IFC's classes; nodes made by earlier
  releases are relabelled when the server starts. Cypher of one's own that named the old labels must follow.
- A preparation of B that meets what A's schema has no equivalent of, such as IFC2X3's IfcWindowStyle in IFC4X3 or
  the owner histories IFC2X3 requires, ends in `conflict` with the problems and the options for each; a new
  `POST …/ifc-merge/prepare` with `resolutions` chooses, and an unknown choice is refused with 400. The converted
  copy is checked against B, and one with issues B did not have is not made (`failed`, with them in `report.new`).
  IFC-LPG is pinned at d8d75b9.
- A new version of an IDS document has the latest version of every IFC document in the project checked again, at
  most 500, so that the reports follow the project's requirements as they are now; before, an IDS applied only to
  the IFC versions uploaded after it.
- A `manager` sets up the teams of a project under `/manage/1.0/projects/{id}/teams`: a name, a responsible member
  with at least the role `editor`, the members, and an IDS document of the project that points out the team's part
  of the model. The trial of a change set lists in `teams` those whose part it touches; a change to the part of one
  team is approved by that team's responsible alone, and one across several teams' parts, or none, by a `manager`.
  The capabilities document gives `teams_url` under `project_administration`.
- A merge compares units by kind, SI base and scale, so that two spellings of the same unit count as one; a class with
  no counterpart in A's schema stops the preparation of B with what it is. IFC-LPG is pinned at 318d466.
- The report of a version gets the check `graph` once its model is converted: an instance that nothing with a
  GlobalId reaches is a warning of the kind `reachability`, with its STEP id, and a product whose shape the geometry
  pass could not build is an issue of the kind `geometry`. Neither refuses the file.
- A change set can delete an instance named by its STEP id that nothing refers to (the op `delete`); one that
  something still refers to is skipped and named in the trial. `POST /documents/1.0/projects/{id}/ifc-unreachable`
  makes the server propose such a change set for a version: a BCF topic that deletes every instance no GlobalId
  reaches, tried and approved like any other.
- A `manager` publishes a version with `POST /documents/1.0/documents/{id}/versions/{index}/publication`: the
  server keeps its file as one archive, `.ifczip` for an IFC file and `.zip` for another, and the version's
  metadata gets `published_at`, `published_by` and `publication`. A version is published once, and not while it is
  being checked or when its check found errors (409). Every member reads `GET …/publication` and downloads the
  archive from `…/publication/download`. Announced as `publication`.
- The building of one model comes into another project's model as the next version of its document:
  `POST /documents/1.0/projects/{id}/ifc-merge/report` tells a member of both projects what would come along and
  lists the objects both have with a GlobalId, with whether their content is the same; `POST …/ifc-merge` lets a
  `manager` make it as a job, with a choice for each differing object (`a`, `b` or `new`) or a `default`. The
  merged model is checked against both, written out as the next version with the base as its parent, and
  converted and checked as an upload. A conflict names the objects that lack a choice, and a base that is not the
  latest gets 412. Where B's schema or length unit is not A's, `POST …/ifc-merge/prepare` first makes a copy of B
  migrated to A's schema and with A's length unit, which stands in for B for a day. Announced as `ifc_merge`.
  A unit of a kind A has none of comes along and is listed in the report's `units_added`. IFC-LPG is pinned at
  e38a71d.
- A list of topics, comments or events without `$top`, or with one above 1000, still holds at most 1000 entries, and
  now says so when more match: `X-Total-Count` with their number and `Link: <…>; rel="next"` with the address of the
  rest, which a browser may read.
- The API document (`/openapi.json`) gives `400` with the error body for a request the server cannot read, as the
  server answers, where it said FastAPI's `422`.
- On Memgraph, an administrator's graph query that runs past its time limit is stopped on the server. Memgraph does
  not take the Bolt transaction timeout and went on running the statement for up to ten minutes after the answer
  "time limit", holding its storage so that no schema statement got through meanwhile.
- On Memgraph, a schema statement waits up to about two minutes for unique access to the storage, which a periodic
  snapshot or a long write holds for seconds: the point index made again after every import, and the schema applied
  at start. Before, it gave up after about seven seconds, and a model lost its boxes or the server did not start. A
  transient error while the point index is dropped is no longer passed over, so a stale index is not left in place.
- The production overlay starts without `OPENCDE_ACME_EMAIL`: Caddy refused an empty `email` and did not start, so
  the address was in practice required. The backup sidecar no longer inherits the image's health check, which asked
  for an API it does not run and showed it as unhealthy.
- Beside what already runs on a server: `docker/compose.proxied.yaml` is the production overlay without its Caddy,
  for a host whose own reverse proxy (nginx, Apache, Traefik) keeps ports 80 and 443 and its certificates; the API is
  published on `127.0.0.1:8010` only (`OPENCDE_PROXIED_ADDRESS`, `OPENCDE_PROXIED_PORT`) and the stack gets a project
  name of its own. The guide `docs/en/deploy/proxied.md` has the nginx site, certbot for the new name only, and how
  to remove it all again.
- Your own region on AWS, Azure or Google Cloud: `docker/cloud-init.yaml`, given as a virtual machine's user data,
  sets up the whole stack with Caddy on Ubuntu 24.04 LTS: the release checked out, `.env` with fresh secrets, HTTPS
  for the machine's DNS name or `<public address>.sslip.io` until it has one, and the first administrator, whose
  password goes to a file only root reads. The guide `docs/en/deploy/cloud.md` gives one command per cloud, the
  firewall and where the personal data is.
- Project administration by its managers (OB-41): a `manager` lists, adds (by exact user name), re-roles and removes
  the members of their project under `/manage/1.0/projects/{id}/members`, with a token holding the new `project`
  scope, which a client asks for explicitly; a project keeps at least one manager (`409 conflict`), the name changes
  through the BCF API's PUT Project, and a deletion stays with the administrators. Every write is in the audit log as
  `manage.*`. Announced as `project_administration`.
- Where the products are, and the geometry (OB-37): after a conversion IFC-LPG's geometry worker runs once over the
  file, every product gets its box in the graph (`bbox_min`, `bbox_max`, `bbox_centre` as points on the `Entity`,
  with a point index on `bbox_centre`, in the archive and the working copy), and
  `GET /documents/1.0/documents/{id}/versions/{index}/ifc-geometry` answers with a binary glTF of the version
  (`lod=full` or `box`, `classes=`, `storey=`; every shared mesh once, a node per product under its storey, `ETag`
  and `304`), built from the records the first time and kept. `OPENCDE_IFC_LPG_SPATIAL` (on) and
  `OPENCDE_IFC_LPG_GEOMETRY_THREADS`; announced as `ifc_geometry`.
- The merge at the approval compares the instances, not the keys the clients wrote: each change is resolved in the
  version it was made on and named by its canonical path (IFC-LPG's `ifc_lpg.paths`), so two changes that reach one
  shared instance from different GlobalIds collide. The `412 version_conflict` of an approval carries
  `conflict_details` beside `conflicts`: per conflict the key, the proposal's own locator, what the base held
  (`base`), what the latest version holds (`theirs`), what the proposal sets (`ours`) and the version that changed it.
- IFC-LPG's form version 2: a styled item (`IfcStyledItem`) is always a node in the skeleton form, so that every
  style can be changed, and a path reaches a mesh's style and layer from an instance in a block; new conversions
  carry `form_version` 2, and models converted before keep form 1. IFC-LPG is locked at 6a8e2cb.

- IFC-LPG names its own labels without Ifc (its release of 2026-11-10): `Model` and `Entity` instead of `IfcModel`
  and `IfcEntity`; `StepBlock`, `model_id`, `step_id`, the relationships and the properties are as before, and a
  `Model` carries `format` (`step`) and `form_version`. The server relabels what was converted before at startup,
  so nothing needs converting again; Cypher of your own that names `IfcModel` or `IfcEntity` changes to the new
  names. IFC-LPG is locked at 61a2d69.
- Headless uploads: a confidential client an administrator approved for it (*May upload documents without the
  browser page*, also `headless_uploads` in the administration API) names `project_id` and the titles in
  `POST /documents/1.0/upload-documents` and goes straight to the instructions; every such upload is in the audit
  log as `documents.headless_upload`. Announced as `headless_uploads` in the capabilities document.
- The working copy: with `OPENCDE_WORKCOPY_GRAPH_URI` a second graph, Memgraph in memory, holds the head model of
  every document too, imported from the same records, and answers the named queries for it; the archive keeps
  every version. `docker/compose.workcopy.yaml` adds the Memgraph; `GET …/ifc-queries` says `workcopy`, `/readyz`
  reports its state, the capabilities document announces it in `ifcgraph.workcopy` (ADR 0024).
- The local engine: `OPENCDE_ENVIRONMENT=local` for Dataregium on a person's own computer behind Dataspatium
  (ADR 0023). The server keeps to the loopback (public URL, interface, a `421` for any other `Host`), needs a
  database password and a secret key, names its CORS origins and answers Chrome's Private Network Access
  preflight. `opencde init --local` writes the `.env`, and `docker/compose.local.yaml` publishes the API on
  127.0.0.1 only.
- An approved change set gives its topic a viewpoint that selects the changed elements, so that the topic shows
  in 3D what the version changed.
- Two named queries more: `entity?global_id=` gives one rooted entity with every literal attribute and what it
  refers to and is referred to by, and `changed-since?since=` lists what changed in the document since a version,
  from the change sets of the versions between (one row with `whole_file` for a whole-file upload).
- Two IFC versions are compared element by element: `GET /documents/1.0/documents/{id}/versions/{index}/ifc-diff/{other}`
  (an extension announced as `ifc_diff`; `?other_document_id=` for another document of the project) answers with
  what was added, removed and changed, by GlobalId and path, computed on request; the version's page shows the
  same as lists.
- A version built on another is a node with its parent: `parent_version_index` and a `DERIVED_FROM` link, on a
  version approved from a change set and on an upload with `base_version_index`. A version approved from a
  change set carries `approved_by`, `change_set_id` and the changes, which
  `GET /documents/1.0/documents/{id}/versions/{index}/ifc-changes` gives (an extension; 404 for a whole-file
  upload).
- The server merges at the approval: when the document has moved on since the change set's base, the changes of
  the versions in between are compared attribute by attribute with the proposal's; when none collide, the change
  set is tried again on the latest version and approved on it, else `412 version_conflict` names the colliding
  attributes in `conflicts` (`*` when a version in between was uploaded as a whole file).
- A `manager` approves a clean trial with `POST /bcf/3.0/projects/{id}/topics/{guid}/ifc-proposal/approve`: the
  applied file becomes the next version of the base document, with `base_version_index`, `change_set_id`,
  `proposed_by`, `approved_by` and, where an AI proposed it, `ai_model` and `tool_call` in its metadata; the topic
  gets a comment with the version's address and the status `Closed` where the project has it. `412
  version_conflict` when the document has moved on since the base, `409` when the trial is not clean.
  `ifc_changes` in the capabilities document carries `approve_url`.
- A change set is tried on its base version when it is uploaded as a topic's snippet and the IFC-LPG module is
  on: a worker applies the changes to the base version's file, the result gets the checks an upload gets, and
  `GET /bcf/3.0/projects/{id}/topics/{guid}/ifc-proposal` gives the trial: `clean` when every change applied and
  no finding is new compared with the base, else `issues`, with the new findings and a `proposal` issue per
  change that could not be applied. `ifc_changes` in the capabilities document carries `tried` and
  `proposal_url`.

- The form of a proposed change to an IFC model: a change set as the `bim_snippet` of a BCF 3.0 topic, with
  `snippet_type` `DataregiumIfcChangeSet` (among a new project's values) and the published JSON Schema
  `GET /documents/1.0/ifc-changes/schema` as its `reference_schema`. `PUT …/topics/{guid}/snippet` holds such a
  snippet to the schema and answers `400` with what is wrong. The capabilities document announces it as
  `ifc_changes`. The changes are checked against the model when a proposal is tried, in a later release.
- A project can refuse uploads with validation errors: *Refuse uploads with validation errors* on its page in the
  administration (`block_on_validation_errors` in the administration API). The checks then run before the file
  becomes a version, and a file with errors is refused with `422 ifc_validation_failed` and the address of its
  report; warnings pass. A file can also be checked without becoming a version:
  `POST /documents/1.0/projects/{id}/ifc-precheck` with the file as the body (an extension announced as
  `ifc_precheck`), and `GET …/ifc-precheck/{id}` gives the report for a day.
- An upload can say which version it builds on: `base_version_index` on a file entry of
  `POST /documents/1.0/upload-documents` (an extension). The completion answers `412 version_conflict` when the
  document already has a newer version, and the new version's metadata carries `base_version_index`.
- The `IfcModel` node records which form IFC-LPG converted the model in (`geometry`: `skeleton`, `blocks` or
  `nodes`); the skeleton is the default since IFC-LPG 1.0.0 of 2026-11-10, with points for coordinate lists.
- A clash check between two IFC document versions of a project, as an extension of the Documents API:
  `POST /documents/1.0/projects/{id}/ifc-clash` starts it (IfcClash in a worker process; modes `intersection` and
  `clearance`), `GET …/ifc-clash/{id}` gives the report in the form Dataspatium's own clash core writes, and
  `POST …/ifc-clash/{id}/topics` makes BCF topics with a viewpoint of chosen clashes, on request only. Off until
  `OPENCDE_IFC_LPG_CLASH_ENABLED=true`; the capabilities document announces it as `ifc_clash`. `ifcclash` joins the
  `ifc-lpg` extra.

- The Docker files live in `docker/`: the Compose files, the Dockerfile and the Caddyfile. `.env` names the
  Compose files to combine (`COMPOSE_FILE`, written by `opencde init`), so the commands are `docker compose up -d`
  and so on, without `-f` options; an overlay such as Memgraph is added to that line.
- The server is called Dataregium; it was Kontroll until 8 November 2026. The capabilities document is
  `GET /.well-known/dataregium`, and `/.well-known/kontroll` answers the same as an alias; `server.name` in it says
  `Dataregium OpenCDE server`. The Compose project is named `dataregium`; an installation that keeps its volumes from
  the old name sets `COMPOSE_PROJECT_NAME=kontroll` in `.env` (see docs/en/deploy/local.md).
- An IFC model can be written back from the graph as a file that holds the same model, on Neo4j and on Memgraph:
  `opencde ifc-lpg export <model id> model.ifc`, with `--verify` to compare it with the upload. See
  [docs/en/ifc-lpg.md](docs/en/ifc-lpg.md).
- A model is converted in a new form by default. It has the same nodes, relationships and values as before, so queries
  keep working. Added to them are `position` on the relationships of forward attributes, `<attribute>__type` beside typed
  values and `<attribute>__step` for references to what is no node. Geometry is compressed text on `StepBlock` nodes, which
  a query should not return whole. `OPENCDE_IFC_LPG_LOSSLESS=false` gives the old form. Models already converted keep
  theirs, and cannot be written back until uploaded again.
- A file written from the graph is validated against the IFC standard, and an issue the upload does not have ends the
  command with an error. The `ifc-lpg` extra now includes pytest, which IfcOpenShell's validator needs at run time.
- Every IFC file uploaded as a document version is checked against the IFC schema in the background, and the upload is
  never held back by it. The version's metadata says how it went (`ifc_validation_status`, `ifc_validation_issues`,
  `ifc_validation_checked_at`, `ifc_validation_ruleset`) and where the report is (`ifc_validation_report`). The report is
  an extension, `GET /documents/1.0/documents/{id}/versions/{index}/ifc-validation`, with up to 10,000 issues and the
  GlobalId of each element. The version's page shows the first 100. `OPENCDE_IFC_LPG_VALIDATE_UPLOADS=false` turns it
  off.
- Uploads are also checked against buildingSMART's ifc-gherkin-rules, the rules of buildingSMART's validation service,
  where `OPENCDE_IFC_LPG_GHERKIN_ENV` names an environment for them. `python -m ifc_lpg.gherkin_install` makes
  one from pinned downloads. The published image leaves them out; the image tagged `-gherkin`, such as `3.0.0-gherkin`
  or `latest-gherkin`, has them and is about 1.1 GB, as is an image built with `--build-arg OPENCDE_GHERKIN=1` or by
  docker compose with `OPENCDE_GHERKIN=1`. A finding is an issue of the kind `gherkin` with the rule's code in
  `rule`. `ifc_validation_status` gains `warnings`, for a file whose issues are all warnings, and `issues` now means at
  least one error. `ifc_validation_ruleset` has one value per check. The report gains `error_count` and `checks`, which
  lists each check with the rules that could not run. See ADR 0012.
- Uploads are also checked against the IDS documents of their project, the latest version of every document whose name
  ends in `.ids`, with IfcOpenShell's IfcTester as Dataspatium runs it. A finding is an issue of the kind `ids`, an
  error, with its document in `document_id`. The check `ids` lists the documents used and every specification with
  its verdict, and the version's page shows them in a table. An IDS that cannot be read, such as one with a DTD, is
  listed under `rules_not_run`. See ADR 0015.
- A member of a project can ask a version's IFC graph named queries, through an extension of the Documents
  API: `GET /documents/1.0/documents/{id}/versions/{index}/ifc-queries` lists them and `…/ifc-queries/{name}`
  asks one, with its parameters in the query string. The seven are `element-classes`, `elements`, `storeys`,
  `spaces`, `areas`, `materials` and `property`. An answer has columns and rows, at most 10,000, and the
  capabilities document announces the queries in `ifc_queries`. See
  ADR 0016.
- `python -m ifc_lpg.equivalence first.ifc second.ifc` says whether two IFC files hold the same model.
- `GET /admin/api/settings` has `ifcgraph.lossless` and `ifcgraph.validate_uploads`.
- The round trip and the checks of the IFC-LPG module are the library [IFC-LPG](https://github.com/marwiss/IFC-LPG),
  installed from its repository at a fixed commit until it is on PyPI. The server always has its graph side, which
  needs no IfcOpenShell, and the `ifc-lpg` extra adds the workers with IfcOpenShell, as before. Building the image
  fetches it with git. See ADR 0014.

## 2.0.0 — 2026-11-07

The single release of the 2 series: everything up to and including 2.7.0, with the deletion of a
project put right and the IFC-graph module renamed IFC-LPG, on the branch `release-2`. The 2.0.0
and 2.0.1 released earlier the same day are withdrawn under the rule above, together with
Dataspatium's, and this release takes the first number again. The commits
stay, and only the earlier releases and tags went; later the same day every commit got the noreply
address of its author, with the same content and new hashes. Works with Dataspatium 2.0.0, which also
speaks BCF API 2.1, so that a server with 2.1 alone can be its source, and draws the IFC graph.

- The server is called Dataregium; it was Kontroll until 8 November 2026. The capabilities document is
  `GET /.well-known/dataregium`, and `/.well-known/kontroll` answers the same as an alias; `server.name` in it says
  `Dataregium OpenCDE server`. The Compose project is named `dataregium`; an installation that keeps its volumes from
  the old name sets `COMPOSE_PROJECT_NAME=kontroll` in `.env` (see docs/en/deploy/local.md).
- A server can offer only some of its APIs. `OPENCDE_APIS=["bcf-2.1"]` makes it a server for BCF API 2.1 alone,
  without the Foundation API, and `["documents"]` a document server with the Foundation API and the Documents API.
  The version lists, the capabilities document and `apis` in `GET /admin/api/settings` say what is offered, and an
  API that is not offered answers 404. All three are offered by default.
- The IFC-graph module is now IFC-LPG, the name of its library,
  [IFC–LPG round-tripping](https://github.com/marwiss/IFC-LPG). Its settings are `OPENCDE_IFC_LPG_*`, its command
  `opencde ifc-lpg`, its extra `ifc-lpg` and its page [docs/en/ifc-lpg.md](docs/en/ifc-lpg.md). The old names
  `OPENCDE_IFCGRAPH_*`, `opencde ifcgraph` and `ifcgraph` still work, so a server keeps its configuration across the
  upgrade, and the log and `opencde doctor` name the old settings it is given. The administration API and the
  capabilities document keep their keys, except that `raw` in `GET /admin/api/settings` names the settings by their
  new names.
- Deleting a project deletes only what the project owns. Before, it followed every relationship from the project,
  so it also deleted each user who had created a topic, comment or viewpoint or uploaded a document in it, then the
  other projects those users were members of, and the topics and documents directly in those. The administration's
  list of files to remove followed the same paths, so it could delete files of other projects.
- Deleting a project deletes all the entities of its IFC models. Those more than a few steps from the project stayed
  behind before.
- `DELETE /admin/api/projects/{id}` frees the project's stored files, as the administration's page did.
- BCF API 2.1 is served next to 3.0, under `/bcf/2.1`, on the same data, so that a client that implements only
  2.1 can connect. `GET /foundation/versions` and `GET /bcf/versions` list both versions, the newest first.
  A topic made through one version can be read and changed through the other; the client guide says what differs.
- An administrator can mark a confidential client that may sign in without PKCE, since BCF API 2.1 knows nothing of
  it: on the client's page, with `pkce_optional` in the administration API, or with
  `opencde client create --without-pkce`. A client that registers at the address in `GET /bcf/2.1/auth` is marked the
  same way. Every other client must use PKCE as before.
- `opencde_client` speaks BCF API 2.1 with `bcf_version="2.1"`, and takes the newest version a server offers with
  `bcf_version="auto"`, also on a server that has 2.1 alone.
- A client's description may hold 4000 characters, as the specifications say.
- `GET /.well-known/kontroll` has `bcf_versions`.
- In the IFC graph, a model's `IfcOwnerHistory` is linked from its `IfcProject` only, as the documentation
  said. Until now every entity that shared it got an `OWNER_HISTORY` relationship, which made one node the
  centre of the graph. A model imported earlier keeps them until it is uploaded again.
- The documentation of the IFC graph says where the method comes from: the article by Zhu, Wu and Lei
  (2023), and where the conversion differs from it.
- The APIs take the schemas' types at their word: a text where a boolean or a number should be,
  such as `"yes"` or `"5"`, is refused with 400 where it was once converted. A number may still
  be written without decimals. The length limits count what was sent, whitespace included.
- The API document says that a deletion and an uploaded part answer with no body, as they do.
- The forms on the administration's pages for a user, a project and a client save without the
  page reloading. Without JavaScript they work as before.
- `opencde init` without options asks for what it needs, in a terminal, and then says what comes
  next, including the administrator and the first client.
- The health checks on the settings page speak the language of the page. The command line and
  the administration API go on in English.
- `opencde seed` builds the graph of the sample model when the IFC graph is on, so the quick
  start's query answers without an upload first.
- The start page says where to start: trying the server, seeing how it is built, running it for
  others and building a client. The API document has examples of the main request bodies.
- `compose.external-db.yaml` runs the stack against a database elsewhere, with its address in
  `OPENCDE_STACK_GRAPH_URI`, and leaves the database container out.
- A generated or reset password has to be changed before anything else works, as the
  documentation said. It only led to the account page once, and a client could get tokens with it
  for as long as it liked. A sign-in through OAuth2 now goes through the change and on to the client.
- A user's page in the administration could not be saved without one's own password, since a
  browser silently refuses a form over a required field in a collapsed section. The password
  is only needed when the administrator flag changes, as the page says.
- A conversion to the IFC graph that a stopped server left behind starts over; it used to stay
  queued or running for good.
- A registration that asks to come back to `http://localhost` is refused with its own code,
  `localhost_redirect`, and a message that says what to do, so that a client can translate it.
- The limit per address on the API, which the documentation described but no code applied,
  now holds at 600 requests a minute, with 240 on the administration. `OPENCDE_RATE_LIMIT_API`
  raises it for an office behind one address, as `OPENCDE_RATE_LIMIT_SIGN_IN` does the limit on
  signing in, and several server processes can share the counts
  through `OPENCDE_RATE_LIMIT_STORAGE`.
- Outside production a client can register 60 times an hour rather than five, since someone
  trying a server out registers again and again.
- Signing out on a page that asks for another account leads to the sign-in and back to that
  page, so that the upload or selection continues in the same window.
- Dynamic registration can be limited further: `OPENCDE_DYNAMIC_CLIENT_REGISTRATION_TOKEN`
  asks for an initial access token, and `OPENCDE_DYNAMIC_CLIENT_APPROVAL` keeps a new client
  disabled until an administrator approves it under `/admin/clients` or with
  `opencde client approve`. The capabilities document says which applies.
- A refresh token left unused for two weeks stops working, inside the absolute lifetime
  of 30 days (`OPENCDE_REFRESH_TOKEN_IDLE_SECONDS`).
- Failed sign-ins make a user name wait, on both sign-in forms: after five in a row a
  wait that doubles from 30 seconds up to 15 minutes, on top of the limit per address.
- `opencde doctor` runs the checks of the settings page, and both now also look at the
  schema, the CORS origins and the headers and certificate at the public address. It
  exits with 1 when a check fails.
- Local development uses `http://127.0.0.1:8000` throughout, in the development
  overlay, `opencde init --dev` and the documentation. A redirect to `127.0.0.1` needs
  no setting, so the quick start has one line less to change in `.env`. `localhost`
  keeps working as an address, and `OPENCDE_ALLOW_LOCALHOST_REDIRECTS` still exists.
- The server removes a service worker that another app left on the same address, by answering
  the browser's check for its script with one that removes it, empties its caches and reloads
  the windows. Such a worker answers with old copies of the pages, so that the sign-in fails
  with an expired form. It works while a saved page is showing, and needs nothing in the pages.
- The quick start covers everything it takes to sign in to Dataregium from
  Dataspatium: what you need, exactly which lines of `.env` to change and why, the
  words on the screen in each language, and a troubleshooting table that quotes each
  message with its cause and what to do. It was followed literally from an empty
  folder in Firefox and Chromium.
- `opencde seed` run right after `docker compose up` no longer risks a deadlock with
  the starting server, which restarted the server and killed the seed without output.
- The page that refuses an authorization request states its reason in the user's
  language, not only in English.
- Dataspatium brings IfcOpenShell into the browser, checks IDS, shows downloads with their progress and draws the
  IFC graph. Apart from BCF API 2.1 above, none of it needs anything new from the server.
- `docs/dataspatium-coordination.md` now records what the two projects share and
  the owner's decisions, without planning.
- The language cookie `opencde_lang` is `HttpOnly`, since the pages' scripts
  never read it, and the security suite proves that only a known language code
  can reach it.
- The personal data page links to Dataspatium's half in each language, and the
  READMEs no longer say that the contribution to IfcOpenShell waits for an
  answer: nothing has been sent.
- The nightly job that tests the pair now runs Dataspatium's live suite and
  requires passed tests. It used to report success without running one,
  because the browser aborted on the runner; the live runs recorded in
  `docs/acceptance.md` from the owner's machine are not affected.
- The documentation exists in the seven languages of the README: the client
  guide, the OAuth2 and Documents API flows, the graph schema, the IFC-graph
  page, the style guide and the security pages are under `docs/<language>/`
  next to the quick start and the deployment guides. The project logs, the
  architecture decisions and the upstream drafts stay in English.
- The quick start follows Dataspatium: a source is added from the left
  column of *Inhämta*, with the client id left empty so that the app registers
  itself.
- The Danish pages say *kodeord* for a password throughout, and the Icelandic
  pages say *tóki* for a token, as Dataspatium does.
- `SECURITY.md` separates what runs on every push, every night and every
  release from what is done by hand (OAuch and testssl.sh, not yet run against
  a production deployment), and the supported versions follow the rule above.
- The validation messages of the administration and account pages (user
  names, passwords, project names and extension lists, clients and their
  redirect URIs) follow the page language; the CLI and the API keep the
  English texts.
- The development overlay's public URL follows `OPENCDE_DEV_PORT`, so a
  second local stack on another port signs in correctly; the quick start and
  the local guide explain the `kontroll-graph-1 is unhealthy` stop (a
  password under 16 characters, or an old database volume) and how two
  checkouts share one machine (`COMPOSE_PROJECT_NAME`).
- The pages a client opens in a pop-up (the authorization page, the
  Documents API selection and upload pages, the sign-in) no longer send
  `Cross-Origin-Opener-Policy: same-origin`, which cut the pop-up's link to
  the application and left the user on the callback page with its address;
  the administration and account pages keep the isolation.
- The authorization page and the Documents API selection and upload pages
  name the client's origin in their `form-action` policy, so Chrome and Edge
  follow the redirect that answers the form; before, those browsers stayed
  on the sign-in page (Chromium checks `form-action` against the redirect)
  while Firefox went on.
- Without `OPENCDE_SECRET_KEY` (allowed outside production) the server now
  keeps its generated key in `OPENCDE_DATA_DIR/secret_key`, so that a
  restart or a rebuild no longer answers every open sign-in form with "the
  form has expired" and no longer ends every browser session.
- The quick start names the demo user it signs in as, `inspection_manager`
  (the editor of *Building permit*), instead of a user that the seed does
  not create.
- Foundation API 1.0, BCF API 3.0 and Documents API 1.0, validated against
  the buildingSMART schemas pinned in `spec/`; OAuth2 authorization code
  with PKCE for every client, rotating refresh tokens, token revocation (RFC
  7009) and dynamic client registration with public clients (RFC 7591,
  `software_id`/`software_version` stored).
- Extensions outside the specifications, each marked as such: the
  capabilities document `GET /.well-known/kontroll`; a stable `code` in every
  error body (`validation_error`, `unauthenticated`, `invalid_token`,
  `insufficient_scope`, `forbidden`, `reauthentication_required`,
  `not_found`, `conflict`, `payload_too_large`, `upload_too_large`,
  `rate_limited`, `internal_error`, `unavailable`); the request log
  (`/admin/requests`, `GET /admin/api/requests`); the IFC-graph module with
  `SAME_AS` links from BCF components to building elements; deep links into
  Dataspatium from the project and document pages.
- The administration API under `/admin/api/` in the resource shapes agreed
  with Dataspatium: a flat overview with `uptime_s` and
  `models`, users with `name` and their project roles, projects with inline
  `members`, clients with `public`, sessions with an `id` that
  `DELETE /admin/api/sessions/{id}` accepts, `DELETE /admin/api/sessions?user=`,
  structured settings with the raw values under `raw`, `PUT` beside `PATCH`,
  `POST …/reset-password`, `POST …/rotate-secret`, `initial_password` in the
  answer to a created user without a given password; dangerous writes need
  a sign-in from the last ten minutes.
- A read-only graph query for administrators, off by default
  (`OPENCDE_GRAPH_QUERY_ENABLED`): `POST /admin/api/graph/query` with
  `{cypher, params}` answers `{columns, rows, truncated}`, nodes,
  relationships and paths as JSON objects, within `max_rows` and
  `timeout_seconds` announced in the capabilities document; writing clauses,
  procedures other than the schema procedures and protected properties are
  refused, and every call is audited.
- Web pages (sign-in and consent, Documents API selection and upload,
  account, administration) in seven languages (English, Swedish, Danish,
  Norwegian Bokmål and Nynorsk, Finnish, Icelandic), chosen by `?lang=`, a
  cookie or `Accept-Language`, with Dataspatium's design (tokens, Inter,
  component looks) by the permission of its copyright holder.
- Deployment: compose overlays for local use, production behind Caddy, a
  tunnel, Memgraph, and `compose.bolt.yaml` for publishing the database
  port with TLS on purpose; a published multi-arch image with an SBOM; a
  seed with the three-wall sample model, one topic, viewpoint and comment
  under fixed ids.
- Documentation: README, the joint quick start and the deployment guides in
  seven languages, the client guide, the security pages (threat model,
  controls, ASVS checklist, personal data), the coordination plan with
  Dataspatium, and `CONTRIBUTING.md`.
