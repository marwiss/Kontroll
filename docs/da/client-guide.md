# At bygge en klient

Hvordan en applikation taler med denne server (eller enhver OpenCDE-server).
Python-biblioteket i [client/](../../client/) gør alt dette; eksemplerne i
[examples/](../examples/) viser det i brug.

## 1. Opdag

`GET /foundation/versions` lister API'erne (`foundation 1.0`, `bcf 3.0`, `bcf 2.1`,
`documents 1.0`). `GET /foundation/1.0/auth` fortæller, hvor man logger ind:

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

En server kan indstilles til kun at tilbyde nogle af dem (`OPENCDE_APIS`). Så
indeholder listerne kun det, den tilbyder, og et API, den ikke tilbyder, svarer
404. En server til BCF API 2.1 alene har intet Foundation API: en klient finder
den gennem `GET /bcf/versions` og logger ind gennem `GET /bcf/2.1/auth`. En
dokumentserver tilbyder Foundation API og Documents API, men ingen BCF.

### Kapabilitetsdokumentet (udvidelse)

Ud over specifikationerne fortæller `GET /.well-known/dataregium` (ingen
autentificering, CORS som for API'et, kan caches i fem minutter), hvilke
udvidelser denne server har slået til, og hvilke grænser der gælder, så en
klient tilpasser sig i stedet for at prøve sig frem:

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
    "ifc_queries": {"enabled": true, "url": "/documents/1.0/documents/{document_id}/versions/{version_index}/ifc-queries", "names": ["entity", "element-classes", "elements", "storeys", "spaces", "areas", "materials", "property", "changed-since"], "max_rows": 10000},
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

Et `404` betyder en server uden udvidelser (en anden OpenCDE-server eller en
ældre Dataregium). Behandl ukendte nøgler som manglende. `ifcgraph.bolt` er kun
sat, når operatøren bevidst har offentliggjort grafdatabasen
(`OPENCDE_GRAPH_PUBLIC_BOLT_URL`); `graph_query` er kun slået til, når
operatøren har sat `OPENCDE_GRAPH_QUERY_ENABLED` (§7); `links.dataspatium`
bærer adressen på en Dataspatium-installation, når operatøren har sat
`OPENCDE_DATASPATIUM_URL`. Intet i dokumentet er hemmeligt.

## 2. Log ind (OAuth2 authorization code med PKCE)

1. Bed serverens administrator om at registrere din applikation: en
   **offentlig** klient til desktop-, mobil- og browserapps (ingen
   hemmelighed, PKCE), eller en **fortrolig** klient til en serverapplikation
   (hemmeligheden vises én gang). Registrér den nøjagtige redirect-URI; for
   native apps accepteres `http://127.0.0.1/…` (vilkårlig port).
2. Generér en `code_verifier` (43–128 URL-sikre tegn) og dens
   `code_challenge = BASE64URL(SHA256(verifier))` samt et tilfældigt `state`.
3. Åbn `oauth2_auth_url?response_type=code&client_id=…&redirect_uri=…&scope=profile bcf documents&state=…&code_challenge=…&code_challenge_method=S256`
   i brugerens browser. Brugeren logger ind og giver samtykke.
4. Browseren omdirigeres til din `redirect_uri` med `code`, `state` og
   `iss`. Tjek `state`; tjek, at `iss` er serveren.
5. `POST oauth2_token_url` med `grant_type=authorization_code`, `code`,
   `code_verifier`, `redirect_uri` og `client_id` (offentlig) eller HTTP
   Basic-autentificering (fortrolig). Svaret er `201` med `access_token`,
   `refresh_token`, `expires_in`, `scope`.
6. Send `Authorization: Bearer <access_token>` med hvert API-kald. Når den
   udløber, `POST oauth2_token_url` med `grant_type=refresh_token`;
   refresh-tokenen roterer, så gem den nye. Genbrug af en gammel
   refresh-token tilbagekalder hele familien: det er serveren, der opdager en
   stjålet token.
7. `POST oauth2_revocation_url` med refresh-tokenen, når brugeren logger ud.

Serveren understøtter aldrig implicit- eller password-grant.

### Registrering af en klient dynamisk

Når serveren kører med `OPENCDE_DYNAMIC_CLIENT_REGISTRATION=true`, bærer
`GET /foundation/1.0/auth` `oauth2_dynamic_client_reg_url`, og en klient kan
registrere sig selv (Foundation API 2.2.3, RFC 7591). En browser- eller
native applikation beder om en offentlig klient:

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

Svaret (201) bærer `client_id`, `client_id_issued_at` og de registrerede
metadata. En fortrolig klient (standardværdien for
`token_endpoint_auth_method`, `client_secret_basic`) får også sin
`client_secret` én gang, med `client_secret_expires_at: 0`. Redirect-URI'er
følger reglerne ovenfor, og kun authorization code- og refresh token-grants
findes. Send `software_id` og `software_version` (RFC 7591 §2): serveren
gemmer dem på klienten og viser dem for administratorer ved siden af
registreringen, hvilket er sådan, en operatør skelner installationer og
versioner af din applikation fra hinanden.

En server kan begrænse dette yderligere. Med `OPENCDE_DYNAMIC_CLIENT_REGISTRATION_TOKEN` sat tager kaldet den værdi som `Authorization: Bearer …` (RFC 7591 §3) og svarer 401 uden den. Med `OPENCDE_DYNAMIC_CLIENT_APPROVAL=true` kan den nye klient ikke logge nogen ind, før en administrator godkender den, og login-siden siger det. Kapabilitetsdokumentet fortæller, hvad der gælder.

Registrér én gang per installation, og gem `client_id`: en selvregistreret
klient, der ikke udsteder nogen token i `OPENCDE_DYNAMIC_CLIENT_UNUSED_DAYS`
(30 som standard), slettes sammen med sine tokens. Når token-endepunktet
derefter svarer `invalid_client`, så registrér igen.

**Pop op-vinduer.** De sider, din applikation åbner i et pop op-vindue
(autorisationssiden, Documents API'ets udvælgelses- og uploadsider og det
login, de kan kræve), isolerer ikke sig selv: de sender
`Cross-Origin-Opener-Policy: unsafe-none`, så vinduet beholder sin
`window.opener` under besøget på serveren, og din callback-side kan sende
resultatet tilbage til applikationen med `postMessage`. Kun `/admin` og
`/account` svarer med `same-origin`. Deres `form-action`-politik nævner også
origin for din redirect-URI (eller callback-URL), så browseren følger den
omdirigering, der svarer på formularen: Chromium tjekker `form-action` mod
den omdirigering, ikke kun mod formularens egen adresse.

## 3. BCF API

- Alt under `/bcf/3.0/projects/{project_id}` er afgrænset til et projekt,
  brugeren er medlem af; projekter, brugeren ikke kan se, svarer `404`.
- `GET …/extensions` giver de tilladte værdier (`topic_type`, `topic_status`,
  `topic_label`, `priority`, `stage`, `users`) og brugerens standardværdier
  for `project_actions`, `topic_actions`, `comment_actions`. Værdier uden for
  listerne afvises med `400`.
- Tilføj `?includeAuthorization=true` til en `GET` af projekter, sager,
  kommentarer eller viewpoints for at få et `authorization`-objekt per
  entitet.
- Samlinger accepterer OData: `$filter` (f.eks. `topic_status eq 'Open' and
  labels/any(l: l eq 'Safety')`), `$orderby`, `$top`, `$skip`.
- En liste uden `$top`, eller med et større end 1000, har højst 1000 poster. Når
  flere matcher, har svaret `X-Total-Count` med deres antal og `Link: <…>; rel="next"`
  med adressen på resten (en udvidelse).
- `PUT` erstatter hele objektet: send hvert felt, du vil beholde.
- Billeder i viewpoints er base64-kodet PNG eller JPEG; serveren tjekker
  bytene.
- Hver `GET` bærer en `ETag`; `If-None-Match` svarer `304`.
- Fejl er `{"message": "…"}` med de sædvanlige statuskoder (`400`, `401`,
  `403`, `404`, `409` for dublerede guid'er, `413` for for store kroppe).

### BCF API 2.1

Serveren kan også BCF API 2.1, til klienter, der ikke kender noget nyere.
`GET /foundation/versions` lister begge versioner, den nyeste først, hver med sin
`api_base_url`, og en klient til 2.1 finder samme liste på `GET /bcf/versions`.
Begge versioner arbejder på de samme data, så en sag, der er oprettet gennem den ene,
kan læses og ændres gennem den anden.

| | 2.1, under `/bcf/2.1` | 3.0, under `/bcf/3.0` |
|---|---|---|
| Versioner, login, brugeren | `/bcf/versions`, `/bcf/2.1/auth`, `/bcf/2.1/current-user` | Foundation API |
| En fil i en sags hoved | `file_name` | `filename` |
| Brugerne i extensions | `user_id_type` | `users` |
| En sags korte id | Intet | `server_assigned_id` |
| En kommentar, der svarer på en anden | `reply_to_comment_guid` | Intet |
| Et kameras `aspect_ratio` | Intet; 3.0 læser det som 1.0 | Påkrævet |
| Hvad et viewpoint skal indeholde | Hvad som helst undtagen to kameraer | Et kamera eller et billede, og et kamera sammen med alt andet |
| Et `guid`, klienten vælger | Ignoreres | Accepteres, `409` hvis det findes |
| `files_information`, at slette et viewpoint | Intet | Ja |
| Egne hændelsestyper | `reply_to_comment_updated`, `reply_to_comment_removed` | `stage_added`, `stage_updated`, `stage_removed` |
| At spørge efter en label i `$filter` | `contains(labels, 'x')` | `labels/any(l: l eq 'x')`; den anden form virker også |

OAuth2-eksemplet i 2.1 kender ikke til PKCE, så en klient, der er skrevet efter det,
kan ikke sende nogen `code_challenge`. En administrator kan markere en fortrolig
klient, der må udelade det: *Må logge ind uden PKCE* på klientens side, `pkce_optional`
i administrations-API'et eller `opencde client create --without-pkce`. Så er det dens
hemmelighed, der beskytter loginene, angivet med HTTP Basic på token-adressen. En
klient, der registrerer sig selv på `oauth2_dynamic_client_reg_url` i `GET /bcf/2.1/auth`,
når `OPENCDE_DYNAMIC_CLIENT_REGISTRATION=true`, markeres på samme måde, mens
registreringen i Foundation API ikke markerer nogen klient. En offentlig klient kan
aldrig udelade PKCE, og en markeret klient, der sender en `code_challenge`, holdes til
den. Brug PKCE, hvis du kan. En redirect-URI på `http://localhost` kræver
`OPENCDE_ALLOW_LOCALHOST_REDIRECTS=true`.

## 4. Documents API

Forløbene involverer brugerens browser; se [flows/documents.md](flows/documents.md).
Din klient har brug for en callback-URL, som browseren kan nå (en
loopback-lytter for desktopapps). Serveren kalder aldrig selv den URL.

Når IFC-LPG-modulet er slået til, kontrolleres en IFC-fil, der uploades som
version, mod IFC-skemaet og, hvor serveren har dem, buildingSMARTs
ifc-gherkin-rules. Dens metadata har da `ifc_validation_status` og, når
den er kontrolleret, de andre `ifc_validation_*`-poster; `ifc_validation_report`
er adressen på rapporten, en udvidelse, der svarer på det samme token. Se
[ifc-lpg.md](ifc-lpg.md#kontrol-af-uploads-mod-ifc-skemaet).

En version, der rummer en IFC-model, kan også få navngivne forespørgsler, som
dens etager, rummenes areal eller en egenskabs værdi. Det er en udvidelse, der
svarer på det samme token, og som kapabilitetsdokumentet annoncerer i
`ifc_queries`. Se [ifc-lpg.md](ifc-lpg.md#navngivne-forespørgsler).

To IFC-versioner i et projekt kan sammenlignes for kollisioner på samme måde, en
udvidelse, der annonceres som `ifc_clash`. Se [ifc-lpg.md](ifc-lpg.md#kollisionskontrol).

En fil kan kontrolleres, før den uploades, en udvidelse, der annonceres som
`ifc_precheck`, og et projekt kan afvise filer med fejl. Se
[ifc-lpg.md](ifc-lpg.md#afvise-filer-med-fejl-og-kontrollere-en-fil-på-forhånd).

En ændring af en model foreslås som en BCF-sag, hvis `bim_snippet` er et
ændringssæt, en form, der annonceres som `ifc_changes`. Se
[ifc-lpg.md](ifc-lpg.md#ændringssæt).

To IFC-versioner sammenlignes element for element med `ifc_diff`, efter
GlobalId og sti. Se [ifc-lpg.md](ifc-lpg.md#sammenligne-to-versioner).

Geometrien i en IFC-version kommer som binær glTF med `ifc_geometry` (`lod=full` eller `box`, `classes`, `storey`),
og hver bygningsdel har sin kasse i grafen. Se [ifc-lpg.md](ifc-lpg.md#hvor-bygningsdelene-er-og-geometrien).

En `manager` publicerer en version med `publication`: `POST …/versions/{index}/publication` gemmer filen som ét
arkiv, `.ifczip` for en IFC-fil og `.zip` for en anden fil, og versionens metadata får `published_at`,
`published_by` og `publication`. En version publiceres én gang, og ikke mens den kontrolleres, eller når kontrollen
har fundet fejl. `GET …/publication` viser alle medlemmer, hvem der publicerede den og hvornår, og
`…/publication/download` giver arkivet.

En bygning fra en anden model kommer ind i en model i projektet som dens næste version med `ifc_merge`, med
en rapport først og et valg for hvert objekt, der er forskelligt. Se [ifc-lpg.md](ifc-lpg.md#en-bygning-ind-i-en-anden-model).

## 5. Korrelering af din log med serverens

Send en `X-Request-ID`-header (1–128 tegn fra `A-Za-z0-9._-`) med hver
forespørgsel, så ekkoer serveren den i svaret og binder den til sine egne
loglinjer; uden en sådan laver serveren et id og returnerer det. Headeren er
tilladt i CORS-preflights og eksponeret for browserklienter.

Når operatøren har slået forespørgselsloggen til (`OPENCDE_REQUEST_LOG_ENABLED`,
en udvidelse uden for specifikationerne), kan en administrator se serversiden
af hvert kald på `/admin/requests`, og en administrationsklient kan læse de
samme poster som JSON:

```http
GET /admin/api/requests?client_id=<your client id>&since=2026-11-05T10:00:00Z&limit=200
Authorization: Bearer <token with the admin scope>
```

Tokenen skal bære scopet `admin`, som en klient beder om udtrykkeligt
(`scope=profile bcf documents admin`), og brugeren skal være administrator.
Posterne indeholder metode, sti, operation, status, tid, request-id, bytetal
og kalderen, aldrig kroppe eller tokens. JSON-administrations-API'et
serveres, så længe `OPENCDE_ADMIN_API_ENABLED` er sand (standard), uafhængigt
af HTML-administrationen; kapabilitetsdokumentet (§1) fortæller, om det er
slået til.

## 6. Fejl

Enhver fejl svarer med Foundation API 1.6's krop, `{"message": "..."}`, og
aldrig med stakspor eller gentaget input. Som en udvidelse bærer enhver fejl,
serveren selv former, også en stabil `code`, som din applikation kan handle på
eller oversætte, mens `message` forbliver en engelsk sætning til mennesker:

```json
{"message": "This operation needs the 'admin' scope", "code": "insufficient_scope"}
```

API-dokumentet (`/openapi.json`) angiver `400` med denne krop for en forespørgsel,
som serveren ikke kan læse, som serveren svarer, hvor FastAPI selv ville angive `422`.

| `code` | Status | Hvornår | Hvad en klient gør |
|---|---|---|---|
| `validation_error` | 400 | Kroppen eller forespørgslen bestod ikke valideringen, et OData-udtryk kunne ikke kompileres, en værdi findes ikke i projektets extensions, et `Content-Range` eller en uploadinstruktion er forkert, et snapshot eller en bitmap er ikke PNG eller JPEG; `message` nævner feltet | Ret forespørgslen |
| `localhost_redirect` | 400 | En registrering angav `http://localhost` som redirect-URI, hvilket denne server ikke tillader | Registrér `http://127.0.0.1` i stedet, eller fortæl operatøren om `OPENCDE_ALLOW_LOCALHOST_REDIRECTS` |
| `unauthenticated` | 401 | Ingen bearer-token | Log ind |
| `invalid_token` | 401 | Tokenen er ukendt, udløbet eller tilbagekaldt (`WWW-Authenticate: Bearer error="invalid_token"`) | Forny, og log derefter ind igen |
| `insufficient_scope` | 403 | Tokenen mangler det scope, ruten kræver, såsom `admin` | Autorisér igen med det scope |
| `forbidden` | 403 | Brugerens rolle i projektet tillader ikke handlingen (Foundation API 1.5), eller brugeren er ikke administrator på administrations-API'et | Vis beskeden |
| `reauthentication_required` | 403 | En farlig administrationshandling, og loginet er ældre end ti minutter | Autorisér igen, og gentag derefter kaldet |
| `not_found` | 404 | Ingen sådan ressource, en ressource uden for brugerens projekter, eller en funktion, der er slået fra (registrering, forespørgselslog, administrations-API) | Vis beskeden, genindlæs listerne |
| `conflict` | 409 | Et guid, der allerede findes, eller et dubleret link | Hent igen |
| `version_conflict` | 412 | Uploaden angav `base_version_index`, og dokumentet har allerede en nyere version; eller et ændringssæt kolliderer med det, der er ændret siden dets basis, angivet i `conflicts`, med de tre værdier for hver i `conflict_details` | Hent den seneste version, flet og upload igen |
| `ifc_validation_failed` | 422 | Projektet afviser filer med valideringsfejl, og filen har nogle; `report` i kroppen er rapportens adresse | Vis rapporten, lad brugeren rette filen og upload igen |
| `payload_too_large` | 413 | Forespørgslens krop er over serverens grænse, eller en BCF-binær er over `max_image_bytes`/`max_upload_bytes` | Ret forespørgslen |
| `upload_too_large` | 413 | En valgt fil eller del er over uploadgrænsen (`max_size_in_bytes` i uploadinstruktionerne) | Fortæl brugeren grænsen |
| `rate_limited` | 429 | For mange forespørgsler fra én adresse; `Retry-After` siger hvornår | Vent, og prøv igen |
| `internal_error` | 500 | En uventet fejl; `message` er altid "Internal server error" | Rapportér med `X-Request-ID` |
| `unavailable` | 503 | Grafdatabasen kan ikke nås | Prøv igen senere |

Listen er lukket: en kode, du ikke kender, behandles som en manglende, og du
viser `message`. Statusser, som rammeværket svarer med på egen hånd (405,
415), bærer ingen kode. OAuth2-token-endepunktet beholder RFC 6749's eget
format (`{"error": "invalid_grant", "error_description": "..."}`), som
specifikationen kræver, så handl på `error` dér (`invalid_request`,
`invalid_client`, `invalid_grant`, `unauthorized_client`,
`unsupported_grant_type`, `invalid_scope`). Kapabilitetsdokumentet (§1)
serveres af enhver server, der udsender koder.

## 7. Administrations-API'et (udvidelse)

En administrationsklient (Dataspatiums fane Administration er den første)
læser det, siderne under `/admin` viser, som JSON under `/admin/api/`, med en
bearer-token, der bærer scopet `admin` og tilhører en administrator.
Kapabilitetsdokumentet fortæller, om API'et er slået til
(`extensions.admin_api`), og hvilken version det har. Lister svarer
`{"items": [...], "total": n}` og tager `limit` (200 som standard, højst
1000) samt `q` eller `since`, hvor det er angivet; fejl bruger kroppen fra §6.

| Endepunkt | Returnerer |
|---|---|
| `GET /admin/api/overview` | `version`, `uptime_s`, `dialect`, `graph_ok`, tallene `users`, `projects`, `clients`, `sessions`, `topics`, `documents`, `models`, og `request_log` (`enabled`, `rows`) |
| `GET /admin/api/users?q=&limit=` | brugere (`id`, `username`, `name`, `email`, `is_admin`, `disabled`, `must_change_password`, `created_at`, `last_sign_in_at`, `projects` som `[{project_id, role}]`); `q` søger i brugernavn, navn og e-mail |
| `GET /admin/api/users/{id}` | én bruger; `projects` bærer også projektets `name` |
| `GET /admin/api/projects?q=` | projekter med `members` (`user_id`, `username`, `role`) og tallene `topics`, `documents`, `models` |
| `GET /admin/api/projects/{id}` | ét projekt, også med dets `extensions` |
| `GET /admin/api/clients` | klienter (`client_id`, `name`, `description`, `url`, `public`, `dynamic`, `redirect_uris`, `disabled`, `created_at`, `expires_at`, `last_used_at`, `software_id`, `software_version`), aldrig en hemmelighed |
| `GET /admin/api/clients/{id}` | én klient |
| `GET /admin/api/sessions?user=&limit=` | én liste af to slags, `kind: "oauth2"` (en refresh-token-familie, `id` = familie-id) og `kind: "web"` (en browsersession), hver med `user_id`, `username`, `created_at`, `expires_at`, og `client_id`/`client_name`/`scope` eller `ip`, hvor de gælder |
| `GET /admin/api/audit?type=&since=&limit=` | revisionshændelser med `at`, `type`, `actor` (bruger-id), `client_id`, `ip`, `request_id` og fortolkede `details` |
| `GET /admin/api/requests?...` | forespørgselsloggen (§5) |
| `GET /admin/api/settings` | `public_url`, `environment`, `dynamic_client_registration`, `request_log`, `ifcgraph`, `cors_origins`, `dataspatium_url`, `graph_public_bolt_url`, de aktiverede `modules`, og hver `OPENCDE_*`-værdi fra indstillingssiden under `raw`; hemmeligheder udeladt |
| `GET /admin/api/health` | `ok` og indstillingssidens `checks` (`name`, `ok`, `detail`) |

Skrivninger, med de samme kroppe som siderne bruger (`PUT` og `PATCH`
accepteres ens; `name` er det fulde navn, `full_name` virker også):

| Endepunkt | Gør |
|---|---|
| `POST /admin/api/users` `{username, password?, name?, email?, is_admin?, must_change_password?}` | opretter en bruger; uden `password` bærer svaret `initial_password` én gang |
| `PUT /admin/api/users/{id}` `{name?, email?, disabled?, is_admin?}` | ændrer en bruger; deaktivering tilbagekalder tokens; ikke for din egen konto |
| `DELETE /admin/api/users/{id}` | sletter en bruger med sessioner og tokens (farlig) |
| `POST /admin/api/users/{id}/reset-password` | sætter et nyt kodeord, der returneres én gang, og som brugeren skal skifte (farlig) |
| `POST /admin/api/projects` `{name, extensions?}` · `PUT /admin/api/projects/{id}` `{name?, extensions?}` | opretter eller ændrer et projekt |
| `DELETE /admin/api/projects/{id}` | sletter et projekt med alt i det (farlig) |
| `PUT /admin/api/projects/{id}/members/{user_id}` `{role}` · `DELETE …/members/{user_id}` | sætter eller fjerner et medlems rolle (viewer, contributor, editor, manager) |
| `POST /admin/api/clients` `{name, redirect_uris, public?, description?, url?}` | registrerer en klient; en fortrolig får `client_secret` én gang |
| `PUT /admin/api/clients/{id}` `{name?, description?, url?, redirect_uris?, disabled?}` | ændrer en klient; deaktivering tilbagekalder dens tokens |
| `POST /admin/api/clients/{id}/rotate-secret` | en ny hemmelighed, returneret én gang (farlig) |
| `POST /admin/api/clients/{id}/revoke` · `DELETE /admin/api/clients/{id}` | tilbagekalder hver token for klienten · sletter klienten med dens tokens (farlig) |
| `DELETE /admin/api/sessions/{id}` · `DELETE /admin/api/sessions?user=` | afslutter én session via listens `id` · afslutter hver session og token for en bruger |

Farlige operationer kræver et **friskt login**: tokenfamiliens `auth_time`,
sat da brugeren autentificerede sig for autorisationskoden, skal ligge inden
for de seneste ti minutter; en refresh fornyer den aldrig. Ellers er svaret
`403` med `code: reauthentication_required`, som en klient håndterer ved at
køre autorisationsforløbet igen (et pop op-login) og gentage kaldet.
Engangsværdier returneres præcis én gang og logges aldrig; hver skrivning
efterlader en revisionshændelse (`admin.*`) med kalderen, klienten og kaldets
`X-Request-ID`.

### Grafforespørgsel (slået fra som standard)

Når operatøren sætter `OPENCDE_GRAPH_QUERY_ENABLED=true`, annoncerer
kapabilitetsdokumentet `graph_query` med `url`, `max_rows` og
`timeout_seconds`, og administratorer med scopet `admin` må køre **læsende**
Cypher mod hele grafen, IFC-grafen inklusive, uden at databaseporten
offentliggøres:

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

Rækkerne bærer JSON-værdier: noder som `{identity, labels, properties}`,
relationer som `{identity, type, start, end, properties}`, stier som
`{nodes, relationships, length}`, tidsværdier som ISO 8601-strenge, heltal
som tal, punkter som `{srid, x, y, z}`, bytes som base64. Udsagnet kører i en
læsetransaktion; serveren afviser skrivende klausuler og enhver procedure
bortset fra skemaprocedurerne (`db.labels`, `db.relationshipTypes`,
`db.propertyKeys`, `db.schema.*`), afviser udsagn og parametre, der nævner en
beskyttet egenskab (`password_hash`, `secret_hash`, `token_hash`,
`code_hash`), fjerner disse egenskaber fra hver node, relation og map i
svaret og maskerer enhver Argon2-hash, der når det ad anden vej. Svaret
stopper efter `max_rows` rækker (`truncated: true`) og udsagnet efter
`timeout_seconds`. Et afvist, fejlet eller stoppet udsagn svarer `400` med
`code: validation_error` og årsagen, databasens egen besked inklusive. Hvert
kald, afvist eller ej, efterlader en revisionshændelse `admin.graph.query`
med udsagnets første 500 tegn, aldrig parametrene.

### Projektadministration ved de projektansvarlige (udvidelse)

En `manager` i et projekt administrerer dets medlemmer og deres roller uden at
være administrator. Tokenet skal bære scopet `project`, som en klient beder om
udtrykkeligt; rollen i hvert projekt afgør det, og et projekt, kalderen ikke er
medlem af, svarer `404`. Et medlem tilføjes med præcist brugernavn, så en
projektansvarlig aldrig lister serverens brugere, og vises med brugernavn,
navn og rolle. Et projekt beholder mindst én `manager` (ellers `409 conflict`).
Navnet ændres gennem BCF API'ets `PUT /bcf/3.0/projects/{project_id}`; at slette
et projekt er administratorernes sag. Hver skrivning efterlader en
revisionshændelse (`manage.*`). Kapabilitetsdokumentet annoncerer det som
`project_administration`.

| Call | What it does |
|---|---|
| `GET /manage/1.0/projects` | de projekter, kalderen er projektansvarlig for |
| `GET /manage/1.0/projects/{project_id}/members` | medlemmerne med `user_id`, `username`, `name` og `role` |
| `POST /manage/1.0/projects/{project_id}/members` | tilføjer `{"username", "role"}` (`201`) eller sætter et medlems rolle (`200`); `404`, når brugeren ikke findes |
| `PUT /manage/1.0/projects/{project_id}/members/{user_id}` | sætter `{"role"}`: `viewer`, `contributor`, `editor` eller `manager` |
| `DELETE /manage/1.0/projects/{project_id}/members/{user_id}` | fjerner medlemmet |
| `GET /manage/1.0/projects/{project_id}/teams` | holdene med `team_id`, `name`, `responsible`, `members` og `ids_document_id` |
| `POST /manage/1.0/projects/{project_id}/teams` | laver et hold af `{"name", "responsible", "members", "ids_document_id"}` (`201`); `400` når den ansvarlige ikke er `editor` eller `manager` i projektet, et medlem ikke er i det, eller dokumentet ikke er en IDS i projektet |
| `PUT /manage/1.0/projects/{project_id}/teams/{team_id}` | erstatter holdet |
| `DELETE /manage/1.0/projects/{project_id}/teams/{team_id}` | fjerner holdet |

Et holds del af modellen er det, specifikationerne i dets IDS-dokument gælder
for. Et ændringssæt, der rører ét holds del, godkendes af holdets ansvarlige
alene; et, der rører flere holds dele eller ingens, af en `manager`. Prøven
lister holdene i `teams`; se [ifc-lpg.md](ifc-lpg.md#ændringssæt).

## 8. Test mod denne server

[Dataspatium](https://github.com/marwiss/Dataspatium) er browserklienten, der
udvikles sammen med denne server; dens OpenCDE-kilde (login, BCF-tabeller,
Documents API, grafforespørgsler, request-id'er) er et gennemarbejdet
eksempel på alt ovenstående, og dens live-testsuiter kører mod
udviklingsstakken.

- `uv run opencde seed` fylder en tom database med demobrugere og projekter
  (kodeordene udskrives én gang), eksempelmodellen `three_walls_gtin.ifc`
  som et dokument og én sag med et viewpoint og en kommentar, alt med faste
  id'er, som en testsuite kan regne med:

  | Hvad | Id |
  |---|---|
  | Dokument (Documents API, version 1, projektet *Building permit*) | `6f5d3b2a-0000-4000-8000-000000000001` |
  | Sag (`ISSUE-0001`, type Inspection, status Open, etiket Reuse) | `6f5d3b2a-0000-4000-8000-000000000002` |
  | Viewpoint (perspektivkamera, komponent væg `1Xezbq735AdBO_4DerG66G`) | `6f5d3b2a-0000-4000-8000-000000000003` |
  | Kommentar (af `inspector`, der henviser til viewpointet) | `6f5d3b2a-0000-4000-8000-000000000004` |

  Modellens vægge er `1Xezbq735AdBO_4DerG66G` (GTIN 3),
  `3eT96F_cnDsOufCEsotwtp` (GTIN 2) og `3k3LbXmTfDWODxdSuyCGYE` (GTIN 1),
  i egenskabssættet `Reuse`; den samme fil er `tests/fixtures/three_walls_gtin.ifc`.
- `docker compose up -d` giver dig en
  server på `http://127.0.0.1:8000` med Neo4j Browser på `:7484`.
- Registrér en klient til din app i admin-grænsefladen (`/admin` → Klienter)
  eller med
  `uv run opencde client create "My app" --redirect-uri http://127.0.0.1/callback --public`.
- `opencde_client.testing` kan gennemføre loginet og Documents API-siderne
  uden browser i automatiserede tests.
