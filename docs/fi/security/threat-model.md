# Uhkamalli

Tila: kattaa vaiheet 0–11. Jokainen vaihe lisää tuomansa suojattavat kohteet,
uhat ja kontrollit, `controls.md` kuvaa jokaisen kontrollin testiin, ja
`asvs-checklist.md` dokumentoi OWASP ASVS tason 2 itsearvioinnin.

## Suojattavat kohteet

| Kohde | Missä | Miksi sillä on merkitystä |
|---|---|---|
| Käyttäjien tunnistetiedot (Argon2id-tiivisteet) | graafin `User` | Tilin kaappaus antaa pääsyn kaikkiin käyttäjän projekteihin |
| OAuth2-asiakassalaisuudet, koodit, access- ja refresh-tokenit (SHA-256-tiivisteet) | graafin `Client`, `AuthorizationCode`, `AccessToken`, `RefreshToken` | Käyttäjien tai asiakkaiden esittäminen |
| Projektidata: asiat, kommentit, viewpointit, tilannekuvat, asiakirjojen metatiedot | graafi + tallennustila | Luottamuksellista rakennustietoa useilta organisaatioilta |
| Asiakirjat (IFC-mallit ja muut tiedostot) | tallennustaustajärjestelmä | Suurta, luottamuksellista, mahdollisesti haitallista syötettä jäsentimille |
| Tapahtumaloki | graafin `AuditEvent` | Todisteet poikkeaman jälkeen |
| Asetukset ja salaisuudet | `.env`, Docker secrets | Täydellinen vaarantuminen, jos ne vuotavat |

## Toimijat

Anonyymi internetin käyttäjä; toisen projektin todennettu käyttäjä; saman
projektin todennettu käyttäjä alemmalla roolilla; rekisteröity OAuth2-asiakas
(tai joku, jolla on sen salaisuus); järjestelmänvalvoja; palveluntarjoaja ja
kuka tahansa, joka voi lukea lokeja tai varmuuskopioita; vahingollinen
asiakirjan laatija.

## Luottamusrajat

Internet → Caddy (TLS) → rajapinta → graafitietokanta ja tallennustila,
kaikki yksityisessä verkossa. Selain (kirjautuminen, suostumus, asiakirjojen
valinta, hallinta) on erillinen raja Bearer-tokeneita käyttäviin
rajapinta-asiakkaisiin nähden.

## Uhat ja kontrollit (STRIDE, kasvaa vaiheittain)

| Uhka | Esimerkki | Kontrolli | Vaihe |
|---|---|---|---|
| Tietovuoto virhevastausten kautta | Pinojäljet, toistettu syöte, sisäiset tunnukset | Yksi virherunko `{"message"}`; validointivirheet nimeävät kentät, eivät koskaan arvoja; 5xx kirjataan vain request-id:n kanssa | 0 |
| Tietovuoto lokien kautta | Tokeneita tai salasanoja lokiriveillä | Peittoprosessori jokaiselle lokitapahtumalle; pyyntö- tai vastausrunkoja ei kirjata | 0 |
| Peukalointi ylisuurilla tai virheellisesti muodostetuilla rungoilla | Muistin loppuminen | Rungon kokoraja ennen jäsentämistä (413); suoratoisto tavulaskennalla lähetyksissä | 0, 5 |
| Clickjacking, MIME-nuuskinta, referrer-vuodot | Hyökkääjän kehystämät sivut; `code` vuotanut Refererissä | CSP `frame-ancestors 'none'`, `X-Content-Type-Options`, `Referrer-Policy: no-referrer` jokaisessa vastauksessa | 0 |
| Request-id:n väärentäminen | Loki-injektio `X-Request-ID`:n kautta | Vain `[A-Za-z0-9._-]{1,128}` hyväksytään; muuten luodaan uusi | 0 |
| Oikeuksien korotus asetusvirheiden kautta | http tuotannossa, tyhjä tietokannan salasana | Asetukset kieltäytyvät käynnistymästä | 0 |
| Toimitusketju | Vaarantunut riippuvuus tai action | `uv.lock`, pip-audit, Dependabot, SHA:lla kiinnitetyt actionit, zizmor | 0 |
| Käyttäjien ja asiakkaiden väärentäminen, toisto, mix-up, CSRF suostumuksessa | | Vain PKCE S256, tarkka redirect_uri, `state`, `iss`, kertakäyttöiset koodit, tiivistetyt tokenit, kierto ja perheen peruutus, CSRF-tokenit | 2 |
| Rikkinäinen objektitason valtuutus | Toisen projektin asian lukeminen guidilla | Jokainen kysely alkaa käyttäjäsolmusta ja kulkee MEMBER_OF:n kautta; 404 vieraille objekteille | 3 |
| Injektio OData:n kautta | `$filter` muotoiltu muuttamaan Cypheriä | Jäsennin → AST → sallittujen lista → parametrit | 1, 3 |
| Kuvaksi naamioitu tallennettu sisältö | HTML tai skripti lähetetty tilannekuvana ja tarjoiltu takaisin | Magic bytes -tunnisteiden on vastattava ilmoitettua tyyppiä; kuvat tarjoillaan `image/*`-tyyppinä `nosniff`-otsakkeella; kokoraja ennen dekoodausta | 4 |
| Selaimen renderöimät lähetetyt tiedostot | Tallennettu XSS asiakirjan latauksen kautta | Asiakirjat ja snippetit ovat aina `application/octet-stream`-liitteitä puhdistetuin, RFC 8187 -koodatuin nimin; niitä ei renderöidä koskaan | 4, 5 |
| Rungon kokorajan kiertäminen | Chunked transfer ilman `Content-Length`-otsaketta; binäärireitti käytetty JSON-tulvaan | Tavut lasketaan saapuessaan; vain binäärireitit on vapautettu, ja ne lasketaan itse `max_upload_bytes`-rajaa vasten | 4 |
| Vahingolliset asiakirjat | Zip-pommit, path traversal, jäsentimien hyväksikäyttö | Palvelimen luomat tunnukset, kokorajat, rajattu purku, jäsennys hiekkalaatikoidussa työprosessissa | 5, 9 |
| Vuotanut Documents API -linkki | `upload_ui_url` tai `select_documents_url` nähty lokissa, historiassa tai olan yli | 256-bittinen token tallennettu tiivisteenä, 10 minuutin voimassaolo, yksi kulku, ja sivu vaatii lisäksi selainistunnon samana käyttäjänä; rajapinnan puolen URLit käyttävät julkista tunnusta ja bearer-tokenia | 5 |
| Callbackin väärinkäyttö | Palvelin saadaan hakemaan hyökkääjän URL (SSRF), avoin uudelleenohjaus callbackin kautta | Palvelin ei koskaan hae callbackia; vain http(s)-URLit hyväksytään, ja selain ohjataan URL-koodatuin parametrein; callbackilla on oma vanhenemisaika | 5 |
| Epätäydelliset tai ylisuuret lähetykset | Ilmoitettua suuremmat osat, summat jotka eivät täsmää, hylätyt osat jotka täyttävät levyn | Tarkka aluetarkistus osaa kohti, koko tarkistettu koottaessa, SHA-256 tallennettu, osat ja istunnot vanhenevat ja siivotaan tiedostoineen | 5 |
| Hyökkäykset selainistuntoon | Kiinnitys, CSRF, varkaus, oikeuksien korotus | Satunnainen tiivistetty eväste luodaan kirjautuessa, `HttpOnly`, `SameSite=Strict`, `Secure` https:n yli, joutoajan ja absoluuttinen vanheneminen, allekirjoitetut lomaketokenit sekä `Sec-Fetch-Site`/`Origin`-tarkistukset, roolitarkistukset jokaisella sivulla | 5, 6 |
| Korotus järjestelmänvalvojaksi | Jäsen pääsee `/admin`-sivuille; varastettua hallintaistuntoa käytetään nollauksiin tai salaisuuden kierrätykseen; järjestelmänvalvoja lukittu ulos | Hallintarooli tarkistetaan jokaisella hallintareitillä (muuten HTML 404); vaaralliset toiminnot vaativat järjestelmänvalvojan oman salasanan uudelleen; järjestelmänvalvojat eivät voi poistaa käytöstä, alentaa tai poistaa itseään; jokainen toiminto kirjataan tapahtumalokiin | 6 |
| Käyttöliittymän kautta paljastuvat salaisuudet | Asiakassalaisuudet tai luodut salasanat luettavissa myöhemmin | Näytetään kerran luotaessa tai kierrätettäessä, tallennetaan tiivisteinä; asetussivu peittää asetusten salaisuudet | 6 |
| Vaarantuminen asennuksen kautta | Tietokanta tavoitettavissa internetistä; salaisuudet leivottu kuvaan; etuoikeutettu kontti; väärennetty `X-Forwarded-For` | Tietokanta vain yksityisessä compose-verkossa; salaisuudet `.env`-tiedostosta tai `opencde init`-komennon luomista Docker secreteistä; ei-root, vain luku -kontti ilman capabilities-oikeuksia; välitettyihin otsakkeisiin luotetaan vain `OPENCDE_TRUSTED_PROXIES`-lähteistä; kuva skannattu SBOM:n kanssa jokaisessa julkaisussa | 8 |
| Varmuuskopiot vuotona tai menetyksenä | Arkisto muiden luettavissa; palautus tuotantodatan päälle | Sovellustason vienti ylläpitäjän varmuuskopiotaltioon (salaus levossa on ylläpitäjän vastuulla); `opencde restore` pysähtyy ei-tyhjään tietokantaan, ellei pakoteta; manifesti tallentaa skeeman version | 8 |
| Vihamielinen IFC-tiedosto | Jäsentimen kaatuminen, muistin loppuminen, jumiutuminen, entiteettitulva | Muunnos erillisessä työprosessissa aika-, muisti- ja entiteettirajoin; epäonnistuminen kirjataan `IfcModel`-solmuun eikä palvelin kärsi; nimiöt ja suhteiden nimet validoidaan ennen kuin ne saavuttavat Cypherin | 9 |
| Kolmannen osapuolen koodi palvelimen sivulla | Vaarantunut CDN, joka tarjoilee Swagger UI:n, ajaa skriptiä palvelimen originissa | Interaktiivinen rajapintadokumentaatio on tuotannossa pois päältä, ellei sitä kytketä päälle; sillä on oma Content-Security-Policy, joka listaa CDN:n; jokainen muu sivu lataa vain saman originin resursseja; CORS koskee vain rajapintapolkuja, joten sivut eivät ole koskaan luettavissa cross-origin | 11 |
| Vanhentunut peruskuva | Korjattavia haavoittuvuuksia jakelussa tai pipin mukana tulevissa kirjastoissa | Ajoaikavaihe soveltaa jakelun turvapäivitykset ja poistaa pipin; Trivy kaataa julkaisun ja yöskannauksen korjattavista HIGH- tai CRITICAL-löydöksistä | 8, 11 |
| Itse rekisteröityneet julkiset asiakkaat | Kuka tahansa rekisteröi asiakkaan vakuuttavalla nimellä ja houkuttelee käyttäjät suostumaan | Rekisteröinti on oletuksena pois päältä ja nopeusrajoitettu; suostumussivu nimeää asiakkaan ja isännän, johon se ohjaa; julkiset asiakkaat tarvitsevat PKCE:n ja tarkat redirect-URIt kuten jokainen asiakas; järjestelmänvalvojat voivat poistaa asiakkaita käytöstä tai poistaa ne `/admin`-sivuilla | 11 |
| Asiakas, joka on merkitty kirjautumaan ilman PKCE:tä | Varastettu koodi lunastetaan, tai PKCE:tä käyttävä pyyntö suostutellaan luopumaan siitä | Merkintä on ylläpitäjän valinta tai seuraa, kun itserekisteröinti on käytössä, rekisteröitymisestä BCF API 2.1:n osoitteessa; vain luottamuksellisella asiakkaalla voi olla se, joten varastettu koodi on arvoton ilman salaisuutta; verifier koodille ilman challengea hylätään; pyynnössä nimetty redirect-URI on nimettävä uudelleen; tarkastusloki kertoo, milloin PKCE jätettiin pois | 2 |
| Pyyntöloki henkilötietojen tai salaisuuksien varastona | Kyselymerkkijonoja nimineen, tokeneita otsakkeissa, runkoja asiatekstein | Oletuksena pois päältä; merkinnät sisältävät polun ilman kyselymerkkijonoa, ei otsakkeita eikä runkoja; säilytys rajattu `request_log_retention_hours`-asetuksella; lukuoikeus vain järjestelmänvalvojille, sivulla istunnon ja `/admin/api/requests`-osoitteessa nimenomaisesti pyydetyn `admin`-scopen sisältävän bearer-tokenin kautta | 11 |
| Graafikyselypäätepiste tienä tietomallin ohi | Järjestelmänvalvojan Cypher lukee tunnistetietojen tiivisteitä, kirjoittaa, muuttaa skeemaa tai kaappaa tietokannan | Oletuksena pois päältä (`OPENCDE_GRAPH_QUERY_ENABLED`); vain nimenomaisesti pyydetyn `admin`-scopen omaavat järjestelmänvalvojat; lukutransaktio sekä kirjoittavien lausekkeiden ja kaikkien muiden kuin skeemaproseduurien hylkäys (teksti tarkistetaan merkkijonot, kommentit ja takahipsuilla merkityt nimet poistettuina, joten myös Memgraph, joka ei pakota lukutilaa, katetaan); suojatut ominaisuudet hylätään lauseessa ja parametreissa, poistetaan jokaisesta vastauksesta, Argon2-tiivisteet peitetään; rivi- ja aikarajat; jokainen kutsu kirjataan lauseen kanssa, ei koskaan parametrien | 11 |
