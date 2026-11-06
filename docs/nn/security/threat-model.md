# Trugsmålsmodell

Status: dekkjer etappe 0–11. Kvar etappe legg til aktivaa, trugsmåla og
kontrollane han innfører, `controls.md` avbildar kvar kontroll på ein test, og
`asvs-checklist.md` dokumenterer sjølvvurderinga mot OWASP ASVS nivå 2.

## Aktiva

| Aktivum | Kvar | Kvifor det er viktig |
|---|---|---|
| Påloggingsopplysningane til brukarane (Argon2id-hashar) | grafen `User` | Ei kontoovertaking gjev tilgang til alle prosjekta til brukaren |
| OAuth2-klientløyndomar, kodar, access- og refresh-tokens (SHA-256-hashar) | grafen `Client`, `AuthorizationCode`, `AccessToken`, `RefreshToken` | Etterlikning av brukarar eller klientar |
| Prosjektdata: saker, kommentarar, viewpoints, snapshots, dokumentmetadata | graf + lager | Konfidensiell bygningsinformasjon frå fleire organisasjonar |
| Dokument (IFC-modellar og andre filer) | lagerbackend | Stor, konfidensiell, potensielt skadeleg inndata til parsarar |
| Revisjonslogg | grafen `AuditEvent` | Bevis etter ei hending |
| Konfigurasjon og løyndomar | `.env`, Docker secrets | Full kompromittering om dei lek |

## Aktørar

Anonym internettbrukar; autentisert brukar av eit anna prosjekt; autentisert
brukar av same prosjekt med ei lågare rolle; ein registrert OAuth2-klient
(eller nokon som har løyndomen hans); ein administrator; hostingleverandøren
og kven som helst som kan lese loggar eller tryggingskopiar; ein vondsinna
dokumentforfattar.

## Tillitsgrenser

Internett → Caddy (TLS) → API → grafdatabase og lager, alt på eit privat nett.
Nettlesaren (innlogging, samtykke, dokumentval, admin) er ei eiga grense
skild frå API-klientar som brukar Bearer-tokens.

## Trugsmål og kontrollar (STRIDE, veks per etappe)

| Trugsmål | Døme | Kontroll | Etappe |
|---|---|---|---|
| Informasjonslekkasje gjennom feilsvar | Stakkspor, attgjeven inndata, interne id-ar | Éin feilkropp `{"message"}`; valideringsfeil namngjev felt, aldri verdiar; 5xx blir logga berre med request-id | 0 |
| Informasjonslekkasje gjennom loggar | Tokens eller passord i logglinjer | Maskeringsprosessor på kvar logghending; ingen førespurnads- eller svarkroppar blir logga | 0 |
| Manipulering via for store eller misdanna kroppar | Minneuttømming | Kroppsstorleiksgrense før parsing (413); strøyming med byteteljing for opplastingar | 0, 5 |
| Clickjacking, MIME-sniffing, referrer-lekkasjar | Sider ramma inn av ein angripar; `code` lekt i Referer | CSP `frame-ancestors 'none'`, `X-Content-Type-Options`, `Referrer-Policy: no-referrer` på kvart svar | 0 |
| Forfalsking av request-id | Logginjeksjon gjennom `X-Request-ID` | Berre `[A-Za-z0-9._-]{1,128}` blir godteke; elles blir ein ny laga | 0 |
| Rettseskalering gjennom konfigurasjonsfeil | http i produksjon, tomt databasepassord | Innstillingane nektar å starte | 0 |
| Leveransekjede | Kompromittert avhengnad eller action | `uv.lock`, pip-audit, Dependabot, actions festa med SHA, zizmor | 0 |
| Forfalsking av brukarar og klientar, replay, mix-up, CSRF på samtykke | | Berre PKCE S256, nøyaktig redirect_uri, `state`, `iss`, eingongskodar, hasha tokens, rotasjon med familietilbaketrekking, CSRF-tokens | 2 |
| Broten autorisasjon på objektnivå | Lese saka til eit anna prosjekt via guid | Kvar spørjing startar i brukarnoden og går via MEMBER_OF; 404 for framande objekt | 3 |
| Injeksjon gjennom OData | `$filter` laga for å endre Cypher | Parsar → AST → kvitliste → parametrar | 1, 3 |
| Lagra innhald forkledd som bilete | HTML eller skript lasta opp som snapshot og servert tilbake | Magic bytes må matche den deklarerte typen; bilete blir serverte som `image/*` med `nosniff`; storleikstak før dekoding | 4 |
| Opplasta filer teikna av ein nettlesar | Lagra XSS gjennom ei dokumentnedlasting | Dokument og snippets er alltid `application/octet-stream`-vedlegg med sanerte, RFC 8187-koda namn; blir aldri teikna | 4, 5 |
| Kroppsstorleiksgrense omgått | Chunked transfer utan `Content-Length`; ei binær rute brukt til JSON-flaumar | Bytes blir telde når dei kjem; berre dei binære rutene er unnatekne, og dei tel sjølve mot `max_upload_bytes` | 4 |
| Vondsinna dokument | Zip-bomber, path traversal, parsar-exploits | Servergenererte id-ar, storleiksgrenser, avgrensa utpakking, parsing i ein sandkassa arbeidsprosess | 5, 9 |
| Lekt Documents API-lenkje | `upload_ui_url` eller `select_documents_url` sett i ein logg, historikk eller over skuldra | 256-bits token lagra hasha, 10 minutt gyldig, éin flyt, og sida krev dessutan ein nettlesarsesjon som same brukar; URL-ane på API-sida brukar ein offentleg id pluss bearer-tokenet | 5 |
| Callback-misbruk | Serveren blir fått til å hente URL-en til ein angripar (SSRF), open omdirigering gjennom callbacken | Serveren hentar aldri callbacken; berre http(s)-URL-ar blir godtekne, og nettlesaren blir omdirigert med URL-koda parametrar; callbacken har si eiga utgangstid | 5 |
| Ufullstendige eller for store opplastingar | Delar større enn annonsert, summar som ikkje stemmer, forlatne delar som fyller disken | Nøyaktig intervallkontroll per del, storleik verifisert ved samansetjing, SHA-256 registrert, delar og sesjonar går ut og blir rydda med filene sine | 5 |
| Angrep på nettlesarsesjonen | Fiksering, CSRF, tjuveri, rettseskalering | Tilfeldig hasha cookie laga ved innlogging, `HttpOnly`, `SameSite=Strict`, `Secure` over https, inaktivitets- og absolutt utgang, signerte skjematokens pluss `Sec-Fetch-Site`/`Origin`-kontrollar, rollekontrollar på kvar side | 5, 6 |
| Eskalering til administrator | Ein medlem som når `/admin`; ein stolen adminsesjon brukt til tilbakestillingar eller løyndomsrotasjon; ein utestengd administrator | Adminrolla blir kontrollert på kvar adminrute (elles HTML 404); farlege handlingar krev administratoren sitt eige passord igjen; administratorar kan ikkje deaktivere, degradere eller slette seg sjølve; kvar handling blir revidert | 6 |
| Løyndomar eksponerte gjennom UI-et | Klientløyndomar eller genererte passord lesbare seinare | Blir viste éin gong ved oppretting eller rotasjon, lagra hasha; innstillingssida maskerer konfigurasjonsløyndomar | 6 |
| Kompromittering gjennom utrullinga | Database tilgjengeleg frå internett; løyndomar baka inn i imaget; privilegert container; forfalska `X-Forwarded-For` | Databasen berre på det private compose-nettet; løyndomar frå `.env` eller Docker secrets genererte av `opencde init`; ikkje-root, skriveverna container med fjerna capabilities; vidaresende headerar blir stolte på berre frå `OPENCDE_TRUSTED_PROXIES`; imaget skanna med ein SBOM ved kvar release | 8 |
| Tryggingskopiar som lekkasje eller tap | Arkiv lesbart for andre; ei gjenoppretting over live-data | Eksport på applikasjonsnivå til backupvolumet til operatøren (kryptering i ro er operatøren sitt); `opencde restore` stoppar ved ein ikkje-tom database om det ikkje blir tvinga; manifestet registrerer skjemaversjonen | 8 |
| Fiendtleg IFC-fil | Parsar-krasj, minneuttømming, henging, entitetsflaum | Konvertering i ein separat arbeidsprosess med tids-, minne- og entitetsgrenser; ein feil blir registrert på `IfcModel`-noden, og serveren blir ikkje påverka; etikettar og relasjonsnamn blir validerte før dei når Cypher | 9 |
| Tredjepartskode på ei serverside | Eit kompromittert CDN som serverer Swagger UI, køyrer skript i origin til serveren | Den interaktive API-dokumentasjonen er av i produksjon om ho ikkje blir slått på; ho har sin eigen Content-Security-Policy som listar CDN-et; alle andre sider lastar berre same-origin-ressursar; CORS gjeld berre API-stiane, slik at sider aldri kan lesast cross-origin | 11 |
| Forelda basisimage | Utbetringsbare sårbarheiter i distribusjonen eller i dei medfølgjande biblioteka til pip | Køyretidssteget nyttar tryggingsoppdateringane frå distribusjonen og fjernar pip; Trivy feller releasen og den nattlege skanninga ved utbetringsbare HIGH- eller CRITICAL-funn | 8, 11 |
| Sjølvregistrerte offentlege klientar | Kven som helst registrerer ein klient med eit overtydande namn og lokkar brukarar til å samtykkje | Registrering er av som standard og takstavgrensa; samtykkesida namngjev klienten og verten han omdirigerer til; offentlege klientar treng PKCE og nøyaktige redirect-URI-ar som kvar klient; administratorar kan deaktivere eller slette klientar i `/admin` | 11 |
| Ein klient merkt for å logge inn utan PKCE | Ein stolen kode blir løyst inn, eller ein førespurnad med PKCE blir overtalt til å vere utan | Merkinga er valet til ein administrator eller følgjer, når sjølvregistrering er på, med registrering på adressa til BCF API 2.1; berre ein konfidensiell klient kan ha henne, så ein stolen kode er verdilaus utan løyndomen; ein verifier for ein kode utan challenge blir avvist; ein redirect-URI som blir oppgitt i førespurnaden, må oppgjevast igjen; revisjonsloggen seier når PKCE vart utelaten | 2 |
| Førespurnadsloggen som lager for personopplysningar eller løyndomar | Spørjestrengar med namn, tokens i headerar, kroppar med sakstekstar | Av som standard; postane held stien utan spørjestreng, ingen headerar og ingen kroppar; lagringstid avgrensa av `request_log_retention_hours`; lesetilgang berre for administratorar, på sida via sesjon og på `/admin/api/requests` via eit bearer-token som ber det eksplisitt førespurde scopet `admin` | 11 |
| Grafspørjingsendepunktet som veg rundt datamodellen | Cypher frå ein administrator les hashar av påloggingsopplysningar, skriv, endrar skjemaet eller legg beslag på databasen | Av som standard (`OPENCDE_GRAPH_QUERY_ENABLED`); berre administratorar med det eksplisitt førespurde scopet `admin`; ein lesetransaksjon pluss avvising av skrivande klausular og av kvar prosedyre bortsett frå skjemaprosedyrane (teksten blir kontrollert med strengar, kommentarar og namn i backticks fjerna, slik at Memgraph, som ikkje handhevar lesemodus, òg er dekt); verna eigenskapar blir avviste i setninga og parametrane, fjerna frå kvart svar, Argon2-hashar maskerte; rad- og tidsgrenser; kvart kall blir revidert med setninga, aldri parametrane | 11 |
