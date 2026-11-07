# Graafiskeema

Tietokanta on skeematon; `opencde/graph/schema.py` on skeema. Tämä sivu
selittää käytännöt ja nimiöt osio kerrallaan siinä järjestyksessä, jossa
suunnitelman vaiheet lisäsivät ne.

## Käytännöt

- Jokaisella solmulla on palvelimen luoma UUID kentässä `id` (tai
  spesifikaation nimi sille: `project_id`, `guid`, `client_id`,
  `document_id`) ja yksilöllisyysrajoite. Mikään asiakkaan lähettämä ei
  päädy tarkistamatta tiedostopolkuun tai tietokanta-avaimeen.
- Aikaleimat ovat ISO 8601 -merkkijonoja UTC-ajassa millisekunnein ja
  `Z`-päätteellä (`2026-11-05T12:34:56.789Z`). Merkkijonojärjestys on sama
  kuin aikajärjestys.
- Koordinaatit ja vektorit ovat tavallisia liukulukuja (`x`, `y`, `z`), ei
  koskaan `point()`.
- Kaikki vanheneva kantaa `expires_at`-kenttää (sama muoto); palvelin poistaa
  vanhentuneet solmut ajastimella (`opencde/graph/cleanup.py`).
- Salaisuudet (koodit, tokenit, asiakassalaisuudet) tallennetaan vain
  SHA-256-tiivisteinä.
- Cypher on murteesta riippumatonta, jotta Neo4j ja Memgraph käyttäytyvät
  samoin (ADR 0003). Skeeman DDL on ainoa tuotekohtainen teksti, ja se on
  tiedostossa `graph/dialect.py`.
- Nimet: nimiöt kirjoitetaan PascalCase-muodossa (`DocumentVersion`,
  `IfcModel`), suhdetyypit isoin kirjaimin ja alaviivoin (`HAS_TOPIC`,
  `CREATED_BY`, ja `IS_DEFINED_BY` IFC-attribuuttisuhteille). Alla olevat
  kaaviot piirtävät vain todelliset solmut ja suhteet; ominaisuutena pidetty
  viittaus (`AuditEvent.actor_user_id`, `UploadSession.user_id`) luetellaan
  laatikossa sen sijaan, että se piirrettäisiin viivana.

## Tilit ja pääsy (vaihe 1)

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

| Nimiö | Avain | Ominaisuudet | Huomautukset |
|---|---|---|---|
| `User` | `id`, yksilöllinen `username` | `email`, `full_name`, `password_hash` (Argon2id), `is_admin`, `disabled`, `created_at`, `must_change_password` | Käyttäjätunnus on se käyttäjän tunnus, jonka rajapinnat näyttävät |
| `MEMBER_OF` (suhde User → Project) | | `role` (viewer, contributor, editor, manager), `since` | Roolit kuvautuvat BCF:n `*_actions`-arvoihin, katso `accounts/roles.py` |
| `Project` | `project_id` | `name`, `created_at`, `topic_counter` | `topic_counter` numeroi `server_assigned_id`-arvot |
| `Extensions` | `id` | `topic_type[]`, `topic_status[]`, `topic_label[]`, `snippet_type[]`, `priority[]`, `stage[]`, `custom_information[]` | `users[]` lasketaan jäsenistä |
| `Client` | `client_id` | `name`, `description`, `url`, `redirect_uris[]`, `is_public`, `secret_hash`, `disabled`, `pending_approval`, `created_at`, `created_by`, `dynamic`, `expires_at` (vain itse rekisteröityneet) | OAuth2-asiakas; itse rekisteröitynyt poistetaan, kun `expires_at` on ohitettu ilman tokenin myöntämistä |
| `AuditEvent` | `id` | `type`, `at`, `actor_user_id`, `client_id`, `ip`, `details` (JSON-merkkijono) | Turvallisuuden kannalta merkitykselliset tapahtumat |
| `Reviewer`, `Building` | `id` | `name`, `status` | Konteksti tarkastussuunnitelman käyttötapauksesta (seed-data): tarkastava organisaatio (alkuperäisessä tarinassa kunta) ja rakennus |

## OAuth2 (vaihe 2)

```mermaid
erDiagram
    AuthorizationCode }o--|| User : FOR
    AuthorizationCode }o--|| Client : ISSUED_TO
    AccessToken }o--|| User : FOR
    AccessToken }o--|| Client : ISSUED_TO
    RefreshToken }o--|| User : FOR
    RefreshToken }o--|| Client : ISSUED_TO
```

`AuthorizationCode`, `AccessToken` ja `RefreshToken` (jolla on `family_id`)
avainnetaan salaisuuden tiivisteellä, kantavat `expires_at`-kenttää ja on
linkitetty `-[:FOR]->(:User)` ja `-[:ISSUED_TO]->(:Client)`. `WebSession`
(selainkirjautuminen, vaihe 5) on linkitetty vain `-[:FOR]->(:User)`.

## BCF-asiat ja tapahtumat (vaihe 3)

```mermaid
erDiagram
    Project ||--o{ Topic : HAS_TOPIC
    Topic }o--|| User : CREATED_BY
    Project ||--o{ Event : HAS_EVENT
```

| Nimiö | Avain | Ominaisuudet | Huomautukset |
|---|---|---|---|
| `Topic` | `guid` | `server_assigned_id`, `title`, `topic_type`, `topic_status`, `priority`, `stage`, `labels[]`, `reference_links[]`, `assigned_to`, `description`, `index`, `due_date`, `creation_date`, `creation_author`, `modified_date`, `modified_author`, `snippet_type`, `snippet_is_external`, `snippet_reference`, `snippet_reference_schema` | Kenttien nimet seuraavat `topic_GET.json`-tiedostoa; BIM snippet -objekti litistetään neljäksi ominaisuudeksi. `server_assigned_id` on `<etuliite><laskuri>` kentästä `Project.topic_counter` |
| `Event` | `id` | `kind` (`topic` tai `comment`), `topic_guid`, `comment_guid`, `author`, `date`, `action_types[]`, `action_values[]` | Yksi solmu jokaista jotakin muuttanutta pyyntöä kohti; kaksi rinnakkaista listaa ovat BCF 3.9/3.10:n `actions`-taulukko. Liitetty projektiin, jotta tapahtumat säilyvät asiansa jälkeen |

Jokainen asiakysely alkaa kutsujan `User`-solmusta ja kulkee
`MEMBER_OF`-suhteen kautta projektiin ennen kuin se koskee asiaan, joten
asia projektissa, jonka jäsen kutsuja ei ole, ei ole rajapinnan kannalta
olemassa (404).

## BCF-kommentit, viewpointit ja viittaukset (vaihe 4)

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

| Nimiö | Avain | Ominaisuudet | Huomautukset |
|---|---|---|---|
| `Comment` | `guid` | `topic_guid`, `date`, `author`, `comment`, `viewpoint_guid`, `modified_date`, `modified_author` | `viewpoint_guid`:n on nimettävä saman asian viewpoint |
| `Viewpoint` | `guid` | `index`, `author`, `creation_date`, `camera_kind`, `camera` (JSON), `lines` (JSON), `clipping_planes` (JSON), `snapshot_type`, `storage_key`, `has_components`, `default_visibility`, `has_hints`, `spaces_visible`, `space_boundaries_visible`, `openings_visible` | Muuttumaton. Geometria on JSON-tekstiä: opaakkia ja samanlaista molemmissa tietokannoissa |
| `Component` | `id` | `role` (`selection`, `coloring`, `exception`), `group_index`, `position`, `color`, `ifc_guid`, `originating_system`, `authoring_tool_id` | Yksi solmu esiintymää kohti; IFC-graafi linkittää `ifc_guid`:n mallin elementteihin (vaihe 9) |
| `Bitmap` | `guid` | `position`, `bitmap_type`, `storage_key`, `height`, `loc_*`, `nrm_*`, `up_*` | Kuvatavut tallennustilassa polussa `bitmaps/<guid>.<tyyppi>` |
| `FileRef` | `id` | `position`, `ifc_project`, `ifc_spatial_structure_element`, `filename`, `date`, `reference` | Asian otsakkeen tiedostot (BCF 3.3) |
| `DocumentReference` | `guid` | `document_guid` tai `url`, `description`, `created_at` | Tasan yksi kahdesta kohteesta |
| `BcfDocument` | `guid` | `filename`, `storage_key`, `size`, `created_at`, `author` | BCF 3.8:n kautta lähetetty tiedosto; tavut polussa `bcf-documents/<guid>` |
| `RELATED_TO` (suhde Topic → Topic) | | | Suunnattu; PUT korvaa asian lähtevän listan |

Asiat pitävät snippet-tiedostonsa kentässä `snippet_storage_key` (tavut
polussa `snippets/<asian guid>.bin`). Asian poisto poistaa kaiken sen alla
sekä solmuista kerätyt tallennusavaimet; tapahtumat säilyvät.

## Asiakirjat ja selainistunnot (vaihe 5)

```mermaid
erDiagram
    Project ||--o{ Document : HAS_DOCUMENT
    Document ||--|{ DocumentVersion : HAS_VERSION
    DocumentVersion }o--|| User : UPLOADED_BY
    DocumentVersion ||--o| IfcValidation : HAS_VALIDATION
    UploadSession ||--o{ UploadPart : HAS_PART
    WebSession }o--|| User : FOR
    UploadSession {
        string user_id
    }
    SelectionSession {
        string user_id
    }
```

| Nimiö | Avain | Ominaisuudet | Huomautukset |
|---|---|---|---|
| `Document` | `document_id` | `title`, `created_at`, `latest_index` | `latest_index` numeroi versiot |
| `DocumentVersion` | `id` | `version_index`, `version_number`, `creation_date`, `title`, `file_name`, `size_in_bytes`, `sha256`, `storage_key`, `author`, `metadata` (JSON) | Tavut polussa `documents/<id>`; rajapinnan runko näyttää vain spesifikaation kentät |
| `IfcValidation` | `id` | `state`, `checked_at`, `issue_count`, `truncated`, `ruleset`, `report`, `storage_key`, `file_name`, `error` | Lähetetyn IFC-tiedoston tarkistus IFC-skeemaa vasten (ADR 0011); `report` on enintään 10 000 huomautusta pakattuna JSONina. Poistetaan version projektin mukana |
| `UploadSession` | `id`, indeksoitu `token_hash` | `user_id`, `username`, `callback_url`, `callback_expires_at`, `expires_at`, `server_context`, `project_id`, `state`, `files_json` | `id` esiintyy rajapinnan URLeissa (bearer vaaditaan); käyttöliittymän URL kantaa tokenia, jonka tiiviste tallennetaan |
| `UploadPart` | `id` | `file_index`, `part_index`, `range_start`, `range_end`, `received`, `storage_key`, `size`, `expires_at` | Tavut polussa `parts/<id>`, kunnes tiedosto kootaan; siivoustyö poistaa vanhentuneet osat ja niiden tiedostot |
| `SelectionSession` | `id`, indeksoitu `token_hash` | `user_id`, `callback_url`, `callback_expires_at`, `expires_at`, `server_context`, `extensions[]`, `state`, `selected[]` | `selected` sisältää selaimessa valitut `document_id:version_index`-parit |
| `WebSession` | `id` (evästeen tiiviste) | `created_at`, `expires_at`, `idle_expires_at`, `ip` | Selainkirjautuminen; `expires_at` on absoluuttinen elinaika |
| `SignInThrottle` | `key` (käyttäjätunnuksen tiiviste) | `failures`, `blocked_until`, `expires_at` | Epäonnistuneet kirjautumiset käyttäjätunnuksittain; vanhenee vuorokauden kuluttua viimeisestä epäonnistumisesta, ja onnistunut kirjautuminen poistaa sen |

## IFC-graafi (vaihe 9)

```mermaid
erDiagram
    Project ||--o{ IfcModel : HAS_MODEL
    IfcModel ||--o| IfcEntity : HAS_PROJECT
    IfcModel ||--o{ StepBlock : HAS_STEP_BLOCK
    IfcEntity }o--o{ IfcEntity : "IS_DEFINED_BY, HAS_PROPERTIES, ... (one type per IFC attribute)"
    Component }o--o| IfcEntity : SAME_AS
```

| Nimiö | Avain | Ominaisuudet | Huomautukset |
|---|---|---|---|
| `IfcModel` | `id`, indeksoitu `project_id` | `document_id`, `version_index` tai `bcf_document_guid`, `file_name`, `storage_key`, `state`, `schema`, `ifc_project_guid`, `entities`, `relationships`, `skipped`, `lossless`, `ifc_header`, `error`, aikaleimat | Yksi tuotua tiedostoa kohti; `state` on `queued`, `running`, `done` tai `failed` |
| `IfcEntity` + luokkanimiöt | `id` (`<mallin tunnus>:<step-tunnus>`), indeksoitu `GlobalId`, `model_id` | `ifc_class`, `step_id`, jokainen literaali IFC-attribuutti nimellään | Entiteettien väliset suhteet nimetään IFC-attribuutin mukaan (eteen- ja käänteissuuntaan), kirjoitettuina kuten jokainen suhdetyyppi isoin kirjaimin ja alaviivoin: `IsDefinedBy` muuttuu `IS_DEFINED_BY`:ksi |
| `StepBlock` | `id` (`<mallin tunnus>:<ensimmäinen step-tunnus>`) | `first_step`, `instances`, `text` | Asetuksella `OPENCDE_IFCGRAPH_LOSSLESS` muunnetun mallin instanssit, jotka eivät ole solmuja: kirjoitettu STEP-muotoon tunnusjärjestyksessä ja pakattu. Älä palauta solmua kokonaisena kyselyssä `text`-kentän vuoksi |

Katso [ifcgraph.md](ifcgraph.md) muunnossäännöt ja esimerkkikyselyt.
