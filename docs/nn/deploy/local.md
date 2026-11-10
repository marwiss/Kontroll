# Lokal test (Windows, macOS, Linux)

Alt køyrer i Docker på maskina di; ingenting kan nåast utanfrå.

## Krav

- Docker Desktop (Windows, macOS) eller Docker Engine med compose-tillegget (Linux)
- [uv](https://docs.astral.sh/uv/) for kommandolinjeverktøya

## Steg

```sh
git clone https://github.com/marwiss/Dataregium.git
cd Dataregium
uv run opencde init --dev                                 # skriv .env med nye løyndomar
docker compose up -d --build
docker compose exec api opencde seed
```

`opencde seed` opprettar demonstrasjonsbrukarar (ein administrator og ein
brukar for kvar av rollene manager, editor, contributor og viewer), to
prosjekt og ein offentleg OAuth2-klient, og skriv ut passorda éin gong.

| Kva | Kvar |
|---|---|
| API-dokumentasjon | <http://127.0.0.1:8000/docs> |
| Administrasjon | <http://127.0.0.1:8000/admin> (logg inn som administratoren) |
| Beredskap | <http://127.0.0.1:8000/readyz> |
| Neo4j Browser | <http://127.0.0.1:7484> (Bolt `127.0.0.1:7697`) |
| Serverlogg | `docker compose logs -f api` |

Utviklingsoverlegget publiserer Neo4j på 7484/7697 i staden for
standardportane 7474/7687, som ein annan Neo4j på same maskin ofte held. Endre
portane med `OPENCDE_DEV_*` i `.env`. To utsjekkingar på same maskin deler
Compose-prosjektnamnet `dataregium` (`docker/compose.yaml` set det); gje den andre
`COMPOSE_PROJECT_NAME=dataregium-2` og andre portar i si `.env`.

Ein installasjon som vart gjord medan prosjektet framleis heitte Kontroll, har
dataa sine i volum som heiter `kontroll_…`. Han held på dei med
`COMPOSE_PROJECT_NAME=kontroll` i `.env`, som går føre namnet i `docker/compose.yaml`;
utan det startar neste `up` eit nytt prosjekt med tomme volum.

## Utan Docker for serveren

Køyr databasen i Docker (eller Neo4j Desktop / Memgraph Lab) og serveren frå
utsjekkinga:

```sh
uv sync
uv run opencde doctor
uv run opencde serve --reload
```

`.env` som `opencde init --dev` skriv, peikar på `bolt://127.0.0.1:7697`,
Bolt-porten til utviklingsoverlegget.

## Memgraph i staden for Neo4j

```sh
# .env: COMPOSE_FILE=docker/compose.yaml:docker/compose.memgraph.yaml:docker/compose.dev.yaml
docker compose up -d --build
```

Set `OPENCDE_GRAPH_DIALECT=memgraph` og `OPENCDE_GRAPH_USER=memgraph` i `.env`
når serveren køyrer utanfor Docker. Memgraph Lab (`memgraph/lab`) kan peikast
mot `127.0.0.1:7697`.

## Testing med Dataspatium

[Dataspatium](https://github.com/marwiss/Dataspatium) er nettlesarklienten
som blir utvikla saman med denne serveren. Server ei utsjekking av han over
http (`python -m http.server 8080` i mappa hans), opne
`http://127.0.0.1:8080/`, registrer appen som ein offentleg klient, og legg til
serveren som OpenCDE-kjelde i Dataspatium (*Inhämta*) med
`http://127.0.0.1:8000` og den klient-id-en:

```sh
uv run opencde client create "Dataspatium" --public --redirect-uri http://127.0.0.1:8080/oauth-callback.html
```

Med `OPENCDE_DYNAMIC_CLIENT_REGISTRATION=true` i `.env` registrerer appen seg
sjølv i staden. CORS tillèt alle opphav som standard, så ingen fleire
innstillingar trengst; `OPENCDE_REQUEST_LOG_ENABLED=true` lèt `/admin/requests`
vise serversida av kalla til appen. Den fullstendige sjekklista er
[docs/acceptance.md](../../acceptance.md), del C.
[Snøggstarten](../quickstart.md) har alle stega og ein feilsøkingstabell.

## Start på nytt

```sh
docker compose down -v   # fjernar voluma: database og filer
```
