# IFC-LPG

Valinnainen IFC-LPG-moduuli muuttaa lähetetyn IFC-mallin graafidataksi,
jotta BCF-viewpointin komponentit voidaan yhdistää rakennusosiin, joihin ne
viittaavat, ja jotta mallista voidaan kysyä Cypherillä asioiden ja
asiakirjojen rinnalla.

Kytke se päälle asetuksella `OPENCDE_IFC_LPG_ENABLED=true` ja asenna
`ifc-lpg`-lisäosa (`uv sync --extra ifc-lpg`). Docker-kuva sisältää
lisäosan oletuksena (`ARG OPENCDE_EXTRAS` Dockerfilessa), mikä yli
kaksinkertaistaa sen koon (noin 680 MB, buildingSMARTin säännöillä 1,1 Gt, vastaan 300 MB); rakenna
`--build-arg OPENCDE_EXTRAS=` saadaksesi kevyemmän kuvan ilman
IfcOpenShelliä, kun moduuli pysyy pois päältä.

Marraskuuhun 2026 asti moduulin nimi oli IFC-graph. Sen asetusten nimet olivat
`OPENCDE_IFCGRAPH_*` ja komennon `opencde ifcgraph`, ja molemmat toimivat yhä;
palvelimen loki ja `opencde doctor` nimeävät vanhat asetukset, jotka se saa.

Muunnos, tiedoston kirjoittaminen ja tarkistukset tulevat kirjastosta
[IFC-LPG](https://github.com/marwiss/IFC-LPG), jonka Dataregium asentaa sen
repositoriosta tietystä commitista ja jonka README kertoo, miten malli
tallennetaan graafiin. Palvelimen oma prosessi käyttää osaa, joka ei tarvitse
IfcOpenShelliä; `ifc-lpg`-lisäosa lisää työprosessit, jotka tarvitsevat sitä.

## Mitä lähetyksessä tapahtuu

1. Documents API -lähetys valmistuu (tai tiedosto lähetetään valintasivulta,
   tai BCF-projektiasiakirja postataan) nimellä, jonka pääte on `.ifc` tai
   `.ifczip`.
2. Palvelin luo projektiin liitetyn `IfcModel`-solmun (tila `queued`) ja
   käynnistää muunnoksen taustalla, yhden kerrallaan.
3. Erillinen työprosessi (`python -m ifc_lpg.worker`) lukee
   tiedoston. Se toimii aikarajalla
   (`OPENCDE_IFC_LPG_TIMEOUT_SECONDS`, 15 minuuttia), osoiteavaruusrajalla
   POSIX-järjestelmissä (`OPENCDE_IFC_LPG_MEMORY_MB`, 4 GiB) ja entiteettien
   ylärajalla (`OPENCDE_IFC_LPG_MAX_ENTITIES`). Kaatuminen tai jumiutuminen
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
`OPENCDE_IFC_LPG_VALIDATE_UPLOADS=false` poistaa tarkistuksen käytöstä.

Tulos on version metatiedoissa, joita mikä tahansa Documents API -asiakas voi lukea:

| Kohta | Tyyppi | Arvo |
|---|---|---|
| `ifc_validation_status` | `string` | `pending`, kunnes tiedosto on tarkistettu, sitten `passed`, `warnings`, kun jokainen huomautus on varoitus, `issues`, kun vähintään yksi on virhe, tai `unknown`, kun sitä ei voitu tarkistaa |
| `ifc_validation_issues` | `integer32` | Kuinka monta huomautusta tiedostossa on |
| `ifc_validation_checked_at` | `date-time` | Milloin se tarkistettiin |
| `ifc_validation_ruleset` | `string` | Millä se tarkistettiin, yksi arvo kutakin tarkistusta kohden |
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
  "ruleset": "IfcOpenShell 0.9.0.post1: schema and EXPRESS rules; ifc-gherkin-rules 893f827 with IfcOpenShell 0.8.6",
  "issue_count": 2,
  "error_count": 1,
  "truncated": false,
  "checks": [
    {"name": "schema", "state": "done", "ruleset": "IfcOpenShell 0.9.0.post1: schema and EXPRESS rules", "issue_count": 1, "rules_not_run": [], "documents": [], "specifications": []},
    {"name": "gherkin", "state": "done", "ruleset": "ifc-gherkin-rules 893f827 with IfcOpenShell 0.8.6", "issue_count": 1, "rules_not_run": [{"rule": "GEM004", "error": "FileNotFoundError"}], "documents": [], "specifications": []}
  ],
  "issues": [
    {
      "kind": "schema",
      "severity": "error",
      "message": "On instance:\n    #373=IfcWallStandardCase('1Xezbq735AdBO_4DerG66G',...)\n...\nRule IfcRoot.UR1:\n    The attribute GlobalId should be unique\n...",
      "step_id": 373,
      "global_id": "1Xezbq735AdBO_4DerG66G"
    },
    {
      "kind": "gherkin",
      "rule": "IFC106",
      "severity": "warning",
      "message": "IFC106 - Resource entities should be referenced by rooted entity. ...",
      "step_id": 99999
    }
  ]
}
```

Siinä luetellaan enintään 10 000 huomautusta, kukin instansseineen ja
juurioliolle myös GlobalId-tunnisteineen, jotta mallinäkymä löytää elementin.
`kind` kertoo, mikä huomautuksen löysi: IFC-skeeman `schema`, `entity_rule`,
`simpletype_rule` tai `global_rule`, tai `gherkin` jollekin buildingSMARTin
säännöistä, jonka koodi on kentässä `rule`. `checks` pitää tarkistukset
erillään. Viesti voi lainata tiedoston riviä, ja se katkaistaan 1 000 merkin
kohdalta. Version sivu selaimessa näyttää ensimmäiset 100
huomautusta ja tarjoaa koko raportin tiedostona.

Monet tiedostot rikkovat jo jotakin sääntöä tullessaan ohjelmastaan: 12
esimerkkitiedostoa 26:sta tekee niin, yksi Teklasta 5 711 huomautuksella.
Esimerkkitiedoston ja sen kirjoitetun kopion tarkistus kesti yhteensä 3–66
sekuntia.

### buildingSMARTin ifc-gherkin-rules

Kun `OPENCDE_IFC_LPG_GHERKIN_ENV` osoittaa niille ympäristön, lähetykset
tarkistetaan myös buildingSMARTin `ifc-gherkin-rules`-sääntöjä vasten:
normatiivisia sääntöjä ja alan käytäntöjä, jotka buildingSMARTin
validointipalvelu tarkistaa skeeman lisäksi ([ADR 0012](../adr/0012-buildingsmarts-rules-run-in-an-environment-of-their-own.md)).
Ne ajetaan skeematarkistuksen jälkeen samanlaisessa työprosessissa samoin
rajoin ja niin kuin sääntökokoelman omat testit ne ajavat: behavella ja
IfcOpenShell 0.8.6:lla, jota sääntökokoelman CI käyttää. Sääntökokoelman 722
testitiedostolla tämä antaa jokaiselle sen tuloksen, jota sen testit odottavat.

Säännöt saavat oman ympäristönsä, koska yksi niiden apufunktioista ei toimi
IfcOpenShell 0.9:n kanssa, jota Dataregium käyttää.
`python -m ifc_lpg.gherkin_install <kansio>` tekee sen lukituista
latauksista, joista jokainen tarkistetaan SHA-256-tiivistettään vasten:
sääntökokoelma tietyssä commitissa, IfcOpenShellin 0.8.6-käännös alustalle ja
Python-paketit tiivisteineen. Kaksi IFC-LPG:n omaa pientä tiedostoa korvaa
sääntökokoelman Django-osat, jotka vain kirjoittavat tulokset
validointipalvelun tietokantaan.
Julkaistusta levykuvasta ne puuttuvat, koska ne kasvattavat sitä noin 425 Mt.
Levykuvassa, jonka tunniste päättyy `-gherkin`, kuten `latest-gherkin` tai
`3.0.0-gherkin`, ympäristö on hakemistossa `/opt/gherkin`, ja
`OPENCDE_IFC_LPG_GHERKIN_ENV` osoittaa siihen, samoin levykuvassa, joka on
käännetty valinnalla `--build-arg OPENCDE_GHERKIN=1`. Docker composessa valinnan
tekee `OPENCDE_IMAGE_TAG` tai `OPENCDE_GHERKIN=1` tiedostossa `.env`.

Säännön löydös on huomautus, jonka laji on `gherkin`, ja siinä on säännön koodi,
kuten `IFC106`, ja vakavuus `error` tai `warning`. Alan käytäntöjen säännöt vain
varoittavat, ja tiedosto, jonka kaikki huomautukset ovat varoituksia, saa tilan
`warnings`, koska buildingSMARTin validointipalvelu pitää sellaista tiedostoa
kelvollisena. Sääntö, joka nosti poikkeuksen sen sijaan, että olisi löytänyt
jotakin, jää ilman tulosta, ja se luetellaan tarkistuksensa kohdassa
`rules_not_run`. Jos sääntöjä ei voida ajaa lainkaan, niiden tarkistus on
`failed`, ja skeeman tarkistus jää ainoaksi.

Säännöt vievät enemmän aikaa kuin skeematarkistus: kahdeksalla esimerkkimallilla
5 sekunnista pienimmälle noin 5 minuuttiin suurimmalle, ja useimmille puolesta
minuutista kahteen minuuttiin.

### Information Delivery Specifications (IDS)

Lähetys tarkistetaan myös jokaista projektinsa IDS-asiakirjaa vasten:
asiakirjaa, jonka uusimman version nimi päättyy `.ids`, enintään 50
([ADR 0015](../adr/0015-uploads-are-checked-against-the-projects-ids-documents.md)).
IFC-LPG:n tarkistus lukee jokaisen IDS:n turvallisesti ja antaa sen
IfcOpenShellin IfcTesterille, samalle tarkistimelle, jota Dataspatium ajaa
selaimessa, jotta molemmat antavat saman tuloksen. Se ajetaan muiden
tarkistusten jälkeen, samanlaisessa työprosessissa samoin rajoin. Myöhemmin
lähetetty IDS koskee sen jälkeen lähetettyjä IFC-versioita.

Jokaisesta vaatimuksesta, jota elementti ei täytä, tulee huomautus lajia `ids`,
vakavuudella `error`, määrittelyn tunnisteella tai nimellä kentässä `rule` ja
IDS-asiakirjalla kentässä `document_id`. Samoin käy pakolliselle määrittelylle,
joka ei koske mitään tiedostossa, ja elementille, jota kielletty määrittely
koskee. Raportin tarkistus `ids` luettelee käyttämänsä asiakirjat versioineen ja
jokaisen määrittelyn käyttöineen ja tuloksineen (`passed`, `failed` tai
`not applicable`) sekä sen, kuinka moneen elementtiin se kohdistuu ja kuinka
monta huomautusta se antoi. IDS-asiakirja, jota ei voi lukea, esimerkiksi
sellainen, jossa on DTD, luetellaan kohdassa `rules_not_run` syineen, ja muut
tarkistetaan silti. Version sivu näyttää määrittelyt omassa taulukossaan.

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

Ei solmuja oletuksena (`OPENCDE_IFC_LPG_INCLUDE_GEOMETRY=false`):
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
uv run opencde ifc-lpg export <mallin tunnus> model.ifc            # kirjoita tiedosto ja validoi se
uv run opencde ifc-lpg export <mallin tunnus> model.ifc --verify   # ja vertaa sitä lähetettyyn
```

Solmut ovat ne, joita kyselyt tarvitsevat. Se, minkä ne jättävät pois, kirjoitetaan
STEP-muotoon ja pakataan tekstiksi `StepBlock`-solmuihin, jotka riippuvat
`IfcModel`-solmussa: se on graafissa, mutta Cypherin ulottumattomissa, eikä sitä voi
muuttaa siellä. Se ei voi olla tuotteiden ominaisuuksia, koska suuri osa siitä on
tuotteiden yhteistä. Asetuksella `OPENCDE_IFC_LPG_INCLUDE_GEOMETRY=true` jokaisesta
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
`python -m ifc_lpg.equivalence first.ifc second.ifc`.

Asetuksella `OPENCDE_IFC_LPG_LOSSLESS=false` malli muunnetaan kuten ennen versiota
3.0.0: se luetaan IfcOpenShellillä, ja se, mikä ei ole solmuja, jätetään kokonaan pois.
Tällaista mallia, kuten aiemman version muuntamaakaan, ei voi kirjoittaa takaisin.

## Ylläpito

Jokainen IFC-tiedoston lähetys lisää `IfcModel`-solmun entiteetteineen, joten
uusia versioita vastaanottava projekti kerää graafeja, joita kukaan ei
kysele. Komentorivi luettelee ja karsii ne; asiakirjat ja niiden tiedostot
säilyvät aina:

```sh
uv run opencde ifc-lpg list --project <projektin tunnus>
uv run opencde ifc-lpg prune                   # epäonnistuneet mallit sekä valmiit mallit, jotka saman asiakirjan
                                                # uudempi valmis versio on korvannut
uv run opencde ifc-lpg prune --project <id> --all   # yhden projektin jokainen malli (esimerkiksi testipino)
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
ominaisuutta (`OPENCDE_IFC_LPG_GTIN_PROPERTY_SET=Reuse`,
`OPENCDE_IFC_LPG_GTIN_PROPERTY=GTIN`), sen arvo kopioidaan komponenttiin
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

## Nimetyt kyselyt

Projektin jäsen esittää version mallille kysymyksiä nimeltä, samalla
bearer-tunnisteella kuin Documents API:lle; vapaa Cypher jää ylläpitäjille
([ADR 0016](../adr/0016-members-ask-the-ifc-graph-named-queries.md)).
`GET /documents/1.0/documents/{id}/versions/{index}/ifc-queries` luettelee
kyselyt parametreineen ja sarakkeineen ja kertoo kentässä `model_state`, kuinka
pitkällä mallin muunnos on. `GET …/ifc-queries/{name}` esittää yhden kyselyn,
parametrit kyselymerkkijonossa, ja vastaa sarakkeilla ja riveillä, joista
kukin on lista sarakkeiden järjestyksessä:

```http
GET /documents/1.0/documents/{id}/versions/1/ifc-queries/property?pset=Reuse&property=GTIN
```

```json
{"name": "property", "columns": ["global_id", "class", "name", "value", "type"],
 "rows": [["1Xezbq735AdBO_4DerG66G", "IfcWallStandardCase", "YVT-A", "3", "IFCLABEL"]],
 "truncated": false}
```

| Kysely | Parametrit | Mihin se vastaa |
|---|---|---|
| `element-classes` | | Kuinka monta elementtiä mallissa on kustakin luokasta |
| `elements` | `class` | Luokan elementit ja kunkin sisältävä tilarakenne |
| `storeys` | | Kerrokset, niiden korkeus ja kuinka monta elementtiä ja tilaa kussakin on |
| `spaces` | | Tilat, niiden kerros sekä niiden netto- ja bruttopinta-ala |
| `areas` | | Kunkin kerroksen tilojen nettopinta-ala yhteenlaskettuna |
| `materials` | `class` | Kunkin elementin materiaalit: oma tai sen kerrosten, luettelon tai osien |
| `property` | `pset`, `property`, `class` | Yhden ominaisuuden arvo jokaisessa kohteessa, jolla se on, IFC-tyyppeineen |

`class` nimeää IFC-luokan, kuten `IfcWall`, ja ottaa mukaan sen aliluokat:
pakollinen kyselylle `elements`, valinnainen muille. Vastauksessa on enintään
10 000 riviä, ja `truncated` kertoo, kun niitä oli enemmän; kysely keskeytetään
10 sekunnin jälkeen. Jokainen kysely alkaa jäsenestä ja tavoittaa mallin
projektin kautta, vain lukee ja ottaa arvonsa parametreina. Versio, jolla ei
ole mallia tai jota käyttäjä ei saa nähdä, vastaa 404, ja versio, jonka mallia
vielä muunnetaan, vastaa 409. Ominaisuusdokumentti ilmoittaa kyselyt kentässä
`ifc_queries`.

## Kyselyt Dataspatiumista

[Dataspatium](https://github.com/marwiss/Dataspatium), tämän palvelimen
kanssa kehitettävä selainasiakas, ajaa Cypheriä tätä graafia vasten
Neo4j-lähteensä kautta Boltilla (WebSocket Bolt-portissa), kun ylläpitäjä
avaa tietokannan, kuten kehityspäällyste tekee osoitteessa `127.0.0.1:7697`.
Sen Dataregium-työtila käyttää yllä olevia malleja (mallit, luokat,
komponentit `SAME_AS`-suhteen kautta, uusin valmis malli asiakirjaa kohti);
kyselyt ovat Dataspatiumin dokumentaatiossa (`docs/grafer.md`), ja live-ajot
on lueteltu tiedostossa [acceptance.md](../acceptance.md). Tuotantopalvelin
ei julkaise Boltia; hallintarajapinnan graafikysely
(`OPENCDE_GRAPH_QUERY_ENABLED`, [client-guide.md §7](client-guide.md)) antaa
järjestelmänvalvojille lukevan Cypherin ilman porttia. Sovellus
myös piirtää graafin korttiinsa IFC-LPG tuon kyselyn kautta tai Boltilla.

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
