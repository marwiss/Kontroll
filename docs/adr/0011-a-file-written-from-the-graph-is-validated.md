# ADR 0011: A file written from the graph is validated

Status: accepted (2026-11-07)

## Context

The file a model is written back as comes from what the graph holds, so a property or a relationship changed in the graph
reaches the file (ADR 0010). The owner's position is that the model then has to be verified against the IFC standard. A
graph database does not help: Neo4j and Memgraph hold no schema that could stop `SET n.GlobalId = 'x'`, and the standard is
written in EXPRESS, with rules that would be hard to hold in one anyway.

The comparison of ADR 0009 cannot answer this, since a changed model is meant to differ. Comparing validation results was
left out of that comparison because a file holding the same model has the same issues. That reasoning holds for a file
that has not changed, which is exactly the case where nothing can go wrong.

Validators there are: IfcOpenShell's own, buildingSMART's Validation Service, which has an upload limit of 256 MB and runs
elsewhere, and its rule set `ifc-gherkin-rules`, which checks implementer agreements on top of the schema with a test
runner of its own.

## Decision

**The file is validated, not the graph.** It is the file that goes out, the rules are about whole models, and instances
in blocks have no nodes to look at. `opencde ifcgraph export` runs `ifcopenshell.validate` on what it wrote, with EXPRESS
rules, in a process of its own with the limits of a conversion (`opencde/ifcgraph/validation.py`). IfcOpenShell compiles
those checks from the schema's EXPRESS: the type and number of attributes, enumerations, the cardinality of inverse
attributes, the form and uniqueness of GlobalIds, and WHERE rules and global rules. It is already a dependency and runs
without a network.

**What counts is what the upload does not have.** Files in use break rules already: 12 of the 26 samples have issues as
they were uploaded, up to 5,711 in one from Tekla. A demand for no issues at all would refuse much of what people have, for
nothing a change here did. So an issue that the uploaded file also has is counted and let through, and a new one is listed
and ends the command with an error. Two files with the same ids have comparable issues; what the parser quotes of the
file's own line stays out of the comparison, so layout and the spelling of a REAL are not new issues. Every one of the 26
written copies had no new issue against its original, so this raises no false alarm on them.

**A broken file is still written, and says so.** The command is for an operator, who needs to see the file to see what is
wrong, and nothing leaves the server by it. `--no-validate` leaves the check out.

**Blocks are covered from the outside.** What is in a block cannot be changed through the graph, as the owner points out,
so it does not become wrong. It can come to refer to what is gone: a deleted node leaves a reference to nothing in a block,
and the parser reports that. A test deletes nodes others refer to and finds the export stopped.

**pytest becomes a dependency of the `ifcgraph` extra.** `ifcopenshell.express.rule_executor` imports `_pytest` when the rules
run, for its rewriting of assertions, and IfcOpenShell does not declare it. In a clean environment with only IfcOpenShell,
the rules end in `ModuleNotFoundError`. The tests would never have shown that, since they run with the dev group, and the
image is built without it. It is pure Python and is called by nothing else. A test checks that the extra names it, and
`.github/workflows/ci.yml` runs the rules in an environment made from the extra alone, so that it is seen if this changes.

## Consequences

Validation adds time: 3 to 66 s for a file and its upload together on the samples, up to 224,496 instances and 19 MB. It
reads with IfcOpenShell's parser, so it does not see what that parser drops without a word (ADR 0010). An upload is not
validated when it comes in, only a file written from the graph.

It does not check everything the standard asks. The implementer agreements in `ifc-gherkin-rules` and the geometry itself
are outside it, so a wall can pass with a meaningless shape. Those can be added behind the same comparison with the upload
if a need shows. The server does not offer editing today, so these changes come from someone with access to the database,
and export is where they are caught.

Project members get files through the Documents API, and this adds no route. A written file that is to replace a model is
uploaded as a new version of its document, and is then converted like any other.
