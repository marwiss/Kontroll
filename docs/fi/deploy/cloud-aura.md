# Hallinnoitu tietokanta ja konttipalvelu (ilman omaa palvelinta)

Aja API konttipalvelussa (Fly.io, Render, Railway, Azure Container Apps,
Google Cloud Run) ja graafi hallinnoidussa Neo4j:ssä (AuraDB) tai Memgraph
Cloud -instanssissa.

## Tietokanta

- **Neo4j AuraDB Free** sopii demoihin: noin 200 000 solmua, keskeytetään 72
  tunnin käyttämättömyyden jälkeen ja poistetaan 30 päivän keskeytyksen
  jälkeen. AuraDB Professional kaikkeen, jonka on pysyttävä pystyssä.
- Luo instanssi ja merkitse muistiin URI `neo4j+s://xxxx.databases.neo4j.io`,
  käyttäjä ja salasana.
- **Memgraph Cloud** toimii samalla tavalla `bolt+s://`-osoitteella ja
  asetuksella `OPENCDE_GRAPH_DIALECT=memgraph`.

## API-kontti

Ota käyttöön `ghcr.io/marwiss/opencdeserver:<version>` näillä muuttujilla:

```
OPENCDE_ENVIRONMENT=production
OPENCDE_PUBLIC_URL=https://<palvelun https-osoite>
OPENCDE_SECRET_KEY=<48 satunnaista merkkiä>
OPENCDE_GRAPH_DIALECT=neo4j
OPENCDE_GRAPH_URI=neo4j+s://xxxx.databases.neo4j.io
OPENCDE_GRAPH_USER=neo4j
OPENCDE_GRAPH_PASSWORD=<Aurasta>
OPENCDE_DATA_DIR=/data
OPENCDE_TRUSTED_PROXIES=["0.0.0.0/0"]
```

- Liitä pysyvä taltio polkuun `/data`: ladatut asiakirjat ja kuvat ovat
  siellä. Ilman taltiota ne katoavat seuraavassa käyttöönotossa.
- `OPENCDE_TRUSTED_PROXIES` on laaja, koska alustan kuormantasaajien osoitteet
  eivät ole kiinteitä; alusta takaa, että vain sen välityspalvelin pääsee
  konttiin.
- Kontti kuuntelee porttia 8000 ja vastaa osoitteissa `/healthz` (elossaolo)
  ja `/readyz` (valmius, tarkistaa tietokannan).
- Luo ensimmäinen järjestelmänvalvoja alustan komentotulkista:
  `opencde user create admin --admin`.

## Varmuuskopiot

`compose.prod.yaml`-tiedoston `backup`-apukontti ei päde tässä. Ajasta
`opencde backup /data/backups` (cron-työ tai alustan ajastettu tehtävä) ja
kopioi kansio objektitallennukseen; Auralla on lisäksi omat
tilannevedoksensa.
