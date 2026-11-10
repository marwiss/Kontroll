# Visual acceptance with independent clients

The automated suites (unit, conformance, security, integration on Neo4j and
Memgraph, the end-to-end scenario with the Python client, Playwright) prove
that the server follows the pinned specifications. This checklist covers what
they cannot: real clients written by other people, used by hand, in both
directions (the client writes and the server shows it; the server has data and
the client shows it). Run it before a release that clients will depend on and
record the outcome in the results table at the end.

Rule of the project: when a client and the specification disagree, the
specification wins. The server is not patched to suit a client; the deviation
is written down under *Client deviations* as a draft report for the client's
maintainers, and the project owner decides whether and how to send it.

## 1. Preparation

### 1.1 A reachable server

| Client | Server URL that works |
|---|---|
| Browser clients on the same machine (Dataspatium, ifc-lite) | the development stack on `http://127.0.0.1:8000` |
| Desktop clients on the same machine (Bonsai) | `http://127.0.0.1:8000` when the client accepts http; otherwise a tunnel |
| Anything on another machine | a public https URL through a tunnel ([docs/en/deploy/tunnel.md](en/deploy/tunnel.md)) or a deployed server |

Start the development stack and load the demonstration data:

```sh
docker compose up -d --build
docker compose exec api opencde seed
```

`seed` prints the demo users and their one-time passwords, the ids of the
projects *Building permit* and *Demolition permit*, a public client and a confidential
client. The example model `tests/fixtures/three_walls_gtin.ifc` (three walls
with GUIDs `1Xezbq735AdBO_4DerG66G`, `3eT96F_cnDsOufCEsotwtp`,
`3k3LbXmTfDWODxdSuyCGYE`) is the model to open in the clients.

### 1.2 One OAuth2 client per test client

Every client needs its own registration with the exact redirect URI it uses
(`uv run opencde client create --help`, or the admin UI under *Clients*):

```sh
uv run opencde client create "Bonsai"      --public --redirect-uri http://127.0.0.1/callback
uv run opencde client create "Dataspatium" --public --redirect-uri http://127.0.0.1:8080/oauth-callback.html
```

Rules the server applies (RFC 8252 §7.3, RFC 9700): `https` URIs match
exactly; `http://127.0.0.1/…` and `http://[::1]/…` match exactly except for the
port, which may vary; `http://localhost/…` is accepted only with
`OPENCDE_ALLOW_LOCALHOST_REDIRECTS=true` in `.env` (`opencde init --dev` writes
it; production refuses it); private-use schemes of native apps are accepted. There are
no wildcards. To find out which redirect URI a client uses, start its sign-in:
the authorization request opens in the browser and its `redirect_uri` query
parameter is visible in the address bar (the sign-in page refuses an
unregistered one and says so without redirecting).

Browser clients call the API cross-origin. `OPENCDE_CORS_ORIGINS` defaults to
`*` (bearer tokens only, never cookies), which is right for tests; a production
server lists its clients' origins instead.

### 1.3 What every sign-in must look like

- The server's sign-in page names the client and the host it will redirect to.
  PKCE `S256` is mandatory, so a client that omits `code_challenge` is refused
  on the sign-in page, not after.
- After consent the browser lands on the client's redirect URI with `code`,
  `state` and `iss`. The client exchanges the code once; a second exchange of
  the same code is refused and revokes what the first one issued.
- Access tokens expire after one hour by default. A client that stays open
  longer must refresh silently; the refresh token rotates every time.
- The *Sessions* page of the admin UI (and `/account` for the user) lists the
  client's grant; revoking it there must make the client ask the user to sign
  in again.

### 1.4 The reference client

The Python client ships a small command line that doubles as the second party
in every two-way check:

```sh
uv run python -m opencde_client --server http://127.0.0.1:8000 --client-id <public client id> login
uv run python -m opencde_client --server http://127.0.0.1:8000 --client-id <public client id> projects
uv run python -m opencde_client --server http://127.0.0.1:8000 --client-id <public client id> topics <project id>
uv run python docs/examples/create_topic.py http://127.0.0.1:8000 <public client id> <project id> snapshot.png
uv run python docs/examples/upload_document.py http://127.0.0.1:8000 <public client id> tests/fixtures/three_walls_gtin.ifc
```

`create_topic.py` creates a topic with a viewpoint that selects the three walls,
colours one of them red and carries the PNG as snapshot, and adds a comment that
refers to the viewpoint. `upload_document.py` uploads a file through the
Documents API; the server's page in the browser asks for the title, the version
and the project, and the finished document is what makes the model appear in
`files_information`.

## 2. Checklist A: openBCF in Bonsai (Blender)

Tested with Blender 4.5 and Bonsai 0.8.3 (record the versions you use). Open
`tests/fixtures/three_walls_gtin.ifc` in Bonsai first. Connect to the server
as Bonsai's BCF documentation describes; the client reads
`/foundation/versions` and `/foundation/1.0/auth` (or the legacy aliases
`/bcf/versions` and `/bcf/3.0/auth`, which the server also serves) and opens
the browser for sign-in.

| # | Step | Expected |
|---|---|---|
| A1 | Connect and sign in as a demo user | Browser shows the server's sign-in page naming "Bonsai"; after consent Bonsai shows the signed-in user and the projects the user belongs to, and no other project |
| A2 | Client → server: create a topic with type, status, priority, labels, assignee and due date | `opencde_client … topics` lists it with a `server_assigned_id`; the values are the ones chosen (they must come from the project's extensions, anything else is a 400 the client has to show) |
| A3 | Client → server: add a viewpoint from the current view with the three walls selected and a snapshot | The viewpoint is listed under the topic; `selection` returns the three GUIDs; the snapshot downloads as PNG or JPEG |
| A4 | Client → server: add a comment and then edit the topic's status | The comment is listed with its `viewpoint_guid` when one was attached; the topic's events contain `comment_created` and `status_updated` in order |
| A5 | Server → client: run `create_topic.py`, refresh in Bonsai | The new topic appears with its viewpoint and comment; opening the viewpoint selects the three walls and shows one of them red; the snapshot is shown |
| A6 | Server → client: change the topic's status with the Python client (`cde.bcf.update_topic`) and refresh | Bonsai shows the new status and `modified_date`; the topic order follows the client's own sorting of `creation_date` |
| A7 | Delete a viewpoint that a comment refers to | The server answers 409 (BCF 3.0 3.5.9); Bonsai reports an error instead of pretending it succeeded |
| A8 | Stay signed in for more than an hour (or set `OPENCDE_ACCESS_TOKEN_TTL_SECONDS=120` for the test) and act again | The client refreshes without asking the user; the admin UI's sessions page shows the grant once, not once per refresh |
| A9 | Revoke the grant in `/account` while Bonsai is connected | The next action in Bonsai fails with 401 and the client offers to sign in again |

## 3. Checklist B: ifc-lite (browser)

ifc-lite is a web client with BCF and Documents API libraries. Run it locally
as its README describes (pnpm), note the origin it is served from (for example
`http://localhost:5173`) and register that origin's callback path as redirect
URI (`http://localhost` needs `OPENCDE_ALLOW_LOCALHOST_REDIRECTS=true`; serving on `127.0.0.1`
works everywhere). Parts of ifc-lite were written against BCF API 2.1, which the
server now answers under `/bcf/2.1/…`, so those parts can stay as they are.

| # | Step | Expected |
|---|---|---|
| B1 | Point ifc-lite at the server and sign in | The sign-in page names the client; the project list matches the user's memberships |
| B2 | Client → server: create a topic, a viewpoint and a comment | Visible through `opencde_client … topics` and in Bonsai (A5 in reverse) |
| B3 | Server → client: topics created by `create_topic.py` and by Bonsai | Listed with title, status, labels and viewpoint snapshot |
| B4 | Documents API, download direction: choose "select documents" in ifc-lite | The browser shows the server's selection page; selecting the IFC returns to ifc-lite, which downloads it and opens the model |
| B5 | Documents API, upload direction: upload a file from ifc-lite | The server's metadata page opens in the browser; after saving, the document is listed in `files_information` and in the project's documents |
| B6 | Cancel both pages with their cancel button | ifc-lite receives `user_cancelled_selection=true` or `user_cancelled_upload=true` and shows no error |
| B7 | Load the page without a token (new private window) and try an API call | 401 with the `{"message": …}` error body; CORS headers present (Foundation API 1.4) so the browser passes the error to the client |

## 4. Checklist C: Dataspatium (browser, own repository)

Dataspatium's automated live suite covers this checklist and more. It runs
every night in the workflow `dataspatium-nightly.yml`: the development stack
with demo data, the paired Dataspatium release served over http, its helpers
playing the user and the administrator at the server's pages, and Chromium
running `tests/index.html?only=opencde live` with the `DATASPATIUM_CDE_*`
parameters (the IFC graph over Bolt and the request log included). A failure
there is a server regression or a client finding to record in §5.

[Dataspatium](https://github.com/marwiss/Dataspatium) is the browser client
developed together with this server (see "Dataregium and Dataspatium" in the
README): its OpenCDE source family signs in with PKCE as a public client,
fetches BCF data as tables and imports documents chosen on the server's own
page. Serve a checkout of Dataspatium
over http (`python -m http.server 8080` in its folder) and open
`http://127.0.0.1:8080/`; with that origin the registration in §1.2 applies.
Under `file://` the family falls back to a manual flow where the user pastes
the address the server redirected to.

| # | Step | Expected |
|---|---|---|
| C1 | *Inhämta* → add a database source → family "OpenCDE (BCF, Documents)" with the server URL and the client id | Dataspatium asks for consent to contact the host once; discovery lists foundation 1.0, bcf 3.0 and documents 1.0; the connector is created without a secret |
| C2 | Sign in (popup) | The popup shows the server's sign-in page; after consent it closes by itself, the view shows the user name and the project picker with the user's projects |
| C3 | Fetch topics, comments, components, events and files for *Building permit* | Five tables; the components table has one row per selected or coloured element with `ifc_guid`, `role` and `color`; the events table has one row per action; the files table shows the uploaded IFC, with its `ifc_project` when the IFC-graph module is enabled ([docs/en/ifc-lpg.md](en/ifc-lpg.md)) |
| C4 | Save the topics table as a dataset and refresh it later | The dataset records the source (connector, project, table); refreshing fetches again through the family and the row count follows the server |
| C5 | "Hämta dokument" | A popup with the server's selection page; the chosen IFC is downloaded and imported as a model dataset; the element GUIDs match the `ifc_guid` column of the components table, so the two datasets can be joined in Dataspatium |
| C6 | Cancel the selection page | Dataspatium reports the cancellation, no error |
| C7 | Let the token expire (see A8) and fetch again | The family refreshes silently; the stored refresh token changes |
| C8 | Sign out | The refresh token is revoked (RFC 7009); the admin UI's sessions page no longer lists the grant; the next fetch asks the user to sign in first |
| C9 | Serve Dataspatium from a different origin than the registered redirect URI | The sign-in page refuses the redirect URI and does not redirect anywhere |

## 5. Results

| Date | Server commit | Client and version | Checklist | Result | Notes |
|---|---|---|---|---|---|
| | | Bonsai | A1–A9 | not yet run | |
| | | ifc-lite | B1–B7 | not yet run | |
| 2026-11-05 | 4ee9425 | Dataspatium (checkout of the same day, Edge) | C1–C9 | passed after three server fixes | Found and fixed in the next commit: 3.8.2 POST Document answered 500 with rate limits on (slowapi had no Response for its headers); CORS did not allow or expose `Content-Disposition`; an unhandled 500 carried no CORS headers. Everything else in the checklist worked, including the Documents API upload and selection, refresh with rotation and sign-out with revocation |
| 2026-11-05 | c9cf654 | Dataspatium (same checkout, Edge on `http://127.0.0.1:8093`) | C1–C9 and more | passed | Re-run after the fixes: every step passes, including six body variants of the 3.8.2 upload (text, octet-stream as typed array, ArrayBuffer and Blob, with and without `Content-Disposition`), the CORS preflight and the 500 body. Also exercised: topic and comment updates, viewpoint delete, a second document version through the Documents API (`version_index` 2), the versions and document-versions queries, document references, related topics, topic and comment events, OData on topics, ETag with 304, a refused redirect URI. Timings on one machine: sign-in 2.3–3.5 s (browser page included), create topic 40 ms, viewpoint with snapshot and components 100 ms, the five tables 27–140 ms, BCF document up and down 0.5 s, Documents API upload 0.3 s (5.2 s with the browser page), selection with IFC import 4.7 s, refresh 34 ms. Without the IFC-graph module `files_information` carries no `ifc_project` for IFC files, as designed |
| 2026-11-05 | c61ee75 | Dataspatium 2.28 live suite (16 automated steps, Edge) | C1–C9 and more | passed | Against the development stack rebuilt with the IFC-graph module and dynamic client registration enabled: 16 of 16 steps green; `files_information` carries `Document id` and `Version index`; the registration endpoint answers and is to be exercised with a public client (`token_endpoint_auth_method: "none"`) in the next Dataspatium release |
| 2026-11-05 | af7e680 | Dataspatium 2.29 live suite (18 automated steps, Edge) | C1–C9 and more | passed | Against the stack rebuilt with the retroactive `SAME_AS` linking: 18 of 18 steps green, among them self-registration as a public client, a topic from a selection with a viewpoint, comment, status change, BCF file out and in, the Documents API in parts, a BCF document, ETag/304, token refresh, sign-out, a refused redirect URI. Graph check afterwards: every `testhus.ifc`/`familjens-hus.ifc` import reached `done` (IFC4, 102 entities, 243 relationships, 100 geometry entities skipped, `ifc_project` filled) in 0.5–3.3 s with queueing below 1.3 s when uploads overlapped; a deliberately invalid `probe.ifc` ends as `failed` with "Unable to parse IFC SPF header" and no stray entities. The suite deletes its topics afterwards, so `SAME_AS` was verified with a probe topic: a viewpoint selecting three wall GUIDs linked each to the matching element of every imported model (617 ms including the viewpoint POST), an unknown GUID to nothing; no GTIN in that fixture |
| 2026-11-05 | af7e680 (stack image) | Dataspatium 2.30 live suite (21 automated steps, Edge) | C1–C9 and graph access | passed | Cypher from the browser over Bolt/WebSocket against the development stack's Neo4j (port 7697, user neo4j): models, classes and topic–element links through `SAME_AS`, selecting the latest finished model per document; a workspace package uploaded through the Documents API and downloaded intact. Re-run against the image built from 47e55e1 with full logging: 21 of 21 again; the browser counted 29 `IfcModel` (done and failed), 138 `IfcWall`, 6 product classes and 6 topic–element links for the suite's own topics; the workspace package (9 337 bytes) round-tripped. Afterwards `opencde client prune --all-dynamic` removed the 5 self-registered test clients and `opencde ifcgraph prune --project … --all` the 29 models with 2 346 entities, leaving the documents in place |
| 2026-11-05 | 8d98576 (stack image) | Dataspatium 2.32 live suite (23 automated steps, Edge) | C1–C9, request log | passed | Against the stack rebuilt with the request log enabled: 23 of 23. The app sent `X-Request-ID` on all 92 of its calls and saw every id echoed back (0 failures, 112 ms average). Its administrator step signed in as a server administrator with the `admin` scope and read `GET /admin/api/requests?client_id=…` (100 rows; 24 of the app's 30 newest ids were there, the last six being calls made after the read). Server side: 104 `RequestLog` rows for the client within 49 s, 89 of them with a UUID request id from the app, none without an id (the rest carry server-minted ids), statuses 200 ×88, 201 ×14, 304 ×2, users dm_manager ×103 and dm_admin ×1; the busiest operations were 3.2.1 GET Topics (13, 36 ms), 3.8.2 POST Document (8, 51 ms) and 3.5.1 GET Viewpoints (7, 46 ms). Token and revocation calls (11) carried the app's ids but no client, since they authenticate by form rather than bearer; fixed in the next commit |
| 2026-11-05 | 2877e95 (stack image) | Dataspatium 2.34 gate plus the 2.32 live suite (24 automated steps, Edge) | C1–C9, capabilities, software ids, error codes | passed | Against the stack rebuilt with the capabilities document, `software_id`/`software_version` at registration, the stable error codes and the new accent: 24 of 24. The app read `/.well-known/dataregium` and showed the server's version and extensions in its source view, registered itself with `software_id` `dataspatium` and its version, and translated the `not_found` code of a deliberately missing resource; everything from the 2.32 suite passed again |
| 2026-11-05 | 697fffa (stack image) | Dataspatium 2.1.0 (commit 8a4e9d7) live suite (24 automated steps, Edge) | C1–C9, IFC graph over Bolt, request log through the administration helper | passed | Against the stack rebuilt with the administration API in the agreed shapes and the graph query on: 24 of 24, with the administrator helper on 8095 and the graph over Bolt; no deviation from client-guide §7 in what 2.1.0 calls (Foundation, BCF, Documents, the request log, the capabilities). The administration API reads and the graph query are exercised from Dataspatium 2.2.0 |
| 2026-11-05 | 247f4fb (image built in the job) | Dataspatium v2.1.0 live suite, headless Chromium in GitHub Actions (`dataspatium-nightly.yml`, first run) | C1–C9, IFC graph over Bolt, request log through the administration helper | not run | The nightly pair job's first run. Corrected 2026-11-06: the job was green and first recorded here as passed, but Chromium aborted at start and no test ran; `tools/run-tests.sh` loses its failure in a pipeline's subshell and exits 0, and the job trusted that exit code. The job now requires a summary with passed tests and no failures |
| 2026-11-05 | 64bb0b2 (the owner's quick-start clone) | Dataspatium 2.1.0 release zip in Firefox, the quick start by hand | C1–C2 | failed, fixed in the next commit | The source was found only behind the "Lägg till databaskälla" card (quick start corrected), and the sign-in pop-up ended on the callback page with "copy the address": the server sent `Cross-Origin-Opener-Policy: same-origin` on every page, which cut the pop-up's `window.opener` on the way through the server, so the callback page could not report back. Fixed by keeping the browser default on the pages a client opens in a pop-up (the administration and account pages stay isolated); the headless suite never saw it because its helper plays the pop-up. A second cause sits in the client: Dataspatium's own service worker makes the app cross-origin isolated (`Cross-Origin-Opener-Policy: same-origin`, `crossOriginIsolated` true), which cuts the pop-up's opener on the app's side as well, so the callback page must reach the app through a `BroadcastChannel` or storage event instead of `window.opener`; reported to Dataspatium for 2.2.0. A third cause, the decisive one in Chrome and Edge: the pages' `form-action 'self'` policy, which Chromium also applies to the redirect that answers the form, so those browsers never left the sign-in page (a CDP trace showed the POST aborted after the 302); fixed by naming the client's origin on the authorization, selection and upload pages. Verified afterwards in headless Chromium against Dataspatium's 2.2.0 working copy: sign-in, callback, relay to the isolated app, pop-up closed by itself, token issued |
| 2026-11-06 | cb751a3 (image built in the job) | Dataspatium v2.3.0 (commit aab8e4a) live suite, headless Chromium in GitHub Actions (`dataspatium-nightly.yml`) | C1–C9, IFC graph over Bolt, request log and graph query through the administration helper | passed | 24 of 24 against the server at 2.3.0, the first run of this job that actually ran the suite (see the row of 247f4fb). The job now requires the summary line, and it adds the user `dm_manager` that the suite signs in as |
| 2026-11-06 | cd79bfe (image built in the job) | Dataspatium v2.4.0 (commit c637fab) live suite, headless Chromium in GitHub Actions (`dataspatium-nightly.yml`) | C1–C9, IFC graph over Bolt, request log and graph query through the administration helper | passed | 24 of 24 against the server at 2.4.0, signed in as the seed's `officer` through the suite's new user parameter |
| 2026-11-06 | b075242 (image built in the job) | Dataspatium v2.5.0 (commit b7bab02) live suite, headless Chromium in GitHub Actions (`dataspatium-nightly.yml`) | C1–C9, IFC graph over Bolt, request log and graph query through the administration helper | passed | 24 of 24 against the server at 2.5.0 |
| 2026-11-06 | 381309c (fresh clone, image built from it) | Dataspatium v2.5.0 release ZIP in Firefox and Chromium through Playwright, the quick start followed literally | Quick start steps 1–5 | passed | The commands and the `.env` lines were read from the page itself and run from an empty folder, with only another project name and other ports added. Real pop-up sign-in as `inspection_manager`, the sample model fetched, an issue with a viewpoint created from a marked wall, a comment sent; the server's project page shows two topics and one document, and an uploaded model links the wall to the component through `SAME_AS`. Also on screen in Chromium: registration off, `http://localhost` refused, the registration limit, a wiped registration, a client id filled in, a wrong password, `admin` without a project, *Deny*, another account on the upload page. The first such run found that `opencde seed` right after `up` could deadlock with the starting server (fixed in 5c0c58c) |
| 2026-11-06 | f77e32e (fresh clone, image built from it) | Dataspatium v2.5.0 release ZIP on `http://127.0.0.1` in Firefox and Chromium through Playwright, the quick start followed literally | Quick start steps 1–4, a planted service worker | passed | The same walk on the loopback address, without `OPENCDE_ALLOW_LOCALHOST_REDIRECTS`. Before that, a browser profile got another app's worker on the server's address, with a saved copy of `/signin` and an expired form: Firefox shows the server's page on the second visit, with the worker gone; Chromium keeps the saved copy until the failed sign-in's answer, which comes from the server and removes the worker, and the next attempt succeeds |
| 2026-11-06 | 270b2c6 (fresh clone, image built from it) | Dataspatium v2.5.0 release ZIP on `http://127.0.0.1` in Firefox and Chromium through Playwright, the quick start followed literally | Quick start steps 1 to 5, a password that has to be changed, another account on the upload page | passed | `opencde seed` built the sample model's graph in 8 s with 150 entities. Both browsers: sign-in, fetch, 3D view and issue without errors. In the pop-up, a user with a password to change went through the account page and back to the app; *Sign out* on the page *Another account* led through the sign-in back to the upload, which closed the pop-up by itself and became a graph, and the query found the wall in every model. Of the 292 answers in the request log none was a 429, so the limits enforced in 280ac66 leave ordinary use alone. |
| 2026-11-06 | 9337149 (release commit of 2.6.0, image built in the job) | Dataspatium v2.6.0 (commit 60739d2) live suite, headless Chromium in GitHub Actions (`dataspatium-nightly.yml`) | C1–C9, IFC graph over Bolt, request log through the administration API | passed | 24 of 24 before the tag. The app speaks BCF API 3.0 against a server that now also has 2.1, and lists both in its versions; Dataspatium's half of 2.1 is for the joint 2.7.0. The same day the nightly security run was green on the commit, with the signed-in scan reaching `/bcf/2.1` as well. The image from GHCR, pulled and started after the tag: `/readyz` ready, `/healthz` 2.6.0, and both versions in `/bcf/versions` |
| 2026-11-07 | ab4e056 (release commit of 2.7.0, image built in the job) | Dataspatium v2.7.0 (commit eae6686) live suite, headless Chromium in GitHub Actions (`dataspatium-nightly.yml`), once through BCF API 3.0 and once through 2.1 | C1–C9, IFC graph over Bolt and through the graph query, request log through the administration API | passed | 24 of 24 in each run, before the tag, and the server's log shows the second run's requests under `/bcf/2.1`. The nightly security run was green on the commit. The image from GHCR, pulled and started after the tag: `/readyz` ready, `/healthz` 2.7.0, and both versions in `/bcf/versions` |
| 2026-11-07 | 24e0853 (release commit of 2.0.0, image built in the job) | Dataspatium v2.0.0 (commit 57f1fa7) live suite, headless Chromium in GitHub Actions (`dataspatium-nightly.yml`), once through BCF API 3.0 and once through 2.1 | C1–C9, IFC graph over Bolt and through the graph query, request log through the administration API | passed | 24 of 24 in each run, before the tag. The nightly security run was green on the commit, with no finding that fails it. The image from GHCR, pulled and started after the tag: `/readyz` ready, `/healthz` 2.0.0, and both versions in `/bcf/versions` |
| 2026-11-07 | 8537e07 (release commit of 2.0.1, image built in the job) | Dataspatium v2.0.1 (commit 17561f2) live suite, headless Chromium in GitHub Actions (`dataspatium-nightly.yml`), once through BCF API 3.0 and once through 2.1 | C1–C9, IFC graph over Bolt and through the graph query, request log through the administration API | passed | 24 of 24 in each run, before the tag (run 42369675782). The nightly security run was green on the commit, run after the tag (42372293569). The image from GHCR, pulled and started after the tag: `/readyz` ready, `/healthz` 2.0.1, and both versions in `/bcf/versions` |
| 2026-11-07 | 395089f (release commit of 2.0.0, image built in the job; the tag is on dbee7f4, which changes a test and the release build only) | Dataspatium v2.0.0 (commit 205e5c9) live suite, headless Chromium in GitHub Actions (`dataspatium-nightly.yml`), once through BCF API 3.0 and once through 2.1 | C1–C9, IFC graph over Bolt and through the graph query, request log through the administration API | passed | 24 of 24 in each run, before the tag (run 42420720562). The nightly security run was green on the release commit too |
| 2026-11-08 | f8de721 (main before the release, image built locally, a throwaway server on 127.0.0.1:8020 with the IFC-LPG module) | Dataspatium v3.0.0 release commit 008cc34, live suite (`tests/opencde-live.test.js`) with the validation document, run in the Dataspatium session, once through BCF API 3.0 and once through 2.1 | The live suite, and the validation card on `three_walls_gtin.ifc` checked against two IDS documents of the project | passed | 25 of 25 in each run. The card read 4 specifications in 2 IDS documents, 2 passed, 2 failed and 0 not applicable, with the checks `schema` (0 issues) and `ids` (4), and the IDS document with a DTD listed under `rules_not_run`. The run showed that every check carries `documents` and `specifications`, filled only for `ids`, which the documented example now shows |
| 2026-11-08 | 58d2532 (release commit of 3.0.0, image built in the job) | Dataspatium v3.0.0 (commit 008cc34) live suite, headless Chromium in GitHub Actions (`dataspatium-nightly.yml`), once through BCF API 3.0 and once through 2.1 | C1–C9, IFC graph over Bolt and through the graph query, request log through the administration API | passed | 25 of 25 in each run, before the tag (run 42469874621), and the scheduled run on the release commit passed too. The suite's test of the validation card skips itself there, since the job gives it no checked version (`cdevaldoc`); the row above ran it. The nightly security run was green on 32ab424, which differs from the release commit only in the pair job's pin, and its Memgraph job now runs the IFC-LPG tests too (338 passed). The image with buildingSMART's rules was built locally from main and ran the rules on a test file, read-only, as user `opencde`, and the rules' installer ran for arm64 under emulation. The Release workflow needed five attempts, because GitHub's release downloads answered 504 for an hour and its SBOM step installs Syft from them; later releases make the SBOM with Trivy (ceb12b2). After the release, GHCR had 3.0.0 (sha256:e1d25dae…) and 3.0.0-gherkin (sha256:b8fa4999…) for amd64 and arm64. The 3.0.0 image, pulled and started: `/readyz` ready, `/healthz` 3.0.0, BCF 3.0 and 2.1 in `/bcf/versions`, and `opencde seed` with the IFC-LPG module. The 3.0.0-gherkin image ran the rules on the same test file |

## 6. Client deviations (draft reports, nothing sent)

Write each finding here before anything leaves the project: client and
version, the request and the response, the specification clause, what the
server does and why. The owner decides whether to report it to the client's
maintainers.

| Client | Observation | Specification | Status |
|---|---|---|---|
| | | | |
