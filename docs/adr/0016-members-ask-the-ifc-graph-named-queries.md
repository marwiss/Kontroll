# ADR 0016: Members ask the IFC graph named queries

Status: accepted (2026-11-08)

## Context

Reading a model is one of the operations the owner requires of the IFC graph in 3.0.0. It means questions and answers
through the API, such as the number of rooms, a building's area and a wall's material. He decided that members ask
named queries with parameters, and that free Cypher stays with administrators (3.0.0, decision 4). Administrators
already have read-only Cypher through the administration API's graph query, `OPENCDE_GRAPH_QUERY_ENABLED`, with the
fences that `admin/graph_query.py` describes. A member's question must not reach beyond the projects they belong to.
Every statement in Kontroll starts at the user and reaches data through `MEMBER_OF`, and these must too.

## Decision

**A catalogue of statements, asked by name.** `opencde/ifcgraph/queries.py` holds each query: its name, description,
parameters and columns, and a Cypher statement. The statement starts at the user and reaches the version's model through
`MEMBER_OF` and `HAS_MODEL`, and the newest finished model of the version if there are several. A client sends only the
name and the values of the parameters. There are seven to start with: `element-classes`, `elements`, `storeys`,
`spaces`, `areas`, `materials` and `property`.

**An extension of the Documents API on the version**, as the report of the checks is (ADR 0011).
`GET /documents/1.0/documents/{id}/versions/{index}/ifc-queries` lists the queries, and `GET …/ifc-queries/{name}` asks
one, with the Documents API's token. The official APIs stay as they are (decision 5), and the capabilities document
announces the queries in `ifc_queries`. An answer has the columns and the rows, each row a list in the order of the
columns, as the administrators' graph query answers.

**Parameters are values, checked first.** A class must be the name of an IFC class, `^Ifc[A-Za-z0-9]{1,64}$`, and is
compared with the labels of a node, so that it takes the subclasses with it. Any other text is 1 to 255 characters,
without control characters. An unknown or a missing parameter answers 400. A version without a model, or one the user
may not see, answers 404, and one whose model is still being converted answers 409.

**Read-only and bounded.** Each statement runs in a read transaction, through the same runner as the administrators'
graph query, with at most 10,000 rows and 10 seconds. A unit test passes every statement through the administrators'
check of reading statements, and checks that it starts at the user and uses only its own parameters.

**On the graph that IFC-LPG makes.** The statements follow the forward relationships, named after the attributes, which
both the lossless and the ordinary form of the graph have. The IFC-LPG session has agreed to say before that shape
changes. Quantities are looked for by name, `NetFloorArea` and `GrossFloorArea`, in any quantity set, since programs
name their sets differently.

## Consequences

- A client builds tables and charts from the answers without Cypher of its own, and without the database's port.
- A new question is a new entry in the catalogue with its tests, not a new route.
- The answers are as good as the model. A model without spaces or quantities answers with no rows or with null areas.
