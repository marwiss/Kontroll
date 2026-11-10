# Lokalt test (Windows, macOS, Linux)

Allt körs i Docker på din dator; ingenting går att nå utifrån.

## Krav

- Docker Desktop (Windows, macOS) eller Docker Engine med compose-tillägget (Linux)
- eller Podman 5 med `podman compose`: samma filer fungerar, se [Podman](#podman) nedan
- [uv](https://docs.astral.sh/uv/) för kommandoradsverktygen

## Steg

```sh
git clone https://github.com/marwiss/Dataregium.git
cd Dataregium
uv run opencde init --dev                                 # skriver .env med nya hemligheter
docker compose up -d --build
docker compose exec api opencde seed
```

`opencde seed` skapar demonstrationsanvändare (en administratör och en
användare för var och en av rollerna manager, editor, contributor och
viewer), två projekt och en publik OAuth2-klient, och skriver ut lösenorden
en gång.

| Vad | Var |
|---|---|
| API-dokumentation | <http://127.0.0.1:8000/docs> |
| Administration | <http://127.0.0.1:8000/admin> (logga in som administratören) |
| Beredskap | <http://127.0.0.1:8000/readyz> |
| Neo4j Browser | <http://127.0.0.1:7484> (Bolt `127.0.0.1:7697`) |
| Serverlogg | `docker compose logs -f api` |

Utvecklingsöverlagringen publicerar Neo4j på 7484/7697 i stället för
standardportarna 7474/7687, som en annan Neo4j på samma dator ofta upptar.
Ändra portarna med `OPENCDE_DEV_*` i `.env`. Två utcheckningar på samma dator
delar Compose-projektnamnet `dataregium` (`docker/compose.yaml` sätter det); ge den
andra `COMPOSE_PROJECT_NAME=dataregium-2` och andra portar i sin `.env`.

En installation som gjordes när projektet ännu hette Kontroll har sitt data i
volymer som heter `kontroll_…`. Den behåller dem med
`COMPOSE_PROJECT_NAME=kontroll` i `.env`, som går före namnet i `docker/compose.yaml`;
utan det startar nästa `up` ett nytt projekt med tomma volymer.

## Utan Docker för servern

Kör databasen i Docker (eller Neo4j Desktop / Memgraph Lab) och servern från
utcheckningen:

```sh
uv sync
uv run opencde doctor
uv run opencde serve --reload
```

`.env` som `opencde init --dev` skriver pekar på `bolt://127.0.0.1:7697`,
utvecklingsöverlagringens Bolt-port.

## Memgraph i stället för Neo4j

```sh
# .env: COMPOSE_FILE=docker/compose.yaml:docker/compose.memgraph.yaml:docker/compose.dev.yaml
docker compose up -d --build
```

Sätt `OPENCDE_GRAPH_DIALECT=memgraph` och `OPENCDE_GRAPH_USER=memgraph` i
`.env` när servern körs utanför Docker. Memgraph Lab (`memgraph/lab`) kan
pekas mot `127.0.0.1:7697`.

## Test med Dataspatium

[Dataspatium](https://github.com/marwiss/Dataspatium) är webbläsarklienten
som utvecklas tillsammans med den här servern. Servera en utcheckning av den
över http (`python -m http.server 8080` i dess mapp), öppna
`http://127.0.0.1:8080/`, registrera appen som en publik klient och lägg till
servern som OpenCDE-källa i Dataspatium (*Inhämta*) med
`http://127.0.0.1:8000` och det klient-id:t:

```sh
uv run opencde client create "Dataspatium" --public --redirect-uri http://127.0.0.1:8080/oauth-callback.html
```

Med `OPENCDE_DYNAMIC_CLIENT_REGISTRATION=true` i `.env` registrerar appen sig
själv i stället. CORS tillåter alla ursprung som standard, så ingen mer
inställning behövs; `OPENCDE_REQUEST_LOG_ENABLED=true` låter `/admin/requests`
visa serversidan av appens anrop.
[Snabbstarten](../quickstart.md) har alla steg och en felsökningstabell.

## Podman

Compose-filerna fungerar med Podman lika väl som med Docker: imagerna har
fullständiga namn, datat ligger i namngivna volymer, bindmonteringarna bär etiketten
`z` för SELinux, och utvecklingsöverlagringen binder portar över 1024 på 127.0.0.1.
Kör dem med `podman compose` (Podman 5) eller med kommandot `docker compose` mot
Podmans socket (`DOCKER_HOST=unix:///run/user/1000/podman/podman.sock`). Rotlös
Podman kan inte binda portarna 80 och 443 åt produktionsöverlagringen: sätt
`sysctl net.ipv4.ip_unprivileged_port_start=80` eller kör den stacken som root.
Podman är kostnadsfritt (Apache-2.0); testerna körs med Docker, och Podman ingår
inte i CI.

## Börja om från början

```sh
docker compose down -v   # tar bort volymerna: databas och filer
```
