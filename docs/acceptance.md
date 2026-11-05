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
| Browser clients on the same machine (Dataspatium, ifc-lite) | the development stack on `http://localhost:8000` |
| Desktop clients on the same machine (Bonsai) | `http://localhost:8000` when the client accepts http; otherwise a tunnel |
| Anything on another machine | a public https URL through a tunnel ([docs/deploy/tunnel.md](deploy/tunnel.md)) or a deployed server |

Start the development stack and load the demonstration data:

```sh
docker compose -f compose.yaml -f compose.dev.yaml up -d --build
docker compose -f compose.yaml -f compose.dev.yaml exec api opencde seed
```

`seed` prints the demo users and their one-time passwords, the ids of the
projects *Bygglov* and *Rivningslov*, a public client and a confidential
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
uv run python -m opencde_client --server http://localhost:8000 --client-id <public client id> login
uv run python -m opencde_client --server http://localhost:8000 --client-id <public client id> projects
uv run python -m opencde_client --server http://localhost:8000 --client-id <public client id> topics <project id>
uv run python docs/examples/create_topic.py http://localhost:8000 <public client id> <project id> snapshot.png
uv run python docs/examples/upload_document.py http://localhost:8000 <public client id> tests/fixtures/three_walls_gtin.ifc
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
URI (`http://localhost` needs the development overlay; serving on `127.0.0.1`
works everywhere). Parts of ifc-lite were written against BCF API 2.1: requests
to `/bcf/2.1/…` are 404 on this server by design (BCF 3.0 only), and such a
finding belongs under *Client deviations*, not in the server.

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

Dataspatium is this project's visual test client: the OpenCDE source family
signs in with PKCE as a public client, fetches BCF data as tables and imports
documents chosen on the server's own page. Serve a checkout of Dataspatium
over http (`python -m http.server 8080` in its folder) and open
`http://127.0.0.1:8080/`; with that origin the registration in §1.2 applies.
Under `file://` the family falls back to a manual flow where the user pastes
the address the server redirected to.

| # | Step | Expected |
|---|---|---|
| C1 | *Inhämta* → add a database source → family "OpenCDE (BCF, Documents)" with the server URL and the client id | Dataspatium asks for consent to contact the host once; discovery lists foundation 1.0, bcf 3.0 and documents 1.0; the connector is created without a secret |
| C2 | Sign in (popup) | The popup shows the server's sign-in page; after consent it closes by itself, the view shows the user name and the project picker with the user's projects |
| C3 | Fetch topics, comments, components, events and files for *Bygglov* | Five tables; the components table has one row per selected or coloured element with `ifc_guid`, `role` and `color`; the events table has one row per action; the files table shows the uploaded IFC with its `ifc_project` |
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
| | | Dataspatium | C1–C9 | not yet run | the family's own tests against a mocked server are green |

## 6. Client deviations (draft reports, nothing sent)

Write each finding here before anything leaves the project: client and
version, the request and the response, the specification clause, what the
server does and why. The owner decides whether to report it to the client's
maintainers.

| Client | Observation | Specification | Status |
|---|---|---|---|
| | | | |
