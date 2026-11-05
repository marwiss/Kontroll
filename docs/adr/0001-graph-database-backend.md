# ADR 0001: Graph database as the only backend

Status: accepted (2026-11-05)

## Context

The 2023 prototype stored BCF data, OAuth2 state and an IFC-graph (an IFC
model converted to a labelled property graph) in Neo4j, and the report behind
it showed that joining BCF components to IFC entities by GlobalId in one graph
is what makes the server useful for inspection plans (GTIN lookup through
`SAME_AS` relationships). A graph database is a hard requirement for the
rewrite.

## Decision

All persistent state except binary files lives in one graph database reached
over Bolt with the official `neo4j` Python driver: users, OAuth2 clients and
tokens, projects, topics, comments, viewpoints, documents and versions,
sessions, events, audit log and the optional IFC-graph. Binary content
(documents, snapshots, bitmaps) lives in a storage backend addressed by
server-generated ids.

Neo4j 5.26 LTS Community is the default. Memgraph must remain a drop-in
alternative (ADR 0003). No APOC or other plugins: expiry is a property plus a
server-side cleanup job.

## Consequences

- One query language for everything, and relationships (user → project →
  topic → viewpoint → component → IfcProduct) are first-class.
- No ORM; repositories hold Cypher with parameters, which keeps the queries
  readable in the code and in the docs.
- Features that exist only in one product (APOC TTL, Neo4j enterprise RBAC,
  Memgraph TTL) are not used.
