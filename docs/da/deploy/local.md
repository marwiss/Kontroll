# Lokal test (Windows, macOS, Linux)

Alt kører i Docker på din maskine; intet kan nås udefra.

## Krav

- Docker Desktop (Windows, macOS) eller Docker Engine med compose-pluginet (Linux)
- [uv](https://docs.astral.sh/uv/) til kommandolinjeværktøjerne

## Trin

```sh
git clone https://github.com/marwiss/Kontroll.git
cd Kontroll
uv run opencde init --dev                                 # skriver .env med nye hemmeligheder
docker compose -f compose.yaml -f compose.dev.yaml up -d --build
docker compose -f compose.yaml -f compose.dev.yaml exec api opencde seed
```

`opencde seed` opretter demonstrationsbrugere (en administrator og en bruger
for hver af rollerne manager, editor, contributor og viewer), to projekter og
en offentlig OAuth2-klient og udskriver kodeordene én gang.

| Hvad | Hvor |
|---|---|
| API-dokumentation | <http://localhost:8000/docs> |
| Administration | <http://localhost:8000/admin> (log ind som administratoren) |
| Parathed | <http://localhost:8000/readyz> |
| Neo4j Browser | <http://localhost:7484> (Bolt `localhost:7697`) |
| Serverlog | `docker compose -f compose.yaml -f compose.dev.yaml logs -f api` |

Udviklingsoverlejringen udgiver Neo4j på 7484/7697 i stedet for
standardportene 7474/7687, som en anden Neo4j på samme maskine ofte optager.
Skift portene med `OPENCDE_DEV_*` i `.env`. To checkouts på samme maskine deler
Compose-projektnavnet `kontroll` (`compose.yaml` sætter det); giv det andet
`COMPOSE_PROJECT_NAME=kontroll-2` og andre porte i sin `.env`.

## Uden Docker til serveren

Kør databasen i Docker (eller Neo4j Desktop / Memgraph Lab) og serveren fra
checkout'et:

```sh
uv sync
uv run opencde doctor
uv run opencde serve --reload
```

`.env`, som `opencde init --dev` skriver, peger på `bolt://127.0.0.1:7697`,
udviklingsoverlejringens Bolt-port.

## Memgraph i stedet for Neo4j

```sh
docker compose -f compose.yaml -f compose.memgraph.yaml -f compose.dev.yaml up -d --build
```

Sæt `OPENCDE_GRAPH_DIALECT=memgraph` og `OPENCDE_GRAPH_USER=memgraph` i `.env`,
når serveren kører uden for Docker. Memgraph Lab (`memgraph/lab`) kan peges
mod `localhost:7697`.

## Test med Dataspatium

[Dataspatium](https://github.com/marwiss/Dataspatium) er browserklienten, der
udvikles sammen med denne server. Servér et checkout af den over http
(`python -m http.server 8080` i dens mappe), åbn `http://127.0.0.1:8080/`,
registrér appen som en offentlig klient, og tilføj serveren som OpenCDE-kilde
i Dataspatium (*Inhämta*) med `http://localhost:8000` og det klient-id:

```sh
uv run opencde client create "Dataspatium" --public --redirect-uri http://127.0.0.1:8080/oauth-callback.html
```

Med `OPENCDE_DYNAMIC_CLIENT_REGISTRATION=true` i `.env` registrerer appen sig
selv i stedet. CORS tillader alle oprindelser som standard, så der skal ikke
indstilles mere; `OPENCDE_REQUEST_LOG_ENABLED=true` lader `/admin/requests`
vise serversiden af appens kald. Den fulde tjekliste er
[docs/acceptance.md](../../acceptance.md), afsnit C.
[Den hurtige start](../quickstart.md) har alle trin og en fejlfindingstabel.

## Ren tavle

```sh
docker compose -f compose.yaml -f compose.dev.yaml down -v   # fjerner volumerne: database og filer
```
