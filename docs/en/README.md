[Svenska](../../README.md) · [Dansk](../da/README.md) · [Norsk bokmål](../nb/README.md) · [Norsk nynorsk](../nn/README.md) · [Suomi](../fi/README.md) · [Íslenska](../is/README.md) · **English**

<img src="../../opencde/ui/static/icon-192.png" alt="" width="64" height="64" align="left">

# Kontroll OpenCDE server

Kontroll is a server for the buildingSMART **OpenCDE APIs** (Foundation API 1.0,
BCF API 3.0 and Documents API 1.0), built on a graph database, with a web
administration and an optional IFC-graph module that joins BCF components to
the building elements they point at. It grew out of a 2023 research prototype
for the digital inspection plans of Swedish building permits and was rewritten
from scratch with security as the first requirement.

![The administration overview of a Kontroll server: counts of users, projects, clients, topics and documents, the database status and the latest audit events](../images/admin-overview.png)

**Contents**

- [Download and get started](#download-and-get-started)
- [Requirements](#requirements)
- [What you can do](#what-you-can-do)
- [Kontroll and Dataspatium](#kontroll-and-dataspatium)
- [Learn more](#learn-more)
- [Limitations in brief](#limitations-in-brief)
- [Bugs and suggestions](#bugs-and-suggestions)
- [Development](#development)
- [Licence](#licence)

## Download and get started

### Quick start (local, Docker)

1. **Download.** Clone the repository, or pull the published image
   `ghcr.io/marwiss/opencdeserver` (multi-arch, scanned and with an SBOM on
   every release):

   ```sh
   git clone https://github.com/marwiss/Kontroll.git
   cd Kontroll
   ```

2. **Configure.** Copy `.env.example` to `.env` and set `OPENCDE_GRAPH_PASSWORD`
   (16 characters or more). Every setting is explained in
   [.env.example](../../.env.example).
3. **Start.** `docker compose -f compose.yaml -f compose.dev.yaml up -d --build`
   starts the server on <http://localhost:8000> and a Neo4j database.
   `docker compose logs -f api` shows the server log.
4. **Look around.** <http://localhost:8000/docs> is the interactive API
   documentation, <http://localhost:8000/readyz> the readiness check and
   <http://localhost:7484> Neo4j Browser (Bolt on `localhost:7697`; the
   development overlay avoids Neo4j's default ports, which another Neo4j on
   the same machine often occupies).
5. **Add demo data and sign in.**
   `docker compose -f compose.yaml -f compose.dev.yaml exec api opencde seed`
   creates demonstration users and projects and prints their passwords once.
   Sign in at <http://localhost:8000/signin> as `admin` and open `/admin`.
6. **Connect a client.** Register your application under *Clients* (or let it
   register itself when `OPENCDE_DYNAMIC_CLIENT_REGISTRATION=true`) and point
   it at `http://localhost:8000`; [Dataspatium](#kontroll-and-dataspatium) and
   the Python library in [client/](../../client/) are ready-made clients.

Without Docker for the server itself (a database is still needed):

```sh
uv sync                          # installs Python 3.13 and all dependencies
uv run opencde doctor            # checks configuration and the database
uv run opencde serve             # http://127.0.0.1:8000
```

### Deployment

One compose file plus an overlay per scenario:

| Scenario | Guide |
|---|---|
| Local test on your machine | [docs/deploy/local.md](../deploy/local.md) |
| Public https URL for client tests without a server (tunnel) | [docs/deploy/tunnel.md](../deploy/tunnel.md) |
| Production on your own server with Caddy (automatic TLS) and nightly backups | [docs/deploy/vps-caddy.md](../deploy/vps-caddy.md) |
| Coolify, Dokploy, Portainer | [docs/deploy/paas.md](../deploy/paas.md) |
| Container service plus managed Neo4j AuraDB or Memgraph Cloud | [docs/deploy/cloud-aura.md](../deploy/cloud-aura.md) |
| Backup and restore (portable between Neo4j and Memgraph) | [docs/deploy/backup.md](../deploy/backup.md) |

`uv run opencde init --public-url https://cde.example.org` writes a production
`.env` with fresh secrets; `opencde doctor` checks the result.

### Configuration

Everything is read from environment variables prefixed `OPENCDE_`, from
`.env`, or from Docker secrets in `/run/secrets/opencde_<name>`. The
annotated list is in [.env.example](../../.env.example). Defaults are safe:
production refuses to start without an `https` public URL and a database
password, and nothing is open until it is configured.

## Requirements

- Windows, macOS or Linux with Docker (Desktop on Windows/macOS, Engine on
  Linux), or Python 3.11 or later with [uv](https://docs.astral.sh/uv/) and a
  Neo4j 5.26 or Memgraph 3.14 database of your own.
- About 1 GB of memory for the database container (`NEO4J_HEAP` and
  `NEO4J_PAGECACHE` in `.env`), more with the IFC-graph module.
- Locally: port 8000 for the server and 7484/7697 for the database, all bound
  to `127.0.0.1`. In production: ports 80 and 443 reachable from the internet
  and a DNS name for the server.
- Clients need an `https` address in production; locally `http://localhost`
  redirect URIs are accepted with `OPENCDE_ALLOW_LOCALHOST_REDIRECTS=true`.

## What you can do

- **Foundation API 1.0**: service discovery, OAuth2 authorization code with
  PKCE for every client, current user, token revocation, and dynamic client
  registration with public clients (off by default).
- **BCF API 3.0**: projects, extensions, topics with OData queries, comments,
  viewpoints with snapshots, bitmaps and components, files, document
  references, documents and the event logs, all validated against the
  buildingSMART schemas.
- **Documents API 1.0**: document selection and download, multipart upload
  with the server's web pages for metadata and selection, version queries with
  ETags.
- **Administration** in the browser: sign in at `/signin` with an
  administrator account and open `/admin` to manage users and their project
  roles, projects and their BCF extension values, OAuth2 clients, sessions, the
  audit log, the optional request log and the server's health checks. Every
  user has `/account` for their own password, applications and sessions. The
  CLI (`uv run opencde --help`) does the same from a terminal.
- **Extensions outside the specifications**, each marked as such: a
  capabilities document at `/.well-known/kontroll` that tells a client which
  extensions are on, a stable `code` in every error body, a request log for
  debugging clients (`/admin/requests`, `GET /admin/api/requests` with the
  `admin` scope), and the IFC-graph module that turns uploaded IFC models into
  graph data linked to BCF components.
- **A client library** in Python ([client/](../../client/), LGPL) with runnable
  examples, and a Dockerfile, compose overlays and a published image for every
  deployment scenario.
- **Status**: all eleven stages of the plan are implemented (the three APIs,
  the administration, the client library, deployment, IFC-graph, the acceptance
  checklist and the security hardening); the contribution to IfcOpenShell has
  not been proposed yet (drafts in [docs/upstream/](../upstream/)).
  [docs/inventory.md](../inventory.md) records what the 2023 prototype did
  and where each function stands in the new code.

## Kontroll and Dataspatium

Kontroll (the server) and [Dataspatium](https://github.com/marwiss/Dataspatium)
(a data app that runs entirely in the browser) are developed to work together
as server and client, and the same release number on both means they work
together: Dataspatium 2.5.0 works with Kontroll 2.5.0 ([quick start](../quickstart.md)).
Dataspatium adds a
Kontroll server as a source: it discovers the APIs through
`/foundation/versions`, signs in with OAuth2 authorization code and PKCE and
registers itself as a public client when dynamic registration is on, lists the
project's models and documents, reads and writes BCF issues with comments and
viewpoints taken from its 3D view, uploads datasets, files and workspace
bundles through the Documents API, queries the IFC graph with Cypher over Bolt
when the operator exposes it, and sends `X-Request-ID` on every request so
that the request log here and the log in the app show the same conversation.
It reads the server's capabilities document to see which extensions are on
and acts on the error codes the server adds to its error bodies.

Apart from the marked extensions, everything Dataspatium does against the
server goes through the three OpenCDE APIs, so any other OpenCDE client works
too, and Kontroll serves any OpenCDE client. The two products are installed
separately: this repository does not bundle Dataspatium (the licences differ,
AGPL here and PolyForm Strict there), and Dataspatium's README says how to
download it. The client side is described in Dataspatium's README and its
documentation; the acceptance runs of the pair are in
[docs/acceptance.md](../acceptance.md) here, and what the two projects
coordinate is in
[docs/dataspatium-coordination.md](../dataspatium-coordination.md).

## Learn more

- [docs/quickstart.md](../quickstart.md): Kontroll and Dataspatium together
  in twenty minutes, from an empty machine to an issue created in the 3D view.
- [docs/client-guide.md](../client-guide.md) and [docs/examples/](../examples/):
  how to build a client, the capabilities document, the error codes, and
  runnable examples with the Python library in [client/](../../client/).
- [docs/flows/](../flows/): sequence diagrams of the OAuth2 and Documents API flows.
- [docs/graph-schema.md](../graph-schema.md): the graph model.
- [docs/ifcgraph.md](../ifcgraph.md): the optional IFC-graph module and example Cypher queries.
- [docs/ui-styleguide.md](../ui-styleguide.md): rules for the server's pages and the mark.
- [docs/acceptance.md](../acceptance.md): visual acceptance checklist with
  independent clients (Bonsai, ifc-lite, Dataspatium).
- [docs/dataspatium-coordination.md](../dataspatium-coordination.md): what
  Kontroll and Dataspatium share, and the owner's decisions.
- [docs/inventory.md](../inventory.md): functional inventory of the 2023
  prototype and status in the rewrite, plus notes on specification quirks.
- [docs/adr/](../adr/): architecture decision records (graph backend,
  opaque tokens, portable Cypher, vanilla web UI, repository strategy).
- [docs/security/](../security/): threat model, controls mapped to tests,
  the OWASP ASVS Level 2 checklist, personal data and retention, and how to
  run the scanners.
- [docs/upstream/](../upstream/): drafts of the issue and pull request for
  IfcOpenShell (not sent).
- [spec/SOURCES.md](../../spec/SOURCES.md): the exact specification revisions the
  server is tested against.

The documentation exists in the seven languages of this README: English under
`docs/`, the others under `docs/<language>/`. The project logs (acceptance,
inventory, coordination), the architecture decisions, the upstream drafts and
CONTRIBUTING are kept in English.

## Limitations in brief

- The server implements BCF API 3.0, not 2.1; only the three legacy discovery
  aliases under `/bcf/` exist for older clients.
- Exporting a project as a BCFzip is left to clients; the server stores
  topics, comments and viewpoints as the API defines them.
- The community editions of Neo4j and Memgraph have no read-only database
  users, so an exposed Bolt port gives full access to whoever holds the
  password. The port stays closed unless the administrator publishes it on
  purpose; the administration API's read-only graph query
  (`OPENCDE_GRAPH_QUERY_ENABLED`) gives Cypher without the port.
- The IFC-graph import runs in a separate process with memory and time limits
  (`OPENCDE_IFCGRAPH_*`); very large models are refused rather than left half
  imported.
- The web pages serve administrators and the OAuth2 and Documents API flows;
  end users work in a client such as Dataspatium or Bonsai.
- The pages exist in the seven languages of this README (switch at the foot of
  every page); the command line and the APIs' error messages are in English.
- No external audit yet. The OAuch and testssl runs described in
  [docs/security/pentest-howto.md](../security/pentest-howto.md) are the
  operator's steps before a production deployment.

## Bugs and suggestions

Report bugs and wishes as *Issues* here on GitHub. Say which server version
you run (the `version` of `/.well-known/kontroll` or `/healthz`), which client
you used and the `X-Request-ID` of a failing call; the request log and your
client's log share it. Attach no personal data and no secrets. How changes are
taken in is in [CONTRIBUTING.md](../../CONTRIBUTING.md). For a security
vulnerability follow [SECURITY.md](../../SECURITY.md) instead of opening an issue.

## Development

```sh
uv run pytest                    # unit, conformance and security tests
uv run pytest -m integration     # starts Neo4j/Memgraph with testcontainers (Docker required)
uv run pytest -m e2e             # the client library against a live server (Docker required)
uv run pytest -m ui              # Playwright + axe-core (uv sync --group ui; playwright install chromium)
uv run ruff format . && uv run ruff check .
uv run ty check opencde client/opencde_client
```

Code and comments are in English because the server and the client library
are intended to be contributed to IfcOpenShell, whose conventions (ruff, 120
columns) the style follows. The README exists in English, Swedish, Danish,
Norwegian (Bokmål and Nynorsk), Finnish and Icelandic (`docs/<lang>/README.md`,
the layout Dataspatium uses); the documentation and the web UI are
available in the same languages, with English always one of the choices, and
shared terms follow Dataspatium's glossary. Every push runs linting, type
checks, the test suites on three Python versions, browser tests with axe-core,
and static security checks; nightly jobs run OWASP ZAP, Schemathesis and
Trivy. See [CONTRIBUTING.md](../../CONTRIBUTING.md).

## Licence

The server is licensed under the GNU Affero General Public License v3.0 or
later ([LICENSE](../../LICENSE)): it is server software, and the AGPL's network
clause keeps improvements to hosted instances open. The client library in
[client/](../../client/) is LGPL-3.0-or-later. Specification files under
[spec/](../../spec/) are © buildingSMART International and redistributed unmodified
for testing. See [SECURITY.md](../../SECURITY.md) for how to report a vulnerability
and what the project does to stay secure.
