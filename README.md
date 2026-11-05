<img src="opencde/ui/static/icon.svg" alt="" width="72" height="72" align="left">

# Kontroll OpenCDE server

*English · [Svenska](README.sv.md)*

A server for the buildingSMART **OpenCDE APIs**, built on a graph database:

- **Foundation API 1.0**: service discovery, OAuth2 authorization code with PKCE, current user
- **BCF API 3.0**: projects, extensions, topics, comments, viewpoints, files, document references, documents, events
- **Documents API 1.0**: document selection and download, multipart upload, version queries

plus a web administration UI for users, OAuth2 clients and projects, and an
optional IFC-graph module that turns uploaded IFC models into graph data so
BCF components can be joined to the building elements they point at.

The project grew out of a 2023 research prototype that tested whether the BCF
API and IFC-graph could carry the digital inspection plans required for
building permits in Sweden. This repository is a rewrite from scratch of that
prototype with the same functionality, modern dependencies and security as the
first requirement. Status: **all 11 stages of the plan are implemented** (the
three APIs, the admin UI, the client library, deployment, IFC-graph, the
acceptance checklist and the security hardening); the contribution to
IfcOpenShell waits for its maintainers' answer (drafts in
[docs/upstream/](docs/upstream/)). See [docs/inventory.md](docs/inventory.md)
for what the prototype did and where each function stands in the new code.

## Quick start (local, Docker)

Requirements: Docker (Desktop on Windows/macOS, Engine on Linux) and
[uv](https://docs.astral.sh/uv/).

```sh
git clone https://github.com/marwiss/Kontroll.git
cd Kontroll
cp .env.example .env            # set OPENCDE_GRAPH_PASSWORD (16+ characters)
docker compose -f compose.yaml -f compose.dev.yaml up -d --build
```

Then open <http://localhost:8000/docs> for the interactive API documentation,
<http://localhost:8000/readyz> for the readiness check, and
<http://localhost:7484> for Neo4j Browser (Bolt on `localhost:7697`; the
development overlay avoids Neo4j's default ports, which another Neo4j on the
same machine often occupies). `docker compose logs -f api` shows the server log.

Without Docker for the server itself (a database is still needed):

```sh
uv sync                          # installs Python 3.13 and all dependencies
uv run opencde doctor            # checks configuration and the database
uv run opencde serve             # http://127.0.0.1:8000
```

## Deployment

One compose file plus an overlay per scenario, and a published multi-arch image
(`ghcr.io/marwiss/opencdeserver`, scanned and with an SBOM on every release):

| Scenario | Guide |
|---|---|
| Local test on your machine | [docs/deploy/local.md](docs/deploy/local.md) |
| Public https URL for client tests without a server (tunnel) | [docs/deploy/tunnel.md](docs/deploy/tunnel.md) |
| Production on your own server with Caddy (automatic TLS) and nightly backups | [docs/deploy/vps-caddy.md](docs/deploy/vps-caddy.md) |
| Coolify, Dokploy, Portainer | [docs/deploy/paas.md](docs/deploy/paas.md) |
| Container service plus managed Neo4j AuraDB or Memgraph Cloud | [docs/deploy/cloud-aura.md](docs/deploy/cloud-aura.md) |
| Backup and restore (portable between Neo4j and Memgraph) | [docs/deploy/backup.md](docs/deploy/backup.md) |

`uv run opencde init --public-url https://cde.example.org` writes a production
`.env` with fresh secrets; `opencde doctor` checks the result.

## Configuration

Everything is read from environment variables prefixed `OPENCDE_`, from
`.env`, or from Docker secrets in `/run/secrets/opencde_<name>`. The
annotated list is in [.env.example](.env.example). Defaults are safe:
production refuses to start without an `https` public URL and a database
password.

## Documentation

- [docs/inventory.md](docs/inventory.md): functional inventory of the 2023
  prototype and status in the rewrite, plus notes on specification quirks
- [docs/client-guide.md](docs/client-guide.md) and [docs/examples/](docs/examples/):
  how to build a client; runnable examples with the Python library in [client/](client/)
- [docs/flows/](docs/flows/): sequence diagrams of the OAuth2 and Documents API flows
- [docs/graph-schema.md](docs/graph-schema.md): the graph model
- [docs/ifcgraph.md](docs/ifcgraph.md): the optional IFC-graph module and example Cypher queries
- [docs/ui-styleguide.md](docs/ui-styleguide.md): rules for the server's pages
- [docs/acceptance.md](docs/acceptance.md): visual acceptance checklist with
  independent clients (Bonsai, ifc-lite, Dataspatium)
- [docs/dataspatium-coordination.md](docs/dataspatium-coordination.md): what
  Kontroll and Dataspatium share and what more to coordinate, with the
  decisions that remain
- [docs/adr/](docs/adr/): architecture decision records (graph backend,
  opaque tokens, portable Cypher, vanilla web UI, repository strategy)
- [docs/security/](docs/security/): threat model, controls mapped to tests,
  the OWASP ASVS Level 2 checklist and how to run the scanners
- [docs/upstream/](docs/upstream/): drafts of the issue and pull request for
  IfcOpenShell (not sent)
- [spec/SOURCES.md](spec/SOURCES.md): the exact specification revisions the
  server is tested against

## Administration

Sign in at `/signin` with an administrator account and open `/admin` to manage
users and their project roles, projects and their BCF extension values, OAuth2
clients, sessions, the audit log, the optional request log and the server's
health checks. Every user has `/account` for their own password, applications
and sessions. The CLI (`uv run opencde --help`) does the same from a terminal,
and administration clients holding the `admin` scope can read the request log
at `/admin/api/requests`.

## Kontroll and Dataspatium

Kontroll (the server) and [Dataspatium](https://github.com/marwiss/Dataspatium)
(a data app that runs entirely in the browser) are developed to work together
as server and client. Dataspatium adds a Kontroll server as a source: it
discovers the APIs through `/foundation/versions`, signs in with OAuth2
authorization code and PKCE and registers itself as a public client when
dynamic registration is on, lists the project's models and documents, reads
and writes BCF issues with comments and viewpoints taken from its 3D view,
uploads datasets, files and workspace bundles through the Documents API,
queries the IFC graph with Cypher over Bolt when the operator exposes it, and
sends `X-Request-ID` on every request so that the request log here and the
log in the app show the same conversation. Apart from the graph queries and
the administration API, which are extensions outside the specifications,
everything Dataspatium does against the server goes through the three OpenCDE
APIs, so any other OpenCDE client works too, and Kontroll serves any OpenCDE
client. The client side is described in Dataspatium's README and its
documentation (`docs/kallor.md`, `docs/cad-bim.md`); the acceptance runs of
the pair are in [docs/acceptance.md](docs/acceptance.md) here.

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
columns) the style follows. The README exists in English and Swedish; the
documentation and the web UI are to be available in Swedish, Norwegian,
Danish, Finnish, Icelandic and English, with English always one of the
choices.

## Security

See [SECURITY.md](SECURITY.md) for how to report a vulnerability and what the
project does to stay secure.

## License

The server is licensed under the GNU Affero General Public License v3.0 or
later ([LICENSE](LICENSE)): it is server software, and the AGPL's network
clause keeps improvements to hosted instances open. The client library in
[client/](client/) is LGPL-3.0-or-later. Specification files under
[spec/](spec/) are © buildingSMART International and redistributed unmodified
for testing.
