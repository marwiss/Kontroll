# ADR 0003: Dialect-neutral Cypher so Memgraph is a drop-in alternative

Status: accepted (2026-11-05)

## Context

The project must be able to switch from Neo4j to Memgraph later without a
rewrite. Both speak Bolt and work with the `neo4j` Python driver, but they
differ in schema DDL, some functions, temporal and spatial type handling, and
transaction features (checked against Memgraph's documentation 2026-11-05).

## Decision

Application Cypher is restricted to the common subset:

- Keys are our own UUID properties with unique constraints. Never
  `elementId()` or `id()`.
- Dates and times are stored as ISO-8601 strings in UTC (sortable, identical
  on both products). Coordinates and vectors are plain floats, never `point()`.
- No APOC, no `CALL {} IN TRANSACTIONS` (batching happens in Python with
  `UNWIND`), no `shortestPath`, and none of: `time()`, `exists(n.prop)`,
  `isEmpty()`, `percentileCont()`, `percentileDisc()`, `stDev()`, `stDevP()`,
  `isNaN()`, `normalize()`, `size((n)-->())`, octal literals, multi-value
  `CASE WHEN a, b`.
- Lists and maps are replaced as a whole, never edited in place.
- Constraints use the form both accept: `CREATE CONSTRAINT FOR (n:Label)
  REQUIRE n.prop IS UNIQUE`. Dropping constraints and creating indexes go
  through the dialect object, outside multi-statement transactions.
- The database name is configurable (`neo4j` vs `memgraph` by default).

A lint test scans all Cypher for the forbidden constructs, and the
integration suite runs against both databases with testcontainers.

## Consequences

- Slightly more verbose Cypher in places (string dates, no spatial type).
- Memgraph Community lacks RBAC, multi-tenancy and TTL; the server does not
  need them (authorization in the application, one database, own expiry).
- Both products' Bolt mapping of temporal values is avoided entirely, so the
  undocumented parts of Memgraph's driver support are never exercised.
