# Quick start: Kontroll and Dataspatium together

Twenty minutes from nothing to an issue created in a 3D view and visible in
the server's logs. The same page exists in Dataspatium's repository; the two
are kept identical. You need Docker (Desktop on Windows/macOS, Engine on
Linux), [uv](https://docs.astral.sh/uv/), Python 3 for a local web server,
and Microsoft Edge, Google Chrome or Firefox.

## 1. Start Kontroll

```sh
git clone https://github.com/marwiss/Kontroll.git
cd Kontroll
cp .env.example .env
```

Open `.env` and set `OPENCDE_GRAPH_PASSWORD` to any value of 16 characters
or more, `OPENCDE_DYNAMIC_CLIENT_REGISTRATION=true` so that Dataspatium can
register itself, and `OPENCDE_ALLOW_LOCALHOST_REDIRECTS=true` so that an app
served from `http://localhost` may sign in. Then:

```sh
docker compose -f compose.yaml -f compose.dev.yaml up -d --build
docker compose -f compose.yaml -f compose.dev.yaml exec api opencde seed
```

The second command creates demonstration users and projects and prints their
passwords once; keep the password of `admin` and of `inspection_manager`. Check
<http://localhost:8000/readyz> (it answers `ready`) and sign in at
<http://localhost:8000/signin> as `admin`: `/admin` shows the projects
*Building permit* and *Demolition permit*.

If Compose stops with `dependency failed to start: container kontroll-graph-1
is unhealthy`, read `docker compose -f compose.yaml -f compose.dev.yaml logs
graph`. The usual cause is a password of fewer than 16 characters, which
Neo4j refuses (`A password must be at least 16 characters`); the other is a
database volume left by an earlier installation with another password, which
`docker compose -f compose.yaml -f compose.dev.yaml down -v` removes together
with its data. Two checkouts on one machine share the Compose project name
`kontroll`, so the second one needs `COMPOSE_PROJECT_NAME=kontroll-2` and
other `OPENCDE_DEV_*` ports in its `.env`.

## 2. Start Dataspatium

1. Download `dataspatium-<version>.zip` from the
   [latest release](https://github.com/marwiss/Dataspatium/releases/latest)
   and compare its SHA-256 with the one in the release text.
2. Unpack the ZIP into a folder of your own (not inside the ZIP).
3. For everything except the OpenCDE sign-in, double-clicking `index.html`
   is enough. For OpenCDE, serve the folder over http, because the OAuth2
   redirect needs an http address:

   ```sh
   cd dataspatium-<version>
   python -m http.server 8080
   ```

   and open <http://localhost:8080/>. The app registers itself with the
   server as a public client with `http://localhost:8080/oauth-callback.html`
   as its redirect URI. (The hosted app at
   <https://marwiss.github.io/Dataspatium/> works against a server that allows
   that address instead.)

## 3. Connect the two

In Dataspatium: the mode *Inhämta* (Import) → the button *Lägg till källa*
(Add source) → *Typ av tjänst* (Kind of service): *OpenCDE (BCF, Documents)*
→ *Adress* (Address): `http://localhost:8000` → *Lägg till* (Add). The source
opens in *Inhämta*: press *Logga in* (Sign in) and sign in as `inspection_manager` in the
pop-up window, then choose *Building permit* in the list *Projekt*. The line
under the heading ("Servern: Kontroll OpenCDE server 2.0.0. Tillägg: …")
comes from the server's capabilities document and says which extensions are
on.

## 4. Create an issue from the 3D view

1. Get the sample model. The seed already stored `three_walls_gtin.ifc`
   (three walls with the GTINs 3, 2 and 1) as a document in *Building
   permit*; in the source's view in *Inhämta* the document list has a fetch
   button per document, which turns it into a model dataset. To send a file
   of your own instead, use the mode *Dela* (Share) → the tab *Till CDE* (To
   the CDE): choose the source and the project, *Vad* (what: the original
   file, an export or a package), *Hur* (how: Documents API or BCF) and
   *Skicka* (Send); then fetch it back the same way.
2. Choose the model in *Bearbeta* (Process); it opens in 3D automatically.
   Select a wall, open the panel *Ärenden* (Issues) and press *Nytt ärende*
   (New issue): give it a title, keep the status and tick *Lägg till vyn som
   viewpoint* (Add the view as a viewpoint). The issue is created through
   the BCF API with a viewpoint whose component points at the wall.
3. Write a comment in the same panel and send it.

## 5. See it on the server

- `/admin/projects` → *Building permit* shows two topics (the seeded one
  and yours) and the document.
- `/admin/audit` lists the sign-in and the registration of the app.
- With `OPENCDE_REQUEST_LOG_ENABLED=true` in `.env` (and a restart),
  `/admin/requests` shows every call the app made, with the same
  `X-Request-ID` values as the card *Logg* at the bottom of the OpenCDE
  source's view in *Inhämta*, so a failing call can be found on both sides.
- With `OPENCDE_IFCGRAPH_ENABLED=true`, the uploaded model becomes a graph;
  Neo4j Browser at <http://localhost:7484> (`bolt://localhost:7697`, user and
  password from `.env`) shows the wall as an `IfcWall` node linked to the
  viewpoint's component by `SAME_AS`, and Dataspatium's graph view can query
  it with Cypher.

## What next

- [docs/client-guide.md](client-guide.md) for the APIs, the capabilities
  document and the error codes.
- [docs/acceptance.md](acceptance.md) for the checklists the pair is tested
  with, and [docs/dataspatium-coordination.md](dataspatium-coordination.md)
  for what the two projects coordinate.
- [docs/deploy/](deploy/) when the server is to run for others.
