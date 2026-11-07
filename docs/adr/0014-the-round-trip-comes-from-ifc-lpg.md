# ADR 0014: The round trip comes from IFC-LPG

Status: accepted (2026-11-07)

*Number 0013 is IFC-LPG's, on checking files against IDS, since the two repositories share one sequence.*

## Context

The STEP reader, the lossless form, the workers that convert and write files, the importer, the exporter, the
comparison of two files and the checks of an uploaded file (ADR 0009 to 0012) were written in Kontroll, under
`opencde/ifcgraph/`. On 2026-11-07 the owner decided to move them to his repository `marwiss/IFC-LPG`, renamed for the
purpose, as a library others can use, under Kontroll's licence, the GNU Affero General Public License, version 3 or
later, and to build the check against IDS there. IFC-LPG was released as 1.0.0 the same day, and is not on PyPI yet.

Kontroll's slim image, built with `--build-arg OPENCDE_EXTRAS=`, has no IfcOpenShell, and the server's own process uses
only what needs none: it imports and exports records, deletes the models of a project that is deleted, and reads the
packed reports. The workers are what need IfcOpenShell.

## Decision

**Kontroll requires IFC-LPG, and its extra requires IFC-LPG's.** The bare package `ifc-lpg` has no dependencies and is
what the server's process imports, so the slim image keeps working. The extra `ifc-lpg` requires
`ifc-lpg[ifcopenshell]`, which brings IfcOpenShell, IfcTester, defusedxml and the pytest that IfcOpenShell's EXPRESS
rules import, for the workers.

**From its repository, at a fixed commit, until it is on PyPI.** `[tool.uv.sources]` names the commit and `uv.lock`
records it. The image's build stage has git for that, and the runtime stage does not. Moving to PyPI changes the source
and nothing else.

**Kontroll keeps what is its own.** `opencde/ifcgraph/` keeps the service, which ties a model to a project and a
document version, queues the conversions and runs the workers, and the maintenance commands. The workers are IFC-LPG's,
run as `python -m ifc_lpg.<module>`, with Kontroll's limits from its settings.

**The tests of the round trip are IFC-LPG's.** Kontroll's tests cover how it uses the library: the extra and the image,
the server's process without IfcOpenShell, buildingSMART's rules without the server's settings, the service, and the
integration tests on Neo4j and Memgraph.

**pip-audit audits what it can.** It cannot audit a package that is not on PyPI, and lists `ifc-lpg` as skipped. The
packages IFC-LPG brings are Kontroll's dependencies and are audited as such. The requirements of buildingSMART's rules
come with IFC-LPG and are audited from where it is installed (`poe _audit_gherkin`).

## Consequences

- A change to the round trip is made in IFC-LPG, and reaches Kontroll when the commit in `[tool.uv.sources]` moves.
- Kontroll's ADRs 0009 to 0012 keep the paths of their time, with a note; IFC-LPG has copies of them.
- The settings, the command `opencde ifc-lpg` and the module's page stay Kontroll's, and so does what a client sees.
