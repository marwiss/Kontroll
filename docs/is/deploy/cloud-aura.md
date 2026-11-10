# Umsjáður gagnagrunnur og gámaþjónusta (enginn eigin þjónn)

Keyrðu API-ið á gámaþjónustu (Fly.io, Render, Railway, Azure Container Apps,
Google Cloud Run) og grafið á umsjáðri Neo4j (AuraDB) eða Memgraph
Cloud-tilviki.

## Gagnagrunnur

- **Neo4j AuraDB Free** hentar fyrir sýningar: um 200 000 hnútar, settur í
  bið eftir 72 klukkustundir án virkni og eytt eftir 30 daga bið. AuraDB
  Professional fyrir allt sem þarf að halda uppi.
- Búðu til tilvikið og skráðu hjá þér URI-ið
  `neo4j+s://xxxx.databases.neo4j.io`, notandann og lykilorðið.
- **Memgraph Cloud** virkar á sama hátt með `bolt+s://` og
  `OPENCDE_GRAPH_DIALECT=memgraph`.

## API-gámur

Settu upp `ghcr.io/marwiss/opencdeserver:<version>` með þessum breytum:

```
OPENCDE_ENVIRONMENT=production
OPENCDE_PUBLIC_URL=https://<https-vistfang þjónustunnar>
OPENCDE_SECRET_KEY=<48 slembin tákn>
OPENCDE_GRAPH_DIALECT=neo4j
OPENCDE_GRAPH_URI=neo4j+s://xxxx.databases.neo4j.io
OPENCDE_GRAPH_USER=neo4j
OPENCDE_GRAPH_PASSWORD=<frá Aura>
OPENCDE_DATA_DIR=/data
OPENCDE_TRUSTED_PROXIES=["0.0.0.0/0"]
```

- Tengdu varanlega gagnageymslu við `/data`: upphöluð skjöl og myndir eru
  þar. Án geymslu hverfa þau við næstu uppsetningu.
- `OPENCDE_TRUSTED_PROXIES` er vítt vegna þess að vistföng álagsjafnara
  vettvangsins eru ekki föst; vettvangurinn tryggir að aðeins milliþjónn hans
  nái gámnum.
- Gámurinn hlustar á 8000 og svarar `/healthz` (lífsmark) og `/readyz`
  (viðbúnaður, athugar gagnagrunninn).
- Búðu til fyrsta stjórnandann úr skel vettvangsins:
  `opencde user create admin --admin`.

## Öryggisafrit

Hliðargámurinn `backup` í `docker/compose.prod.yaml` gildir ekki hér. Tímasettu
`opencde backup /data/backups` (cron-verk eða tímasett verk á vettvanginum)
og afritaðu möppuna í hlutageymslu; Aura hefur líka sínar eigin skyndimyndir.

## Eigin þjónn með gagnagrunninn annars staðar

Ef þú keyrir restina af staflanum sjálfur, eins og á [eigin þjóni](vps-caddy.md), og aðeins
gagnagrunninn annars staðar, tilgreindu hvar hann er í `.env` og slepptu gagnagrunnsgámnum:

```
OPENCDE_STACK_GRAPH_URI=neo4j+s://xxxx.databases.neo4j.io
OPENCDE_GRAPH_USER=neo4j
OPENCDE_GRAPH_PASSWORD=<frá Aura>
```

```bash
# .env: COMPOSE_FILE=docker/compose.yaml:docker/compose.prod.yaml:docker/compose.external-db.yaml
docker compose up -d
```

API og öryggisafritunin nota þá þann gagnagrunn. Fyrir Memgraph skaltu einnig stilla
`OPENCDE_GRAPH_DIALECT=memgraph`.
