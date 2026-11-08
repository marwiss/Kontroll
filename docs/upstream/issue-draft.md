# Draft: issue for IfcOpenShell maintainers

Status: **draft, not sent**. The project owner reviews, adapts and posts it
(or decides not to). Nothing in this folder is sent automatically.

---

**Title:** OpenCDE server: a rewrite of `src/opencdeserver` (Foundation 1.0,
BCF 3.0 and 2.1, Documents 1.0): where should it live?

## Background

`src/opencdeserver` is the 2023 research prototype of an OpenCDE server
(Foundation API, BCF API 3.0, Documents API) on FastAPI and Neo4j, written for
Solibri tests. It no longer runs: its dependencies are obsolete (Pydantic 1,
py2neo, passlib, APOC TTL) and a review found some sixty defects in start-up,
data loss, security and specification conformance. Rather than patch it, I
rewrote it from scratch, keeping the functionality and the idea (BCF plus an
IFC graph for digital inspection plans).

## What the rewrite is

- Foundation API 1.0, BCF API 3.0 (all 40 operations) and 2.1, and Documents API 1.0
  (all 13 operations), tested against the pinned buildingSMART JSON schemas and
  the Documents swagger, with the deviations between the README examples and the
  schemas documented.
- OAuth2 per RFC 9700 / OAuth 2.1: authorization code with PKCE `S256` only,
  exact redirect URIs with the RFC 8252 loopback rule, one-time codes, opaque
  hashed tokens, rotating refresh tokens with reuse detection, RFC 7009
  revocation, optional dynamic client registration (spec 2.2.3).
- Graph database through the official `neo4j` driver, dialect-neutral Cypher
  so that the same code runs on Neo4j 5.26 LTS and Memgraph (both in CI).
- A web administration UI (users, projects, clients, sessions, audit log) as
  server-rendered pages with vanilla JavaScript enhancements, no framework.
- An optional IFC-graph module (IfcOpenShell in a limited worker process).
- A Python client library (`opencde-client`: discovery, PKCE, BCF, Documents).
- A browser client developed alongside it, [Dataspatium](https://github.com/marwiss/Dataspatium)
  (PKCE as a public client, BCF issues from a 3D view, Documents API, graph
  queries), whose live test suites run against the server.
- Tests: unit, conformance, security, integration on both databases, an
  end-to-end scenario, Playwright with axe-core, Schemathesis; nightly ZAP.
- Deployment: one compose file with overlays (Caddy with automatic TLS,
  tunnel, Memgraph), a multi-arch image with SBOM and Trivy scan, backups.
- Documentation: inventory of the prototype's functions and their status,
  threat model, controls mapped to tests, ASVS checklist, deployment guides,
  client guide with runnable examples.

Python 3.11 or newer (the project's baseline), `uv`, `ruff`, `ty`. Dependencies
and their versions are listed in the repository's `pyproject.toml`.

The code lives today in <https://github.com/marwiss/Dataregium> (branch `main`).

## Licensing

The prototype was accepted into the repository in 2024 under AGPL-3.0 as a
sub-folder with its own LICENSE. The rewrite keeps **AGPL-3.0-or-later** for the
server, a deliberate choice for server software (network clause). The client
library is **LGPL-3.0-or-later** so that it can join `src/bcf`. `AGENTS.md`
mentions LGPL and GPL only, so I want to confirm that an AGPL sub-folder is
still acceptable before preparing a pull request.

## How I would contribute it

One pull request that replaces `src/opencdeserver`, split into clean,
individually green commits (scaffold → graph core → Foundation API → BCF API →
Documents API → admin UI → tests → docs), each marked as AI-assisted in the
commit body as `AGENTS.md` asks, with `# This file was generated with the
assistance of an AI coding tool.` at the top of the generated files. The client
library would be a separate, smaller pull request against `src/bcf`.

Integration tests need Docker (the database runs in a container through
testcontainers); the unit, conformance and security suites do not.

## Questions

1. Is a rewrite of this size welcome in `src/opencdeserver`, or would you
   rather see the server stay in its own repository with only the client
   library contributed?
2. Is AGPL-3.0-or-later for the server sub-folder still acceptable?
3. How should the Docker-dependent tests be wired into your CI (a separate
   job that is allowed to skip when Docker is absent, or not at all)?
4. Any constraints on dependencies (`fastapi`, `neo4j`, `pydantic-settings`,
   `structlog`, `pwdlib[argon2]`, `itsdangerous`, `slowapi`, `odata-query`)?
