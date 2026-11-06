[Svenska](../../README.md) · [Dansk](../da/README.md) · [Norsk bokmål](../nb/README.md) · [Norsk nynorsk](../nn/README.md) · **Suomi** · [Íslenska](../is/README.md) · [English](../en/README.md)

<img src="../../opencde/ui/static/icon-192.png" alt="" width="64" height="64" align="left">

# Kontroll OpenCDE-palvelin

Kontroll on palvelin buildingSMARTin **OpenCDE-rajapinnoille** (Foundation
API 1.0, BCF API 3.0 ja Documents API 1.0). Se on rakennettu
graafitietokannan päälle, siinä on selainpohjainen hallinta ja valinnainen
IFC-graafimoduuli, joka yhdistää BCF-komponentit rakennusosiin, joihin ne
viittaavat. Se sai alkunsa vuoden 2023 tutkimusprototyypistä Ruotsin
rakennuslupien digitaalisia tarkastussuunnitelmia varten ja kirjoitettiin
uudelleen alusta alkaen tietoturva ensimmäisenä vaatimuksena.

![Kontroll-palvelimen hallinnan yleiskuva: käyttäjien, projektien, asiakkaiden, asioiden ja asiakirjojen määrät, tietokannan tila ja viimeisimmät tapahtumalokin merkinnät](../images/admin-overview.png)

**Sisältö**

- [Lataa ja aloita](#lataa-ja-aloita)
- [Vaatimukset](#vaatimukset)
- [Mitä voit tehdä](#mitä-voit-tehdä)
- [Kontroll ja Dataspatium](#kontroll-ja-dataspatium)
- [Lue lisää](#lue-lisää)
- [Rajoitukset lyhyesti](#rajoitukset-lyhyesti)
- [Virheet ja ehdotukset](#virheet-ja-ehdotukset)
- [Kehitys](#kehitys)
- [Lisenssi](#lisenssi)

## Lataa ja aloita

### Pika-aloitus (paikallisesti, Docker)

1. **Lataa.** Kloonaa repo tai hae julkaistu image
   `ghcr.io/marwiss/opencdeserver` (useita arkkitehtuureja, skannattu ja
   SBOM:n kanssa jokaisessa julkaisussa):

   ```sh
   git clone https://github.com/marwiss/Kontroll.git
   cd Kontroll
   ```

2. **Määritä.** Kopioi `.env.example` tiedostoksi `.env` ja aseta
   `OPENCDE_GRAPH_PASSWORD` (vähintään 16 merkkiä). Jokainen asetus selitetään
   tiedostossa [.env.example](../../.env.example).
3. **Käynnistä.** `docker compose -f compose.yaml -f compose.dev.yaml up -d --build`
   käynnistää palvelimen osoitteessa <http://127.0.0.1:8000> ja
   Neo4j-tietokannan. `docker compose logs -f api` näyttää palvelimen lokin.
4. **Katsele ympärillesi.** <http://127.0.0.1:8000/docs> on vuorovaikutteinen
   API-dokumentaatio, <http://127.0.0.1:8000/readyz> valmiustarkistus ja
   <http://127.0.0.1:7484> Neo4j Browser (Bolt osoitteessa `127.0.0.1:7697`;
   kehitysylikerros välttää Neo4j:n oletusportit, jotka toinen Neo4j samalla
   koneella usein varaa).
5. **Lisää demodata ja kirjaudu.**
   `docker compose -f compose.yaml -f compose.dev.yaml exec api opencde seed`
   luo demokäyttäjät ja -projektit ja tulostaa niiden salasanat kerran.
   Kirjaudu osoitteessa <http://127.0.0.1:8000/signin> käyttäjänä `admin` ja
   avaa `/admin`.
6. **Yhdistä asiakasohjelma.** Rekisteröi sovelluksesi kohdassa *Clients*
   (tai anna sen rekisteröityä itse, kun
   `OPENCDE_DYNAMIC_CLIENT_REGISTRATION=true`) ja osoita se osoitteeseen
   `http://127.0.0.1:8000`; [Dataspatium](#kontroll-ja-dataspatium) ja
   Python-kirjasto kansiossa [client/](../../client/) ovat valmiita
   asiakasohjelmia.
   Jos kirjaudut Dataspatiumista, seuraa [pika-aloitusta](quickstart.md): siinä on
   kaikki tarvittavat asetukset ja ohjeet siihen, mitä tehdä, jos jokin menee vikaan.

Ilman Dockeria itse palvelimelle (tietokanta tarvitaan edelleen):

```sh
uv sync                          # asentaa Python 3.13:n ja kaikki riippuvuudet
uv run opencde doctor            # tarkistaa määritykset ja tietokannan
uv run opencde serve             # http://127.0.0.1:8000
```

### Käyttöönotto

Yksi compose-tiedosto ja yksi ylikerros per skenaario:

| Skenaario | Ohje |
|---|---|
| Paikallinen testi omalla koneella | [docs/fi/deploy/local.md](deploy/local.md) |
| Julkinen https-osoite asiakastesteihin ilman omaa palvelinta (tunneli) | [docs/fi/deploy/tunnel.md](deploy/tunnel.md) |
| Tuotanto omalla palvelimella Caddyn (automaattinen TLS) ja öisten varmuuskopioiden kanssa | [docs/fi/deploy/vps-caddy.md](deploy/vps-caddy.md) |
| Coolify, Dokploy, Portainer | [docs/fi/deploy/paas.md](deploy/paas.md) |
| Konttipalvelu ja hallittu Neo4j AuraDB tai Memgraph Cloud | [docs/fi/deploy/cloud-aura.md](deploy/cloud-aura.md) |
| Varmuuskopiointi ja palautus (siirrettävä Neo4j:n ja Memgraphin välillä) | [docs/fi/deploy/backup.md](deploy/backup.md) |

`uv run opencde init --public-url https://cde.example.org` kirjoittaa
tuotannon `.env`-tiedoston uusilla salaisuuksilla; `opencde doctor`
tarkistaa tuloksen.

### Määritykset

Kaikki luetaan ympäristömuuttujista etuliitteellä `OPENCDE_`,
`.env`-tiedostosta tai Docker-salaisuuksista polusta
`/run/secrets/opencde_<nimi>`. Kommentoitu luettelo on tiedostossa
[.env.example](../../.env.example). Oletusarvot ovat turvallisia: tuotanto ei
käynnisty ilman julkista `https`-osoitetta ja tietokannan salasanaa, eikä
mikään ole auki ennen kuin se on määritetty.

## Vaatimukset

- Windows, macOS tai Linux ja Docker (Desktop Windowsissa/macOS:ssä, Engine
  Linuxissa), tai Python 3.11 tai uudempi, [uv](https://docs.astral.sh/uv/) ja
  oma Neo4j 5.26- tai Memgraph 3.14 -tietokanta.
- Noin 1 Gt muistia tietokantakontille (`NEO4J_HEAP` ja `NEO4J_PAGECACHE`
  tiedostossa `.env`), enemmän IFC-graafimoduulin kanssa.
- Paikallisesti: portti 8000 palvelimelle ja 7484/7697 tietokannalle, kaikki
  sidottuina osoitteeseen `127.0.0.1`. Tuotannossa: portit 80 ja 443
  tavoitettavissa internetistä ja DNS-nimi palvelimelle.
- Asiakasohjelmat tarvitsevat tuotannossa `https`-osoitteen; paikallisesti
  `http://127.0.0.1` hyväksytään redirect-URI:ksi, ja `http://localhost` asetuksella `OPENCDE_ALLOW_LOCALHOST_REDIRECTS=true`.

## Mitä voit tehdä

- **Foundation API 1.0**: palvelujen löytäminen, OAuth2 authorization code ja
  PKCE jokaiselle asiakkaalle, nykyinen käyttäjä, tokenien peruutus ja
  dynaaminen asiakasrekisteröinti julkisine asiakkaineen (oletuksena pois
  päältä).
- **BCF API 3.0**: projektit, extensions-arvot, asiat OData-kyselyineen,
  kommentit, viewpoint-näkymät kuvakaappauksineen, bittikarttoineen ja
  komponentteineen, tiedostot, asiakirjaviittaukset, asiakirjat ja
  tapahtumalokit, kaikki validoituina buildingSMARTin skeemoja vasten.
- **Documents API 1.0**: asiakirjojen valinta ja lataus, lähetys osissa
  palvelimen metatieto- ja valintasivujen avulla, versiokyselyt ETag-tunnistein.
- **Hallinta** selaimessa: kirjaudu osoitteessa `/signin` järjestelmänvalvojan
  tilillä ja avaa `/admin` hallitaksesi käyttäjiä ja heidän projektiroolejaan,
  projekteja ja niiden BCF-extensions-arvoja, OAuth2-asiakkaita, istuntoja,
  tapahtumalokia, valinnaista pyyntölokia ja palvelimen kuntotarkistuksia.
  Jokaisella käyttäjällä on `/account` omaa salasanaa, omia sovelluksia ja
  omia istuntoja varten. Komentorivi (`uv run opencde --help`) tekee saman
  terminaalista.
- **Spesifikaatioiden ulkopuoliset laajennukset**, jokainen sellaiseksi
  merkittynä: kyvykkyysasiakirja osoitteessa `/.well-known/kontroll`, joka
  kertoo asiakkaalle, mitkä laajennukset ovat päällä, pysyvä `code`
  jokaisessa virhevastauksessa, pyyntöloki asiakasohjelmien vianetsintään
  (`/admin/requests`, `GET /admin/api/requests` `admin`-oikeudella) ja
  IFC-graafimoduuli, joka muuttaa lähetetyt IFC-mallit BCF-komponentteihin
  yhdistetyksi graafidataksi.
- **Asiakaskirjasto** Pythonille ([client/](../../client/), LGPL) ajettavine
  esimerkkeineen sekä Dockerfile, compose-ylikerrokset ja julkaistu image
  jokaista käyttöönottoskenaariota varten.
- **Tila**: suunnitelman kaikki yksitoista vaihetta on toteutettu (kolme
  rajapintaa, hallinta, asiakaskirjasto, käyttöönotto, IFC-graafi,
  hyväksymistarkistuslista ja tietoturvan kovennus); osallistumista
  IfcOpenShelliin ei ole vielä ehdotettu (luonnokset kansiossa
  [docs/upstream/](../upstream/)). [docs/inventory.md](../inventory.md)
  kertoo, mitä vuoden 2023 prototyyppi teki ja missä kukin toiminto on
  uudessa koodissa.

## Kontroll ja Dataspatium

Kontroll (palvelin) ja [Dataspatium](https://github.com/marwiss/Dataspatium)
(kokonaan selaimessa toimiva datasovellus) on kehitetty toimimaan yhdessä
palvelimena ja asiakkaana, ja sama julkaisunumero molemmissa tarkoittaa, että
ne toimivat yhdessä: Dataspatium 2.5.0 toimii Kontroll 2.5.0:n kanssa
([pika-aloitus](quickstart.md)).
Dataspatium lisää Kontroll-palvelimen lähteeksi: sovellus löytää rajapinnat
osoitteesta `/foundation/versions`, kirjautuu OAuth2 authorization code
-kululla ja PKCE:llä ja rekisteröi itsensä julkiseksi asiakkaaksi, kun
dynaaminen rekisteröinti on päällä, luettelee projektin mallit ja asiakirjat,
lukee ja kirjoittaa BCF-asioita kommentteineen ja 3D-näkymästään otettuine
viewpoint-näkymineen, lähettää datamäärät, tiedostot ja työtilapaketit
Documents API:n kautta, kyselee IFC-graafia Cypherillä Boltin yli, kun
ylläpitäjä julkaisee sen, ja lähettää jokaisessa kutsussa
`X-Request-ID`-otsakkeen, jotta pyyntöloki täällä ja sovelluksen loki
näyttävät saman keskustelun. Sovellus lukee palvelimen kyvykkyysasiakirjan
nähdäkseen, mitkä laajennukset ovat päällä, ja toimii palvelimen
virhevastauksiin lisäämien virhekoodien mukaan.

Merkittyjä laajennuksia lukuun ottamatta kaikki, mitä Dataspatium tekee
palvelinta vastaan, kulkee kolmen OpenCDE-rajapinnan kautta, joten muutkin
OpenCDE-asiakkaat toimivat, ja Kontroll palvelee mitä tahansa
OpenCDE-asiakasta. Kaksi tuotetta asennetaan erikseen: tämä repo ei niputa
Dataspatiumia mukaansa (lisenssit eroavat, AGPL täällä ja PolyForm Strict
siellä), ja Dataspatiumin README kertoo, miten sovellus ladataan.
Asiakaspuoli kuvataan Dataspatiumin README-tiedostossa ja sen
dokumentaatiossa; parin hyväksymisajot ovat täällä tiedostossa
[docs/acceptance.md](../acceptance.md), ja se, mitä kaksi projektia
sovittavat yhteen, on tiedostossa
[docs/dataspatium-coordination.md](../dataspatium-coordination.md).

## Lue lisää

- [docs/fi/quickstart.md](quickstart.md): Kontroll ja Dataspatium yhdessä
  kahdessakymmenessä minuutissa, tyhjästä koneesta 3D-näkymässä luotuun asiaan.
- [docs/fi/client-guide.md](client-guide.md) ja [docs/examples/](../examples/):
  miten asiakasohjelma rakennetaan, kyvykkyysasiakirja, virhekoodit ja
  ajettavia esimerkkejä Python-kirjastolla kansiossa [client/](../../client/).
- [docs/fi/architecture.md](architecture.md): miten osat liittyvät toisiinsa, mitä pyynnölle tapahtuu ja missä kaikki on koodissa.
- [docs/fi/glossary.md](glossary.md): dokumentaation käyttämät sanat.
- [docs/fi/flows/](flows/): OAuth2-, Documents API- ja BCF-näkymäkulkujen sekvenssikaaviot.
- [docs/fi/graph-schema.md](graph-schema.md): graafimalli.
- [docs/fi/ifcgraph.md](ifcgraph.md): valinnainen IFC-graafimoduuli ja esimerkkejä Cypher-kyselyistä.
- [docs/fi/ui-styleguide.md](ui-styleguide.md): palvelimen sivujen ja tunnuksen säännöt.
- [docs/acceptance.md](../acceptance.md): visuaalisen hyväksymisen
  tarkistuslista riippumattomilla asiakasohjelmilla (Bonsai, ifc-lite, Dataspatium).
- [docs/dataspatium-coordination.md](../dataspatium-coordination.md): mitä
  Kontroll ja Dataspatium jakavat sekä omistajan päätökset.
- [docs/inventory.md](../inventory.md): vuoden 2023 prototyypin
  toimintoluettelo ja tilanne uudelleenkirjoituksessa sekä huomioita
  spesifikaatioiden erikoisuuksista.
- [docs/adr/](../adr/): arkkitehtuuripäätökset (graafitietokanta, läpinäkymättömät
  tokenit, siirrettävä Cypher, kehyksetön selainkäyttöliittymä, repostrategia).
- [docs/fi/security/](security/): uhkamalli, testeihin kytketyt kontrollit,
  OWASP ASVS tason 2 tarkistuslista, henkilötiedot ja säilytysajat sekä
  skannerien ajaminen.
- [docs/upstream/](../upstream/): luonnokset IfcOpenShellin issueksi ja pull
  requestiksi (ei lähetetty).
- [spec/SOURCES.md](../../spec/SOURCES.md): tarkat spesifikaatioversiot,
  joita vastaan palvelin testataan.

Dokumentaatio on tämän README-tiedoston seitsemällä kielellä: englanti
hakemistossa `docs/`, muut hakemistoissa `docs/<kieli>/`. Projektilokit
(hyväksyntä, toimintoluettelo, yhteensovitus), arkkitehtuuripäätökset,
IfcOpenShell-luonnokset ja CONTRIBUTING pidetään englanniksi.

### Lisälukemista

- [BCF API](https://github.com/buildingSMART/BCF-API), [Foundation API](https://github.com/buildingSMART/foundation-API) ja [Documents API](https://github.com/buildingSMART/documents-API):
  määrittelyt, joita palvelin noudattaa.
- [IFC](https://github.com/buildingSMART/IFC4.x-development): rakennusmallien tiedostomuoto.
- [RFC 9700](https://www.rfc-editor.org/rfc/rfc9700): nykyiset parhaat käytännöt OAuth 2.0:n turvallisuudelle, ja
  [OAuth 2.1](https://datatracker.ietf.org/doc/draft-ietf-oauth-v2-1/), luonnos, joka kokoaa ne.
- [RFC 7636](https://www.rfc-editor.org/rfc/rfc7636) (PKCE), [RFC 8252](https://www.rfc-editor.org/rfc/rfc8252) (sovellukset tietokoneessa tai puhelimessa) ja
  [RFC 7591](https://www.rfc-editor.org/rfc/rfc7591) (asiakkaiden rekisteröinti).
- [OWASP ASVS](https://owasp.org/www-project-application-security-verification-standard/): turvallisuustyön tarkistuslista.

## Rajoitukset lyhyesti

- Palvelin toteuttaa BCF API 3.0:n, ei 2.1:tä; vanhemmille asiakkaille on vain
  kolme vanhaa löytämisaliasta polun `/bcf/` alla.
- Projektin vienti BCFzip-tiedostoksi jää asiakasohjelmille; palvelin
  tallentaa asiat, kommentit ja viewpoint-näkymät rajapinnan määrittelemässä
  muodossa.
- Neo4j:n ja Memgraphin community-versioissa ei ole vain lukuun oikeutettuja
  tietokantakäyttäjiä, joten julkaistu Bolt-portti antaa täydet oikeudet
  salasanan haltijalle. Portti pysyy kiinni, ellei järjestelmänvalvoja julkaise
  sitä tarkoituksella; hallintarajapinnan lukeva graafikysely
  (`OPENCDE_GRAPH_QUERY_ENABLED`) antaa Cypherin ilman porttia.
- IFC-graafin tuonti ajetaan erillisessä prosessissa muisti- ja aikarajoin
  (`OPENCDE_IFCGRAPH_*`); hyvin suuret mallit hylätään sen sijaan, että ne
  jäisivät puoliksi tuoduiksi.
- Selainsivut palvelevat järjestelmänvalvojia sekä OAuth2- ja Documents API
  -kulkuja; loppukäyttäjät työskentelevät asiakasohjelmassa, kuten
  Dataspatiumissa tai Bonsaissa.
- Sivut ovat tämän README-tiedoston seitsemällä kielellä (vaihda jokaisen sivun
  alareunasta); komentorivi ja rajapintojen virheviestit ovat englanniksi.
- Ulkoista auditointia ei ole vielä tehty. Tiedostossa
  [docs/fi/security/pentest-howto.md](security/pentest-howto.md) kuvatut
  OAuch- ja testssl-ajot ovat ylläpitäjän askeleet ennen tuotantokäyttöönottoa.

## Virheet ja ehdotukset

Ilmoita virheet ja toiveet *Issues*-kohdassa täällä GitHubissa. Kerro, mitä
palvelinversiota käytät (`version` osoitteessa `/.well-known/kontroll` tai
`/healthz`), mitä asiakasohjelmaa käytit ja epäonnistuneen kutsun
`X-Request-ID`; pyyntöloki ja asiakasohjelman loki jakavat sen. Älä liitä
henkilötietoja tai salaisuuksia. Se, miten muutokset otetaan vastaan, kerrotaan
tiedostossa [CONTRIBUTING.md](../../CONTRIBUTING.md). Tietoturvahaavoittuvuudesta
ilmoitetaan tiedoston [SECURITY.md](../../SECURITY.md) mukaisesti, ei
issuena.

## Kehitys

```sh
uv run pytest                    # yksikkö-, yhdenmukaisuus- ja tietoturvatestit
uv run pytest -m integration     # käynnistää Neo4j:n/Memgraphin testcontainersilla (vaatii Dockerin)
uv run pytest -m e2e             # asiakaskirjasto käynnissä olevaa palvelinta vastaan (vaatii Dockerin)
uv run pytest -m ui              # Playwright + axe-core (uv sync --group ui; playwright install chromium)
uv run ruff format . && uv run ruff check .
uv run ty check opencde client/opencde_client
```

Koodi ja kommentit ovat englanniksi, koska palvelin ja asiakaskirjasto on
tarkoitus luovuttaa IfcOpenShelliin, jonka käytäntöjä (ruff, 120 saraketta)
tyyli noudattaa. README on englanniksi, ruotsiksi, tanskaksi, norjaksi
(bokmål ja nynorsk), suomeksi ja islanniksi (`docs/<kieli>/README.md`, sama
rakenne kuin Dataspatiumissa); dokumentaatio ja selainkäyttöliittymä ovat
saatavilla samoilla kielillä, englanti aina yhtenä
vaihtoehtona, ja yhteiset termit noudattavat Dataspatiumin sanastoa. Jokainen
push ajaa lintauksen, tyyppitarkistuksen, testisarjat kolmella
Python-versiolla, selaintestit axe-corella ja staattiset tietoturvatarkistukset;
yölliset ajot suorittavat OWASP ZAP:n, Schemathesisin ja Trivyn. Katso
[CONTRIBUTING.md](../../CONTRIBUTING.md).

## Lisenssi

Palvelin on lisensoitu GNU Affero General Public License v3.0 -lisenssillä tai
uudemmalla ([LICENSE](../../LICENSE)): se on palvelinohjelmisto, ja AGPL:n
verkkolauseke pitää hostattujen asennusten parannukset avoimina.
Asiakaskirjasto kansiossa [client/](../../client/) on LGPL-3.0-or-later.
Spesifikaatiotiedostot kansiossa [spec/](../../spec/) ovat © buildingSMART
International, ja niitä jaetaan muuttamattomina testausta varten. Katso
[SECURITY.md](../../SECURITY.md): miten haavoittuvuudesta ilmoitetaan ja mitä
projekti tekee pysyäkseen turvallisena.
