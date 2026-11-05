# Security policy

Security is the first requirement of this server: it holds building models,
issue data and user credentials for several organisations at once.

## Reporting a vulnerability

Please do not open a public issue for a security problem. Report it privately
through GitHub's "Report a vulnerability" button on this repository (Security
→ Advisories). Include the version, what you observed, and how to reproduce
it. You will get an acknowledgement within a few days and a fix or a
mitigation plan as soon as the problem is understood.

## What we do

- Threat model, controls and their tests are documented in `docs/security/`.
- Every release runs the security test suite (`tests/security/`), schema
  fuzzing (Schemathesis), dynamic scanning (OWASP ZAP), OAuth2 compliance
  checks (OAuch), static analysis, dependency and container scanning.
- Dependencies are pinned in `uv.lock` and updated by Dependabot.
- The container runs as an unprivileged user on a read-only file system; the
  database is never exposed outside the private network.

## Supported versions

Pre-release (0.x): only the latest release receives fixes.
