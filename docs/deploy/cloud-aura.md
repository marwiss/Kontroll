# Managed database and container service (no server of your own)

Run the API on a container service (Fly.io, Render, Railway, Azure Container
Apps, Google Cloud Run) and the graph on a managed Neo4j (AuraDB) or Memgraph
Cloud instance.

## Database

- **Neo4j AuraDB Free** suits demos: about 200 000 nodes, paused after 72 hours
  without activity and deleted after 30 days of pause. AuraDB Professional for
  anything that must stay up.
- Create the instance, note the `neo4j+s://xxxx.databases.neo4j.io` URI, the
  user and the password.
- **Memgraph Cloud** works the same way with `bolt+s://` and
  `OPENCDE_GRAPH_DIALECT=memgraph`.

## API container

Deploy `ghcr.io/marwiss/opencdeserver:<version>` with these variables:

```
OPENCDE_ENVIRONMENT=production
OPENCDE_PUBLIC_URL=https://<the service's https URL>
OPENCDE_SECRET_KEY=<48 random characters>
OPENCDE_GRAPH_DIALECT=neo4j
OPENCDE_GRAPH_URI=neo4j+s://xxxx.databases.neo4j.io
OPENCDE_GRAPH_USER=neo4j
OPENCDE_GRAPH_PASSWORD=<from Aura>
OPENCDE_DATA_DIR=/data
OPENCDE_TRUSTED_PROXIES=["0.0.0.0/0"]
```

- Mount a persistent volume at `/data`: uploaded documents and images live
  there. Without a volume they vanish on redeploy.
- `OPENCDE_TRUSTED_PROXIES` is wide because the platform's load balancer
  addresses are not fixed; the platform guarantees that only its proxy reaches
  the container.
- The container listens on 8000, answers `/healthz` (liveness) and `/readyz`
  (readiness, checks the database).
- Create the first administrator from the platform's shell:
  `opencde user create admin --admin`.

## Backups

The `backup` sidecar of `compose.prod.yaml` does not apply here. Schedule
`opencde backup /data/backups` (a cron job or a scheduled task on the platform)
and copy the folder to object storage; Aura has its own snapshots as well.

## Your own server with a database elsewhere

If you run the rest of the stack yourself, as in [your own server](vps-caddy.md), and only the
database elsewhere, say where it is in `.env` and leave the database container out:

```
OPENCDE_STACK_GRAPH_URI=neo4j+s://xxxx.databases.neo4j.io
OPENCDE_GRAPH_USER=neo4j
OPENCDE_GRAPH_PASSWORD=<from Aura>
```

```bash
docker compose -f compose.yaml -f compose.prod.yaml -f compose.external-db.yaml up -d
```

The API and the backup sidecar then use that database. For Memgraph, also set
`OPENCDE_GRAPH_DIALECT=memgraph`.
