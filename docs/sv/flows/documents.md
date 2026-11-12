# Documents API-flöden

Documents API 1.0 är en konversation mellan tre parter: klientapplikationen,
den här servern och användarens webbläsare. Klienten talar med API:t med en
bearer-token; webbläsaren visar serverns egna sidor (inloggning,
metadatainmatning, dokumentval); servern anropar aldrig klienten, den
omdirigerar bara webbläsaren till klientens callback-URL.

## Uppladdning

```mermaid
sequenceDiagram
    participant C as Klient (bearer-token)
    participant S as Server
    participant B as Webbläsare
    C->>S: POST /documents/1.0/upload-documents {callback, files}
    S-->>C: {upload_ui_url, expires_in, max_size_in_bytes}
    C->>B: öppna upload_ui_url
    B->>S: GET /documents/1.0/upload-ui/{token}
    S-->>B: inloggningssida vid behov, sedan metadataformuläret
    B->>S: POST formulär (titel, version, projekt, formulärtoken)
    S-->>B: 302 callback?upload_documents_url=… (eller user_cancelled_upload=true)
    B->>C: callback
    C->>S: POST /upload-sessions/{id}/instructions {files: [{session_file_id, size_in_bytes}]}
    S-->>C: {documents_to_upload: [{upload_file_parts, upload_completion, upload_cancellation}]}
    loop varje del
        C->>S: PUT /upload-part/{part_id} (bytena i intervallet)
    end
    C->>S: POST /upload-sessions/{id}/files/{n}/complete
    S-->>C: DocumentVersion
```

* UI-länken är giltig i `OPENCDE_DOCUMENTS_SESSION_TTL_SECONDS` (10 minuter);
  när instruktioner har utfärdats lever sessionen
  `OPENCDE_UPLOAD_SESSION_TTL_SECONDS` (24 timmar) så att stora filer kan
  laddas upp.
* Delarna är `OPENCDE_UPLOAD_PART_BYTES` (50 MiB) var, laddas upp i valfri
  ordning, parallellt om klienten vill. En del måste vara exakt det
  annonserade intervallet.
* Slutförandet sätter samman delarna, verifierar den totala storleken,
  beräknar SHA-256 och skapar versionen. Om det tar mer än 15 sekunder börjar
  svaret med blanksteg för att hålla anslutningen öppen.
* `document_id` i en filpost gör uppladdningen till en ny version av det
  dokumentet; titeln behålls, versionsindexet ökar.
* `base_version_index` i en filpost (ett tillägg) säger vilken version
  uppladdningen bygger på: avslutet svarar `412 version_conflict` när dokumentet
  redan har en nyare, och versionens metadata anger basen.
* Ett projekt kan avvisa filer med valideringsfel: avslutet svarar då
  `422 ifc_validation_failed` med rapportens adress, och
  `POST …/projects/{id}/ifc-precheck` kontrollerar en fil utan att spara den.
* En konfidentiell klient som en administratör godkänt för det (*Får ladda upp
  dokument utan webbsidan* på klientens sida) laddar upp huvudlöst: `project_id`
  i begäran, med `title` och `version_number` per fil, hoppar över sidan, och
  instruktionerna finns genast på `upload-sessions/{id}/instructions`; varje
  sådan uppladdning står i granskningsloggen. 403 för varje annan klient.

## Urval och nedladdning

```mermaid
sequenceDiagram
    participant C as Klient (bearer-token)
    participant S as Server
    participant B as Webbläsare
    C->>S: POST /documents/1.0/select-documents {callback, supported_file_extensions}
    S-->>C: {select_documents_url, expires_in}
    C->>B: öppna select_documents_url
    B->>S: GET /documents/1.0/select-ui/{token}
    S-->>B: inloggningssida vid behov, sedan dokumentlistan
    B->>S: POST formulär (valda dokument-id:n, formulärtoken)
    S-->>B: 302 callback?selected_documents_url=… (eller user_cancelled_selection=true)
    B->>C: callback
    C->>S: GET /selection-sessions/{id}/documents
    S-->>C: {server_context, documents: [DocumentVersion]}
    C->>S: GET links.document_version_download
    S-->>C: filen (bilaga)
```

* Listan visar den senaste versionen av varje dokument i användarens projekt,
  filtrerad på klientens filändelser med en länk "visa alla".
* Användare med rollen editor eller manager kan ladda upp en fil från sidan;
  den dyker upp i listan direkt (detta är ett tillägg till specifikationen).
* `POST /documents/1.0/document-versions` svarar med de senaste versionerna
  av en lista dokument-id:n med en `ETag`; `If-None-Match` ger `304`.

[Dataspatium](https://github.com/marwiss/Dataspatium) implementerar båda
flödena från webbläsaren (`src/api/families/opencde.js`): den öppnar serverns
urvalssida i ett popup-fönster och importerar de valda filerna, och laddar
upp datamängder, filer och arbetsytepaket i delar med serverns
uppladdningssida för metadata; dess live-sviter kör dessa flöden mot
utvecklingsstacken.

## Vem får göra vad

| Handling | Kräver |
|---|---|
| Starta en uppladdning eller ett urval | en bearer-token med scopet `documents` |
| Använda webbläsarsidorna | en webbläsarsession som samma användare (`/signin`) |
| Spara metadata, slutföra en uppladdning, ladda upp från sidan | rollen editor eller manager |
| Se, välja och ladda ned dokument | medlemskap i projektet (vilken roll som helst) |
| Publicera en version | rollen `manager` |

Dokument i andra projekt finns inte för anroparen (404), så varken deras id:n
eller deras existens läcker.
