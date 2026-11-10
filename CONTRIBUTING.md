# Contributing to Dataregium

Thank you for helping. Dataregium is a server for the buildingSMART OpenCDE
APIs, licensed under the GNU Affero General Public License v3.0 or later
([LICENSE](LICENSE)); the client library in [client/](client/) is
LGPL-3.0-or-later. Both licences let you change the code and pass it on
under the same terms, and contributions are taken in under those terms
(inbound = outbound). No contributor agreement is needed.

## Bug reports and suggestions

Open an issue on GitHub. Say which version of the server you run (the
`version` field of `GET /healthz` or `/.well-known/dataregium`), which client
you used, what you did, what happened and what you expected. Include the
`X-Request-ID` of a failing call when you have it; the server's request log
and your client's log share it. Attach no personal data and no secrets; a
small example (an IFC model, a BCF request body with made-up text) is enough.

For a security vulnerability do not open an issue: follow
[SECURITY.md](SECURITY.md).

When the server and a client disagree, the specification decides
(`spec/`, pinned revisions in [spec/SOURCES.md](spec/SOURCES.md)). Report a
specification problem, or a place where the specification is silent, as an
issue too.

## Code changes

Agree on the change in an issue first for anything beyond a small fix. Then
send a pull request against `main` that follows the house rules, which are
those of IfcOpenShell, so that contributing the server there stays possible:

- Code, comments, tests and commit messages are in English. Commit subjects
  are imperative and at most 50 characters; the body says why.
- Say in the commit body when a change was generated with an AI coding tool,
  and start new files written that way with
  `# This file was generated with the assistance of an AI coding tool.`
- `uv run ruff format .`, `uv run ruff check .` and
  `uv run ty check opencde client/opencde_client` are clean; no cosmetic
  changes to unrelated code.
- A new endpoint is route + schema + conformance test + security test + docs
  in one series of commits.
- The golden rules hold: Cypher takes parameters only, every query starts at the user node,
  nothing secret is logged, nothing client-provided lands in a file path,
  and everything that expires carries `expires_at`.
- Cypher stays portable between Neo4j and Memgraph (ADR 0003): no APOC, no
  `elementId()`/`id()` as keys, no Neo4j-only functions.
- Web pages are server-rendered with the design system in `opencde/ui/`
  and work without JavaScript.

Run the suites before you push:

```sh
uv run pytest                    # unit, conformance and security tests
uv run pytest -m integration     # Neo4j and Memgraph in testcontainers (Docker)
uv run pytest -m ui              # Playwright and axe-core (uv sync --group ui)
uv run poe security              # ruff, bandit and pip-audit; CI adds gitleaks, zizmor and Semgrep
```

## Translations

The README, the documentation and the web pages exist in English, Swedish,
Danish, Norwegian (Bokmål and Nynorsk), Finnish and Icelandic: the English
pages under `docs/en/`, the translations under `docs/<lang>/`. English is the
source, and a change to a page is made in all seven languages in the same
commit (`tests/unit/test_docs.py` checks that they keep up). This file stays in
English. Shared terms follow
the glossary that Dataregium and [Dataspatium](https://github.com/marwiss/Dataspatium)
keep together (`presets/i18n-shared.json` there); keep "viewpoint" and the
API names untranslated, and send corrections of a translation as an issue or
a pull request like any other change.

## Working with Dataspatium

Dataregium and Dataspatium are developed to work together but are separate
projects with different licences (AGPL here, PolyForm Strict there). Both
have the same copyright holder, who gave two permissions on 2026-11-05:
Dataregium may use Dataspatium's design (tokens, type, spacing, component
styles), which is why `opencde/ui/static/css/tokens.css` carries
Dataspatium's tokens under this project's licence and the components follow
Dataspatium's; and Dataspatium may use all of Dataregium's own code and
resources (the quick start, the sample model, anything else) under its own
licence. The licences are otherwise unchanged, and third-party material
keeps its own terms (the buildingSMART specification files, the Inter font,
the dependencies). Dataspatium's `docs/licenser.md` says the same. Keep the
shared pieces in step.
