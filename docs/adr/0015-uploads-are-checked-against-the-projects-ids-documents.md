# ADR 0015: Uploads are checked against the project's IDS documents

Status: accepted (2026-11-07)

## Context

The owner decided that the server checks uploaded IFC files against IDS as well (3.0.0, decision 6), in the first step
of 3.0.0, with the IFC schema (ADR 0011) and buildingSMART's rules (ADR 0012). IFC-LPG has the check, as its ADR 0013
records. IfcTester checks with its own defaults, as Dataspatium runs it. An IDS is read with defusedxml, against a schema
built without the network. Every failure is an error, and each specification gets a summary.

What Kontroll has to decide is which IDS apply to an upload, when they are applied, and how the result reaches a client.
An IDS is an XML file, and the Documents API takes any file. A project's files are kept there, with their versions and
who uploaded them, and Kontroll has no other place for a project's requirements.

## Decision

**The IDS documents of the version's project apply.** A document of the project is an IDS document when the name of its
latest version ends in `.ids`, and its latest version is the one that applies. At most 50 are used, in the order of their
document ids. A member who may upload documents can thus add, replace and retire the requirements of a project, and the
report says which versions were used.

**At upload, with the other checks.** The IDS check runs after the schema check and the rules, in the same job and with
the same limits, in IFC-LPG's worker (`python -m ifc_lpg.ids`). The worker gets the files by the storage paths the server
made. An IDS added later applies to the IFC versions uploaded after it. Checking earlier versions again is left for
later.

**In the same report.** Each finding is an issue of the kind `ids`, an error, with the document it came from in
`document_id`. The check `ids` lists the documents with the version used, the documents that could not be read under
`rules_not_run`, and every specification with its verdict. The status follows the count of errors as before, so a failed
specification makes the version's status `issues`. The version's page shows the specifications in a table of their own.
If the check cannot run at all, its state is `failed`, and the other checks stand.

**No setting of its own.** A project without IDS documents is checked against none, and
`OPENCDE_IFC_LPG_VALIDATE_UPLOADS=false` turns all the checks off together.

## Consequences

- The report gains `document_id` on issues and on `rules_not_run`, and `documents` and `specifications` on checks. They
  are null or empty for the schema and the rules.
- A project's members see the findings of every IDS in it, as they see the documents themselves.
- Dataspatium can show the specifications as it shows its own IDS check, with the same words.
- Checking again when an IDS changes, and checking the graph itself as it is edited, belong to later steps of 3.0.0.
