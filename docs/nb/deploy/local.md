# Lokal test (Windows, macOS, Linux)

Alt kjører i Docker på din maskin; ingenting kan nås utenfra.

## Krav

- Docker Desktop (Windows, macOS) eller Docker Engine med compose-tillegget (Linux)
- eller Podman 5 med `podman compose`: de samme filene virker, se [Podman](#podman) nedenfor
- [uv](https://docs.astral.sh/uv/) for kommandolinjeverktøyene

## Trinn

```sh
git clone https://github.com/marwiss/Dataregium.git
cd Dataregium
uv run opencde init --dev                                 # skriver .env med nye hemmeligheter
docker compose up -d --build
docker compose exec api opencde seed
```

`opencde seed` oppretter demonstrasjonsbrukere (en administrator og en bruker
for hver av rollene manager, editor, contributor og viewer), to prosjekter og
en offentlig OAuth2-klient, og skriver ut passordene én gang.

| Hva | Hvor |
|---|---|
| API-dokumentasjon | <http://127.0.0.1:8000/docs> |
| Administrasjon | <http://127.0.0.1:8000/admin> (logg inn som administratoren) |
| Beredskap | <http://127.0.0.1:8000/readyz> |
| Neo4j Browser | <http://127.0.0.1:7484> (Bolt `127.0.0.1:7697`) |
| Serverlogg | `docker compose logs -f api` |

Utviklingsoverlegget publiserer Neo4j på 7484/7697 i stedet for
standardportene 7474/7687, som en annen Neo4j på samme maskin ofte holder.
Endre portene med `OPENCDE_DEV_*` i `.env`. To utsjekkinger på samme maskin
deler Compose-prosjektnavnet `dataregium` (`docker/compose.yaml` setter det); gi den
andre `COMPOSE_PROJECT_NAME=dataregium-2` og andre porter i sin `.env`.

En installasjon som ble gjort mens prosjektet fortsatt het Kontroll, har dataene
sine i volumer som heter `kontroll_…`. Den beholder dem med
`COMPOSE_PROJECT_NAME=kontroll` i `.env`, som går foran navnet i `docker/compose.yaml`;
uten det starter neste `up` et nytt prosjekt med tomme volumer.

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
# .env: COMPOSE_FILE=docker/compose.yaml:docker/compose.memgraph.yaml:docker/compose.dev.yaml
docker compose up -d --build
```

Sett `OPENCDE_GRAPH_DIALECT=memgraph` og `OPENCDE_GRAPH_USER=memgraph` i `.env`
når serveren kjører utenfor Docker. Memgraph Lab (`memgraph/lab`) kan pekes
mot `127.0.0.1:7697`.

## Testing med Dataspatium

[Dataspatium](https://github.com/marwiss/Dataspatium) er nettleserklienten
som utvikles sammen med denne serveren. Server en utsjekking av den over http
(`python -m http.server 8080` i mappen dens), åpne `http://127.0.0.1:8080/`,
registrer appen som en offentlig klient, og legg til serveren som
OpenCDE-kilde i Dataspatium (*Inhämta*) med `http://127.0.0.1:8000` og den
klient-id-en:

```sh
uv run opencde client create "Dataspatium" --public --redirect-uri http://127.0.0.1:8080/oauth-callback.html
```

Med `OPENCDE_DYNAMIC_CLIENT_REGISTRATION=true` i `.env` registrerer appen seg
selv i stedet. CORS tillater alle opprinnelser som standard, så ingen flere
innstillinger trengs; `OPENCDE_REQUEST_LOG_ENABLED=true` lar `/admin/requests`
vise serversiden av appens kall.
[Hurtigstarten](../quickstart.md) har alle trinnene og en feilsøkingstabell.

## Podman

Compose-filene virker med Podman like godt som med Docker: imagene har fulle navn,
dataene ligger i navngitte volumer, bindmonteringene bærer merket `z` for SELinux,
og utviklingsoverlegget binder porter over 1024 på 127.0.0.1. Kjør dem med
`podman compose` (Podman 5) eller med kommandoen `docker compose` mot Podmans
socket (`DOCKER_HOST=unix:///run/user/1000/podman/podman.sock`). Rotløs Podman kan
ikke binde portene 80 og 443 for produksjonsoverlegget: sett
`sysctl net.ipv4.ip_unprivileged_port_start=80`, eller kjør den stakken som root.
Podman er gratis (Apache-2.0); testene kjører med Docker, og Podman er ikke en del
av CI.

## Start på nytt

```sh
docker compose down -v   # fjerner volumene: database og filer
```
