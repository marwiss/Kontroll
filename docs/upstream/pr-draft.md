# Draft: pull request description for IfcOpenShell

Status: **draft, not sent**. To be used only after the maintainers have
answered the issue in `issue-draft.md` and the project owner has approved the
pull request. The commit series below is the plan for splitting this
repository's history into reviewable steps; each commit must be green on its
own.

---

**Title:** Replace the OpenCDE server prototype with a specification-driven rewrite

## Summary

Replaces the 2023 prototype in `src/opencdeserver` with a new implementation
of the buildingSMART OpenCDE APIs: Foundation API 1.0, BCF API 3.0 and 2.1, and
Documents API 1.0, with a web administration UI and an optional IFC-graph
module. Same purpose and functionality as the prototype (see
`docs/inventory.md` for the function-by-function mapping), modern
dependencies, specification conformance tests and security as the first
requirement. Discussed in #<issue number>.

## Commit series

1. `Add the OpenCDE server scaffold`: packaging (`uv`), settings with safe
   defaults, container, compose, CI configuration, licences.
2. `Add the graph core and cross-cutting protection`: Neo4j/Memgraph dialects,
   schema, cleanup of expiring nodes, OData compiler, security headers, body
   limits, rate limiting, logging with redaction, audit log, CLI.
3. `Add the Foundation API and OAuth2`: discovery, PKCE authorization code
   flow, token endpoint, refresh rotation, revocation, dynamic registration,
   sign-in and consent page, design system.
4. `Add the BCF API`: projects, extensions, topics, comments, viewpoints,
   related topics, document references, files, snippets, documents, events,
   authorization objects.
5. `Add the Documents API`: upload and selection flows with their pages,
   multipart upload, versions and queries with ETag.
6. `Add the web administration UI`: users, projects, clients, sessions, audit
   log, settings, account page.
7. `Add the IFC-graph module`: worker process, batched import, component
   linking.
8. `Add tests and security tooling`: conformance against the buildingSMART
   schemas, security suite, integration on Neo4j and Memgraph, end-to-end
   scenario, Playwright with axe-core, Schemathesis, ZAP configuration.
9. `Add the documentation`: inventory, architecture decisions, threat model,
   controls, ASVS checklist, deployment guides, client guide and examples.

## Testing

```sh
cd src/opencdeserver
uv sync
uv run pytest                          # unit, conformance, security
uv run pytest -m "integration or e2e"  # needs Docker
```

## Licensing

Server: AGPL-3.0-or-later (as the prototype, with its own LICENSE in the
sub-folder). Client library (`opencde_client`, separate pull request):
LGPL-3.0-or-later.

## Notes for reviewers

- The code was written with the assistance of an AI coding tool, reviewed and
  tested by the author; every commit body and every generated file says so, as
  `AGENTS.md` asks.
- Behaviour follows the pinned specification revisions in `spec/SOURCES.md`;
  the places where the specification's README examples and JSON schemas
  disagree are listed in `docs/inventory.md` §10 with the decision taken.
- No cosmetic changes outside `src/opencdeserver`.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
