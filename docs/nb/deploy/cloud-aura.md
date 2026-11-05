# Administrert database og containertjeneste (uten egen server)

Kjør API-et på en containertjeneste (Fly.io, Render, Railway, Azure Container
Apps, Google Cloud Run) og grafen på en administrert Neo4j (AuraDB) eller en
Memgraph Cloud-instans.

## Database

- **Neo4j AuraDB Free** passer for demonstrasjoner: omtrent 200 000 noder,
  settes på pause etter 72 timer uten aktivitet og slettes etter 30 dagers
  pause. AuraDB Professional for alt som må holdes oppe.
- Opprett instansen og noter URI-en `neo4j+s://xxxx.databases.neo4j.io`,
  brukeren og passordet.
- **Memgraph Cloud** fungerer på samme måte med `bolt+s://` og
  `OPENCDE_GRAPH_DIALECT=memgraph`.

## API-container

Distribuer `ghcr.io/marwiss/opencdeserver:<version>` med disse variablene:

```
OPENCDE_ENVIRONMENT=production
OPENCDE_PUBLIC_URL=https://<tjenestens https-adresse>
OPENCDE_SECRET_KEY=<48 tilfeldige tegn>
OPENCDE_GRAPH_DIALECT=neo4j
OPENCDE_GRAPH_URI=neo4j+s://xxxx.databases.neo4j.io
OPENCDE_GRAPH_USER=neo4j
OPENCDE_GRAPH_PASSWORD=<fra Aura>
OPENCDE_DATA_DIR=/data
OPENCDE_TRUSTED_PROXIES=["0.0.0.0/0"]
```

- Monter et vedvarende volum på `/data`: opplastede dokumenter og bilder ligger
  der. Uten et volum forsvinner de ved neste distribusjon.
- `OPENCDE_TRUSTED_PROXIES` er bred fordi plattformens lastbalansereradresser
  ikke er faste; plattformen garanterer at bare dens proxy når containeren.
- Containeren lytter på 8000 og svarer på `/healthz` (liveness) og `/readyz`
  (readiness, sjekker databasen).
- Opprett den første administratoren fra plattformens skall:
  `opencde user create admin --admin`.

## Sikkerhetskopier

Sidevognen `backup` i `compose.prod.yaml` gjelder ikke her. Planlegg
`opencde backup /data/backups` (en cron-jobb eller en planlagt oppgave på
plattformen) og kopier mappen til objektlagring; Aura har også sine egne
snapshots.
