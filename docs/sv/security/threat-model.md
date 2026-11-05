# Hotmodell

Status: täcker etapperna 0–11. Varje etapp lägger till de tillgångar, hot och
kontroller den inför, `controls.md` avbildar varje kontroll på ett test, och
`asvs-checklist.md` dokumenterar självskattningen mot OWASP ASVS nivå 2.

## Tillgångar

| Tillgång | Var | Varför den är viktig |
|---|---|---|
| Användarnas inloggningsuppgifter (Argon2id-hashar) | grafen `User` | Ett kontoövertagande ger åtkomst till användarens alla projekt |
| OAuth2-klienthemligheter, koder, access- och refresh-tokens (SHA-256-hashar) | grafen `Client`, `AuthorizationCode`, `AccessToken`, `RefreshToken` | Imitation av användare eller klienter |
| Projektdata: ärenden, kommentarer, viewpoints, snapshots, dokumentmetadata | graf + lagring | Konfidentiell byggnadsinformation från flera organisationer |
| Dokument (IFC-modeller och andra filer) | lagringsbackend | Stor, konfidentiell, potentiellt skadlig indata till tolkar |
| Revisionslogg | grafen `AuditEvent` | Bevis efter en incident |
| Konfiguration och hemligheter | `.env`, Docker secrets | Fullständig kompromettering om de läcker |

## Aktörer

Anonym internetanvändare; autentiserad användare i ett annat projekt;
autentiserad användare i samma projekt med en lägre roll; en registrerad
OAuth2-klient (eller någon som innehar dess hemlighet); en administratör;
värdleverantören och vem som helst som kan läsa loggar eller säkerhetskopior;
en illvillig dokumentförfattare.

## Förtroendegränser

Internet → Caddy (TLS) → API → grafdatabas och lagring, allt på ett privat
nät. Webbläsaren (inloggning, samtycke, dokumentval, admin) är en egen gräns
skild från API-klienter som använder Bearer-tokens.

## Hot och kontroller (STRIDE, växer per etapp)

| Hot | Exempel | Kontroll | Etapp |
|---|---|---|---|
| Informationsläckage genom felsvar | Stackspår, ekad indata, interna id:n | En felkropp `{"message"}`; valideringsfel namnger fält, aldrig värden; 5xx loggas bara med request-id | 0 |
| Informationsläckage genom loggar | Tokens eller lösenord i loggrader | Maskeringsprocessor på varje logghändelse; inga begärande- eller svarskroppar loggas | 0 |
| Manipulation via för stora eller felformade kroppar | Minnesutmattning | Kroppsstorleksgräns före tolkning (413); strömning med byteräkning för uppladdningar | 0, 5 |
| Clickjacking, MIME-sniffning, referrer-läckor | Sidor inramade av en angripare; `code` läckt i Referer | CSP `frame-ancestors 'none'`, `X-Content-Type-Options`, `Referrer-Policy: no-referrer` på varje svar | 0 |
| Förfalskning av request-id | Logginjektion via `X-Request-ID` | Bara `[A-Za-z0-9._-]{1,128}` accepteras; annars myntas ett | 0 |
| Behörighetshöjning genom konfigurationsmisstag | http i produktion, tomt databaslösenord | Inställningarna vägrar starta | 0 |
| Leveranskedja | Komprometterat beroende eller action | `uv.lock`, pip-audit, Dependabot, actions pinnade med SHA, zizmor | 0 |
| Förfalskning av användare och klienter, replay, mix-up, CSRF på samtycke | | Bara PKCE S256, exakt redirect_uri, `state`, `iss`, engångskoder, hashade tokens, rotation med familjeåterkallning, CSRF-tokens | 2 |
| Bristande objektnivåbehörighet | Läsa ett annat projekts ärende via guid | Varje fråga startar i användarnoden och går via MEMBER_OF; 404 för främmande objekt | 3 |
| Injektion via OData | `$filter` konstruerat för att ändra Cypher | Parser → AST → vitlista → parametrar | 1, 3 |
| Lagrat innehåll förklätt till bild | HTML eller skript uppladdat som snapshot och serverat tillbaka | Magic bytes måste matcha den deklarerade typen; bilder serveras som `image/*` med `nosniff`; storlekstak före avkodning | 4 |
| Uppladdade filer renderade av en webbläsare | Lagrad XSS via en dokumentnedladdning | Dokument och snippets är alltid `application/octet-stream`-bilagor med sanerade, RFC 8187-kodade namn; renderas aldrig | 4, 5 |
| Kroppsstorleksgräns kringgången | Chunked transfer utan `Content-Length`; en binär rutt använd för JSON-floder | Bytes räknas när de kommer; bara de binära rutterna är undantagna och de räknas själva mot `max_upload_bytes` | 4 |
| Skadliga dokument | Zip-bomber, path traversal, exploits mot tolkar | Servergenererade id:n, storleksgränser, begränsad uppackning, tolkning i en sandlådad arbetsprocess | 5, 9 |
| Läckt Documents API-länk | `upload_ui_url` eller `select_documents_url` sedd i en logg, historik eller över skuldran | 256-bitars token lagrad hashad, 10 minuters giltighet, ett flöde, och sidan kräver dessutom en webbläsarsession som samma användare; API-sidans URL:er använder ett publikt id plus bearer-tokenen | 5 |
| Callback-missbruk | Servern förmås hämta en angripares URL (SSRF), öppen omdirigering via callbacken | Servern hämtar aldrig callbacken; bara http(s)-URL:er accepteras och webbläsaren omdirigeras med URL-kodade parametrar; callbacken har egen utgångstid | 5 |
| Ofullständiga eller för stora uppladdningar | Delar större än annonserat, summor som inte går ihop, övergivna delar som fyller disken | Exakt intervallkontroll per del, storlek verifierad vid sammansättning, SHA-256 registrerad, delar och sessioner går ut och städas med sina filer | 5 |
| Attacker mot webbläsarsessionen | Fixation, CSRF, stöld, behörighetshöjning | Slumpmässig hashad kaka myntad vid inloggning, `HttpOnly`, `SameSite=Strict`, `Secure` över https, inaktivitets- och absolut utgång, signerade formulärtokens plus `Sec-Fetch-Site`/`Origin`-kontroller, rollkontroller på varje sida | 5, 6 |
| Höjning till administratör | En medlem som når `/admin`; en stulen adminsession använd för återställningar eller hemlighetsrotation; en utelåst administratör | Adminrollen kontrolleras på varje adminrutt (annars HTML 404); farliga handlingar kräver administratörens eget lösenord igen; administratörer kan inte inaktivera, degradera eller ta bort sig själva; varje handling revideras | 6 |
| Hemligheter exponerade via gränssnittet | Klienthemligheter eller genererade lösenord läsbara senare | Visas en gång vid skapande eller rotation, lagras hashade; inställningssidan maskerar konfigurationshemligheter | 6 |
| Kompromettering genom driftsättningen | Databas nåbar från internet; hemligheter inbakade i avbildningen; privilegierad container; förfalskad `X-Forwarded-For` | Databasen bara på det privata compose-nätet; hemligheter från `.env` eller Docker secrets genererade av `opencde init`; icke-root, skrivskyddad container med borttagna capabilities; vidarebefordrade huvuden litas på bara från `OPENCDE_TRUSTED_PROXIES`; avbildningen skannad med en SBOM vid varje release | 8 |
| Säkerhetskopior som läcka eller förlust | Arkiv läsbart av andra; en återställning över live-data | Export på applikationsnivå till operatörens backupvolym (kryptering i vila är operatörens); `opencde restore` stoppar vid en icke-tom databas om inte tvingad; manifestet registrerar schemaversionen | 8 |
| Fientlig IFC-fil | Tolkkrasch, minnesutmattning, hängning, entitetsflod | Konvertering i en separat arbetsprocess med tids-, minnes- och entitetsgränser; ett misslyckande registreras på `IfcModel`-noden och servern påverkas inte; etiketter och relationsnamn valideras innan de når Cypher | 9 |
| Tredjepartskod på en serversida | Ett komprometterat CDN som serverar Swagger UI kör skript i serverns origin | Den interaktiva API-dokumentationen är avstängd i produktion om den inte slås på; den har en egen Content-Security-Policy som listar CDN:et; varje annan sida laddar bara resurser från samma origin; CORS gäller bara API-sökvägarna så att sidor aldrig är läsbara cross-origin | 11 |
| Föråldrad basavbildning | Åtgärdbara sårbarheter i distributionen eller i pips medföljande bibliotek | Körtidssteget tillämpar distributionens säkerhetsuppdateringar och tar bort pip; Trivy fäller releasen och den nattliga skanningen vid åtgärdbara HIGH- eller CRITICAL-fynd | 8, 11 |
| Självregistrerade publika klienter | Vem som helst registrerar en klient med ett övertygande namn och lockar användare att samtycka | Registreringen är avstängd som standard och hastighetsbegränsad; samtyckessidan namnger klienten och värden den omdirigerar till; publika klienter behöver PKCE och exakta redirect-URI:er som varje klient; administratörer kan inaktivera eller ta bort klienter i `/admin` | 11 |
| Begärandeloggen som lager för personuppgifter eller hemligheter | Frågesträngar med namn, tokens i huvuden, kroppar med ärendetexter | Avstängd som standard; posterna håller sökvägen utan frågesträng, inga huvuden och inga kroppar; lagringstiden begränsad av `request_log_retention_hours`; läsåtkomst bara för administratörer, på sidan via session och på `/admin/api/requests` via en bearer-token som bär det uttryckligen begärda scopet `admin` | 11 |
| Graffråge-endpointen som väg runt datamodellen | En administratörs Cypher läser hashar av inloggningsuppgifter, skriver, ändrar schemat eller lägger beslag på databasen | Avstängd som standard (`OPENCDE_GRAPH_QUERY_ENABLED`); bara administratörer med det uttryckligen begärda scopet `admin`; en lästransaktion plus avvisning av skrivande satsdelar och av varje procedur utom schemaprocedurerna (texten kontrolleras med strängar, kommentarer och namn i backticks borttagna, så Memgraph, som inte upprätthåller läsläget, täcks också); skyddade egenskaper avvisas i satsen och parametrarna, tas bort ur varje svar, Argon2-hashar maskeras; rad- och tidsgränser; varje anrop revideras med satsen, aldrig parametrarna | 11 |
