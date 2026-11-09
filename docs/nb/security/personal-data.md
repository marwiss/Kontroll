# Personopplysninger og lagringstid

Hva en Dataregium-server lagrer om personer, hvor lenge, og hvem som kan se
det. Dette er serverens halvdel av en side som deles med Dataspatium; appens
halvdel (hva den lagrer i nettleseren og hva den sender) står i Dataspatiums
dokumentasjon. Den som driver Dataregium for andre, er behandlingsansvarlig for
disse opplysningene; siden gir fakta til egne oversikter.

## Hva som lagres

| Opplysning | Hvor | Innhold | Beholdes |
|---|---|---|---|
| Brukerkontoer | `User`-noder | brukernavn, fullt navn, e-post (valgfritt), Argon2id-hash av passordet, administratorflagg, opprettelsestid, siste innlogging | Til en administrator sletter kontoen |
| Prosjektmedlemskap | `MEMBER_OF`-relasjoner | bruker, prosjekt, rolle | Til det fjernes |
| OAuth2-tokens | nodene `AuthorizationCode`, `AccessToken`, `RefreshToken` | SHA-256-hasher (aldri selve tokenene), bruker, klient, scope, tidspunkter | Koder 60 s, access-tokens 1 t, refresh-tokens 30 dager (`OPENCDE_*_TTL_SECONDS`); slettes av oppryddingen når de er utløpt eller trukket tilbake |
| Nettlesersesjoner | `WebSession`-noder | bruker, opprettelses- og siste aktivitetstid, klientadressen ved innlogging | 8 timer, eller 30 minutters inaktivitet; slettes ved utlogging |
| Mislykkede innlogginger | `SignInThrottle`-noder | en hash av brukernavnet, antall feil, når neste forsøk er tillatt | et døgn etter siste feil; en vellykket innlogging fjerner den |
| OAuth2-klienter | `Client`-noder | navn, beskrivelse, adresse, redirect-URI-er, hashet hemmelighet, `software_id`/`software_version`, hvem som opprettet den | Til de slettes; selvregistrerte klienter som ikke er brukt på 30 dager, slettes med tokenene sine |
| BCF-data | nodene `Topic`, `Comment`, `Viewpoint`, `Event` og tilhørende | titler, beskrivelser og kommentarer skrevet av brukere, brukernavn som forfattere og tildelte, tidspunkter, øyeblikksbilder, komponentreferanser | Til saken, kommentaren eller prosjektet slettes |
| Dokumenter | nodene `Document` og `DocumentVersion`, filer under `OPENCDE_DATA_DIR` | tittel, filnavn, størrelse, SHA-256, opplaster, tid; selve filen (som kan inneholde personopplysninger, for eksempel navn i en IFC-modells eierhistorikk) | Til versjonen eller prosjektet slettes; sikkerhetskopier beholder kopier så lenge operatøren beholder sikkerhetskopiene |
| IFC-graf | `IfcModel`-noder og entitetene i hver importerte modell | IFC-filens innhold som grafdata, inkludert `IfcOwnerHistory` for prosjektet; med `OPENCDE_IFC_LPG_LOSSLESS`, som er standard, hele filen, med headeren og hver owner history | Erstattede eller mislykkede modeller fjernes med `opencde ifc-lpg prune`; ellers med dokumentversjonen |
| IFC-validering | `IfcValidation`-noder under dokumentversjoner | hvor mange anmerkninger filen har og når den ble kontrollert, og opptil 10 000 anmerkninger der meldingene kan sitere linjer fra filen | Med dokumentversjonen eller prosjektet |
| Revisjonslogg | `AuditEvent`-noder | hva som skjedde (innlogging, utstedt token, registrert klient, endret rolle …), hvem som gjorde det, klientadressen, tid, request-id | Utløper ikke av seg selv; administratorer kan eksportere den som CSV, og operatøren sletter etter egen policy |
| Forespørselslogg (valgfri) | `RequestLog`-noder | metode, sti uten spørrestreng, operasjon, status, tid, bytetall, request-id, bruker- eller klient-id; aldri headere, kropper eller tokens | `OPENCDE_REQUEST_LOG_RETENTION_HOURS` (72 som standard); av med mindre `OPENCDE_REQUEST_LOG_ENABLED=true` |
| Opplastings- og utvalgssesjoner | nodene `UploadSession`, `UploadPart`, `SelectionSession` og midlertidige delfiler | hvem som startet flyten, hvilke filer, callback-adresse, tidspunkter | 24 timer for opplastinger, 10 minutter for sidelenkene; ryddes av serveren |
| Serverlogger | containerens standardutdata (JSON-linjer) | request-id, sti, status, tid, bruker- eller klient-id, klientadressen fra den betrodde proxyen; aldri kropper, tokens, koder eller passord | Så lenge operatøren beholder containerlogger |

Sikkerhetskopier laget med `opencde backup` eller tjenesten `backup`
inneholder alt ovenfor unntatt serverloggene, kryptert eller ikke etter
operatørens valg ([deploy/backup.md](../deploy/backup.md)).

## Hvem ser hva

- Medlemmer av et prosjekt ser sakene, kommentarene, viewpointene og
  dokumentene gjennom API-ene; rollen avgjør hva de får endre. Brukere
  utenfor et prosjekt kan ikke se at det finnes (404).
- Administratorer ser alle brukere, prosjekter, klienter, sesjoner,
  revisjonsloggen og, når den er på, forespørselsloggen, på sidene under
  `/admin` og, med en bearer-token som har scopet `admin`, gjennom
  `/admin/api`.
- Hver bruker ser sin egen konto, sine applikasjoner og sesjoner på
  `/account` og kan trekke dem tilbake.
- Ingen ser passord, hemmeligheter eller tokens: serveren lagrer bare hasher
  og viser en ny hemmelighet én gang, ved opprettelsen.
- Alle kan lese `/.well-known/dataregium`, `/foundation/versions`,
  `/foundation/1.0/auth` og `/healthz`; de inneholder konfigurasjon, aldri
  personer.

## Rettigheter og handlinger

- **Slett en person**: slett kontoen under `/admin/users` (eller med
  `opencde user delete`); sesjoner og tokens følger med. Navnet blir stående
  på saker og kommentarer personen har skrevet, som prosjektets BCF-data;
  slett eller rediger dem gjennom API-et, eller slett prosjektet.
- **Eksporter**: revisjonsloggen eksporteres som CSV; BCF- og dokumentdata
  eksporteres gjennom API-ene (en klient som Dataspatium kan lagre et prosjekt
  som BCFzip); `opencde backup` skriver hele databasen.
- **Hendelse**: `opencde revoke --all` avslutter alle sesjoner og tokens;
  roter databasepassordet og den hemmelige nøkkelen etterpå
  ([controls.md](controls.md)).
- **Minimer**: la forespørselsloggen være av med mindre du feilsøker en
  klient, hold `OPENCDE_DYNAMIC_CLIENT_REGISTRATION` av med mindre du trenger
  den, og publiser ikke databaseporten ([deploy/bolt.md](../deploy/bolt.md)).

## I Dataspatium

Appen lagrer serverens adresse, klient-id-en den har registrert, brukerens
tokens for sesjonen og en logg over kallene sine (med request-id-er) i
nettleseren; den lagrer aldri passordet. Hva av dette som forlater
nettleseren, og hvordan det tømmes, står på [Dataspatiums egen side om personopplysninger](https://github.com/marwiss/Dataspatium/blob/main/docs/nb/sakerhet.md).
