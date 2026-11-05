<img src="../../opencde/ui/static/icon.svg" alt="" width="72" height="72" align="left">

# Kontroll OpenCDE-palvelin

*[English](../../README.md) · [Svenska](../sv/README.md) · [Dansk](../da/README.md) · [Norsk bokmål](../nb/README.md) · [Norsk nynorsk](../nn/README.md) · Suomi · [Íslenska](../is/README.md)*

Palvelin buildingSMARTin **OpenCDE-rajapinnoille**, rakennettu graafitietokannan päälle:

- **Foundation API 1.0**: palvelujen löytäminen, OAuth2 authorization code ja PKCE, nykyinen käyttäjä
- **BCF API 3.0**: projektit, extensions-arvot, asiat, kommentit, viewpoint-näkymät, tiedostot, asiakirjaviittaukset, asiakirjat, tapahtumat
- **Documents API 1.0**: asiakirjojen valinta ja lataus, lähetys osissa, versiokyselyt

sekä selainkäyttöliittymä käyttäjien, OAuth2-asiakkaiden ja projektien
hallintaan ja valinnainen IFC-graafimoduuli, joka muuttaa lähetetyt
IFC-mallit graafidataksi, jotta BCF-komponentit voidaan yhdistää
rakennusosiin, joihin ne viittaavat.

Projekti sai alkunsa vuoden 2023 tutkimusprototyypistä, jolla kokeiltiin,
voivatko BCF API ja IFC-graafi kantaa Ruotsin rakennuslupiin vaadittavat
digitaaliset tarkastussuunnitelmat. Tämä repo on prototyypin uudelleenkirjoitus
alusta alkaen samoilla toiminnoilla, nykyaikaisilla riippuvuuksilla ja
tietoturva ensimmäisenä vaatimuksena. Tila: **suunnitelman kaikki 11 vaihetta
on toteutettu** (kolme rajapintaa, hallintakäyttöliittymä, asiakaskirjasto,
käyttöönotto, IFC-graafi, hyväksymistarkistuslista ja tietoturvan kovennus);
osallistuminen IfcOpenShelliin odottaa ylläpitäjien vastausta (luonnokset
kansiossa [docs/upstream/](../upstream/)). Katso
[docs/inventory.md](../inventory.md): mitä prototyyppi teki ja missä kukin
toiminto on uudessa koodissa.

## Pika-aloitus (paikallisesti, Docker)

Vaatimukset: Docker (Desktop Windowsissa/macOS:ssä, Engine Linuxissa) ja
[uv](https://docs.astral.sh/uv/).

```sh
git clone https://github.com/marwiss/Kontroll.git
cd Kontroll
cp .env.example .env            # aseta OPENCDE_GRAPH_PASSWORD (vähintään 16 merkkiä)
docker compose -f compose.yaml -f compose.dev.yaml up -d --build
```

Avaa sitten <http://localhost:8000/docs> (vuorovaikutteinen
API-dokumentaatio), <http://localhost:8000/readyz> (valmiustarkistus) ja
<http://localhost:7484> (Neo4j Browser; Bolt osoitteessa `localhost:7697`;
kehitysylikerros välttää Neo4j:n oletusportit, jotka toinen Neo4j samalla
koneella usein varaa). `docker compose logs -f api` näyttää palvelimen lokin.

Ilman Dockeria itse palvelimelle (tietokanta tarvitaan edelleen):

```sh
uv sync                          # asentaa Python 3.13:n ja kaikki riippuvuudet
uv run opencde doctor            # tarkistaa määritykset ja tietokannan
uv run opencde serve             # http://127.0.0.1:8000
```

## Käyttöönotto

Yksi compose-tiedosto ja yksi ylikerros per skenaario sekä julkaistu
usean arkkitehtuurin image (`ghcr.io/marwiss/opencdeserver`, skannattu ja
SBOM:n kanssa jokaisessa julkaisussa):

| Skenaario | Ohje |
|---|---|
| Paikallinen testi omalla koneella | [docs/deploy/local.md](../deploy/local.md) |
| Julkinen https-osoite asiakastesteihin ilman omaa palvelinta (tunneli) | [docs/deploy/tunnel.md](../deploy/tunnel.md) |
| Tuotanto omalla palvelimella Caddyn (automaattinen TLS) ja öisten varmuuskopioiden kanssa | [docs/deploy/vps-caddy.md](../deploy/vps-caddy.md) |
| Coolify, Dokploy, Portainer | [docs/deploy/paas.md](../deploy/paas.md) |
| Konttipalvelu ja hallittu Neo4j AuraDB tai Memgraph Cloud | [docs/deploy/cloud-aura.md](../deploy/cloud-aura.md) |
| Varmuuskopiointi ja palautus (siirrettävä Neo4j:n ja Memgraphin välillä) | [docs/deploy/backup.md](../deploy/backup.md) |

`uv run opencde init --public-url https://cde.example.org` kirjoittaa
tuotannon `.env`-tiedoston uusilla salaisuuksilla; `opencde doctor`
tarkistaa tuloksen.

## Määritykset

Kaikki luetaan ympäristömuuttujista etuliitteellä `OPENCDE_`, `.env`-
tiedostosta tai Docker-salaisuuksista polusta `/run/secrets/opencde_<nimi>`.
Kommentoitu luettelo on tiedostossa [.env.example](../../.env.example).
Oletusarvot ovat turvallisia: tuotanto ei käynnisty ilman julkista
`https`-osoitetta ja tietokannan salasanaa.

## Dokumentaatio

Dokumentaatio on englanniksi; käännökset ruotsiksi, tanskaksi, norjaksi
(bokmål ja nynorsk), suomeksi ja islanniksi ovat suunnitelmissa.

- [docs/inventory.md](../inventory.md): vuoden 2023 prototyypin
  toimintoluettelo ja tilanne uudelleenkirjoituksessa sekä huomioita
  spesifikaatioiden erikoisuuksista
- [docs/client-guide.md](../client-guide.md) ja [docs/examples/](../examples/):
  miten asiakasohjelma rakennetaan; ajettavia esimerkkejä Python-kirjastolla kansiossa [client/](../../client/)
- [docs/flows/](../flows/): OAuth2- ja Documents API -kulkujen sekvenssikaaviot
- [docs/graph-schema.md](../graph-schema.md): graafimalli
- [docs/ifcgraph.md](../ifcgraph.md): valinnainen IFC-graafimoduuli ja esimerkkejä Cypher-kyselyistä
- [docs/ui-styleguide.md](../ui-styleguide.md): palvelimen sivujen säännöt
- [docs/acceptance.md](../acceptance.md): visuaalisen hyväksymisen
  tarkistuslista riippumattomilla asiakasohjelmilla (Bonsai, ifc-lite, Dataspatium)
- [docs/dataspatium-coordination.md](../dataspatium-coordination.md): mitä
  Kontroll ja Dataspatium jakavat ja mitä muuta sovitetaan yhteen, omistajan päätöksin
- [docs/adr/](../adr/): arkkitehtuuripäätökset (graafitietokanta, läpinäkymättömät
  tokenit, siirrettävä Cypher, kehyksetön selainkäyttöliittymä, repostrategia)
- [docs/security/](../security/): uhkamalli, testeihin kytketyt kontrollit,
  OWASP ASVS tason 2 tarkistuslista ja skannerien ajaminen
- [docs/upstream/](../upstream/): luonnokset IfcOpenShellin issueksi ja pull
  requestiksi (ei lähetetty)
- [spec/SOURCES.md](../../spec/SOURCES.md): tarkat spesifikaatioversiot,
  joita vastaan palvelin testataan

## Hallinta

Kirjaudu osoitteessa `/signin` järjestelmänvalvojan tilillä ja avaa `/admin`
hallitaksesi käyttäjiä ja heidän projektiroolejaan, projekteja ja niiden
BCF-extensions-arvoja, OAuth2-asiakkaita, istuntoja, tapahtumalokia,
valinnaista pyyntölokia ja palvelimen kuntotarkistuksia. Jokaisella
käyttäjällä on `/account` omaa salasanaa, omia sovelluksia ja omia istuntoja
varten. Komentorivi (`uv run opencde --help`) tekee saman terminaalista, ja
hallinta-asiakkaat, joilla on `admin`-oikeus (scope), voivat lukea pyyntölokin
osoitteesta `/admin/api/requests`.

## Kontroll ja Dataspatium

Kontroll (palvelin) ja [Dataspatium](https://github.com/marwiss/Dataspatium)
(kokonaan selaimessa toimiva datasovellus) on kehitetty toimimaan yhdessä
palvelimena ja asiakkaana. Dataspatium lisää Kontroll-palvelimen lähteeksi:
sovellus löytää rajapinnat osoitteesta `/foundation/versions`, kirjautuu
OAuth2 authorization code -kululla ja PKCE:llä ja rekisteröi itsensä
julkiseksi asiakkaaksi, kun itserekisteröinti on päällä, luettelee projektin
mallit ja asiakirjat, lukee ja kirjoittaa BCF-asioita kommentteineen ja
3D-näkymästään otettuine viewpoint-näkymineen, lähettää datamäärät, tiedostot
ja työtilapaketit Documents API:n kautta, kyselee IFC-graafia Cypherillä
Boltin yli, kun operaattori julkaisee sen, ja lähettää jokaisessa kutsussa
`X-Request-ID`-otsakkeen, jotta pyyntöloki täällä ja sovelluksen loki
näyttävät saman keskustelun. Sovellus lukee palvelimen kyvykkyysasiakirjan
(`/.well-known/kontroll`) nähdäkseen, mitkä laajennukset ovat päällä, ja
toimii palvelimen virhevastauksiinsa lisäämien pysyvien virhekoodien mukaan.
Graafikyselyjä, hallintarajapintaa, kyvykkyysasiakirjaa ja virhekoodeja
lukuun ottamatta, jotka ovat spesifikaatioiden ulkopuolisia laajennuksia,
kaikki, mitä Dataspatium tekee palvelinta vastaan, kulkee kolmen
OpenCDE-rajapinnan kautta, joten muutkin OpenCDE-asiakkaat toimivat, ja
Kontroll palvelee mitä tahansa OpenCDE-asiakasta. Kaksi tuotetta asennetaan
erikseen: tämä repo ei niputa Dataspatiumia mukaansa (lisenssit eroavat, AGPL
täällä ja PolyForm Strict siellä), ja Dataspatiumin README kertoo, miten
sovellus ladataan. Asiakaspuoli kuvataan Dataspatiumin README-tiedostossa ja
sen dokumentaatiossa (`docs/kallor.md`, `docs/cad-bim.md`); parin
hyväksymisajot ovat täällä tiedostossa [docs/acceptance.md](../acceptance.md),
ja se, mitä kaksi projektia sovittavat yhteen, on tiedostossa
[docs/dataspatium-coordination.md](../dataspatium-coordination.md).

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
rakenne kuin Dataspatiumissa); dokumentaation ja selainkäyttöliittymän on
tarkoitus olla saatavilla samoilla kielillä, englanti aina yhtenä
vaihtoehtona, ja yhteiset termit noudattavat Dataspatiumin sanastoa.

## Tietoturva

Katso [SECURITY.md](../../SECURITY.md): miten haavoittuvuudesta ilmoitetaan ja
mitä projekti tekee pysyäkseen turvallisena.

## Lisenssi

Palvelin on lisensoitu GNU Affero General Public License v3.0 -lisenssillä tai
uudemmalla ([LICENSE](../../LICENSE)): se on palvelinohjelmisto, ja AGPL:n
verkkolauseke pitää hostattujen asennusten parannukset avoimina.
Asiakaskirjasto kansiossa [client/](../../client/) on LGPL-3.0-or-later.
Spesifikaatiotiedostot kansiossa [spec/](../../spec/) ovat © buildingSMART
International, ja niitä jaetaan muuttamattomina testausta varten.
