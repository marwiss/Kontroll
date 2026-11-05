# Pinned specification files

Unmodified copies of the buildingSMART OpenCDE specification artefacts the
conformance tests validate against. They are © buildingSMART International
Ltd. and redistributed here for testing; the BCF-API repository licenses its
content under CC BY-ND 4.0 (see `bcf-api/LICENSE`). Behaviour follows these
exact revisions. Re-pin deliberately, in its own commit, when a newer release
is adopted.

| API | Repository | Revision | Files copied |
|---|---|---|---|
| BCF API 3.0 | https://github.com/buildingSMART/BCF-API | branch `release_3_0` at commit `701e5ceb3548b2feec73f4ec56f5a1d6112bd16f` | `Schemas/**/*.json` (52 files, JSON Schema draft-03), `LICENSE` |
| Foundation API 1.0 | https://github.com/buildingSMART/foundation-API | tag `v1.0` at commit `d8577940560a4ee8428ca0b073cd0572fb2bc0e3` | `schemas/*.json` (6 files) |
| Documents API 1.0 | https://github.com/buildingSMART/documents-API | branch `main` at commit `938bd7636e094c2dc3c65ad6dae846ac3c7b6a9b` (release `v1.0`) | `swagger.yaml` (OpenAPI 3.0.0) |

The prose specifications (README files) are not copied; read them at the
repositories above at the same revisions.

Known quirk: `foundation-api/schemas/versions_GET.json` restricts `api_id` to
`bcf` and `foundation`, while the Documents API expects `documents` in the
same list. The conformance tests allow `documents`.
