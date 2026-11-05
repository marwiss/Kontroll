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
 "grant_types": ["authorization_code", "refresh_token"]}
```

The answer (201) carries `client_id`, `client_id_issued_at` and the registered
metadata. A confidential client (the default `token_endpoint_auth_method`,
`client_secret_basic`) also gets its `client_secret` once, with
`client_secret_expires_at: 0`. Redirect URIs follow the rules above, and only
the authorization code and refresh token grants exist.

Register once per installation and store the `client_id`: a self-registered
client that issues no token for `OPENCDE_DYNAMIC_CLIENT_UNUSED_DAYS` (30 by
default) is deleted together with its tokens. When the token endpoint then
answers `invalid_client`, register again.

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
and the caller, never bodies or tokens.

## 6. Testing against this server

- `uv run opencde seed` fills an empty database with demo users and
  projects (passwords are printed once).
- `docker compose -f compose.yaml -f compose.dev.yaml up -d` gives you a
  server on `http://localhost:8000` with Neo4j Browser on `:7484`.
- Register a client for your app in the admin UI (`/admin` → Clients) or with
  `uv run opencde client create "My app" --redirect-uri http://127.0.0.1/callback --public`.
- `opencde_client.testing` can complete the sign-in and the Documents API
  pages without a browser in automated tests.
