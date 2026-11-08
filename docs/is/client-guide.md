# Að smíða biðlara

Hvernig forrit talar við þennan þjón (eða hvaða OpenCDE-þjón sem er).
Python-safnið í [client/](../../client/) gerir allt þetta; dæmin í
[examples/](../examples/) sýna það í notkun.

## 1. Uppgötvun

`GET /foundation/versions` telur upp forritaskilin (`foundation 1.0`,
`bcf 3.0`, `bcf 2.1`, `documents 1.0`). `GET /foundation/1.0/auth` segir hvar skal skrá
sig inn:

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

Hægt er að stilla þjón svo að hann bjóði aðeins sum þeirra (`OPENCDE_APIS`). Þá
innihalda listarnir aðeins það sem hann býður, og forritaskil sem hann býður
ekki svara 404. Þjónn sem býður aðeins BCF API 2.1 hefur ekkert Foundation API:
biðlari finnur hann með `GET /bcf/versions` og skráir sig inn með `GET
/bcf/2.1/auth`. Skjalaþjónn býður Foundation API og Documents API en ekkert BCF.

### Getuskjalið (viðbót)

Umfram forskriftirnar segir `GET /.well-known/kontroll` (engin auðkenning,
CORS eins og fyrir forritaskilin, má geyma í skyndiminni í fimm mínútur)
hvaða viðbætur þessi þjónn hefur kveikt á og hvaða takmörk gilda, svo að
biðlari aðlagi sig í stað þess að þreifa fyrir sér:

```json
{
  "server": {"name": "Kontroll OpenCDE server", "version": "3.0.0", "public_url": "https://cde.example.org"},
  "apis": {"foundation": "1.0", "bcf": "3.0", "documents": "1.0"},
  "scopes": ["profile", "bcf", "documents", "admin"],
  "extensions": {
    "dynamic_client_registration": {"enabled": true, "public_clients": true, "initial_access_token": false, "approval": false, "unused_days": 30,
                                    "url": "/foundation/oauth2/reg"},
    "request_log": {"enabled": true, "retention_hours": 72, "url": "/admin/api/requests"},
    "admin_api": {"enabled": true, "version": 1, "url": "/admin/api", "scope": "admin"},
    "ifcgraph": {"enabled": true, "bolt": null},
    "ifc_queries": {"enabled": true, "url": "/documents/1.0/documents/{document_id}/versions/{version_index}/ifc-queries", "names": ["element-classes", "elements", "storeys", "spaces", "areas", "materials", "property"], "max_rows": 10000},
    "graph_query": {"enabled": true, "url": "/admin/api/graph/query", "max_rows": 1000, "timeout_seconds": 10.0}
  },
  "limits": {"max_upload_bytes": 1073741824, "max_image_bytes": 10485760, "access_token_ttl_seconds": 3600},
  "links": {"dataspatium": null}
}
```

`404` þýðir þjónn án viðbóta (annar OpenCDE-þjónn, eða eldri Kontroll).
Meðhöndlaðu óþekkta lykla sem fjarverandi. `ifcgraph.bolt` er aðeins sett
þegar rekstraraðilinn hefur af ásettu ráði birt grafgagnagrunninn
(`OPENCDE_GRAPH_PUBLIC_BOLT_URL`); `graph_query` er aðeins virkt þegar
rekstraraðilinn hefur sett `OPENCDE_GRAPH_QUERY_ENABLED` (§7);
`links.dataspatium` ber vistfang Dataspatium-uppsetningar þegar
rekstraraðilinn hefur sett `OPENCDE_DATASPATIUM_URL`. Ekkert í skjalinu er
leynilegt.

## 2. Innskráning (OAuth2 authorization code með PKCE)

1. Biddu stjórnanda þjónsins að skrá forritið þitt: **opinberan** biðlara
   fyrir skjáborðs-, far- og vafraforrit (ekkert leyndarmál, PKCE), eða
   **trúnaðarbiðlara** fyrir þjónsforrit (leyndarmálið sýnt einu sinni).
   Skráðu nákvæma redirect-URI; fyrir innbyggð forrit er
   `http://127.0.0.1/…` (hvaða gátt sem er) samþykkt.
2. Búðu til `code_verifier` (43–128 URL-örugg tákn) og
   `code_challenge = BASE64URL(SHA256(verifier))` hans, auk slembins `state`.
3. Opnaðu `oauth2_auth_url?response_type=code&client_id=…&redirect_uri=…&scope=profile bcf documents&state=…&code_challenge=…&code_challenge_method=S256`
   í vafra notandans. Notandinn skráir sig inn og veitir samþykki.
4. Vafranum er áframsent á `redirect_uri` þitt með `code`, `state` og `iss`.
   Athugaðu `state`; athugaðu að `iss` sé þjónninn.
5. `POST oauth2_token_url` með `grant_type=authorization_code`, `code`,
   `code_verifier`, `redirect_uri` og `client_id` (opinber) eða HTTP
   Basic-auðkenningu (trúnaðar). Svarið er `201` með `access_token`,
   `refresh_token`, `expires_in`, `scope`.
6. Sendu `Authorization: Bearer <access_token>` með hverju kalli á
   forritaskilin. Þegar hann rennur út, `POST oauth2_token_url` með
   `grant_type=refresh_token`; endurnýjunartókinn skiptist, svo geymdu nýja.
   Endurnotkun gamals endurnýjunartóka afturkallar alla fjölskylduna:
   þannig verður þjónninn var við stolinn tóka.
7. `POST oauth2_revocation_url` með endurnýjunartókanum þegar notandinn
   skráir sig út.

Þjónninn styður aldrei implicit- eða password-veitingar.

### Að skrá biðlara á kvikan hátt

Þegar þjónninn keyrir með `OPENCDE_DYNAMIC_CLIENT_REGISTRATION=true` ber
`GET /foundation/1.0/auth` `oauth2_dynamic_client_reg_url` og biðlari getur
skráð sig sjálfur (Foundation API 2.2.3, RFC 7591). Vafra- eða innbyggt
forrit biður um opinberan biðlara:

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

Svarið (201) ber `client_id`, `client_id_issued_at` og skráðu lýsigögnin.
Trúnaðarbiðlari (sjálfgefið `token_endpoint_auth_method`,
`client_secret_basic`) fær einnig `client_secret` sitt einu sinni, með
`client_secret_expires_at: 0`. Redirect-URI fylgja reglunum að ofan, og
aðeins authorization code- og refresh token-veitingarnar eru til. Sendu
`software_id` og `software_version` (RFC 7591 §2): þjónninn geymir þau á
biðlaranum og sýnir stjórnendum þau við hlið skráningarinnar, og þannig
greinir rekstraraðili uppsetningar og útgáfur forritsins þíns í sundur.

Þjónn getur takmarkað þetta frekar. Með `OPENCDE_DYNAMIC_CLIENT_REGISTRATION_TOKEN` stillt tekur kallið það gildi sem `Authorization: Bearer …` (RFC 7591 §3) og svarar 401 án þess. Með `OPENCDE_DYNAMIC_CLIENT_APPROVAL=true` getur nýi biðlarinn ekki skráð neinn inn fyrr en stjórnandi samþykkir hann, og innskráningarsíðan segir það. Getuskjalið segir hvað gildir.

Skráðu einu sinni fyrir hverja uppsetningu og geymdu `client_id`: sjálfskráður
biðlari sem gefur út engan tóka í `OPENCDE_DYNAMIC_CLIENT_UNUSED_DAYS` daga
(30 sjálfgefið) er eytt ásamt tókum sínum. Þegar tókaendapunkturinn svarar
síðan `invalid_client`, skráðu aftur.

**Sprettigluggar.** Síðurnar sem forritið þitt opnar í sprettiglugga
(heimildarsíðan, val- og upphalssíður Documents API og innskráningin sem þær
geta þurft) einangra sig ekki: þær senda
`Cross-Origin-Opener-Policy: unsafe-none`, svo glugginn heldur
`window.opener` sínum meðan heimsóknin á þjóninn stendur og callback-síðan
þín getur sent niðurstöðuna aftur til forritsins með `postMessage`. Aðeins
`/admin` og `/account` svara með `same-origin`. `form-action`-stefna þeirra
nefnir líka uppruna redirect-URI þíns (eða callback-URL), svo vafrinn fylgi
áframsendingunni sem svarar eyðublaðinu: Chromium athugar `form-action` gegn
þeirri áframsendingu, ekki aðeins gegn vistfangi eyðublaðsins sjálfs.

## 3. BCF API

- Allt undir `/bcf/3.0/projects/{project_id}` er afmarkað við verkefni sem
  notandinn er meðlimur í; verkefni sem notandinn getur ekki séð svara `404`.
- `GET …/extensions` gefur leyfilegu gildin (`topic_type`, `topic_status`,
  `topic_label`, `priority`, `stage`, `users`) og sjálfgefin
  `project_actions`, `topic_actions`, `comment_actions` notandans. Gildum
  utan listanna er hafnað með `400`.
- Bættu `?includeAuthorization=true` við `GET` á verkefnum, málum,
  athugasemdum eða viewpoint til að fá `authorization`-hlut fyrir hverja
  einingu.
- Söfn taka við OData: `$filter` (t.d. `topic_status eq 'Open' and
  labels/any(l: l eq 'Safety')`), `$orderby`, `$top`, `$skip`.
- `PUT` kemur í stað alls hlutarins: sendu hvert svið sem þú vilt halda.
- Myndir í viewpoint eru base64-kóðuð PNG eða JPEG; þjónninn athugar bætin.
- Hvert `GET` ber `ETag`; `If-None-Match` svarar `304`.
- Villur eru `{"message": "…"}` með venjulegu stöðukóðunum (`400`, `401`,
  `403`, `404`, `409` fyrir tvítekin guid, `413` fyrir of stór meginmál).

### BCF API 2.1

Þjónninn kann líka BCF API 2.1, fyrir biðlara sem þekkja ekkert nýrra.
`GET /foundation/versions` telur upp báðar útgáfurnar, þá nýjustu fyrst, hvora með sitt
`api_base_url`, og biðlari fyrir 2.1 finnur sama lista á `GET /bcf/versions`.
Báðar útgáfurnar vinna með sömu gögn, svo mál sem er búið til í gegnum aðra má lesa og
breyta í gegnum hina.

| | 2.1, undir `/bcf/2.1` | 3.0, undir `/bcf/3.0` |
|---|---|---|
| Útgáfur, innskráning, notandinn | `/bcf/versions`, `/bcf/2.1/auth`, `/bcf/2.1/current-user` | Foundation API |
| Skrá í haus máls | `file_name` | `filename` |
| Notendurnir í extensions | `user_id_type` | `users` |
| Stutt auðkenni máls | Ekkert | `server_assigned_id` |
| Athugasemd sem svarar annarri | `reply_to_comment_guid` | Ekkert |
| `aspect_ratio` myndavélar | Ekkert; 3.0 les það sem 1.0 | Áskilið |
| Hvað sjónarhorn verður að innihalda | Hvað sem er nema tvær myndavélar | Myndavél eða mynd, og myndavél með öllu öðru |
| `guid` sem biðlarinn velur | Hunsað | Samþykkt, `409` ef það er til |
| `files_information`, að eyða sjónarhorni | Ekkert | Já |
| Eigin atburðagerðir | `reply_to_comment_updated`, `reply_to_comment_removed` | `stage_added`, `stage_updated`, `stage_removed` |
| Að spyrja um merki í `$filter` | `contains(labels, 'x')` | `labels/any(l: l eq 'x')`; hitt formið virkar líka |

OAuth2-dæmið í 2.1 þekkir ekki PKCE, svo biðlari sem er skrifaður eftir því getur ekki
sent neitt `code_challenge`. Stjórnandi getur merkt trúnaðarbiðlara sem má sleppa því:
*Má skrá sig inn án PKCE* á síðu biðlarans, `pkce_optional` í stjórnunarforritaskilunum
eða `opencde client create --without-pkce`. Þá er það leyndarmál hans sem verndar
innskráningarnar, gefið með HTTP Basic á tókaslóðinni. Biðlari sem skráir sig sjálfur á
`oauth2_dynamic_client_reg_url` í `GET /bcf/2.1/auth`, þegar
`OPENCDE_DYNAMIC_CLIENT_REGISTRATION=true`, er merktur á sama hátt, en skráningin í
Foundation API merkir engan biðlara. Opinber biðlari getur aldrei sleppt PKCE, og merktur
biðlari sem sendir `code_challenge` er bundinn við það. Notaðu PKCE ef þú getur.
Redirect-URI á `http://localhost` krefst `OPENCDE_ALLOW_LOCALHOST_REDIRECTS=true`.

## 4. Documents API

Ferlin snerta vafra notandans; sjá [flows/documents.md](flows/documents.md).
Biðlarinn þinn þarf callback-URL sem vafrinn nær í (loopback-hlustara fyrir
skjáborðsforrit). Þjónninn kallar aldrei sjálfur á þá URL.

Þegar IFC-LPG-einingin er virk er IFC-skrá sem hlaðið er upp sem útgáfu prófuð
gagnvart IFC-skemanu og, þar sem þjónninn hefur þær, ifc-gherkin-rules frá
buildingSMART. Lýsigögn hennar hafa þá `ifc_validation_status` og, þegar
hún hefur verið prófuð, hinar `ifc_validation_*`-færslurnar;
`ifc_validation_report` er slóð skýrslunnar, viðbót sem svarar sama tóka. Sjá
[ifc-lpg.md](ifc-lpg.md#prófun-upphalaðra-skráa-gagnvart-ifc-skemanu).

Útgáfu sem geymir IFC-líkan má líka spyrja nefndra fyrirspurna, svo sem um
hæðir hennar, flatarmál rýma eða gildi eiginleika. Það er viðbót sem svarar
sama tóka og getuskjalið kynnir í `ifc_queries`. Sjá
[ifc-lpg.md](ifc-lpg.md#nefndar-fyrirspurnir).

## 5. Að tengja atvikaskrá þína við þjónsins

Sendu `X-Request-ID`-haus (1–128 tákn úr `A-Za-z0-9._-`) með hverri beiðni
og þjónninn endurómar hann í svarinu og bindur hann við eigin skrárlínur;
án hans býr þjónninn til auðkenni og skilar því. Hausinn er leyfður í
CORS-forathugunum og sýnilegur vafrabiðlurum.

Þegar rekstraraðilinn hefur kveikt á beiðnaskránni
(`OPENCDE_REQUEST_LOG_ENABLED`, viðbót utan forskriftanna) getur stjórnandi
séð þjónshlið hvers kalls á `/admin/requests`, og stjórnunarbiðlari getur
lesið sömu færslur sem JSON:

```http
GET /admin/api/requests?client_id=<your client id>&since=2026-11-05T10:00:00Z&limit=200
Authorization: Bearer <token with the admin scope>
```

Tókinn þarf að bera heimildina `admin`, sem biðlari biður um sérstaklega
(`scope=profile bcf documents admin`), og notandinn þarf að vera stjórnandi.
Færslurnar geyma aðferð, slóð, aðgerð, stöðu, tímalengd, request-id,
bætafjölda og þann sem kallaði, aldrei meginmál eða tóka.
JSON-stjórnunarforritaskilin eru í boði meðan `OPENCDE_ADMIN_API_ENABLED` er
satt (sjálfgefið), óháð HTML-stjórnuninni; getuskjalið (§1) segir þér hvort
þau séu virk.

## 6. Villur

Hver bilun svarar með meginmáli Foundation API 1.6, `{"message": "..."}`, og
aldrei með staflarakningu eða endurómuðu inntaki. Sem viðbót ber hver villa
sem þjónninn mótar sjálfur einnig stöðugan `code` sem forritið þitt getur
brugðist við eða þýtt, meðan `message` er áfram ensk setning fyrir fólk:

```json
{"message": "This operation needs the 'admin' scope", "code": "insufficient_scope"}
```

| `code` | Staða | Þegar | Hvað biðlari gerir |
|---|---|---|---|
| `validation_error` | 400 | Meginmálið eða fyrirspurnin stóðst ekki sannprófun, OData-segð gat ekki verið þýdd, gildi er ekki í extensions verkefnisins, `Content-Range` eða upphalsfyrirmæli eru röng, skyndimynd eða bitamynd er ekki PNG eða JPEG; `message` nefnir sviðið | Lagaðu beiðnina |
| `localhost_redirect` | 400 | Skráning tilgreindi `http://localhost` sem redirect-URI, sem þessi þjónn leyfir ekki | Skráðu `http://127.0.0.1` í staðinn eða segðu rekstraraðilanum frá `OPENCDE_ALLOW_LOCALHOST_REDIRECTS` |
| `unauthenticated` | 401 | Enginn bearer-tóki | Skráðu þig inn |
| `invalid_token` | 401 | Tókinn er óþekktur, útrunninn eða afturkallaður (`WWW-Authenticate: Bearer error="invalid_token"`) | Endurnýjaðu, skráðu þig svo inn aftur |
| `insufficient_scope` | 403 | Tókann skortir heimildina sem leiðin þarf, svo sem `admin` | Veittu heimild aftur með þeirri heimild |
| `forbidden` | 403 | Hlutverk notandans í verkefninu leyfir ekki aðgerðina (Foundation API 1.5), eða notandinn er ekki stjórnandi á stjórnunarforritaskilunum | Sýndu skilaboðin |
| `reauthentication_required` | 403 | Hættuleg stjórnunaraðgerð og innskráningin er eldri en tíu mínútur | Veittu heimild aftur, endurtaktu svo kallið |
| `not_found` | 404 | Engin slík auðlind, auðlind utan verkefna notandans, eða eiginleiki sem er óvirkur (skráning, beiðnaskrá, stjórnunarforritaskil) | Sýndu skilaboðin, endurhladdu lista |
| `conflict` | 409 | Guid sem er þegar til, eða tvítekinn tengill | Sæktu aftur |
| `payload_too_large` | 413 | Meginmál beiðninnar fer yfir mörk þjónsins, eða BCF-tvíundarskrá fer yfir `max_image_bytes`/`max_upload_bytes` | Lagaðu beiðnina |
| `upload_too_large` | 413 | Valin skrá eða hluti fer yfir upphalsmörkin (`max_size_in_bytes` í upphalsfyrirmælunum) | Segðu notandanum mörkin |
| `rate_limited` | 429 | Of margar beiðnir frá einu vistfangi; `Retry-After` segir hvenær | Bíddu og reyndu aftur |
| `internal_error` | 500 | Óvænt villa; `message` er alltaf "Internal server error" | Tilkynntu með `X-Request-ID` |
| `unavailable` | 503 | Ekki næst í grafgagnagrunninn | Reyndu aftur síðar |

Listinn er lokaður: kóði sem þú þekkir ekki er meðhöndlaður eins og vantandi
kóði, og þú sýnir `message`. Stöður sem umgjörðin svarar sjálf (405, 415)
bera engan kóða. OAuth2-tókaendapunkturinn heldur eigin sniði RFC 6749
(`{"error": "invalid_grant", "error_description": "..."}`), eins og
forskriftin krefst, svo bregstu við `error` þar (`invalid_request`,
`invalid_client`, `invalid_grant`, `unauthorized_client`,
`unsupported_grant_type`, `invalid_scope`). Getuskjalið (§1) er veitt af
hverjum þjóni sem gefur frá sér kóða.

## 7. Stjórnunarforritaskilin (viðbót)

Stjórnunarbiðlari (flipinn Stjórnun í Dataspatium er sá fyrsti) les það sem
síðurnar undir `/admin` sýna, sem JSON undir `/admin/api/`, með bearer-tóka
sem ber heimildina `admin` og tilheyrir stjórnanda. Getuskjalið segir hvort
forritaskilin séu virk (`extensions.admin_api`) og hvaða útgáfu þau hafa.
Listar svara `{"items": [...], "total": n}` og taka `limit` (200 sjálfgefið,
mest 1000) auk `q` eða `since` þar sem það er tekið fram; villur nota
meginmálið í §6.

| Endapunktur | Skilar |
|---|---|
| `GET /admin/api/overview` | `version`, `uptime_s`, `dialect`, `graph_ok`, talningarnar `users`, `projects`, `clients`, `sessions`, `topics`, `documents`, `models`, og `request_log` (`enabled`, `rows`) |
| `GET /admin/api/users?q=&limit=` | notendur (`id`, `username`, `name`, `email`, `is_admin`, `disabled`, `must_change_password`, `created_at`, `last_sign_in_at`, `projects` sem `[{project_id, role}]`); `q` leitar í notandanafni, nafni og netfangi |
| `GET /admin/api/users/{id}` | einn notandi; `projects` ber líka `name` verkefnisins |
| `GET /admin/api/projects?q=` | verkefni með `members` (`user_id`, `username`, `role`) og talningarnar `topics`, `documents`, `models` |
| `GET /admin/api/projects/{id}` | eitt verkefni, einnig með `extensions` þess |
| `GET /admin/api/clients` | biðlarar (`client_id`, `name`, `description`, `url`, `public`, `dynamic`, `redirect_uris`, `disabled`, `created_at`, `expires_at`, `last_used_at`, `software_id`, `software_version`), aldrei leyndarmál |
| `GET /admin/api/clients/{id}` | einn biðlari |
| `GET /admin/api/sessions?user=&limit=` | einn listi af tveimur gerðum, `kind: "oauth2"` (endurnýjunartókafjölskylda, `id` = fjölskylduauðkenni) og `kind: "web"` (vafraseta), hver með `user_id`, `username`, `created_at`, `expires_at`, og `client_id`/`client_name`/`scope` eða `ip` þar sem það á við |
| `GET /admin/api/audit?type=&since=&limit=` | endurskoðunaratburðir með `at`, `type`, `actor` (notandaauðkenni), `client_id`, `ip`, `request_id` og þáttuðum `details` |
| `GET /admin/api/requests?...` | beiðnaskráin (§5) |
| `GET /admin/api/settings` | `public_url`, `environment`, `dynamic_client_registration`, `request_log`, `ifcgraph`, `cors_origins`, `dataspatium_url`, `graph_public_bolt_url`, virku `modules`, og hvert `OPENCDE_*`-gildi stillingasíðunnar undir `raw`; leyndarmálum sleppt |
| `GET /admin/api/health` | `ok` og `checks` (`name`, `ok`, `detail`) stillingasíðunnar |

Skrif, með sömu meginmálum og síðurnar nota (`PUT` og `PATCH` eru samþykkt
jafnt; `name` er fullt nafn, `full_name` virkar líka):

| Endapunktur | Gerir |
|---|---|
| `POST /admin/api/users` `{username, password?, name?, email?, is_admin?, must_change_password?}` | býr til notanda; án `password` ber svarið `initial_password` einu sinni |
| `PUT /admin/api/users/{id}` `{name?, email?, disabled?, is_admin?}` | breytir notanda; að gera óvirkan afturkallar tóka; ekki fyrir þinn eigin reikning |
| `DELETE /admin/api/users/{id}` | eyðir notanda með setum og tókum (hættulegt) |
| `POST /admin/api/users/{id}/reset-password` | setur nýtt lykilorð sem er skilað einu sinni og notandinn þarf að breyta (hættulegt) |
| `POST /admin/api/projects` `{name, extensions?}` · `PUT /admin/api/projects/{id}` `{name?, extensions?}` | býr til eða breytir verkefni |
| `DELETE /admin/api/projects/{id}` | eyðir verkefni með öllu sem í því er (hættulegt) |
| `PUT /admin/api/projects/{id}/members/{user_id}` `{role}` · `DELETE …/members/{user_id}` | setur eða fjarlægir hlutverk meðlims (viewer, contributor, editor, manager) |
| `POST /admin/api/clients` `{name, redirect_uris, public?, description?, url?}` | skráir biðlara; trúnaðarbiðlari fær `client_secret` einu sinni |
| `PUT /admin/api/clients/{id}` `{name?, description?, url?, redirect_uris?, disabled?}` | breytir biðlara; að gera óvirkan afturkallar tóka hans |
| `POST /admin/api/clients/{id}/rotate-secret` | nýtt leyndarmál, skilað einu sinni (hættulegt) |
| `POST /admin/api/clients/{id}/revoke` · `DELETE /admin/api/clients/{id}` | afturkallar hvern tóka biðlarans · eyðir biðlaranum með tókum hans (hættulegt) |
| `DELETE /admin/api/sessions/{id}` · `DELETE /admin/api/sessions?user=` | lýkur einni setu með `id` úr listanum · lýkur hverri setu og hverjum tóka notanda |

Hættulegar aðgerðir krefjast **nýlegrar innskráningar**: `auth_time`
tókafjölskyldunnar, sett þegar notandinn auðkenndi sig fyrir
heimildarkóðann, þarf að vera innan síðustu tíu mínútna; endurnýjun
endurnýjar hann aldrei. Annars er svarið `403` með
`code: reauthentication_required`, sem biðlari mætir með því að keyra
heimildarferlið aftur (innskráning í sprettiglugga) og endurtaka kallið.
Einnota gildum er skilað nákvæmlega einu sinni og þau aldrei skráð; hvert
skrif skilur eftir endurskoðunaratburð (`admin.*`) með þeim sem kallaði,
biðlaranum og `X-Request-ID` kallsins.

### Graffyrirspurn (óvirk sjálfgefið)

Þegar rekstraraðilinn setur `OPENCDE_GRAPH_QUERY_ENABLED=true` tilkynnir
getuskjalið `graph_query` með `url`, `max_rows` og `timeout_seconds`, og
stjórnendur með heimildina `admin` mega keyra **lesandi** Cypher gegn öllu
grafinu, IFC-grafinu meðtöldu, án þess að gagnagrunnsgáttin sé birt:

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

Raðirnar bera JSON-gildi: hnúta sem `{identity, labels, properties}`, vensl
sem `{identity, type, start, end, properties}`, slóðir sem
`{nodes, relationships, length}`, tímagildi sem ISO 8601-strengi, heiltölur
sem tölur, punkta sem `{srid, x, y, z}`, bæti sem base64. Setningin keyrir í
lesfærslu; þjónninn hafnar skrifandi setningarliðum og hverri stefju annarri
en skemastefjunum (`db.labels`, `db.relationshipTypes`, `db.propertyKeys`,
`db.schema.*`), hafnar setningum og stikum sem nefna verndaðan eiginleika
(`password_hash`, `secret_hash`, `token_hash`, `code_hash`), fjarlægir þá
eiginleika úr hverjum hnút, venslum og vörpun í svarinu og hylur hvert
Argon2-tætigildi sem nær þangað aðra leið. Svarið stoppar eftir `max_rows`
raðir (`truncated: true`) og setningin eftir `timeout_seconds`. Setning sem
er hafnað, misheppnast eða er stöðvuð svarar `400` með
`code: validation_error` og ástæðunni, eigin skilaboð gagnagrunnsins
meðtalin. Hvert kall, hafnað eða ekki, skilur eftir endurskoðunaratburð
`admin.graph.query` með fyrstu 500 táknum setningarinnar, aldrei stikunum.

## 8. Prófanir gegn þessum þjóni

[Dataspatium](https://github.com/marwiss/Dataspatium) er vafrabiðlarinn sem
er þróaður samhliða þessum þjóni; OpenCDE-uppruni hans (innskráning,
BCF-töflur, Documents API, graffyrirspurnir, request-id) er útfært dæmi um
allt ofangreint, og lifandi prófunarsvítur hans keyra gegn þróunarstaflanum
(sjá [acceptance.md](../acceptance.md)).

- `uv run opencde seed` fyllir tóman gagnagrunn með sýninotendum og
  -verkefnum (lykilorðin eru prentuð einu sinni), sýnilíkaninu
  `three_walls_gtin.ifc` sem skjali og einu máli með viewpoint og
  athugasemd, allt með föstum auðkennum sem prófunarsvíta getur reitt sig á:

  | Hvað | Auðkenni |
  |---|---|
  | Skjal (Documents API, útgáfa 1, verkefnið *Building permit*) | `6f5d3b2a-0000-4000-8000-000000000001` |
  | Mál (`ISSUE-0001`, gerð Inspection, staða Open, merki Reuse) | `6f5d3b2a-0000-4000-8000-000000000002` |
  | Viewpoint (fjarvíddarmyndavél, eining veggur `1Xezbq735AdBO_4DerG66G`) | `6f5d3b2a-0000-4000-8000-000000000003` |
  | Athugasemd (frá `inspector`, vísar í viewpointið) | `6f5d3b2a-0000-4000-8000-000000000004` |

  Veggir líkansins eru `1Xezbq735AdBO_4DerG66G` (GTIN 3),
  `3eT96F_cnDsOufCEsotwtp` (GTIN 2) og `3k3LbXmTfDWODxdSuyCGYE` (GTIN 1), í
  eiginleikasettinu `Reuse`; sama skrá er `tests/fixtures/three_walls_gtin.ifc`.
- `docker compose -f compose.yaml -f compose.dev.yaml up -d` gefur þér þjón á
  `http://127.0.0.1:8000` með Neo4j Browser á `:7484`.
- Skráðu biðlara fyrir forritið þitt í stjórnunarviðmótinu (`/admin` →
  Biðlarar) eða með
  `uv run opencde client create "My app" --redirect-uri http://127.0.0.1/callback --public`.
- `opencde_client.testing` getur lokið innskráningunni og Documents
  API-síðunum án vafra í sjálfvirkum prófunum.
