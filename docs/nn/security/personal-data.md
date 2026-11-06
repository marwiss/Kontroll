# Personopplysningar og lagringstid

Kva ein Kontroll-server lagrar om personar, kor lenge, og kven som kan sjå
det. Dette er serveren sin halvdel av ei side som blir delt med Dataspatium;
appen sin halvdel (kva han lagrar i nettlesaren og kva han sender) står i
dokumentasjonen til Dataspatium. Den som driv Kontroll for andre, er
behandlingsansvarleg for desse opplysningane; sida gjev fakta til eigne
oversikter.

## Kva som blir lagra

| Opplysning | Kvar | Innhald | Blir halde |
|---|---|---|---|
| Brukarkontoar | `User`-nodar | brukarnamn, fullt namn, e-post (valfritt), Argon2id-hash av passordet, administratorflagg, opprettingstid, siste innlogging | Til ein administrator slettar kontoen |
| Prosjektmedlemskap | `MEMBER_OF`-relasjonar | brukar, prosjekt, rolle | Til det blir fjerna |
| OAuth2-tokens | nodane `AuthorizationCode`, `AccessToken`, `RefreshToken` | SHA-256-hashar (aldri sjølve tokenane), brukar, klient, scope, tidspunkt | Kodar 60 s, access-tokens 1 t, refresh-tokens 30 dagar (`OPENCDE_*_TTL_SECONDS`); sletta av oppryddinga når dei har gått ut eller er trekte tilbake |
| Nettlesarsesjonar | `WebSession`-nodar | brukar, opprettings- og siste aktivitetstid, klientadressa ved innlogging | 8 timar, eller 30 minutt utan aktivitet; sletta ved utlogging |
| OAuth2-klientar | `Client`-nodar | namn, skildring, adresse, redirect-URI-ar, hasha løyndom, `software_id`/`software_version`, kven som oppretta han | Til dei blir sletta; sjølvregistrerte klientar som ikkje er brukte på 30 dagar, blir sletta med tokenane sine |
| BCF-data | nodane `Topic`, `Comment`, `Viewpoint`, `Event` og tilhøyrande | titlar, skildringar og kommentarar skrivne av brukarar, brukarnamn som forfattarar og tildelte, tidspunkt, augneblinksbilete, komponentreferansar | Til saka, kommentaren eller prosjektet blir sletta |
| Dokument | nodane `Document` og `DocumentVersion`, filer under `OPENCDE_DATA_DIR` | tittel, filnamn, storleik, SHA-256, opplastar, tid; sjølve fila (som kan innehalde personopplysningar, til dømes namn i eigarhistorikken til ein IFC-modell) | Til versjonen eller prosjektet blir sletta; tryggingskopiar held på kopiar så lenge operatøren held på tryggingskopiane |
| IFC-graf | `IfcModel`-nodar og entitetane i kvar importert modell | innhaldet i IFC-fila som grafdata, inkludert `IfcOwnerHistory` for prosjektet | Erstatta eller mislukka modellar blir fjerna med `opencde ifcgraph prune`; elles med dokumentversjonen |
| Revisjonslogg | `AuditEvent`-nodar | kva som hende (innlogging, utferda token, registrert klient, endra rolle …), kven som gjorde det, klientadressa, tid, request-id | Går ikkje ut av seg sjølv; administratorar kan eksportere han som CSV, og operatøren slettar etter eigen policy |
| Førespurnadslogg (valfri) | `RequestLog`-nodar | metode, sti utan spørjestreng, operasjon, status, tid, bytetal, request-id, brukar- eller klient-id; aldri hovud, kroppar eller tokens | `OPENCDE_REQUEST_LOG_RETENTION_HOURS` (72 som standard); av med mindre `OPENCDE_REQUEST_LOG_ENABLED=true` |
| Opplastings- og utvalssesjonar | nodane `UploadSession`, `UploadPart`, `SelectionSession` og mellombelse delfiler | kven som starta flyten, kva filer, callback-adresse, tidspunkt | 24 timar for opplastingar, 10 minutt for sidelenkjene; rydda av serveren |
| Serverloggar | standardutdata frå containeren (JSON-linjer) | request-id, sti, status, tid, brukar- eller klient-id, klientadressa frå den betrudde proxyen; aldri kroppar, tokens, kodar eller passord | Så lenge operatøren held på containerloggar |

Tryggingskopiar laga med `opencde backup` eller tenesta `backup` inneheld
alt ovanfor unnateke serverloggane, krypterte eller ikkje etter operatøren
sitt val ([deploy/backup.md](../deploy/backup.md)).

## Kven ser kva

- Medlemer av eit prosjekt ser sakene, kommentarane, viewpointane og
  dokumenta gjennom API-ane; rolla avgjer kva dei får endre. Brukarar utanfor
  eit prosjekt kan ikkje sjå at det finst (404).
- Administratorar ser alle brukarar, prosjekt, klientar, sesjonar,
  revisjonsloggen og, når han er på, førespurnadsloggen, på sidene under
  `/admin` og, med ein bearer-token som har scopet `admin`, gjennom
  `/admin/api`.
- Kvar brukar ser sin eigen konto, sine applikasjonar og sesjonar på
  `/account` og kan trekkje dei tilbake.
- Ingen ser passord, løyndomar eller tokens: serveren lagrar berre hashar og
  viser ein ny løyndom éin gong, ved opprettinga.
- Alle kan lese `/.well-known/kontroll`, `/foundation/versions`,
  `/foundation/1.0/auth` og `/healthz`; dei inneheld konfigurasjon, aldri
  personar.

## Rettar og handlingar

- **Slett ein person**: slett kontoen under `/admin/users` (eller med
  `opencde user delete`); sesjonar og tokens følgjer med. Namnet står att på
  saker og kommentarar personen har skrive, som BCF-dataa til prosjektet;
  slett eller rediger dei gjennom API-et, eller slett prosjektet.
- **Eksporter**: revisjonsloggen blir eksportert som CSV; BCF- og
  dokumentdata blir eksporterte gjennom API-ane (ein klient som Dataspatium
  kan lagre eit prosjekt som BCFzip); `opencde backup` skriv heile databasen.
- **Hending**: `opencde revoke --all` avsluttar alle sesjonar og tokens;
  roter databasepassordet og den løynde nøkkelen etterpå
  ([controls.md](controls.md)).
- **Minimer**: lat førespurnadsloggen vere av med mindre du feilsøkjer ein
  klient, hald `OPENCDE_DYNAMIC_CLIENT_REGISTRATION` av med mindre du treng
  han, og publiser ikkje databaseporten ([deploy/bolt.md](../deploy/bolt.md)).

## I Dataspatium

Appen lagrar adressa til serveren, klient-id-en han har registrert,
brukaren sine tokens for sesjonen og ein logg over kalla sine (med
request-id-ar) i nettlesaren; han lagrar aldri passordet. Kva av dette som
forlèt nettlesaren, og korleis det blir tømt, står på [Dataspatium si eiga side om personopplysningar](https://github.com/marwiss/Dataspatium/blob/main/docs/nn/sakerhet.md).
