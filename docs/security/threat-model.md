# Threat model

Status: covers stages 0–9. Each stage adds the assets, threats and controls
it introduces, `controls.md` maps every control to a test, and
`asvs-checklist.md` records the OWASP ASVS Level 2 self-assessment.

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
| Stored content disguised as an image | HTML or script uploaded as a snapshot and served back | Magic bytes must match the declared type; images served as `image/*` with `nosniff`; size cap before decoding | 4 |
| Uploaded files rendered by a browser | Stored XSS through a document download | Documents and snippets are always `application/octet-stream` attachments with sanitised, RFC 8187 encoded names; never rendered | 4, 5 |
| Body size limit bypassed | Chunked transfer without `Content-Length`; a binary route used for JSON floods | Bytes are counted as they arrive; only the binary routes are exempt and they count against `max_upload_bytes` themselves | 4 |
| Malicious documents | Zip bombs, path traversal, parser exploits | Server-generated ids, size limits, bounded extraction, parsing in a sandboxed worker | 5, 9 |
| Leaked Documents API link | `upload_ui_url` or `select_documents_url` seen in a log, history or shoulder-surfed | 256-bit token stored hashed, 10-minute validity, single flow, and the page also requires a browser session as the same user; API-side URLs use a public id plus the bearer token | 5 |
| Callback abuse | Server made to fetch an attacker's URL (SSRF), open redirect through the callback | The server never fetches the callback; only http(s) URLs are accepted and the browser is redirected with URL-encoded parameters; the callback has its own expiry | 5 |
| Incomplete or oversized uploads | Parts larger than announced, totals that do not add up, abandoned parts filling the disk | Exact range check per part, size verified at assembly, SHA-256 recorded, parts and sessions expire and are swept with their files | 5 |
| Browser session attacks | Fixation, CSRF, theft, privilege escalation | Random hashed cookie minted at sign-in, `HttpOnly`, `SameSite=Strict`, `Secure` on https, idle and absolute expiry, signed form tokens plus `Sec-Fetch-Site`/`Origin` checks, role checks on every page | 5, 6 |
| Elevation to administrator | A member reaching `/admin`; a stolen admin session used for resets or secret rotation; an administrator locked out | Admin role checked on every admin route (HTML 404 otherwise); dangerous actions need the administrator's own password again; administrators cannot disable, demote or delete themselves; every action audited | 6 |
| Secrets exposed through the UI | Client secrets or generated passwords readable later | Shown once at creation or rotation, stored hashed; the settings page redacts configuration secrets | 6 |
| Compromise through the deployment | Database reachable from the internet; secrets baked into the image; privileged container; forged `X-Forwarded-For` | Database only on the private compose network; secrets from `.env` or Docker secrets generated by `opencde init`; non-root, read-only container with dropped capabilities; forwarded headers trusted only from `OPENCDE_TRUSTED_PROXIES`; image scanned with an SBOM on every release | 8 |
| Backups as a leak or a loss | Archive readable by others; a restore over live data | Application-level export into the operator's backup volume (encryption at rest is the operator's); `opencde restore` stops at a non-empty database unless forced; manifest records the schema version | 8 |
| Hostile IFC file | Parser crash, memory exhaustion, hang, entity flood | Conversion in a separate worker process with time, memory and entity limits; a failure is recorded on the `IfcModel` node and the server is unaffected; labels and relationship names validated before they reach Cypher | 9 |
| Third-party code on a server page | A compromised CDN serving Swagger UI runs script in the server's origin | The interactive API documentation is off in production unless enabled; it has its own Content-Security-Policy listing the CDN; every other page loads same-origin resources only; CORS applies to the API paths alone so pages are never readable cross-origin | 11 |
| Stale base image | Fixable vulnerabilities in the distribution or in pip's vendored libraries | The runtime stage applies the distribution's security updates and removes pip; Trivy fails the release and the nightly scan on fixable HIGH or CRITICAL findings | 8, 11 |
| Self-registered public clients | Anyone registers a client with a convincing name and lures users into consenting | Registration is off by default and rate limited; the consent page names the client and the host it redirects to; public clients need PKCE and exact redirect URIs like every client; administrators can disable or delete clients in `/admin` | 11 |
| The request log as a store of personal data or secrets | Query strings with names, tokens in headers, bodies with issue texts | Off by default; entries hold the path without its query string, no headers and no bodies; retention bounded by `request_log_retention_hours`; read access only for administrators, on the page by session and on `/admin/api/requests` by a bearer token that holds the explicitly requested `admin` scope | 11 |
