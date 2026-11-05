# Changelog

Kontroll takes the same release numbers as [Dataspatium](https://github.com/marwiss/Dataspatium):
the same number on both means they work together. Every release lists what
a client can see; internal changes are in the commit history.

## Unreleased

- The administration API follows the resource list agreed with Dataspatium
  for its 2.2.0: a flat overview with `uptime_s` and `models`, users with
  `name` and their project roles, projects with inline `members`, clients
  with `public`, sessions with an `id` that `DELETE /admin/api/sessions/{id}`
  accepts, `DELETE /admin/api/sessions?user=`, structured settings with the
  raw values under `raw`, `PUT` beside `PATCH`, `POST …/reset-password`,
  `POST …/rotate-secret`, and `initial_password` in the answer to a created
  user without a given password.
- A read-only graph query for administrators, off by default
  (`OPENCDE_GRAPH_QUERY_ENABLED`): `POST /admin/api/graph/query` with
  `{cypher, params}` answers `{columns, rows, truncated}`, nodes,
  relationships and paths as JSON objects, within `max_rows` and
  `timeout_seconds` announced in the capabilities document; writing clauses,
  procedures other than the schema procedures and protected properties are
  refused, and every call is audited.
- The deployment guides (local test, tunnel, production with Caddy,
  self-hosted platforms, managed database, backup and restore, the Bolt
  port) exist in all seven languages under `docs/<lang>/deploy/`, linked
  from each README.

## 2.0.0 — 2026-11-05

The first tagged release. Works with Dataspatium 2.0.0.

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
  (`/admin/requests`, `GET /admin/api/requests`); the administration API
  under `/admin/api/` (read and write, dangerous writes need a sign-in from
  the last ten minutes); the IFC-graph module with `SAME_AS` links from BCF
  components to building elements; deep links into Dataspatium from the
  project and document pages.
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
- Documentation: README and the joint quick start in seven languages, the
  client guide, deployment guides, the security pages (threat model,
  controls, ASVS checklist, personal data), the coordination plan with
  Dataspatium, and `CONTRIBUTING.md`.
