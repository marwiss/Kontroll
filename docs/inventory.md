# Functional inventory: the 2023 prototype and its status in the rewrite

Source of the inventory: the prototype in IfcOpenShell `src/opencdeserver`
(branch `v0.9.0`, commit `da37bea5`) and the previous contents of this
repository, together with the official specifications (`spec/SOURCES.md`).

Status values: **keep** (same function, new code), **reshape** (same purpose,
new design), **drop** (removed, with the reason), **new** (required by the
specification but absent in the prototype). The stage column refers to the
project plan. This file is updated with every stage.

## Progress

| Stage | Content | Status |
|---|---|---|
| 0 | Repository, scaffold, CI, Docker, security baseline | done |
| 1 | Graph core (dialects, schema, cleanup), accounts, OAuth2 clients, OData compiler, storage, audit log, rate limiting, ETag, CLI | done |
| 2 | Foundation API and OAuth2 (PKCE, rotating refresh tokens, revocation, dynamic registration), design system, sign-in page | done |
| 3 | BCF API: projects, extensions, topics, topic events, authorization objects | done |
| 4 | BCF API: comments, viewpoints, related topics, document references, files, snippets, documents, comment events | |
| 5 | Documents API | |
| 6 | Admin UI | |
| 7 | Client library and end-to-end tests | |
| 8 | Deployment | |
| 9 | IFC-graph | |
| 10 | Visual acceptance, Dataspatium | |
| 11 | Hardening, documentation, upstream preparation | |

## 1. Foundation API 1.0

| Function | Prototype | Status | Stage |
|---|---|---|---|
| `GET /foundation/versions` | yes | keep; lists foundation, bcf, documents with `api_base_url` | 2 |
| `GET /foundation/1.0/auth` | yes, claimed HTTP Basic | keep; `http_basic_supported: false`, `oauth2_dynamic_client_reg_url` when enabled | 2 |
| `GET /foundation/1.0/current-user` | returned internal user fields | keep; `id` and `name` per `user_GET.json` | 2 |
| Authorization endpoint (sign-in and consent page) | `GET /foundation/oauth2/auth` + `GET .../code` with password in the URL | reshape: `GET` renders the page, `POST` verifies and redirects (302) with `code`, `state`, `iss`; PKCE S256 required | 2 |
| Token endpoint | `POST /foundation/oauth2/token`, JWT, non-expiring | reshape: opaque hashed tokens, one-time rotating refresh tokens, 201, `Cache-Control: no-store` | 2 |
| Dynamic client registration (spec 2.2.3) | commented out | new; off by default | 2 |
| Token revocation (RFC 7009) | no | new (extension) | 2 |
| Single hard-coded client from environment variables | yes | reshape: clients in the graph, managed by CLI and admin UI | 2, 6 |
| Scopes `test`, `user`, `admin`, undocumented `test` required everywhere | yes | reshape: server-defined scopes per route | 2 |
| Legacy aliases `GET /bcf/versions`, `/bcf/3.0/auth`, `/bcf/3.0/current-user` | commented out | keep as thin aliases (clients such as openBCF use them) | 2 |

## 2. BCF API 3.0 (40 operations in the specification)

| Function | Prototype | Status | Stage |
|---|---|---|---|
| Projects: list, get, put | yes | keep, with `authorization.project_actions` | 3 |
| Extensions (incl. custom values) | yes | keep | 3 |
| Topics: list, post, get, put, delete | yes; no OData, no labels/reference_links/bim_snippet persisted, Neo4j internal id as `server_assigned_id` | keep; OData `$filter/$orderby/$top/$skip` incl. `labels/any()`, all fields, validation against extensions, 409 on duplicate guid, project-unique readable `server_assigned_id` | 3 |
| `includeAuthorization=true` (spec 1.2.1) | no | new | 3 |
| BIM snippet get/put | routes only | keep and implement | 4 |
| Files information (`open-cde-documents://`) | yes, broken URL rewrite | keep | 4 |
| Files header get/put | yes, first file only | keep | 4 |
| Comments: list, post, get, put, delete | yes; `viewpoint_guid` never returned, reply guid disabled | keep; replies, viewpoint link, OData on `author`/`date` | 4 |
| Viewpoints: list, post, get, snapshot, bitmaps, selection, coloring, visibility, delete | yes, many defects (optional parts crashed, JPEG mismatch, colour grouping) | keep; both cameras, lines, clipping planes, bitmaps, components, PNG and JPEG | 4 |
| Related topics get/put | yes, invalid Cypher | keep; PUT replaces the list | 4 |
| Document references get/post/put | yes, invalid Cypher | keep; `document_guid` or external `url` | 4 |
| Documents: list, post, get | stubs returning `True` | keep and implement; `?guid=` with 409 | 4 |
| Topic events, topic events by topic | stubs; routes shadowed by `/topics/{id}` | implemented; 17 event types, several actions per event, events outlive the topic, OData on `topic_guid`/`author`/`date`/`type` | 3 |
| Comment events, comment events by comment | stubs | keep and implement; 4 comment event types, OData | 4 |
| Per-entity `authorization` objects | no | new | 3, 4 |
| ETag / If-None-Match on GET | no | new | 1, 3 |

## 3. Documents API 1.0 (13 operations in the specification)

| Function | Prototype | Status | Stage |
|---|---|---|---|
| `POST upload-documents` | yes | keep | 5 |
| Upload metadata page (`document-upload`) | yes, AJAX callback | reshape: form POST, 302 to callback with `upload_documents_url` or `user_cancelled_upload=true` | 5 |
| Upload instructions (`upload-documents-url`) | yes | keep; parts with content ranges, `include_authorization` | 5 |
| Upload file part `POST` | yes, whole body in memory | keep; streaming with byte counting and limits | 5 |
| Upload file part `PUT` | no | new | 5 |
| Upload completion / cancellation | per session, swallowed errors | keep; per file, SHA-256 check, keep-alive whitespace | 5 |
| `POST document-versions` (aggregate query) | bare list in and out, always version 1 | keep; `DocumentQuery`/`DocumentQueryResult`, `ETag`/`If-None-Match` → 304 | 5 |
| `POST select-documents` | yes | keep | 5 |
| Selection page (`document-selection`) | yes, AJAX callback | reshape: form POST, 302 with `selected_documents_url` or `user_cancelled_selection=true`, filter on `supported_file_extensions` | 5 |
| Selected documents (`download-instructions`) | yes, not bound to the user | keep; bound to the user's session | 5 |
| Document version, metadata, download, versions | yes; inverted version filter, fixed filename | keep; strict `DocumentVersion` body | 5 |
| Document details page | route without template | keep | 5 |
| Custom upload from the selection page (`upload_file_to_project`) | yes, unauthenticated | keep; authenticated, server-generated ids | 5 |
| `/user/1.0/*` duplicate router | never mounted | drop: dead code | – |

## 4. Other server functions

| Function | Prototype | Status | Stage |
|---|---|---|---|
| Start page `/` | sign-in form | keep: index with links to docs (stage 0 returns JSON) | 0, 2 |
| `/favicon.ico` from a file outside the repo | yes | keep; icon in the repo | 2 |
| OpenAPI with tags and descriptions | yes | keep; descriptions from the specification | 0 |
| CORS for all origins with credentials | yes | reshape: configurable origins, Bearer only, never credentials | 0 |
| Request/response body logging to a file | yes | reshape: structured logs with request id and redaction, no bodies | 0 |
| `debug()` prints with jsonpickle | yes | drop: structured logging | 0 |
| Liveness and readiness endpoints | no | new: `/healthz`, `/readyz` | 0 |
| Web admin UI (users, clients, projects, audit log) | no (README TODO) | new | 6 |
| CLI (`init`, `doctor`, `seed`, `cleanup`, `user`, `project`, `client`; `backup`/`restore` and `revoke` follow) | no | new; done except backup and revoke | 0, 1, 8 |
| Expiry of codes, tokens and sessions (prototype: APOC TTL) | APOC | reshape: `expires_at` + server-side cleanup, done | 1 |
| OData `$filter/$orderby/$top/$skip` (prototype: none) | no | new: whitelist compiler to Cypher, done | 1 |

## 5. Data model

| Prototype | Status |
|---|---|
| `User` with role labels (Admin, Officer, Developer, Auditor, Tester), `hashed_password` (bcrypt) | keep; roles as `MEMBER_OF {role}` relationships, Argon2id |
| Five test users named after the roles in a building-permit process (administrator, municipal building officer, developer, inspection manager, inspector) | keep in seed data with English user names; passwords generated at seed time, printed once |
| `Municipality`, `Building` | keep in seed data as inspection-plan context |
| Two projects, a building permit and a demolition permit, with `Extensions` | keep, with English names |
| `HAS_ACTIONS_ON` relationship with boolean flags | reshape: role → spec `*_actions` enums |
| `Document` node with version fields | reshape: `Document` + `DocumentVersion`, SHA-256 |
| `Topic`, `Comment`, `Viewpoint`, `Component` (`GTIN`), `Line`, `ClippingPlane`, `Bitmap`, `SAME_AS` → `IfcProduct` | keep, with unique constraints; `Event` and `AuditEvent` nodes added |
| Sessions, parts and links expiring through APOC TTL | reshape: `expires_at` property and a server-side cleanup job |
| Tokens stored as JWT text plus MD5 | reshape: SHA-256 hashes only, `family_id` on refresh tokens |
| `Process` node (undefined) | drop; belongs to the later inspection-plan API |
| Database wiped and re-seeded at every start | drop: seeding only on demand into an empty database |

## 6. Security and configuration

| Prototype | Status |
|---|---|
| JWT HS256 with a secret key, `expires` claim never checked | reshape: opaque tokens, no signing key |
| passlib + bcrypt | reshape: pwdlib + Argon2id |
| Secrets from `/run/secrets` with fixed names | reshape: pydantic-settings, `OPENCDE_*` variables, Docker secrets, `opencde init` generates them |
| `.env` with `NEO4J_*`, `KONTROLL_*`, `SECURITY_*`, `SESSION_*` | reshape: `OPENCDE_*` with the same meanings and safer defaults |
| Neo4j 5.7 with APOC, database ports published, 4-character passwords | reshape: Neo4j 5.26 LTS, no APOC, private network, 16-character minimum |
| Python 3.10 image with `ifcopenshell.zip`, pip | reshape: Python 3.13 slim image, uv lockfile, IfcOpenShell from PyPI as optional extra, non-root, read-only |
| `restart.sh` | drop: `docker compose` |

## 7. IFC-graph

| Prototype | Status | Stage |
|---|---|---|
| One node per IFC entity with the class hierarchy as labels, literal attributes as properties | keep; `IfcModel` node per document version, index on `GlobalId` | 9 |
| Relationships named after attributes, inverse attributes included, `IfcOwnerHistory` skipped | keep | 9 |
| Synchronous py2neo `merge` during upload (hours for a normal model) | reshape: background worker process with limits, batched `UNWIND ... CREATE` | 9 |
| `SAME_AS` from viewpoint components to `IfcProduct`, GTIN copied from property set `Reuse` | keep; property set and name configurable | 9 |

## 8. Web pages

| Prototype | Status | Stage |
|---|---|---|
| `login.html` (Bootstrap and jQuery from CDN, AJAX) | reshape: same content, own CSS, form POST, CSRF token, no CDN | 2 |
| `select_files.html` | reshape: same content, form POST, filtering, cancel | 5 |
| `upload_files.html` | reshape: same content, cancel | 5 |
| `index.html`, missing `document_details.html` | keep both | 2, 5 |

## 9. Test data

The Archicad model with three walls carrying property set `Reuse` / `GTIN`
1–3 (IFC2X3, 16 KB) is kept once as `tests/fixtures/three_walls_gtin.ifc`
and used by the seed command and the end-to-end tests.

## 10. README items of the prototype

Code structure, deployment steps, suggested reading and the TODO list of the
prototype's README are covered by this document, the ADRs, `docs/deploy/`
(stage 8) and the plan. Two TODO items are out of scope for the rewrite:
native-IFC editing through BIM snippets and git integration.
