# Local test (Windows, macOS, Linux)

Everything runs in Docker on your machine; nothing is reachable from outside.

## Requirements

- Docker Desktop (Windows, macOS) or Docker Engine with the compose plugin (Linux)
- or Podman 5 with `podman compose`: the same files work, see [Podman](#podman) below
- [uv](https://docs.astral.sh/uv/) for the command line tools

## Steps

```sh
git clone https://github.com/marwiss/Dataregium.git
cd Dataregium
uv run opencde init --dev                                 # writes .env with fresh secrets
docker compose up -d --build
docker compose exec api opencde seed
```

`opencde seed` creates demonstration users (an administrator, a manager, an
editor, a contributor and a viewer), two projects and a public OAuth2 client,
and prints the passwords once.

| What | Where |
|---|---|
| API documentation | <http://127.0.0.1:8000/docs> |
| Administration | <http://127.0.0.1:8000/admin> (sign in as the administrator) |
| Readiness | <http://127.0.0.1:8000/readyz> |
| Neo4j Browser | <http://127.0.0.1:7484> (Bolt `127.0.0.1:7697`) |
| Server log | `docker compose logs -f api` |

The development overlay publishes Neo4j on 7484/7697 rather than the default
7474/7687, which another Neo4j on the same machine often holds. Change the
ports with `OPENCDE_DEV_*` in `.env`. Two checkouts on one machine share the
Compose project name `dataregium` (`docker/compose.yaml` sets it); give the second one
`COMPOSE_PROJECT_NAME=dataregium-2` and other ports in its `.env`.

An installation made when the project was still called Kontroll has its data
in volumes named `kontroll_…`. It keeps them by setting
`COMPOSE_PROJECT_NAME=kontroll` in `.env`, which overrides the name in
`docker/compose.yaml`; without it, the next `up` starts a new project with empty
volumes.

## Without Docker for the server

Run the database in Docker (or Neo4j Desktop / Memgraph Lab) and the server
from the checkout:

```sh
uv sync
uv run opencde doctor
uv run opencde serve --reload
```

`.env` written by `opencde init --dev` points at `bolt://127.0.0.1:7697`, the
Bolt port of the development overlay.

## Memgraph instead of Neo4j

```sh
# .env: COMPOSE_FILE=docker/compose.yaml:docker/compose.memgraph.yaml:docker/compose.dev.yaml
docker compose up -d --build
```

Set `OPENCDE_GRAPH_DIALECT=memgraph` and `OPENCDE_GRAPH_USER=memgraph` in `.env`
when running the server outside Docker. Memgraph Lab (`memgraph/lab`) can be
pointed at `127.0.0.1:7697`.

## Testing with Dataspatium

[Dataspatium](https://github.com/marwiss/Dataspatium) is the browser client
developed together with this server. Serve a checkout of it over http
(`python -m http.server 8080` in its folder), open `http://127.0.0.1:8080/`,
register the app as a public client, and add the server as an OpenCDE source
in Dataspatium (*Inhämta*) with `http://127.0.0.1:8000` and that client id:

```sh
uv run opencde client create "Dataspatium" --public --redirect-uri http://127.0.0.1:8080/oauth-callback.html
```

With `OPENCDE_DYNAMIC_CLIENT_REGISTRATION=true` in `.env` the app registers
itself instead. CORS allows every origin by default, so no further setting is
needed; `OPENCDE_REQUEST_LOG_ENABLED=true` lets `/admin/requests` show the
server side of the app's calls.
The [quick start](../quickstart.md) has the complete steps and a troubleshooting table.

## The local engine

Dataregium can run on a person's own computer as the engine behind Dataspatium
for models larger than a browser tab holds (ADR 0023). `opencde init --local`
writes a `.env` for that, and `OPENCDE_ENVIRONMENT=local` makes the server
keep to it: the public URL must be the loopback, a database password and a
secret key are required, the CORS origins must be named (`*` is refused), no
database address may be published, and `opencde serve` refuses any interface
but the loopback. A request whose `Host` is not `127.0.0.1`, `localhost` or
`::1` is answered `421`, before anything else, so that a page on the internet
cannot reach the engine through a name of its own that resolves to the
loopback. A public page that asks in its preflight
(`Access-Control-Request-Private-Network: true`) is allowed when its origin is
named. OAuth2 with PKCE is required locally as everywhere. The origins the
file writes are `null` (Dataspatium opened from a file), `http://127.0.0.1:8080`
(a local http server) and `https://marwiss.github.io`; drop `null` when the
app runs from an http origin.

```sh
uv run opencde init --local   # .env: OPENCDE_ENVIRONMENT=local, random passwords, the origins Dataspatium comes from
docker compose up -d          # the API on http://127.0.0.1:8000 only; the database is never published
```

## Podman

The Compose files work with Podman as well as Docker: the images have full names,
the data lives in named volumes, bind mounts carry the `z` label for SELinux, and
the development overlay binds ports above 1024 on 127.0.0.1. Run them with
`podman compose` (Podman 5), or with the `docker compose` command against Podman's
socket (`DOCKER_HOST=unix:///run/user/1000/podman/podman.sock`). Rootless Podman
cannot bind ports 80 and 443 for the production overlay: set
`sysctl net.ipv4.ip_unprivileged_port_start=80`, or run that stack as root. Podman
is free of charge (Apache-2.0); the tests run with Docker, and Podman is not part
of CI.

## Clean slate

```sh
docker compose down -v   # removes the volumes: database and files
```
