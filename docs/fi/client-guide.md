# Asiakassovelluksen rakentaminen

Miten sovellus keskustelee tämän palvelimen (tai minkä tahansa
OpenCDE-palvelimen) kanssa. Python-kirjasto hakemistossa
[client/](../../client/) tekee kaiken tämän; esimerkit hakemistossa
[examples/](../examples/) näyttävät sen käytössä.

## 1. Löytäminen

`GET /foundation/versions` luettelee rajapinnat (`foundation 1.0`, `bcf 3.0`,
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

### Kyvykkyysasiakirja (laajennus)

Spesifikaatioiden lisäksi `GET /.well-known/kontroll` (ei todennusta, CORS
kuten rajapinnalle, välimuistitettava viideksi minuutiksi) kertoo, mitkä
laajennukset tämä palvelin on kytkenyt päälle ja mitkä rajat ovat voimassa,
jotta asiakas sopeutuu sen sijaan että kokeilisi:

```json
{
  "server": {"name": "Kontroll OpenCDE server", "version": "2.4.0", "public_url": "https://cde.example.org"},
  "apis": {"foundation": "1.0", "bcf": "3.0", "documents": "1.0"},
  "scopes": ["profile", "bcf", "documents", "admin"],
  "extensions": {
    "dynamic_client_registration": {"enabled": true, "public_clients": true, "unused_days": 30,
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

`404` tarkoittaa palvelinta ilman laajennuksia (toinen OpenCDE-palvelin tai
vanhempi Kontroll). Käsittele tuntemattomat avaimet puuttuvina.
`ifcgraph.bolt` on asetettu vain, kun ylläpitäjä on tarkoituksella
julkaissut graafitietokannan (`OPENCDE_GRAPH_PUBLIC_BOLT_URL`); `graph_query`
on päällä vain, kun ylläpitäjä on asettanut `OPENCDE_GRAPH_QUERY_ENABLED`
(§7); `links.dataspatium` sisältää Dataspatium-asennuksen osoitteen, kun
ylläpitäjä on asettanut `OPENCDE_DATASPATIUM_URL`. Mikään asiakirjassa ei
ole salaista.

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
- `PUT` korvaa koko objektin: lähetä jokainen kenttä, jonka haluat säilyttää.
- Viewpointien kuvat ovat base64-koodattua PNG:tä tai JPEG:tä; palvelin
  tarkistaa tavut.
- Jokainen `GET` sisältää `ETag`-otsakkeen; `If-None-Match` vastaa `304`.
- Virheet ovat `{"message": "…"}` tavallisin tilakoodein (`400`, `401`,
  `403`, `404`, `409` päällekkäisille guideille, `413` liian suurille
  rungoille).

## 4. Documents API

Kulut koskevat käyttäjän selainta; katso [flows/documents.md](flows/documents.md).
Asiakkaasi tarvitsee callback-URLin, johon selain pääsee
(loopback-kuuntelija työpöytäsovelluksille). Palvelin ei koskaan kutsu tuota
URLia itse.

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

| `code` | Tila | Milloin | Mitä asiakas tekee |
|---|---|---|---|
| `validation_error` | 400 | Runko tai kysely ei läpäissyt validointia, OData-lauseketta ei voitu kääntää, arvo ei ole projektin extensions-listoissa, `Content-Range` tai lähetysohje on väärä, tilannekuva tai bittikartta ei ole PNG tai JPEG; `message` nimeää kentän | Korjaa pyyntö |
| `unauthenticated` | 401 | Ei bearer-tokenia | Kirjaudu |
| `invalid_token` | 401 | Token on tuntematon, vanhentunut tai peruttu (`WWW-Authenticate: Bearer error="invalid_token"`) | Uusi, kirjaudu sitten uudelleen |
| `insufficient_scope` | 403 | Tokenilta puuttuu reitin vaatima scope, kuten `admin` | Valtuuta uudelleen tuolla scopella |
| `forbidden` | 403 | Käyttäjän rooli projektissa ei salli toimintoa (Foundation API 1.5), tai käyttäjä ei ole järjestelmänvalvoja hallintarajapinnassa | Näytä viesti |
| `reauthentication_required` | 403 | Vaarallinen hallintatoiminto ja kirjautuminen on yli kymmenen minuuttia vanha | Valtuuta uudelleen, toista sitten kutsu |
| `not_found` | 404 | Resurssia ei ole, resurssi on käyttäjän projektien ulkopuolella, tai toiminto on pois päältä (rekisteröinti, pyyntöloki, hallintarajapinta) | Näytä viesti, lataa listat uudelleen |
| `conflict` | 409 | Guid on jo olemassa, tai linkki on päällekkäinen | Hae uudelleen |
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
`unsupported_grant_type`, `invalid_scope`). Kyvykkyysasiakirjaa (§1) tarjoaa
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
| `GET /admin/api/projects?q=` | projektit `members`-listoineen (`user_id`, `username`, `role`) ja lukumäärät `topics`, `documents`, `models` |
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
| `POST /admin/api/projects` `{name, extensions?}` · `PUT /admin/api/projects/{id}` `{name?, extensions?}` | luo tai muuttaa projektin |
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

## 8. Testaaminen tätä palvelinta vasten

[Dataspatium](https://github.com/marwiss/Dataspatium) on tämän palvelimen
kanssa kehitettävä selainasiakas; sen OpenCDE-lähde (kirjautuminen,
BCF-taulukot, Documents API, graafikyselyt, request-id:t) on työstetty
esimerkki kaikesta edellä olevasta, ja sen live-testisarjat ajetaan
kehityspinoa vasten (katso [acceptance.md](../acceptance.md)).

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
- `docker compose -f compose.yaml -f compose.dev.yaml up -d` antaa
  palvelimen osoitteessa `http://localhost:8000` ja Neo4j Browserin portissa
  `:7484`.
- Rekisteröi asiakas sovelluksellesi hallintakäyttöliittymässä (`/admin` →
  Asiakkaat) tai komennolla
  `uv run opencde client create "My app" --redirect-uri http://127.0.0.1/callback --public`.
- `opencde_client.testing` voi suorittaa kirjautumisen ja Documents API
  -sivut ilman selainta automaattitesteissä.
