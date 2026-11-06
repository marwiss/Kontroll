# Pika-aloitus: Kontroll ja Dataspatium yhdessä

Tyhjästä koneesta siihen, että olet kirjautunut Kontrolliin Dataspatiumista ja
3D-näkymässä luotu asia näkyy palvelimen lokeissa. Se vie noin kaksikymmentä minuuttia,
josta suurin osa kuluu ensimmäiseen koontiin. Seuraa vaiheita järjestyksessä ja käytä
osoitteita ja portteja juuri niin kuin ne on kirjoitettu: lähes kaikki ongelmat johtuvat
ohitetusta asetuksesta tai toisesta osoitteesta. [Vianmääritys](#vianmääritys) kertoo,
mitä tehdä, jos jokin menee vikaan. Sama sivu on Dataspatiumin repossa; ne pidetään
identtisinä.

## Mitä tarvitset

- Docker: Docker Desktop Windowsissa ja macOS:ssä, Docker Engine ja compose-lisäosa
  Linuxissa. Sen on oltava käynnissä: `docker version` vastaa sekä asiakkaan että
  palvelimen osalta.
- Git tai lähdekoodi-ZIP Kontrollin
  [uusimmasta julkaisusta](https://github.com/marwiss/Kontroll/releases/latest)
  alla olevan `git clone` -komennon sijaan.
- Python 3 pienenä paikallisena web-palvelimena.
- Microsoft Edge, Google Chrome tai Firefox.
- Portit 8000, 7484, 7697 ja 8080 vapaina koneella.

Jos olet kokeillut Kontrollia tällä koneella aiemmin, aloita kohdasta
[Aloita alusta](#aloita-alusta).

## 1. Käynnistä Kontroll

```sh
git clone https://github.com/marwiss/Kontroll.git
cd Kontroll
cp .env.example .env
```

Windowsin komentokehotteessa `cp`:n sijaan käytetään `copy`-komentoa.

Avaa `.env` tekstieditorissa. Alla olevat neljä riviä ovat jo tiedostossa: muuta ne
tällaisiksi ja tallenna. Valitse oma salasana, vähintään 16 merkkiä, vain kirjaimia ja
numeroita.

```ini
OPENCDE_GRAPH_PASSWORD=YourOwnPassword1234
OPENCDE_DYNAMIC_CLIENT_REGISTRATION=true
OPENCDE_REQUEST_LOG_ENABLED=true
OPENCDE_IFCGRAPH_ENABLED=true
```

| Rivi | Mitä se tekee | Ilman sitä |
|---|---|---|
| `OPENCDE_GRAPH_PASSWORD` | Graafitietokannan salasana | Alle 16 merkkiä: tietokanta ei käynnisty |
| `OPENCDE_DYNAMIC_CLIENT_REGISTRATION` | Antaa Dataspatiumin rekisteröityä itse palvelimelle | Vaihe 3 pysähtyy, ja sovellus pyytää asiakastunnusta |
| `OPENCDE_REQUEST_LOG_ENABLED` | Tallentaa sovelluksen kutsut | Vaiheen 5 pyyntöloki pysyy tyhjänä |
| `OPENCDE_IFCGRAPH_ENABLED` | Tekee ladatuista malleista graafin | Vaiheessa 5 ei ole graafia |

Asetukset on tarkoitettu Kontrollin kokeiluun omalla koneella, ei palvelimelle, jota
muut käyttävät.

Käynnistä palvelin ja lataa esittelytiedot:

```sh
docker compose -f compose.yaml -f compose.dev.yaml up -d --build --wait
docker compose -f compose.yaml -f compose.dev.yaml exec api opencde seed
```

Ensimmäinen komento vie ensimmäisellä kerralla muutaman minuutin ja palaa, kun palvelin
on käynnissä. Toinen luo esittelykäyttäjät ja -projektit ja tulostaa niiden salasanat
**kerran**: tallenna käyttäjien `admin` ja `inspection_manager` salasanat nyt. Älä
välitä riveistä, jotka alkavat sanalla `client`; Dataspatium rekisteröi oman asiakkaansa.

Tarkista, että se toimii: <http://127.0.0.1:8000/readyz> vastaa `"status":"ready"`.
Kirjaudu osoitteessa <http://127.0.0.1:8000/signin> käyttäjänä `admin` ja avaa
<http://127.0.0.1:8000/admin/projects>, jossa näkyvät *Building permit* ja
*Demolition permit*.

Kun muutat `.env`-tiedostoa myöhemmin, suorita `up`-komento uudelleen. `docker compose
restart` ei lue tiedostoa.

## 2. Käynnistä Dataspatium

1. Lataa `dataspatium-<version>.zip`
   [uusimmasta julkaisusta](https://github.com/marwiss/Dataspatium/releases/latest)
   ja vertaa sen SHA-256-summaa julkaisun tekstissä olevaan (`Get-FileHash`
   PowerShellissä, `shasum -a 256` macOS:ssä ja Linuxissa).
2. Pura ZIP-tiedosto omaan kansioon. Windows saattaa luoda kansion kansion sisään;
   ratkaisevaa on kansio, jossa `index.html` on suoraan.
3. Avaa pääte siinä kansiossa ja käynnistä web-palvelin porttiin 8080:

   ```sh
   python -m http.server 8080 --bind 127.0.0.1
   ```

   Komento voi olla `python3` macOS:ssä ja Linuxissa ja `py` Windowsissa. Pidä pääte auki,
   kun käytät sovellusta. Anna aina portti: ilman sitä Python ottaa portin 8000, joka on Kontrollin portti.
4. Avaa <http://127.0.0.1:8080/> juuri näin kirjoitettuna: palvelin palauttaa selaimen kirjautumisen jälkeen osoitteeseen `127.0.0.1`, ei osoitteeseen `localhost`. Älä kaksoisnapsauta tiedostoa `index.html`: kansiosta
   avattuna sovellus ei voi rekisteröidä itseään. Sovellus latautuu kerran uudelleen
   ensimmäisellä käynnistyskerralla.
5. Ensimmäinen käynnistys kysyy kieltä: valitse kieli ja paina *Jatka kielellä …*. Tämä
   sivu käyttää suomenkielisiä nimiä. Paneeli *Tervetuloa Dataspatiumiin* tarjoaa kurssia:
   paina *Ei nyt*.

## 3. Kirjaudu Kontrolliin Dataspatiumista

1. Valitse tila *Nouda*. Valitse vasemmasta sarakkeesta kohdasta *Lisää lähteitä*
   *OpenCDE*.
2. Kirjoita kohtaan *Osoite* `http://127.0.0.1:8000`. **Jätä *Asiakastunnus (client id)*
   ja salaisuus tyhjiksi**: sovellus rekisteröi itsensä, vaikka valintaikkunan teksti
   puhuu ylläpitäjältä saatavasta asiakastunnuksesta. Paina *Lisää lähde*.
3. Sovellus kysyy *Sallitaanko internetyhteys?* enintään kolme kertaa, kerran kutakin
   tarkoitusta varten. Tässä se koskee vain omaa palvelintasi: paina joka kerta *Salli*.
4. Lähde avautuu ja näkyy kohdassa *Lisätyt lähteet*. Rivi "Palvelin: Kontroll OpenCDE
   server <version>. Lisäykset: …" tulee palvelimen kyvykkyysasiakirjasta ja kertoo,
   mitkä lisäykset ovat päällä. Merkistä *Vaatii avaimen* ei tarvitse välittää: se, mitä
   tarvitaan, on kirjautuminen.
5. Paina *Kirjaudu*. Ponnahdusikkuna avautuu palvelimen kirjautumissivulle. Jos selain
   estää sen, salli ponnahdusikkunat osoitteelle `http://127.0.0.1:8080` ja paina
   uudelleen.
6. Kirjaudu käyttäjänä `inspection_manager` vaiheen 1 salasanalla ja paina *Salli ja
   kirjaudu*. Älä käytä käyttäjää `admin`, joka ei kuulu mihinkään projektiin. Ikkuna
   sulkeutuu itsestään, ja lähteessä lukee *Kirjautunut: Certified inspection manager*.
7. *Building permit* on jo valittuna luettelossa *Projekti*.

Pysyt kirjautuneena, kunnes sivu ladataan uudelleen; paina silloin *Kirjaudu* uudelleen.
Lähde säilyy.

## 4. Luo asia 3D-näkymästä

1. Etsi lähteen näkymästä *Projektin tiedostot* ja paina *Näytä tiedostot*. `opencde seed`
   tallensi sinne tiedoston `three_walls_gtin.ifc` (kolme seinää, GTIN 3, 2 ja 1). Paina
   *Hae*: tiedostosta tulee mallitietojoukko.
2. Valitse tila *Muokkaa*; malli avautuu 3D:nä. Merkitse seinä napsauttamalla sitä.
3. Paina 3D-näkymän yläpuolella *Asiat* ja sitten oikeassa sarakkeessa *Uusi asia*.
   Kirjoita jotain kohtaan *Otsikko* ja paina *Luo asia*. Asia luodaan BCF API:n kautta,
   ja näkymä ja merkitty seinä tulevat mukaan viewpointina.
4. Kirjoita asian alla jotain kohtaan *Kirjoita kommentti* ja paina *Lähetä*.

## 5. Katso se palvelimella

Käyttäjänä `admin` kirjautuneena avaa <http://127.0.0.1:8000/admin>:

- *Projektit* näyttää projektin *Building permit*, jossa on kaksi asiaa (`opencde seed`
  -komennon luoma ja sinun) ja yksi asiakirja.
- *Tapahtumaloki* näyttää kirjautumisen ja sovelluksen rekisteröinnin.
- *Pyyntöloki* näyttää jokaisen sovelluksen tekemän kutsun samoilla
  `X-Request-ID`-arvoilla kuin kortti *Loki* lähteen näkymän alareunassa tilassa *Nouda*,
  joten epäonnistunut kutsu löytyy molemmilta puolilta.

Paina sitten *Kirjaudu ulos* palvelimen sivun yläreunassa, koska alla oleva lataus tehdään
toisena käyttäjänä.

Graafi rakennetaan ladatuista malleista, ei `opencde seed` -komennon luomasta. Nähdäksesi
sen lähetä malli palvelimelle:

1. Valitse Dataspatiumissa tila *Jaa* ja välilehti *CDE:hen*. Valitse kohdassa *Mitä*
   *Alkuperäinen tiedosto* ja paina *Lähetä*.
2. *Tarkistus ennen jakamista* näyttää, mitä tulee mukaan: paina *Jatka*.
3. Palvelimen lataussivu avautuu ponnahdusikkunassa. Kirjaudu käyttäjänä
   `inspection_manager` ja paina *Tallenna ja jatka*. Ikkuna sulkeutuu itsestään.

Muutaman sekunnin kuluttua Neo4j Browser osoitteessa <http://127.0.0.1:7484> (yhdistä
osoitteeseen `bolt://127.0.0.1:7697` käyttäjänä `neo4j` ja tiedoston `.env` salasanalla)
vastaa tähän kyselyyn seinällä, joka on linkitetty viewpointin komponenttiin:

```cypher
MATCH (c:Component)-[:SAME_AS]->(w:IfcWall) RETURN c, w
```

## Vianmääritys

Jokainen rivi lainaa näyttöä sellaisena kuin se on suomenkielisillä nimillä.

| Mitä näet | Miksi | Mitä teet |
|---|---|---|
| `Cannot connect to the Docker daemon`, `error during connect` tai `docker: command not found` | Docker ei ole käynnissä | Käynnistä Docker Desktop, odota, kunnes se kertoo olevansa käynnissä, ja suorita komento uudelleen |
| `dependency failed to start: container kontroll-graph-1 is unhealthy` | Alle 16 merkin salasana, jonka Neo4j hylkää (`docker compose -f compose.yaml -f compose.dev.yaml logs graph` kertoo `A password must be at least 16 characters`), tai aiemmasta asennuksesta jäänyt tietokantaltaltio, jolla on toinen salasana | Korjaa salasana ja suorita `up`-komento uudelleen. Vanhasta taltiosta: katso [Aloita alusta](#aloita-alusta) |
| `port is already allocated`, `Ports are not available` tai `address already in use` | Toinen ohjelma varaa portin 8000, 7484 tai 7697, ehkä aiempi Kontroll (`docker ps` näyttää sen) | Pysäytä se tai anna muut portit asetuksilla `OPENCDE_DEV_PORT`, `OPENCDE_DEV_NEO4J_HTTP_PORT` ja `OPENCDE_DEV_NEO4J_BOLT_PORT` tiedostossa `.env` ja käytä omaa porttiasi 8000:n sijaan siitä lähtien |
| Toisen kansion kontit korvautuvat | Kaksi kopiota samalla koneella jakavat Compose-projektin nimen `kontroll` | Anna toiselle `COMPOSE_PROJECT_NAME=kontroll-2` ja muut `OPENCDE_DEV_*`-portit sen tiedostossa `.env` |
| `the database is not empty` | `opencde seed` on jo suoritettu, ja se tulosti salasanat silloin | Hanki uusi salasana komennolla `docker compose -f compose.yaml -f compose.dev.yaml exec api opencde user set-password inspection_manager` tai [aloita alusta](#aloita-alusta) |
| `python`-komentoa ei löydy, tai Microsoft Store avautuu | Komennolla on tällä koneella toinen nimi | Käytä komentoa `py` tai `python3` |
| Tiedostoluettelo sovelluksen sijaan | Web-palvelin toimii ulommassa kansiossa | Pysäytä se näppäimillä Ctrl+C ja käynnistä se kansiossa, jossa `index.html` on |
| Sovelluksen vanha versio tai jotain aivan muuta | Jokin muu vastaa portissa 8080; Windowsissa toinen web-palvelin voi käynnistyä samaan porttiin ilman virhettä | Käytä toista porttia, `python -m http.server 8090 --bind 127.0.0.1`, ja avaa `http://127.0.0.1:8090/` |
| *Sovellus voi rekisteröityä palvelimelle itse vain, kun se toimii web-palvelimelta …* | Sovellus avattiin kansiosta | Avaa `http://127.0.0.1:8080/` |
| *Palveluun 127.0.0.1:8000 ei saatu yhteyttä …* | Kontroll ei ole käynnissä, tai osoite on kirjoitettu väärin | Osoitteen <http://127.0.0.1:8000/readyz> on vastattava. Osoite on `http://127.0.0.1:8000` ilman mitään perässä |
| *Palvelin ei salli sovelluksen rekisteröidä itseään …* | `OPENCDE_DYNAMIC_CLIENT_REGISTRATION` ei ole `true` | Muuta tiedostoa `.env`, suorita `up`-komento uudelleen ja paina *Lisää lähde* uudelleen |
| *Rekisteröinti epäonnistui:* … `Redirect URIs to http://localhost are not allowed here` | Sovellus avattiin osoitteessa `localhost`, jota palvelin ei hyväksy paluureitiksi | Avaa `http://127.0.0.1:8080/` ja lisää lähde siellä |
| *Rekisteröinti epäonnistui:* … `rate_limited` | Yli 60 rekisteröintiä tunnin sisällä; jokainen *Lisää lähde* tyhjällä kentällä *Asiakastunnus (client id)* on yksi | `docker compose -f compose.yaml -f compose.dev.yaml restart api` nollaa laskurin |
| *Internetyhteyttä tarkoitukseen … ei ole sallittu.* | Painettiin *Kiellä* | Salli se kohdassa *Hallitse*, *Työtila*, *Internetyhteys* ja yritä uudelleen |
| *Selain esti kirjautumisikkunan …* | Selaimen ponnahdusikkunoiden esto | Salli ponnahdusikkunat osoitteelle `http://127.0.0.1:8080` ja paina *Kirjaudu* uudelleen |
| Ponnahdusikkunassa: *Ei voi jatkaa* ja *Tuntematon asiakas.* | Palvelin on unohtanut sovelluksen rekisteröinnin, yleensä komennon `down -v` jälkeen | Sulje ikkuna ja lataa sovellus uudelleen, koska *Kirjaudu* muuten pyörii viisi minuuttia. Poista lähde sen vieressä olevalla ristillä kohdassa *Lisätyt lähteet* ja lisää se uudelleen |
| Ponnahdusikkunassa: *Ei voi jatkaa* ja *Redirect-URI:a ei ole rekisteröity tälle asiakkaalle.* | Kenttä *Asiakastunnus (client id)* täytettiin, esimerkiksi komennon `opencde seed` tulosteesta | Sulje ikkuna ja lataa sovellus uudelleen. Poista lähde sen vieressä olevalla ristillä kohdassa *Lisätyt lähteet* ja lisää se uudelleen kenttä tyhjänä |
| Ponnahdusikkunassa: *Käyttäjätunnus tai salasana ei ole oikein.* | Jokaisella käyttäjällä on oma salasanansa komennosta `opencde seed` | Käytä oikeaa tai hanki uusi kuten edellä |
| *Liian monta epäonnistunutta yritystä tällä käyttäjätunnuksella …* | Viisi väärää salasanaa peräkkäin saa palvelimen odottamaan, enintään 15 minuuttia | Odota ilmoitettu aika ja käytä komennon `opencde seed` antamaa salasanaa |
| *Lomake on vanhentunut. Yritä uudelleen.* sivulla `/signin`, tai ponnahdusikkunassa *Ei voi jatkaa* ja *Kirjautumislomake on vanhentunut tai sitä on muokattu. Aloita alusta.*, vaikka avasit sivun juuri. `docker compose -f compose.yaml -f compose.dev.yaml logs api` näyttää `GET /sw.js` ja 404 | Selaimessasi on service worker toisesta web-sovelluksesta, joka on joskus toiminut osoitteessa `http://127.0.0.1:8000`, esimerkiksi käynnistetty komennolla `python -m http.server` ilman porttia. Se vastaa Kontrollin sivujen vanhoilla kopioilla | Lataa sivu uudelleen ja yritä vielä kerran, koska Kontrollin sivut poistavat tällaisen workerin itse. Jos viesti ei katoa, poista se käsin: `about:debugging#/runtime/this-firefox` Firefoxissa, `edge://serviceworker-internals` Edgessä, `chrome://serviceworker-internals` Chromessa; etsi `127.0.0.1:8000` ja valitse *Unregister*. Jokaisella selaimella on omansa, myös editoriin sisäänrakennetulla. Yksityisessä ikkunassa sitä ei ole, mikä näyttää nopeasti, onko tämä syy. Pidä muut sovellukset poissa portista 8000 |
| *Et ole jäsenenä missään projektissa palvelimella.* | Kirjauduit käyttäjänä `admin`, joka ei kuulu mihinkään projektiin | Paina *Kirjaudu ulos* ja sitten *Kirjaudu* käyttäjänä `inspection_manager` |
| *Kirjaudu* pyörii pyörimistään | Ikkuna suljettiin ennen kuin kirjautuminen oli valmis | Lataa sivu uudelleen |
| Ikkunassa lukee *Kopiera adressen … / Copy the address …* | Se ei saanut yhteyttä sovelluksen ikkunaan, joka ehkä suljettiin tai ladattiin uudelleen sillä välin | Sulje ikkuna ja paina *Kirjaudu* uudelleen |
| *Toinen tili* lataussivulla | Selain on kirjautunut palvelimelle käyttäjänä `admin`, joka ei aloittanut latausta | Paina sillä sivulla *Kirjaudu ulos* ja kirjaudu käyttäjänä `inspection_manager`; lataus jatkuu sitten samassa ikkunassa |

## Aloita alusta

Kansiossa, josta käynnistit (tai missä tahansa, kun korvaat kaksi `-f`-valitsinta
valitsimella `-p kontroll`):

```sh
docker compose -f compose.yaml -f compose.dev.yaml down -v
```

Se poistaa tietokannan ja esittelyn tiedostot. Suorita sitten vaiheen 1 `up`- ja
`seed`-komennot uudelleen, jolloin saat uudet salasanat. Poista Dataspatiumissa lähde sen
vieressä olevalla ristillä kohdassa *Lisätyt lähteet* ja lisää se uudelleen, koska palvelin
on unohtanut sovelluksen rekisteröinnin.

Jos haluat pysäyttää poistamatta mitään, jätä `-v` pois. Web-palvelimen pysäytät
näppäimillä Ctrl+C.

## Seuraavaksi

- [docs/client-guide.md](client-guide.md): rajapinnat, kyvykkyysasiakirja
  ja virhekoodit.
- [docs/acceptance.md](../acceptance.md): tarkistuslistat, joilla paria
  testataan, ja [docs/dataspatium-coordination.md](../dataspatium-coordination.md):
  mitä kaksi projektia sovittavat yhteen.
- [docs/deploy/](deploy/), kun palvelimen on määrä palvella muita.
