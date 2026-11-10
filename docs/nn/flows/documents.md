# Documents API-flytar

Documents API 1.0 er ein samtale mellom tre partar: klientapplikasjonen, denne
serveren og nettlesaren til brukaren. Klienten snakkar med API-et med eit
bearer-token; nettlesaren viser serveren sine eigne sider (innlogging,
inntasting av metadata, dokumentval); serveren kallar aldri klienten, han
omdirigerer berre nettlesaren til callback-URL-en til klienten.

## Opplasting

```mermaid
sequenceDiagram
    participant C as Klient (bearer-token)
    participant S as Server
    participant B as Nettlesar
    C->>S: POST /documents/1.0/upload-documents {callback, files}
    S-->>C: {upload_ui_url, expires_in, max_size_in_bytes}
    C->>B: opne upload_ui_url
    B->>S: GET /documents/1.0/upload-ui/{token}
    S-->>B: innloggingsside om naudsynt, deretter metadataskjemaet
    B->>S: POST skjema (tittel, versjon, prosjekt, skjematoken)
    S-->>B: 302 callback?upload_documents_url=… (eller user_cancelled_upload=true)
    B->>C: callback
    C->>S: POST /upload-sessions/{id}/instructions {files: [{session_file_id, size_in_bytes}]}
    S-->>C: {documents_to_upload: [{upload_file_parts, upload_completion, upload_cancellation}]}
    loop kvar del
        C->>S: PUT /upload-part/{part_id} (bytane i intervallet)
    end
    C->>S: POST /upload-sessions/{id}/files/{n}/complete
    S-->>C: DocumentVersion
```

* UI-lenkja er gyldig i `OPENCDE_DOCUMENTS_SESSION_TTL_SECONDS` (10 minutt);
  når instruksjonar er utferda, lever sesjonen
  `OPENCDE_UPLOAD_SESSION_TTL_SECONDS` (24 timar) slik at store filer kan
  lastast opp.
* Delane er `OPENCDE_UPLOAD_PART_BYTES` (50 MiB) kvar, blir lasta opp i
  vilkårleg rekkjefølgje, parallelt om klienten vil. Ein del må vere nøyaktig
  det annonserte intervallet.
* Fullføringa set saman delane, verifiserer den totale storleiken, reknar ut
  SHA-256 og opprettar versjonen. Tek det meir enn 15 sekund, byrjar svaret
  med blankteikn for å halde sambandet ope.
* `document_id` i ein filpost gjer opplastinga til ein ny versjon av det
  dokumentet; tittelen blir halden på, versjonsindeksen aukar.
* `base_version_index` i ein filpost (ei utviding) seier kva versjon
  opplastinga byggjer på: fullføringa svarar `412 version_conflict` når
  dokumentet alt har ein nyare, og metadataa til versjonen oppgjev basen.

## Utval og nedlasting

```mermaid
sequenceDiagram
    participant C as Klient (bearer-token)
    participant S as Server
    participant B as Nettlesar
    C->>S: POST /documents/1.0/select-documents {callback, supported_file_extensions}
    S-->>C: {select_documents_url, expires_in}
    C->>B: opne select_documents_url
    B->>S: GET /documents/1.0/select-ui/{token}
    S-->>B: innloggingsside om naudsynt, deretter dokumentlista
    B->>S: POST skjema (valde dokument-id-ar, skjematoken)
    S-->>B: 302 callback?selected_documents_url=… (eller user_cancelled_selection=true)
    B->>C: callback
    C->>S: GET /selection-sessions/{id}/documents
    S-->>C: {server_context, documents: [DocumentVersion]}
    C->>S: GET links.document_version_download
    S-->>C: fila (vedlegg)
```

* Lista viser den siste versjonen av kvart dokument i prosjekta til brukaren,
  filtrert på filendingane til klienten med ei lenkje "vis alle".
* Brukarar med rolla editor eller manager kan laste opp ei fil frå sida; ho
  dukkar opp i lista straks (dette er eit tillegg til spesifikasjonen).
* `POST /documents/1.0/document-versions` svarar med dei siste versjonane av
  ei liste dokument-id-ar med ein `ETag`; `If-None-Match` gjev `304`.

[Dataspatium](https://github.com/marwiss/Dataspatium) implementerer begge
flytane frå nettlesaren (`src/api/families/opencde.js`): han opnar utvalssida
til serveren i eit popup-vindauge og importerer dei valde filene, og lastar
opp datasett, filer og arbeidsområdepakkar i delar med opplastingssida til
serveren for metadata; live-suitene køyrer desse flytane mot
utviklingsstakken.

## Kven får gjere kva

| Handling | Krev |
|---|---|
| Starte ei opplasting eller eit utval | eit bearer-token med scopet `documents` |
| Bruke nettlesarsidene | ein nettlesarsesjon som same brukar (`/signin`) |
| Lagre metadata, fullføre ei opplasting, laste opp frå sida | prosjekthandlinga `createDocument` (editor, manager) |
| Sjå, velje og laste ned dokument | medlemskap i prosjektet (kva rolle som helst) |

Dokument i andre prosjekt finst ikkje for kallaren (404), så verken id-ane
eller eksistensen deira lek.
