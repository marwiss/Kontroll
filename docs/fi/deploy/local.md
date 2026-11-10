# Paikallinen testi (Windows, macOS, Linux)

Kaikki toimii Dockerissa omalla koneellasi; mihinkään ei pääse ulkopuolelta.

## Vaatimukset

- Docker Desktop (Windows, macOS) tai Docker Engine compose-liitännäisellä (Linux)
- tai Podman 5 ja `podman compose`: samat tiedostot toimivat, katso [Podman](#podman) alla
- [uv](https://docs.astral.sh/uv/) komentorivityökaluja varten

## Vaiheet

```sh
git clone https://github.com/marwiss/Dataregium.git
cd Dataregium
uv run opencde init --dev                                 # kirjoittaa .env-tiedoston uusilla salaisuuksilla
docker compose up -d --build
docker compose exec api opencde seed
```

`opencde seed` luo demokäyttäjät (järjestelmänvalvojan sekä yhden käyttäjän
kullekin roolille manager, editor, contributor ja viewer), kaksi projektia
ja julkisen OAuth2-asiakkaan ja tulostaa salasanat kerran.

| Mikä | Missä |
|---|---|
| API-dokumentaatio | <http://127.0.0.1:8000/docs> |
| Hallinta | <http://127.0.0.1:8000/admin> (kirjaudu järjestelmänvalvojana) |
| Valmius | <http://127.0.0.1:8000/readyz> |
| Neo4j Browser | <http://127.0.0.1:7484> (Bolt `127.0.0.1:7697`) |
| Palvelimen loki | `docker compose logs -f api` |

Kehityskerros (`docker/compose.dev.yaml`) julkaisee Neo4j:n porteissa 7484/7697
oletusporttien 7474/7687 sijaan, jotka toinen samalla koneella oleva Neo4j
usein varaa. Vaihda portit `.env`-tiedoston `OPENCDE_DEV_*`-muuttujilla. Kaksi
lähdekoodikopiota samalla koneella jakavat Compose-projektinimen `dataregium`
(`docker/compose.yaml` asettaa sen); anna toiselle `.env`-tiedostossa
`COMPOSE_PROJECT_NAME=dataregium-2` ja eri portit.

Asennuksella, joka tehtiin projektin ollessa vielä nimeltään Kontroll, on datansa
taltioissa nimeltä `kontroll_…`. Se säilyttää ne, kun `.env`-tiedostossa on
`COMPOSE_PROJECT_NAME=kontroll`, joka ohittaa `docker/compose.yaml`-tiedoston nimen;
ilman sitä seuraava `up` käynnistää uuden projektin tyhjillä taltioilla.

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
# .env: COMPOSE_FILE=docker/compose.yaml:docker/compose.memgraph.yaml:docker/compose.dev.yaml
docker compose up -d --build
```

Aseta `.env`-tiedostoon `OPENCDE_GRAPH_DIALECT=memgraph` ja
`OPENCDE_GRAPH_USER=memgraph`, kun palvelin ajetaan Dockerin ulkopuolella.
Memgraph Labin (`memgraph/lab`) voi osoittaa osoitteeseen `127.0.0.1:7697`.

## Testaus Dataspatiumin kanssa

[Dataspatium](https://github.com/marwiss/Dataspatium) on selainasiakas, jota
kehitetään yhdessä tämän palvelimen kanssa. Tarjoile sen lähdekoodi http:n yli
(`python -m http.server 8080` sen kansiossa), avaa `http://127.0.0.1:8080/`,
rekisteröi sovellus julkiseksi asiakkaaksi ja lisää palvelin OpenCDE-lähteeksi
Dataspatiumiin (*Inhämta*) osoitteella `http://127.0.0.1:8000` ja tällä
asiakastunnuksella:

```sh
uv run opencde client create "Dataspatium" --public --redirect-uri http://127.0.0.1:8080/oauth-callback.html
```

Kun `.env`-tiedostossa on `OPENCDE_DYNAMIC_CLIENT_REGISTRATION=true`, sovellus
rekisteröi itsensä. CORS sallii oletuksena kaikki alkuperät, joten muita
asetuksia ei tarvita; `OPENCDE_REQUEST_LOG_ENABLED=true` antaa
`/admin/requests`-sivun näyttää sovelluksen kutsujen palvelinpuolen.
[Pika-aloituksessa](../quickstart.md) on kaikki vaiheet ja vianmääritystaulukko.

## Paikallinen moottori

Dataregium voi toimia omalla tietokoneella Dataspatiumin takana olevana
moottorina malleille, jotka ovat suurempia kuin selaimen välilehti kantaa
(ADR 0023). `opencde init --local` kirjoittaa sitä varten `.env`-tiedoston, ja
`OPENCDE_ENVIRONMENT=local` saa palvelimen pysymään siinä: julkisen osoitteen on
oltava loopback, tietokannan salasana ja salainen avain vaaditaan,
CORS-alkuperät on nimettävä (`*` hylätään), tietokannan osoitetta ei saa
julkaista, ja `opencde serve` kieltäytyy muista liitännöistä kuin loopbackista.
Pyyntöön, jonka `Host` ei ole `127.0.0.1`, `localhost` tai `::1`, vastataan
`421` ennen kaikkea muuta, jotta internetissä oleva sivu ei tavoita moottoria
omalla nimellään, joka osoittaa loopbackiin. Julkinen sivu, joka kysyy
esitarkistuksessaan (`Access-Control-Request-Private-Network: true`),
sallitaan, kun sen alkuperä on nimetty. OAuth2 ja PKCE vaaditaan paikallisesti
kuten kaikkialla. Tiedoston kirjoittamat alkuperät ovat `null` (Dataspatium
avattuna tiedostosta), `http://127.0.0.1:8080` (paikallinen http-palvelin) ja
`https://marwiss.github.io`; poista `null`, kun sovellus toimii
http-alkuperästä.

```sh
uv run opencde init --local   # .env: OPENCDE_ENVIRONMENT=local, random passwords, the origins Dataspatium comes from
docker compose up -d          # the API on http://127.0.0.1:8000 only; the database is never published
```

## Podman

Compose-tiedostot toimivat Podmanilla yhtä hyvin kuin Dockerilla: imageilla on
täydet nimet, data on nimetyissä taltioissa, sidosliitoksilla on SELinuxin
`z`-merkintä, ja kehityskerros sitoo portit yli 1024 osoitteeseen 127.0.0.1. Aja ne
komennolla `podman compose` (Podman 5) tai komennolla `docker compose` Podmanin
socketia vasten (`DOCKER_HOST=unix:///run/user/1000/podman/podman.sock`). Juureton
Podman ei voi sitoa portteja 80 ja 443 tuotantokerrokselle: aseta
`sysctl net.ipv4.ip_unprivileged_port_start=80` tai aja se pino roottina. Podman on
maksuton (Apache-2.0); testit ajetaan Dockerilla, eikä Podman kuulu CI:hin.

## Puhtaalta pöydältä

```sh
docker compose down -v   # poistaa taltiot: tietokannan ja tiedostot
```
