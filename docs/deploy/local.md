# Local test (Windows, macOS, Linux)

Everything runs in Docker on your machine; nothing is reachable from outside.

## Requirements

- Docker Desktop (Windows, macOS) or Docker Engine with the compose plugin (Linux)
- [uv](https://docs.astral.sh/uv/) for the command line tools

## Steps

```sh
git clone https://github.com/marwiss/Kontroll.git
cd Kontroll
uv run opencde init --dev                                 # writes .env with fresh secrets
docker compose -f compose.yaml -f compose.dev.yaml up -d --build
docker compose -f compose.yaml -f compose.dev.yaml exec api opencde seed
```

`opencde seed` creates demonstration users (an administrator, a manager, an
editor, a contributor and a viewer), two projects and a public OAuth2 client,
and prints the passwords once.

| What | Where |
|---|---|
| API documentation | <http://localhost:8000/docs> |
| Administration | <http://localhost:8000/admin> (sign in as the administrator) |
| Readiness | <http://localhost:8000/readyz> |
| Neo4j Browser | <http://localhost:7484> (Bolt `localhost:7697`) |
| Server log | `docker compose -f compose.yaml -f compose.dev.yaml logs -f api` |

The development overlay publishes Neo4j on 7484/7697 rather than the default
7474/7687, which another Neo4j on the same machine often holds. Change the
ports with `OPENCDE_DEV_*` in `.env`.

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
docker compose -f compose.yaml -f compose.memgraph.yaml -f compose.dev.yaml up -d --build
```

Set `OPENCDE_GRAPH_DIALECT=memgraph` and `OPENCDE_GRAPH_USER=memgraph` in `.env`
when running the server outside Docker. Memgraph Lab (`memgraph/lab`) can be
pointed at `localhost:7697`.

## Clean slate

```sh
docker compose -f compose.yaml -f compose.dev.yaml down -v   # removes the volumes: database and files
```
