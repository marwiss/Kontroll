# Lokalt test (Windows, macOS, Linux)

Allt körs i Docker på din dator; ingenting går att nå utifrån.

## Krav

- Docker Desktop (Windows, macOS) eller Docker Engine med compose-tillägget (Linux)
- [uv](https://docs.astral.sh/uv/) för kommandoradsverktygen

## Steg

```sh
git clone https://github.com/marwiss/Kontroll.git
cd Kontroll
uv run opencde init --dev                                 # skriver .env med nya hemligheter
docker compose -f compose.yaml -f compose.dev.yaml up -d --build
docker compose -f compose.yaml -f compose.dev.yaml exec api opencde seed
```

`opencde seed` skapar demonstrationsanvändare (en administratör och en
användare för var och en av rollerna manager, editor, contributor och
viewer), två projekt och en publik OAuth2-klient, och skriver ut lösenorden
en gång.

| Vad | Var |
|---|---|
| API-dokumentation | <http://localhost:8000/docs> |
| Administration | <http://localhost:8000/admin> (logga in som administratören) |
| Beredskap | <http://localhost:8000/readyz> |
| Neo4j Browser | <http://localhost:7484> (Bolt `localhost:7697`) |
| Serverlogg | `docker compose -f compose.yaml -f compose.dev.yaml logs -f api` |

Utvecklingsöverlagringen publicerar Neo4j på 7484/7697 i stället för
standardportarna 7474/7687, som en annan Neo4j på samma dator ofta upptar.
Ändra portarna med `OPENCDE_DEV_*` i `.env`. Två utcheckningar på samma dator
delar Compose-projektnamnet `kontroll` (`compose.yaml` sätter det); ge den
andra `COMPOSE_PROJECT_NAME=kontroll-2` och andra portar i sin `.env`.

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
docker compose -f compose.yaml -f compose.memgraph.yaml -f compose.dev.yaml up -d --build
```

Sätt `OPENCDE_GRAPH_DIALECT=memgraph` och `OPENCDE_GRAPH_USER=memgraph` i
`.env` när servern körs utanför Docker. Memgraph Lab (`memgraph/lab`) kan
pekas mot `localhost:7697`.

## Test med Dataspatium

[Dataspatium](https://github.com/marwiss/Dataspatium) är webbläsarklienten
som utvecklas tillsammans med den här servern. Servera en utcheckning av den
över http (`python -m http.server 8080` i dess mapp), öppna
`http://127.0.0.1:8080/`, registrera appen som en publik klient och lägg till
servern som OpenCDE-källa i Dataspatium (*Inhämta*) med
`http://localhost:8000` och det klient-id:t:

```sh
uv run opencde client create "Dataspatium" --public --redirect-uri http://127.0.0.1:8080/oauth-callback.html
```

Med `OPENCDE_DYNAMIC_CLIENT_REGISTRATION=true` i `.env` registrerar appen sig
själv i stället. CORS tillåter alla ursprung som standard, så ingen mer
inställning behövs; `OPENCDE_REQUEST_LOG_ENABLED=true` låter `/admin/requests`
visa serversidan av appens anrop. Hela checklistan finns i
[docs/acceptance.md](../../acceptance.md), avsnitt C.
[Snabbstarten](../quickstart.md) har alla steg och en felsökningstabell.

## Börja om från början

```sh
docker compose -f compose.yaml -f compose.dev.yaml down -v   # tar bort volymerna: databas och filer
```
