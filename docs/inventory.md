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
| 4 | BCF API: comments, viewpoints, related topics, document references, files, snippets, documents, comment events | done |
| 5 | Documents API and browser sign-in | done |
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
| BIM snippet get/put | routes only | implemented; binary upload and download, the snippet becomes internal with the uploaded file name as `reference` (3.2.7) | 4 |
| Files information | yes, broken URL rewrite to an `open-cde-documents://` scheme the specification does not define | implemented from the project's documents; `reference` is the document's download URL, display fields are the same for every entry (3.3.1) | 4 |
| Files header get/put | yes, first file only | implemented; PUT replaces the list | 4 |
| Comments: list, post, get, put, delete | yes; `viewpoint_guid` never returned, reply guid disabled | implemented; viewpoint link checked against the topic, text or viewpoint required, OData on `author`/`date`; BCF 3.0 has no reply field, so the prototype's `reply_to_comment_guid` is dropped | 4 |
| Viewpoints: list, post, get, snapshot, bitmaps, selection, coloring, visibility, delete | yes, many defects (optional parts crashed, JPEG mismatch, colour grouping) | implemented; immutable, exactly one camera, lines, clipping planes, bitmaps, components, PNG and JPEG checked by magic bytes, 409 on delete while a comment refers to it (3.5.9) | 4 |
| Related topics get/put | yes, invalid Cypher | implemented; PUT replaces the list, all guids must be topics of the project | 4 |
| Document references get/post/put | yes, invalid Cypher | implemented; exactly one of `document_guid` (must exist in the project) and `url` (http or https) | 4 |
| Documents: list, post, get | stubs returning `True` | implemented; binary body, file name from `Content-Disposition`, `?guid=` with 409, download as attachment | 4 |
| Topic events, topic events by topic | stubs; routes shadowed by `/topics/{id}` | implemented; 17 event types, several actions per event, events outlive the topic, OData on `topic_guid`/`author`/`date`/`type` | 3 |
| Comment events, comment events by comment | stubs | implemented; 4 comment event types, creation also records the initial text and viewpoint, OData on `comment_guid`/`topic_guid`/`author`/`date`/`type` | 4 |
| Per-entity `authorization` objects | no | implemented for projects, topics, comments and viewpoints | 3, 4 |
| ETag / If-None-Match on GET | no | new | 1, 3 |

## 3. Documents API 1.0 (13 operations in the specification)

| Function | Prototype | Status | Stage |
|---|---|---|---|
| `POST upload-documents` | yes | implemented; `upload_ui_url` carries a 256-bit token stored hashed, `max_size_in_bytes` from settings | 5 |
| Upload metadata page (`document-upload`) | yes, AJAX callback | implemented as `/documents/1.0/upload-ui/{token}`: browser sign-in required and bound to the user who started the flow, form POST, 302 to the callback with `upload_documents_url` or `user_cancelled_upload=true` | 5 |
| Upload instructions (`upload-documents-url`) | yes | implemented; parts of `OPENCDE_UPLOAD_PART_BYTES` with inclusive content ranges, `PUT`, `include_authorization: true`, 400 above `max_size_in_bytes` | 5 |
| Upload file part `POST` | yes, whole body in memory | implemented; streamed and counted, exact size required, bound to the uploading user | 5 |
| Upload file part `PUT` | no | implemented (same handler) | 5 |
| Upload completion / cancellation | per session, swallowed errors | implemented per file; parts assembled with a size check and SHA-256, idempotent completion, keep-alive whitespace after 15 s | 5 |
| `POST document-versions` (aggregate query) | bare list in and out, always version 1 | implemented; `DocumentQuery` in, `DocumentQueryResult` out, `ETag` and `If-None-Match` → 304, unknown or foreign ids omitted | 5 |
| `POST select-documents` | yes | implemented; `select_documents_url` with a hashed token | 5 |
| Selection page (`document-selection`) | yes, AJAX callback | implemented as `/documents/1.0/select-ui/{token}`: sign-in required, latest versions per project, filtered on `supported_file_extensions` with "show all", 302 with `selected_documents_url` or `user_cancelled_selection=true` | 5 |
| Selected documents (`download-instructions`) | yes, not bound to the user | implemented; bound to the user who selected, returns the versions chosen at selection time | 5 |
| Document version, metadata, download, versions | yes; inverted version filter, fixed filename | implemented; strict `DocumentVersion` body, absolute links, downloads as attachments with the original file name | 5 |
| Document details page | route without template | implemented (`…/details`, sign-in required) with a browser download | 5 |
| Custom upload from the selection page (`upload_file_to_project`) | yes, unauthenticated | implemented; signed-in editors and managers only, multipart streamed to storage, server-generated ids | 5 |
| Browser sign-in for the server's pages | none (API token in the browser) | new: `/signin`, `/signout`, hashed session cookie, idle and absolute expiry | 5 |
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
| `select_files.html` | done: `documents/select.html`, form POST, filtering, cancel, upload form for editors | 5 |
| `upload_files.html` | done: `documents/upload.html`, project choice, cancel | 5 |
| `index.html`, missing `document_details.html` | done: `index.html`, `documents/details.html` | 2, 5 |
| none: a sign-in page for the server's own pages | new: `web/signin.html`, `web/message.html` | 5 |

## 9. Test data

The Archicad model with three walls carrying property set `Reuse` / `GTIN`
1–3 (IFC2X3, 16 KB) is kept once as `tests/fixtures/three_walls_gtin.ifc`
and used by the seed command and the end-to-end tests.

## 10. Specification notes

Places where the pinned specifications are silent or inconsistent, and what
this server does:

| Observation | Decision |
|---|---|
| BCF 3.0 README examples call the per-event list `events`; the JSON schemas (`topic_event_GET.json`, `comment_event_GET.json`) call it `actions` | The schemas win: `actions` |
| BCF 3.0 README 3.3.1 example uses `file_name`; `file_GET.json` uses `filename` | The schema wins: `filename` |
| The prototype rewrote file references to `open-cde-documents://…`; no OpenCDE specification defines that scheme | `reference` is the document's download URL |
| BCF 3.0 lists no `delete` flag under 3.1.5 but requires one in 3.2.5, 3.4.5 and 3.5.9 | `delete` is part of `topic_actions`, `comment_actions` and `viewpoint_actions` |
| BCF 3.0 says nothing about content types or file names of binary responses | Snapshots and bitmaps are `image/png` or `image/jpeg`; documents and snippets are `application/octet-stream` attachments with the stored file name |
| BCF 3.0 says nothing about how the file name of a document upload (3.8.2) is transmitted | `Content-Disposition` (RFC 6266), as Foundation API 1.9 does for binary uploads; `document` when absent |
| Foundation `versions_GET.json` allows `api_id` `bcf` and `foundation` only, while the Documents API needs `documents` there | The conformance test accepts `documents` |
| Documents `UploadFilePartInstruction` is `allOf: [LinkData, …]` where `LinkData` has `additionalProperties: false`; read as strict JSON Schema nothing could satisfy it | The conformance test reads `allOf` as composition, as OpenAPI tooling does |
| Documents API: no callback parameter is defined for the user cancelling an upload in some wording (`user_cancelled_selection` appears under the upload flow once) | `user_cancelled_upload=true` for uploads, `user_cancelled_selection=true` for selections, as the operation descriptions state |

## 11. README items of the prototype

Code structure, deployment steps, suggested reading and the TODO list of the
prototype's README are covered by this document, the ADRs, `docs/deploy/`
(stage 8) and the plan. Two TODO items are out of scope for the rewrite:
native-IFC editing through BIM snippets and git integration.
