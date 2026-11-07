# IFC-graafi

Valinnainen IFC-graafimoduuli muuttaa lähetetyn IFC-mallin graafidataksi,
jotta BCF-viewpointin komponentit voidaan yhdistää rakennusosiin, joihin ne
viittaavat, ja jotta mallista voidaan kysyä Cypherillä asioiden ja
asiakirjojen rinnalla.

Kytke se päälle asetuksella `OPENCDE_IFCGRAPH_ENABLED=true` ja asenna
`ifcgraph`-lisäosa (`uv sync --extra ifcgraph`). Docker-kuva sisältää
lisäosan oletuksena (`ARG OPENCDE_EXTRAS` Dockerfilessa), mikä yli
kaksinkertaistaa sen koon (noin 680 MB vastaan 300 MB); rakenna
`--build-arg OPENCDE_EXTRAS=` saadaksesi kevyemmän kuvan ilman
IfcOpenShelliä, kun moduuli pysyy pois päältä.

## Mitä lähetyksessä tapahtuu

1. Documents API -lähetys valmistuu (tai tiedosto lähetetään valintasivulta,
   tai BCF-projektiasiakirja postataan) nimellä, jonka pääte on `.ifc` tai
   `.ifczip`.
2. Palvelin luo projektiin liitetyn `IfcModel`-solmun (tila `queued`) ja
   käynnistää muunnoksen taustalla, yhden kerrallaan.
3. Erillinen työprosessi (`python -m opencde.ifcgraph.worker`) lukee
   tiedoston. Se toimii aikarajalla
   (`OPENCDE_IFCGRAPH_TIMEOUT_SECONDS`, 15 minuuttia), osoiteavaruusrajalla
   POSIX-järjestelmissä (`OPENCDE_IFCGRAPH_MEMORY_MB`, 4 GiB) ja entiteettien
   ylärajalla (`OPENCDE_IFCGRAPH_MAX_ENTITIES`). Kaatuminen tai jumiutuminen
   tappaa työprosessin, ei palvelinta. `.ifczip` puretaan lähetyksen
   kokorajan puitteissa.
4. Tietueet tuodaan erissä `UNWIND … CREATE` -lauseilla (siirrettävä Cypher,
   ei APOC:ia). `IfcModel` päätyy tilaan `done` lukumäärineen ja
   `IfcProject`-guidin kanssa, tai tilaan `failed` virheen kanssa.
5. Muunnos, jonka pysäytetty palvelin jätti kesken, alkaa alusta: jonossa oleva heti, kun palvelin on taas
   käynnissä, ja käynnissä ollut, kun kaksinkertainen aikaraja on kulunut, koska se voi olla käynnissä toisessa palvelinprosessissa.

`opencde seed` muuntaa esimerkkimallin samalla tavalla, kun moduuli on käytössä.

## Lähetysten tarkistus IFC-skeemaa vasten

Jokainen dokumenttiversiona lähetetty `.ifc`- tai `.ifczip`-tiedosto tarkistetaan
myös IFC-skeemaa vasten samalla validaattorilla, joka tarkistaa kirjoitetun
tiedoston ([Mallin kirjoittaminen takaisin](#mallin-kirjoittaminen-takaisin)):
attribuuttien tyyppi ja määrä, luetellut arvot, käänteiset attribuutit, GlobalId
ja EXPRESS-skeeman säännöt. Tarkistus ajetaan taustalla ennen muunnosta
erillisessä työprosessissa samoin rajoin. Se ei koskaan estä lähetystä: tiedosto
tallennetaan sellaisenaan, löysi tarkistus mitä tahansa. BCF-projektidokumenttia
ei tarkisteta, koska sillä ei ole metatietoja.
`OPENCDE_IFCGRAPH_VALIDATE_UPLOADS=false` poistaa tarkistuksen käytöstä.

Tulos on version metatiedoissa, joita mikä tahansa Documents API -asiakas voi lukea:

| Kohta | Tyyppi | Arvo |
|---|---|---|
| `ifc_validation_status` | `string` | `pending`, kunnes tiedosto on tarkistettu, sitten `passed`, `issues` tai `unknown`, kun sitä ei voitu tarkistaa |
| `ifc_validation_issues` | `integer32` | Kuinka monta huomautusta tiedostossa on |
| `ifc_validation_checked_at` | `date-time` | Milloin se tarkistettiin |
| `ifc_validation_ruleset` | `string` | Millä se tarkistettiin |
| `ifc_validation_report` | `url` | Missä raportti on |

Raportti on Documents API:n laajennus. Jokainen projektin jäsen saa sen samalla
Bearer-tunnisteella:

```http
GET /documents/1.0/documents/{document_id}/versions/{version_index}/ifc-validation
```

```json
{
  "status": "issues",
  "checked_at": "2026-11-07T10:05:25.123Z",
  "ruleset": "IfcOpenShell 0.9.0.post1: schema and EXPRESS rules",
  "issue_count": 1,
  "truncated": false,
  "issues": [
    {
      "kind": "schema",
      "severity": "error",
      "message": "On instance:\n    #373=IfcWallStandardCase('1Xezbq735AdBO_4DerG66G',...)\n...\nRule IfcRoot.UR1:\n    The attribute GlobalId should be unique\n...",
      "step_id": 373,
      "global_id": "1Xezbq735AdBO_4DerG66G"
    }
  ]
}
```

Siinä luetellaan enintään 10 000 huomautusta, kukin instansseineen ja
juurioliolle myös GlobalId-tunnisteineen, jotta mallinäkymä löytää elementin.
`kind` kertoo, mikä huomautuksen löysi: `schema`, `entity_rule`,
`simpletype_rule` tai `global_rule`. Viesti voi lainata tiedoston riviä, ja se
katkaistaan 1 000 merkin kohdalta. Version sivu selaimessa näyttää ensimmäiset 100
huomautusta ja tarjoaa koko raportin tiedostona.

Monet tiedostot rikkovat jo jotakin sääntöä tullessaan ohjelmastaan: 12
esimerkkitiedostoa 26:sta tekee niin, yksi Teklasta 5 711 huomautuksella.
Esimerkkitiedoston ja sen kirjoitetun kopion tarkistus kesti yhteensä 3–66
sekuntia. buildingSMARTin `ifc-gherkin-rules`-sääntöjen toteuttajasopimuksia ei
tarkisteta ([ADR 0011](../adr/0011-a-file-written-from-the-graph-is-validated.md)).

## Graafi

Jokaisesta entiteetistä tulee `IfcEntity`-solmu, joka kantaa luokkaansa ja
kaikkia ylätyyppejään nimiöinä, esimerkiksi `IfcEntity:IfcWallStandardCase:IfcWall:
IfcBuildingElement:IfcElement:IfcProduct:IfcObject:IfcObjectDefinition:IfcRoot`.

| Ominaisuus | Merkitys |
|---|---|
| `id` | `<mallin tunnus>:<STEP-tunnus>`, yksilöllinen |
| `model_id`, `step_id` | malli ja tiedoston `#123`-numero |
| `ifc_class` | konkreettinen luokka |
| `GlobalId`, `Name`, `Description`, `Tag`, … | entiteetin jokainen literaaliattribuutti IFC-nimellään |

Toisiin entiteetteihin viittaavista attribuuteista tulee attribuutin mukaan
nimettyjä suhteita, jotka kirjoitetaan kuten jokainen graafin suhdetyyppi
isoin kirjaimin ja alaviivoin sanarajoilla:
`(:IfcRelDefinesByProperties)-[:RELATING_PROPERTY_DEFINITION]->(:IfcPropertySet)-[:HAS_PROPERTIES]->(:IfcPropertySingleValue)`.
Käänteisistä attribuuteista tulee myös suhteita, joten molemmat suunnat
luetaan luontevasti: `(:IfcWall)-[:IS_DEFINED_BY]->(:IfcRelDefinesByProperties)`.
Select-arvot puretaan (`IfcLabel('3')` muuttuu `"3"`:ksi).

Ei solmuja oletuksena (`OPENCDE_IFCGRAPH_INCLUDE_GEOMETRY=false`):
esitysalkiot, esitykset, profiilit, sijoitukset ja tyylit; ne ovat suurin osa
mallista ja harvoin sitä, mitä CDE-kysely tarvitsee, ja ne säilyvät graafissa
tekstinä, kuten kohdassa Mallin kirjoittaminen takaisin. `IfcOwnerHistory` on
solmu vain `IfcProject`-entiteetille.

## Mistä menetelmä on peräisin

Muunnos noudattaa Zhun, Wun ja Lein IFC-Graph-menetelmää: yksi solmu ilmentymää
kohden, luokkahierarkia nimiöinä, literaaliattribuutit ominaisuuksina ja toisiin
ilmentymiin viittaavat attribuutit, käänteiset attribuutit mukaan lukien,
attribuutin mukaan nimettyinä suhteina. Vuoden 2023 prototyyppi käytti artikkelin
koodia. Tämän palvelimen muunnos on kirjoitettu uudelleen.

Junxiang Zhu, Peng Wu ja Xiang Lei: "IFC-graph for facilitating building
information access and query". *Automation in Construction* 148 (2023), 104778.
[doi:10.1016/j.autcon.2023.104778](https://doi.org/10.1016/j.autcon.2023.104778),
avoimesti saatavilla CC BY 4.0 -lisenssillä.

Se eroaa artikkelista seuraavasti:

- Geometriasta ei tule solmuja, ellei sitä pyydetä. Artikkeli muuntaa kaiken ja
  mainitsee graafin koon rajoituksena.
- Tietueet kirjoitetaan erissä `CREATE`-komennolla erillisestä prosessista.
  Artikkeli yhdistää jokaisen solmun ja suhteen, mikä etsii graafista
  kaksoiskappaleita ja hidastuu graafin kasvaessa.
- Select-arvoista tulee solmunsa ominaisuuksia. Artikkeli antaa niille omat
  solmut, joilla on luotu tunniste.
- Useat mallit jakavat yhden tietokannan ja erotetaan toisistaan `model_id`:n
  avulla. Artikkelissa on yksi malli tietokantaa kohden.
- Suhdetyypit kirjoitetaan isoin kirjaimin, ja `SAME_AS` sekä GTIN-kopio on
  lisätty tässä.

Artikkeli huomauttaa, että sen graafi kadottaa luetteloiden järjestyksen, koska
suhde ei kerro, missä kohdassa luetteloa sen kohde oli. Tässä sen kertoo `position`.

## Mallin kirjoittaminen takaisin

Graafi sisältää koko mallin, ja tiedosto voidaan kirjoittaa siitä takaisin: samat
instanssit samoilla tunnuksilla ja samat arvot samassa järjestyksessä, siis myös sama
sijaintitieto.

```sh
uv run opencde ifcgraph export <mallin tunnus> model.ifc            # kirjoita tiedosto ja validoi se
uv run opencde ifcgraph export <mallin tunnus> model.ifc --verify   # ja vertaa sitä lähetettyyn
```

Solmut ovat ne, joita kyselyt tarvitsevat. Se, minkä ne jättävät pois, kirjoitetaan
STEP-muotoon ja pakataan tekstiksi `StepBlock`-solmuihin, jotka riippuvat
`IfcModel`-solmussa: se on graafissa, mutta Cypherin ulottumattomissa, eikä sitä voi
muuttaa siellä. Se ei voi olla tuotteiden ominaisuuksia, koska suuri osa siitä on
tuotteiden yhteistä. Asetuksella `OPENCDE_IFCGRAPH_INCLUDE_GEOMETRY=true` jokaisesta
instanssista tulee sen sijaan solmu, moninkertaisella koolla ja tuontiajalla; kyselyt
kestivät suunnilleen yhtä kauan [mittauksissa](../adr/0010-a-lossless-graph-reads-and-writes-step-itself.md).

| Tiedostossa | Graafissa |
|---|---|
| Viittaus | Suhde, jolla on `position`, luetteloiden luettelossa `[rivi, sarake]`; käänteisillä suhteilla sitä ei ole |
| Viittaus lohkossa olevaan instanssiin | Sen tunnus, kuten `Representation__step: 1234` |
| Tyypitetty arvo, `IFCLABEL('3')` | `NominalValue: "3"` ja sen vieressä `NominalValue__type: "IFCLABEL"` |
| Lukujen luetteloiden luettelo | JSON-tekstiä |
| Se, millä ei ole yksinkertaista muotoa, kuten tyypitettyjen arvojen luettelo | Merkittyä JSONia, tyyppinä `$json` |
| Otsake | `ifc_header` solmussa `IfcModel` |
| Lohkossa oleva instanssi | Tekstiä `StepBlock`-solmussa |

Tiedosto kirjoitetaan siitä, mitä graafi sisältää, eikä sitä kopioida, joten graafissa
muutettu ominaisuus tai suhde näkyy siinä. Graafitietokannassa ei ole skeemaa, johon
muutosta voisi verrata, joten tiedosto validoidaan IFC-standardia vasten IfcOpenShellin
validaattorilla: attribuuttien tyyppi ja määrä, luetellut arvot, käänteiset attribuutit,
GlobalId ja EXPRESS-skeeman säännöt. Käytössä olevat tiedostot rikkovat usein jo jotakin
sääntöä, joten merkitystä on huomautuksella, jota lähetetyssä tiedostossa ei ole. Komento
luettelee sen silloin ja päättyy virheeseen. `--no-validate` jättää tämän pois. Vienti
keskeytyy myös, jos lohko puuttuu.

Projektin jäsenet saavat tiedostot Documents API:n kautta, eikä palvelimelta ole muuta
tietä ulos. Kirjoitettu tiedosto, jonka on määrä korvata malli, lähetetään asiakirjansa
uutena versiona, jolloin se myös muunnetaan.

Tätä muotoa ei lueta IfcOpenShellillä, josta tässä otetaan vain skeema. IfcOpenShell
muuttaa joitakin arvoja lukiessaan (`.NULLENUM.` muuttuu `$`:ksi ja `($,$)` `()`:ksi), ja
Teklan ja Archicadin tiedostoissa niitä on. Siksi työprosessi lukee tiedoston itse ja
hylkää sen, mitä se ei osaa lukea. [ADR 0010](../adr/0010-a-lossless-graph-reads-and-writes-step-itself.md) kertoo miksi ja
[ADR 0011](../adr/0011-a-file-written-from-the-graph-is-validated.md) miten tiedosto validoidaan.

`--verify` kysyy, sisältävätkö kaksi tiedostoa saman mallin määritelmän
[ADR 0009](../adr/0009-what-makes-two-ifc-files-the-same-model.md) mukaan: yksi yhteen, arvo arvolta ja ilman toleranssia, sijaintitieto
raportissa nimettynä. Valinnalla `--geometry` myös jokaisen tuotteen verkko rakennetaan,
ja niitä verrataan bitti bitiltä. Mitkä tahansa kaksi tiedostoa voi verrata komennolla
`python -m opencde.ifcgraph.equivalence first.ifc second.ifc`.

Asetuksella `OPENCDE_IFCGRAPH_LOSSLESS=false` malli muunnetaan kuten ennen versiota
3.0.0: se luetaan IfcOpenShellillä, ja se, mikä ei ole solmuja, jätetään kokonaan pois.
Tällaista mallia, kuten aiemman version muuntamaakaan, ei voi kirjoittaa takaisin.

## Ylläpito

Jokainen IFC-tiedoston lähetys lisää `IfcModel`-solmun entiteetteineen, joten
uusia versioita vastaanottava projekti kerää graafeja, joita kukaan ei
kysele. Komentorivi luettelee ja karsii ne; asiakirjat ja niiden tiedostot
säilyvät aina:

```sh
uv run opencde ifcgraph list --project <projektin tunnus>
uv run opencde ifcgraph prune                   # epäonnistuneet mallit sekä valmiit mallit, jotka saman asiakirjan
                                                # uudempi valmis versio on korvannut
uv run opencde ifcgraph prune --project <id> --all   # yhden projektin jokainen malli (esimerkiksi testipino)
```

Jonossa olevia ja käynnissä olevia malleja ei karsita koskaan. Kyselyjen,
jotka haluavat yhden graafin asiakirjaa kohti, tulee itse valita uusin valmis
malli, koska vanhemmat versiot säilyvät karsintaan asti:

```cypher
MATCH (:Project {project_id: $project})-[:HAS_MODEL]->(m:IfcModel {state: 'done'})
WITH coalesce(m.document_id, m.bcf_document_guid) AS doc, m
ORDER BY m.version_index DESC, m.done_at DESC
WITH doc, collect(m)[0] AS latest
MATCH (e:IfcProduct {model_id: latest.id})
RETURN latest.file_name AS model, count(e) AS products
```

## BCF-komponenttien linkitys

Kun viewpoint luodaan komponenttien kanssa, jokainen komponentti, jonka
`ifc_guid` vastaa jonkin projektin tuodun mallin rakennusosan
`GlobalId`-arvoa, saa `SAME_AS`-suhteen siihen. Sama linkitys ajetaan
projektin jokaiselle olemassa olevalle komponentille, kun mallin tuonti
valmistuu, joten myös ennen mallin lähettämistä tai sen muuntamisen aikana
luodut viewpointit linkitetään. Jos rakennusosa kantaa määritettyä
ominaisuutta (`OPENCDE_IFCGRAPH_GTIN_PROPERTY_SET=Reuse`,
`OPENCDE_IFCGRAPH_GTIN_PROPERTY=GTIN`), sen arvo kopioidaan komponenttiin
`gtin`-kenttänä. Tämä on vuoden 2023 tutkimusraportin käyttötapaus:
tarkastus (BCF-asia), joka viittaa GTIN-koodilla tunnistettuihin
rakennustuotteisiin.

```cypher
// Mihin tuotteisiin tämä viewpoint viittaa, ja mitkä ovat niiden GTIN-koodit?
MATCH (:Viewpoint {guid: $viewpoint})-[:HAS_COMPONENT]->(c:Component)-[:SAME_AS]->(e:IfcProduct)
RETURN c.ifc_guid, e.Name, c.gtin
```

```cypher
// Raportin kysely suoraan mallista: jokaisen seinän GTIN.
MATCH (w:IfcWall)-[:IS_DEFINED_BY]->(:IfcRelDefinesByProperties)-[:RELATING_PROPERTY_DEFINITION]
      ->(:IfcPropertySet {Name: 'Reuse'})-[:HAS_PROPERTIES]->(p:IfcPropertySingleValue {Name: 'GTIN'})
RETURN w.GlobalId, w.Name, p.NominalValue
```

```cypher
// Jokainen asia, joka koskee annettua rakennusosaa.
MATCH (e:IfcEntity {GlobalId: $guid})<-[:SAME_AS]-(:Component)<-[:HAS_COMPONENT]-(v:Viewpoint)<-[:HAS_VIEWPOINT]-(t:Topic)
RETURN DISTINCT t.server_assigned_id, t.title, t.topic_status
```

BCF-palvelu `files_information` näyttää tuotujen mallien `IfcProject`-guidin
`ifc_project`-kenttänä, minkä avulla asiakkaat voivat täyttää asian
otsakkeen tiedostot.

## Kyselyt Dataspatiumista

[Dataspatium](https://github.com/marwiss/Dataspatium), tämän palvelimen
kanssa kehitettävä selainasiakas, ajaa Cypheriä tätä graafia vasten
Neo4j-lähteensä kautta Boltilla (WebSocket Bolt-portissa), kun ylläpitäjä
avaa tietokannan, kuten kehityspäällyste tekee osoitteessa `127.0.0.1:7697`.
Sen Kontroll-työtila käyttää yllä olevia malleja (mallit, luokat,
komponentit `SAME_AS`-suhteen kautta, uusin valmis malli asiakirjaa kohti);
kyselyt ovat Dataspatiumin dokumentaatiossa (`docs/grafer.md`), ja live-ajot
on lueteltu tiedostossa [acceptance.md](../acceptance.md). Tuotantopalvelin
ei julkaise Boltia; hallintarajapinnan graafikysely
(`OPENCDE_GRAPH_QUERY_ENABLED`, [client-guide.md §7](client-guide.md)) antaa
järjestelmänvalvojille lukevan Cypherin ilman porttia. Sovellus
myös piirtää graafin korttiinsa IFC-graafi tuon kyselyn kautta tai Boltilla.

## Rajat ja tila

- Yksi muunnos kerrallaan; suuret mallit jonottavat. Esimerkkimalli (248
  entiteettiä) tuodaan noin sekunnissa; 200 MB:n arkkitehtimalli vie
  minuutteja.
- `IfcModel`-solmu kantaa kentät `state`, `entities`, `relationships`,
  `skipped`, `lossless`, `schema`, `ifc_project_guid`, aikaleimat ja `error`.
  Järjestelmänvalvojat voivat tarkastella sitä Neo4j Browserissa tai
  Memgraph Labissa:
  `MATCH (m:IfcModel) RETURN m.file_name, m.state, m.entities, m.error`.
- Projektin poisto poistaa sen mallien entiteetit samalla.
- Malli palautuu identtisenä molemmista tietokannoista 224 496 instanssiin ja 19 megatavuun
  asti kaikissa mitatuissa muodoissa. Suurempia ei ole kokeiltu.
