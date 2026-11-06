# Administreret database og containertjeneste (uden egen server)

Kør API'et på en containertjeneste (Fly.io, Render, Railway, Azure Container
Apps, Google Cloud Run) og grafen på en administreret Neo4j (AuraDB) eller en
Memgraph Cloud-instans.

## Database

- **Neo4j AuraDB Free** passer til demonstrationer: cirka 200 000 noder, sættes
  på pause efter 72 timer uden aktivitet og slettes efter 30 dages pause.
  AuraDB Professional til alt, der skal holdes kørende.
- Opret instansen, og notér URI'en `neo4j+s://xxxx.databases.neo4j.io`,
  brugeren og kodeordet.
- **Memgraph Cloud** fungerer på samme måde med `bolt+s://` og
  `OPENCDE_GRAPH_DIALECT=memgraph`.

## API-container

Udrul `ghcr.io/marwiss/opencdeserver:<version>` med disse variabler:

```
OPENCDE_ENVIRONMENT=production
OPENCDE_PUBLIC_URL=https://<tjenestens https-adresse>
OPENCDE_SECRET_KEY=<48 tilfældige tegn>
OPENCDE_GRAPH_DIALECT=neo4j
OPENCDE_GRAPH_URI=neo4j+s://xxxx.databases.neo4j.io
OPENCDE_GRAPH_USER=neo4j
OPENCDE_GRAPH_PASSWORD=<fra Aura>
OPENCDE_DATA_DIR=/data
OPENCDE_TRUSTED_PROXIES=["0.0.0.0/0"]
```

- Montér en vedvarende volume på `/data`: uploadede dokumenter og billeder
  ligger der. Uden en volume forsvinder de ved næste udrulning.
- `OPENCDE_TRUSTED_PROXIES` er bred, fordi platformens load balancer-adresser
  ikke er faste; platformen garanterer, at kun dens proxy når containeren.
- Containeren lytter på 8000 og svarer på `/healthz` (liveness) og `/readyz`
  (readiness, tjekker databasen).
- Opret den første administrator fra platformens shell:
  `opencde user create admin --admin`.

## Sikkerhedskopier

Sidevognen `backup` i `compose.prod.yaml` gælder ikke her. Planlæg
`opencde backup /data/backups` (et cron-job eller en planlagt opgave på
platformen), og kopiér mappen til objektlager; Aura har også sine egne
snapshots.

## Egen server med databasen et andet sted

Hvis du selv kører resten af stakken, som på [en egen server](vps-caddy.md), og kun databasen et
andet sted, så angiv, hvor den er, i `.env`, og lad databasecontaineren være ude:

```
OPENCDE_STACK_GRAPH_URI=neo4j+s://xxxx.databases.neo4j.io
OPENCDE_GRAPH_USER=neo4j
OPENCDE_GRAPH_PASSWORD=<fra Aura>
```

```bash
docker compose -f compose.yaml -f compose.prod.yaml -f compose.external-db.yaml up -d
```

API'et og sikkerhedskopieringen bruger så den database. For Memgraph, sæt også
`OPENCDE_GRAPH_DIALECT=memgraph`.
