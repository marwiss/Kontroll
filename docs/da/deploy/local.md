# Lokal test (Windows, macOS, Linux)

Alt kører i Docker på din maskine; intet kan nås udefra.

## Krav

- Docker Desktop (Windows, macOS) eller Docker Engine med compose-pluginet (Linux)
- eller Podman 5 med `podman compose`: de samme filer virker, se [Podman](#podman) nedenfor
- [uv](https://docs.astral.sh/uv/) til kommandolinjeværktøjerne

## Trin

```sh
git clone https://github.com/marwiss/Dataregium.git
cd Dataregium
uv run opencde init --dev                                 # skriver .env med nye hemmeligheder
docker compose up -d --build
docker compose exec api opencde seed
```

`opencde seed` opretter demonstrationsbrugere (en administrator og en bruger
for hver af rollerne manager, editor, contributor og viewer), to projekter og
en offentlig OAuth2-klient og udskriver kodeordene én gang.

| Hvad | Hvor |
|---|---|
| API-dokumentation | <http://127.0.0.1:8000/docs> |
| Administration | <http://127.0.0.1:8000/admin> (log ind som administratoren) |
| Parathed | <http://127.0.0.1:8000/readyz> |
| Neo4j Browser | <http://127.0.0.1:7484> (Bolt `127.0.0.1:7697`) |
| Serverlog | `docker compose logs -f api` |

Udviklingsoverlejringen udgiver Neo4j på 7484/7697 i stedet for
standardportene 7474/7687, som en anden Neo4j på samme maskine ofte optager.
Skift portene med `OPENCDE_DEV_*` i `.env`. To checkouts på samme maskine deler
Compose-projektnavnet `dataregium` (`docker/compose.yaml` sætter det); giv det andet
`COMPOSE_PROJECT_NAME=dataregium-2` og andre porte i sin `.env`.

En installation, der blev lavet, mens projektet stadig hed Kontroll, har sine
data i volumener med navnet `kontroll_…`. Den beholder dem med
`COMPOSE_PROJECT_NAME=kontroll` i `.env`, som går forud for navnet i
`docker/compose.yaml`; uden det starter næste `up` et nyt projekt med tomme volumener.

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
# .env: COMPOSE_FILE=docker/compose.yaml:docker/compose.memgraph.yaml:docker/compose.dev.yaml
docker compose up -d --build
```

Sæt `OPENCDE_GRAPH_DIALECT=memgraph` og `OPENCDE_GRAPH_USER=memgraph` i `.env`,
når serveren kører uden for Docker. Memgraph Lab (`memgraph/lab`) kan peges
mod `127.0.0.1:7697`.

## Test med Dataspatium

[Dataspatium](https://github.com/marwiss/Dataspatium) er browserklienten, der
udvikles sammen med denne server. Servér et checkout af den over http
(`python -m http.server 8080` i dens mappe), åbn `http://127.0.0.1:8080/`,
registrér appen som en offentlig klient, og tilføj serveren som OpenCDE-kilde
i Dataspatium (*Inhämta*) med `http://127.0.0.1:8000` og det klient-id:

```sh
uv run opencde client create "Dataspatium" --public --redirect-uri http://127.0.0.1:8080/oauth-callback.html
```

Med `OPENCDE_DYNAMIC_CLIENT_REGISTRATION=true` i `.env` registrerer appen sig
selv i stedet. CORS tillader alle oprindelser som standard, så der skal ikke
indstilles mere; `OPENCDE_REQUEST_LOG_ENABLED=true` lader `/admin/requests`
vise serversiden af appens kald.
[Den hurtige start](../quickstart.md) har alle trin og en fejlfindingstabel.

## Den lokale motor

Dataregium kan køre på ens egen computer som motoren bag Dataspatium for
modeller, der er større end en browserfane rummer (ADR 0023). `opencde init --local`
skriver en `.env` til det, og `OPENCDE_ENVIRONMENT=local` får serveren til at
holde sig til det: den offentlige adresse skal være loopback, databaseadgangskode
og hemmelig nøgle kræves, CORS-oprindelserne skal navngives (`*` afvises), ingen
databaseadresse må offentliggøres, og `opencde serve` afviser andre grænseflader
end loopback. En forespørgsel, hvis `Host` ikke er `127.0.0.1`, `localhost` eller
`::1`, besvares med `421` før alt andet, så en side på internettet ikke når
motoren gennem et eget navn, der peger på loopback. En offentlig side, der
spørger i sin preflight (`Access-Control-Request-Private-Network: true`),
tillades, når dens oprindelse er navngivet. OAuth2 med PKCE kræves lokalt som
overalt. Oprindelserne, filen skriver, er `null` (Dataspatium åbnet fra en
fil), `http://127.0.0.1:8080` (en lokal http-server) og
`https://marwiss.github.io`; fjern `null`, når appen kører fra en
http-oprindelse.

```sh
uv run opencde init --local   # .env: OPENCDE_ENVIRONMENT=local, random passwords, the origins Dataspatium comes from
docker compose up -d          # the API on http://127.0.0.1:8000 only; the database is never published
```

## Podman

Compose-filerne virker med Podman såvel som med Docker: images har fulde navne,
data ligger i navngivne volumener, bindmonteringer bærer mærket `z` til SELinux, og
udviklingsoverlejringen binder porte over 1024 på 127.0.0.1. Kør dem med
`podman compose` (Podman 5) eller med kommandoen `docker compose` mod Podmans
socket (`DOCKER_HOST=unix:///run/user/1000/podman/podman.sock`). Rodløs Podman kan
ikke binde portene 80 og 443 for produktionsoverlejringen: sæt
`sysctl net.ipv4.ip_unprivileged_port_start=80`, eller kør den stak som root.
Podman er gratis (Apache-2.0); testene kører med Docker, og Podman er ikke en del
af CI.

## Ren tavle

```sh
docker compose down -v   # fjerner volumerne: database og filer
```
