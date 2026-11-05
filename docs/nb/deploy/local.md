# Lokal test (Windows, macOS, Linux)

Alt kjører i Docker på din maskin; ingenting kan nås utenfra.

## Krav

- Docker Desktop (Windows, macOS) eller Docker Engine med compose-tillegget (Linux)
- [uv](https://docs.astral.sh/uv/) for kommandolinjeverktøyene

## Trinn

```sh
git clone https://github.com/marwiss/Kontroll.git
cd Kontroll
uv run opencde init --dev                                 # skriver .env med nye hemmeligheter
docker compose -f compose.yaml -f compose.dev.yaml up -d --build
docker compose -f compose.yaml -f compose.dev.yaml exec api opencde seed
```

`opencde seed` oppretter demonstrasjonsbrukere (en administrator og en bruker
for hver av rollene manager, editor, contributor og viewer), to prosjekter og
en offentlig OAuth2-klient, og skriver ut passordene én gang.

| Hva | Hvor |
|---|---|
| API-dokumentasjon | <http://localhost:8000/docs> |
| Administrasjon | <http://localhost:8000/admin> (logg inn som administratoren) |
| Beredskap | <http://localhost:8000/readyz> |
| Neo4j Browser | <http://localhost:7484> (Bolt `localhost:7697`) |
| Serverlogg | `docker compose -f compose.yaml -f compose.dev.yaml logs -f api` |

Utviklingsoverlegget publiserer Neo4j på 7484/7697 i stedet for
standardportene 7474/7687, som en annen Neo4j på samme maskin ofte holder.
Endre portene med `OPENCDE_DEV_*` i `.env`. To utsjekkinger på samme maskin
deler Compose-prosjektnavnet `kontroll` (`compose.yaml` setter det); gi den
andre `COMPOSE_PROJECT_NAME=kontroll-2` og andre porter i sin `.env`.

## Uten Docker for serveren

Kjør databasen i Docker (eller Neo4j Desktop / Memgraph Lab) og serveren fra
utsjekkingen:

```sh
uv sync
uv run opencde doctor
uv run opencde serve --reload
```

`.env` som `opencde init --dev` skriver, peker på `bolt://127.0.0.1:7697`,
utviklingsoverleggets Bolt-port.

## Memgraph i stedet for Neo4j

```sh
docker compose -f compose.yaml -f compose.memgraph.yaml -f compose.dev.yaml up -d --build
```

Sett `OPENCDE_GRAPH_DIALECT=memgraph` og `OPENCDE_GRAPH_USER=memgraph` i `.env`
når serveren kjører utenfor Docker. Memgraph Lab (`memgraph/lab`) kan pekes
mot `localhost:7697`.

## Testing med Dataspatium

[Dataspatium](https://github.com/marwiss/Dataspatium) er nettleserklienten
som utvikles sammen med denne serveren. Server en utsjekking av den over http
(`python -m http.server 8080` i mappen dens), åpne `http://127.0.0.1:8080/`,
registrer appen som en offentlig klient, og legg til serveren som
OpenCDE-kilde i Dataspatium (*Inhämta*) med `http://localhost:8000` og den
klient-id-en:

```sh
uv run opencde client create "Dataspatium" --public --redirect-uri http://127.0.0.1:8080/oauth-callback.html
```

Med `OPENCDE_DYNAMIC_CLIENT_REGISTRATION=true` i `.env` registrerer appen seg
selv i stedet. CORS tillater alle opprinnelser som standard, så ingen flere
innstillinger trengs; `OPENCDE_REQUEST_LOG_ENABLED=true` lar `/admin/requests`
vise serversiden av appens kall. Den fullstendige sjekklisten er
[docs/acceptance.md](../../acceptance.md), del C.

## Start på nytt

```sh
docker compose -f compose.yaml -f compose.dev.yaml down -v   # fjerner volumene: database og filer
```
