# Paikallinen testi (Windows, macOS, Linux)

Kaikki toimii Dockerissa omalla koneellasi; mihinkään ei pääse ulkopuolelta.

## Vaatimukset

- Docker Desktop (Windows, macOS) tai Docker Engine compose-liitännäisellä (Linux)
- [uv](https://docs.astral.sh/uv/) komentorivityökaluja varten

## Vaiheet

```sh
git clone https://github.com/marwiss/Kontroll.git
cd Kontroll
uv run opencde init --dev                                 # kirjoittaa .env-tiedoston uusilla salaisuuksilla
docker compose -f compose.yaml -f compose.dev.yaml up -d --build
docker compose -f compose.yaml -f compose.dev.yaml exec api opencde seed
```

`opencde seed` luo demokäyttäjät (järjestelmänvalvojan sekä yhden käyttäjän
kullekin roolille manager, editor, contributor ja viewer), kaksi projektia
ja julkisen OAuth2-asiakkaan ja tulostaa salasanat kerran.

| Mikä | Missä |
|---|---|
| API-dokumentaatio | <http://localhost:8000/docs> |
| Hallinta | <http://localhost:8000/admin> (kirjaudu järjestelmänvalvojana) |
| Valmius | <http://localhost:8000/readyz> |
| Neo4j Browser | <http://localhost:7484> (Bolt `localhost:7697`) |
| Palvelimen loki | `docker compose -f compose.yaml -f compose.dev.yaml logs -f api` |

Kehityskerros (`compose.dev.yaml`) julkaisee Neo4j:n porteissa 7484/7697
oletusporttien 7474/7687 sijaan, jotka toinen samalla koneella oleva Neo4j
usein varaa. Vaihda portit `.env`-tiedoston `OPENCDE_DEV_*`-muuttujilla.

## Ilman Dockeria palvelimelle

Aja tietokanta Dockerissa (tai Neo4j Desktopissa / Memgraph Labissa) ja
palvelin lähdekoodista:

```sh
uv sync
uv run opencde doctor
uv run opencde serve --reload
```

`opencde init --dev`:n kirjoittama `.env` osoittaa osoitteeseen
`bolt://127.0.0.1:7697`, kehityskerroksen Bolt-porttiin.

## Memgraph Neo4j:n sijaan

```sh
docker compose -f compose.yaml -f compose.memgraph.yaml -f compose.dev.yaml up -d --build
```

Aseta `.env`-tiedostoon `OPENCDE_GRAPH_DIALECT=memgraph` ja
`OPENCDE_GRAPH_USER=memgraph`, kun palvelin ajetaan Dockerin ulkopuolella.
Memgraph Labin (`memgraph/lab`) voi osoittaa osoitteeseen `localhost:7697`.

## Testaus Dataspatiumin kanssa

[Dataspatium](https://github.com/marwiss/Dataspatium) on selainasiakas, jota
kehitetään yhdessä tämän palvelimen kanssa. Tarjoile sen lähdekoodi http:n yli
(`python -m http.server 8080` sen kansiossa), avaa `http://127.0.0.1:8080/`,
rekisteröi sovellus julkiseksi asiakkaaksi ja lisää palvelin OpenCDE-lähteeksi
Dataspatiumiin (*Inhämta*) osoitteella `http://localhost:8000` ja tällä
asiakastunnuksella:

```sh
uv run opencde client create "Dataspatium" --public --redirect-uri http://127.0.0.1:8080/oauth-callback.html
```

Kun `.env`-tiedostossa on `OPENCDE_DYNAMIC_CLIENT_REGISTRATION=true`, sovellus
rekisteröi itsensä. CORS sallii oletuksena kaikki alkuperät, joten muita
asetuksia ei tarvita; `OPENCDE_REQUEST_LOG_ENABLED=true` antaa
`/admin/requests`-sivun näyttää sovelluksen kutsujen palvelinpuolen. Koko
tarkistuslista on [docs/acceptance.md](../../acceptance.md), osa C.

## Puhtaalta pöydältä

```sh
docker compose -f compose.yaml -f compose.dev.yaml down -v   # poistaa taltiot: tietokannan ja tiedostot
```
