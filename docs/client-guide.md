# Building a client

How an application talks to this server (or any OpenCDE server). The Python
library in [client/](../client/) does all of this; the examples in
[examples/](examples/) show it in use.

## 1. Discover

`GET /foundation/versions` lists the APIs (`foundation 1.0`, `bcf 3.0`,
`documents 1.0`). `GET /foundation/1.0/auth` tells you where to sign in:

```json
{
  "oauth2_auth_url": "https://cde.example/foundation/oauth2/auth",
  "oauth2_token_url": "https://cde.example/foundation/oauth2/token",
  "oauth2_revocation_url": "https://cde.example/foundation/oauth2/revoke",
  "http_basic_supported": false,
  "supported_oauth2_flows": ["authorization_code_grant"],
  "oauth2_pkce_methods": ["S256"],
  "oauth2_pkce_required": true
}
```

### The capabilities document (extension)

Beyond the specifications, `GET /.well-known/kontroll` (no authentication,
CORS as for the API, cacheable for five minutes) says which extensions this
server has turned on and which limits apply, so that a client adapts instead
of probing:

```json
{
  "server": {"name": "Kontroll OpenCDE server", "version": "2.5.0", "public_url": "https://cde.example.org"},
  "apis": {"foundation": "1.0", "bcf": "3.0", "documents": "1.0"},
  "scopes": ["profile", "bcf", "documents", "admin"],
  "extensions": {
    "dynamic_client_registration": {"enabled": true, "public_clients": true, "initial_access_token": false, "approval": false, "unused_days": 30,
                                    "url": "/foundation/oauth2/reg"},
    "request_log": {"enabled": true, "retention_hours": 72, "url": "/admin/api/requests"},
    "admin_api": {"enabled": true, "version": 1, "url": "/admin/api", "scope": "admin"},
    "ifcgraph": {"enabled": true, "bolt": null},
    "graph_query": {"enabled": true, "url": "/admin/api/graph/query", "max_rows": 1000, "timeout_seconds": 10.0}
  },
  "limits": {"max_upload_bytes": 1073741824, "max_image_bytes": 10485760, "access_token_ttl_seconds": 3600},
  "links": {"dataspatium": null}
}
```

A `404` means a server without extensions (another OpenCDE server, or an
older Kontroll). Treat unknown keys as absent. `ifcgraph.bolt` is set only
when the operator has deliberately published the graph database
(`OPENCDE_GRAPH_PUBLIC_BOLT_URL`); `graph_query` is on only when the
operator has set `OPENCDE_GRAPH_QUERY_ENABLED` (§7); `links.dataspatium`
carries the address of a Dataspatium installation when the operator has set
`OPENCDE_DATASPATIUM_URL`. Nothing in the document is secret.

## 2. Sign in (OAuth2 authorization code with PKCE)

1. Ask the server's administrator to register your application: a **public**
   client for desktop, mobile and browser apps (no secret, PKCE), or a
   **confidential** client for a server application (secret shown once).
   Register the exact redirect URI; for native apps `http://127.0.0.1/…`
   (any port) is accepted.
2. Generate a `code_verifier` (43–128 URL-safe characters) and its
   `code_challenge = BASE64URL(SHA256(verifier))`, plus a random `state`.
3. Open `oauth2_auth_url?response_type=code&client_id=…&redirect_uri=…&scope=profile bcf documents&state=…&code_challenge=…&code_challenge_method=S256`
   in the user's browser. The user signs in and consents.
4. The browser is redirected to your `redirect_uri` with `code`, `state`
   and `iss`. Check `state`; check `iss` is the server.
5. `POST oauth2_token_url` with `grant_type=authorization_code`, `code`,
   `code_verifier`, `redirect_uri` and `client_id` (public) or HTTP Basic
   authentication (confidential). The answer is `201` with `access_token`,
   `refresh_token`, `expires_in`, `scope`.
6. Send `Authorization: Bearer <access_token>` on every API call. When it
   expires, `POST oauth2_token_url` with `grant_type=refresh_token`; the
   refresh token rotates, so store the new one. Reusing an old refresh token
   revokes the whole family: that is the server noticing a stolen token.
7. `POST oauth2_revocation_url` with the refresh token when the user signs out.

The server never supports the implicit or password grants.

### Registering a client dynamically

When the server runs with `OPENCDE_DYNAMIC_CLIENT_REGISTRATION=true`,
`GET /foundation/1.0/auth` carries `oauth2_dynamic_client_reg_url` and a client
can register itself (Foundation API 2.2.3, RFC 7591). A browser or native
application asks for a public client:

```http
POST /foundation/oauth2/reg
Content-Type: application/json

{"client_name": "My viewer",
 "redirect_uris": ["http://127.0.0.1:8093/oauth-callback.html"],
 "token_endpoint_auth_method": "none",
 "grant_types": ["authorization_code", "refresh_token"],
 "software_id": "my-viewer",
 "software_version": "1.4.0"}
```

The answer (201) carries `client_id`, `client_id_issued_at` and the registered
metadata. A confidential client (the default `token_endpoint_auth_method`,
`client_secret_basic`) also gets its `client_secret` once, with
`client_secret_expires_at: 0`. Redirect URIs follow the rules above, and only
the authorization code and refresh token grants exist. Send `software_id` and
`software_version` (RFC 7591 §2): the server stores them on the client and
shows them to administrators next to the registration, which is how an
operator tells installations and versions of your application apart.

A server can limit this further. With `OPENCDE_DYNAMIC_CLIENT_REGISTRATION_TOKEN` set, the request takes that value as `Authorization: Bearer …` (RFC 7591 §3) and answers 401 without it. With `OPENCDE_DYNAMIC_CLIENT_APPROVAL=true`, the new client can sign nobody in until an administrator approves it, and the sign-in page says so. The capabilities document tells which applies.

Register once per installation and store the `client_id`: a self-registered
client that issues no token for `OPENCDE_DYNAMIC_CLIENT_UNUSED_DAYS` (30 by
default) is deleted together with its tokens. When the token endpoint then
answers `invalid_client`, register again.

**Pop-ups.** The pages your application opens in a pop-up (the authorization
page, the Documents API selection and upload pages, and the sign-in they may
need) do not isolate themselves: they send
`Cross-Origin-Opener-Policy: unsafe-none`, so the window keeps its
`window.opener` across the visit to the server and your callback page can
`postMessage` the result back to the application. Only `/admin` and
`/account` answer with `same-origin`. Their `form-action` policy also names
the origin of your redirect URI (or callback URL), so the browser follows
the redirect that answers the form: Chromium checks `form-action` against
that redirect, not only against the form's own address.

## 3. BCF API

- Everything under `/bcf/3.0/projects/{project_id}` is scoped to a project
  the user is a member of; projects the user cannot see answer `404`.
- `GET …/extensions` gives the allowed values (`topic_type`, `topic_status`,
  `topic_label`, `priority`, `stage`, `users`) and the user's default
  `project_actions`, `topic_actions`, `comment_actions`. Values outside the
  lists are refused with `400`.
- Add `?includeAuthorization=true` to a `GET` of projects, topics, comments
  or viewpoints to receive an `authorization` object per entity.
- Collections accept OData: `$filter` (e.g. `topic_status eq 'Open' and
  labels/any(l: l eq 'Safety')`), `$orderby`, `$top`, `$skip`.
- `PUT` replaces the whole object: send every field you want to keep.
- Images in viewpoints are base64 PNG or JPEG; the server checks the bytes.
- Every `GET` carries an `ETag`; `If-None-Match` answers `304`.
- Errors are `{"message": "…"}` with the usual status codes (`400`, `401`,
  `403`, `404`, `409` for duplicate guids, `413` for oversized bodies).

## 4. Documents API

The flows involve the user's browser; see [flows/documents.md](flows/documents.md).
Your client needs a callback URL the browser can reach (a loopback listener
for desktop apps). The server never calls that URL itself.

## 5. Correlating your log with the server's

Send an `X-Request-ID` header (1–128 characters of `A-Za-z0-9._-`) with every
request and the server echoes it in the response and binds it to its own log
lines; without one the server mints an id and returns it. The header is allowed
in CORS preflights and exposed to browser clients.

When the operator has turned on the request log (`OPENCDE_REQUEST_LOG_ENABLED`,
an extension outside the specifications), an administrator can see the server
side of every call at `/admin/requests`, and an administration client can read
the same entries as JSON:

```http
GET /admin/api/requests?client_id=<your client id>&since=2026-11-05T10:00:00Z&limit=200
Authorization: Bearer <token with the admin scope>
```

The token must carry the `admin` scope, which a client asks for explicitly
(`scope=profile bcf documents admin`), and the user must be an administrator.
Entries hold method, path, operation, status, timing, request id, byte counts
and the caller, never bodies or tokens. The JSON administration API is served
while `OPENCDE_ADMIN_API_ENABLED` is true (the default), independently of the
HTML administration; the capabilities document (§1) tells you whether it is on.

## 6. Errors

Every failure answers with the Foundation API 1.6 body, `{"message": "..."}`,
and never with stack traces or echoed input. As an extension, every error the
server shapes itself also carries a stable `code` that your application can
act on or translate, while `message` stays an English sentence for people:

```json
{"message": "This operation needs the 'admin' scope", "code": "insufficient_scope"}
```

| `code` | Status | When | What a client does |
|---|---|---|---|
| `validation_error` | 400 | The body or query failed validation, an OData expression could not be compiled, a value is not in the project's extensions, a `Content-Range` or upload instruction is wrong, a snapshot or bitmap is not PNG or JPEG; `message` names the field | Fix the request |
| `unauthenticated` | 401 | No bearer token | Sign in |
| `invalid_token` | 401 | The token is unknown, expired or revoked (`WWW-Authenticate: Bearer error="invalid_token"`) | Refresh, then sign in again |
| `insufficient_scope` | 403 | The token lacks the scope the route needs, such as `admin` | Authorize again with that scope |
| `forbidden` | 403 | The user's role in the project does not allow the action (Foundation API 1.5), or the user is not an administrator on the administration API | Show the message |
| `reauthentication_required` | 403 | A dangerous administration action and the sign-in is older than ten minutes | Authorize again, then repeat the call |
| `not_found` | 404 | No such resource, a resource outside the user's projects, or a feature that is off (registration, request log, administration API) | Show the message, refresh lists |
| `conflict` | 409 | A guid that already exists, or a duplicate link | Fetch again |
| `payload_too_large` | 413 | The request body is over the server's limit, or a BCF binary is over `max_image_bytes`/`max_upload_bytes` | Fix the request |
| `upload_too_large` | 413 | A chosen file or part is over the upload limit (`max_size_in_bytes` in the upload instructions) | Tell the user the limit |
| `rate_limited` | 429 | Too many requests from one address; `Retry-After` says when | Wait and retry |
| `internal_error` | 500 | An unexpected error; `message` is always "Internal server error" | Report with the `X-Request-ID` |
| `unavailable` | 503 | The graph database cannot be reached | Retry later |

The list is closed: a code you do not know is treated like a missing one, and
you show `message`. Statuses the framework answers on its own (405, 415) carry
no code. The OAuth2 token endpoint keeps RFC 6749's own format
(`{"error": "invalid_grant", "error_description": "..."}`), as the
specification requires, so act on `error` there (`invalid_request`,
`invalid_client`, `invalid_grant`, `unauthorized_client`,
`unsupported_grant_type`, `invalid_scope`). The capabilities document (§1)
is served by every server that emits codes.

## 7. The administration API (extension)

An administration client (Dataspatium's Administration tab is the first)
reads what the pages under `/admin` show, as JSON under `/admin/api/`, with
a bearer token that holds the `admin` scope and belongs to an administrator.
The capabilities document says whether the API is on
(`extensions.admin_api`) and which version it has. Lists answer
`{"items": [...], "total": n}` and take `limit` (200 by default, at most
1000) plus `q` or `since` where noted; errors use the body of §6.

| Endpoint | Returns |
|---|---|
| `GET /admin/api/overview` | `version`, `uptime_s`, `dialect`, `graph_ok`, the counts `users`, `projects`, `clients`, `sessions`, `topics`, `documents`, `models`, and `request_log` (`enabled`, `rows`) |
| `GET /admin/api/users?q=&limit=` | users (`id`, `username`, `name`, `email`, `is_admin`, `disabled`, `must_change_password`, `created_at`, `last_sign_in_at`, `projects` as `[{project_id, role}]`); `q` searches user name, name and e-mail |
| `GET /admin/api/users/{id}` | one user; `projects` also carries the project `name` |
| `GET /admin/api/projects?q=` | projects with `members` (`user_id`, `username`, `role`) and the counts `topics`, `documents`, `models` |
| `GET /admin/api/projects/{id}` | one project with its `extensions` as well |
| `GET /admin/api/clients` | clients (`client_id`, `name`, `description`, `url`, `public`, `dynamic`, `redirect_uris`, `disabled`, `created_at`, `expires_at`, `last_used_at`, `software_id`, `software_version`), never a secret |
| `GET /admin/api/clients/{id}` | one client |
| `GET /admin/api/sessions?user=&limit=` | one list of two kinds, `kind: "oauth2"` (a refresh-token family, `id` = family id) and `kind: "web"` (a browser session), each with `user_id`, `username`, `created_at`, `expires_at`, and `client_id`/`client_name`/`scope` or `ip` where they apply |
| `GET /admin/api/audit?type=&since=&limit=` | audit events with `at`, `type`, `actor` (user id), `client_id`, `ip`, `request_id` and parsed `details` |
| `GET /admin/api/requests?...` | the request log (§5) |
| `GET /admin/api/settings` | `public_url`, `environment`, `dynamic_client_registration`, `request_log`, `ifcgraph`, `cors_origins`, `dataspatium_url`, `graph_public_bolt_url`, the enabled `modules`, and every `OPENCDE_*` value of the Settings page under `raw`; secrets left out |
| `GET /admin/api/health` | `ok` and the `checks` (`name`, `ok`, `detail`) of the Settings page |

Writes, with the same bodies the pages use (`PUT` and `PATCH` are accepted
alike; `name` is the full name, `full_name` works as well):

| Endpoint | Does |
|---|---|
| `POST /admin/api/users` `{username, password?, name?, email?, is_admin?, must_change_password?}` | creates a user; without `password` the answer carries `initial_password` once |
| `PUT /admin/api/users/{id}` `{name?, email?, disabled?, is_admin?}` | changes a user; disabling revokes the tokens; not for your own account |
| `DELETE /admin/api/users/{id}` | deletes a user with sessions and tokens (dangerous) |
| `POST /admin/api/users/{id}/reset-password` | sets a new password returned once, which the user must change (dangerous) |
| `POST /admin/api/projects` `{name, extensions?}` · `PUT /admin/api/projects/{id}` `{name?, extensions?}` | creates or changes a project |
| `DELETE /admin/api/projects/{id}` | deletes a project with everything in it (dangerous) |
| `PUT /admin/api/projects/{id}/members/{user_id}` `{role}` · `DELETE …/members/{user_id}` | sets or removes a member's role (viewer, contributor, editor, manager) |
| `POST /admin/api/clients` `{name, redirect_uris, public?, description?, url?}` | registers a client; a confidential one gets `client_secret` once |
| `PUT /admin/api/clients/{id}` `{name?, description?, url?, redirect_uris?, disabled?}` | changes a client; disabling revokes its tokens |
| `POST /admin/api/clients/{id}/rotate-secret` | a new secret, returned once (dangerous) |
| `POST /admin/api/clients/{id}/revoke` · `DELETE /admin/api/clients/{id}` | revokes every token of the client · deletes the client with its tokens (dangerous) |
| `DELETE /admin/api/sessions/{id}` · `DELETE /admin/api/sessions?user=` | ends one session by the `id` of the listing · ends every session and token of a user |

Dangerous operations require a **fresh sign-in**: the token family's
`auth_time`, set when the user authenticated for the authorization code,
must be within the last ten minutes; a refresh never renews it. Otherwise
the answer is `403` with `code: reauthentication_required`, which a client
meets by running the authorization flow again (a pop-up sign-in) and
repeating the call. One-time values are returned exactly once and never
logged; every write leaves an audit event (`admin.*`) with the caller, the
client and the `X-Request-ID` of the call.

### Graph query (off by default)

When the operator sets `OPENCDE_GRAPH_QUERY_ENABLED=true`, the capabilities
document announces `graph_query` with `url`, `max_rows` and
`timeout_seconds`, and administrators holding the `admin` scope may run
**reading** Cypher against the whole graph, the IFC graph included, without
the database port being published:

```http
POST /admin/api/graph/query
{"cypher": "MATCH (p:Project)<-[m:MEMBER_OF]-(u:User) RETURN p, m, u LIMIT 50", "params": {}}
```

```json
{"columns": ["p", "m", "u"],
 "rows": [[{"identity": "4:…:12", "labels": ["Project"], "properties": {"project_id": "…", "name": "Building permit"}},
           {"identity": "5:…:3", "type": "MEMBER_OF", "start": "4:…:7", "end": "4:…:12", "properties": {"role": "editor"}},
           {"identity": "4:…:7", "labels": ["User"], "properties": {"username": "editor"}}]],
 "truncated": false}
```

Rows carry JSON values: nodes as `{identity, labels, properties}`,
relationships as `{identity, type, start, end, properties}`, paths as
`{nodes, relationships, length}`, temporal values as ISO 8601 strings,
integers as numbers, points as `{srid, x, y, z}`, bytes as base64. The
statement runs in a read transaction; the server refuses writing clauses
and any procedure other than the schema procedures (`db.labels`,
`db.relationshipTypes`, `db.propertyKeys`, `db.schema.*`), refuses
statements and parameters that name a protected property (`password_hash`,
`secret_hash`, `token_hash`, `code_hash`), removes those properties from
every node, relationship and map in the answer and redacts any Argon2 hash
that reaches it another way. The answer stops after `max_rows` rows
(`truncated: true`) and the statement after `timeout_seconds`. A refused,
failed or stopped statement answers `400` with `code: validation_error` and
the reason, the database's own message included. Every call, refused or
not, leaves an audit event `admin.graph.query` with the first 500 characters
of the statement, never the parameters.

## 8. Testing against this server

[Dataspatium](https://github.com/marwiss/Dataspatium) is the browser client
developed together with this server; its OpenCDE source (sign-in, BCF tables,
Documents API, graph queries, request ids) is a worked example of everything
above, and its live test suites run against the development stack
(see [acceptance.md](acceptance.md)).

- `uv run opencde seed` fills an empty database with demo users and
  projects (passwords are printed once), the sample model
  `three_walls_gtin.ifc` as a document and one topic with a viewpoint and a
  comment, all with fixed ids a test suite can rely on:

  | What | Id |
  |---|---|
  | Document (Documents API, version 1, project *Building permit*) | `6f5d3b2a-0000-4000-8000-000000000001` |
  | Topic (`ISSUE-0001`, type Inspection, status Open, label Reuse) | `6f5d3b2a-0000-4000-8000-000000000002` |
  | Viewpoint (perspective camera, component wall `1Xezbq735AdBO_4DerG66G`) | `6f5d3b2a-0000-4000-8000-000000000003` |
  | Comment (by `inspector`, referring to the viewpoint) | `6f5d3b2a-0000-4000-8000-000000000004` |

  The model's walls are `1Xezbq735AdBO_4DerG66G` (GTIN 3),
  `3eT96F_cnDsOufCEsotwtp` (GTIN 2) and `3k3LbXmTfDWODxdSuyCGYE` (GTIN 1),
  in property set `Reuse`; the same file is `tests/fixtures/three_walls_gtin.ifc`.
- `docker compose -f compose.yaml -f compose.dev.yaml up -d` gives you a
  server on `http://127.0.0.1:8000` with Neo4j Browser on `:7484`.
- Register a client for your app in the admin UI (`/admin` → Clients) or with
  `uv run opencde client create "My app" --redirect-uri http://127.0.0.1/callback --public`.
- `opencde_client.testing` can complete the sign-in and the Documents API
  pages without a browser in automated tests.
