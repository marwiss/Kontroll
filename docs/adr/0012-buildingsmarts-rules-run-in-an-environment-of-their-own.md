# ADR 0012: buildingSMART's rules run in an environment of their own

Status: accepted (2026-11-07)

*The code this records moved to the library [IFC-LPG](https://github.com/marwiss/IFC-LPG) on 2026-11-07 (ADR 0014). The paths
below are those of the time: `opencde/ifcgraph/<module>.py` is `ifc_lpg/<module>.py` there.*

## Context

ADR 0011 checks every uploaded IFC file against the IFC schema with IfcOpenShell, and left open whether to run
buildingSMART's `ifc-gherkin-rules` as well. Those rules are what buildingSMART's validation service checks beyond the
schema: about a hundred features, normative rules and industry practice, written in Gherkin with steps in Python and run
by behave.

The owner doubted what they bring with them, since the rule set's requirements name Django, SQLAlchemy and pandas, and
Kontroll has a graph database and FastAPI. The source says otherwise. Django is used only to write results into the
validation service's database, in `validation_results.py` and `features/environment.py`. SQLAlchemy is imported nowhere,
and pandas only by two helper scripts. The steps themselves need behave 1.2.6, IfcOpenShell and a handful of packages for
geometry and parsing: numpy, shapely, pyproj, rtree, networkx, lark and a few more.

The IfcOpenShell version matters. The rule set's CI uses IfcOpenShell 0.8.6, build 8b5b400; Kontroll uses 0.9. A runner
without Django was tried on the rule set's own test files. With 0.9.0.post1 it gave the expected verdict for 673 of the
722 files whose rules are enabled, and 101 files belong to disabled rules. The 49 deviations come from one helper:
`PackedSequence` in `features/steps/utils/misc.py` does `file[None]`, which gives `None` in 0.8 and raises `TypeError` in
0.9. With 0.8.6 the same runner gave the expected verdict for all 722.

## Decision

**The rules run as their own tests run them.** Kontroll calls behave with the flags of the rule set's own `main.run` in
testing mode: every rule not tagged `disabled`, `execution_mode=ExecutionMode.TESTING`, no limit on outcomes per rule,
and the formatter that embeds the outcomes in behave's JSON report. The 722 verdicts were checked that way.

**In an environment of their own, with IfcOpenShell 0.8.6.** Kontroll keeps 0.9 for everything else. Patching the helper
would change upstream's rules, and support for 0.9 upstream does not help now. `python -m opencde.ifcgraph.gherkin_install
<folder>` makes the environment from pinned downloads, each checked against a SHA-256 written in the installer:

- the rule set at a fixed commit, of which only `features/`, the JSON formatter, `behave.ini` and the licence are kept;
- `dataclass_compat.py` and the licence of buildingSMART's data model, which hold the result codes without Django;
- IfcOpenShell's own build of 0.8.6 for the platform, for Linux on x86_64 and aarch64 and for Windows on AMD64, unpacked
  into the environment as the rule set's CI does;
- the packages of `gherkin-requirements.txt`, installed with `--require-hashes`.

An archive member that would land outside its folder is refused, and links are never written. The installer uses only
the standard library and uv or pip, so that the Docker build can run it. `OPENCDE_IFCGRAPH_GHERKIN_ENV` names the
environment.

**The published image leaves the rules out by default.** The environment adds about 425 MB, so the owner decided that
the default image goes without it and that the rules are a choice. A release publishes a second image with them, tagged
`-gherkin` (`3.0.0-gherkin`, `latest-gherkin`), scanned like the first before either is published. A production
deployment pulls its image, so it chooses with `OPENCDE_IMAGE_TAG`; an image built locally chooses with
`--build-arg OPENCDE_GHERKIN=1`, which docker compose passes on from `OPENCDE_GHERKIN`. Such an image has the
environment in `/opt/gherkin`, owned by root, so that the server can run the rules but not change them.

**Two files of Kontroll's own take the place of the Django parts.** `gherkin_shim/validation_results.py.in` hands on the
result codes from `dataclass_compat.py`. `gherkin_shim/environment.py.in` keeps the hooks of the testing mode and embeds the
outcomes in the report, without the database. It is derived from the rule set's `features/environment.py` and carries
that file's MIT licence.

**A finding is an issue; an exception is not.** Every outcome with the severity error or warning becomes an issue of the
kind `gherkin`, with the code of its rule and the STEP id of its instance. The GlobalId is read from the file with
Kontroll's own STEP reader (ADR 0010). A rule that raised an exception has no verdict, so it is listed under
`rules_not_run` of its check, apart from the findings. The rules run after the schema check, in the same kind of worker
with the same limits, and one report holds both, with a `checks` list that tells them apart. If the rules cannot run at
all, their check is `failed` and the schema's check stands alone.

**Warnings are not errors.** Rules of industry practice only warn, and buildingSMART's validation service holds a file
valid when all it finds are warnings. Such a file gets the status `warnings`, and `issues` means that at least one finding
is an error. The report and the node carry `error_count` beside `issue_count`. The schema check reports only errors, so an
upload checked before this keeps the status it had.

**The rules see nothing of the server.** behave runs with an environment that holds only `PATH`, the temporary folder,
`HOME` and the locale, so none of the server's settings or secrets reach it.

## Consequences

The rules take time on top of the schema check. On eight sample models they took from 5 s for the smallest to 322 s for
the largest, and most took 27 to 117 s. Uploads are checked one at a time, as conversions are.

An image with the environment is 1.10 GB against 675 MB without it: IfcOpenShell 0.8.6 and its own copies of numpy,
shapely, pyproj and rtree. In that image the rules took 3 s on the small test model. A release builds and scans one more
image, and has twice as many image tags to keep or remove.

Some rules do not always run at the pinned commit. GEM004 has no table for IFC2X3 and raises `FileNotFoundError`, and
GRP001 raises `KeyError` on subtypes of `IfcGroup`. PSE001 raised `JSONDecodeError` on some sample files, which was not
investigated. These show under `rules_not_run`. Reporting them upstream is the owner's step.

A new commit of the rule set, or a new IfcOpenShell build for it, means new pins in the installer and a new run against
the rule set's test files.

Two later decisions change what ADR 0011 left to clients. A check against an IDS will run on the server too. Clash
detection runs both on the server with IfcClash and in Dataspatium with a core of its own.
