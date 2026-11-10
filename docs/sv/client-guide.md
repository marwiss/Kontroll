# Bygga en klient

Hur en applikation talar med den här servern (eller vilken OpenCDE-server som
helst). Python-biblioteket i [client/](../../client/) gör allt detta; exemplen
i [examples/](../examples/) visar det i bruk.

## 1. Upptäck

`GET /foundation/versions` listar API:erna (`foundation 1.0`, `bcf 3.0`, `bcf 2.1`,
`documents 1.0`). `GET /foundation/1.0/auth` talar om var man loggar in:

```json
{
  "oauth2_auth_url": "https://cde.example/foundation/oauth2/auth",
  "oauth2_token_url": "https://cde.example/foundation/oauth2/token",
  "oauth2_revocation_url": "https://cde.example/foundation/oauth2/revoke",
  "http_basic_supported": false,
  "supported_oauth2_flows": ["authorization_code_grant"],
  "oauth2_pkce_methods": ["S256"],
  "oauth2_pkce_required": true
}
```

En server kan ställas in så att den bara erbjuder några av dem (`OPENCDE_APIS`).
Då innehåller listorna bara det den erbjuder, och ett API som den inte erbjuder
svarar 404. En server för bara BCF API 2.1 har inget Foundation API: en klient
hittar den genom `GET /bcf/versions` och loggar in genom `GET /bcf/2.1/auth`. En
dokumentserver erbjuder Foundation API och Documents API men ingen BCF.

### Kapabilitetsdokumentet (tillägg)

Utöver specifikationerna säger `GET /.well-known/dataregium` (ingen
autentisering, CORS som för API:t, cachebart i fem minuter) vilka tillägg den
här servern har slagit på och vilka gränser som gäller, så att en klient
anpassar sig i stället för att prova sig fram:

```json
{
  "server": {"name": "Dataregium OpenCDE server", "version": "2.0.0", "public_url": "https://cde.example.org"},
  "apis": {"foundation": "1.0", "bcf": "3.0", "documents": "1.0"},
  "scopes": ["profile", "bcf", "documents", "admin"],
  "extensions": {
    "dynamic_client_registration": {"enabled": true, "public_clients": true, "initial_access_token": false, "approval": false, "unused_days": 30,
                                    "url": "/foundation/oauth2/reg"},
    "request_log": {"enabled": true, "retention_hours": 72, "url": "/admin/api/requests"},
    "admin_api": {"enabled": true, "version": 1, "url": "/admin/api", "scope": "admin"},
    "ifcgraph": {"enabled": true, "bolt": null},
    "graph_query": {"enabled": true, "url": "/admin/api/graph/query", "max_rows": 1000, "timeout_seconds": 10.0}
  },
  "limits": {"max_upload_bytes": 1073741824, "max_image_bytes": 10485760, "access_token_ttl_seconds": 3600},
  "links": {"dataspatium": null}
}
```

Ett `404` betyder en server utan tillägg (en annan OpenCDE-server, eller en
äldre Dataregium). Behandla okända nycklar som om de saknades. `ifcgraph.bolt`
är satt bara när operatören avsiktligt har publicerat grafdatabasen
(`OPENCDE_GRAPH_PUBLIC_BOLT_URL`); `graph_query` är på bara när operatören
har satt `OPENCDE_GRAPH_QUERY_ENABLED` (§7); `links.dataspatium` bär
adressen till en Dataspatium-installation när operatören har satt
`OPENCDE_DATASPATIUM_URL`. Ingenting i dokumentet är hemligt.

## 2. Logga in (OAuth2 authorization code med PKCE)

1. Be serverns administratör registrera din applikation: en **publik** klient
   för skrivbords-, mobil- och webbläsarappar (ingen hemlighet, PKCE), eller
   en **konfidentiell** klient för en serverapplikation (hemligheten visas en
   gång). Registrera den exakta redirect-URI:n; för inbyggda appar accepteras
   `http://127.0.0.1/…` (valfri port).
2. Generera en `code_verifier` (43–128 URL-säkra tecken) och dess
   `code_challenge = BASE64URL(SHA256(verifier))`, samt ett slumpmässigt
   `state`.
3. Öppna `oauth2_auth_url?response_type=code&client_id=…&redirect_uri=…&scope=profile bcf documents&state=…&code_challenge=…&code_challenge_method=S256`
   i användarens webbläsare. Användaren loggar in och ger sitt samtycke.
4. Webbläsaren omdirigeras till din `redirect_uri` med `code`, `state` och
   `iss`. Kontrollera `state`; kontrollera att `iss` är servern.
5. `POST oauth2_token_url` med `grant_type=authorization_code`, `code`,
   `code_verifier`, `redirect_uri` och `client_id` (publik) eller HTTP
   Basic-autentisering (konfidentiell). Svaret är `201` med `access_token`,
   `refresh_token`, `expires_in`, `scope`.
6. Skicka `Authorization: Bearer <access_token>` med varje API-anrop. När den
   går ut, `POST oauth2_token_url` med `grant_type=refresh_token`;
   refresh-tokenen roterar, så spara den nya. Att återanvända en gammal
   refresh-token återkallar hela familjen: det är servern som upptäcker en
   stulen token.
7. `POST oauth2_revocation_url` med refresh-tokenen när användaren loggar ut.

Servern stöder aldrig implicit- eller password-grant.

### Registrera en klient dynamiskt

När servern körs med `OPENCDE_DYNAMIC_CLIENT_REGISTRATION=true` bär
`GET /foundation/1.0/auth` `oauth2_dynamic_client_reg_url` och en klient kan
registrera sig själv (Foundation API 2.2.3, RFC 7591). En webbläsar- eller
inbyggd applikation begär en publik klient:

```http
POST /foundation/oauth2/reg
Content-Type: application/json

{"client_name": "My viewer",
 "redirect_uris": ["http://127.0.0.1:8093/oauth-callback.html"],
 "token_endpoint_auth_method": "none",
 "grant_types": ["authorization_code", "refresh_token"],
 "software_id": "my-viewer",
 "software_version": "1.4.0"}
```

Svaret (201) bär `client_id`, `client_id_issued_at` och de registrerade
metadata. En konfidentiell klient (standardvärdet för
`token_endpoint_auth_method`, `client_secret_basic`) får också sin
`client_secret` en gång, med `client_secret_expires_at: 0`. Redirect-URI:er
följer reglerna ovan, och bara authorization code- och refresh token-granten
finns. Skicka `software_id` och `software_version` (RFC 7591 §2): servern
lagrar dem på klienten och visar dem för administratörer bredvid
registreringen, vilket är så en operatör skiljer installationer och versioner
av din applikation åt.

En server kan begränsa det här ytterligare. Med `OPENCDE_DYNAMIC_CLIENT_REGISTRATION_TOKEN` satt tar anropet det värdet som `Authorization: Bearer …` (RFC 7591 §3) och svarar 401 utan det. Med `OPENCDE_DYNAMIC_CLIENT_APPROVAL=true` kan den nya klienten inte logga in någon förrän en administratör godkänner den, och inloggningssidan säger det. Kapabilitetsdokumentet talar om vad som gäller.

Registrera en gång per installation och spara `client_id`: en självregistrerad
klient som inte utfärdar någon token på `OPENCDE_DYNAMIC_CLIENT_UNUSED_DAYS`
(30 som standard) tas bort tillsammans med sina tokens. När token-endpointen
sedan svarar `invalid_client`, registrera igen.

**Popup-fönster.** Sidorna din applikation öppnar i ett popup-fönster
(auktoriseringssidan, Documents API:ts urvals- och uppladdningssidor och den
inloggning de kan behöva) isolerar sig inte: de skickar
`Cross-Origin-Opener-Policy: unsafe-none`, så fönstret behåller sin
`window.opener` under besöket på servern och din callback-sida kan skicka
resultatet tillbaka till applikationen med `postMessage`. Bara `/admin` och
`/account` svarar med `same-origin`. Deras `form-action`-policy namnger också
origin för din redirect-URI (eller callback-URL), så att webbläsaren följer
omdirigeringen som svarar på formuläret: Chromium kontrollerar `form-action`
mot den omdirigeringen, inte bara mot formulärets egen adress.

## 3. BCF API

- Allt under `/bcf/3.0/projects/{project_id}` är avgränsat till ett projekt
  användaren är medlem i; projekt användaren inte kan se svarar `404`.
- `GET …/extensions` ger de tillåtna värdena (`topic_type`, `topic_status`,
  `topic_label`, `priority`, `stage`, `users`) och användarens standardvärden
  för `project_actions`, `topic_actions`, `comment_actions`. Värden utanför
  listorna avvisas med `400`.
- Lägg till `?includeAuthorization=true` på en `GET` av projekt, ärenden,
  kommentarer eller viewpoints för att få ett `authorization`-objekt per
  entitet.
- Samlingar accepterar OData: `$filter` (t.ex. `topic_status eq 'Open' and
  labels/any(l: l eq 'Safety')`), `$orderby`, `$top`, `$skip`.
- `PUT` ersätter hela objektet: skicka varje fält du vill behålla.
- Bilder i viewpoints är base64-kodad PNG eller JPEG; servern kontrollerar
  bytena.
- Varje `GET` bär en `ETag`; `If-None-Match` svarar `304`.
- Fel är `{"message": "…"}` med de vanliga statuskoderna (`400`, `401`,
  `403`, `404`, `409` för dubblerade guid, `413` för för stora kroppar).

### BCF API 2.1

Servern kan också BCF API 2.1, för klienter som inte känner till något nyare.
`GET /foundation/versions` listar båda versionerna, den nyaste först, var och en med
sin `api_base_url`, och en klient för 2.1 hittar samma lista på `GET /bcf/versions`.
Båda versionerna arbetar på samma data, så ett ärende som skapats genom den ena kan
läsas och ändras genom den andra.

| | 2.1, under `/bcf/2.1` | 3.0, under `/bcf/3.0` |
|---|---|---|
| Versioner, inloggning, användaren | `/bcf/versions`, `/bcf/2.1/auth`, `/bcf/2.1/current-user` | Foundation API |
| En fil i ett ärendes huvud | `file_name` | `filename` |
| Användarna i extensions | `user_id_type` | `users` |
| Ett ärendes korta id | Inget | `server_assigned_id` |
| En kommentar som svarar på en annan | `reply_to_comment_guid` | Inget |
| En kameras `aspect_ratio` | Inget; 3.0 läser den som 1.0 | Krävs |
| Vad en viewpoint måste innehålla | Vad som helst utom två kameror | En kamera eller en bild, och en kamera tillsammans med allt annat |
| Ett `guid` som klienten väljer | Ignoreras | Godtas, `409` om det finns |
| `files_information`, att radera en viewpoint | Inget | Ja |
| Egna händelsetyper | `reply_to_comment_updated`, `reply_to_comment_removed` | `stage_added`, `stage_updated`, `stage_removed` |
| Att fråga efter en etikett i `$filter` | `contains(labels, 'x')` | `labels/any(l: l eq 'x')`; den andra formen fungerar också |

OAuth2-exemplet i 2.1 känner inte till PKCE, så en klient som skrivits efter det kan
inte skicka någon `code_challenge`. En administratör kan märka en konfidentiell klient
som får utelämna det: *Får logga in utan PKCE* på klientens sida, `pkce_optional` i
administrations-API:t eller `opencde client create --without-pkce`. Då är det dess
hemlighet som skyddar inloggningarna, angiven med HTTP Basic på token-adressen. En
klient som registrerar sig själv på `oauth2_dynamic_client_reg_url` i `GET /bcf/2.1/auth`,
när `OPENCDE_DYNAMIC_CLIENT_REGISTRATION=true`, märks på samma sätt, medan
registreringen i Foundation API inte märker någon klient. En publik klient kan aldrig
utelämna PKCE, och en märkt klient som skickar en `code_challenge` hålls till den.
Använd PKCE om du kan. En redirect-URI på `http://localhost` kräver
`OPENCDE_ALLOW_LOCALHOST_REDIRECTS=true`.

## 4. Documents API

Flödena involverar användarens webbläsare; se [flows/documents.md](flows/documents.md).
Din klient behöver en callback-URL som webbläsaren kan nå (en
loopback-lyssnare för skrivbordsappar). Servern anropar aldrig den URL:en
själv.

## 5. Korrelera din logg med serverns

Skicka ett `X-Request-ID`-huvud (1–128 tecken ur `A-Za-z0-9._-`) med varje
begäran, så ekar servern det i svaret och binder det till sina egna
loggrader; utan ett sådant myntar servern ett id och returnerar det. Huvudet
är tillåtet i CORS-preflights och exponerat för webbläsarklienter.

När operatören har slagit på begärandeloggen (`OPENCDE_REQUEST_LOG_ENABLED`,
ett tillägg utanför specifikationerna) kan en administratör se serversidan av
varje anrop på `/admin/requests`, och en administrationsklient kan läsa samma
poster som JSON:

```http
GET /admin/api/requests?client_id=<your client id>&since=2026-11-05T10:00:00Z&limit=200
Authorization: Bearer <token with the admin scope>
```

Tokenen måste bära scopet `admin`, som en klient begär uttryckligen
(`scope=profile bcf documents admin`), och användaren måste vara
administratör. Posterna innehåller metod, sökväg, operation, status, tid,
request-id, bytestorlekar och anroparen, aldrig kroppar eller tokens.
JSON-administrations-API:t serveras så länge `OPENCDE_ADMIN_API_ENABLED` är
sant (standard), oberoende av HTML-administrationen; kapabilitetsdokumentet
(§1) talar om ifall det är på.

## 6. Fel

Varje misslyckande svarar med Foundation API 1.6:s kropp,
`{"message": "..."}`, och aldrig med stackspår eller ekad indata. Som ett
tillägg bär varje fel som servern själv formar också en stabil `code` som din
applikation kan agera på eller översätta, medan `message` förblir en engelsk
mening för människor:

```json
{"message": "This operation needs the 'admin' scope", "code": "insufficient_scope"}
```

| `code` | Status | När | Vad en klient gör |
|---|---|---|---|
| `validation_error` | 400 | Kroppen eller frågan klarade inte valideringen, ett OData-uttryck kunde inte kompileras, ett värde finns inte i projektets extensions, ett `Content-Range` eller en uppladdningsinstruktion är fel, en snapshot eller bitmap är inte PNG eller JPEG; `message` namnger fältet | Rätta begäran |
| `localhost_redirect` | 400 | En registrering angav `http://localhost` som redirect-URI, vilket den här servern inte tillåter | Registrera `http://127.0.0.1` i stället, eller berätta för operatören om `OPENCDE_ALLOW_LOCALHOST_REDIRECTS` |
| `unauthenticated` | 401 | Ingen bearer-token | Logga in |
| `invalid_token` | 401 | Tokenen är okänd, utgången eller återkallad (`WWW-Authenticate: Bearer error="invalid_token"`) | Förnya, logga sedan in igen |
| `insufficient_scope` | 403 | Tokenen saknar det scope som rutten kräver, till exempel `admin` | Auktorisera igen med det scopet |
| `forbidden` | 403 | Användarens roll i projektet tillåter inte handlingen (Foundation API 1.5), eller användaren är inte administratör på administrations-API:t | Visa meddelandet |
| `reauthentication_required` | 403 | En farlig administrationshandling och inloggningen är äldre än tio minuter | Auktorisera igen, upprepa sedan anropet |
| `not_found` | 404 | Ingen sådan resurs, en resurs utanför användarens projekt, eller en funktion som är avstängd (registrering, begärandelogg, administrations-API) | Visa meddelandet, läs om listorna |
| `conflict` | 409 | Ett guid som redan finns, eller en dubblerad länk | Hämta igen |
| `payload_too_large` | 413 | Begärans kropp överstiger serverns gräns, eller en BCF-binär överstiger `max_image_bytes`/`max_upload_bytes` | Rätta begäran |
| `upload_too_large` | 413 | En vald fil eller del överstiger uppladdningsgränsen (`max_size_in_bytes` i uppladdningsinstruktionerna) | Berätta gränsen för användaren |
| `rate_limited` | 429 | För många begäranden från en adress; `Retry-After` säger när | Vänta och försök igen |
| `internal_error` | 500 | Ett oväntat fel; `message` är alltid "Internal server error" | Rapportera med `X-Request-ID` |
| `unavailable` | 503 | Grafdatabasen kan inte nås | Försök igen senare |

Listan är sluten: en kod du inte känner till behandlas som en saknad, och du
visar `message`. Statusar som ramverket svarar med på egen hand (405, 415)
bär ingen kod. OAuth2:s token-endpoint behåller RFC 6749:s eget format
(`{"error": "invalid_grant", "error_description": "..."}`), som
specifikationen kräver, så agera på `error` där (`invalid_request`,
`invalid_client`, `invalid_grant`, `unauthorized_client`,
`unsupported_grant_type`, `invalid_scope`). Kapabilitetsdokumentet (§1)
serveras av varje server som skickar koder.

## 7. Administrations-API:t (tillägg)

En administrationsklient (Dataspatiums flik Administration är den första)
läser det som sidorna under `/admin` visar, som JSON under `/admin/api/`, med
en bearer-token som bär scopet `admin` och tillhör en administratör.
Kapabilitetsdokumentet säger om API:t är på (`extensions.admin_api`) och
vilken version det har. Listor svarar `{"items": [...], "total": n}` och tar
`limit` (200 som standard, högst 1000) samt `q` eller `since` där det anges;
fel använder kroppen i §6.

| Endpoint | Returnerar |
|---|---|
| `GET /admin/api/overview` | `version`, `uptime_s`, `dialect`, `graph_ok`, antalen `users`, `projects`, `clients`, `sessions`, `topics`, `documents`, `models`, och `request_log` (`enabled`, `rows`) |
| `GET /admin/api/users?q=&limit=` | användare (`id`, `username`, `name`, `email`, `is_admin`, `disabled`, `must_change_password`, `created_at`, `last_sign_in_at`, `projects` som `[{project_id, role}]`); `q` söker i användarnamn, namn och e-post |
| `GET /admin/api/users/{id}` | en användare; `projects` bär också projektets `name` |
| `GET /admin/api/projects?q=` | projekt med `members` (`user_id`, `username`, `role`) och antalen `topics`, `documents`, `models` |
| `GET /admin/api/projects/{id}` | ett projekt, även med dess `extensions` |
| `GET /admin/api/clients` | klienter (`client_id`, `name`, `description`, `url`, `public`, `dynamic`, `redirect_uris`, `disabled`, `created_at`, `expires_at`, `last_used_at`, `software_id`, `software_version`), aldrig någon hemlighet |
| `GET /admin/api/clients/{id}` | en klient |
| `GET /admin/api/sessions?user=&limit=` | en lista av två slag, `kind: "oauth2"` (en refresh-token-familj, `id` = familje-id) och `kind: "web"` (en webbläsarsession), var och en med `user_id`, `username`, `created_at`, `expires_at`, och `client_id`/`client_name`/`scope` eller `ip` där de är tillämpliga |
| `GET /admin/api/audit?type=&since=&limit=` | revisionshändelser med `at`, `type`, `actor` (användar-id), `client_id`, `ip`, `request_id` och tolkade `details` |
| `GET /admin/api/requests?...` | begärandeloggen (§5) |
| `GET /admin/api/settings` | `public_url`, `environment`, `dynamic_client_registration`, `request_log`, `ifcgraph`, `cors_origins`, `dataspatium_url`, `graph_public_bolt_url`, de påslagna `modules`, och varje `OPENCDE_*`-värde från inställningssidan under `raw`; hemligheter utelämnade |
| `GET /admin/api/health` | `ok` och inställningssidans `checks` (`name`, `ok`, `detail`) |

Skrivningar, med samma kroppar som sidorna använder (`PUT` och `PATCH`
accepteras lika; `name` är det fullständiga namnet, `full_name` fungerar
också):

| Endpoint | Gör |
|---|---|
| `POST /admin/api/users` `{username, password?, name?, email?, is_admin?, must_change_password?}` | skapar en användare; utan `password` bär svaret `initial_password` en gång |
| `PUT /admin/api/users/{id}` `{name?, email?, disabled?, is_admin?}` | ändrar en användare; inaktivering återkallar tokens; inte för ditt eget konto |
| `DELETE /admin/api/users/{id}` | tar bort en användare med sessioner och tokens (farlig) |
| `POST /admin/api/users/{id}/reset-password` | sätter ett nytt lösenord som returneras en gång och som användaren måste byta (farlig) |
| `POST /admin/api/projects` `{name, extensions?}` · `PUT /admin/api/projects/{id}` `{name?, extensions?}` | skapar eller ändrar ett projekt |
| `DELETE /admin/api/projects/{id}` | tar bort ett projekt med allt i det (farlig) |
| `PUT /admin/api/projects/{id}/members/{user_id}` `{role}` · `DELETE …/members/{user_id}` | sätter eller tar bort en medlems roll (viewer, contributor, editor, manager) |
| `POST /admin/api/clients` `{name, redirect_uris, public?, description?, url?}` | registrerar en klient; en konfidentiell får `client_secret` en gång |
| `PUT /admin/api/clients/{id}` `{name?, description?, url?, redirect_uris?, disabled?}` | ändrar en klient; inaktivering återkallar dess tokens |
| `POST /admin/api/clients/{id}/rotate-secret` | en ny hemlighet, returnerad en gång (farlig) |
| `POST /admin/api/clients/{id}/revoke` · `DELETE /admin/api/clients/{id}` | återkallar varje token för klienten · tar bort klienten med dess tokens (farlig) |
| `DELETE /admin/api/sessions/{id}` · `DELETE /admin/api/sessions?user=` | avslutar en session via listans `id` · avslutar varje session och token för en användare |

Farliga operationer kräver en **färsk inloggning**: tokenfamiljens
`auth_time`, satt när användaren autentiserade sig för auktoriseringskoden,
måste ligga inom de senaste tio minuterna; en refresh förnyar den aldrig.
Annars är svaret `403` med `code: reauthentication_required`, som en klient
möter genom att köra auktoriseringsflödet igen (en popup-inloggning) och
upprepa anropet. Engångsvärden returneras exakt en gång och loggas aldrig;
varje skrivning lämnar en revisionshändelse (`admin.*`) med anroparen,
klienten och anropets `X-Request-ID`.

### Graffråga (avstängd som standard)

När operatören sätter `OPENCDE_GRAPH_QUERY_ENABLED=true` tillkännager
kapabilitetsdokumentet `graph_query` med `url`, `max_rows` och
`timeout_seconds`, och administratörer med scopet `admin` får köra
**läsande** Cypher mot hela grafen, IFC-grafen inräknad, utan att
databasporten publiceras:

```http
POST /admin/api/graph/query
{"cypher": "MATCH (p:Project)<-[m:MEMBER_OF]-(u:User) RETURN p, m, u LIMIT 50", "params": {}}
```

```json
{"columns": ["p", "m", "u"],
 "rows": [[{"identity": "4:…:12", "labels": ["Project"], "properties": {"project_id": "…", "name": "Building permit"}},
           {"identity": "5:…:3", "type": "MEMBER_OF", "start": "4:…:7", "end": "4:…:12", "properties": {"role": "editor"}},
           {"identity": "4:…:7", "labels": ["User"], "properties": {"username": "editor"}}]],
 "truncated": false}
```

Raderna bär JSON-värden: noder som `{identity, labels, properties}`,
relationer som `{identity, type, start, end, properties}`, vägar som
`{nodes, relationships, length}`, temporala värden som ISO 8601-strängar,
heltal som tal, punkter som `{srid, x, y, z}`, bytes som base64. Satsen körs
i en lästransaktion; servern avvisar skrivande satsdelar och varje procedur
utom schemaprocedurerna (`db.labels`, `db.relationshipTypes`,
`db.propertyKeys`, `db.schema.*`), avvisar satser och parametrar som namnger
en skyddad egenskap (`password_hash`, `secret_hash`, `token_hash`,
`code_hash`), tar bort dessa egenskaper från varje nod, relation och map i
svaret och maskerar varje Argon2-hash som når det på annan väg. Svaret
stoppar efter `max_rows` rader (`truncated: true`) och satsen efter
`timeout_seconds`. En avvisad, misslyckad eller stoppad sats svarar `400` med
`code: validation_error` och orsaken, databasens eget meddelande inräknat.
Varje anrop, avvisat eller inte, lämnar en revisionshändelse
`admin.graph.query` med satsens första 500 tecken, aldrig parametrarna.

## 8. Testa mot den här servern

[Dataspatium](https://github.com/marwiss/Dataspatium) är webbläsarklienten
som utvecklas tillsammans med den här servern; dess OpenCDE-källa
(inloggning, BCF-tabeller, Documents API, graffrågor, request-id:n) är ett
utarbetat exempel på allt ovan, och dess live-testsviter körs mot
utvecklingsstacken.

- `uv run opencde seed` fyller en tom databas med demoanvändare och projekt
  (lösenorden skrivs ut en gång), exempelmodellen `three_walls_gtin.ifc` som
  ett dokument och ett ärende med en viewpoint och en kommentar, allt med
  fasta id:n som en testsvit kan lita på:

  | Vad | Id |
  |---|---|
  | Dokument (Documents API, version 1, projektet *Building permit*) | `6f5d3b2a-0000-4000-8000-000000000001` |
  | Ärende (`ISSUE-0001`, typ Inspection, status Open, etikett Reuse) | `6f5d3b2a-0000-4000-8000-000000000002` |
  | Viewpoint (perspektivkamera, komponent vägg `1Xezbq735AdBO_4DerG66G`) | `6f5d3b2a-0000-4000-8000-000000000003` |
  | Kommentar (av `inspector`, som hänvisar till viewpointen) | `6f5d3b2a-0000-4000-8000-000000000004` |

  Modellens väggar är `1Xezbq735AdBO_4DerG66G` (GTIN 3),
  `3eT96F_cnDsOufCEsotwtp` (GTIN 2) och `3k3LbXmTfDWODxdSuyCGYE` (GTIN 1),
  i egenskapssetet `Reuse`; samma fil är `tests/fixtures/three_walls_gtin.ifc`.
- `docker compose up -d` ger dig en
  server på `http://127.0.0.1:8000` med Neo4j Browser på `:7484`.
- Registrera en klient för din app i admin-gränssnittet (`/admin` → Klienter)
  eller med
  `uv run opencde client create "My app" --redirect-uri http://127.0.0.1/callback --public`.
- `opencde_client.testing` kan slutföra inloggningen och Documents
  API-sidorna utan webbläsare i automatiska tester.
