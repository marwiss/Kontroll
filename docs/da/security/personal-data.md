# Personoplysninger og opbevaring

Hvad en Dataregium-server gemmer om personer, hvor længe, og hvem der kan se
det. Dette er serverens halvdel af en side, der deles med Dataspatium;
appens halvdel (hvad den gemmer i browseren, og hvad den sender) står i
Dataspatiums dokumentation. Den, der driver Dataregium for andre, er
dataansvarlig for disse oplysninger; siden giver fakta til de egne
fortegnelser.

## Hvad der gemmes

| Oplysning | Hvor | Indhold | Opbevares |
|---|---|---|---|
| Brugerkonti | `User`-noder | brugernavn, fulde navn, e-mail (valgfrit), Argon2id-hash af kodeordet, administratorflag, oprettelsestid, seneste login | Indtil en administrator sletter kontoen |
| Projektmedlemskaber | `MEMBER_OF`-relationer | bruger, projekt, rolle | Indtil det fjernes |
| OAuth2-tokens | noderne `AuthorizationCode`, `AccessToken`, `RefreshToken` | SHA-256-hashes (aldrig selve tokens), bruger, klient, scope, tidspunkter | Koder 60 s, access-tokens 1 t, refresh-tokens 30 dage (`OPENCDE_*_TTL_SECONDS`); slettes af oprydningen, når de er udløbet eller tilbagekaldt |
| Browsersessioner | `WebSession`-noder | bruger, oprettelses- og seneste aktivitetstid, klientadressen ved login | 8 timer eller 30 minutters inaktivitet; slettes ved logout |
| Mislykkede logins | `SignInThrottle`-noder | en hash af brugernavnet, antallet af fejl, hvornår næste forsøg er tilladt | et døgn efter den seneste fejl; et vellykket login fjerner den |
| OAuth2-klienter | `Client`-noder | navn, beskrivelse, adresse, redirect-URI'er, hashet hemmelighed, `software_id`/`software_version`, hvem der oprettede den | Indtil de slettes; selvregistrerede klienter, der ikke er brugt i 30 dage, slettes med deres tokens |
| BCF-data | noderne `Topic`, `Comment`, `Viewpoint`, `Event` og tilhørende | titler, beskrivelser og kommentarer skrevet af brugere, brugernavne som forfattere og ansvarlige, tidspunkter, snapshotbilleder, komponentreferencer | Indtil emnet, kommentaren eller projektet slettes |
| Dokumenter | noderne `Document` og `DocumentVersion`, filer under `OPENCDE_DATA_DIR` | titel, filnavn, størrelse, SHA-256, uploader, tid; selve filen (som kan indeholde personoplysninger, for eksempel navne i en IFC-models ejerhistorik) | Indtil versionen eller projektet slettes; sikkerhedskopier beholder kopier, så længe operatøren beholder sikkerhedskopierne |
| IFC-graf | `IfcModel`-noder og entiteterne i hver importeret model | IFC-filens indhold som grafdata, inklusive `IfcOwnerHistory` for projektet | Erstattede eller fejlede modeller fjernes med `opencde ifc-lpg prune`; ellers med dokumentversionen |
| Revisionslog | `AuditEvent`-noder | hvad der skete (login, udstedt token, registreret klient, ændret rolle …), hvem der gjorde det, klientadressen, tid, request-id | Udløber ikke af sig selv; administratorer kan eksportere den som CSV, og operatøren sletter efter egen politik |
| Forespørgselslog (tilvalg) | `RequestLog`-noder | metode, sti uden forespørgselsstreng, operation, status, tid, bytetal, request-id, bruger- eller klient-id; aldrig headers, kroppe eller tokens | `OPENCDE_REQUEST_LOG_RETENTION_HOURS` (72 som standard); slået fra, medmindre `OPENCDE_REQUEST_LOG_ENABLED=true` |
| Upload- og udvælgelsessessioner | noderne `UploadSession`, `UploadPart`, `SelectionSession` og midlertidige delfiler | hvem der startede forløbet, hvilke filer, callback-adresse, tidspunkter | 24 timer for uploads, 10 minutter for sidelinkene; ryddes op af serveren |
| Serverlogs | containerens standardoutput (JSON-linjer) | request-id, sti, status, tid, bruger- eller klient-id, klientadressen fra den betroede proxy; aldrig kroppe, tokens, koder eller kodeord | Så længe operatøren beholder containerlogs |

Sikkerhedskopier lavet med `opencde backup` eller tjenesten `backup`
indeholder alt ovenstående undtagen serverloggene, krypteret eller ej efter
operatørens valg ([deploy/backup.md](../deploy/backup.md)).

## Hvem kan se hvad

- Medlemmer af et projekt ser dets emner, kommentarer, viewpoints og
  dokumenter gennem API'erne; rollen afgør, hvad de må ændre. Brugere uden
  for et projekt kan ikke se, at det findes (404).
- Administratorer ser alle brugere, projekter, klienter, sessioner,
  revisionsloggen og, når den er slået til, forespørgselsloggen på siderne
  under `/admin` og, med en bearer-token med scopet `admin`, gennem
  `/admin/api`.
- Hver bruger ser sin egen konto, sine applikationer og sessioner på
  `/account` og kan tilbagekalde dem.
- Ingen ser kodeord, hemmeligheder eller tokens: serveren gemmer kun
  hashes og viser en ny hemmelighed én gang, ved oprettelsen.
- Alle kan læse `/.well-known/dataregium`, `/foundation/versions`,
  `/foundation/1.0/auth` og `/healthz`; de indeholder konfiguration, aldrig
  personer.

## Rettigheder og handlinger

- **Slet en person**: slet kontoen under `/admin/users` (eller med
  `opencde user delete`); sessioner og tokens følger med. Navnet bliver
  stående på emner og kommentarer, personen har skrevet, som projektets
  BCF-data; slet eller redigér dem gennem API'et, eller slet projektet.
- **Eksportér**: revisionsloggen eksporteres som CSV; BCF- og dokumentdata
  eksporteres gennem API'erne (en klient som Dataspatium kan gemme et projekt
  som BCFzip); `opencde backup` skriver hele databasen.
- **Hændelse**: `opencde revoke --all` afslutter alle sessioner og tokens;
  rotér databasekodeordet og den hemmelige nøgle bagefter
  ([controls.md](controls.md)).
- **Minimér**: lad forespørgselsloggen være slået fra, medmindre du fejlsøger
  en klient, hold `OPENCDE_DYNAMIC_CLIENT_REGISTRATION` slået fra, medmindre
  du har brug for den, og udgiv ikke databaseporten
  ([deploy/bolt.md](../deploy/bolt.md)).

## I Dataspatium

Appen gemmer serverens adresse, det klient-id, den har registreret,
brugerens tokens for sessionen og en log over sine kald (med request-id'er)
i browseren; den gemmer aldrig kodeordet. Hvad af dette der forlader
browseren, og hvordan det ryddes, står på [Dataspatiums egen side om personoplysninger](https://github.com/marwiss/Dataspatium/blob/main/docs/da/sakerhet.md).
