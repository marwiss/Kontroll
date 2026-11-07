# ADR 0009: What makes two IFC files the same model

Status: accepted (2026-11-07)

*The code this records moved to the library [IFC-LPG](https://github.com/marwiss/IFC-LPG) on 2026-11-07 (ADR 0014). The paths
below are those of the time: `opencde/ifcgraph/<module>.py` is `ifc_lpg/<module>.py` there.*

## Context

The owner wants a round trip: an IFC file becomes an IFC graph in the database, and the graph becomes a file again that
builds the same BIM model, with the same geographic information. Nothing can be said to work until something decides
what "the same" means, so that test comes first.

No standard defines it. ISO 10303-21 says instance names are unique within a file and that their order is free, and
buildingSMART has validators that judge one file, not comparisons of two. Research and tools use five levels, from
byte identity to generated geometry, and most compare by GlobalId, which reaches a small part of a file: in one sample,
3,893 of 38,898 instances. Run against deliberate changes, IfcDiff with every option on let a changed colour, material
name, `IfcMapConversion.Eastings` and a reversed polygon through, and IfcOpenShell's `==` let the same georeference
change through and ended the process on a cycle of references.

The published way of hashing an IFC graph from the leaves up (Shi et al. 2018, Liu et al. 2023) ignores ids, file order
and SET order, but it merges duplicates and takes the graph for acyclic. Forward hashes also cannot tell apart two equal
shapes with their styles swapped, because the style refers to the shape and not the other way around.

## Decision

**The same model** means there is a one-to-one pairing of the instances of the two files in which paired instances have
the same class and the same values, their references lead to paired instances, every LIST and ARRAY has its order, and
every SET and BAG has the same members. All instances count, not only those reached from an `IfcRoot`, since a map
conversion is reached from none. Duplicates count: a merged point is another model, because sharing decides what a
style or a later edit applies to.

**Identical** asks for the same ids, the same order in SETs and the same header too. It implies the same model. It is
what a store that keeps a file's ids can promise. The promise is worth making on top: native IFC tools merge by id, and
the geometry kernel can build another shape from another order in a SET (the volume of one wall in a sample went from
6.288 to 4.177). What this store promises is for the round trip's own tests to show.

**There is no tolerance.** A REAL is compared by its bits. A double survives text, JSON and Bolt exactly when written
with its shortest form, so a tolerance would only hide a defect, and the `Precision` of a context is a value of the
model, not a licence. `1.` and `1.0E0` are the same value. `-0.`, `0.` and the INTEGER `1` are not.

**The comparison reads the files itself** (`opencde/ifcgraph/step.py`). It uses IfcOpenShell only for what the schema
says about order and for building geometry. A comparison through IfcOpenShell could not see what IfcOpenShell loses on
reading, and running this one over 26 sample models showed what that is: `.NULLENUM.` becomes `$`, with a line in its
log, and `($,$)` becomes `()`, without one. Its notes also have raw bytes above 0x7F vanishing from strings, `.5` in a list of REALs being
read as nothing, and complex instances being left out. This reader refuses what it cannot read: six truncated files in
the samples were refused, where IfcOpenShell read what was there and said so only in its log.

**"The same" is only said of a pairing that was built and checked.** Classes of instances are refined by values and by
references in both directions, in one graph over both files. A class with more instances from one file than from the
other proves there is no pairing, and which instance that was goes in the report. Instances still alike after that are
paired by choice, and refinement goes on from there; a choice that leads nowhere is taken back, which is what tells a
ring of six from two rings of three. Then the pairing is checked from the start against the files alone, so a defect in
the refinement can cause a wrong "not the same", but not a wrong "the same". The search has a limit, and reaching it
means no answer, which counts as not the same. W3C's RDF Dataset Canonicalization stands before the same problem and
limits its work in the same way.

**Georeference and generated geometry are reports, not parts of the definition.** The same-model check covers every
value, so naming `IfcMapConversion.Eastings` adds no strictness, but it does say what moved, and it protects against
someone later narrowing the check to rooted instances. Geometry is the one check that sees the file the way a user
does, and it needs IfcOpenShell's kernel, so it is asked for by a flag. It compares raw vertices and faces per product:
a rounded mesh hash failed on values next to the rounding's edge in the samples, and `geometry.id` holds STEP ids. A
comparison that built nothing does not pass, because that is how IfcDiff came to report no changes on models it never
looked at. Since the order of a SET can change the mesh, this says something only of files that keep it.

Comparing validation results before and after was proposed in the research and left out: a validator judges one file,
and a file that holds the same model has the same issues.

## Consequences

The round trip has a test that can fail. That is shown, not assumed: `tests/unit/test_ifcgraph_equivalence.py` has every
row of the research's table of changes. A throwaway run that breaks the code on purpose in 57 places is now caught at
every one. The first such run let 18 through, which led to more tests and to one check removed as redundant.

IfcOpenShell cannot carry every file through unchanged. Two of the samples are such files, from Tekla and from Archicad,
and a round trip through it would fail this test on them however good the graph is. ADR 0010 says what follows from that.

A check takes seconds: 224,496 instances and 19 MB in about 10 s, single-threaded. Nothing larger has been run, and
memory grows with the number of instances, so a model of millions needs measuring first. The check is meant for tests
and for an operator's question, not for every request. On a model with instances that look alike the search costs more,
and how much on a hostile file is bounded only by `MAX_FAILED_PAIRINGS`, so it runs in a process of its own when the
input is not trusted (`python -m opencde.ifcgraph.equivalence`).

Sources: Shi et al., IFCdiff, 2018; Liu et al., A Parallel IFC Normalization Algorithm, 2023 (arXiv 2312.14931); Esser et
al., EG-ICE 2021; ISO 10303-21 edition 3 draft; W3C RDF Dataset Canonicalization (2024).
