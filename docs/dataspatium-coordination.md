# Coordinating Dataregium and Dataspatium

Dataregium (this server) and [Dataspatium](https://github.com/marwiss/Dataspatium)
(the browser app) are developed to work together. This page records what the
two projects share, the interfaces and practices they agreed on, and the
decisions the owner took. The counterpart on the app side is its
`docs/utveckling.md` ("Prov mot Dataregium") and the release notes.

## Overview

| Area | State |
|---|---|
| Protocol | Dataspatium talks to Dataregium through the three OpenCDE APIs, plus marked extensions: the capabilities document, the administration API with the request log and the graph query, and Cypher over Bolt against the IFC graph when the operator publishes the port |
| Sign-in | OAuth2 authorization code with PKCE as a public client; self-registration through RFC 7591 (`token_endpoint_auth_method: "none"`) when the server allows it; one registration per installation, unused registrations expire |
| Correlation | `X-Request-ID` on every call from the app, echoed by the server and kept in its request log |
| Testing | Dataspatium's live suite runs against Dataregium's development stack, on the owner's machine and in the nightly pair job; results and server findings are recorded in [acceptance.md](acceptance.md) |
| Documentation | A shared section "Dataregium and Dataspatium" in both READMEs, each in seven languages (English, Swedish, Danish, Norwegian Bokmål and Nynorsk, Finnish, Icelandic), and cross-references from the guides on both sides |
| Branding | Sibling marks: Dataspatium's stacked sheets (D) and Dataregium's connected nodes, same plate, stroke and margins |
| Working agreements | Announce heavy local runs to the other session; non-release commits in Dataspatium from this project; no git operations in the other checkout; findings reported with request ids |

## The capabilities document

Dataspatium does not have to guess which extensions a Dataregium server offers.
`GET /.well-known/dataregium` (outside the specifications, no auth) lists the
server version, the enabled extensions and their versions, the retention of the
request log, whether Bolt is published, and the registration policy. Dataspatium
shows this in its source settings and switches features on and off by it.
`/.well-known/kontroll`, the path from before the rename of 2026-11-08, answers
the same and stays as an alias.

Shape (unauthenticated, CORS as for the API, cacheable for five minutes,
never a secret; `bolt` appears only when the operator states a published Bolt
address explicitly with `OPENCDE_GRAPH_PUBLIC_BOLT_URL`; `links.dataspatium`
comes from `OPENCDE_DATASPATIUM_URL`; the administration API is mounted by
`OPENCDE_ADMIN_API_ENABLED` independently of the HTML administration):

```json
{
  "server": {"name": "Dataregium OpenCDE server", "version": "2.0.0", "public_url": "https://cde.example.org"},
  "apis": {"foundation": "1.0", "bcf": "3.0", "documents": "1.0"},
  "scopes": ["profile", "bcf", "documents", "admin"],
  "extensions": {
    "dynamic_client_registration": {"enabled": true, "public_clients": true, "initial_access_token": false, "approval": false, "unused_days": 30,
                                    "url": "/foundation/oauth2/reg"},
    "request_log": {"enabled": true, "retention_hours": 72, "url": "/admin/api/requests"},
    "admin_api": {"enabled": true, "version": 1, "url": "/admin/api", "scope": "admin"},
    "ifcgraph": {"enabled": true, "bolt": null},
    "graph_query": {"enabled": false}
  },
  "limits": {"max_upload_bytes": 104857600, "max_image_bytes": 10485760, "access_token_ttl_seconds": 3600},
  "links": {"dataspatium": null}
}
```

`version` under `admin_api` counts breaking changes of that extension;
`links.dataspatium` carries the app's address when the operator sets it.
Clients treat unknown keys as absent.

## Which app registered

RFC 7591 lets a client send `software_id` and `software_version`. Dataspatium
sends them when it registers; Dataregium stores them on the `Client` node, echoes
them in the registration response and shows them on the clients page and in
`opencde client list`, so the operator can tell app versions apart when
debugging.

## Graph access in production

Only the development overlay publishes Bolt. In production the IFC graph can be
reached in two ways (decision A): the `compose.bolt.yaml` overlay for operators
who publish the port on purpose, and `POST /admin/api/graph/query`
(`OPENCDE_GRAPH_QUERY_ENABLED`, off by default) for administrators holding the
`admin` scope: one reading statement in a read transaction, answered as
`{columns, rows, truncated}` with nodes `{identity, labels, properties}`,
relationships `{identity, type, start, end, properties}` and paths `{nodes,
relationships, length}`, within `max_rows` and `timeout_seconds` that the
capabilities document announces (`extensions.graph_query`).

The endpoint is for administrators (the Administration tab's "Graph query"
card), not per project, so the "starts at the user node" rule is replaced by the
administrator fences: writing clauses and non-schema procedures refused,
protected properties refused and kept out of answers, every call audited. The
answer is tabular, and Dataspatium builds graphs from tables itself.
`docs/client-guide.md` §7.

### The form of the IFC graph

From 3.0.0 a model is converted so that the file can be written back (ADR 0010). The nodes, relationships and values of
the earlier form are all there, so queries written for it keep working. Added to them:

- `position` on the relationships of forward attributes, an integer or `[row, column]`. Inverse relationships have none.
- `<attribute>__type` beside a typed value, such as `NominalValue__type: "IFCLABEL"`.
- `<attribute>__step` for a reference to what is no node, such as `Representation__step: 1234`.
- JSON text in a property for a list of lists, and tagged JSON with `$json` in `<attribute>__type` for what has no plain form.
- `IfcModel.lossless` and `IfcModel.ifc_header`.
- `(:IfcModel)-[:HAS_STEP_BLOCK]->(:StepBlock)`, whose `text` is up to about 100 KB. A query that returns any node whole, or
  walks everything hanging off a model, should leave it out.

Anything that lists a node's properties sees these. `OPENCDE_IFC_LPG_LOSSLESS=false` gives the earlier form.

### Checks of a model

The owner divided the checks on 2026-11-07. Dataregium checks every uploaded IFC file against the IFC schema, since the
answer belongs to the file and is the same for everyone. Dataspatium runs the checks a person chooses: IDS with
ifctester, and clash detection. Findings that are to be followed up go to the server as BCF topics. Later the same day
the owner added buildingSMART's ifc-gherkin-rules to the upload check (ADR 0012), an IDS check on the server too, and
clash detection on both sides: IfcClash on the server and Dataspatium's own core, to become `marwiss/ifc-clash-js`.

From 3.0.0 the version's metadata carries `ifc_validation_status` (`pending`, `passed`, `warnings`, `issues`,
`unknown`), and once the file is checked `ifc_validation_issues`, `ifc_validation_checked_at`, `ifc_validation_ruleset`
(one value per check) and `ifc_validation_report`. `warnings` means every finding is a warning, which buildingSMART's
validation service holds valid; `issues` means at least one error. The report is
`GET /documents/1.0/documents/{id}/versions/{index}/ifc-validation`, with the same bearer token as the Documents API, on
the API's own origin. Its shape is stable: `status`, `checked_at`, `ruleset`, `issue_count`, `error_count`,
`truncated`, `checks` (each with `name`, `state`, `ruleset`, `issue_count` and `rules_not_run`), and `issues`, each
with `kind`, `severity`, `message`, and where known `rule`, `step_id`, `global_id` and `attribute`.
[ifc-lpg.md](ifc-lpg.md) has an example, and ADR 0011 and ADR 0012 the reasons.

## Languages and glossary

Both projects exist in seven languages, with Norwegian in both Bokmål and
Nynorsk. They share the mechanics: flat dictionaries with dotted keys, `{name}`
parameters and `docs/<lang>/` folders. One glossary of shared terms (project,
topic, viewpoint, document, version, client, scope, request id …), whose source
is Dataspatium's `presets/i18n-shared.json`, means that a user moving between the
app and the server's pages meets the same words.

In Dataregium the pages exist in the seven languages, and so does the documentation
(English under `docs/`, the others under `docs/<lang>/`; the project logs, the
ADRs and the upstream drafts stay in English, and `tests/unit/test_docs.py` keeps
the translations in step with the source). Dataspatium's links to Dataregium's pages
go to `docs/<lang>/`.

## One look

The owner decided that one look applies to both products and that it is
Dataspatium's: the same font (Inter, self-hosted in Dataregium under the SIL
Open Font License), type scale, weights, 4 px spacing scale, radii, shadows,
light and dark colours, status colours, control sizes (32 px buttons and
fields, 44 px touch targets below 760 px) and component looks. As the
copyright holder of Dataspatium the owner permitted Dataregium to use that
design despite the different licences, so Dataregium's `tokens.css` carries
Dataspatium's tokens with the same `--dm-*` names, and `base.css` and
`components.css` express Dataspatium's components (`dm-button`, `.dm-field`,
`dm-badge`, `dm-table`, `.dm-list-item`, `dialog.dm-dialog`, `.dm-toast`) on
the server's plain HTML classes. Dataspatium's style rules apply too: one
primary button per view, danger actions confirmed in a dialog, tabular
numbers, dates as `YYYY-MM-DD` and times as `HH:MM`, keyboard reachability,
reduced motion respected. The source of the design stays Dataspatium; when
its tokens change, Dataregium's follow.

## Error codes

The server keeps one error body, the Foundation API's `{"message": …}`, and adds
a stable `code` field where a client must react (`docs/client-guide.md` §6). The
app translates the codes. There is no second error format.

## Test data

Dataregium's seed stores `tests/fixtures/three_walls_gtin.ifc` (three walls with
`Reuse`/`GTIN` 1–3 and known GlobalIds) as a document and creates a topic,
viewpoint and comment with fixed ids (`docs/client-guide.md` §7, inventory §9),
so runs against the seed know what to expect.

## Deep links

`OPENCDE_DATASPATIUM_URL` gives the server's project and document pages an "Open
in Dataspatium" link, also for workspace packages (`.dataspatium.zip`), with the
app's route `#/inhamta/opencde?server=…&project=…&document=…&version=…`.

## Releases

The two projects take the same release numbers in lockstep (decision C): every
Dataspatium release gets a Dataregium release with the same number the same day,
even when the server change is small. `CHANGELOG.md` lists the client-visible
changes, every README says which Dataspatium this Dataregium works with, and
Dataregium's release workflow builds the image and the SBOM on a tag. Only the
latest release per major number is kept: the next release removes the previous
release and its tag, the commits stay, and `CHANGELOG.md` folds the notes
together. When a new major number begins, the last release of the old one is made
again as X.0.0, by a commit that sets the number, with a branch `release-X` at it, on
the owner's word. No history is rewritten. Dataspatium's 1.0.0 and both projects'
2.0.0 came about this way.

### The checklist of a joint release

The same steps on both sides, in this order, under the same number on the same day:

| Step | Kontroll | Dataspatium |
|---|---|---|
| The version | `pyproject.toml`, `opencde/__init__.py`, `client/pyproject.toml`, `client/opencde_client/__init__.py` and `uv.lock`; the number in the READMEs, `docs/client-guide.md` and `docs/deploy/vps-caddy.md` in every language | `src/platform/registry.js` and `sw-coi.js`; the number in the READMEs |
| The notes | `## Unreleased` in `CHANGELOG.md` is folded in under the number | The release notes |
| Each other | `DATASPATIUM_REF` in `dataspatium-nightly.yml` is the other side's new commit; the READMEs say which release works with which | The READMEs say the same |
| The tests | CI and both nightly jobs are green on the commit | The test matrix: Edge and Firefox from `file://`, the ZIP, Pages, localhost with real Python |
| The tag | `vX.Y.Z` builds the image and the SBOM (`release.yml`) | `vX.Y.Z` builds the ZIP |
| What was published | Pull the image and start it: `/readyz` answers and `/healthz` has the number | Download the ZIP and try it, and try Pages |
| The record | A row in `docs/acceptance.md` for the pair's run on the tag | `docs/help/*.js` is regenerated (`tools/wrap_local.py`), since it embeds the quick start |
| In words | Notes in Swedish and English on the release | The same |
| The one before | The previous release of the major number and its tag go; the commits stay | The same |

## Tests across the repositories

The live suite runs on the owner's machine against the local stack, and
`.github/workflows/dataspatium-nightly.yml` runs it in CI, nightly and on demand,
so a server change that breaks the app (or the reverse) shows up before a release.
The job checks out the paired Dataspatium release (`DATASPATIUM_REF`, the same
number as this server), starts the development stack with demo data, the IFC
graph, dynamic registration and the request log, registers a public client
for `http://127.0.0.1:8080/oauth-callback.html`, serves Dataspatium with
`python3 -m http.server`, starts `tools/cde-helper.py` as the user
(`officer` from the seed) and as the administrator, and runs
`tools/run-tests.sh` headless in Chromium with the `DATASPATIUM_CDE_*`
parameters. It requires a `DATASPATIUM-TESTS: pass=N fail=0` line, so a run that
tests nothing fails.

## The joint quick start

`docs/quickstart.md` here and `docs/snabbstart.md` there are the same text in
seven languages, apart from the links and the line that names the other
repository: install Dataregium locally, serve Dataspatium, register the app, open
the demo project, create an issue from the 3D view, see it in the server's audit
and request logs.

## Specification quirks

Dataregium's inventory records where the OpenCDE specifications are silent or
inconsistent and what the server does. Dataspatium meets the same questions
from the client side (file names, `ifc_project`, display fields, event
actions). Both sides report to one list, in inventory §10 with the client's view
added, which is also what the upstream issue to IfcOpenShell cites.

## BCFzip and workspace packages

Dataspatium exports and imports BCFzip itself and stores workspace packages as
Documents API documents, so the server has no BCFzip export of its own.

## Security and personal data

What the app keeps in the browser and what the server stores, and for how long,
is described in two halves, cross-linked in each language:
`docs/security/personal-data.md` here and `docs/sakerhet.md` there.

## The administration API

`/admin/api/` is a JSON administration API in the shape of the resource list
Dataspatium wrote (read: overview, users, projects, clients,
sessions, audit, settings, health; write: users, projects and members, clients
and secrets, sessions; dangerous actions behind a fresh sign-in; one-time values
returned once). `docs/client-guide.md` §7 documents it and
`tests/integration/test_admin_api*.py` tests it. The agreed details:

- Errors keep the server's `{"message", "code"}` body.
- The overview is flat (`users`, `projects`, `clients`, `sessions`, `topics`,
  `documents`, `models`, `request_log{enabled, rows}`, `version`, `uptime_s`,
  `dialect`, `graph_ok`).
- A user carries `name` (`full_name` is accepted in bodies too) and
  `projects: [{project_id, role}]`; a project carries its `members` inline and a
  `models` count; a client says `public`.
- Sessions are two kinds in one list (`kind: "oauth2"` refresh-token families and
  `kind: "web"` browser sessions), with an `id` that
  `DELETE /admin/api/sessions/{id}` accepts for either kind, plus
  `DELETE /admin/api/sessions?user=`.
- The settings are structured with the raw `OPENCDE_*` values under `raw`; `PUT`
  and `PATCH` are both accepted; the password reset is `POST …/reset-password`
  and the secret rotation `POST …/rotate-secret`; a created user without a given
  password answers `initial_password` once.
- "Fresh" means a recent *authentication*, not a recent token, since a refresh
  issues new tokens without the user. `auth_time` is recorded on the authorization
  code and carried through the token family; dangerous actions require `auth_time`
  within ten minutes and otherwise answer 403 with
  `code: reauthentication_required`, which the app meets with a new authorization
  (popup).
- Lists answer `{"items": [...], "total": n}` with `limit` (default 200, at most
  1000) and `since`/`q` where they apply; audit events carry the request id of the
  request that caused them, users have `last_sign_in_at` and clients
  `last_used_at`.
- The API is served independently of the HTML administration
  (`OPENCDE_ADMIN_API_ENABLED`, default on when the admin UI is on) and is
  described in the capabilities document, so the app shows its Administration tab
  only where the API exists.
- Resource names and field names follow the existing pages and the inventory; the
  OpenAPI document lists the API under the tag "Administration (extension)".

## BCF API 2.1

The owner decided on 2026-11-06 that a client that implements only 2.1 must be able to connect, and that Dataspatium
and the Python client speak 2.1 too, so that it is tried from both ends. The
reasoning is in [ADR 0008](adr/0008-bcf-api-2-1-next-to-3-0.md). This is what the server promises, everything under
`/bcf/2.1` unless it says otherwise, and on the same data as 3.0.

| What | What a client of 2.1 gets |
|---|---|
| Which versions | `GET /foundation/versions` has two `bcf` entries, 3.0 first, each with its own `api_base_url`. `GET /bcf/versions` has the same two. A server of 2.1 alone has no Foundation API: `/foundation/versions` is a 404, and its entries may have only `version_id` and `detailed_version` |
| Where to sign in | `GET /bcf/2.1/auth`: the same `oauth2_auth_url`, `oauth2_token_url` and `oauth2_revocation_url` as the Foundation API, and `oauth2_pkce_methods`, but no `oauth2_pkce_required`. `oauth2_dynamic_client_reg_url` is `/bcf/2.1/oauth2/reg` when registration is on |
| Clients and tokens | The same for both versions. A public client with PKCE works on 2.1 as on 3.0, and a token from one works on the other |
| The user | `GET /bcf/2.1/current-user`: `{id, name}` |
| Projects | As in 3.0 |
| Extensions | `user_id_type` for `users` |
| Topics | No `server_assigned_id` in any answer. `guid` in a request is ignored. `$filter` also takes `contains(labels, 'x')`. Otherwise as in 3.0, `includeAuthorization` and OData included |
| A topic's header files | `GET` and `PUT .../files` with `file_name` for `filename` |
| The project's files | No `files_information`: it is a 404. `GET .../documents` lists `[{guid, filename}]`, the BCF documents only. What came through the Documents API is not listed in 2.1, but the Documents API itself works as ever, whichever version of BCF is in use |
| Documents | `POST .../documents` and `GET .../documents/{guid}` as in 3.0 |
| Document references | `GET`, `POST` and `PUT .../document_references`, with exactly one of `document_guid` and `url`. `document_guid` is a BCF document of the project or a Documents API `document_id`, as in 3.0. `guid` in a request is ignored |
| Comments | `reply_to_comment_guid` in `POST`, `PUT` and every answer. It must be a comment of the same topic, or the answer is 400. A `PUT` without it clears it. 3.0 neither shows nor changes it. Deleting the comment answered clears it |
| Creating a viewpoint | `guid` is ignored. A camera needs no `aspect_ratio`, and it is kept if sent. A colour may start with `#`. Anything may be left out, but two cameras are a 400 |
| Reading a viewpoint | No `aspect_ratio` and no `authorization`, and `includeAuthorization` does nothing. 3.0 reads `aspect_ratio` as 1.0 when 2.1 left it out |
| Snapshots and bitmaps | As in 3.0: base64 in the viewpoint's `POST`, `{snapshot_type}` and `bitmaps[]` without data in its answers, and the files at `GET .../snapshot` and `GET .../bitmaps/{guid}` with `Content-Type` `image/png` or `image/jpeg` |
| Components | `GET .../selection`, `.../coloring` and `.../visibility` as in 3.0. Colours come without `#`, in upper case |
| Deleting a viewpoint | Not in 2.1: a 405 |
| Related topics | As in 3.0 |
| Events | The same addresses, without the `stage_*` types and with `reply_to_comment_updated` and `reply_to_comment_removed`. An event with no action left in a version is not listed in it, so the counts can differ between the versions |
| Errors | The same body and codes as 3.0 |

A client may also do what Dataspatium does, and the server takes it: fall back to `GET /bcf/versions` when
`/foundation/versions` gives no readable answer at all, not only on a 404, since a server may have CORS headers on its APIs
alone; sign in without a `scope`, which gives the default scopes; and take the address from `api_base_url`.

Outside 2.1 itself, `GET /.well-known/dataregium` has `bcf_versions: ["3.0", "2.1"]`, and `apis.bcf` goes on saying `3.0`.
The administration API's clients have `pkce_optional`, in its answers and in `POST` and `PATCH /admin/api/clients`.

## Decisions by the owner

All four were taken on 2026-11-05.

- **A. Graph access in production**: the server-side read-only query endpoint,
  which keeps the database private and the authorization model, and in addition
  it must be *possible* to open the database port in production, closed by default
  and only by an explicit administrator action: the `compose.bolt.yaml` overlay
  publishes Bolt with TLS from certificates the administrator provides,
  `OPENCDE_GRAPH_PUBLIC_BOLT_URL` announces the address in the capabilities
  document (`extensions.ifcgraph.bolt`), the settings page shows it, and production
  refuses a published address without TLS. The community editions of Neo4j and
  Memgraph have no read-only database users, so an open port gives full access to
  whoever holds the database password; the deployment guide says so.
- **B. Licences and bundling**: Dataregium stays AGPL-3.0-or-later and Dataspatium
  PolyForm Strict. Nothing stops them from working together over the network.
  There is no one-command install of both: users of either product download and
  install the other separately, so both READMEs and the joint quick start explain
  how to get the other one. Dataregium never bundles Dataspatium; Dataspatium may
  bundle or download Dataregium (the AGPL allows redistribution with source), which
  is that project's choice. The owner, who holds the copyright of both projects,
  gave two permissions: Dataregium may use Dataspatium's design (the tokens are
  carried over as they are, under Dataregium's licence), and Dataspatium may use all
  of Dataregium's own code and resources under its licence (the quick start and the
  sample model move over verbatim). Third-party material (specification files, the
  Inter font, dependencies) keeps its own terms. Both repositories say so:
  `CONTRIBUTING.md` here, `docs/licenser.md` there.
- **C. Release numbers**: Dataspatium's release history was consolidated to one
  release per major number, with the other releases and tags removed and the
  history untouched. Dataregium takes **the same release numbers as Dataspatium**, in
  lockstep, starting at `v2.0.0`, and mirrors the rule of one release per major
  number. The same number means the two work together. The owner's acceptance runs
  and the OAuch/testssl runs are the gate for a production deployment, not for a
  tag.
- **D. Capabilities document**: the shape above, a well-known path outside the
  specifications, is confirmed.
