# Trusselsmodel

Status: dækker etape 0–11. Hver etape tilføjer de aktiver, trusler og
kontroller, den indfører, `controls.md` afbilder hver kontrol på en test, og
`asvs-checklist.md` dokumenterer selvevalueringen mod OWASP ASVS niveau 2.

## Aktiver

| Aktiv | Hvor | Hvorfor det er vigtigt |
|---|---|---|
| Brugernes legitimationsoplysninger (Argon2id-hashes) | grafen `User` | En kontoovertagelse giver adgang til alle brugerens projekter |
| OAuth2-klienthemmeligheder, koder, access- og refresh-tokens (SHA-256-hashes) | grafen `Client`, `AuthorizationCode`, `AccessToken`, `RefreshToken` | Efterligning af brugere eller klienter |
| Projektdata: sager, kommentarer, viewpoints, snapshots, dokumentmetadata | graf + lager | Fortrolig bygningsinformation fra flere organisationer |
| Dokumenter (IFC-modeller og andre filer) | lagerbackend | Stort, fortroligt, potentielt skadeligt input til parsere |
| Revisionslog | grafen `AuditEvent` | Bevis efter en hændelse |
| Konfiguration og hemmeligheder | `.env`, Docker secrets | Fuld kompromittering, hvis de lækker |

## Aktører

Anonym internetbruger; autentificeret bruger af et andet projekt;
autentificeret bruger af samme projekt med en lavere rolle; en registreret
OAuth2-klient (eller nogen, der har dens hemmelighed); en administrator;
hostingudbyderen og enhver, der kan læse logs eller sikkerhedskopier; en
ondsindet dokumentforfatter.

## Tillidsgrænser

Internet → Caddy (TLS) → API → grafdatabase og lager, alt på et privat
netværk. Browseren (login, samtykke, dokumentvalg, admin) er en separat
grænse i forhold til API-klienter, der bruger Bearer-tokens.

## Trusler og kontroller (STRIDE, vokser per etape)

| Trussel | Eksempel | Kontrol | Etape |
|---|---|---|---|
| Informationslækage gennem fejlsvar | Stakspor, gentaget input, interne id'er | Én fejlkrop `{"message"}`; valideringsfejl nævner felter, aldrig værdier; 5xx logges kun med request-id | 0 |
| Informationslækage gennem logs | Tokens eller kodeord i loglinjer | Maskeringsprocessor på hver loghændelse; ingen forespørgsels- eller svarkroppe logges | 0 |
| Manipulation via for store eller misdannede kroppe | Hukommelsesudtømning | Kropsstørrelsesgrænse før parsing (413); streaming med bytetælling for uploads | 0, 5 |
| Clickjacking, MIME-sniffing, referrer-læk | Sider indrammet af en angriber; `code` lækket i Referer | CSP `frame-ancestors 'none'`, `X-Content-Type-Options`, `Referrer-Policy: no-referrer` på hvert svar | 0 |
| Forfalskning af request-id | Loginjektion gennem `X-Request-ID` | Kun `[A-Za-z0-9._-]{1,128}` accepteres; ellers laves et nyt | 0 |
| Rettighedseskalering gennem konfigurationsfejl | http i produktion, tomt databasekodeord | Indstillingerne nægter at starte | 0 |
| Forsyningskæde | Kompromitteret afhængighed eller action | `uv.lock`, pip-audit, Dependabot, actions fastgjort med SHA, zizmor | 0 |
| Forfalskning af brugere og klienter, replay, mix-up, CSRF på samtykke | | Kun PKCE S256, nøjagtig redirect_uri, `state`, `iss`, engangskoder, hashede tokens, rotation med familietilbagekaldelse, CSRF-tokens | 2 |
| Brudt autorisation på objektniveau | Læse et andet projekts sag via guid | Hver forespørgsel starter i brugernoden og går via MEMBER_OF; 404 for fremmede objekter | 3 |
| Injektion gennem OData | `$filter` konstrueret til at ændre Cypher | Parser → AST → hvidliste → parametre | 1, 3 |
| Gemt indhold forklædt som billede | HTML eller script uploadet som snapshot og serveret tilbage | Magic bytes skal matche den deklarerede type; billeder serveres som `image/*` med `nosniff`; størrelsesloft før dekodning | 4 |
| Uploadede filer renderet af en browser | Gemt XSS gennem en dokumentdownload | Dokumenter og snippets er altid `application/octet-stream`-vedhæftninger med sanerede, RFC 8187-kodede navne; renderes aldrig | 4, 5 |
| Kropsstørrelsesgrænse omgået | Chunked transfer uden `Content-Length`; en binær rute brugt til JSON-oversvømmelser | Bytes tælles, når de ankommer; kun de binære ruter er undtaget, og de tæller selv mod `max_upload_bytes` | 4 |
| Ondsindede dokumenter | Zip-bomber, path traversal, parser-exploits | Servergenererede id'er, størrelsesgrænser, begrænset udpakning, parsing i en sandboxet arbejdsproces | 5, 9 |
| Lækket Documents API-link | `upload_ui_url` eller `select_documents_url` set i en log, historik eller over skulderen | 256-bit token gemt hashet, 10 minutters gyldighed, ét forløb, og siden kræver desuden en browsersession som samme bruger; API-sidens URL'er bruger et offentligt id plus bearer-tokenen | 5 |
| Callback-misbrug | Serveren bragt til at hente en angribers URL (SSRF), åben omdirigering gennem callbacken | Serveren henter aldrig callbacken; kun http(s)-URL'er accepteres, og browseren omdirigeres med URL-kodede parametre; callbacken har sin egen udløbstid | 5 |
| Ufuldstændige eller for store uploads | Dele større end annonceret, summer, der ikke stemmer, forladte dele, der fylder disken | Nøjagtig intervalkontrol per del, størrelse verificeret ved samling, SHA-256 registreret, dele og sessioner udløber og ryddes med deres filer | 5 |
| Angreb på browsersessionen | Fixation, CSRF, tyveri, rettighedseskalering | Tilfældig hashet cookie lavet ved login, `HttpOnly`, `SameSite=Strict`, `Secure` over https, inaktivitets- og absolut udløb, signerede formulartokens plus `Sec-Fetch-Site`/`Origin`-kontroller, rollekontroller på hver side | 5, 6 |
| Eskalering til administrator | Et medlem, der når `/admin`; en stjålet adminsession brugt til nulstillinger eller hemmelighedsrotation; en udelukket administrator | Adminrollen kontrolleres på hver adminrute (ellers HTML 404); farlige handlinger kræver administratorens eget kodeord igen; administratorer kan ikke deaktivere, degradere eller slette sig selv; hver handling revideres | 6 |
| Hemmeligheder eksponeret gennem UI'et | Klienthemmeligheder eller genererede kodeord læsbare senere | Vises én gang ved oprettelse eller rotation, gemmes hashede; indstillingssiden maskerer konfigurationshemmeligheder | 6 |
| Kompromittering gennem udrulningen | Database tilgængelig fra internettet; hemmeligheder bagt ind i imaget; privilegeret container; forfalsket `X-Forwarded-For` | Databasen kun på det private compose-netværk; hemmeligheder fra `.env` eller Docker secrets genereret af `opencde init`; ikke-root, skrivebeskyttet container med fjernede capabilities; videresendte headere stoles kun på fra `OPENCDE_TRUSTED_PROXIES`; imaget scannet med en SBOM ved hver release | 8 |
| Sikkerhedskopier som læk eller tab | Arkiv læsbart af andre; en gendannelse over live-data | Eksport på applikationsniveau til operatørens backupvolumen (kryptering i hvile er operatørens); `opencde restore` stopper ved en ikke-tom database, medmindre det tvinges; manifestet registrerer skemaversionen | 8 |
| Fjendtlig IFC-fil | Parser-nedbrud, hukommelsesudtømning, hængning, entitetsoversvømmelse | Konvertering i en separat arbejdsproces med tids-, hukommelses- og entitetsgrænser; en fejl registreres på `IfcModel`-noden, og serveren påvirkes ikke; labels og relationsnavne valideres, før de når Cypher | 9 |
| Tredjepartskode på en serverside | Et kompromitteret CDN, der serverer Swagger UI, kører script i serverens origin | Den interaktive API-dokumentation er slået fra i produktion, medmindre den slås til; den har sin egen Content-Security-Policy, der lister CDN'et; alle andre sider indlæser kun same-origin-ressourcer; CORS gælder kun API-stierne, så sider aldrig kan læses cross-origin | 11 |
| Forældet basisimage | Rettelige sårbarheder i distributionen eller i pips medfølgende biblioteker | Runtime-trinnet anvender distributionens sikkerhedsopdateringer og fjerner pip; Trivy fælder releasen og den natlige scanning ved rettelige HIGH- eller CRITICAL-fund | 8, 11 |
| Selvregistrerede offentlige klienter | Enhver registrerer en klient med et overbevisende navn og lokker brugere til at give samtykke | Registrering er slået fra som standard og hastighedsbegrænset; samtykkesiden nævner klienten og den vært, den omdirigerer til; offentlige klienter kræver PKCE og nøjagtige redirect-URI'er som enhver klient; administratorer kan deaktivere eller slette klienter i `/admin` | 11 |
| En klient markeret til at logge ind uden PKCE | En stjålet kode indløses, eller en forespørgsel med PKCE overtales til at undvære det | Markeringen er en administrators valg eller følger, når selvregistrering er slået til, med registrering på adressen til BCF API 2.1; kun en fortrolig klient kan have den, så en stjålet kode er værdiløs uden hemmeligheden; en verifier til en kode uden challenge afvises; en redirect-URI, der angives i forespørgslen, skal angives igen; revisionsloggen fortæller, hvornår PKCE blev udeladt | 2 |
| Forespørgselsloggen som lager for personoplysninger eller hemmeligheder | Forespørgselsstrenge med navne, tokens i headere, kroppe med sagstekster | Slået fra som standard; posterne holder stien uden forespørgselsstreng, ingen headere og ingen kroppe; opbevaring begrænset af `request_log_retention_hours`; læseadgang kun for administratorer, på siden via session og på `/admin/api/requests` via en bearer-token, der bærer det udtrykkeligt anmodede scope `admin` | 11 |
| Grafforespørgselsendepunktet som vej uden om datamodellen | En administrators Cypher læser hashes af legitimationsoplysninger, skriver, ændrer skemaet eller beslaglægger databasen | Slået fra som standard (`OPENCDE_GRAPH_QUERY_ENABLED`); kun administratorer med det udtrykkeligt anmodede scope `admin`; en læsetransaktion plus afvisning af skrivende klausuler og af enhver procedure bortset fra skemaprocedurerne (teksten kontrolleres med strenge, kommentarer og navne i backticks fjernet, så Memgraph, som ikke håndhæver læsetilstanden, også er dækket); beskyttede egenskaber afvises i udsagnet og parametrene, fjernes fra hvert svar, Argon2-hashes maskeres; række- og tidsgrænser; hvert kald revideres med udsagnet, aldrig parametrene | 11 |
