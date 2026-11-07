# Sanasto

Tämän dokumentaation käyttämät sanat ja mitä ne tässä tarkoittavat. Asia, kommentti,
näkymä ja projekti ovat samat sanat kuin Dataspatiumissa.

## Standardit

| Sana | Mitä se tässä tarkoittaa |
|---|---|
| OpenCDE | buildingSMARTin API-rajapinnat yhteiselle tietoympäristölle: Foundation, BCF ja Documents |
| CDE | Common data environment, yhteinen tietoympäristö: projektin tietojen jaettu paikka |
| Foundation API | OpenCDE:n osa, joka kertoo, mitä API-rajapintoja palvelin tarjoaa, miten kirjaudutaan ja kuka olet |
| BCF | BIM Collaboration Format, rakennusmallia koskeville asioille. BCF API 3.0 ja 2.1 ovat sen verkkorajapinnat |
| Documents API | OpenCDE:n osa, joka lataa ja valitsee asiakirjoja selaimen sivuilla |
| IFC | Industry Foundation Classes, rakennusmallien avoin tiedostomuoto |

## Projektissa

| Sana | Mitä se tässä tarkoittaa |
|---|---|
| Projekti | Jaettu tila: jäsenet, asiat ja asiakirjat |
| Jäsen, rooli | Henkilö projektissa, roolina viewer, contributor, editor tai manager. Rooli ratkaisee, mitä hän saa tehdä |
| Ylläpitäjä | Käyttäjä, joka hallitsee käyttäjiä, projekteja ja asiakkaita. Se ei ole projektin rooli eikä anna pääsyä projektin sisältöön |
| Laajennukset (extensions) | Arvot, jotka projekti sallii tyypille, tilalle, prioriteetille, tunnisteille ja niin edelleen |
| Asia (topic) | Jotain tehtävää, tarkistettavaa tai vastattavaa. BCF:n sana on topic |
| Kommentti | Huomautus asiaan, ja se voi osoittaa näkymään |
| Näkymä (viewpoint) | Mallin tallennettu näkymä: kamera, komponentit ja kuva |
| Komponentti | Rakennuksen osa, jonka näkymä nimeää sen `GlobalId`:llä |
| Tilannekuva (snapshot) | Näkymän kuva |
| Tapahtuma | Merkintä asian tai kommentin historiassa |
| Asiakirja, versio | Tiedosto, jolla on otsikko; sen uusi lataus on uusi versio |

## Kirjautuminen

| Sana | Mitä se tässä tarkoittaa |
|---|---|
| Asiakas | Ohjelma, joka toimii käyttäjän puolesta ja on rekisteröity palvelimelle |
| Julkinen asiakas | Asiakas, joka ei voi pitää salaisuutta, kuten selain- tai työpöytäsovellus |
| Luottamuksellinen asiakas | Omalla palvelimellaan oleva asiakas, joka voi pitää salaisuuden |
| Itserekisteröinti | Asiakas rekisteröi itsensä, oletuksena pois päältä |
| Redirect-URI | Osoite, johon palvelin lähettää selaimen takaisin kirjautumisen jälkeen |
| PKCE | Kertakäyttöinen todiste siitä, että koodin vaihtaja on sama, joka sitä pyysi |
| Access-token | Lyhytikäinen todiste, joka lähetetään jokaisen API-pyynnön mukana |
| Refresh-token | Pidempi todiste, joka antaa uuden access-tokenin ja kelpaa kerran |
| Scope | Mihin tokenia saa käyttää: `profile`, `bcf`, `documents` tai `admin` |

## Malli graafina

| Sana | Mitä se tässä tarkoittaa |
|---|---|
| IFC-graafi | Ladattu malli solmuina ja suhteina tietokannassa, valinnainen |
| IFC-LPG | Moduuli, joka muuttaa IFC-tiedostot IFC-graafiksi, ennen versiota 2.0.2 nimeltään IFC-graph |
| `GlobalId` | Elementin pysyvä tunnus IFC-tiedostossa |
| `SAME_AS` | Suhde näkymän komponentista mallin elementtiin |
| GTIN | Global Trade Item Number, tuotteen numero; tässä luettu ominaisuusjoukosta `Reuse` |
| Cypher | Graafitietokannan kyselykieli |
| Bolt | Tietokannan oma yhteys, valinnainen niille, jotka kysyvät graafilta suoraan |

## Palvelimen ylläpito

| Sana | Mitä se tässä tarkoittaa |
|---|---|
| Pino | Kontit, jotka muodostavat käynnissä olevan palvelimen: API, tietokanta ja tuotannossa proxy ja varmuuskopiointi |
| Seed | `opencde seed`, joka lataa esittelytiedot tyhjään tietokantaan |
| Capabilities | `/.well-known/kontroll`, joka kertoo, mitä tämä palvelin on ottanut käyttöön |
| Pyyntöloki | Valinnainen luettelo pyynnöistä, joihin palvelin on vastannut |
| Tarkastusloki | Luettelo siitä, kuka on kirjautunut ja muuttanut mitä |
