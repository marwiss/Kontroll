# OWASP ASVS Level 2 checklist

Self-assessment against the OWASP Application Security Verification Standard
5.0 at Level 2, written by the developers on 2026-11-05. It is not an external
verification. Each chapter lists the Level 2 requirements that apply to this
server (paraphrased), the status and the evidence: a control in
[controls.md](controls.md) with its test, a document, or code. Known gaps are
collected at the end; they are tracked as *Later* in the project plan.

Status: **met** (control and test exist), **partly** (control exists with a
documented limitation), **not met** (planned or left to the operator),
**n/a** (the server has no such component).

## V1 Encoding and sanitization

| Requirement | Status | Evidence |
|---|---|---|
| Output encoding for HTML; no DOM injection of server data | met | Jinja2 autoescape, enhancement scripts use `textContent` only, strict CSP as defence in depth; `tests/ui` fails on console errors |
| Database queries never built from input | met | Cypher parameters only, enforced by the lint test `test_core_helpers::test_dialect_ddl_and_cypher_lint`; IFC labels validated as identifiers (`importer._safe`) |
| Query languages exposed to clients are parsed, not interpolated | met | OData: parser → AST → field whitelist → parameters, `test_odata` |
| File names and header values sanitised and encoded | met | `sanitize_filename`, RFC 8187 `attachment_header`, `test_bcf_helpers` |
| URLs from clients validated (scheme, host) before use | met | `validate_redirect_uri` (https, loopback, private-use schemes), callbacks and document references http(s) only |

## V2 Validation and business logic

| Requirement | Status | Evidence |
|---|---|---|
| Positive validation with bounds on every input | met | Pydantic v2 models with length, list and depth limits, finite numbers; unknown fields ignored per Foundation API 1.8 |
| Business rules enforced server-side | met | Topic values against extensions, exactly one camera, 409 on deleting a referenced viewpoint, duplicate guids, one transaction per write |
| Anti-automation on authentication and expensive operations | partly | Sign-in and token endpoints rate limited per address (`test_sign_in_is_rate_limited`); uploads capped per file (`max_upload_bytes`); no per-user storage quota yet |

## V3 Web frontend security

| Requirement | Status | Evidence |
|---|---|---|
| Content Security Policy without `unsafe-inline`, framing denied | met | `default-src 'none'` on API responses, `default-src 'self'; frame-ancestors 'none'` on pages; no inline scripts or styles; `X-Frame-Options: DENY` |
| Cookies `HttpOnly`, `Secure`, `SameSite=Strict` | partly | `test_web_signin::test_sign_in_sets_a_hardened_cookie_and_sign_out_removes_it`; the cookie has no `__Host-` prefix yet |
| CSRF protection on every state change from a browser | met | Signed, purpose-bound form tokens plus `Sec-Fetch-Site`/`Origin` checks, `test_csrf_protections_on_admin_forms`, `test_cross_site_posts_are_refused_and_next_cannot_leave_the_site` |
| Browser security headers on every response | met | `X-Content-Type-Options`, `Referrer-Policy: no-referrer`, `Permissions-Policy`, `Cross-Origin-Opener-Policy`, `Cross-Origin-Resource-Policy`, `test_headers_and_errors` |
| HSTS | met | Added by Caddy in the production overlay (`Caddyfile`) |
| No sensitive data in URLs | partly | Tokens and passwords travel in headers and bodies only; the Documents API specification puts a one-time link token in `upload_ui_url`/`select_documents_url`, so it is 256 bits, stored hashed, valid 10 minutes and the page also requires a browser session as the same user |

## V4 API and web service

| Requirement | Status | Evidence |
|---|---|---|
| JSON APIs validate content types and reject unsupported methods | met | FastAPI parsing with the spec error body, 405 on other methods; Schemathesis `unsupported_method` in the nightly run |
| CORS restricted; never credentials with a wildcard | met | `test_headers_and_errors::test_cors_is_bearer_only_never_credentials` |
| Consistent error format without internals | met | `{"message": …}` only, `test_headers_and_errors` |
| Authentication on every API operation; Bearer only | met | `test_foundation::test_current_user_requires_a_bearer_token`, security suite |
| Contract fuzzing: no 5xx, responses match the documented schemas, invalid input rejected | met | `tests/e2e/test_schemathesis.py` (every operation, positive and negative generation) |

## V5 File handling

| Requirement | Status | Evidence |
|---|---|---|
| Size limits on the bytes actually received | met | Streaming writes count bytes; chunked bodies cut off; `test_storage_stream_counts_bytes`, `test_chunked_body_over_the_limit_is_cut_off` |
| File type decided by content, not by the client | met | Magic bytes for images; documents stored and served as `application/octet-stream` |
| Client file names never reach the file system | met | UUID storage keys, `test_storage_keys_cannot_escape` |
| Uploaded content never executed or rendered | met | Attachments with `nosniff`; no templates from storage |
| Archive extraction bounded | met | `.ifczip` with exactly one `.ifc` and the size cap on unpacked bytes |
| Parsing of untrusted files isolated | met | IFC conversion in a worker process with time, memory and entity limits (`test_ifcgraph_convert`) |
| Antivirus scanning of uploaded files | not met | Left to the operator (scan the storage volume); no scanner integrated |

## V6 Authentication

| Requirement | Status | Evidence |
|---|---|---|
| Password length and strength policy, no composition rules | met | `auth/passwords.py`: at least 12 characters and zxcvbn score ≥ 3 with the user name as a known input, `test_password_policy_and_hashing` |
| Check against breached password lists | partly | zxcvbn's dictionaries of common passwords; no live breach-list lookup |
| Argon2id hashing | met | `pwdlib` with Argon2id, `test_password_policy_and_hashing` |
| Brute-force protection with generic messages | met | Rate limit per address, constant message for wrong user or password, disabled accounts refused (`test_disabled_user_cannot_sign_in_and_loses_tokens`) |
| Multi-factor authentication | not met | Passwords only; TOTP for the sign-in page is planned (*Later* in the plan). API clients never see passwords: they authenticate through OAuth2 against this sign-in page, so one MFA covers everything |
| Secure credential recovery | met | No self-service reset; an administrator issues a one-time password after re-authenticating, and the user must change it at the next sign-in |
| Re-authentication for sensitive operations | met | Own password required for password changes, resets, admin flag changes, secret rotation and deletion (`test_user_management`, `test_client_management_and_secret_rotation`) |
| Disabling an account ends its access | met | Tokens and sessions revoked when a user is disabled |

## V7 Session management

| Requirement | Status | Evidence |
|---|---|---|
| Server-side sessions with random identifiers, stored hashed | met | `web/sessions.py`, 256-bit cookie value, SHA-256 at rest |
| New session at sign-in; sign-out destroys it | met | `test_sign_in_sets_a_hardened_cookie_and_sign_out_removes_it` |
| Idle and absolute timeouts | met | `web_session_idle_seconds` and absolute expiry, swept by the cleaner |
| Users can see and end their sessions and grants | met | `/account`: sessions, applications, "sign out everywhere" |
| Administrators can end any session or grant | met | `/admin/sessions`, `opencde revoke` |

## V8 Authorization

| Requirement | Status | Evidence |
|---|---|---|
| Deny by default; object-level checks on every access | met | Every query starts at the user node and traverses `MEMBER_OF`; non-members get 404 (`test_topic_authorization_matrix`) |
| Function-level checks by role, server-side | met | Role × action matrix for projects, topics, comments, viewpoints, documents; `authorization` objects derived from the same rules |
| Administrative functions separated and protected | met | `/admin` needs the admin role on every route (`test_admin_pages_need_the_admin_role`) |
| Authorization decided in the same transaction as the change | met | Repository methods check and write in one transaction |
| Field-level exposure limited | met | Explicit response models; hashes and storage keys are in no response (`validate_documents`, conformance suite) |

## V9 Self-contained tokens

n/a: tokens are opaque references stored as hashes (ADR 0002); there are no
JWTs to validate.

## V10 OAuth and OIDC

| Requirement | Status | Evidence |
|---|---|---|
| Authorization code with PKCE `S256` only; no implicit or password grants | met | `test_pkce_is_mandatory_and_plain_is_refused` |
| Exact redirect URI matching; loopback exception per RFC 8252 | met | `test_unregistered_redirect_uri_is_shown_not_followed`, `test_loopback_port_may_vary_but_host_may_not` |
| `state` required; `iss` in the response | met | `test_state_is_required_and_unknown_scope_is_refused`, `test_public_client_flow_with_pkce` |
| One-time codes bound to client, redirect URI and verifier | met | `test_code_is_single_use_and_replay_revokes_tokens`, `test_wrong_verifier_wrong_client_and_wrong_redirect_are_invalid_grant` |
| Refresh token rotation with reuse detection | met | `test_refresh_rotates_and_reuse_revokes_the_family` |
| Revocation (RFC 7009) | met | `test_revocation` |
| Client authentication; public clients without secrets | met | `test_client_authentication_failures` |
| Token responses not cacheable | met | `test_token_response_is_never_cached_and_has_spec_fields` |
| Consent screen names the client and the redirect target; the user can refuse | met | `test_deny_redirects_with_access_denied`, `auth/templates` |
| Dynamic registration restricted | met | Off by default; https or loopback redirects only when on |
| Sender-constrained tokens (DPoP, mTLS) | not met | Level 3 item; listed under *Later* in the plan |
| Compliance tested with an external tool | not met | OAuch run described in [pentest-howto.md](pentest-howto.md) §4, to be done before the first production deployment |

## V11 Cryptography

| Requirement | Status | Evidence |
|---|---|---|
| Approved algorithms and CSPRNG | met | `secrets` for codes, tokens, cookies and client secrets; Argon2id; SHA-256 for token hashes; HMAC-signed form tokens (`itsdangerous`) |
| Secrets not in code or images | met | `OPENCDE_SECRET_KEY` and the database password from the environment or Docker secrets, generated by `opencde init`; `.env` ignored by git; gitleaks in CI |
| Key rotation | partly | Rotating `OPENCDE_SECRET_KEY` invalidates form tokens and browser sessions, nothing else; documented as an operator step in `docs/deploy/vps-caddy.md`; no dual-key rollover |

## V12 Secure communication

| Requirement | Status | Evidence |
|---|---|---|
| TLS 1.2 or 1.3 only, valid certificates, HSTS | met | Caddy in `compose.prod.yaml`; production refuses an http public URL (`test_settings`); testssl.sh run in [pentest-howto.md](pentest-howto.md) §5 before production |
| Internal connections protected | met | Database only on the private compose network; `neo4j+s://` for an external database (`docs/deploy/cloud-aura.md`) |
| Forwarded headers trusted from known proxies only | met | `OPENCDE_TRUSTED_PROXIES` |

## V13 Configuration

| Requirement | Status | Evidence |
|---|---|---|
| Secure defaults; the server refuses unsafe production settings | met | `test_settings`: https, database password and secret key required in production, localhost redirects refused |
| Dependencies pinned, audited and updated | met | `uv.lock`, pip-audit, Dependabot with a 7-day cooldown, actions pinned by SHA and checked by zizmor |
| Hardened container | met | Non-root, read-only root file system, dropped capabilities, `no-new-privileges`, Trivy scan with SBOM on release |
| Operational checks | met | `opencde doctor` (database, schema, clock, public URL, headers, storage) |
| Administrative interface can be isolated | met | Separate sign-in and role; `OPENCDE_ADMIN_UI_ENABLED=false` removes it from a public instance (administer through the CLI instead), or restrict `/admin` to internal addresses at the proxy |
| No third-party code on production pages | met | The server's pages load nothing from other origins; the interactive API documentation (`/docs`, Swagger UI from a CDN) is served only outside production unless `OPENCDE_API_DOCS_ENABLED=true` |

## V14 Data protection

| Requirement | Status | Evidence |
|---|---|---|
| No sensitive data in logs | met | Redaction processor and no bodies logged, `test_passwords_and_codes_never_reach_the_logs`, `test_logging` |
| Sensitive responses not cached | met | `Cache-Control: no-store` on every non-static response |
| Credentials and tokens hashed at rest | met | Argon2id and SHA-256 |
| Data minimisation | met | Event values clipped; response models carry only specification fields |
| Backups protected | partly | Application-level export (ADR 0006) into the operator's backup volume; the server does not encrypt it, so the volume or the archive must be encrypted by the operator |
| Users can be removed | met | Admin UI deletes users (after re-authentication) and revokes their tokens |

## V15 Secure coding and architecture

| Requirement | Status | Evidence |
|---|---|---|
| Documented architecture and threat model | met | `docs/adr/`, [threat-model.md](threat-model.md), `docs/graph-schema.md` |
| Static analysis and dependency checks in CI | met | ruff `S` rules, Bandit, Semgrep (`p/python`, `p/owasp-top-ten`, `p/secrets`), pip-audit |
| No dangerous functions or deserialisation of untrusted data | met | JSON only; no `pickle`, `eval` or shell interpolation (Bandit) |
| Race conditions on one-time secrets | met | Code and refresh token redemption are single transactions with reuse detection |
| Separation of browser UI and API trust boundaries | met | Cookies only for pages, bearer tokens only for the API; neither accepts the other |

## V16 Security logging and error handling

| Requirement | Status | Evidence |
|---|---|---|
| Structured logs with a request identifier and time in UTC | met | structlog JSON, `RequestIDMiddleware` |
| Security events logged (sign-in, token issue, revocation, admin actions) | met | `AuditEvent` nodes, shown in `/admin/audit` with CSV export |
| Errors handled without leaking internals; unexpected errors logged | met | `errors.py`: spec body, 5xx logged with the request id |
| Clock correctness for expiry checks | met | `opencde doctor` compares the clock with an NTP source |
| Log protection, forwarding and alerting | not met | Left to the operator (compose logging driver, SIEM) |

## V17 WebRTC

n/a.

## Known gaps

| Gap | Plan |
|---|---|
| No multi-factor authentication on the sign-in page | TOTP (pyotp) as a later stage; one implementation covers browser users and OAuth2 clients |
| Session cookie without the `__Host-` prefix | Rename the cookie when the next cookie change is made (requires https everywhere, which production has) |
| No live breached-password check | Optional k-anonymity lookup against a breach API as a setting |
| No per-user storage quota | Add `max_storage_bytes_per_user` when multi-tenant use begins |
| No sender-constrained tokens | DPoP (RFC 9449) as a later stage |
| No antivirus scanning | Operator's choice on the storage volume |
| Backups not encrypted by the server | Encrypt the backup volume or wrap `opencde backup` with `age`/`gpg` in the sidecar |
| OAuch and testssl.sh not yet run against a deployment | Run before the first production deployment; record the reports |
| No external penetration test | Optional, at the owner's discretion, after the above |
