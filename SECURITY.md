# Security policy

Security is the first requirement of this server: it holds building models,
issue data and user credentials for several organisations at once. The policy
is the same as Dataspatium's; the two projects are developed as a pair and
released with the same numbers.

## Reporting a vulnerability

Please do not open a public issue for a security problem. Report it privately
through GitHub's "Report a vulnerability" button on this repository (Security
→ Advisories). Include the version, what you observed, and how to reproduce
it. You will get an acknowledgement within a few days and a fix or a
mitigation plan as soon as the problem is understood.

## What we do

- Every security control has at least one automated test in `tests/security/`;
  the suite is the list of controls. What the server stores about people, and
  for how long, is in the README ("Personal data").
- Every push runs the security test suite (`tests/security/`), contract fuzzing
  with Schemathesis, browser tests, static analysis (ruff, Bandit, Semgrep) and
  the checks for known vulnerabilities and leaked secrets (pip-audit, gitleaks).
  Every night dynamic scanning (OWASP ZAP), a longer Schemathesis run and an image
  scan (Trivy) run as well; every release scans its image and ships an SBOM.
- OAuth2 compliance (OAuch) and TLS (testssl.sh) are checked by hand against a
  deployment; they are the operator's steps before production and have not been
  run against a production deployment yet. Known gaps: no second factor on the
  sign-in page, no sender-constrained tokens (DPoP), no breached-password check,
  no per-user storage quota, backups not encrypted by the server, no external
  penetration test.
- Dependencies are pinned in `uv.lock` and updated by Dependabot.
- The container runs as an unprivileged user on a read-only file system; the
  database stays on the private network unless an administrator publishes its
  port on purpose (`docs/en/deploy/bolt.md`).

## Supported versions

One release per major number is kept; only the latest release of the 2 series
receives fixes.
