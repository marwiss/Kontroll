# Coordinating Kontroll and Dataspatium

Kontroll (this server) and [Dataspatium](https://github.com/marwiss/Dataspatium)
(the browser app) are developed to work together. This page lists what the
two projects already share, what more could be coordinated, in which order,
and which decisions the owner has to take. It is a working plan, kept in sync
with Dataspatium's own release plan; the counterpart on the app side is its
`docs/utveckling.md` ("Prov mot Kontroll") and the release notes.

## What is coordinated today (2026-11-05)

| Area | State |
|---|---|
| Protocol | Dataspatium talks to Kontroll only through the three OpenCDE APIs, plus two marked extensions: Cypher over Bolt against the IFC graph (when the operator exposes it) and the administration API (`/admin/api/requests`, scope `admin`) |
| Sign-in | OAuth2 authorization code with PKCE as a public client; self-registration through RFC 7591 (`token_endpoint_auth_method: "none"`) when the server allows it; one registration per installation, unused registrations expire |
| Correlation | `X-Request-ID` on every call from the app, echoed by the server and kept in its request log |
| Testing | Dataspatium's live suites (2.28–2.32) run against Kontroll's development stack; results and server findings are recorded in [acceptance.md](acceptance.md); server bugs found this way are fixed the same day |
| Documentation | A shared section "Kontroll and Dataspatium" in both READMEs (Dataspatium's in six languages), cross-references from the guides on both sides |
| Branding | Sibling marks: Dataspatium's stacked sheets (D) and Kontroll's connected nodes, same plate, stroke and margins |
| Working agreements | Announce heavy local runs to the other session; non-release commits in Dataspatium from this project; no git operations in the other checkout; findings reported with request ids |

## Opportunities

Ordered by value for the pair against effort. "K" marks work in Kontroll,
"D" work in Dataspatium.

### 1. Make the server describe itself to the app (K, small) — done 2026-11-05

Dataspatium had to guess which extensions a Kontroll server offers (request
log, administration API, IFC graph, dynamic registration, graph access). A
small capabilities document lets the app adapt instead of probing:
`GET /.well-known/kontroll` (outside the specifications, no auth) listing
the server version, the enabled extensions and their versions, the retention
of the request log, whether Bolt is published, and the registration policy.
Dataspatium shows this in its source settings and switches features on and
off by it. Pairs with a first tagged Kontroll release (item 6).

Shape (unauthenticated, CORS as for the API, cacheable for five minutes,
never a secret; `bolt` appears only when the operator states a published Bolt
address explicitly with `OPENCDE_GRAPH_PUBLIC_BOLT_URL`; `links.dataspatium`
comes from `OPENCDE_DATASPATIUM_URL`; the administration API is mounted by
`OPENCDE_ADMIN_API_ENABLED` independently of the HTML administration):

```json
{
  "server": {"name": "Kontroll OpenCDE server", "version": "0.1.0", "public_url": "https://cde.example.org"},
  "apis": {"foundation": "1.0", "bcf": "3.0", "documents": "1.0"},
  "scopes": ["profile", "bcf", "documents", "admin"],
  "extensions": {
    "dynamic_client_registration": {"enabled": true, "public_clients": true, "unused_days": 30,
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
`links.dataspatium` carries the app's address when the operator sets it
(item 7, deep links). Clients treat unknown keys as absent.

### 2. Say which app registered (D + K, small) — server side done 2026-11-05

RFC 7591 lets a client send `software_id` and `software_version`. Dataspatium
sends them when it registers (2.33); Kontroll stores them on the `Client`
node, echoes them in the registration response and shows them on the clients
page and in `opencde client list`, so the operator can tell app versions
apart when debugging.

### 3. Graph access in production (K, medium; D, small)

Kontroll III queries the IFC graph over Bolt, which only the development
overlay publishes. Production needs either an operator who exposes Bolt behind
TLS with a read-only database user, or a server-side query endpoint: a
read-only Cypher endpoint under the administration API, limited to the
caller's projects, with the `graph` scope, a statement allow-list and a time
limit. The second keeps the "every query starts at the user node" rule and
needs no open database port. Decision for the owner (item A below).

### 4. One language layer, one glossary (K + D, medium)

Both projects are to exist in six languages. Dataspatium already has the
mechanics (flat dictionaries with dotted keys, `{name}` parameters, a glossary
in its style guide, `docs/<lang>/` folders re-embedded by a script). Kontroll
adopts the same key style for its templates and the same folder layout for
its documentation, and the two projects keep one glossary of shared terms
(project, topic, viewpoint, document, version, client, scope, request id …)
so that a user moving between the app and the server's pages meets the same
words. Planned as Dataspatium's "uniformity" release (2.34); Kontroll builds
the language layer and the translations, Dataspatium delivers the glossary
and the tokens.

### 5. One look (K, small) — accent done 2026-11-05, tokens with item 4

The marks share the blue `#2b6cb0`, and since 2026-11-05 Kontroll's pages
use it as their accent too (`tokens.css`: `#2b6cb0`, hover `#245c96`, soft
`#e6effa`, a lighter blue in dark mode, focus ring from the same hue) instead
of the earlier teal. Still to do with item 4: align the type scale and radii
with Dataspatium's tokens where they differ for no reason. The two projects
stay separate code bases (different licences, see item B), so token values are
re-stated as facts, not copied as files.

### 6. Releases that can be matched (K, small; D, small)

Kontroll has no tagged release yet (`0.1.0.dev0`); Dataspatium releases
weekly. A first tagged Kontroll release, a changelog that lists client-visible
changes, and a compatibility line in both READMEs ("Dataspatium 2.32 or later
works with Kontroll 0.1 or later") let users and the live suites pin what
goes together. Kontroll's release workflow already builds the image and the
SBOM on a tag.

### 7. Cross-repository tests in CI (D, medium; K, small)

Today the live suites run on the owner's machine against the local stack.
Dataspatium's CI could start Kontroll's published image with the development
overlay, seed it, and run the live suite headless, so a server change that
breaks the app (or the reverse) shows up before a release. Kontroll's side:
a `compose` profile and a seed option with a fixed demo password for CI, both
already present in the nightly ZAP job, and the image tag to pin.

### 8. A joint quick start (K + D, small)

One page, the same in both repositories (and their languages): install
Kontroll locally, serve Dataspatium, register the app, open the demo project,
create an issue from the 3D view, see it in the server's audit and request
logs. The pieces exist in `docs/deploy/local.md`, `docs/acceptance.md` and
Dataspatium's `utveckling.md`; the quick start strings them together for a
newcomer.

### 9. Spec quirks reported from both sides (process, small)

Kontroll's inventory records where the OpenCDE specifications are silent or
inconsistent and what the server does. Dataspatium meets the same questions
from the client side (file names, `ifc_project`, display fields, event
actions). One list, kept in Kontroll's inventory §10 with the client's view
added, is also what the upstream issue to IfcOpenShell should cite.

### 10. BCFzip and workspace packages (D now; K later, optional)

Dataspatium exports and imports BCFzip itself and stores workspace packages
as Documents API documents, so no server work is needed today. If several
clients want BCFzip from the server (an export of a project's topics as one
file), that becomes a marked extension in Kontroll; not before a second
client asks.

### 11. The inspection-plan domain (K later, D later)

Kontroll's reason to exist is a later Kontrollplan API (inspection plans
for building permits) on top of the OpenCDE server; Dataspatium would be its
first client (plans as documents, checkpoints as topics, reviewers as the
`Reviewer` node, reports through its document generator). When that API is
designed, the data model should be reviewed by both sides before the first
endpoint, and Dataspatium's document templates should be able to render it.

### 12. The administration API (K, medium; D, medium) — Dataspatium 2.35

Dataspatium has proposed the shape of a JSON administration API under
`/admin/api/` from the client side (read: overview, users, projects, clients,
sessions, audit, settings, health; write: users, projects and members,
clients and secrets, sessions; dangerous actions behind a fresh sign-in;
one-time values returned once). Kontroll's position, to be settled before
either side writes code:

- Keep one error body for the whole server, the Foundation API's
  `{"message": …}`, and add a stable `code` field where a client must react
  (`"code": "reauthentication_required"`), rather than a second format
  (RFC 9457) for one prefix.
- "Fresh" must mean a recent *authentication*, not a recent token: a refresh
  issues new tokens without the user. Kontroll will record `auth_time` on the
  authorization code and carry it through the token family; dangerous
  actions require `auth_time` within ten minutes and otherwise answer 403
  with `code: reauthentication_required`, which the app meets with a new
  authorization (popup). No separate confirmation code is needed.
- Lists answer `{"items": [...], "total": n}` with `limit` (default 200, at
  most 1000) and `since`/`q` where they apply; the audit API gains the
  request id of the request that caused each event, and users get
  `last_sign_in_at`, clients `last_used_at`.
- Sessions are two kinds in one list (`kind: "oauth2"` refresh-token families
  and `kind: "web"` browser sessions), as the page shows them.
- The API is served independently of the HTML administration
  (`OPENCDE_ADMIN_API_ENABLED`, default on when the admin UI is on) and is
  described in the capabilities document of item 1, so the app shows its
  Administration tab only where the API exists.
- Resource names and field names follow the existing pages and the inventory;
  Kontroll documents the API in `docs/client-guide.md` and the OpenAPI
  document under the tag "Administration (extension)".

### Inputs from Dataspatium

Two working documents from the Dataspatium side feed items 4, 5 and 12 (they
live in that project's planning, not in this repository): a "shared look"
sheet with Dataspatium's 95 design variables (light values; dark under
`prefers-color-scheme` and `[data-theme=dark]`), its layout skeleton, writing
rules, glossary ("Datamängd", "Hämta", "Ta bort", "Ångra" …), the language
key style (flat dictionaries, dotted keys per area, `{name}` parameters,
`key.one` for singular, Swedish as the base language) and its Lucide icon
choices; and the administration API proposal summarised above. Kontroll's
language layer will use the same key names where the concepts are shared
(topic, viewpoint, document, project, client, sign in, sign out), the same
icons for the same actions, and the same token names (`--dm-*`) so that a
copied token file needs no translation; whether Kontroll self-hosts the Inter
font or keeps system fonts is part of item 5.

## Agreed order (merged with Dataspatium's plan, §13.2 there)

The two projects drew up their lists independently and merged them on
2026-11-05. The agreed order, with the items above and the additions from
the Dataspatium side:

1. Capabilities document (item 1) + compatibility matrix and the first tagged
   Kontroll release (item 6).
2. Glossary and language keys, with the token file copied under the same
   names (items 4 and 5) — Dataspatium 2.34.
3. Error codes: a stable `code` field in the Foundation `{"message"}` body,
   translated by the app; no second error format. Server side done
   2026-11-05 (thirteen codes, `docs/client-guide.md` §6); the app translates
   them in 2.34.
4. Shared test data: `tests/fixtures/three_walls_gtin.ifc` (three walls with
   `Reuse`/`GTIN` 1–3 and known GlobalIds) becomes the pair's fixture on both
   sides; the seed gets known BCF guids.
5. The pair's CI (item 7): Dataspatium's live suite from its release zip,
   headless, in Kontroll's nightly job; the same job in Dataspatium with a
   pinned server image.
6. Deep links both ways: `OPENCDE_DATASPATIUM_URL` gives the server's project
   and document pages an "Open in Dataspatium" link (also for workspace
   packages, `.dataspatium.zip`), and the app links to the server's detail and
   administration pages.
7. `software_id`/`software_version` at registration (item 2) — Dataspatium
   2.33 sends them.
8. A joint quick start (item 8).
9. The administration API (item 12) — Dataspatium 2.35.
10. The graph query endpoint (item 3) after decision A.
11. A shared security and personal-data page: what the app keeps in the
    browser, what the server stores and for how long, one half each, cross-linked.
12. `CONTRIBUTING.md` in Kontroll and the licence terms of the shared pieces
    (decision B).

Continuously: specification quirks from both sides (item 9). Later: BCFzip on
the server (item 10) and the inspection-plan domain (item 11).

## Decisions for the owner

All four were taken on 2026-11-05.

- **A. Graph access in production**: exposed Bolt with a read-only database
  user, or a server-side read-only query endpoint (item 3). The endpoint is
  more work but keeps the database private and the authorization model.
  Decided: the server-side read-only query endpoint (item 10 of the agreed
  order). Later, the administration UI gets an option for also announcing a
  published Bolt address, so an operator who exposes the database
  deliberately can keep that path open; the capabilities document already
  carries `extensions.ifcgraph.bolt` for it.
- **B. Licences and bundling**: Kontroll is AGPL-3.0-or-later, Dataspatium is
  PolyForm Strict. Nothing stops them from working together over the network,
  but code and assets cannot move between the repositories, and Kontroll's
  compose files cannot bundle Dataspatium. If a one-command install of both
  is wanted, Dataspatium's licence for that purpose has to be decided. The
  pieces the two projects want to share (the token file, the glossary JSON,
  the test model, the quick-start text) would need a separate permissive
  licence (CC0 or MIT) stated in both repositories. Decided: the licences
  stay as they are and no code or assets move between the repositories;
  each project writes its own files with the same values (colour values,
  term lists, test geometry), which are facts, not copies. No one-command
  install of both. Users of either product download and install the other
  separately, so both READMEs and the joint quick start (item 8) explain how
  to get the other one.
- **C. First Kontroll release**: when to tag `v0.1.0` (item 6). The code is
  there; what remains is the owner's acceptance runs A and B
  (`docs/acceptance.md`) and the OAuch/testssl runs before a production
  deployment. Decided: before releases are coordinated across the
  repositories, Dataspatium's release history is consolidated to far fewer
  releases (its `1.0.0` becomes today's `1.18.1`, the latest release of each
  major number stands for that number, and its README describes everything
  the merged releases contained). Settled the same day: one release per
  major number, the other releases and tags removed, the history untouched,
  the app shows 2.0.0 and continues with 2.1.0. Kontroll takes **the same
  release numbers as Dataspatium**, in lockstep: the first tag is `v2.0.0`
  (with `__version__`, `pyproject.toml` and `server.version` in the
  capabilities document at 2.0.0), made when Dataspatium 2.0.0 is out, and
  every later Dataspatium release gets a Kontroll release with the same
  number the same day, even when the server change is small. The
  compatibility line in both READMEs becomes "Dataspatium 2.0.0 works with
  Kontroll 2.0.0": the same number means the two work together. The owner's
  acceptance runs and the OAuch/testssl runs remain the gate for a production
  deployment, not for the tag.
- **D. Capabilities document**: the shape of item 1 (a well-known path outside
  the specifications) was confirmed on 2026-11-05 and is implemented; the
  Dataspatium side builds on it.

## How the plan is kept

This page changes when a decision is taken or an item ships; the Dataspatium
session mirrors the state in its release plan. Items that become work in
Kontroll get the usual treatment: route + schema + tests + docs in one commit
series, an inventory row, and a note here.
