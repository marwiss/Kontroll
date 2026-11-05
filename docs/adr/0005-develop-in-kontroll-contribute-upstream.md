# ADR 0005: Develop in marwiss/Kontroll, contribute to IfcOpenShell as one PR

Status: accepted (2026-11-05)

## Context

The 2023 prototype lives in IfcOpenShell (`src/opencdeserver`) as an AGPL
sub-tree accepted in 2024 (PR #4289), and in this repository. IfcOpenShell
asks for small, focused pull requests, but a rewrite cannot be reviewed as a
series of independent small PRs against the old code.

## Decision

The rewrite is developed here, with its own CI and releases, replacing the old
code in this repository (kept in history). When the server is stable the plan
is checked with the IfcOpenShell maintainers; if they want it, the server moves
to `src/opencdeserver` and `client/` to `src/bcf` as one combined PR made of
clean, individually green commits, each marked as AI-assisted where applicable.
Until then this repository follows IfcOpenShell's `AGENTS.md` conventions
(ruff, 120 columns, commit style, AI attribution) so the move needs no
reformatting.

## Consequences

- Fast iteration and the freedom to run heavy security scans in our own CI.
- Two homes for a while; IfcOpenShell's copy stays the 2023 prototype until
  the PR lands.
- The server stays AGPL-3.0 (server software, network clause); the client
  library is LGPL-3.0-or-later so it can join the LGPL `bcf` package.
