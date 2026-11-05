# Threat model

Status: skeleton (stage 0). Each stage adds the assets, threats and controls
it introduces, and `controls.md` maps every control to a test.

## Assets

| Asset | Where | Why it matters |
|---|---|---|
| User credentials (Argon2id hashes) | graph `User` | Account takeover gives access to every project of that user |
| OAuth2 client secrets, codes, access and refresh tokens (SHA-256 hashes) | graph `Client`, `AuthorizationCode`, `AccessToken`, `RefreshToken` | Impersonation of users or clients |
| Project data: topics, comments, viewpoints, snapshots, document metadata | graph + storage | Confidential building information from several organisations |
| Documents (IFC models and other files) | storage backend | Large, confidential, potentially malicious input to parsers |
| Audit log | graph `AuditEvent` | Evidence after an incident |
| Configuration and secrets | `.env`, Docker secrets | Full compromise if leaked |

## Actors

Anonymous internet user; authenticated user of another project; authenticated
user of the same project with a lesser role; a registered OAuth2 client (or
someone holding its secret); an administrator; the hosting provider and
anyone who can read logs or backups; a malicious document author.

## Trust boundaries

Internet → Caddy (TLS) → API → graph database and storage, all on a private
network. The browser (sign-in, consent, document selection, admin) is a
separate boundary from API clients using Bearer tokens.

## Threats and controls (STRIDE, grows per stage)

| Threat | Example | Control | Stage |
|---|---|---|---|
| Information disclosure through error responses | Stack traces, echoed input, internal ids | One error body `{"message"}`; validation errors name fields, never values; 5xx logged with request id only | 0 |
| Information disclosure through logs | Tokens or passwords in log lines | Redaction processor on every log event; no request or response bodies logged | 0 |
| Tampering via oversized or malformed bodies | Memory exhaustion | Body size limit before parsing (413); streaming with byte counting for uploads | 0, 5 |
| Clickjacking, MIME sniffing, referrer leaks | Pages framed by an attacker; `code` leaked in Referer | CSP `frame-ancestors 'none'`, `X-Content-Type-Options`, `Referrer-Policy: no-referrer` on every response | 0 |
| Spoofing of the request id | Log injection through `X-Request-ID` | Only `[A-Za-z0-9._-]{1,128}` accepted; otherwise minted | 0 |
| Elevation through configuration mistakes | http in production, empty database password | Settings refuse to start | 0 |
| Supply chain | Compromised dependency or action | `uv.lock`, pip-audit, Dependabot, actions pinned by SHA, zizmor | 0 |
| Spoofing of users and clients, replay, mix-up, CSRF on consent | | PKCE S256 only, exact redirect_uri, `state`, `iss`, one-time codes, hashed tokens, rotation with family revocation, CSRF tokens | 2 |
| Broken object level authorization | Reading another project's topic by guid | Every query starts at the user node and traverses MEMBER_OF; 404 for foreign objects | 3 |
| Injection through OData | `$filter` crafted to alter Cypher | Parser → AST → whitelist → parameters | 1, 3 |
| Malicious documents | Zip bombs, path traversal, parser exploits | Server-generated ids, size limits, bounded extraction, parsing in a sandboxed worker | 5, 9 |
| Admin UI session attacks | Fixation, CSRF, privilege escalation | Server-side sessions, rotation at login, `SameSite=Strict`, role checks on every route | 6 |
