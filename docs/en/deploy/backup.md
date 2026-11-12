# Backup and restore

`opencde backup DIR` writes a folder `DIR/opencde-backup-<UTC time>/` with

| File | Content |
|---|---|
| `nodes.jsonl.gz` | every node: labels and properties, one JSON object per line |
| `relationships.jsonl.gz` | every relationship, with start and end node named by their unique keys |
| `storage.tar.gz` | the storage directory: documents, snapshots, bitmaps, snippets |
| `manifest.json` | format, time, server version, dialect, counts, SHA-256 of each file |

Nodes are identified by the unique keys of the schema (`id`, `guid`,
`project_id`, …), never by database-internal ids, so a backup taken from Neo4j
restores into Memgraph and vice versa (ADR 0006). The database keeps running
during the backup; a backup taken while uploads are in progress may miss the
parts of those uploads, which the clients simply redo.

With the server's own data in a graph of its own (`OPENCDE_STORE_GRAPH_URI`,
[ifc-db.md](../ifc-db.md)), one backup holds both graphs in the same files,
IFC-DB's nodes from the IFC graph and the rest from the store, and
`manifest.json` names the store's dialect in `store_dialect`. A restore puts
each node where its label belongs, whichever graphs the backup came from, so a
backup of one database restores into two and the other way round; it refuses
unless both are empty or `--force` is given, and leaves out a relationship
between the two kinds, which only a database from before ADR 0027 can hold.

## Restore

```sh
opencde restore DIR/opencde-backup-20261105T031700Z           # into an empty database
opencde restore DIR/opencde-backup-20261105T031700Z --force   # replace the current contents
```

`restore` verifies the checksums, refuses a non-empty database unless `--force`,
recreates nodes and relationships in batches and unpacks the files into the
storage directory. Sessions and tokens are restored too; run
`opencde revoke --all` afterwards if the backup is old or came from another
server.

## In Docker Compose

`docker/compose.prod.yaml` runs a `backup` service that calls `opencde backup /backups`
once a day and keeps the newest 14 folders in the `backups` volume. Copy that
volume somewhere else (another host, object storage); a backup on the same disk
as the data is only half a backup:

```sh
docker run --rm -v dataregium_backups:/backups -v "$PWD":/out alpine \
  tar czf /out/dataregium-backups.tgz -C /backups .
```

An installation that kept the old project name has the volume as `kontroll_backups`.

To restore on a fresh host, start the stack, copy a backup folder into the
`api` container (or mount it) and run
`docker compose exec api opencde restore /path --force`.

## Test your restore

A backup you have never restored is a hope, not a backup. The integration test
`tests/integration/test_backup.py` restores a backup into an empty database on
both Neo4j and Memgraph; do the same once on a staging instance after setting up
production.
