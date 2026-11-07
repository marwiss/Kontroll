# Personal data and retention

What a Kontroll server stores about people, for how long, and who can see
it. This is the server's half of a page shared with Dataspatium; the app's
half (what it keeps in the browser and what it sends) is in Dataspatium's
documentation. Operators who run Kontroll for others are the controllers of
this data; this page gives them the facts for their own records.

## What is stored

| Data | Where | Contains | Kept |
|---|---|---|---|
| User accounts | `User` nodes | user name, full name, e-mail (optional), Argon2id password hash, administrator flag, creation time, last sign-in | Until an administrator deletes the account |
| Project memberships | `MEMBER_OF` relationships | user, project, role | Until removed |
| OAuth2 tokens | `AuthorizationCode`, `AccessToken`, `RefreshToken` nodes | SHA-256 hashes (never the tokens), user, client, scope, times | Codes 60 s, access tokens 1 h, refresh tokens 30 days (`OPENCDE_*_TTL_SECONDS`); deleted by the cleaner when expired or revoked |
| Browser sessions | `WebSession` nodes | user, creation and last-activity times, the client address at sign-in | 8 hours, or 30 minutes of inactivity; deleted on sign-out |
| Failed sign-ins | `SignInThrottle` nodes | a hash of the user name, the number of failures, when the next attempt is allowed | a day after the last failure; a success removes it |
| OAuth2 clients | `Client` nodes | name, description, URL, redirect URIs, hashed secret, `software_id`/`software_version`, who created it | Until deleted; self-registered clients unused for 30 days are deleted with their tokens |
| BCF data | `Topic`, `Comment`, `Viewpoint`, `Event` and related nodes | titles, descriptions and comments written by users, user names as authors and assignees, times, snapshot images, component references | Until the topic, comment or project is deleted |
| Documents | `Document` and `DocumentVersion` nodes, files under `OPENCDE_DATA_DIR` | title, file name, size, SHA-256, uploader, time; the file itself (which may contain personal data, such as names in an IFC model's owner history) | Until the version or project is deleted; backups keep copies for as long as the operator keeps backups |
| IFC graph | `IfcModel` nodes and the entities of each imported model | the content of the IFC file as graph data, including `IfcOwnerHistory` for the project; with `OPENCDE_IFCGRAPH_LOSSLESS`, the default, all of the file, with its header and every owner history | Superseded or failed models are removed by `opencde ifcgraph prune`; otherwise with the document version |
| IFC validation | `IfcValidation` nodes below document versions | how many issues the file has and when it was checked, and up to 10,000 issues, whose messages may quote lines of the file | With the document version or the project |
| Audit log | `AuditEvent` nodes | what happened (sign-in, token issued, client registered, role changed …), who did it, the client address, time, request id | Not expired by the server; administrators can export it as CSV and an operator deletes it according to their own policy |
| Request log (opt-in) | `RequestLog` nodes | method, path without query string, operation, status, timing, byte counts, request id, user or client id; never headers, bodies or tokens | `OPENCDE_REQUEST_LOG_RETENTION_HOURS` (72 by default); off unless `OPENCDE_REQUEST_LOG_ENABLED=true` |
| Upload and selection sessions | `UploadSession`, `UploadPart`, `SelectionSession` nodes and temporary part files | who started the flow, which files, callback URL, times | 24 hours for uploads, 10 minutes for the page links; cleaned by the server |
| Server logs | the container's standard output (JSON lines) | request id, path, status, timing, user id or client id, the client address from the trusted proxy; never bodies, tokens, codes or passwords | As long as the operator keeps container logs |

Backups made by `opencde backup` or the `backup` service contain all of the
above except the server logs, encrypted or not as the operator chooses
([deploy/backup.md](../deploy/backup.md)).

## Who can see what

- Members of a project see its topics, comments, viewpoints and documents
  through the APIs; the role decides what they may change. Users outside a
  project cannot tell that it exists (404).
- Administrators see every user, project, client, session, the audit log and,
  when it is on, the request log, on the pages under `/admin` and, with a
  bearer token holding the `admin` scope, through `/admin/api`.
- Every user sees their own account, applications and sessions at `/account`
  and can revoke them.
- Nobody sees passwords, secrets or tokens: the server stores hashes only and
  shows a new secret once, at creation.
- Anyone can read `/.well-known/kontroll`, `/foundation/versions`,
  `/foundation/1.0/auth` and `/healthz`; they contain configuration, never
  people.

## Rights and operations

- **Delete a person**: delete the account in `/admin/users` (or with
  `opencde user delete`); their sessions and tokens go with it. Their name
  stays on topics and comments they wrote, as the BCF data of the project;
  delete or edit those through the API or delete the project.
- **Export**: the audit log exports as CSV; BCF and document data export
  through the APIs (a client such as Dataspatium can save a project as
  BCFzip); `opencde backup` writes the whole database.
- **Incident**: `opencde revoke --all` ends every session and token; rotate
  the database password and the secret key afterwards
  ([controls.md](controls.md)).
- **Minimise**: leave the request log off unless you are debugging a client,
  keep `OPENCDE_DYNAMIC_CLIENT_REGISTRATION` off unless you need it, and do
  not publish the database port ([deploy/bolt.md](../deploy/bolt.md)).

## In Dataspatium

The app keeps the server's address, the client id it registered, the user's
tokens for the session and a log of its calls (with request ids) in the
browser; it never stores the password. Which of that leaves the browser, and
how to clear it, is in [Dataspatium's own page on personal data](https://github.com/marwiss/Dataspatium/blob/main/docs/en/sakerhet.md).
