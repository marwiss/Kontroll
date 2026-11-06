# Trusselmodell

Status: dekker etappe 0–11. Hver etappe legger til aktivaene, truslene og
kontrollene den innfører, `controls.md` avbilder hver kontroll på en test, og
`asvs-checklist.md` dokumenterer selvvurderingen mot OWASP ASVS nivå 2.

## Aktiva

| Aktivum | Hvor | Hvorfor det er viktig |
|---|---|---|
| Brukernes påloggingsopplysninger (Argon2id-hasher) | grafen `User` | En kontoovertakelse gir tilgang til alle prosjektene til brukeren |
| OAuth2-klienthemmeligheter, koder, access- og refresh-tokens (SHA-256-hasher) | grafen `Client`, `AuthorizationCode`, `AccessToken`, `RefreshToken` | Etterligning av brukere eller klienter |
| Prosjektdata: saker, kommentarer, viewpoints, snapshots, dokumentmetadata | graf + lager | Konfidensiell bygningsinformasjon fra flere organisasjoner |
| Dokumenter (IFC-modeller og andre filer) | lagerbackend | Stor, konfidensiell, potensielt skadelig inndata til parsere |
| Revisjonslogg | grafen `AuditEvent` | Bevis etter en hendelse |
| Konfigurasjon og hemmeligheter | `.env`, Docker secrets | Full kompromittering hvis de lekker |

## Aktører

Anonym internettbruker; autentisert bruker av et annet prosjekt; autentisert
bruker av samme prosjekt med en lavere rolle; en registrert OAuth2-klient
(eller noen som har hemmeligheten dens); en administrator; hostingleverandøren
og enhver som kan lese logger eller sikkerhetskopier; en ondsinnet
dokumentforfatter.

## Tillitsgrenser

Internett → Caddy (TLS) → API → grafdatabase og lager, alt på et privat nett.
Nettleseren (innlogging, samtykke, dokumentvalg, admin) er en egen grense
atskilt fra API-klienter som bruker Bearer-tokens.

## Trusler og kontroller (STRIDE, vokser per etappe)

| Trussel | Eksempel | Kontroll | Etappe |
|---|---|---|---|
| Informasjonslekkasje gjennom feilsvar | Stakkspor, gjentatt inndata, interne id-er | Én feilkropp `{"message"}`; valideringsfeil navngir felt, aldri verdier; 5xx logges bare med request-id | 0 |
| Informasjonslekkasje gjennom logger | Tokens eller passord i logglinjer | Maskeringsprosessor på hver logghendelse; ingen forespørsels- eller svarkropper logges | 0 |
| Manipulering via for store eller misdannede kropper | Minneuttømming | Kroppsstørrelsesgrense før parsing (413); strømming med bytetelling for opplastinger | 0, 5 |
| Clickjacking, MIME-sniffing, referrer-lekkasjer | Sider rammet inn av en angriper; `code` lekket i Referer | CSP `frame-ancestors 'none'`, `X-Content-Type-Options`, `Referrer-Policy: no-referrer` på hvert svar | 0 |
| Forfalskning av request-id | Logginjeksjon gjennom `X-Request-ID` | Bare `[A-Za-z0-9._-]{1,128}` godtas; ellers lages en ny | 0 |
| Rettighetseskalering gjennom konfigurasjonsfeil | http i produksjon, tomt databasepassord | Innstillingene nekter å starte | 0 |
| Forsyningskjede | Kompromittert avhengighet eller action | `uv.lock`, pip-audit, Dependabot, actions festet med SHA, zizmor | 0 |
| Forfalskning av brukere og klienter, replay, mix-up, CSRF på samtykke | | Bare PKCE S256, nøyaktig redirect_uri, `state`, `iss`, engangskoder, hashede tokens, rotasjon med familietilbaketrekking, CSRF-tokens | 2 |
| Brutt autorisasjon på objektnivå | Lese et annet prosjekts sak via guid | Hver spørring starter i brukernoden og går via MEMBER_OF; 404 for fremmede objekter | 3 |
| Injeksjon gjennom OData | `$filter` laget for å endre Cypher | Parser → AST → hvitliste → parametere | 1, 3 |
| Lagret innhold forkledd som bilde | HTML eller skript lastet opp som snapshot og servert tilbake | Magic bytes må matche den deklarerte typen; bilder serveres som `image/*` med `nosniff`; størrelsestak før dekoding | 4 |
| Opplastede filer gjengitt av en nettleser | Lagret XSS gjennom en dokumentnedlasting | Dokumenter og snippets er alltid `application/octet-stream`-vedlegg med sanerte, RFC 8187-kodede navn; gjengis aldri | 4, 5 |
| Kroppsstørrelsesgrense omgått | Chunked transfer uten `Content-Length`; en binær rute brukt til JSON-flommer | Bytes telles når de kommer; bare de binære rutene er unntatt, og de teller selv mot `max_upload_bytes` | 4 |
| Ondsinnede dokumenter | Zip-bomber, path traversal, parser-exploits | Servergenererte id-er, størrelsesgrenser, begrenset utpakking, parsing i en sandkasset arbeidsprosess | 5, 9 |
| Lekket Documents API-lenke | `upload_ui_url` eller `select_documents_url` sett i en logg, historikk eller over skulderen | 256-bits token lagret hashet, 10 minutters gyldighet, én flyt, og siden krever dessuten en nettlesersesjon som samme bruker; API-sidens URL-er bruker en offentlig id pluss bearer-tokenet | 5 |
| Callback-misbruk | Serveren fås til å hente en angripers URL (SSRF), åpen omdirigering gjennom callbacken | Serveren henter aldri callbacken; bare http(s)-URL-er godtas, og nettleseren omdirigeres med URL-kodede parametere; callbacken har sin egen utløpstid | 5 |
| Ufullstendige eller for store opplastinger | Deler større enn annonsert, summer som ikke stemmer, forlatte deler som fyller disken | Nøyaktig intervallkontroll per del, størrelse verifisert ved sammensetting, SHA-256 registrert, deler og sesjoner utløper og ryddes med filene sine | 5 |
| Angrep på nettlesersesjonen | Fiksering, CSRF, tyveri, rettighetseskalering | Tilfeldig hashet cookie laget ved innlogging, `HttpOnly`, `SameSite=Strict`, `Secure` over https, inaktivitets- og absolutt utløp, signerte skjematokens pluss `Sec-Fetch-Site`/`Origin`-kontroller, rollekontroller på hver side | 5, 6 |
| Eskalering til administrator | Et medlem som når `/admin`; en stjålet adminsesjon brukt til tilbakestillinger eller hemmelighetsrotasjon; en utestengt administrator | Adminrollen kontrolleres på hver adminrute (ellers HTML 404); farlige handlinger krever administratorens eget passord igjen; administratorer kan ikke deaktivere, degradere eller slette seg selv; hver handling revideres | 6 |
| Hemmeligheter eksponert gjennom UI-et | Klienthemmeligheter eller genererte passord lesbare senere | Vises én gang ved opprettelse eller rotasjon, lagres hashet; innstillingssiden maskerer konfigurasjonshemmeligheter | 6 |
| Kompromittering gjennom utrullingen | Database tilgjengelig fra internett; hemmeligheter bakt inn i imaget; privilegert container; forfalsket `X-Forwarded-For` | Databasen bare på det private compose-nettet; hemmeligheter fra `.env` eller Docker secrets generert av `opencde init`; ikke-root, skrivebeskyttet container med fjernede capabilities; videresendte headere stoles på bare fra `OPENCDE_TRUSTED_PROXIES`; imaget skannet med en SBOM ved hver release | 8 |
| Sikkerhetskopier som lekkasje eller tap | Arkiv lesbart for andre; en gjenoppretting over live-data | Eksport på applikasjonsnivå til operatørens backupvolum (kryptering i ro er operatørens); `opencde restore` stopper ved en ikke-tom database med mindre det tvinges; manifestet registrerer skjemaversjonen | 8 |
| Fiendtlig IFC-fil | Parser-krasj, minneuttømming, henging, entitetsflom | Konvertering i en separat arbeidsprosess med tids-, minne- og entitetsgrenser; en feil registreres på `IfcModel`-noden, og serveren påvirkes ikke; etiketter og relasjonsnavn valideres før de når Cypher | 9 |
| Tredjepartskode på en serverside | Et kompromittert CDN som serverer Swagger UI, kjører skript i serverens origin | Den interaktive API-dokumentasjonen er av i produksjon med mindre den slås på; den har sin egen Content-Security-Policy som lister CDN-et; alle andre sider laster bare same-origin-ressurser; CORS gjelder bare API-stiene, slik at sider aldri kan leses cross-origin | 11 |
| Foreldet basisimage | Utbedrbare sårbarheter i distribusjonen eller i pips medfølgende biblioteker | Kjøretidstrinnet anvender distribusjonens sikkerhetsoppdateringer og fjerner pip; Trivy feller releasen og den nattlige skanningen ved utbedrbare HIGH- eller CRITICAL-funn | 8, 11 |
| Selvregistrerte offentlige klienter | Hvem som helst registrerer en klient med et overbevisende navn og lokker brukere til å samtykke | Registrering er av som standard og hastighetsbegrenset; samtykkesiden navngir klienten og verten den omdirigerer til; offentlige klienter trenger PKCE og nøyaktige redirect-URI-er som enhver klient; administratorer kan deaktivere eller slette klienter i `/admin` | 11 |
| En klient merket for å logge inn uten PKCE | En stjålet kode løses inn, eller en forespørsel med PKCE overtales til å være uten | Merkingen er en administrators valg eller følger, når selvregistrering er på, med registrering på adressen til BCF API 2.1; bare en konfidensiell klient kan ha den, så en stjålet kode er verdiløs uten hemmeligheten; en verifier for en kode uten challenge avvises; en redirect-URI som oppgis i forespørselen, må oppgis igjen; revisjonsloggen sier når PKCE ble utelatt | 2 |
| Forespørselsloggen som lager for personopplysninger eller hemmeligheter | Spørrestrenger med navn, tokens i headere, kropper med sakstekster | Av som standard; postene holder stien uten spørrestreng, ingen headere og ingen kropper; oppbevaring begrenset av `request_log_retention_hours`; lesetilgang bare for administratorer, på siden via sesjon og på `/admin/api/requests` via et bearer-token som bærer det eksplisitt forespurte scopet `admin` | 11 |
| Grafspørringsendepunktet som vei rundt datamodellen | En administrators Cypher leser hasher av påloggingsopplysninger, skriver, endrer skjemaet eller legger beslag på databasen | Av som standard (`OPENCDE_GRAPH_QUERY_ENABLED`); bare administratorer med det eksplisitt forespurte scopet `admin`; en lesetransaksjon pluss avvisning av skrivende klausuler og av enhver prosedyre bortsett fra skjemaprosedyrene (teksten kontrolleres med strenger, kommentarer og navn i backticks fjernet, slik at Memgraph, som ikke håndhever lesemodus, også er dekket); beskyttede egenskaper avvises i setningen og parameterne, fjernes fra hvert svar, Argon2-hasher maskeres; rad- og tidsgrenser; hvert kall revideres med setningen, aldri parameterne | 11 |
