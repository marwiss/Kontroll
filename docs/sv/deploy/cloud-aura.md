# Hanterad databas och containertjänst (utan egen server)

Kör API:t på en containertjänst (Fly.io, Render, Railway, Azure Container
Apps, Google Cloud Run) och grafen på en hanterad Neo4j (AuraDB) eller en
Memgraph Cloud-instans.

## Databas

- **Neo4j AuraDB Free** passar för demonstrationer: ungefär 200 000 noder,
  pausas efter 72 timmar utan aktivitet och raderas efter 30 dagars paus.
  AuraDB Professional för allt som måste vara uppe.
- Skapa instansen och notera URI:n `neo4j+s://xxxx.databases.neo4j.io`,
  användaren och lösenordet.
- **Memgraph Cloud** fungerar på samma sätt med `bolt+s://` och
  `OPENCDE_GRAPH_DIALECT=memgraph`.

## API-container

Driftsätt `ghcr.io/marwiss/opencdeserver:<version>` med dessa variabler:

```
OPENCDE_ENVIRONMENT=production
OPENCDE_PUBLIC_URL=https://<tjänstens https-adress>
OPENCDE_SECRET_KEY=<48 slumpmässiga tecken>
OPENCDE_GRAPH_DIALECT=neo4j
OPENCDE_GRAPH_URI=neo4j+s://xxxx.databases.neo4j.io
OPENCDE_GRAPH_USER=neo4j
OPENCDE_GRAPH_PASSWORD=<från Aura>
OPENCDE_DATA_DIR=/data
OPENCDE_TRUSTED_PROXIES=["0.0.0.0/0"]
```

- Montera en beständig volym på `/data`: uppladdade dokument och bilder ligger
  där. Utan volym försvinner de vid nästa driftsättning.
- `OPENCDE_TRUSTED_PROXIES` är bred eftersom plattformens
  lastbalanseraradresser inte är fasta; plattformen garanterar att bara dess
  proxy når containern.
- Containern lyssnar på 8000 och svarar på `/healthz` (liveness) och `/readyz`
  (readiness, kontrollerar databasen).
- Skapa den första administratören från plattformens skal:
  `opencde user create admin --admin`.

## Säkerhetskopior

Sidovagnen `backup` i `compose.prod.yaml` gäller inte här. Schemalägg
`opencde backup /data/backups` (ett cron-jobb eller en schemalagd uppgift på
plattformen) och kopiera mappen till objektlagring; Aura har dessutom egna
snapshots.

## Egen server med databasen någon annanstans

Om du kör resten av stacken själv, som på [en egen server](vps-caddy.md), och bara databasen
någon annanstans, ange var den finns i `.env` och lämna databascontainern utanför:

```
OPENCDE_STACK_GRAPH_URI=neo4j+s://xxxx.databases.neo4j.io
OPENCDE_GRAPH_USER=neo4j
OPENCDE_GRAPH_PASSWORD=<från Aura>
```

```bash
docker compose -f compose.yaml -f compose.prod.yaml -f compose.external-db.yaml up -d
```

API:et och säkerhetskopieringen använder då den databasen. För Memgraph, sätt också
`OPENCDE_GRAPH_DIALECT=memgraph`.
