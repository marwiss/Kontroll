# Å byggje ein klient

Korleis ein applikasjon snakkar med denne serveren (eller ein kva som helst
OpenCDE-server). Python-biblioteket i [client/](../../client/) gjer alt
dette; døma i [examples/](../examples/) viser det i bruk.

## 1. Oppdag

`GET /foundation/versions` listar API-ane (`foundation 1.0`, `bcf 3.0`, `bcf 2.1`,
`documents 1.0`). `GET /foundation/1.0/auth` fortel kvar ein loggar inn:

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

Ein tenar kan stillast inn til å tilby berre nokre av dei (`OPENCDE_APIS`). Då
inneheld listene berre det han tilbyr, og eit API han ikkje tilbyr, svarar 404.
Ein tenar for berre BCF API 2.1 har ikkje Foundation API: ein klient finn han
gjennom `GET /bcf/versions` og loggar inn gjennom `GET /bcf/2.1/auth`. Ein
dokumenttenar tilbyr Foundation API og Documents API, men ingen BCF.

### Kapabilitetsdokumentet (utviding)

Utover spesifikasjonane fortel `GET /.well-known/dataregium` (ingen
autentisering, CORS som for API-et, kan cachast i fem minutt) kva utvidingar
denne serveren har slått på og kva grenser som gjeld, slik at ein klient
tilpassar seg i staden for å prøve seg fram:

```json
{
  "server": {"name": "Dataregium OpenCDE server", "version": "3.0.0", "public_url": "https://cde.example.org"},
  "apis": {"foundation": "1.0", "bcf": "3.0", "documents": "1.0"},
  "scopes": ["profile", "bcf", "documents", "project", "admin"],
  "extensions": {
    "dynamic_client_registration": {"enabled": true, "public_clients": true, "initial_access_token": false, "approval": false, "unused_days": 30,
                                    "url": "/foundation/oauth2/reg"},
    "request_log": {"enabled": true, "retention_hours": 72, "url": "/admin/api/requests"},
    "admin_api": {"enabled": true, "version": 1, "url": "/admin/api", "scope": "admin"},
    "ifcgraph": {"enabled": true, "bolt": null, "workcopy": false},
    "ifc_queries": {"enabled": true, "url": "/documents/1.0/documents/{document_id}/versions/{version_index}/ifc-queries", "names": ["entity", "element-classes", "elements", "storeys", "spaces", "areas", "materials", "property", "site", "changed-since"], "max_rows": 10000},
    "ifc_clash": {"enabled": true, "url": "/documents/1.0/projects/{project_id}/ifc-clash", "modes": ["intersection", "clearance"], "max_clashes": 10000},
    "project_administration": {"enabled": true, "url": "/manage/1.0/projects", "teams_url": "/manage/1.0/projects/{project_id}/teams", "scope": "project", "roles": ["viewer", "contributor", "editor", "manager"], "for": "managers of a project"},
    "publication": {"enabled": true, "url": "/documents/1.0/documents/{document_id}/versions/{version_index}/publication", "roles": ["manager"], "formats": ["ifczip", "zip"]},
    "headless_uploads": {"enabled": true, "url": "/documents/1.0/upload-documents", "for": "confidential clients an administrator approved"},
    "ifc_diff": {"enabled": true, "url": "/documents/1.0/documents/{document_id}/versions/{version_index}/ifc-diff/{other_index}", "max_entries": 10000},
    "ifc_geometry": {"enabled": true, "url": "/documents/1.0/documents/{document_id}/versions/{version_index}/ifc-geometry", "format": "model/gltf-binary", "lods": ["full", "box"]},
    "ifc_validation": {"enabled": true, "url": "/documents/1.0/documents/{document_id}/versions/{version_index}/ifc-validation", "bsdd": false},
    "ifc_precheck": {"enabled": true, "url": "/documents/1.0/projects/{project_id}/ifc-precheck"},
    "ifc_changes": {"enabled": true, "schema": "/documents/1.0/ifc-changes/schema", "snippet_type": "DataregiumIfcChangeSet", "max_changes": 10000, "tried": true, "proposal_url": "/bcf/3.0/projects/{project_id}/topics/{topic_guid}/ifc-proposal", "approve_url": "/bcf/3.0/projects/{project_id}/topics/{topic_guid}/ifc-proposal/approve", "ifc_proposals_url": "/documents/1.0/documents/{document_id}/ifc-proposals"},
    "ifc_merge": {"enabled": true, "url": "/documents/1.0/projects/{project_id}/ifc-merge", "report_url": "/documents/1.0/projects/{project_id}/ifc-merge/report", "prepare_url": "/documents/1.0/projects/{project_id}/ifc-merge/prepare", "choices": ["a", "b", "new"], "roles": ["manager"]},
    "graph_query": {"enabled": true, "url": "/admin/api/graph/query", "max_rows": 1000, "timeout_seconds": 10.0}
  },
  "limits": {"max_upload_bytes": 1073741824, "max_image_bytes": 10485760, "access_token_ttl_seconds": 3600},
  "links": {"dataspatium": null}
}
```

Ein `404` tyder ein server utan utvidingar (ein annan OpenCDE-server, eller
ein eldre Dataregium). Handsam ukjende nøklar som om dei mangla.
`ifcgraph.bolt` er sett berre når operatøren medvite har publisert
grafdatabasen (`OPENCDE_GRAPH_PUBLIC_BOLT_URL`); `graph_query` er på berre
når operatøren har sett `OPENCDE_GRAPH_QUERY_ENABLED` (§7);
`links.dataspatium` ber adressa til ein Dataspatium-installasjon når
operatøren har sett `OPENCDE_DATASPATIUM_URL`. Ingenting i dokumentet er
løynt.

## 2. Logg inn (OAuth2 authorization code med PKCE)

1. Be administratoren til serveren registrere applikasjonen din: ein
   **offentleg** klient for skrivebords-, mobil- og nettlesarappar (ingen
   løyndom, PKCE), eller ein **konfidensiell** klient for ein
   serverapplikasjon (løyndomen blir vist éin gong). Registrer den nøyaktige
   redirect-URI-en; for native appar blir `http://127.0.0.1/…` (vilkårleg
   port) godteke.
2. Generer ein `code_verifier` (43–128 URL-sikre teikn) og
   `code_challenge = BASE64URL(SHA256(verifier))` for han, samt ein tilfeldig
   `state`.
3. Opne `oauth2_auth_url?response_type=code&client_id=…&redirect_uri=…&scope=profile bcf documents&state=…&code_challenge=…&code_challenge_method=S256`
   i nettlesaren til brukaren. Brukaren loggar inn og gjev samtykke.
4. Nettlesaren blir omdirigert til din `redirect_uri` med `code`, `state` og
   `iss`. Sjekk `state`; sjekk at `iss` er serveren.
5. `POST oauth2_token_url` med `grant_type=authorization_code`, `code`,
   `code_verifier`, `redirect_uri` og `client_id` (offentleg) eller HTTP
   Basic-autentisering (konfidensiell). Svaret er `201` med `access_token`,
   `refresh_token`, `expires_in`, `scope`.
6. Send `Authorization: Bearer <access_token>` med kvart API-kall. Når det
   går ut, `POST oauth2_token_url` med `grant_type=refresh_token`;
   refresh-tokenet roterer, så lagre det nye. Gjenbruk av eit gammalt
   refresh-token trekkjer tilbake heile familien: det er serveren som
   oppdagar eit stole token.
7. `POST oauth2_revocation_url` med refresh-tokenet når brukaren loggar ut.

Serveren støttar aldri implicit- eller password-grant.

### Registrere ein klient dynamisk

Når serveren køyrer med `OPENCDE_DYNAMIC_CLIENT_REGISTRATION=true`, ber
`GET /foundation/1.0/auth` `oauth2_dynamic_client_reg_url`, og ein klient kan
registrere seg sjølv (Foundation API 2.2.3, RFC 7591). Ein nettlesar- eller
native applikasjon ber om ein offentleg klient:

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

Svaret (201) ber `client_id`, `client_id_issued_at` og dei registrerte
metadataa. Ein konfidensiell klient (standardverdien for
`token_endpoint_auth_method`, `client_secret_basic`) får òg `client_secret`
sin éin gong, med `client_secret_expires_at: 0`. Redirect-URI-ar følgjer
reglane ovanfor, og berre authorization code- og refresh token-grantane
finst. Send `software_id` og `software_version` (RFC 7591 §2): serveren
lagrar dei på klienten og viser dei for administratorar ved sida av
registreringa, som er slik ein operatør skil installasjonar og versjonar av
applikasjonen din frå kvarandre.

Ein server kan avgrense dette ytterlegare. Med `OPENCDE_DYNAMIC_CLIENT_REGISTRATION_TOKEN` sett tek kallet den verdien som `Authorization: Bearer …` (RFC 7591 §3) og svarar 401 utan han. Med `OPENCDE_DYNAMIC_CLIENT_APPROVAL=true` kan den nye klienten ikkje logge inn nokon før ein administrator godkjenner han, og innloggingssida seier det. Kapabilitetsdokumentet fortel kva som gjeld.

Registrer éin gong per installasjon og lagre `client_id`: ein sjølvregistrert
klient som ikkje utferdar noko token på `OPENCDE_DYNAMIC_CLIENT_UNUSED_DAYS`
(30 som standard), blir sletta saman med tokena sine. Når token-endepunktet
deretter svarar `invalid_client`, registrer igjen.

**Popup-vindauge.** Sidene applikasjonen din opnar i eit popup-vindauge
(autorisasjonssida, utvals- og opplastingssidene til Documents API og
innlogginga dei kan trenge) isolerer seg ikkje: dei sender
`Cross-Origin-Opener-Policy: unsafe-none`, så vindauget held på
`window.opener` under besøket på serveren, og callback-sida di kan sende
resultatet tilbake til applikasjonen med `postMessage`. Berre `/admin` og
`/account` svarar med `same-origin`. `form-action`-policyen deira namngjev òg
origin for din redirect-URI (eller callback-URL), slik at nettlesaren følgjer
omdirigeringa som svarar på skjemaet: Chromium sjekkar `form-action` mot den
omdirigeringa, ikkje berre mot skjemaet si eiga adresse.

## 3. BCF API

- Alt under `/bcf/3.0/projects/{project_id}` er avgrensa til eit prosjekt
  brukaren er medlem av; prosjekt brukaren ikkje kan sjå, svarar `404`.
- `GET …/extensions` gjev dei tillatne verdiane (`topic_type`,
  `topic_status`, `topic_label`, `priority`, `stage`, `users`) og
  standardverdiane til brukaren for `project_actions`, `topic_actions`,
  `comment_actions`. Verdiar utanfor listene blir avviste med `400`.
- Legg til `?includeAuthorization=true` på ein `GET` av prosjekt, saker,
  kommentarar eller viewpoints for å få eit `authorization`-objekt per
  entitet.
- Samlingar godtek OData: `$filter` (t.d. `topic_status eq 'Open' and
  labels/any(l: l eq 'Safety')`), `$orderby`, `$top`, `$skip`.
- Ei liste utan `$top`, eller med ein større enn 1000, har høgst 1000 postar. Når
  fleire treffer, har svaret `X-Total-Count` med talet på dei og
  `Link: <…>; rel="next"` med adressa til resten (ei utviding).
- `PUT` erstattar heile objektet: send kvart felt du vil halde på.
- Bilete i viewpoints er base64-koda PNG eller JPEG; serveren sjekkar
  bytane.
- Kvar `GET` ber ein `ETag`; `If-None-Match` svarar `304`.
- Feil er `{"message": "…"}` med dei vanlege statuskodane (`400`, `401`,
  `403`, `404`, `409` for dupliserte guid-ar, `413` for for store kroppar).

### BCF API 2.1

Serveren kan òg BCF API 2.1, for klientar som ikkje kjenner til noko nyare.
`GET /foundation/versions` listar begge versjonane, den nyaste først, kvar med si
`api_base_url`, og ein klient for 2.1 finn same lista på `GET /bcf/versions`.
Begge versjonane arbeider på dei same dataa, så ei sak som er oppretta gjennom den
eine, kan lesast og endrast gjennom den andre.

| | 2.1, under `/bcf/2.1` | 3.0, under `/bcf/3.0` |
|---|---|---|
| Versjonar, innlogging, brukaren | `/bcf/versions`, `/bcf/2.1/auth`, `/bcf/2.1/current-user` | Foundation API |
| Ei fil i hovudet på ei sak | `file_name` | `filename` |
| Brukarane i extensions | `user_id_type` | `users` |
| Den korte id-en til ei sak | Ingen | `server_assigned_id` |
| Ein kommentar som svarar på ein annan | `reply_to_comment_guid` | Ingen |
| `aspect_ratio` for eit kamera | Ingen; 3.0 les han som 1.0 | Påkravd |
| Kva eit viewpoint må innehalde | Kva som helst unnateke to kamera | Eit kamera eller eit bilete, og eit kamera saman med alt anna |
| Ein `guid` klienten vel | Blir ignorert | Blir godteken, `409` om han finst |
| `files_information`, å slette eit viewpoint | Ingen | Ja |
| Eigne hendingstypar | `reply_to_comment_updated`, `reply_to_comment_removed` | `stage_added`, `stage_updated`, `stage_removed` |
| Å spørje etter ein etikett i `$filter` | `contains(labels, 'x')` | `labels/any(l: l eq 'x')`; den andre forma verkar òg |

OAuth2-eksempelet i 2.1 kjenner ikkje til PKCE, så ein klient som er skriven etter det,
kan ikkje sende nokon `code_challenge`. Ein administrator kan merke ein konfidensiell
klient som kan utelate det: *Kan logge inn utan PKCE* på sida til klienten,
`pkce_optional` i administrasjons-API-et eller `opencde client create --without-pkce`.
Då er det løyndomen hans som vernar innloggingane, oppgitt med HTTP Basic på
token-adressa. Ein klient som registrerer seg sjølv på `oauth2_dynamic_client_reg_url` i
`GET /bcf/2.1/auth`, når `OPENCDE_DYNAMIC_CLIENT_REGISTRATION=true`, blir merkt på same
måte, medan registreringa i Foundation API ikkje merkjer nokon klient. Ein offentleg
klient kan aldri utelate PKCE, og ein merkt klient som sender ein `code_challenge`, blir
halden til han. Bruk PKCE om du kan. Ein redirect-URI på `http://localhost` krev
`OPENCDE_ALLOW_LOCALHOST_REDIRECTS=true`.

## 4. Documents API

Flytane involverer nettlesaren til brukaren; sjå [flows/documents.md](flows/documents.md).
Klienten din treng ein callback-URL som nettlesaren kan nå (ein
loopback-lyttar for skrivebordsappar). Serveren kallar aldri den URL-en
sjølv.

Når IFC-LPG-modulen er på, blir ei IFC-fil som blir lasta opp som versjon,
kontrollert mot IFC-skjemaet og, der tenaren har dei, ifc-gherkin-rules frå
buildingSMART. Metadataa hennar har då `ifc_validation_status`
og, når ho er kontrollert, dei andre `ifc_validation_*`-postane;
`ifc_validation_report` er adressa til rapporten, ei utviding som svarar på det
same tokenet. Sjå [ifc-lpg.md](ifc-lpg.md#kontroll-av-opplastingar-mot-ifc-skjemaet).

Ein versjon som rommar ein IFC-modell, kan òg få namngjevne spørjingar, som
etasjane, arealet av romma eller verdien av ein eigenskap. Det er ei utviding
som svarar på det same tokenet, og som kapabilitetsdokumentet kunngjer i
`ifc_queries`. Sjå [ifc-lpg.md](ifc-lpg.md#namngjevne-spørjingar).

To IFC-versjonar i eit prosjekt kan samanliknast for kollisjonar på same måte, ei
utviding som blir annonsert som `ifc_clash`. Sjå [ifc-lpg.md](ifc-lpg.md#kollisjonskontroll).

Ei fil kan kontrollerast før ho blir lasta opp, ei utviding som blir annonsert
som `ifc_precheck`, og eit prosjekt kan avvise filer med feil. Sjå
[ifc-lpg.md](ifc-lpg.md#avvise-filer-med-feil-og-kontrollere-ei-fil-på-førehand).

Ei endring av ein modell blir føreslått som ei BCF-sak der `bim_snippet` er eit
endringssett, ei form som blir annonsert som `ifc_changes`. Sjå
[ifc-lpg.md](ifc-lpg.md#endringssett).

To IFC-versjonar blir samanlikna element for element med `ifc_diff`, etter
GlobalId og sti. Sjå [ifc-lpg.md](ifc-lpg.md#samanlikne-to-versjonar).

Geometrien i ein IFC-versjon kjem som binær glTF med `ifc_geometry` (`lod=full` eller `box`, `classes`, `storey`),
og kvar bygningsdel har boksen sin i grafen. Sjå [ifc-lpg.md](ifc-lpg.md#kvar-bygningsdelane-er-og-geometrien).

Ein `manager` publiserer ein versjon med `publication`: `POST …/versions/{index}/publication` lagrar fila som eitt
arkiv, `.ifczip` for ei IFC-fil og `.zip` for ei anna fil, og metadataa til versjonen får `published_at`,
`published_by` og `publication`. Ein versjon blir publisert éin gong, og ikkje medan han blir kontrollert eller
når kontrollen har funne feil. `GET …/publication` viser kvart medlem kven som publiserte han og når, og
`…/publication/download` gjev arkivet.

Ein bygning frå ein annan modell kjem inn i ein modell i prosjektet som neste versjon med `ifc_merge`, med
ein rapport først og eit val for kvart objekt som er ulikt. Sjå [ifc-lpg.md](ifc-lpg.md#ein-bygning-inn-i-ein-annan-modell).

## 5. Korrelere loggen din med loggen til serveren

Send ein `X-Request-ID`-header (1–128 teikn frå `A-Za-z0-9._-`) med kvar
førespurnad, så ekkoar serveren han i svaret og bind han til sine eigne
logglinjer; utan ein slik lagar serveren ein id og returnerer han. Headeren
er tillaten i CORS-preflights og eksponert for nettlesarklientar.

Når operatøren har slått på førespurnadsloggen (`OPENCDE_REQUEST_LOG_ENABLED`,
ei utviding utanfor spesifikasjonane), kan ein administrator sjå serversida
av kvart kall på `/admin/requests`, og ein administrasjonsklient kan lese dei
same postane som JSON:

```http
GET /admin/api/requests?client_id=<your client id>&since=2026-11-05T10:00:00Z&limit=200
Authorization: Bearer <token with the admin scope>
```

Tokenet må bere scopet `admin`, som ein klient ber om eksplisitt
(`scope=profile bcf documents admin`), og brukaren må vere administrator.
Postane inneheld metode, sti, operasjon, status, tid, request-id, bytetal og
kallaren, aldri kroppar eller tokens. JSON-administrasjons-API-et blir
servert så lenge `OPENCDE_ADMIN_API_ENABLED` er sann (standard), uavhengig
av HTML-administrasjonen; kapabilitetsdokumentet (§1) fortel om det er på.

## 6. Feil

Kvar feil svarar med kroppen frå Foundation API 1.6, `{"message": "..."}`,
og aldri med stakkspor eller attgjeven inndata. Som ei utviding ber kvar feil
serveren sjølv formar òg ein stabil `code` som applikasjonen din kan handle
på eller setje om, medan `message` held fram som ei engelsk setning for
menneske:

```json
{"message": "This operation needs the 'admin' scope", "code": "insufficient_scope"}
```

API-dokumentet (`/openapi.json`) oppgjev `400` med denne kroppen for ein
førespurnad serveren ikkje kan lese, slik serveren svarar, der FastAPI sjølv ville
oppgje `422`.

| `code` | Status | Når | Kva ein klient gjer |
|---|---|---|---|
| `validation_error` | 400 | Kroppen eller spørjinga stod ikkje valideringa, eit OData-uttrykk kunne ikkje kompilerast, ein verdi finst ikkje i extensions til prosjektet, ein `Content-Range` eller ein opplastingsinstruksjon er feil, eit snapshot eller ein bitmap er ikkje PNG eller JPEG; `message` namngjev feltet | Rett førespurnaden |
| `localhost_redirect` | 400 | Ei registrering oppgav `http://localhost` som redirect-URI, noko denne serveren ikkje tillèt | Registrer `http://127.0.0.1` i staden, eller fortel operatøren om `OPENCDE_ALLOW_LOCALHOST_REDIRECTS` |
| `unauthenticated` | 401 | Ingen bearer-token | Logg inn |
| `invalid_token` | 401 | Tokenet er ukjent, utgått eller trekt tilbake (`WWW-Authenticate: Bearer error="invalid_token"`) | Forny, logg deretter inn igjen |
| `insufficient_scope` | 403 | Tokenet manglar scopet ruta krev, til dømes `admin` | Autoriser igjen med det scopet |
| `forbidden` | 403 | Rolla brukaren har i prosjektet tillèt ikkje handlinga (Foundation API 1.5), eller brukaren er ikkje administrator på administrasjons-API-et | Vis meldinga |
| `reauthentication_required` | 403 | Ei farleg administrasjonshandling, og innlogginga er eldre enn ti minutt | Autoriser igjen, gjenta deretter kallet |
| `not_found` | 404 | Ingen slik ressurs, ein ressurs utanfor prosjekta til brukaren, eller ein funksjon som er av (registrering, førespurnadslogg, administrasjons-API) | Vis meldinga, last listene på nytt |
| `conflict` | 409 | Ein guid som alt finst, eller ei duplisert lenkje | Hent igjen |
| `version_conflict` | 412 | Opplastinga oppgav `base_version_index`, og dokumentet har alt ein nyare versjon; eller eit endringssett kolliderer med det som er endra sidan basen, oppgjeve i `conflicts`, med dei tre verdiane for kvar i `conflict_details` | Hent den nyaste versjonen, slå saman og last opp på nytt |
| `ifc_validation_failed` | 422 | Prosjektet avviser filer med valideringsfeil, og fila har nokre; `report` i kroppen er adressa til rapporten | Vis rapporten, lat brukaren rette fila og last opp på nytt |
| `payload_too_large` | 413 | Kroppen i førespurnaden er over grensa til serveren, eller ein BCF-binær er over `max_image_bytes`/`max_upload_bytes` | Rett førespurnaden |
| `upload_too_large` | 413 | Ei vald fil eller ein del er over opplastingsgrensa (`max_size_in_bytes` i opplastingsinstruksjonane) | Fortel brukaren grensa |
| `rate_limited` | 429 | For mange førespurnader frå éi adresse; `Retry-After` seier når | Vent og prøv igjen |
| `internal_error` | 500 | Ein uventa feil; `message` er alltid "Internal server error" | Rapporter med `X-Request-ID` |
| `unavailable` | 503 | Grafdatabasen kan ikkje nåast | Prøv igjen seinare |

Lista er lukka: ein kode du ikkje kjenner, blir handsama som ein manglande,
og du viser `message`. Statusar som rammeverket svarar med på eiga hand (405,
415), ber ingen kode. OAuth2-token-endepunktet held på sitt eige format frå
RFC 6749 (`{"error": "invalid_grant", "error_description": "..."}`), som
spesifikasjonen krev, så handle på `error` der (`invalid_request`,
`invalid_client`, `invalid_grant`, `unauthorized_client`,
`unsupported_grant_type`, `invalid_scope`). Kapabilitetsdokumentet (§1) blir
servert av kvar server som sender kodar.

## 7. Administrasjons-API-et (utviding)

Ein administrasjonsklient (fana Administrasjon i Dataspatium er den første)
les det sidene under `/admin` viser, som JSON under `/admin/api/`, med eit
bearer-token som ber scopet `admin` og høyrer til ein administrator.
Kapabilitetsdokumentet seier om API-et er på (`extensions.admin_api`) og kva
versjon det har. Lister svarar `{"items": [...], "total": n}` og tek `limit`
(200 som standard, høgst 1000) samt `q` eller `since` der det er oppgjeve;
feil brukar kroppen i §6.

| Endepunkt | Returnerer |
|---|---|
| `GET /admin/api/overview` | `version`, `uptime_s`, `dialect`, `graph_ok`, tala `users`, `projects`, `clients`, `sessions`, `topics`, `documents`, `models`, og `request_log` (`enabled`, `rows`) |
| `GET /admin/api/users?q=&limit=` | brukarar (`id`, `username`, `name`, `email`, `is_admin`, `disabled`, `must_change_password`, `created_at`, `last_sign_in_at`, `projects` som `[{project_id, role}]`); `q` søkjer i brukarnamn, namn og e-post |
| `GET /admin/api/users/{id}` | éin brukar; `projects` ber òg `name` til prosjektet |
| `GET /admin/api/projects?q=` | prosjekt med `members` (`user_id`, `username`, `role`) og tala `topics`, `documents`, `models` |
| `GET /admin/api/projects/{id}` | eitt prosjekt, òg med `extensions` |
| `GET /admin/api/clients` | klientar (`client_id`, `name`, `description`, `url`, `public`, `dynamic`, `redirect_uris`, `disabled`, `created_at`, `expires_at`, `last_used_at`, `software_id`, `software_version`), aldri ein løyndom |
| `GET /admin/api/clients/{id}` | éin klient |
| `GET /admin/api/sessions?user=&limit=` | éi liste av to slag, `kind: "oauth2"` (ein refresh-token-familie, `id` = familie-id) og `kind: "web"` (ein nettlesarsesjon), kvar med `user_id`, `username`, `created_at`, `expires_at`, og `client_id`/`client_name`/`scope` eller `ip` der dei gjeld |
| `GET /admin/api/audit?type=&since=&limit=` | revisjonshendingar med `at`, `type`, `actor` (brukar-id), `client_id`, `ip`, `request_id` og tolka `details` |
| `GET /admin/api/requests?...` | førespurnadsloggen (§5) |
| `GET /admin/api/settings` | `public_url`, `environment`, `dynamic_client_registration`, `request_log`, `ifcgraph`, `cors_origins`, `dataspatium_url`, `graph_public_bolt_url`, dei aktiverte `modules`, og kvar `OPENCDE_*`-verdi frå innstillingssida under `raw`; løyndomar utelatne |
| `GET /admin/api/health` | `ok` og `checks` (`name`, `ok`, `detail`) frå innstillingssida |

Skrivingar, med dei same kroppane som sidene brukar (`PUT` og `PATCH` blir
godtekne likt; `name` er det fulle namnet, `full_name` verkar òg):

| Endepunkt | Gjer |
|---|---|
| `POST /admin/api/users` `{username, password?, name?, email?, is_admin?, must_change_password?}` | opprettar ein brukar; utan `password` ber svaret `initial_password` éin gong |
| `PUT /admin/api/users/{id}` `{name?, email?, disabled?, is_admin?}` | endrar ein brukar; deaktivering trekkjer tilbake tokens; ikkje for din eigen konto |
| `DELETE /admin/api/users/{id}` | slettar ein brukar med sesjonar og tokens (farleg) |
| `POST /admin/api/users/{id}/reset-password` | set eit nytt passord som blir returnert éin gong, og som brukaren må byte (farleg) |
| `POST /admin/api/projects` `{name, extensions?}` · `PUT /admin/api/projects/{id}` `{name?, extensions?}` | opprettar eller endrar eit prosjekt |
| `DELETE /admin/api/projects/{id}` | slettar eit prosjekt med alt i det (farleg) |
| `PUT /admin/api/projects/{id}/members/{user_id}` `{role}` · `DELETE …/members/{user_id}` | set eller fjernar rolla til ein medlem (viewer, contributor, editor, manager) |
| `POST /admin/api/clients` `{name, redirect_uris, public?, description?, url?}` | registrerer ein klient; ein konfidensiell får `client_secret` éin gong |
| `PUT /admin/api/clients/{id}` `{name?, description?, url?, redirect_uris?, disabled?}` | endrar ein klient; deaktivering trekkjer tilbake tokena hans |
| `POST /admin/api/clients/{id}/rotate-secret` | ein ny løyndom, returnert éin gong (farleg) |
| `POST /admin/api/clients/{id}/revoke` · `DELETE /admin/api/clients/{id}` | trekkjer tilbake kvart token for klienten · slettar klienten med tokena hans (farleg) |
| `DELETE /admin/api/sessions/{id}` · `DELETE /admin/api/sessions?user=` | avsluttar éin sesjon via `id` i lista · avsluttar kvar sesjon og kvart token for ein brukar |

Farlege operasjonar krev ei **fersk innlogging**: `auth_time` til
tokenfamilien, sett då brukaren autentiserte seg for autorisasjonskoden, må
liggje innanfor dei siste ti minutta; ein refresh fornyar han aldri. Elles er
svaret `403` med `code: reauthentication_required`, som ein klient møter ved
å køyre autorisasjonsflyten igjen (ei popup-innlogging) og gjenta kallet.
Eingongsverdiar blir returnerte nøyaktig éin gong og aldri logga; kvar
skriving legg att ei revisjonshending (`admin.*`) med kallaren, klienten og
`X-Request-ID` for kallet.

### Grafspørjing (av som standard)

Når operatøren set `OPENCDE_GRAPH_QUERY_ENABLED=true`, kunngjer
kapabilitetsdokumentet `graph_query` med `url`, `max_rows` og
`timeout_seconds`, og administratorar med scopet `admin` kan køyre
**lesande** Cypher mot heile grafen, IFC-grafen inkludert, utan at
databaseporten blir publisert:

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

Radene ber JSON-verdiar: nodar som `{identity, labels, properties}`,
relasjonar som `{identity, type, start, end, properties}`, stiar som
`{nodes, relationships, length}`, tidsverdiar som ISO 8601-strengar, heiltal
som tal, punkt som `{srid, x, y, z}`, bytes som base64. Setninga køyrer i ein
lesetransaksjon; serveren avviser skrivande klausular og kvar prosedyre
bortsett frå skjemaprosedyrane (`db.labels`, `db.relationshipTypes`,
`db.propertyKeys`, `db.schema.*`), avviser setningar og parametrar som
namngjev ein verna eigenskap (`password_hash`, `secret_hash`, `token_hash`,
`code_hash`), fjernar desse eigenskapane frå kvar node, relasjon og map i
svaret og maskerer kvar Argon2-hash som når det på anna vis. Svaret stoppar
etter `max_rows` rader (`truncated: true`) og setninga etter
`timeout_seconds`. Ei avvist, mislukka eller stoppa setning svarar `400` med
`code: validation_error` og årsaka, databasen si eiga melding inkludert.
Kvart kall, avvist eller ikkje, legg att ei revisjonshending
`admin.graph.query` med dei første 500 teikna i setninga, aldri parametrane.

### Prosjektadministrasjon ved dei prosjektansvarlege (utviding)

Ein `manager` i eit prosjekt administrerer medlemmene og rollene deira utan å
vere administrator. Tokenet må bere scopet `project`, som ein klient ber om
uttrykkeleg; rolla i kvart prosjekt avgjer, og eit prosjekt den som kallar ikkje
er medlem av, svarar `404`. Eit medlem blir lagt til med eksakt brukarnamn, slik
at ein prosjektansvarleg aldri listar brukarane til serveren, og blir vist med
brukarnamn, namn og rolle. Eit prosjekt held på minst éin `manager` (elles
`409 conflict`). Namnet blir endra gjennom `PUT /bcf/3.0/projects/{project_id}`
i BCF API-et; å slette eit prosjekt er saka til administratorane. Kvar skriving
etterlèt ei revisjonshending (`manage.*`). Kapabilitetsdokumentet annonserer
det som `project_administration`.

| Call | What it does |
|---|---|
| `GET /manage/1.0/projects` | prosjekta den som kallar er prosjektansvarleg for |
| `GET /manage/1.0/projects/{project_id}/members` | medlemmene med `user_id`, `username`, `name` og `role` |
| `POST /manage/1.0/projects/{project_id}/members` | legg til `{"username", "role"}` (`201`), eller set rolla til eit medlem (`200`); `404` når brukaren ikkje finst |
| `PUT /manage/1.0/projects/{project_id}/members/{user_id}` | set `{"role"}`: `viewer`, `contributor`, `editor` eller `manager` |
| `DELETE /manage/1.0/projects/{project_id}/members/{user_id}` | fjernar medlemmen |
| `GET /manage/1.0/projects/{project_id}/teams` | teama med `team_id`, `name`, `responsible`, `members` og `ids_document_id` |
| `POST /manage/1.0/projects/{project_id}/teams` | lagar eit team av `{"name", "responsible", "members", "ids_document_id"}` (`201`); `400` når den ansvarlege ikkje er `editor` eller `manager` i prosjektet, eit medlem ikkje er i det, eller dokumentet ikkje er ein IDS i prosjektet |
| `PUT /manage/1.0/projects/{project_id}/teams/{team_id}` | erstattar teamet |
| `DELETE /manage/1.0/projects/{project_id}/teams/{team_id}` | fjernar teamet |

Delen av modellen til eit team er det spesifikasjonane i IDS-dokumentet gjeld
for. Eit endringssett som rører delen til eitt team, blir godkjent av den
ansvarlege for teamet åleine; eitt som rører delane til fleire team, eller
ingen, av ein `manager`. Prøva listar teama i `teams`; sjå
[ifc-lpg.md](ifc-lpg.md#endringssett).

## 8. Teste mot denne serveren

[Dataspatium](https://github.com/marwiss/Dataspatium) er nettlesarklienten
som blir utvikla saman med denne serveren; OpenCDE-kjelda der (innlogging,
BCF-tabellar, Documents API, grafspørjingar, request-id-ar) er eit
gjennomarbeidd døme på alt ovanfor, og live-testsuitene køyrer mot
utviklingsstakken.

- `uv run opencde seed` fyller ein tom database med demobrukarar og prosjekt
  (passorda blir skrivne ut éin gong), dømemodellen `three_walls_gtin.ifc`
  som eit dokument og éi sak med eit viewpoint og ein kommentar, alt med
  faste id-ar som ei testsuite kan stole på:

  | Kva | Id |
  |---|---|
  | Dokument (Documents API, versjon 1, prosjektet *Building permit*) | `6f5d3b2a-0000-4000-8000-000000000001` |
  | Sak (`ISSUE-0001`, type Inspection, status Open, etikett Reuse) | `6f5d3b2a-0000-4000-8000-000000000002` |
  | Viewpoint (perspektivkamera, komponent vegg `1Xezbq735AdBO_4DerG66G`) | `6f5d3b2a-0000-4000-8000-000000000003` |
  | Kommentar (av `inspector`, som viser til viewpointet) | `6f5d3b2a-0000-4000-8000-000000000004` |

  Veggene i modellen er `1Xezbq735AdBO_4DerG66G` (GTIN 3),
  `3eT96F_cnDsOufCEsotwtp` (GTIN 2) og `3k3LbXmTfDWODxdSuyCGYE` (GTIN 1),
  i eigenskapssettet `Reuse`; den same fila er `tests/fixtures/three_walls_gtin.ifc`.
- `docker compose up -d` gjev deg ein
  server på `http://127.0.0.1:8000` med Neo4j Browser på `:7484`.
- Registrer ein klient for appen din i admin-grensesnittet (`/admin` →
  Klientar) eller med
  `uv run opencde client create "My app" --redirect-uri http://127.0.0.1/callback --public`.
- `opencde_client.testing` kan fullføre innlogginga og Documents API-sidene
  utan nettlesar i automatiserte testar.
