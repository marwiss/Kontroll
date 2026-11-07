# Changelog

Kontroll takes the same release numbers as [Dataspatium](https://github.com/marwiss/Dataspatium):
the same number on both means they work together. Only the latest release
of each major number is kept; an earlier one of the same major number is
withdrawn (its commits remain) and its notes are folded into the one that
stays. Every release lists what a client can see; internal changes are in
the commit history.

## Unreleased

Toward 3.0.0, with Dataspatium.

- An IFC model can be written back from the graph as a file that holds the same model, on Neo4j and on Memgraph:
  `opencde ifcgraph export <model id> model.ifc`, with `--verify` to compare it with the upload. See
  [docs/ifcgraph.md](docs/ifcgraph.md).
- A model is converted in a new form by default. It has the same nodes, relationships and values as before, so queries
  keep working. Added to them are `position` on the relationships of forward attributes, `<attribute>__type` beside typed
  values and `<attribute>__step` for references to what is no node. Geometry is compressed text on `StepBlock` nodes, which
  a query should not return whole. `OPENCDE_IFCGRAPH_LOSSLESS=false` gives the old form. Models already converted keep
  theirs, and cannot be written back until uploaded again.
- A file written from the graph is validated against the IFC standard, and an issue the upload does not have ends the
  command with an error. The `ifcgraph` extra now includes pytest, which IfcOpenShell's validator needs at run time.
- Every IFC file uploaded as a document version is checked against the IFC schema in the background, and the upload is
  never held back by it. The version's metadata says how it went (`ifc_validation_status`, `ifc_validation_issues`,
  `ifc_validation_checked_at`, `ifc_validation_ruleset`) and where the report is (`ifc_validation_report`). The report is
  an extension, `GET /documents/1.0/documents/{id}/versions/{index}/ifc-validation`, with up to 10,000 issues and the
  GlobalId of each element. The version's page shows the first 100. `OPENCDE_IFCGRAPH_VALIDATE_UPLOADS=false` turns it
  off.
- `python -m opencde.ifcgraph.equivalence first.ifc second.ifc` says whether two IFC files hold the same model.
- `GET /admin/api/settings` has `ifcgraph.lossless` and `ifcgraph.validate_uploads`.

## 2.0.1 — 2026-11-07

The single release of the 2 series: 2.0.0 with the deletion of a project put right, and with
it everything up to and including 2.7.0, on the branch `release-2`. 2.0.0 is withdrawn under the
rule above, together with Dataspatium 2.0.0. No history is rewritten: the commits stay, and only
the earlier releases and tags went. Works with Dataspatium 2.0.1, which also speaks BCF API 2.1,
so that a server with 2.1 alone can be its source, and draws the IFC graph.

- Deleting a project deletes only what the project owns. In 2.0.0 it followed every relationship from the project,
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
- The quick start covers everything it takes to sign in to Kontroll from
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
