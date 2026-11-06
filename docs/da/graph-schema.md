# Grafskema

Databasen er skemaløs; `opencde/graph/schema.py` er skemaet. Denne side
forklarer konventionerne og labels, afsnit for afsnit i den rækkefølge,
planens etaper tilføjede dem.

## Konventioner

- Hver node har et servergenereret UUID i `id` (eller specifikationens navn
  for det: `project_id`, `guid`, `client_id`, `document_id`) med en unik
  constraint. Intet, en klient sender, ender ukontrolleret i en filsti eller
  en databasenøgle.
- Tidsstempler er ISO 8601-strenge i UTC med millisekunder og et `Z`
  (`2026-11-05T12:34:56.789Z`). Strengorden er lig med tidsorden.
- Koordinater og vektorer er almindelige flydende tal (`x`, `y`, `z`), aldrig
  `point()`.
- Alt, der udløber, bærer `expires_at` (samme format); serveren sletter
  udløbne noder på en timer (`opencde/graph/cleanup.py`).
- Hemmeligheder (koder, tokens, klienthemmeligheder) gemmes kun som
  SHA-256-hashes.
- Cypher er dialektneutral, så Neo4j og Memgraph opfører sig ens (ADR 0003).
  Skema-DDL er den eneste produktspecifikke tekst og ligger i `graph/dialect.py`.
- Navne: labels skrives i PascalCase (`DocumentVersion`, `IfcModel`),
  relationstyper med store bogstaver og understregninger (`HAS_TOPIC`,
  `CREATED_BY`, og `IS_DEFINED_BY` for IFC-attributrelationerne). Diagrammerne
  nedenfor tegner kun rigtige noder og relationer; en reference, der holdes
  som egenskab (`AuditEvent.actor_user_id`, `UploadSession.user_id`), listes
  i boksen i stedet for at tegnes som en linje.

## Konti og adgang (etape 1)

```mermaid
erDiagram
    User }o--o{ Project : MEMBER_OF
    Project ||--|| Extensions : HAS_EXTENSIONS
    Reviewer ||--o{ Project : ISSUES
    Project ||--o{ Building : CONCERNS
    AuditEvent {
        string actor_user_id
        string client_id
    }
```

| Label | Nøgle | Egenskaber | Noter |
|---|---|---|---|
| `User` | `id`, unikt `username` | `email`, `full_name`, `password_hash` (Argon2id), `is_admin`, `disabled`, `created_at`, `must_change_password` | Brugernavnet er det bruger-id, API'erne eksponerer |
| `MEMBER_OF` (relation User → Project) | | `role` (viewer, contributor, editor, manager), `since` | Rollerne afbildes på BCF's `*_actions`, se `accounts/roles.py` |
| `Project` | `project_id` | `name`, `created_at`, `topic_counter` | `topic_counter` nummererer `server_assigned_id` |
| `Extensions` | `id` | `topic_type[]`, `topic_status[]`, `topic_label[]`, `snippet_type[]`, `priority[]`, `stage[]`, `custom_information[]` | `users[]` beregnes ud fra medlemmerne |
| `Client` | `client_id` | `name`, `description`, `url`, `redirect_uris[]`, `is_public`, `secret_hash`, `disabled`, `pending_approval`, `created_at`, `created_by`, `dynamic`, `expires_at` (kun selvregistrerede) | OAuth2-klient; en selvregistreret slettes, når `expires_at` er passeret, uden at en token er udstedt |
| `AuditEvent` | `id` | `type`, `at`, `actor_user_id`, `client_id`, `ip`, `details` (JSON-streng) | Sikkerhedsrelevante hændelser |
| `Reviewer`, `Building` | `id` | `name`, `status` | Kontekst fra kontrolplan-anvendelsen (seed-data): den gennemgående organisation (en kommune i den oprindelige historie) og bygningen |

## OAuth2 (etape 2)

```mermaid
erDiagram
    AuthorizationCode }o--|| User : FOR
    AuthorizationCode }o--|| Client : ISSUED_TO
    AccessToken }o--|| User : FOR
    AccessToken }o--|| Client : ISSUED_TO
    RefreshToken }o--|| User : FOR
    RefreshToken }o--|| Client : ISSUED_TO
```

`AuthorizationCode`, `AccessToken` og `RefreshToken` (med `family_id`) nøgles
på en hash af hemmeligheden, bærer `expires_at` og er knyttet
`-[:FOR]->(:User)` og `-[:ISSUED_TO]->(:Client)`. `WebSession` (browserlogin,
etape 5) er kun knyttet `-[:FOR]->(:User)`.

## BCF-sager og hændelser (etape 3)

```mermaid
erDiagram
    Project ||--o{ Topic : HAS_TOPIC
    Topic }o--|| User : CREATED_BY
    Project ||--o{ Event : HAS_EVENT
```

| Label | Nøgle | Egenskaber | Noter |
|---|---|---|---|
| `Topic` | `guid` | `server_assigned_id`, `title`, `topic_type`, `topic_status`, `priority`, `stage`, `labels[]`, `reference_links[]`, `assigned_to`, `description`, `index`, `due_date`, `creation_date`, `creation_author`, `modified_date`, `modified_author`, `snippet_type`, `snippet_is_external`, `snippet_reference`, `snippet_reference_schema` | Feltnavnene følger `topic_GET.json`; BIM snippet-objektet flades ud til fire egenskaber. `server_assigned_id` er `<præfiks><tæller>` fra `Project.topic_counter` |
| `Event` | `id` | `kind` (`topic` eller `comment`), `topic_guid`, `comment_guid`, `author`, `date`, `action_types[]`, `action_values[]` | Én node per forespørgsel, der ændrede noget; de to parallelle lister er `actions`-arrayet i BCF 3.9/3.10. Knyttet til projektet, så hændelser overlever deres sag |

Hver sagsforespørgsel starter i kalderens `User`-node og går via `MEMBER_OF`
til projektet, før den rører en sag, så en sag i et projekt, kalderen ikke er
medlem af, findes ikke, så vidt API'et angår (404).

## BCF-kommentarer, viewpoints og referencer (etape 4)

```mermaid
erDiagram
    Topic ||--o{ Comment : HAS_COMMENT
    Topic ||--o{ Viewpoint : HAS_VIEWPOINT
    Viewpoint ||--o{ Component : HAS_COMPONENT
    Viewpoint ||--o{ Bitmap : HAS_BITMAP
    Topic ||--o{ FileRef : HAS_FILE
    Topic ||--o{ DocumentReference : HAS_DOCUMENT_REFERENCE
    Topic }o--o{ Topic : RELATED_TO
    Project ||--o{ BcfDocument : HAS_DOCUMENT
    Comment }o--|| User : CREATED_BY
    Viewpoint }o--|| User : CREATED_BY
    BcfDocument }o--|| User : UPLOADED_BY
```

| Label | Nøgle | Egenskaber | Noter |
|---|---|---|---|
| `Comment` | `guid` | `topic_guid`, `date`, `author`, `comment`, `viewpoint_guid`, `modified_date`, `modified_author` | `viewpoint_guid` skal nævne et viewpoint i samme sag |
| `Viewpoint` | `guid` | `index`, `author`, `creation_date`, `camera_kind`, `camera` (JSON), `lines` (JSON), `clipping_planes` (JSON), `snapshot_type`, `storage_key`, `has_components`, `default_visibility`, `has_hints`, `spaces_visible`, `space_boundaries_visible`, `openings_visible` | Uforanderligt. Geometri er JSON-tekst: opak og identisk i begge databaser |
| `Component` | `id` | `role` (`selection`, `coloring`, `exception`), `group_index`, `position`, `color`, `ifc_guid`, `originating_system`, `authoring_tool_id` | Én node per forekomst; IFC-grafen knytter `ifc_guid` til modelelementer (etape 9) |
| `Bitmap` | `guid` | `position`, `bitmap_type`, `storage_key`, `height`, `loc_*`, `nrm_*`, `up_*` | Billedbytes i lageret under `bitmaps/<guid>.<type>` |
| `FileRef` | `id` | `position`, `ifc_project`, `ifc_spatial_structure_element`, `filename`, `date`, `reference` | Filerne i sagens hoved (BCF 3.3) |
| `DocumentReference` | `guid` | `document_guid` eller `url`, `description`, `created_at` | Præcis ét af de to mål |
| `BcfDocument` | `guid` | `filename`, `storage_key`, `size`, `created_at`, `author` | En fil uploadet gennem BCF 3.8; bytes under `bcf-documents/<guid>` |
| `RELATED_TO` (relation Topic → Topic) | | | Rettet; PUT erstatter en sags udgående liste |

Sager holder deres snippet-fil i `snippet_storage_key` (bytes under
`snippets/<sags-guid>.bin`). Sletning af en sag sletter alt under den og de
lagernøgler, der er samlet fra noderne; hændelserne bliver.

## Dokumenter og browsersessioner (etape 5)

```mermaid
erDiagram
    Project ||--o{ Document : HAS_DOCUMENT
    Document ||--|{ DocumentVersion : HAS_VERSION
    DocumentVersion }o--|| User : UPLOADED_BY
    UploadSession ||--o{ UploadPart : HAS_PART
    WebSession }o--|| User : FOR
    UploadSession {
        string user_id
    }
    SelectionSession {
        string user_id
    }
```

| Label | Nøgle | Egenskaber | Noter |
|---|---|---|---|
| `Document` | `document_id` | `title`, `created_at`, `latest_index` | `latest_index` nummererer versionerne |
| `DocumentVersion` | `id` | `version_index`, `version_number`, `creation_date`, `title`, `file_name`, `size_in_bytes`, `sha256`, `storage_key`, `author`, `metadata` (JSON) | Bytes under `documents/<id>`; API-kroppen viser kun specifikationens felter |
| `UploadSession` | `id`, indekseret `token_hash` | `user_id`, `username`, `callback_url`, `callback_expires_at`, `expires_at`, `server_context`, `project_id`, `state`, `files_json` | `id` optræder i API-URL'er (bearer kræves); UI-URL'en bærer den token, hvis hash gemmes |
| `UploadPart` | `id` | `file_index`, `part_index`, `range_start`, `range_end`, `received`, `storage_key`, `size`, `expires_at` | Bytes under `parts/<id>`, indtil filen samles; oprydningsjobbet sletter udløbne dele og deres filer |
| `SelectionSession` | `id`, indekseret `token_hash` | `user_id`, `callback_url`, `callback_expires_at`, `expires_at`, `server_context`, `extensions[]`, `state`, `selected[]` | `selected` holder `document_id:version_index`-par valgt i browseren |
| `WebSession` | `id` (hash af cookien) | `created_at`, `expires_at`, `idle_expires_at`, `ip` | Browserlogin; `expires_at` er den absolutte levetid |
| `SignInThrottle` | `key` (hash af brugernavnet) | `failures`, `blocked_until`, `expires_at` | Mislykkede logins per brugernavn; udløber et døgn efter den seneste fejl, og et vellykket login fjerner den |

## IFC-graf (etape 9)

```mermaid
erDiagram
    Project ||--o{ IfcModel : HAS_MODEL
    IfcModel ||--o| IfcEntity : HAS_PROJECT
    IfcEntity }o--o{ IfcEntity : "IS_DEFINED_BY, HAS_PROPERTIES, ... (one type per IFC attribute)"
    Component }o--o| IfcEntity : SAME_AS
```

| Label | Nøgle | Egenskaber | Noter |
|---|---|---|---|
| `IfcModel` | `id`, indekseret `project_id` | `document_id`, `version_index` eller `bcf_document_guid`, `file_name`, `storage_key`, `state`, `schema`, `ifc_project_guid`, `entities`, `relationships`, `skipped`, `error`, tidsstempler | Én per importeret fil; `state` er `queued`, `running`, `done` eller `failed` |
| `IfcEntity` + klasselabels | `id` (`<model-id>:<step-id>`), indekseret `GlobalId`, `model_id` | `ifc_class`, `step_id`, hver literal IFC-attribut ved navn | Relationer mellem entiteter navngives efter IFC-attributten (fremad og inverst), skrevet som enhver relationstype med store bogstaver og understregninger: `IsDefinedBy` bliver `IS_DEFINED_BY` |

Se [ifcgraph.md](ifcgraph.md) for konverteringsreglerne og
eksempelforespørgsler.
