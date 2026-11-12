# Quick start: Dataregium and Dataspatium together

From an empty machine to signed in to Dataregium from Dataspatium, with an issue
created in a 3D view and visible in the server's logs. It takes about twenty
minutes, most of it the first build. Follow the steps in order and use the
addresses and ports exactly as written: almost every problem comes from a skipped
setting or another address. [Troubleshooting](#troubleshooting) says what to do
if something goes wrong. The same page exists in Dataspatium's repository; the
two are kept identical.

## What you need

- Docker: Docker Desktop on Windows and macOS, Docker Engine with the compose
  plugin on Linux. It must be running: `docker version` answers for both client
  and server.
- Git, or the source code ZIP from Dataregium's
  [latest release](https://github.com/marwiss/Dataregium/releases/latest) in place
  of `git clone` below.
- Python 3, as a small local web server.
- Microsoft Edge, Google Chrome or Firefox.
- The ports 8000, 7484, 7697 and 8080 free on your machine.

If you have tried Dataregium on this machine before, begin with
[Start over](#start-over).

## 1. Start Dataregium

```sh
git clone https://github.com/marwiss/Dataregium.git
cd Dataregium
cp .env.example .env
```

In the Windows Command Prompt, `copy` takes the place of `cp`.

Open `.env` in a text editor. The four lines below are already in the file:
change them to read like this, and save. Choose your own password, at least 16
characters, letters and digits only.

```ini
OPENCDE_GRAPH_PASSWORD=YourOwnPassword1234
OPENCDE_DYNAMIC_CLIENT_REGISTRATION=true
OPENCDE_REQUEST_LOG_ENABLED=true
OPENCDE_IFC_DB_ENABLED=true
```

| Line | What it does | Without it |
|---|---|---|
| `OPENCDE_GRAPH_PASSWORD` | The password of the graph database | Shorter than 16 characters: the database does not start |
| `OPENCDE_DYNAMIC_CLIENT_REGISTRATION` | Lets Dataspatium register itself with the server | Step 3 stops, and the app asks for a client id |
| `OPENCDE_REQUEST_LOG_ENABLED` | Records the app's calls | The request log in step 5 stays empty |
| `OPENCDE_IFC_DB_ENABLED` | Turns uploaded models into a graph | No graph in step 5 |

These settings are for trying Dataregium on your own machine, not for a server that
others use.

Start the server and load the demonstration data:

```sh
docker compose up -d --build --wait
docker compose exec api opencde seed
```

The first command takes a few minutes the first time and returns when the server
is running. The second creates demonstration users and projects and prints their
passwords **once**: save the passwords of `admin` and `inspection_manager` now.
Leave the lines that begin with `client` alone; Dataspatium registers a client of
its own.

Check that it works: <http://127.0.0.1:8000/readyz> answers `"status":"ready"`.
Sign in at <http://127.0.0.1:8000/signin> as `admin` and open
<http://127.0.0.1:8000/admin/projects>, which lists *Building permit* and
*Demolition permit*.

When you change `.env` later, run the `up` command again. `docker compose restart`
does not read the file.

## 2. Start Dataspatium

1. Download `dataspatium-<version>.zip` from the
   [latest release](https://github.com/marwiss/Dataspatium/releases/latest)
   and compare its SHA-256 with the one in the release text (`Get-FileHash` in
   PowerShell, `shasum -a 256` on macOS and Linux).
2. Unpack the ZIP into a folder of your own. Windows may create a folder inside
   the folder; what counts is the folder that directly holds `index.html`.
3. Open a terminal in that folder and start a web server on port 8080:

   ```sh
   python -m http.server 8080 --bind 127.0.0.1
   ```

   The command may be `python3` on macOS and Linux and `py` on Windows. Keep the
   terminal open while you use the app. Always give the port: without it Python takes 8000, which is Dataregium's port.
4. Open <http://127.0.0.1:8080/>, written just like that: the server sends the browser back after the sign-in to `127.0.0.1`, not to `localhost`. Do not double-click `index.html`: opened from
   the folder, the app cannot register itself. The app reloads once at its first
   start.
5. The first start asks for a language: choose one and press *Continue in …*. This
   page uses the English names. The panel *Welcome to Dataspatium* offers a course:
   press *Not now*.

## 3. Sign in to Dataregium from Dataspatium

1. Choose the mode *Import*. In the left column, under *Add sources*, choose
   *OpenCDE*.
2. Under *Address*, write `http://127.0.0.1:8000`. **Leave *Client id* and the
   secret empty**: the app registers itself, even though the text in the dialog
   speaks of a client id from the administrator. Press *Add source*.
3. The app asks *Allow internet access?* up to three times, once per purpose. Here
   it concerns only your own server: press *Allow* each time.
4. The source opens and is listed under *Added sources*. The line "Server: Dataregium
   OpenCDE server <version>. Extensions: …" comes from the server's capabilities
   document and says which extensions are on. The label *Requires a key* can be
   ignored: what it takes is the sign-in.
5. Press *Sign in*. A pop-up opens with the server's sign-in page. If the browser
   blocks it, allow pop-ups for `http://127.0.0.1:8080` and press again.
6. Sign in as `inspection_manager` with the password from step 1 and press *Allow
   and sign in*. Do not use `admin`, who is in no project. The pop-up closes by
   itself, and the source says *Signed in as Certified inspection manager*.
7. *Building permit* is already chosen in the list *Project*.

You stay signed in until the page is reloaded; then press *Sign in* again. The
source remains.

## 4. Create an issue from the 3D view

1. In the source's view, find *Files in the project* and press *Show files*.
   `opencde seed` stored `three_walls_gtin.ifc` there (three walls with the GTINs 3,
   2 and 1). Press *Fetch*: the file becomes a model dataset.
2. Choose the mode *Process*; the model opens in 3D. Click a wall to mark it.
3. Press *Issues* above the 3D view and then *New issue* in the right column. Write
   something under *Title* and press *Create issue*. The issue is created through
   the BCF API, and the view and the marked wall go along as a viewpoint.
4. Under the issue, write something in *Write a comment* and press *Send*.

## 5. See it on the server

Signed in as `admin`, open <http://127.0.0.1:8000/admin>:

- *Projects* shows *Building permit* with two topics (the one from `opencde seed` and
  yours) and one document.
- *Audit log* lists the sign-in and the registration of the app.
- *Request log* shows every call the app made, with the same `X-Request-ID` values
  as the card *Log* at the bottom of the source's view in *Import*, so a failing
  call can be found on both sides.

The sample model is a graph already, since `OPENCDE_IFC_DB_ENABLED=true` was in
`.env` when you ran `opencde seed`. Neo4j Browser at <http://127.0.0.1:7484> (connect
to `bolt://127.0.0.1:7697` as `neo4j` with the password from `.env`) answers this
query with the wall linked to the viewpoint's component:

```cypher
MATCH (c:Component), (w:IfcWall {GlobalId: c.ifc_guid}) RETURN c, w
```

A model you send from Dataspatium becomes a graph the same way. To try it, press
*Sign out* at the top of the server's page, since the upload is done as another user:

1. In Dataspatium, choose the mode *Share* and the tab *To the CDE*. Under *What*,
   choose *The original file*, and press *Send*.
2. *Review before sharing* lists what goes along: press *Continue*.
3. The server's upload page opens in a pop-up. Sign in as `inspection_manager` and
   press *Save and continue*. The pop-up closes by itself.

Within seconds the same query finds the wall in the new model too.

## Troubleshooting

Each row quotes the screen as it reads with the English names.

| What you see | Why | What to do |
|---|---|---|
| `Cannot connect to the Docker daemon`, `error during connect` or `docker: command not found` | Docker is not running | Start Docker Desktop, wait until it says it is running, and run the command again |
| `dependency failed to start: container dataregium-graph-1 is unhealthy` | A password of fewer than 16 characters, which Neo4j refuses (`docker compose logs graph` says `A password must be at least 16 characters`), or a database volume left by an earlier installation with another password | Correct the password and run the `up` command again. For the old volume, see [Start over](#start-over) |
| `port is already allocated`, `Ports are not available` or `address already in use` | Another program holds 8000, 7484 or 7697, perhaps an earlier Dataregium (`docker ps` shows it) | Stop it, or set other ports with `OPENCDE_DEV_PORT`, `OPENCDE_DEV_NEO4J_HTTP_PORT` and `OPENCDE_DEV_NEO4J_BOLT_PORT` in `.env` and use your port instead of 8000 from then on |
| The containers of another folder are replaced | Two checkouts on one machine share the Compose project name `dataregium` | Give the second one `COMPOSE_PROJECT_NAME=dataregium-2` and other `OPENCDE_DEV_*` ports in its `.env` |
| `the database is not empty` | `opencde seed` has already run and printed the passwords then | Get a new password with `docker compose exec api opencde user set-password inspection_manager`, or [start over](#start-over) |
| `python` is not found, or the Microsoft Store opens | The command has another name on this machine | Use `py` or `python3` |
| A list of files instead of the app | The web server runs in the outer folder | Stop it with Ctrl+C and start it in the folder that holds `index.html` |
| An old version of the app, or something else entirely | Something else answers on port 8080; on Windows a second web server can start on the same port without an error | Use another port, `python -m http.server 8090 --bind 127.0.0.1`, and open `http://127.0.0.1:8090/` |
| *The app can register itself with the server only when it runs from a web server …* | The app was opened from the folder | Open `http://127.0.0.1:8080/` |
| *Could not reach 127.0.0.1:8000 …* | Dataregium is not running, or the address is mistyped | <http://127.0.0.1:8000/readyz> must answer. The address is `http://127.0.0.1:8000` with nothing after it |
| *The server does not let the app register itself …* | `OPENCDE_DYNAMIC_CLIENT_REGISTRATION` is not `true` | Change `.env`, run the `up` command again, and press *Add source* again |
| *The registration failed:* … `Redirect URIs to http://localhost are not allowed here` | The app was opened on `localhost`, which the server does not accept as the way back | Open `http://127.0.0.1:8080/` and add the source there |
| *The registration failed:* … `rate_limited` | More than 60 registrations within an hour; every *Add source* with an empty *Client id* is one | `docker compose restart api` empties the counter |
| *Internet access for … is not allowed.* | *Deny* was pressed | Allow it under *Manage*, *Workspace*, *Internet access*, and try again |
| *The browser blocked the sign-in window …* | The browser's pop-up blocker | Allow pop-ups for `http://127.0.0.1:8080` and press *Sign in* again |
| In the pop-up: *Cannot continue* and *Unknown client.* | The server has forgotten the app's registration, usually after `down -v` | Close the pop-up and reload the app, since *Sign in* otherwise keeps spinning for five minutes. Delete the source with the cross beside it under *Added sources* and add it again |
| In the pop-up: *Cannot continue* and *The redirect URI is not registered for this client.* | *Client id* was filled in, for instance from the output of `opencde seed` | Close the pop-up and reload the app. Delete the source with the cross beside it under *Added sources* and add it again with *Client id* empty |
| In the pop-up: *The user name or password is not correct.* | Every user has their own password from `opencde seed` | Use the right one, or get a new one as above |
| *Too many failed attempts for this user name …* | Five wrong passwords in a row make the server wait, at most 15 minutes | Wait for as long as it says, and use the password from `opencde seed` |
| *The form has expired. Please try again.* on `/signin`, or in the pop-up *Cannot continue* and *The sign-in form has expired or was tampered with. Start again.*, although you just opened the page. `docker compose logs api` shows `foreign_service_worker_removed` | A service worker in your browser from another web app that once ran on `http://127.0.0.1:8000`, for instance one started with `python -m http.server` without a port. It answers with old copies of Dataregium's pages | Wait a few seconds, until the page has reloaded by itself, and try again, since Dataregium removes such a worker. If the message stays, remove it by hand: `about:debugging#/runtime/this-firefox` in Firefox, `edge://serviceworker-internals` in Edge, `chrome://serviceworker-internals` in Chrome; find `127.0.0.1:8000` and choose *Unregister*. Every browser has its own, also one built into an editor. A private window has none, which shows quickly whether this is the cause. Keep other apps off port 8000 |
| *You are not a member of any project on the server.* | You signed in as `admin`, who is in no project | Press *Sign out* and then *Sign in* as `inspection_manager` |
| *Sign in* keeps spinning | The pop-up was closed before the sign-in was finished | Reload the page |
| The pop-up says *Kopiera adressen … / Copy the address …* | It could not reach the app's window, which was perhaps closed or reloaded meanwhile | Close the pop-up and press *Sign in* again |
| *Another account* on the upload page | The browser is signed in to the server as `admin`, who did not start the upload | Press *Sign out* on that page and sign in as `inspection_manager`; the upload then continues in the same window |

## Start over

In the folder you started from (or anywhere, with `-p dataregium`):

```sh
docker compose down -v
```

This deletes the database and the files of the demonstration. Then run the `up` and
`seed` commands of step 1 again, which gives new passwords. In Dataspatium, delete
the source with the cross beside it under *Added sources* and add it again, since
the server has forgotten the app's registration.

To stop without deleting anything, leave out `-v`, and stop the web server with
Ctrl+C.

## What next

- [docs/en/client-guide.md](client-guide.md) for the APIs, the capabilities
  document and the error codes.
- [docs/en/deploy/](deploy/) when the server is to run for others.
