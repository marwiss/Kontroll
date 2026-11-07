# ADR 0010: A lossless graph reads and writes STEP itself

Status: accepted (2026-11-07)

*The code this records moved to the library [IFC-LPG](https://github.com/marwiss/IFC-LPG) on 2026-11-07 (ADR 0014). The paths
below are those of the time: `opencde/ifcgraph/<module>.py` is `ifc_lpg/<module>.py` there.*

## Context

The owner wants a model written back from the graph as a file that builds the same model, and expects that geometry
cannot all be nodes. ADR 0009 says what "the same" means and gives the test. The graph as it was cannot do it. It leaves
geometry out, unwraps `IFCLABEL('3')` to `"3"`, and its relationships do not say where in a list they stood.

The research before this work advised reading with IfcOpenShell and writing through its API with `create_entity`,
keeping ids, and against writing STEP text by hand, since writers elsewhere get REALs and `*` wrong. Trying that gave
other evidence:

- **Reading changes values.** `.NULLENUM.` becomes `$` (2,834 instances in a Tekla sample) and `($,$)` becomes `()` (an
  Archicad sample, with nothing in the log). The BINARY `"15"` is read as `010` and written as `"12"`, although `"15"`
  is valid: the reader drops the unused bits from the wrong end. Raw bytes above 0x7F vanish from strings, `.5` in a
  list of REALs is read as nothing, and complex instances are left out. A round trip through that reader cannot pass
  the test on those files whatever the graph does.
- **The API cannot make every value.** `create_entity("IfcPropertySetDefinitionSet", (pset,))` ends the process with an
  access violation, and a plain tuple in that attribute is refused. The value is valid IFC4.
- **The risk the advice guards against is a writer that gets a value wrong and nobody sees.** The comparison in ADR 0009
  is there to see that. In the tests, IfcOpenShell's own written form of both files is compared as well, which shares
  nothing with this project's reader.

## Decision

A second form of conversion, the default from 3.0.0 by the owner's decision of 2026-11-07, reads the file with
`opencde/ifcgraph/step.py`, and a file is written back with the same module. IfcOpenShell gives the schema's tables and
nothing else, so its parser never sees the file on this path. The ordinary form stays as it was behind
`OPENCDE_IFCGRAPH_LOSSLESS=false`, which reads with IfcOpenShell and leaves out what is no node.

**The graph is what gets written.** Keeping each instance's text on its node would have been far simpler and exact by
construction. But the graph would then say two things, and a changed property would not reach the file, so it would not
be the graph's content that came back, which is what was asked for. A test changes a name and the order of a list in the
graph and finds them in the file.

**A value goes where a query looks for it** (`lossless.py`): a property named after the attribute, a list property, JSON
text for a list of lists, since Neo4j has no nested lists, a relationship with a `position` for a reference, and the
keyword of a typed value beside it in `<attribute>__type`. The nodes, relationships and values of the ordinary form are
all there, which a test checks, so queries written for one work on the other.

**Nothing is trusted to fit.** Each attribute is read back from that form as it is written, at conversion. What does not
come back the same goes in tagged JSON instead, and what the schema does not know goes whole in `ifc_args`. So the
values that need the fallback are found by trying, not from a list that could be incomplete: a string where the schema
has an enumeration, an INTEGER no database holds, half of a surrogate pair, NUL, raw bytes, a REAL beyond a double's
range, a reference to nothing.

**Geometry is kept in blocks.** What the ordinary form leaves out as nodes (`GEOMETRY_ROOTS`, and owner histories other
than the project's) is written out as STEP in order of id, and compressed into text on `StepBlock` nodes that hang off
the `IfcModel`: at most 256 KiB of STEP per block, deflated and in base64, since a string is the one thing both
databases store alike. This is the owner's idea of geometry as properties of another node, drawn by class and not by
product, because 17-94% of the geometry in the samples belongs to more than one product and some of it to none. What
refers to an instance in a block holds its id in `<attribute>__step`, as a plain number a query can read.
`OPENCDE_IFCGRAPH_INCLUDE_GEOMETRY=true` makes them nodes instead.

**The relationships are the one place that says what refers to what between nodes.** A reference in tagged JSON says
only "the relationship at this position". The inverse relationships are worked out from the schema's tables, and a test
finds them the same as IfcOpenShell's. The writer reads only what the schema says is an attribute, so inverse
relationships, `SAME_AS` and the copy of the GTIN stay behind. As in the ordinary form, an owner history is linked from
its project alone, or it would become the centre of the graph.

**A file is written one line at a time from the graph's pages,** in order of id, so the size of the file does not decide
the memory it takes. It runs in a process of its own with the memory limit, like the conversion. An export stops if the
blocks do not hold the number of instances the conversion put in them, because a file without them could not be told
from a right one.

## Consequences

Without a database, all 26 whole files in the samples came back identical, up to 224,496 instances and 19 MB, from
Revit, Archicad, Tekla, SketchUp, SierraSoft and IfcOpenShell. IfcOpenShell's own written form of original and copy was
equal on every one, and the generated meshes were equal bit for bit, up to 4,134 products in one model. Six truncated
files and one in a schema IfcOpenShell does not have (`IFC2X_FINAL`) were refused. In the tests, a file of the hardest
values and the sample model go through both databases, in both forms, and through a backup and a restore.

Five real models through a fresh database of each kind, in each form, all coming back identical (Neo4j with the default
512 MiB heap and 256 MiB page cache; its store after a clean stop, and Memgraph's own count of its memory):

| Model | File | Instances | Neo4j store, MB: ordinary / blocks / nodes | Memgraph RAM, MB: ordinary / blocks / nodes | Import on Neo4j, s: ordinary / blocks / nodes |
|---|---|---|---|---|---|
| SketchUp, tessellated | 5.6 MB | 23,528 | 2.3 / 3.9 / 19.6 | 13 / 17 / 48 | 3 / 3 / 12 |
| Archicad | 2.8 MB | 49,664 | 6.6 / 8.3 / 21.0 | 26 / 27 / 55 | 13 / 13 / 32 |
| Archicad | 6.0 MB | 110,176 | 11.3 / 14.6 / 42.8 | 37 / 39 / 95 | 20 / 15 / 53 |
| SierraSoft, road | 14.6 MB | 127,491 | 4.8 / 10.6 / 54.7 | 21 / 27 / 130 | 9 / 7 / 38 |
| Tekla | 19.2 MB | 224,496 | 55.8 / 108.9 / 137.2 | 144 / 149 / 264 | 58 / 32 / 94 |

So on these models blocks took up to about twice the store of the ordinary form on Neo4j and little more than it on
Memgraph, and nodes 2.5 to 11 times the ordinary form. Typed queries did not follow the size: the storey-to-element and
property-set queries took 7-25 and 11-90 ms in all three forms on Neo4j, with no pattern among them. That agrees with
Zhu et al. 2025, and it means the reason to keep geometry out of the nodes is what it costs to store and import, not what
it costs to ask. This is one run on one machine, with other work going on, on small models. Nothing larger has been run,
and a model of millions of instances needs measuring first.

What a block holds cannot be reached with Cypher, and a changed instance in one would need its block rewritten. Nothing
does that today, so what is in a block does not become wrong. A reference from a block into a node is not known to the
database, so a deleted node would leave a dangling reference in the file. A changed property or relationship of a node
reaches the file, and ADR 0011 is how a file is held to the standard after that.

We now keep a STEP reader and writer of about 370 lines where IfcOpenShell has a far better tested one. That is a cost,
and if the code goes upstream, the parser's faults may be better fixed there, at which point this path could go through
it again. A test says when the three changes it found stop happening.

Bonsai and FreeCAD work in IFC itself, so they show what a file holds without an import that translates it, unlike
Revit, Tekla and Archicad. Four pairs of original and written copy were opened in Bonsai 0.8.3 on IfcOpenShell 0.8.3,
and in FreeCAD 1.0.1 through NativeIFC on its own IfcOpenShell. Both gave the same objects, products and meshes for
original and copy, and what each would save of the two was the same, with one exception: FreeCAD's parser keeps how a
REAL is spelled, so one line of one file reads `1.0E-5` from the original and `1.E-05` from the copy, the same number.
Those are other versions of the parser than the one the tests run on, so they say the writer's text is read the same
there too. FreeCAD's older importer fails on any file with that IfcOpenShell, so it says nothing either way.

The ordinary form answers the same queries, so nothing written for it needs changing, but a query that reads all of a
node's properties sees more of them. A model converted by an earlier version keeps its form and cannot be written back
until it is uploaded again.
