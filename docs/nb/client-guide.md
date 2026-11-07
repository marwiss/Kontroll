# Å bygge en klient

Hvordan en applikasjon snakker med denne serveren (eller en hvilken som helst
OpenCDE-server). Python-biblioteket i [client/](../../client/) gjør alt
dette; eksemplene i [examples/](../examples/) viser det i bruk.

## 1. Oppdag

`GET /foundation/versions` lister API-ene (`foundation 1.0`, `bcf 3.0`, `bcf 2.1`,
`documents 1.0`). `GET /foundation/1.0/auth` forteller hvor man logger inn:

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

### Kapabilitetsdokumentet (utvidelse)

Utover spesifikasjonene forteller `GET /.well-known/kontroll` (ingen
autentisering, CORS som for API-et, kan caches i fem minutter) hvilke
utvidelser denne serveren har slått på og hvilke grenser som gjelder, slik at
en klient tilpasser seg i stedet for å prøve seg fram:

```json
{
  "server": {"name": "Kontroll OpenCDE server", "version": "2.7.0", "public_url": "https://cde.example.org"},
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

En `404` betyr en server uten utvidelser (en annen OpenCDE-server, eller en
eldre Kontroll). Behandle ukjente nøkler som om de manglet. `ifcgraph.bolt`
er satt bare når operatøren bevisst har publisert grafdatabasen
(`OPENCDE_GRAPH_PUBLIC_BOLT_URL`); `graph_query` er på bare når operatøren
har satt `OPENCDE_GRAPH_QUERY_ENABLED` (§7); `links.dataspatium` bærer
adressen til en Dataspatium-installasjon når operatøren har satt
`OPENCDE_DATASPATIUM_URL`. Ingenting i dokumentet er hemmelig.

## 2. Logg inn (OAuth2 authorization code med PKCE)

1. Be serverens administrator registrere applikasjonen din: en **offentlig**
   klient for skrivebords-, mobil- og nettleserapper (ingen hemmelighet,
   PKCE), eller en **konfidensiell** klient for en serverapplikasjon
   (hemmeligheten vises én gang). Registrer den nøyaktige redirect-URI-en;
   for native apper godtas `http://127.0.0.1/…` (vilkårlig port).
2. Generer en `code_verifier` (43–128 URL-sikre tegn) og dens
   `code_challenge = BASE64URL(SHA256(verifier))`, samt en tilfeldig `state`.
3. Åpne `oauth2_auth_url?response_type=code&client_id=…&redirect_uri=…&scope=profile bcf documents&state=…&code_challenge=…&code_challenge_method=S256`
   i brukerens nettleser. Brukeren logger inn og gir samtykke.
4. Nettleseren omdirigeres til din `redirect_uri` med `code`, `state` og
   `iss`. Sjekk `state`; sjekk at `iss` er serveren.
5. `POST oauth2_token_url` med `grant_type=authorization_code`, `code`,
   `code_verifier`, `redirect_uri` og `client_id` (offentlig) eller HTTP
   Basic-autentisering (konfidensiell). Svaret er `201` med `access_token`,
   `refresh_token`, `expires_in`, `scope`.
6. Send `Authorization: Bearer <access_token>` med hvert API-kall. Når den
   utløper, `POST oauth2_token_url` med `grant_type=refresh_token`;
   refresh-tokenet roterer, så lagre det nye. Gjenbruk av et gammelt
   refresh-token trekker tilbake hele familien: det er serveren som oppdager
   et stjålet token.
7. `POST oauth2_revocation_url` med refresh-tokenet når brukeren logger ut.

Serveren støtter aldri implicit- eller password-grant.

### Registrere en klient dynamisk

Når serveren kjører med `OPENCDE_DYNAMIC_CLIENT_REGISTRATION=true`, bærer
`GET /foundation/1.0/auth` `oauth2_dynamic_client_reg_url`, og en klient kan
registrere seg selv (Foundation API 2.2.3, RFC 7591). En nettleser- eller
native applikasjon ber om en offentlig klient:

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

Svaret (201) bærer `client_id`, `client_id_issued_at` og de registrerte
metadataene. En konfidensiell klient (standardverdien for
`token_endpoint_auth_method`, `client_secret_basic`) får også sin
`client_secret` én gang, med `client_secret_expires_at: 0`. Redirect-URI-er
følger reglene ovenfor, og bare authorization code- og refresh token-grantene
finnes. Send `software_id` og `software_version` (RFC 7591 §2): serveren
lagrer dem på klienten og viser dem for administratorer ved siden av
registreringen, som er slik en operatør skiller installasjoner og versjoner
av applikasjonen din fra hverandre.

En server kan begrense dette ytterligere. Med `OPENCDE_DYNAMIC_CLIENT_REGISTRATION_TOKEN` satt tar kallet den verdien som `Authorization: Bearer …` (RFC 7591 §3) og svarer 401 uten den. Med `OPENCDE_DYNAMIC_CLIENT_APPROVAL=true` kan den nye klienten ikke logge inn noen før en administrator godkjenner den, og innloggingssiden sier det. Kapabilitetsdokumentet forteller hva som gjelder.

Registrer én gang per installasjon og lagre `client_id`: en selvregistrert
klient som ikke utsteder noe token på `OPENCDE_DYNAMIC_CLIENT_UNUSED_DAYS`
(30 som standard) slettes sammen med tokenene sine. Når token-endepunktet
deretter svarer `invalid_client`, registrer igjen.

**Popup-vinduer.** Sidene applikasjonen din åpner i et popup-vindu
(autorisasjonssiden, Documents API-ets utvalgs- og opplastingssider og
innloggingen de kan trenge) isolerer seg ikke: de sender
`Cross-Origin-Opener-Policy: unsafe-none`, så vinduet beholder sin
`window.opener` under besøket på serveren, og callback-siden din kan sende
resultatet tilbake til applikasjonen med `postMessage`. Bare `/admin` og
`/account` svarer med `same-origin`. `form-action`-policyen deres navngir
også origin for din redirect-URI (eller callback-URL), slik at nettleseren
følger omdirigeringen som svarer på skjemaet: Chromium sjekker `form-action`
mot den omdirigeringen, ikke bare mot skjemaets egen adresse.

## 3. BCF API

- Alt under `/bcf/3.0/projects/{project_id}` er avgrenset til et prosjekt
  brukeren er medlem av; prosjekter brukeren ikke kan se, svarer `404`.
- `GET …/extensions` gir de tillatte verdiene (`topic_type`, `topic_status`,
  `topic_label`, `priority`, `stage`, `users`) og brukerens standardverdier
  for `project_actions`, `topic_actions`, `comment_actions`. Verdier utenfor
  listene avvises med `400`.
- Legg til `?includeAuthorization=true` på en `GET` av prosjekter, saker,
  kommentarer eller viewpoints for å få et `authorization`-objekt per
  entitet.
- Samlinger godtar OData: `$filter` (f.eks. `topic_status eq 'Open' and
  labels/any(l: l eq 'Safety')`), `$orderby`, `$top`, `$skip`.
- `PUT` erstatter hele objektet: send hvert felt du vil beholde.
- Bilder i viewpoints er base64-kodet PNG eller JPEG; serveren sjekker
  bytene.
- Hver `GET` bærer en `ETag`; `If-None-Match` svarer `304`.
- Feil er `{"message": "…"}` med de vanlige statuskodene (`400`, `401`,
  `403`, `404`, `409` for dupliserte guid-er, `413` for for store kropper).

### BCF API 2.1

Serveren kan også BCF API 2.1, for klienter som ikke kjenner til noe nyere.
`GET /foundation/versions` lister begge versjonene, den nyeste først, hver med sin
`api_base_url`, og en klient for 2.1 finner samme liste på `GET /bcf/versions`.
Begge versjonene arbeider på de samme dataene, så en sak som er opprettet gjennom den
ene, kan leses og endres gjennom den andre.

| | 2.1, under `/bcf/2.1` | 3.0, under `/bcf/3.0` |
|---|---|---|
| Versjoner, innlogging, brukeren | `/bcf/versions`, `/bcf/2.1/auth`, `/bcf/2.1/current-user` | Foundation API |
| En fil i hodet på en sak | `file_name` | `filename` |
| Brukerne i extensions | `user_id_type` | `users` |
| Den korte id-en til en sak | Ingen | `server_assigned_id` |
| En kommentar som svarer på en annen | `reply_to_comment_guid` | Ingen |
| `aspect_ratio` for et kamera | Ingen; 3.0 leser den som 1.0 | Påkrevd |
| Hva et viewpoint må inneholde | Hva som helst unntatt to kameraer | Et kamera eller et bilde, og et kamera sammen med alt annet |
| En `guid` klienten velger | Ignoreres | Godtas, `409` hvis den finnes |
| `files_information`, å slette et viewpoint | Ingen | Ja |
| Egne hendelsestyper | `reply_to_comment_updated`, `reply_to_comment_removed` | `stage_added`, `stage_updated`, `stage_removed` |
| Å spørre etter en etikett i `$filter` | `contains(labels, 'x')` | `labels/any(l: l eq 'x')`; den andre formen virker også |

OAuth2-eksemplet i 2.1 kjenner ikke til PKCE, så en klient som er skrevet etter det,
kan ikke sende noen `code_challenge`. En administrator kan merke en konfidensiell
klient som kan utelate det: *Kan logge inn uten PKCE* på siden til klienten,
`pkce_optional` i administrasjons-API-et eller `opencde client create --without-pkce`.
Da er det hemmeligheten dens som beskytter innloggingene, oppgitt med HTTP Basic på
token-adressen. En klient som registrerer seg selv på `oauth2_dynamic_client_reg_url` i
`GET /bcf/2.1/auth`, når `OPENCDE_DYNAMIC_CLIENT_REGISTRATION=true`, merkes på samme måte,
mens registreringen i Foundation API ikke merker noen klient. En offentlig klient kan
aldri utelate PKCE, og en merket klient som sender en `code_challenge`, holdes til den.
Bruk PKCE hvis du kan. En redirect-URI på `http://localhost` krever
`OPENCDE_ALLOW_LOCALHOST_REDIRECTS=true`.

## 4. Documents API

Flytene involverer brukerens nettleser; se [flows/documents.md](flows/documents.md).
Klienten din trenger en callback-URL som nettleseren kan nå (en
loopback-lytter for skrivebordsapper). Serveren kaller aldri den URL-en selv.

## 5. Korrelere loggen din med serverens

Send en `X-Request-ID`-header (1–128 tegn fra `A-Za-z0-9._-`) med hver
forespørsel, så ekkoer serveren den i svaret og binder den til sine egne
logglinjer; uten en slik lager serveren en id og returnerer den. Headeren er
tillatt i CORS-preflights og eksponert for nettleserklienter.

Når operatøren har slått på forespørselsloggen (`OPENCDE_REQUEST_LOG_ENABLED`,
en utvidelse utenfor spesifikasjonene), kan en administrator se serversiden
av hvert kall på `/admin/requests`, og en administrasjonsklient kan lese de
samme postene som JSON:

```http
GET /admin/api/requests?client_id=<your client id>&since=2026-11-05T10:00:00Z&limit=200
Authorization: Bearer <token with the admin scope>
```

Tokenet må bære scopet `admin`, som en klient ber om eksplisitt
(`scope=profile bcf documents admin`), og brukeren må være administrator.
Postene inneholder metode, sti, operasjon, status, tid, request-id, bytetall
og kalleren, aldri kropper eller tokens. JSON-administrasjons-API-et serveres
så lenge `OPENCDE_ADMIN_API_ENABLED` er sann (standard), uavhengig av
HTML-administrasjonen; kapabilitetsdokumentet (§1) forteller om det er på.

## 6. Feil

Enhver feil svarer med Foundation API 1.6s kropp, `{"message": "..."}`, og
aldri med stakkspor eller gjentatt inndata. Som en utvidelse bærer hver feil
serveren selv former også en stabil `code` som applikasjonen din kan handle
på eller oversette, mens `message` forblir en engelsk setning for mennesker:

```json
{"message": "This operation needs the 'admin' scope", "code": "insufficient_scope"}
```

| `code` | Status | Når | Hva en klient gjør |
|---|---|---|---|
| `validation_error` | 400 | Kroppen eller spørringen besto ikke valideringen, et OData-uttrykk kunne ikke kompileres, en verdi finnes ikke i prosjektets extensions, en `Content-Range` eller en opplastingsinstruksjon er feil, et snapshot eller en bitmap er ikke PNG eller JPEG; `message` navngir feltet | Rett forespørselen |
| `localhost_redirect` | 400 | En registrering oppga `http://localhost` som redirect-URI, noe denne serveren ikke tillater | Registrer `http://127.0.0.1` i stedet, eller fortell operatøren om `OPENCDE_ALLOW_LOCALHOST_REDIRECTS` |
| `unauthenticated` | 401 | Ingen bearer-token | Logg inn |
| `invalid_token` | 401 | Tokenet er ukjent, utløpt eller trukket tilbake (`WWW-Authenticate: Bearer error="invalid_token"`) | Forny, logg deretter inn igjen |
| `insufficient_scope` | 403 | Tokenet mangler scopet ruten krever, for eksempel `admin` | Autoriser igjen med det scopet |
| `forbidden` | 403 | Brukerens rolle i prosjektet tillater ikke handlingen (Foundation API 1.5), eller brukeren er ikke administrator på administrasjons-API-et | Vis meldingen |
| `reauthentication_required` | 403 | En farlig administrasjonshandling, og innloggingen er eldre enn ti minutter | Autoriser igjen, gjenta deretter kallet |
| `not_found` | 404 | Ingen slik ressurs, en ressurs utenfor brukerens prosjekter, eller en funksjon som er av (registrering, forespørselslogg, administrasjons-API) | Vis meldingen, last listene på nytt |
| `conflict` | 409 | En guid som allerede finnes, eller en duplisert lenke | Hent igjen |
| `payload_too_large` | 413 | Forespørselens kropp er over serverens grense, eller en BCF-binær er over `max_image_bytes`/`max_upload_bytes` | Rett forespørselen |
| `upload_too_large` | 413 | En valgt fil eller del er over opplastingsgrensen (`max_size_in_bytes` i opplastingsinstruksjonene) | Fortell brukeren grensen |
| `rate_limited` | 429 | For mange forespørsler fra én adresse; `Retry-After` sier når | Vent og prøv igjen |
| `internal_error` | 500 | En uventet feil; `message` er alltid "Internal server error" | Rapporter med `X-Request-ID` |
| `unavailable` | 503 | Grafdatabasen kan ikke nås | Prøv igjen senere |

Listen er lukket: en kode du ikke kjenner, behandles som en manglende, og du
viser `message`. Statuser som rammeverket svarer med på egen hånd (405,
415), bærer ingen kode. OAuth2-token-endepunktet beholder RFC 6749s eget
format (`{"error": "invalid_grant", "error_description": "..."}`), som
spesifikasjonen krever, så handle på `error` der (`invalid_request`,
`invalid_client`, `invalid_grant`, `unauthorized_client`,
`unsupported_grant_type`, `invalid_scope`). Kapabilitetsdokumentet (§1)
serveres av hver server som sender koder.

## 7. Administrasjons-API-et (utvidelse)

En administrasjonsklient (Dataspatiums fane Administrasjon er den første)
leser det sidene under `/admin` viser, som JSON under `/admin/api/`, med et
bearer-token som bærer scopet `admin` og tilhører en administrator.
Kapabilitetsdokumentet sier om API-et er på (`extensions.admin_api`) og
hvilken versjon det har. Lister svarer `{"items": [...], "total": n}` og tar
`limit` (200 som standard, høyst 1000) samt `q` eller `since` der det er
angitt; feil bruker kroppen i §6.

| Endepunkt | Returnerer |
|---|---|
| `GET /admin/api/overview` | `version`, `uptime_s`, `dialect`, `graph_ok`, tallene `users`, `projects`, `clients`, `sessions`, `topics`, `documents`, `models`, og `request_log` (`enabled`, `rows`) |
| `GET /admin/api/users?q=&limit=` | brukere (`id`, `username`, `name`, `email`, `is_admin`, `disabled`, `must_change_password`, `created_at`, `last_sign_in_at`, `projects` som `[{project_id, role}]`); `q` søker i brukernavn, navn og e-post |
| `GET /admin/api/users/{id}` | én bruker; `projects` bærer også prosjektets `name` |
| `GET /admin/api/projects?q=` | prosjekter med `members` (`user_id`, `username`, `role`) og tallene `topics`, `documents`, `models` |
| `GET /admin/api/projects/{id}` | ett prosjekt, også med dets `extensions` |
| `GET /admin/api/clients` | klienter (`client_id`, `name`, `description`, `url`, `public`, `dynamic`, `redirect_uris`, `disabled`, `created_at`, `expires_at`, `last_used_at`, `software_id`, `software_version`), aldri en hemmelighet |
| `GET /admin/api/clients/{id}` | én klient |
| `GET /admin/api/sessions?user=&limit=` | én liste av to slag, `kind: "oauth2"` (en refresh-token-familie, `id` = familie-id) og `kind: "web"` (en nettlesersesjon), hver med `user_id`, `username`, `created_at`, `expires_at`, og `client_id`/`client_name`/`scope` eller `ip` der de gjelder |
| `GET /admin/api/audit?type=&since=&limit=` | revisjonshendelser med `at`, `type`, `actor` (bruker-id), `client_id`, `ip`, `request_id` og tolkede `details` |
| `GET /admin/api/requests?...` | forespørselsloggen (§5) |
| `GET /admin/api/settings` | `public_url`, `environment`, `dynamic_client_registration`, `request_log`, `ifcgraph`, `cors_origins`, `dataspatium_url`, `graph_public_bolt_url`, de aktiverte `modules`, og hver `OPENCDE_*`-verdi fra innstillingssiden under `raw`; hemmeligheter utelatt |
| `GET /admin/api/health` | `ok` og innstillingssidens `checks` (`name`, `ok`, `detail`) |

Skrivinger, med de samme kroppene som sidene bruker (`PUT` og `PATCH` godtas
likt; `name` er det fulle navnet, `full_name` virker også):

| Endepunkt | Gjør |
|---|---|
| `POST /admin/api/users` `{username, password?, name?, email?, is_admin?, must_change_password?}` | oppretter en bruker; uten `password` bærer svaret `initial_password` én gang |
| `PUT /admin/api/users/{id}` `{name?, email?, disabled?, is_admin?}` | endrer en bruker; deaktivering trekker tilbake tokens; ikke for din egen konto |
| `DELETE /admin/api/users/{id}` | sletter en bruker med sesjoner og tokens (farlig) |
| `POST /admin/api/users/{id}/reset-password` | setter et nytt passord som returneres én gang, og som brukeren må bytte (farlig) |
| `POST /admin/api/projects` `{name, extensions?}` · `PUT /admin/api/projects/{id}` `{name?, extensions?}` | oppretter eller endrer et prosjekt |
| `DELETE /admin/api/projects/{id}` | sletter et prosjekt med alt i det (farlig) |
| `PUT /admin/api/projects/{id}/members/{user_id}` `{role}` · `DELETE …/members/{user_id}` | setter eller fjerner et medlems rolle (viewer, contributor, editor, manager) |
| `POST /admin/api/clients` `{name, redirect_uris, public?, description?, url?}` | registrerer en klient; en konfidensiell får `client_secret` én gang |
| `PUT /admin/api/clients/{id}` `{name?, description?, url?, redirect_uris?, disabled?}` | endrer en klient; deaktivering trekker tilbake dens tokens |
| `POST /admin/api/clients/{id}/rotate-secret` | en ny hemmelighet, returnert én gang (farlig) |
| `POST /admin/api/clients/{id}/revoke` · `DELETE /admin/api/clients/{id}` | trekker tilbake hvert token for klienten · sletter klienten med dens tokens (farlig) |
| `DELETE /admin/api/sessions/{id}` · `DELETE /admin/api/sessions?user=` | avslutter én sesjon via listens `id` · avslutter hver sesjon og hvert token for en bruker |

Farlige operasjoner krever en **fersk innlogging**: tokenfamiliens
`auth_time`, satt da brukeren autentiserte seg for autorisasjonskoden, må
ligge innenfor de siste ti minuttene; en refresh fornyer den aldri. Ellers
er svaret `403` med `code: reauthentication_required`, som en klient møter
ved å kjøre autorisasjonsflyten igjen (en popup-innlogging) og gjenta
kallet. Engangsverdier returneres nøyaktig én gang og logges aldri; hver
skriving etterlater en revisjonshendelse (`admin.*`) med kalleren, klienten
og kallets `X-Request-ID`.

### Grafspørring (av som standard)

Når operatøren setter `OPENCDE_GRAPH_QUERY_ENABLED=true`, kunngjør
kapabilitetsdokumentet `graph_query` med `url`, `max_rows` og
`timeout_seconds`, og administratorer med scopet `admin` kan kjøre
**lesende** Cypher mot hele grafen, IFC-grafen inkludert, uten at
databaseporten publiseres:

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

Radene bærer JSON-verdier: noder som `{identity, labels, properties}`,
relasjoner som `{identity, type, start, end, properties}`, stier som
`{nodes, relationships, length}`, tidsverdier som ISO 8601-strenger, heltall
som tall, punkter som `{srid, x, y, z}`, bytes som base64. Setningen kjører i
en lesetransaksjon; serveren avviser skrivende klausuler og enhver prosedyre
bortsett fra skjemaprosedyrene (`db.labels`, `db.relationshipTypes`,
`db.propertyKeys`, `db.schema.*`), avviser setninger og parametere som
navngir en beskyttet egenskap (`password_hash`, `secret_hash`, `token_hash`,
`code_hash`), fjerner disse egenskapene fra hver node, relasjon og map i
svaret og maskerer enhver Argon2-hash som når det på annen måte. Svaret
stopper etter `max_rows` rader (`truncated: true`) og setningen etter
`timeout_seconds`. En avvist, mislykket eller stoppet setning svarer `400`
med `code: validation_error` og årsaken, databasens egen melding inkludert.
Hvert kall, avvist eller ikke, etterlater en revisjonshendelse
`admin.graph.query` med setningens første 500 tegn, aldri parameterne.

## 8. Teste mot denne serveren

[Dataspatium](https://github.com/marwiss/Dataspatium) er nettleserklienten
som utvikles sammen med denne serveren; dens OpenCDE-kilde (innlogging,
BCF-tabeller, Documents API, grafspørringer, request-id-er) er et
gjennomarbeidet eksempel på alt ovenfor, og dens live-testsuiter kjører mot
utviklingsstakken (se [acceptance.md](../acceptance.md)).

- `uv run opencde seed` fyller en tom database med demobrukere og prosjekter
  (passordene skrives ut én gang), eksempelmodellen `three_walls_gtin.ifc`
  som et dokument og én sak med et viewpoint og en kommentar, alt med faste
  id-er som en testsuite kan stole på:

  | Hva | Id |
  |---|---|
  | Dokument (Documents API, versjon 1, prosjektet *Building permit*) | `6f5d3b2a-0000-4000-8000-000000000001` |
  | Sak (`ISSUE-0001`, type Inspection, status Open, etikett Reuse) | `6f5d3b2a-0000-4000-8000-000000000002` |
  | Viewpoint (perspektivkamera, komponent vegg `1Xezbq735AdBO_4DerG66G`) | `6f5d3b2a-0000-4000-8000-000000000003` |
  | Kommentar (av `inspector`, som viser til viewpointet) | `6f5d3b2a-0000-4000-8000-000000000004` |

  Modellens vegger er `1Xezbq735AdBO_4DerG66G` (GTIN 3),
  `3eT96F_cnDsOufCEsotwtp` (GTIN 2) og `3k3LbXmTfDWODxdSuyCGYE` (GTIN 1),
  i egenskapssettet `Reuse`; den samme filen er `tests/fixtures/three_walls_gtin.ifc`.
- `docker compose -f compose.yaml -f compose.dev.yaml up -d` gir deg en
  server på `http://127.0.0.1:8000` med Neo4j Browser på `:7484`.
- Registrer en klient for appen din i admin-grensesnittet (`/admin` →
  Klienter) eller med
  `uv run opencde client create "My app" --redirect-uri http://127.0.0.1/callback --public`.
- `opencde_client.testing` kan fullføre innloggingen og Documents API-sidene
  uten nettleser i automatiserte tester.
