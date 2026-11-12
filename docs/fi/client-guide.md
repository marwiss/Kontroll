# Asiakassovelluksen rakentaminen

Miten sovellus keskustelee tämän palvelimen (tai minkä tahansa
OpenCDE-palvelimen) kanssa. Python-kirjasto hakemistossa
[client/](../../client/) tekee kaiken tämän; esimerkit hakemistossa
[examples/](../examples/) näyttävät sen käytössä.

## 1. Löytäminen

`GET /foundation/versions` luettelee rajapinnat (`foundation 1.0`, `bcf 3.0`, `bcf 2.1`,
`documents 1.0`). `GET /foundation/1.0/auth` kertoo, missä kirjaudutaan:

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

Palvelimen voi asettaa tarjoamaan vain osan niistä (`OPENCDE_APIS`). Silloin
luettelot sisältävät vain sen, mitä se tarjoaa, ja rajapinta, jota se ei tarjoa,
vastaa 404. Palvelimella, joka tarjoaa vain BCF API 2.1:n, ei ole Foundation
API:a: asiakas löytää sen osoitteesta `GET /bcf/versions` ja kirjautuu osoitteen
`GET /bcf/2.1/auth` kautta. Dokumenttipalvelin tarjoaa Foundation API:n ja
Documents API:n mutta ei BCF:ää.

### Kyvykkyysasiakirja (laajennus)

Spesifikaatioiden lisäksi `GET /.well-known/dataregium` (ei todennusta, CORS
kuten rajapinnalle, välimuistitettava viideksi minuutiksi) kertoo, mitkä
laajennukset tämä palvelin on kytkenyt päälle ja mitkä rajat ovat voimassa,
jotta asiakas sopeutuu sen sijaan että kokeilisi:

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
    "ifc_validation": {"enabled": true, "url": "/documents/1.0/documents/{document_id}/versions/{version_index}/ifc-validation", "bsdd": false, "rooms": false},
    "ifc_precheck": {"enabled": true, "url": "/documents/1.0/projects/{project_id}/ifc-precheck"},
    "ifc_changes": {"enabled": true, "schema": "/documents/1.0/ifc-changes/schema", "snippet_type": "DataregiumIfcChangeSet", "max_changes": 10000, "tried": true, "proposal_url": "/bcf/3.0/projects/{project_id}/topics/{topic_guid}/ifc-proposal", "approve_url": "/bcf/3.0/projects/{project_id}/topics/{topic_guid}/ifc-proposal/approve", "ifc_proposals_url": "/documents/1.0/documents/{document_id}/ifc-proposals"},
    "ifc_merge": {"enabled": true, "url": "/documents/1.0/projects/{project_id}/ifc-merge", "report_url": "/documents/1.0/projects/{project_id}/ifc-merge/report", "prepare_url": "/documents/1.0/projects/{project_id}/ifc-merge/prepare", "choices": ["a", "b", "new"], "roles": ["manager"]},
    "graph_query": {"enabled": true, "url": "/admin/api/graph/query", "max_rows": 1000, "timeout_seconds": 10.0},
    "ai_policy": {"enabled": true, "url": "/documents/1.0/projects/{project_id}/ai-policy", "default": "local"},
    "mcp": {"enabled": true, "url": "/mcp", "protocol_versions": ["2026-07-28", "2025-11-25", "2025-06-18", "2025-03-26"], "scopes": ["mcp", "mcp:propose"], "default_ai_policy": "local", "ai_policy_url": "/documents/1.0/projects/{project_id}/ai-policy"}
  },
  "limits": {"max_upload_bytes": 1073741824, "max_image_bytes": 10485760, "access_token_ttl_seconds": 3600},
  "links": {"dataspatium": null}
}
```

`404` tarkoittaa palvelinta ilman laajennuksia (toinen OpenCDE-palvelin tai
vanhempi Dataregium). Käsittele tuntemattomat avaimet puuttuvina.
`ifcgraph.bolt` on asetettu vain, kun ylläpitäjä on tarkoituksella
julkaissut graafitietokannan (`OPENCDE_GRAPH_PUBLIC_BOLT_URL`); `graph_query`
on päällä vain, kun ylläpitäjä on asettanut `OPENCDE_GRAPH_QUERY_ENABLED`
(§7); `links.dataspatium` sisältää Dataspatium-asennuksen osoitteen, kun
ylläpitäjä on asettanut `OPENCDE_DATASPATIUM_URL`. Mikään asiakirjassa ei
ole salaista.

`mcp` on päällä vain, kun ylläpitäjä on asettanut `OPENCDE_MCP_ENABLED`, ja
antaa silloin MCP-päätepisteen, jossa tekoälyohjelmat lukevat projektien malleja
ja ehdottavat muutosjoukkoja, jotka ihminen hyväksyy (ADR 0028), protokollan
versiot, joihin se vastaa, uusin ensin, ja sen tunnisteiden scopet;
`default_ai_policy` on sellaisen projektin tekoälykäytäntö, jolle kukaan ei ole
asettanut käytäntöä, ja `ai_policy_url` kertoo, mistä jäsen lukee projektin oman
käytännön (§7).

## 2. Kirjautuminen (OAuth2 authorization code ja PKCE)

1. Pyydä palvelimen järjestelmänvalvojaa rekisteröimään sovelluksesi:
   **julkinen** asiakas työpöytä-, mobiili- ja selainsovelluksille (ei
   salaisuutta, PKCE) tai **luottamuksellinen** asiakas
   palvelinsovellukselle (salaisuus näytetään kerran). Rekisteröi tarkka
   redirect-URI; natiivisovelluksille hyväksytään `http://127.0.0.1/…` (mikä
   tahansa portti).
2. Luo `code_verifier` (43–128 URL-turvallista merkkiä) ja sen
   `code_challenge = BASE64URL(SHA256(verifier))` sekä satunnainen `state`.
3. Avaa `oauth2_auth_url?response_type=code&client_id=…&redirect_uri=…&scope=profile bcf documents&state=…&code_challenge=…&code_challenge_method=S256`
   käyttäjän selaimessa. Käyttäjä kirjautuu ja antaa suostumuksensa.
4. Selain ohjataan `redirect_uri`-osoitteeseesi parametrein `code`, `state`
   ja `iss`. Tarkista `state`; tarkista, että `iss` on palvelin.
5. `POST oauth2_token_url` parametrein `grant_type=authorization_code`,
   `code`, `code_verifier`, `redirect_uri` ja `client_id` (julkinen) tai
   HTTP Basic -todennuksella (luottamuksellinen). Vastaus on `201` ja
   sisältää `access_token`, `refresh_token`, `expires_in`, `scope`.
6. Lähetä `Authorization: Bearer <access_token>` jokaisessa
   rajapintakutsussa. Kun se vanhenee, `POST oauth2_token_url` parametrilla
   `grant_type=refresh_token`; refresh-token kiertää, joten tallenna uusi.
   Vanhan refresh-tokenin uudelleenkäyttö peruu koko perheen: niin palvelin
   huomaa varastetun tokenin.
7. `POST oauth2_revocation_url` refresh-tokenilla, kun käyttäjä kirjautuu
   ulos.

Palvelin ei koskaan tue implicit- tai password-granteja.

### Asiakkaan dynaaminen rekisteröinti

Kun palvelin käy asetuksella `OPENCDE_DYNAMIC_CLIENT_REGISTRATION=true`,
`GET /foundation/1.0/auth` sisältää `oauth2_dynamic_client_reg_url`-kentän ja
asiakas voi rekisteröidä itsensä (Foundation API 2.2.3, RFC 7591). Selain-
tai natiivisovellus pyytää julkista asiakasta:

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

Vastaus (201) sisältää `client_id`, `client_id_issued_at` ja rekisteröidyt
metatiedot. Luottamuksellinen asiakas (`token_endpoint_auth_method`-kentän
oletus `client_secret_basic`) saa lisäksi `client_secret`-arvonsa kerran, ja
`client_secret_expires_at: 0`. Redirect-URIt noudattavat yllä olevia
sääntöjä, ja vain authorization code- ja refresh token -grantit ovat
olemassa. Lähetä `software_id` ja `software_version` (RFC 7591 §2): palvelin
tallentaa ne asiakkaalle ja näyttää ne järjestelmänvalvojille rekisteröinnin
vierellä; näin ylläpitäjä erottaa sovelluksesi asennukset ja versiot
toisistaan.

Palvelin voi rajoittaa tätä lisää. Kun `OPENCDE_DYNAMIC_CLIENT_REGISTRATION_TOKEN` on asetettu, pyyntö ottaa arvon muodossa `Authorization: Bearer …` (RFC 7591 §3) ja vastaa ilman sitä 401. Kun `OPENCDE_DYNAMIC_CLIENT_APPROVAL=true`, uusi asiakas ei voi kirjata ketään sisään ennen kuin järjestelmänvalvoja hyväksyy sen, ja kirjautumissivu kertoo sen. Kyvykkyysasiakirja kertoo, mikä on voimassa.

Rekisteröi kerran asennusta kohti ja tallenna `client_id`: itse
rekisteröitynyt asiakas, joka ei myönnä yhtään tokenia
`OPENCDE_DYNAMIC_CLIENT_UNUSED_DAYS`-päivään (oletus 30), poistetaan
tokeneineen. Kun token-päätepiste sen jälkeen vastaa `invalid_client`,
rekisteröi uudelleen.

**Ponnahdusikkunat.** Sivut, jotka sovelluksesi avaa ponnahdusikkunaan
(valtuutussivu, Documents API:n valinta- ja lähetyssivut sekä niiden
mahdollisesti vaatima kirjautuminen), eivät eristä itseään: ne lähettävät
`Cross-Origin-Opener-Policy: unsafe-none`, joten ikkuna säilyttää
`window.opener`-viittauksensa palvelinvierailun ajan ja callback-sivusi voi
lähettää tuloksen takaisin sovellukseen `postMessage`-kutsulla. Vain `/admin`
ja `/account` vastaavat arvolla `same-origin`. Niiden `form-action`-käytäntö
nimeää myös redirect-URIsi (tai callback-URLisi) originin, jotta selain
seuraa lomakkeeseen vastaavaa uudelleenohjausta: Chromium tarkistaa
`form-action`-käytännön tätä uudelleenohjausta vasten, ei vain lomakkeen
omaa osoitetta.

### MCP-päätepisteen metatiedot ja tokenit (laajennus)

`GET /.well-known/oauth-authorization-server` (RFC 8414; ei todennusta, CORS,
välimuistitettava viideksi minuutiksi) kuvaa saman valtuutuspalvelimen
OAuth-asiakkaille, jotka eivät tunne Foundation API:a. `issuer` on julkinen
osoite, sama arvo kuin `iss` jokaisessa valtuutusvastauksessa (RFC 9207,
`authorization_response_iss_parameter_supported: true`); sen rinnalla ovat
valtuutuksen, tokenien ja peruutuksen päätepisteet, `registration_endpoint`
silloin, kun itserekisteröinti on päällä,
`code_challenge_methods_supported: ["S256"]`, grant-tyypit `authorization_code`
ja `refresh_token` sekä `scopes_supported`, jossa `mcp` ja `mcp:propose` ovat
vain silloin, kun MCP-päätepiste on päällä.

MCP-päätepiste, jonka kautta tekoälytyökalut ehdottavat ja ihminen hyväksyy,
on pois päältä, kunnes ylläpitäjä asettaa `OPENCDE_MCP_ENABLED=true`. Sen
tokenit on sidottu siihen:

- Asiakas nimeää päätepisteen `resource`-parametrina (RFC 8707) sekä
  valtuutuspyynnössä että token-pyynnössä. Ainoa hyväksytty arvo on
  `<public_url>/mcp`, jota verrataan ilman lopun kauttaviivaa ja niin, että
  skeema ja isäntä ovat pienillä kirjaimilla; mikä tahansa muu arvo, useampi
  kuin yksi tai resurssi silloin, kun päätepiste on pois päältä, antaa
  `invalid_target`.
- Scope on `mcp` lukutyökaluille tai `mcp mcp:propose`, kun myös
  muutosjoukkoja ehdotetaan. Kumpaakin pyydetään nimenomaisesti ja vain
  yhdessä resurssin kanssa: `mcp` ilman sitä antaa `invalid_target`, ja
  resurssi toisella scopella tai ilman `mcp`:tä antaa `invalid_scope`.
  Suostumussivu kertoo, mitä ne antavat ja ettei niiden kautta hyväksytä eikä
  julkaista mitään.
- Koodi ja token-perhe säilyttävät resurssin, joten uusimisessa sitä ei
  tarvitse nimetä, ja uusiminen, joka nimeää toisen, antaa `invalid_target`.
  Jokainen REST-rajapinta hylkää sidotun tokenin vastauksella
  `401 invalid_token`, eikä MCP-päätepiste ota vastaan muita: tekoälyn token ei
  koskaan ulotu hyväksyntään tai julkaisuun.

Kun päätepiste on päällä, `GET /.well-known/oauth-protected-resource/mcp`
(RFC 9728; myös julkinen ja välimuistitettava) kertoo, mikä resurssi se on ja
mistä sen tokenit tulevat:

```json
{"resource": "https://cde.example.org/mcp",
 "authorization_servers": ["https://cde.example.org"],
 "scopes_supported": ["mcp", "mcp:propose"],
 "bearer_methods_supported": ["header"]}
```

Päätepisteen hylkäys osoittaa sinne: `401` ja `WWW-Authenticate: Bearer resource_metadata="https://cde.example.org/.well-known/oauth-protected-resource/mcp", scope="mcp"`,
sekä `403` ja `error="insufficient_scope"` ja `scope="mcp mcp:propose"`, kun
ehdottava työkalu tarvitsee suostumuksen, joka tokenilta puuttuu; asiakas
pyytää sitä silloin käyttäjältä.

## 3. BCF API

- Kaikki polun `/bcf/3.0/projects/{project_id}` alla rajautuu projektiin,
  jonka jäsen käyttäjä on; projektit, joita käyttäjä ei näe, vastaavat `404`.
- `GET …/extensions` antaa sallitut arvot (`topic_type`, `topic_status`,
  `topic_label`, `priority`, `stage`, `users`) sekä käyttäjän oletusarvot
  `project_actions`, `topic_actions`, `comment_actions`. Listojen
  ulkopuoliset arvot hylätään koodilla `400`.
- Lisää `?includeAuthorization=true` projektien, asioiden, kommenttien tai
  viewpointien `GET`-kutsuun saadaksesi `authorization`-objektin jokaiselle
  entiteetille.
- Kokoelmat hyväksyvät OData-kyselyt: `$filter` (esim. `topic_status eq
  'Open' and labels/any(l: l eq 'Safety')`), `$orderby`, `$top`, `$skip`.
- Luettelossa ilman `$top`-arvoa tai sitä suuremmalla kuin 1000 on enintään 1000
  merkintää. Kun osumia on enemmän, vastauksessa on `X-Total-Count` niiden määrällä ja
  `Link: <…>; rel="next"` loppujen osoitteella (laajennus).
- `PUT` korvaa koko objektin: lähetä jokainen kenttä, jonka haluat säilyttää.
- Viewpointien kuvat ovat base64-koodattua PNG:tä tai JPEG:tä; palvelin
  tarkistaa tavut.
- Jokainen `GET` sisältää `ETag`-otsakkeen; `If-None-Match` vastaa `304`.
- Virheet ovat `{"message": "…"}` tavallisin tilakoodein (`400`, `401`,
  `403`, `404`, `409` päällekkäisille guideille, `413` liian suurille
  rungoille).

### BCF API 2.1

Palvelin osaa myös BCF API 2.1:n asiakkaille, jotka eivät tunne mitään uudempaa.
`GET /foundation/versions` luettelee molemmat versiot uusimman ensin, kummallakin oma
`api_base_url`, ja 2.1:n asiakas löytää saman luettelon osoitteesta `GET /bcf/versions`.
Molemmat versiot käsittelevät samaa dataa, joten toisen kautta luotua asiaa voi lukea ja
muuttaa toisen kautta.

| | 2.1, polussa `/bcf/2.1` | 3.0, polussa `/bcf/3.0` |
|---|---|---|
| Versiot, kirjautuminen, käyttäjä | `/bcf/versions`, `/bcf/2.1/auth`, `/bcf/2.1/current-user` | Foundation API |
| Tiedosto asian otsakkeessa | `file_name` | `filename` |
| Käyttäjät extensions-arvoissa | `user_id_type` | `users` |
| Asian lyhyt tunniste | Ei ole | `server_assigned_id` |
| Toiseen kommenttiin vastaava kommentti | `reply_to_comment_guid` | Ei ole |
| Kameran `aspect_ratio` | Ei ole; 3.0 lukee sen arvona 1.0 | Pakollinen |
| Mitä näkymässä on oltava | Mitä tahansa paitsi kaksi kameraa | Kamera tai kuva, ja kamera kaiken muun kanssa |
| Asiakkaan valitsema `guid` | Jätetään huomiotta | Hyväksytään, `409` jos se on olemassa |
| `files_information`, näkymän poistaminen | Ei ole | On |
| Omat tapahtumatyypit | `reply_to_comment_updated`, `reply_to_comment_removed` | `stage_added`, `stage_updated`, `stage_removed` |
| Nimiön kysyminen `$filter`-ehdossa | `contains(labels, 'x')` | `labels/any(l: l eq 'x')`; toinenkin muoto toimii |

2.1:n OAuth2-esimerkki ei tunne PKCE:tä, joten sen mukaan kirjoitettu asiakas ei voi
lähettää `code_challenge`-arvoa. Ylläpitäjä voi merkitä luottamuksellisen asiakkaan,
joka saa jättää sen pois: *Saa kirjautua ilman PKCE:tä* asiakkaan sivulla, `pkce_optional`
hallinnan rajapinnassa tai `opencde client create --without-pkce`. Silloin sen salaisuus
suojaa kirjautumiset, ja se annetaan HTTP Basicilla token-osoitteessa. Asiakas, joka
rekisteröityy itse osoitteessa `oauth2_dynamic_client_reg_url`, joka on kohteessa
`GET /bcf/2.1/auth`, kun `OPENCDE_DYNAMIC_CLIENT_REGISTRATION=true`, merkitään samalla
tavalla, kun taas Foundation API:n rekisteröinti ei merkitse ketään. Julkinen asiakas ei
voi koskaan jättää PKCE:tä pois, ja merkitty asiakas, joka lähettää `code_challenge`-arvon,
sidotaan siihen. Käytä PKCE:tä, jos voit. Redirect-URI osoitteessa `http://localhost` vaatii
asetuksen `OPENCDE_ALLOW_LOCALHOST_REDIRECTS=true`.

## 4. Documents API

Kulut koskevat käyttäjän selainta; katso [flows/documents.md](flows/documents.md).
Asiakkaasi tarvitsee callback-URLin, johon selain pääsee
(loopback-kuuntelija työpöytäsovelluksille). Palvelin ei koskaan kutsu tuota
URLia itse.

Kun IFC-LPG-moduuli on käytössä, versiona lähetetty IFC-tiedosto tarkistetaan
IFC-skeemaa ja, jos palvelimella on ne, buildingSMARTin ifc-gherkin-rules-sääntöjä
vasten. Sen metatiedoissa on silloin `ifc_validation_status` ja
tarkistuksen jälkeen muut `ifc_validation_*`-kohdat; `ifc_validation_report` on
raportin osoite, laajennus, joka vastaa samalle tunnisteelle. Katso
[ifc-lpg.md](ifc-lpg.md#lähetysten-tarkistus-ifc-skeemaa-vasten).

IFC-mallin sisältävältä versiolta voi myös kysyä nimettyjä kyselyitä, kuten sen
kerrokset, tilojen pinta-alat tai ominaisuuden arvon. Se on laajennus, joka
vastaa samalle tunnisteelle ja jonka ominaisuusdokumentti ilmoittaa kentässä
`ifc_queries`. Katso [ifc-lpg.md](ifc-lpg.md#nimetyt-kyselyt).

Projektin kahta IFC-versiota voi verrata törmäysten varalta samalla tavalla;
laajennus ilmoitetaan nimellä `ifc_clash`. Katso [ifc-lpg.md](ifc-lpg.md#törmäystarkastus).

Tiedoston voi tarkistaa ennen lähettämistä; laajennus ilmoitetaan nimellä
`ifc_precheck`, ja projekti voi hylätä virheelliset tiedostot. Katso
[ifc-lpg.md](ifc-lpg.md#virheellisten-tiedostojen-hylkääminen-ja-tiedoston-tarkistaminen-etukäteen).

Muutosta malliin ehdotetaan BCF-asiana, jonka `bim_snippet` on muutosjoukko;
muoto ilmoitetaan nimellä `ifc_changes`. Katso
[ifc-lpg.md](ifc-lpg.md#muutosjoukot).

Kahta IFC-versiota verrataan elementti kerrallaan laajennuksella `ifc_diff`,
GlobalId:n ja polun mukaan. Katso [ifc-lpg.md](ifc-lpg.md#kahden-version-vertailu).

IFC-version geometria tulee binäärisenä glTF:nä laajennuksella `ifc_geometry` (`lod=full` tai `box`, `classes`, `storey`),
ja jokaisella rakennusosalla on laatikkonsa graafissa. Katso [ifc-lpg.md](ifc-lpg.md#missä-rakennusosat-ovat-ja-geometria).

`manager` julkaisee version laajennuksella `publication`: `POST …/versions/{index}/publication` tallentaa
tiedoston yhdeksi arkistoksi, IFC-tiedoston `.ifczip`-muodossa ja muun tiedoston `.zip`-muodossa, ja version
metatietoihin tulevat `published_at`, `published_by` ja `publication`. Versio julkaistaan kerran, eikä sitä
julkaista tarkistuksen ollessa kesken tai sen löydettyä virheitä. `GET …/publication` kertoo jokaiselle
jäsenelle, kuka sen julkaisi ja milloin, ja `…/publication/download` antaa arkiston.

Toisen mallin rakennus tulee projektin malliin sen seuraavana versiona laajennuksella `ifc_merge`, ensin
raportti ja valinta jokaiselle eroavalle objektille. Katso [ifc-lpg.md](ifc-lpg.md#rakennus-toiseen-malliin).

## 5. Lokisi ja palvelimen lokin yhdistäminen

Lähetä `X-Request-ID`-otsake (1–128 merkkiä joukosta `A-Za-z0-9._-`)
jokaisessa pyynnössä, niin palvelin toistaa sen vastauksessa ja sitoo sen
omiin lokiriveihinsä; ilman sitä palvelin luo tunnisteen ja palauttaa sen.
Otsake on sallittu CORS-esitarkistuksissa ja näkyvissä selainasiakkaille.

Kun ylläpitäjä on kytkenyt pyyntölokin päälle (`OPENCDE_REQUEST_LOG_ENABLED`,
spesifikaatioiden ulkopuolinen laajennus), järjestelmänvalvoja näkee jokaisen
kutsun palvelinpuolen osoitteessa `/admin/requests`, ja hallinta-asiakas voi
lukea samat merkinnät JSON-muodossa:

```http
GET /admin/api/requests?client_id=<your client id>&since=2026-11-05T10:00:00Z&limit=200
Authorization: Bearer <token with the admin scope>
```

Tokenin on sisällettävä `admin`-scope, jota asiakas pyytää nimenomaisesti
(`scope=profile bcf documents admin`), ja käyttäjän on oltava
järjestelmänvalvoja. Merkinnät sisältävät metodin, polun, operaation, tilan,
keston, request-id:n, tavumäärät ja kutsujan, eivät koskaan runkoja tai
tokeneita. JSON-hallintarajapintaa tarjotaan niin kauan kuin
`OPENCDE_ADMIN_API_ENABLED` on tosi (oletus), HTML-hallinnasta riippumatta;
kyvykkyysasiakirja (§1) kertoo, onko se päällä.

## 6. Virheet

Jokainen epäonnistuminen vastaa Foundation API 1.6:n rungolla,
`{"message": "..."}`, eikä koskaan pinojäljillä tai toistetulla syötteellä.
Laajennuksena jokainen palvelimen itse muotoilema virhe sisältää myös vakaan
`code`-kentän, jonka perusteella sovelluksesi voi toimia tai jonka se voi
kääntää, kun `message` pysyy englanninkielisenä lauseena ihmisille:

```json
{"message": "This operation needs the 'admin' scope", "code": "insufficient_scope"}
```

API-dokumentti (`/openapi.json`) ilmoittaa pyynnölle, jota palvelin ei pysty
lukemaan, `400` tällä rungolla, kuten palvelin vastaa, siinä missä FastAPI itse
ilmoittaisi `422`.

| `code` | Tila | Milloin | Mitä asiakas tekee |
|---|---|---|---|
| `validation_error` | 400 | Runko tai kysely ei läpäissyt validointia, OData-lauseketta ei voitu kääntää, arvo ei ole projektin extensions-listoissa, `Content-Range` tai lähetysohje on väärä, tilannekuva tai bittikartta ei ole PNG tai JPEG; `message` nimeää kentän | Korjaa pyyntö |
| `localhost_redirect` | 400 | Rekisteröinnissä oli redirect-URIna `http://localhost`, jota tämä palvelin ei salli | Rekisteröi sen sijaan `http://127.0.0.1` tai kerro ylläpitäjälle asetuksesta `OPENCDE_ALLOW_LOCALHOST_REDIRECTS` |
| `unauthenticated` | 401 | Ei bearer-tokenia | Kirjaudu |
| `invalid_token` | 401 | Token on tuntematon, vanhentunut, peruttu tai sidottu MCP-päätepisteeseen (`WWW-Authenticate: Bearer error="invalid_token"`) | Uusi, kirjaudu sitten uudelleen |
| `insufficient_scope` | 403 | Tokenilta puuttuu reitin vaatima scope, kuten `admin` | Valtuuta uudelleen tuolla scopella |
| `forbidden` | 403 | Käyttäjän rooli projektissa ei salli toimintoa (Foundation API 1.5), tai käyttäjä ei ole järjestelmänvalvoja hallintarajapinnassa | Näytä viesti |
| `reauthentication_required` | 403 | Vaarallinen hallintatoiminto ja kirjautuminen on yli kymmenen minuuttia vanha | Valtuuta uudelleen, toista sitten kutsu |
| `not_found` | 404 | Resurssia ei ole, resurssi on käyttäjän projektien ulkopuolella, tai toiminto on pois päältä (rekisteröinti, pyyntöloki, hallintarajapinta) | Näytä viesti, lataa listat uudelleen |
| `conflict` | 409 | Guid on jo olemassa, tai linkki on päällekkäinen | Hae uudelleen |
| `version_conflict` | 412 | Lähetys antoi `base_version_index`:n, ja dokumentilla on jo uudempi versio; tai muutosjoukko törmää siihen, mitä on muutettu sen perustan jälkeen, nimettynä kentässä `conflicts`, kunkin kolme arvoa kentässä `conflict_details` | Hae uusin versio, yhdistä ja lähetä uudelleen |
| `ifc_validation_failed` | 422 | Projekti hylkää tiedostot, joissa on validointivirheitä, ja tiedostossa on niitä; rungon `report` on raportin osoite | Näytä raportti, anna käyttäjän korjata tiedosto ja lähetä uudelleen |
| `payload_too_large` | 413 | Pyynnön runko ylittää palvelimen rajan, tai BCF-binääri ylittää `max_image_bytes`/`max_upload_bytes` | Korjaa pyyntö |
| `upload_too_large` | 413 | Valittu tiedosto tai osa ylittää lähetysrajan (`max_size_in_bytes` lähetysohjeissa) | Kerro käyttäjälle raja |
| `rate_limited` | 429 | Liian monta pyyntöä yhdestä osoitteesta; `Retry-After` kertoo milloin | Odota ja yritä uudelleen |
| `internal_error` | 500 | Odottamaton virhe; `message` on aina "Internal server error" | Raportoi `X-Request-ID`:n kanssa |
| `unavailable` | 503 | Graafitietokantaan ei saada yhteyttä | Yritä myöhemmin uudelleen |

Lista on suljettu: koodia, jota et tunne, käsitellään kuin puuttuvaa, ja
näytät `message`-kentän. Tilat, joihin kehys vastaa itse (405, 415), eivät
sisällä koodia. OAuth2:n token-päätepiste säilyttää RFC 6749:n oman muodon
(`{"error": "invalid_grant", "error_description": "..."}`), kuten
spesifikaatio vaatii, joten toimi siellä `error`-kentän mukaan
(`invalid_request`, `invalid_client`, `invalid_grant`, `unauthorized_client`,
`unsupported_grant_type`, `invalid_scope`, `invalid_target`). Kyvykkyysasiakirjaa (§1) tarjoaa
jokainen palvelin, joka lähettää koodeja.

## 7. Hallintarajapinta (laajennus)

Hallinta-asiakas (Dataspatiumin Hallinta-välilehti on ensimmäinen) lukee
sen, mitä `/admin`-sivut näyttävät, JSON-muodossa polun `/admin/api/` alta,
bearer-tokenilla, joka sisältää `admin`-scopen ja kuuluu
järjestelmänvalvojalle. Kyvykkyysasiakirja kertoo, onko rajapinta päällä
(`extensions.admin_api`) ja mikä versio sillä on. Listat vastaavat
`{"items": [...], "total": n}` ja ottavat `limit`-parametrin (oletus 200,
enintään 1000) sekä `q`- tai `since`-parametrin, missä niin mainitaan;
virheet käyttävät §6:n runkoa.

| Päätepiste | Palauttaa |
|---|---|
| `GET /admin/api/overview` | `version`, `uptime_s`, `dialect`, `graph_ok`, lukumäärät `users`, `projects`, `clients`, `sessions`, `topics`, `documents`, `models`, ja `request_log` (`enabled`, `rows`) |
| `GET /admin/api/users?q=&limit=` | käyttäjät (`id`, `username`, `name`, `email`, `is_admin`, `disabled`, `must_change_password`, `created_at`, `last_sign_in_at`, `projects` muodossa `[{project_id, role}]`); `q` hakee käyttäjätunnuksesta, nimestä ja sähköpostista |
| `GET /admin/api/users/{id}` | yksi käyttäjä; `projects` sisältää myös projektin `name`-kentän |
| `GET /admin/api/projects?q=` | projektit `members`-listoineen (`user_id`, `username`, `role`), lukumäärät `topics`, `documents`, `models` ja `ai_policy` |
| `GET /admin/api/projects/{id}` | yksi projekti, myös sen `extensions` |
| `GET /admin/api/clients` | asiakkaat (`client_id`, `name`, `description`, `url`, `public`, `dynamic`, `redirect_uris`, `disabled`, `created_at`, `expires_at`, `last_used_at`, `software_id`, `software_version`), ei koskaan salaisuutta |
| `GET /admin/api/clients/{id}` | yksi asiakas |
| `GET /admin/api/sessions?user=&limit=` | yksi lista kahdenlaisia: `kind: "oauth2"` (refresh-token-perhe, `id` = perheen tunnus) ja `kind: "web"` (selainistunto), kullakin `user_id`, `username`, `created_at`, `expires_at`, sekä `client_id`/`client_name`/`scope` tai `ip`, missä ne pätevät |
| `GET /admin/api/audit?type=&since=&limit=` | tapahtumat kentin `at`, `type`, `actor` (käyttäjätunnus), `client_id`, `ip`, `request_id` ja jäsennetty `details` |
| `GET /admin/api/requests?...` | pyyntöloki (§5) |
| `GET /admin/api/settings` | `public_url`, `environment`, `dynamic_client_registration`, `request_log`, `ifcgraph`, `cors_origins`, `dataspatium_url`, `graph_public_bolt_url`, päällä olevat `modules`, ja jokainen asetussivun `OPENCDE_*`-arvo `raw`-kentän alla; salaisuudet jätetty pois |
| `GET /admin/api/health` | `ok` ja asetussivun `checks` (`name`, `ok`, `detail`) |

Kirjoitukset, samoilla rungoilla kuin sivut käyttävät (`PUT` ja `PATCH`
hyväksytään samoin; `name` on koko nimi, `full_name` toimii myös):

| Päätepiste | Tekee |
|---|---|
| `POST /admin/api/users` `{username, password?, name?, email?, is_admin?, must_change_password?}` | luo käyttäjän; ilman `password`-kenttää vastaus sisältää `initial_password`-arvon kerran |
| `PUT /admin/api/users/{id}` `{name?, email?, disabled?, is_admin?}` | muuttaa käyttäjää; käytöstä poisto peruu tokenit; ei omalle tilillesi |
| `DELETE /admin/api/users/{id}` | poistaa käyttäjän istuntoineen ja tokeneineen (vaarallinen) |
| `POST /admin/api/users/{id}/reset-password` | asettaa uuden salasanan, joka palautetaan kerran ja jonka käyttäjän on vaihdettava (vaarallinen) |
| `POST /admin/api/projects` `{name, extensions?}` · `PUT /admin/api/projects/{id}` `{name?, extensions?, block_on_validation_errors?, ai_policy?}` | luo tai muuttaa projektin |
| `DELETE /admin/api/projects/{id}` | poistaa projektin ja kaiken sen sisällön (vaarallinen) |
| `PUT /admin/api/projects/{id}/members/{user_id}` `{role}` · `DELETE …/members/{user_id}` | asettaa tai poistaa jäsenen roolin (viewer, contributor, editor, manager) |
| `POST /admin/api/clients` `{name, redirect_uris, public?, description?, url?}` | rekisteröi asiakkaan; luottamuksellinen saa `client_secret`-arvon kerran |
| `PUT /admin/api/clients/{id}` `{name?, description?, url?, redirect_uris?, disabled?}` | muuttaa asiakasta; käytöstä poisto peruu sen tokenit |
| `POST /admin/api/clients/{id}/rotate-secret` | uusi salaisuus, palautetaan kerran (vaarallinen) |
| `POST /admin/api/clients/{id}/revoke` · `DELETE /admin/api/clients/{id}` | peruu asiakkaan jokaisen tokenin · poistaa asiakkaan tokeneineen (vaarallinen) |
| `DELETE /admin/api/sessions/{id}` · `DELETE /admin/api/sessions?user=` | päättää yhden istunnon listauksen `id`:llä · päättää käyttäjän jokaisen istunnon ja tokenin |

Vaaralliset operaatiot vaativat **tuoreen kirjautumisen**: tokenperheen
`auth_time`, joka asetetaan, kun käyttäjä todentautui valtuutuskoodia
varten, on oltava viimeisten kymmenen minuutin sisällä; refresh ei koskaan
uudista sitä. Muuten vastaus on `403` ja `code: reauthentication_required`,
johon asiakas vastaa ajamalla valtuutuskulun uudelleen
(ponnahdusikkunakirjautuminen) ja toistamalla kutsun. Kertakäyttöiset arvot
palautetaan tasan kerran eikä niitä koskaan kirjata lokiin; jokainen
kirjoitus jättää tapahtuman (`admin.*`), jossa ovat kutsuja, asiakas ja
kutsun `X-Request-ID`.

### Graafikysely (oletuksena pois päältä)

Kun ylläpitäjä asettaa `OPENCDE_GRAPH_QUERY_ENABLED=true`, kyvykkyysasiakirja
ilmoittaa `graph_query`-laajennuksen kentin `url`, `max_rows` ja
`timeout_seconds`, ja `admin`-scopen omaavat järjestelmänvalvojat voivat
ajaa **lukevaa** Cypheriä koko graafia vasten, IFC-graafi mukaan lukien,
ilman että tietokantaporttia julkaistaan:

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

Rivit sisältävät JSON-arvoja: solmut muodossa
`{identity, labels, properties}`, suhteet muodossa `{identity, type, start, end, properties}`,
polut muodossa `{nodes, relationships, length}`, aika-arvot ISO 8601
-merkkijonoina, kokonaisluvut lukuina, pisteet muodossa `{srid, x, y, z}`,
tavut base64-muodossa. Lause ajetaan lukutransaktiossa; palvelin hylkää
kirjoittavat lausekkeet ja kaikki proseduurit paitsi skeemaproseduurit
(`db.labels`, `db.relationshipTypes`, `db.propertyKeys`, `db.schema.*`),
hylkää lauseet ja parametrit, jotka nimeävät suojatun ominaisuuden
(`password_hash`, `secret_hash`, `token_hash`, `code_hash`), poistaa nämä
ominaisuudet vastauksen jokaisesta solmusta, suhteesta ja mapista ja peittää
jokaisen muuta tietä sinne päätyvän Argon2-tiivisteen. Vastaus katkeaa
`max_rows` rivin jälkeen (`truncated: true`) ja lause `timeout_seconds`
jälkeen. Hylätty, epäonnistunut tai keskeytetty lause vastaa `400` ja
`code: validation_error` sekä syyn, tietokannan oma viesti mukaan lukien.
Jokainen kutsu, hylätty tai ei, jättää tapahtuman `admin.graph.query`, jossa
ovat lauseen ensimmäiset 500 merkkiä, eivät koskaan parametrit.

### Projektin hallinta sen vastuuhenkilöiden toimesta (laajennus)

Projektin `manager` hallitsee sen jäseniä ja heidän roolejaan olematta
ylläpitäjä. Tunnisteessa on oltava scope `project`, jota asiakas pyytää
erikseen; rooli kussakin projektissa ratkaisee, ja projekti, jonka jäsen kutsuja
ei ole, vastaa `404`. Jäsen lisätään tarkalla käyttäjänimellä, jotta
vastuuhenkilö ei koskaan listaa palvelimen käyttäjiä, ja hänet näytetään
käyttäjänimen, nimen ja roolin kanssa. Projektiin jää aina vähintään yksi
`manager` (muuten `409 conflict`). Nimi muutetaan BCF API:n kautta
(`PUT /bcf/3.0/projects/{project_id}`); projektin poistaminen kuuluu
ylläpitäjille. Jokainen kirjoitus jättää tarkastustapahtuman (`manage.*`).
Kyvykkyysasiakirja ilmoittaa sen nimellä `project_administration`.

| Call | What it does |
|---|---|
| `GET /manage/1.0/projects` | projektit, joista kutsuja vastaa |
| `GET /manage/1.0/projects/{project_id}` | projekti kentin `project_id`, `name` ja `ai_policy` |
| `PUT /manage/1.0/projects/{project_id}` | asettaa `{"ai_policy"}`: `local` tai `cloud` |
| `GET /manage/1.0/projects/{project_id}/members` | jäsenet kentin `user_id`, `username`, `name` ja `role` |
| `POST /manage/1.0/projects/{project_id}/members` | lisää `{"username", "role"}` (`201`) tai asettaa jäsenen roolin (`200`); `404`, jos käyttäjää ei ole |
| `PUT /manage/1.0/projects/{project_id}/members/{user_id}` | asettaa `{"role"}`: `viewer`, `contributor`, `editor` tai `manager` |
| `DELETE /manage/1.0/projects/{project_id}/members/{user_id}` | poistaa jäsenen |
| `GET /manage/1.0/projects/{project_id}/teams` | tiimit kentillä `team_id`, `name`, `responsible`, `members` ja `ids_document_id` |
| `POST /manage/1.0/projects/{project_id}/teams` | tekee tiimin rungosta `{"name", "responsible", "members", "ids_document_id"}` (`201`); `400`, kun vastuuhenkilö ei ole projektin `editor` tai `manager`, jäsen ei kuulu projektiin tai asiakirja ei ole projektin IDS |
| `PUT /manage/1.0/projects/{project_id}/teams/{team_id}` | korvaa tiimin |
| `DELETE /manage/1.0/projects/{project_id}/teams/{team_id}` | poistaa tiimin |

Tiimin osa mallista on se, mihin sen IDS-asiakirjan määrittelyt kohdistuvat.
Muutosjoukon, joka koskee yhden tiimin osaa, hyväksyy tiimin vastuuhenkilö
yksin; useamman tiimin osia tai ei kenenkään osaa koskevan hyväksyy `manager`.
Kokeilu luettelee tiimit kentässä `teams`; katso
[ifc-lpg.md](ifc-lpg.md#muutosjoukot).

Projektin `ai_policy` kertoo, minne tekoälytyökalut saavat viedä sen tiedot
(ADR 0028): `local`, uuden projektin käytäntö ja sellaisen, jolle kukaan ei
ole asettanut käytäntöä, antaa tekoälytyökalujen saada tiedot vain käyttäjän
omalla tietokoneella, paikallisen moottorin tai paikallisen mallin kautta;
`cloud` antaa myös pilven tekoälypalvelujen saada ne. `manager` asettaa sen
täällä, ylläpitäjä projektin sivulla tai hallintarajapinnan kentällä
`ai_policy`, ja jokainen muutos jättää tarkastustapahtuman
(`manage.project.ai_policy`, `admin.project.ai_policy` tai
`admin.project.update`). Jokainen jäsen lukee sen kutsulla
`GET /documents/1.0/projects/{project_id}/ai-policy`, joka vastaa
`{"project_id", "ai_policy"}` tunnisteelle, jossa on scope `documents`, ja
`404` projektille, jonka jäsen kutsuja ei ole. Asiakas ei käytä pilven
tekoälypalveluja `local`-projektille. OpenCDE-spesifikaatioiden määrittelemät
vastaukset eivät sisällä käytäntöä.

## 8. Testaaminen tätä palvelinta vasten

[Dataspatium](https://github.com/marwiss/Dataspatium) on tämän palvelimen
kanssa kehitettävä selainasiakas; sen OpenCDE-lähde (kirjautuminen,
BCF-taulukot, Documents API, graafikyselyt, request-id:t) on työstetty
esimerkki kaikesta edellä olevasta, ja sen live-testisarjat ajetaan
kehityspinoa vasten.

- `uv run opencde seed` täyttää tyhjän tietokannan demokäyttäjillä ja
  -projekteilla (salasanat tulostetaan kerran), esimerkkimallilla
  `three_walls_gtin.ifc` asiakirjana sekä yhdellä asialla, jolla on
  viewpoint ja kommentti, kaikki kiintein tunnistein, joihin testisarja voi
  luottaa:

  | Mikä | Tunnus |
  |---|---|
  | Asiakirja (Documents API, versio 1, projekti *Building permit*) | `6f5d3b2a-0000-4000-8000-000000000001` |
  | Asia (`ISSUE-0001`, tyyppi Inspection, tila Open, tunniste Reuse) | `6f5d3b2a-0000-4000-8000-000000000002` |
  | Viewpoint (perspektiivikamera, komponenttina seinä `1Xezbq735AdBO_4DerG66G`) | `6f5d3b2a-0000-4000-8000-000000000003` |
  | Kommentti (käyttäjältä `inspector`, viittaa viewpointiin) | `6f5d3b2a-0000-4000-8000-000000000004` |

  Mallin seinät ovat `1Xezbq735AdBO_4DerG66G` (GTIN 3),
  `3eT96F_cnDsOufCEsotwtp` (GTIN 2) ja `3k3LbXmTfDWODxdSuyCGYE` (GTIN 1),
  ominaisuusjoukossa `Reuse`; sama tiedosto on `tests/fixtures/three_walls_gtin.ifc`.
- `docker compose up -d` antaa
  palvelimen osoitteessa `http://127.0.0.1:8000` ja Neo4j Browserin portissa
  `:7484`.
- Rekisteröi asiakas sovelluksellesi hallintakäyttöliittymässä (`/admin` →
  Asiakkaat) tai komennolla
  `uv run opencde client create "My app" --redirect-uri http://127.0.0.1/callback --public`.
- `opencde_client.testing` voi suorittaa kirjautumisen ja Documents API
  -sivut ilman selainta automaattitesteissä.
