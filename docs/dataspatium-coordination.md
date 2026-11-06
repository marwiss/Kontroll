# Coordinating Kontroll and Dataspatium

Kontroll (this server) and [Dataspatium](https://github.com/marwiss/Dataspatium)
(the browser app) are developed to work together. This page records what the
two projects share, the interfaces and practices they agreed on, and the
decisions the owner took. The counterpart on the app side is its
`docs/utveckling.md` ("Prov mot Kontroll") and the release notes.

## Overview

| Area | State |
|---|---|
| Protocol | Dataspatium talks to Kontroll through the three OpenCDE APIs, plus marked extensions: the capabilities document, the administration API with the request log and the graph query, and Cypher over Bolt against the IFC graph when the operator publishes the port |
| Sign-in | OAuth2 authorization code with PKCE as a public client; self-registration through RFC 7591 (`token_endpoint_auth_method: "none"`) when the server allows it; one registration per installation, unused registrations expire |
| Correlation | `X-Request-ID` on every call from the app, echoed by the server and kept in its request log |
| Testing | Dataspatium's live suite runs against Kontroll's development stack, on the owner's machine and in the nightly pair job; results and server findings are recorded in [acceptance.md](acceptance.md) |
| Documentation | A shared section "Kontroll and Dataspatium" in both READMEs, each in seven languages (English, Swedish, Danish, Norwegian Bokmål and Nynorsk, Finnish, Icelandic), and cross-references from the guides on both sides |
| Branding | Sibling marks: Dataspatium's stacked sheets (D) and Kontroll's connected nodes, same plate, stroke and margins |
| Working agreements | Announce heavy local runs to the other session; non-release commits in Dataspatium from this project; no git operations in the other checkout; findings reported with request ids |

## The capabilities document

Dataspatium does not have to guess which extensions a Kontroll server offers.
`GET /.well-known/kontroll` (outside the specifications, no auth) lists the
server version, the enabled extensions and their versions, the retention of the
request log, whether Bolt is published, and the registration policy. Dataspatium
shows this in its source settings and switches features on and off by it.

Shape (unauthenticated, CORS as for the API, cacheable for five minutes,
never a secret; `bolt` appears only when the operator states a published Bolt
address explicitly with `OPENCDE_GRAPH_PUBLIC_BOLT_URL`; `links.dataspatium`
comes from `OPENCDE_DATASPATIUM_URL`; the administration API is mounted by
`OPENCDE_ADMIN_API_ENABLED` independently of the HTML administration):

```json
{
  "server": {"name": "Kontroll OpenCDE server", "version": "2.0.0", "public_url": "https://cde.example.org"},
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
sends them when it registers; Kontroll stores them on the `Client` node, echoes
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

## Languages and glossary

Both projects exist in seven languages, with Norwegian in both Bokmål and
Nynorsk. They share the mechanics: flat dictionaries with dotted keys, `{name}`
parameters and `docs/<lang>/` folders. One glossary of shared terms (project,
topic, viewpoint, document, version, client, scope, request id …), whose source
is Dataspatium's `presets/i18n-shared.json`, means that a user moving between the
app and the server's pages meets the same words.

In Kontroll the pages exist in the seven languages, and so does the documentation
(English under `docs/`, the others under `docs/<lang>/`; the project logs, the
ADRs and the upstream drafts stay in English, and `tests/unit/test_docs.py` keeps
the translations in step with the source). Dataspatium's links to Kontroll's pages
go to `docs/<lang>/`.

## One look

The owner decided that one look applies to both products and that it is
Dataspatium's: the same font (Inter, self-hosted in Kontroll under the SIL
Open Font License), type scale, weights, 4 px spacing scale, radii, shadows,
light and dark colours, status colours, control sizes (32 px buttons and
fields, 44 px touch targets below 760 px) and component looks. As the
copyright holder of Dataspatium the owner permitted Kontroll to use that
design despite the different licences, so Kontroll's `tokens.css` carries
Dataspatium's tokens with the same `--dm-*` names, and `base.css` and
`components.css` express Dataspatium's components (`dm-button`, `.dm-field`,
`dm-badge`, `dm-table`, `.dm-list-item`, `dialog.dm-dialog`, `.dm-toast`) on
the server's plain HTML classes. Dataspatium's style rules apply too: one
primary button per view, danger actions confirmed in a dialog, tabular
numbers, dates as `YYYY-MM-DD` and times as `HH:MM`, keyboard reachability,
reduced motion respected. The source of the design stays Dataspatium; when
its tokens change, Kontroll's follow.

## Error codes

The server keeps one error body, the Foundation API's `{"message": …}`, and adds
a stable `code` field where a client must react (`docs/client-guide.md` §6). The
app translates the codes. There is no second error format.

## Test data

Kontroll's seed stores `tests/fixtures/three_walls_gtin.ifc` (three walls with
`Reuse`/`GTIN` 1–3 and known GlobalIds) as a document and creates a topic,
viewpoint and comment with fixed ids (`docs/client-guide.md` §7, inventory §9),
so runs against the seed know what to expect.

## Deep links

`OPENCDE_DATASPATIUM_URL` gives the server's project and document pages an "Open
in Dataspatium" link, also for workspace packages (`.dataspatium.zip`), with the
app's route `#/inhamta/opencde?server=…&project=…&document=…&version=…`.

## Releases

The two projects take the same release numbers in lockstep (decision C): every
Dataspatium release gets a Kontroll release with the same number the same day,
even when the server change is small. `CHANGELOG.md` lists the client-visible
changes, every README says which Dataspatium this Kontroll works with, and
Kontroll's release workflow builds the image and the SBOM on a tag. Only the
latest release per major number is kept: the next release removes the previous
release and its tag, the commits stay, and `CHANGELOG.md` folds the notes
together.

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
repository: install Kontroll locally, serve Dataspatium, register the app, open
the demo project, create an issue from the 3D view, see it in the server's audit
and request logs.

## Specification quirks

Kontroll's inventory records where the OpenCDE specifications are silent or
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
Dataspatium wrote for its 2.2.0 (read: overview, users, projects, clients,
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
- **B. Licences and bundling**: Kontroll stays AGPL-3.0-or-later and Dataspatium
  PolyForm Strict. Nothing stops them from working together over the network.
  There is no one-command install of both: users of either product download and
  install the other separately, so both READMEs and the joint quick start explain
  how to get the other one. Kontroll never bundles Dataspatium; Dataspatium may
  bundle or download Kontroll (the AGPL allows redistribution with source), which
  is that project's choice. The owner, who holds the copyright of both projects,
  gave two permissions: Kontroll may use Dataspatium's design (the tokens are
  carried over as they are, under Kontroll's licence), and Dataspatium may use all
  of Kontroll's own code and resources under its licence (the quick start and the
  sample model move over verbatim). Third-party material (specification files, the
  Inter font, dependencies) keeps its own terms. Both repositories say so:
  `CONTRIBUTING.md` here, `docs/licenser.md` there.
- **C. Release numbers**: Dataspatium's release history was consolidated to one
  release per major number, with the other releases and tags removed and the
  history untouched. Kontroll takes **the same release numbers as Dataspatium**, in
  lockstep, starting at `v2.0.0`, and mirrors the rule of one release per major
  number. The same number means the two work together. The owner's acceptance runs
  and the OAuch/testssl runs are the gate for a production deployment, not for a
  tag.
- **D. Capabilities document**: the shape above, a well-known path outside the
  specifications, is confirmed.
