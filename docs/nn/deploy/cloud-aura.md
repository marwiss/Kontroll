# Administrert database og containerteneste (utan eigen server)

Køyr API-et på ei containerteneste (Fly.io, Render, Railway, Azure Container
Apps, Google Cloud Run) og grafen på ein administrert Neo4j (AuraDB) eller ein
Memgraph Cloud-instans.

## Database

- **Neo4j AuraDB Free** passar for demonstrasjonar: om lag 200 000 nodar, blir
  sett på pause etter 72 timar utan aktivitet og sletta etter 30 dagars pause.
  AuraDB Professional for alt som må haldast oppe.
- Opprett instansen og noter URI-en `neo4j+s://xxxx.databases.neo4j.io`,
  brukaren og passordet.
- **Memgraph Cloud** fungerer på same måte med `bolt+s://` og
  `OPENCDE_GRAPH_DIALECT=memgraph`.

## API-container

Distribuer `ghcr.io/marwiss/opencdeserver:<version>` med desse variablane:

```
OPENCDE_ENVIRONMENT=production
OPENCDE_PUBLIC_URL=https://<https-adressa til tenesta>
OPENCDE_SECRET_KEY=<48 tilfeldige teikn>
OPENCDE_GRAPH_DIALECT=neo4j
OPENCDE_GRAPH_URI=neo4j+s://xxxx.databases.neo4j.io
OPENCDE_GRAPH_USER=neo4j
OPENCDE_GRAPH_PASSWORD=<frå Aura>
OPENCDE_DATA_DIR=/data
OPENCDE_TRUSTED_PROXIES=["0.0.0.0/0"]
```

- Monter eit varig volum på `/data`: opplasta dokument og bilete ligg der.
  Utan eit volum forsvinn dei ved neste distribusjon.
- `OPENCDE_TRUSTED_PROXIES` er brei fordi lastbalanseraradressene til
  plattforma ikkje er faste; plattforma garanterer at berre proxyen hennar når
  containeren.
- Containeren lyttar på 8000 og svarar på `/healthz` (liveness) og `/readyz`
  (readiness, sjekkar databasen).
- Opprett den første administratoren frå skalet til plattforma:
  `opencde user create admin --admin`.

## Tryggingskopiar

Sidevogna `backup` i `docker/compose.prod.yaml` gjeld ikkje her. Planlegg
`opencde backup /data/backups` (ein cron-jobb eller ei planlagd oppgåve på
plattforma) og kopier mappa til objektlagring; Aura har òg sine eigne
snapshots.

## Eigen server med databasen ein annan stad

Om du sjølv køyrer resten av stakken, som på [ein eigen server](vps-caddy.md), og berre databasen
ein annan stad, oppgje kvar han er i `.env`, og la databasecontaineren stå utanfor:

```
OPENCDE_STACK_GRAPH_URI=neo4j+s://xxxx.databases.neo4j.io
OPENCDE_GRAPH_USER=neo4j
OPENCDE_GRAPH_PASSWORD=<frå Aura>
```

```bash
# .env: COMPOSE_FILE=docker/compose.yaml:docker/compose.prod.yaml:docker/compose.external-db.yaml
docker compose up -d
```

API-et og tryggingskopieringa brukar då den databasen. For Memgraph, set òg
`OPENCDE_GRAPH_DIALECT=memgraph`.
