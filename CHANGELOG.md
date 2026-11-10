# Changelog

Dataregium takes the same release numbers as [Dataspatium](https://github.com/marwiss/Dataspatium):
the same number on both means they work together. Each major number has one
release, numbered X.0.0: 2.0.0 for the 2 series and 3.0.0 for the 3 series.
A change to a series is released again under the same number; the release
before it is withdrawn (its commits remain) and its notes are folded into the
new one. Every release lists what a client can see; internal changes are in
the commit history.

## Unreleased

- The report of a version gets the check `graph` once its model is converted: an instance that nothing with a
  GlobalId reaches is a warning of the kind `reachability`, with its STEP id, and a product whose shape the geometry
  pass could not build is an issue of the kind `geometry`. Neither refuses the file. IFC-LPG is pinned at 8177587.

## 3.0.0 — 2026-11-10

Released again on 2026-11-10 (the fourth time) in step with Dataspatium 3.0.0; the releases of 2026-11-08 and
earlier on 2026-11-10 are withdrawn and their notes are folded in here. The first release of the 3 series: everything in 2.0.0, and the IFC graph as a lossless model that
can be written back as a file, every upload checked against the IFC schema, buildingSMART's rules
and the IDS documents of its project, named queries for members, IFC-LPG as a library, the clash check between two versions, the base version of an
upload, the refusal of uploads with validation errors, the precheck of a file, the schema of a change set and its trial on its base version, the approval of a trial as a new version with
the merge, the version nodes and the diff between two versions, the local engine, the working copy, headless
uploads, IFC-LPG's labels without Ifc, the geometry as glTF with a box per element in the graph, the merge by
instance with the three values of a conflict, the administration of a project by its managers, and a server in a
cloud region of one's own or beside an nginx. Works with Dataspatium 3.0.0.

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
Dataspatium's, and this release takes the first number again. No history is rewritten: the
commits stay, and only the earlier releases and tags went. Works with Dataspatium 2.0.0, which also
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
