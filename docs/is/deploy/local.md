# Staðbundin prófun (Windows, macOS, Linux)

Allt keyrir í Docker á tölvunni þinni; ekkert er aðgengilegt að utan.

## Kröfur

- Docker Desktop (Windows, macOS) eða Docker Engine með compose-viðbótinni (Linux)
- [uv](https://docs.astral.sh/uv/) fyrir skipanalínutólin

## Skref

```sh
git clone https://github.com/marwiss/Dataregium.git
cd Dataregium
uv run opencde init --dev                                 # skrifar .env með nýjum leyndarmálum
docker compose -f compose.yaml -f compose.dev.yaml up -d --build
docker compose -f compose.yaml -f compose.dev.yaml exec api opencde seed
```

`opencde seed` býr til sýninotendur (stjórnanda og einn notanda fyrir hvert
hlutverkanna manager, editor, contributor og viewer), tvö verkefni og
opinberan OAuth2-biðlara, og prentar lykilorðin einu sinni.

| Hvað | Hvar |
|---|---|
| API-skjölun | <http://127.0.0.1:8000/docs> |
| Stjórnun | <http://127.0.0.1:8000/admin> (skráðu þig inn sem stjórnandinn) |
| Viðbúnaður | <http://127.0.0.1:8000/readyz> |
| Neo4j Browser | <http://127.0.0.1:7484> (Bolt `127.0.0.1:7697`) |
| Atvikaskrá þjónsins | `docker compose -f compose.yaml -f compose.dev.yaml logs -f api` |

Þróunaryfirlagið birtir Neo4j á 7484/7697 frekar en sjálfgefnu gáttunum
7474/7687, sem annar Neo4j á sömu tölvu heldur oft. Breyttu gáttunum með
`OPENCDE_DEV_*` í `.env`. Tvö útgáfusöfn á sömu tölvu deila
Compose-verkefnisheitinu `kontroll` (`compose.yaml` setur það); gefðu hinu
síðara `COMPOSE_PROJECT_NAME=kontroll-2` og aðrar gáttir í sinni `.env`.

## Án Docker fyrir þjóninn

Keyrðu gagnagrunninn í Docker (eða Neo4j Desktop / Memgraph Lab) og þjóninn
úr útgáfusafninu:

```sh
uv sync
uv run opencde doctor
uv run opencde serve --reload
```

`.env`, sem `opencde init --dev` skrifar, vísar á `bolt://127.0.0.1:7697`,
Bolt-gátt þróunaryfirlagsins.

## Memgraph í stað Neo4j

```sh
docker compose -f compose.yaml -f compose.memgraph.yaml -f compose.dev.yaml up -d --build
```

Settu `OPENCDE_GRAPH_DIALECT=memgraph` og `OPENCDE_GRAPH_USER=memgraph` í
`.env` þegar þjónninn keyrir utan Docker. Memgraph Lab (`memgraph/lab`) má
beina á `127.0.0.1:7697`.

## Prófun með Dataspatium

[Dataspatium](https://github.com/marwiss/Dataspatium) er vafrabiðlarinn sem
er þróaður samhliða þessum þjóni. Þjónaðu afriti af honum yfir http
(`python -m http.server 8080` í möppu hans), opnaðu `http://127.0.0.1:8080/`,
skráðu forritið sem opinberan biðlara og bættu þjóninum við sem
OpenCDE-uppsprettu í Dataspatium (*Inhämta*) með `http://127.0.0.1:8000` og
því biðlaraauðkenni:

```sh
uv run opencde client create "Dataspatium" --public --redirect-uri http://127.0.0.1:8080/oauth-callback.html
```

Með `OPENCDE_DYNAMIC_CLIENT_REGISTRATION=true` í `.env` skráir forritið sig
sjálft í staðinn. CORS leyfir sjálfgefið allan uppruna, svo engrar frekari
stillingar er þörf; `OPENCDE_REQUEST_LOG_ENABLED=true` lætur `/admin/requests`
sýna þjónshlið kalla forritsins. Gátlistinn í heild er
[docs/acceptance.md](../../acceptance.md), kafli C.
[Fljótlega byrjunin](../quickstart.md) hefur öll skrefin og bilanaleitartöflu.

## Hreint borð

```sh
docker compose -f compose.yaml -f compose.dev.yaml down -v   # fjarlægir gagnageymslurnar: gagnagrunn og skrár
```
