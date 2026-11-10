# Lokal test (Windows, macOS, Linux)

Alt køyrer i Docker på maskina di; ingenting kan nåast utanfrå.

## Krav

- Docker Desktop (Windows, macOS) eller Docker Engine med compose-tillegget (Linux)
- eller Podman 5 med `podman compose`: dei same filene verkar, sjå [Podman](#podman) nedanfor
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
vise serversida av kalla til appen.
[Snøggstarten](../quickstart.md) har alle stega og ein feilsøkingstabell.

## Den lokale motoren

Dataregium kan køyre på den eigne datamaskina som motoren bak Dataspatium for
modellar større enn ei nettlesarfane rommar (ADR 0023). `opencde init --local`
skriv ei `.env` for det, og `OPENCDE_ENVIRONMENT=local` får serveren til å
halde seg til det: den offentlege adressa må vere loopback, databasepassord og
hemmeleg nøkkel krevst, CORS-opphava må namngjevast (`*` blir avvist), inga
databaseadresse kan publiserast, og `opencde serve` avviser andre grensesnitt
enn loopback. Ein førespurnad der `Host` ikkje er `127.0.0.1`, `localhost`
eller `::1`, blir svara med `421` før alt anna, slik at ei side på internett
ikkje når motoren gjennom eit eige namn som peikar på loopback. Ei offentleg
side som spør i sin preflight (`Access-Control-Request-Private-Network: true`)
blir tillaten når opphavet er namngjeve. OAuth2 med PKCE krevst lokalt som
overalt. Opphava fila skriv, er `null` (Dataspatium opna frå ei fil),
`http://127.0.0.1:8080` (ein lokal http-tenar) og `https://marwiss.github.io`;
fjern `null` når appen køyrer frå eit http-opphav.

```sh
uv run opencde init --local   # .env: OPENCDE_ENVIRONMENT=local, random passwords, the origins Dataspatium comes from
docker compose up -d          # the API on http://127.0.0.1:8000 only; the database is never published
```

## Podman

Compose-filene verkar med Podman like godt som med Docker: imagea har fulle namn,
dataa ligg i namngjevne volum, bindmonteringane ber merket `z` for SELinux, og
utviklingsoverlegget bind portar over 1024 på 127.0.0.1. Køyr dei med
`podman compose` (Podman 5) eller med kommandoen `docker compose` mot Podman sin
socket (`DOCKER_HOST=unix:///run/user/1000/podman/podman.sock`). Rotlaus Podman kan
ikkje binde portane 80 og 443 for produksjonsoverlegget: set
`sysctl net.ipv4.ip_unprivileged_port_start=80`, eller køyr den stabelen som root.
Podman er gratis (Apache-2.0); testane køyrer med Docker, og Podman er ikkje ein
del av CI.

## Start på nytt

```sh
docker compose down -v   # fjernar voluma: database og filer
```
