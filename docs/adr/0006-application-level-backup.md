# ADR 0006: Application-level backup instead of database dumps

Status: accepted (2026-11-05)

## Context

The server must be easy to back up and restore, on Neo4j and on Memgraph.
`neo4j-admin database dump` needs the database stopped (Community Edition) and
produces a Neo4j-only file; Memgraph has snapshots and WAL in its own format;
neither covers the files in the storage directory. Operators would need two
procedures and could not move between databases.

## Decision

`opencde backup` exports every node and relationship through Cypher into
compressed JSON lines, identifying nodes by the unique keys the schema defines
(never by `elementId()`/`id()`), and archives the storage directory. A manifest
carries checksums and counts. `opencde restore` recreates the graph in batches
with `UNWIND … CREATE` and unpacks the files. `compose.prod.yaml` runs the
export nightly.

## Consequences

- One procedure for both databases; a backup moves between them.
- The database stays online; the export is consistent per label batch, not a
  point-in-time snapshot. Uploads in progress may be incomplete in the backup
  and are simply redone by clients.
- Nodes without a unique key (none in the current schema) would be skipped;
  the manifest reports them.
- Large graphs export slower than a native dump; for the data volumes of a CDE
  (thousands of topics, gigabytes of files) this is minutes, not hours.
