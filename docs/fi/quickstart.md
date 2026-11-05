# Pika-aloitus: Kontroll ja Dataspatium yhdessä

Kaksikymmentä minuuttia tyhjästä siihen, että 3D-näkymässä luotu asia näkyy
palvelimen lokeissa. Sama sivu on Dataspatiumin repossa; ne pidetään
identtisinä. Tarvitset Dockerin (Desktop Windowsissa/macOS:ssä, Engine
Linuxissa), [uv](https://docs.astral.sh/uv/):n, Python 3:n paikallista
web-palvelinta varten sekä Microsoft Edgen, Google Chromen tai Firefoxin.

## 1. Käynnistä Kontroll

```sh
git clone https://github.com/marwiss/Kontroll.git
cd Kontroll
cp .env.example .env
```

Avaa `.env` ja aseta `OPENCDE_GRAPH_PASSWORD` mihin tahansa vähintään 16
merkin arvoon, `OPENCDE_DYNAMIC_CLIENT_REGISTRATION=true`, jotta Dataspatium
voi rekisteröityä itse, ja `OPENCDE_ALLOW_LOCALHOST_REDIRECTS=true`, jotta
osoitteesta `http://localhost` tarjoiltu sovellus saa kirjautua. Sitten:

```sh
docker compose -f compose.yaml -f compose.dev.yaml up -d --build
docker compose -f compose.yaml -f compose.dev.yaml exec api opencde seed
```

Jälkimmäinen komento luo demokäyttäjät ja -projektit ja tulostaa niiden
salasanat kerran; ota talteen käyttäjien `admin` ja `editor` salasanat.
Tarkista <http://localhost:8000/readyz> (vastaa `ready`) ja kirjaudu
osoitteessa <http://localhost:8000/signin> käyttäjänä `admin`: `/admin`
näyttää projektit *Building permit* ja *Demolition permit*.

Jos Compose pysähtyy ilmoitukseen `dependency failed to start: container
kontroll-graph-1 is unhealthy`, lue `docker compose -f compose.yaml -f
compose.dev.yaml logs graph`. Tavallinen syy on alle 16 merkin salasana, jonka
Neo4j hylkää (`A password must be at least 16 characters`); toinen on
aiemmasta asennuksesta jäänyt tietokannan taltio, jossa on eri salasana ja
jonka `docker compose -f compose.yaml -f compose.dev.yaml down -v` poistaa
tietoineen. Kaksi lähdekoodikopiota samalla koneella jakavat
Compose-projektinimen `kontroll`, joten toinen tarvitsee `.env`-tiedostoonsa
`COMPOSE_PROJECT_NAME=kontroll-2` ja eri `OPENCDE_DEV_*`-portit.

## 2. Käynnistä Dataspatium

1. Lataa `dataspatium-<version>.zip` kohdasta
   [uusin julkaisu](https://github.com/marwiss/Dataspatium/releases/latest)
   ja vertaa sen SHA-256-summaa julkaisutekstissä olevaan.
2. Pura ZIP omaan kansioonsa (ei ZIP-tiedoston sisällä).
3. Kaikkeen muuhun paitsi OpenCDE-kirjautumiseen riittää `index.html`-
   tiedoston kaksoisnapsautus. OpenCDE:tä varten kansio on tarjoiltava
   http:n yli, koska OAuth2-uudelleenohjaus tarvitsee http-osoitteen:

   ```sh
   cd dataspatium-<version>
   python -m http.server 8080
   ```

   ja avaa <http://localhost:8080/>. Sovellus rekisteröi itsensä palvelimelle
   julkiseksi asiakkaaksi redirect-URI:lla
   `http://localhost:8080/oauth-callback.html`. (Verkossa julkaistu sovellus
   osoitteessa <https://marwiss.github.io/Dataspatium/> toimii sen sijaan
   palvelinta vastaan, joka sallii tuon osoitteen.)

## 3. Yhdistä ne

Dataspatiumissa: tila *Inhämta* (Tuo) → painike *Lägg till källa* (Lisää
lähde) → *Typ av tjänst* (Palvelun tyyppi): *OpenCDE (BCF, Documents)* →
*Adress* (Osoite): `http://localhost:8000` → *Lägg till* (Lisää). Lähde
avautuu *Inhämta*-tilaan: paina *Logga in* (Kirjaudu) ja kirjaudu
ponnahdusikkunassa käyttäjänä `editor`, ja valitse sitten *Building permit*
luettelosta *Projekt*. Otsikon alla oleva rivi ("Servern: Kontroll OpenCDE
server 2.0.0. Tillägg: …") tulee palvelimen kyvykkyysasiakirjasta ja kertoo,
mitkä laajennukset ovat päällä.

## 4. Luo asia 3D-näkymästä

1. Hae esimerkkimalli. Seed on jo tallentanut tiedoston `three_walls_gtin.ifc`
   (kolme seinää GTIN-koodein 3, 2 ja 1) asiakirjaksi projektiin *Building
   permit*; lähteen näkymässä *Inhämta*-tilassa asiakirjaluettelossa on
   hakupainike jokaiselle asiakirjalle, ja asiakirjasta tulee
   mallidatamäärä. Jos haluat sen sijaan lähettää oman tiedoston, käytä tilaa
   *Dela* (Jaa) → välilehti *Till CDE* (CDE:hen): valitse lähde ja projekti,
   *Vad* (mitä: alkuperäinen tiedosto, vienti tai paketti), *Hur* (miten:
   Documents API tai BCF) ja *Skicka* (Lähetä); hae se sitten takaisin samalla
   tavalla.
2. Valitse malli tilassa *Bearbeta* (Käsittele); se avautuu automaattisesti
   3D:nä. Valitse seinä, avaa paneeli *Ärenden* (Asiat) ja paina *Nytt
   ärende* (Uusi asia): anna otsikko, säilytä tila ja rastita *Lägg till vyn
   som viewpoint* (Lisää näkymä viewpointina). Asia luodaan BCF API:n kautta
   viewpointilla, jonka komponentti osoittaa seinään.
3. Kirjoita kommentti samaan paneeliin ja lähetä se.

## 5. Katso se palvelimella

- `/admin/projects` → *Building permit* näyttää kaksi asiaa (seedatun ja
  omasi) sekä asiakirjan.
- `/admin/audit` luettelee kirjautumisen ja sovelluksen rekisteröinnin.
- Kun `.env`-tiedostossa on `OPENCDE_REQUEST_LOG_ENABLED=true` (ja palvelin
  on käynnistetty uudelleen), `/admin/requests` näyttää jokaisen sovelluksen
  tekemän kutsun samoilla `X-Request-ID`-arvoilla kuin kortti *Logg*
  OpenCDE-lähteen näkymän alareunassa *Inhämta*-tilassa, joten epäonnistunut
  kutsu löytyy molemmilta puolilta.
- Kun `OPENCDE_IFCGRAPH_ENABLED=true`, lähetetystä mallista tulee graafi;
  Neo4j Browser osoitteessa <http://localhost:7484> (`bolt://localhost:7697`,
  käyttäjä ja salasana `.env`-tiedostosta) näyttää seinän `IfcWall`-solmuna,
  joka on yhdistetty viewpointin komponenttiin `SAME_AS`-suhteella, ja
  Dataspatiumin graafinäkymä voi kysellä sitä Cypherillä.

## Seuraavaksi

- [docs/client-guide.md](../client-guide.md): rajapinnat, kyvykkyysasiakirja
  ja virhekoodit.
- [docs/acceptance.md](../acceptance.md): tarkistuslistat, joilla paria
  testataan, ja [docs/dataspatium-coordination.md](../dataspatium-coordination.md):
  mitä kaksi projektia sovittavat yhteen.
- [docs/deploy/](../deploy/), kun palvelimen on määrä palvella muita.
