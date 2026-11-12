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
2. Palvelin luo projektiin liitetyn `Conversion`-tietueen (tila `queued`) ja
   käynnistää muunnoksen taustalla, yhden kerrallaan.
3. Erillinen työprosessi (`python -m ifc_lpg.worker`) lukee
   tiedoston. Se toimii aikarajalla
   (`OPENCDE_IFC_LPG_TIMEOUT_SECONDS`, 15 minuuttia), osoiteavaruusrajalla
   POSIX-järjestelmissä (`OPENCDE_IFC_LPG_MEMORY_MB`, 4 GiB) ja entiteettien
   ylärajalla (`OPENCDE_IFC_LPG_MAX_ENTITIES`). Kaatuminen tai jumiutuminen
   tappaa työprosessin, ei palvelinta. `.ifczip` puretaan lähetyksen
   kokorajan puitteissa.
4. Tietueet tuodaan erissä `UNWIND … CREATE` -lauseilla (siirrettävä Cypher,
   ei APOC:ia). `Conversion` päätyy tilaan `done` lukumäärineen ja
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
erillisessä työprosessissa samoin rajoin. Oletuksena se ei koskaan estä lähetystä: tiedosto
tallennetaan sellaisenaan, löysi tarkistus mitä tahansa; projekti voi valita
toisin ([alla](#virheellisten-tiedostojen-hylkääminen-ja-tiedoston-tarkistaminen-etukäteen)). BCF-projektidokumenttia
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
  "error_count": 2,
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
      "rule": "GEM111",
      "severity": "error",
      "message": "GEM111 - No duplicated points within a polyloop or polyline. ...",
      "step_id": 202,
      "ifc_class": "IfcPolyline",
      "root_global_id": "1Xezbq735AdBO_4DerG66G"
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
validointipalvelu tarkistaa skeeman lisäksi (ADR 0012).
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

Löydöksellä, joka osoittaa instanssin, on myös sen luokka kentässä
`ifc_class` ja kentässä `root_global_id` lähimmän instanssin tavoittavan
juuriolion GlobalId: juurioliolla sen oma, ja seinän rungon ääriviivassa
olevalla `IfcPolyline`-instanssilla, jonka GEM111 löytää, seinän. Juuriolio
tavoittaa instanssin samoin kuin IFC-LPG:n polut: eteenpäin attribuuttien
kautta ja taaksepäin käänteisten attribuuttien kautta. Työprosessi lukee
molemmat tiedostosta, joten mallia ei tarvitse muuntaa, ja `global_id` pysyy
instanssin omana. Version sivu näyttää luokan instanssin vieressä ja elementin
GlobalId:n, kun instanssilla ei ole omaa, jotta myös asiakas voi osoittaa
elementin. Löydös, joka ei osoita instanssia, pysyy ennallaan, ja löydöksellä,
jonka instanssia mikään ei tavoita, on vain luokka.

Säännöt vievät enemmän aikaa kuin skeematarkistus: kahdeksalla esimerkkimallilla
5 sekunnista pienimmälle noin 5 minuuttiin suurimmalle, ja useimmille puolesta
minuutista kahteen minuuttiin.

### Information Delivery Specifications (IDS)

Lähetys tarkistetaan myös jokaista projektinsa IDS-asiakirjaa vasten:
asiakirjaa, jonka uusimman version nimi päättyy `.ids`, enintään 50
(ADR 0015).
IFC-LPG:n tarkistus lukee jokaisen IDS:n turvallisesti ja antaa sen
IfcOpenShellin IfcTesterille, samalle tarkistimelle, jota Dataspatium ajaa
selaimessa, jotta molemmat antavat saman tuloksen. Se ajetaan muiden
tarkistusten jälkeen, samanlaisessa työprosessissa samoin rajoin. IDS-asiakirjan uusi versio saa projektin jokaisen IFC-asiakirjan uusimman version tarkistetuksi uudelleen,
enintään 500, jotta sen raportti seuraa vaatimuksia sellaisina kuin ne nyt ovat; vanhemmat versiot pitävät
raporttinsa.

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

### buildingSMART Data Dictionary (bSDD)

Asetuksella `OPENCDE_BSDD_ENABLED=true` lähetys tarkistetaan myös buildingSMARTin Data Dictionarya vasten
IDS-tarkistuksen jälkeen. Työprosessi lukee tiedoston viittaukset siihen: jokaisen
`IfcClassificationReference`-viittauksen, jonka `Location` on bSDD-URI, kuten
`https://identifier.buildingsmart.org/uri/molio/cciconstruction/1.0/class/L-BD`, tai jonka `Identification`
(IFC2X3:ssa `ItemReference`) on koodi siinä sanakirjassa, jonka URI on viittauksen `Location`-kentässä tai sen
luokituksessa, sekä objektit, joihin viittaus liittyy; jokaisen ominaisuusjoukon ominaisuuden, jonka `Specification`
(IFC 4.3) tai aiemmassa skeemassa `Description` on bSDD:n ominaisuuden URI, kuten
`https://identifier.buildingsmart.org/uri/buildingsmart/ifc/4.3/prop/FireRating`, sekä objektit, joihin sen joukko
liittyy; ja jokaisen `Pset_…`- tai `Qto_…`-nimisen joukon ominaisuudet. Toinen työprosessi lukee bSDD-URI:t, jotka
projektin IDS-asiakirjat antavat luokitus- ja ominaisuusfasettiensa (facet) `uri`-attribuutissa, kerran asiakirjan
kustakin versiosta ja samalla tavalla kuin IDS-tarkistus sen lukee. Palvelin kysyy sitten jokaisesta URI:sta bSDD:n
API:lta osoitteessa `OPENCDE_BSDD_API_URL` (`https://api.bsdd.buildingsmart.org`), kullekin kysymykselle asetetulla
aikarajalla (`OPENCDE_BSDD_TIMEOUT_SECONDS`, 10 sekuntia) ja kahdella uusintayrityksellä, kun bSDD vastaa 429 tai
5xx, ja pitää jokaisen vastauksen muistissa vuorokauden (`OPENCDE_BSDD_CACHE_SECONDS`, 86400; 0 kysyy joka kerta),
joten URI:sta, jonka useampi tiedosto tai IDS-asiakirja nimeää, kysytään vain kerran. Mitään, mitä tiedosto nimeää,
ei haeta: URI menee bSDD:n API:lle parametrina, ja muulla kuin `identifier.buildingsmart.org`-palvelimella oleva URI
raportoidaan sen sijaan. Tarkistus on oletuksena pois päältä, koska se lähettää tiedoston ja IDS-asiakirjojen URI:t
sekä tiedoston ominaisuusjoukkojen nimet bSDD:lle; tuotannossa osoitteen on oltava https.

Kaikki, mitä se löytää, on varoitus lajia `bsdd`: luokitusviittaus, ominaisuus tai ominaisuusjoukko on kentässä
`step_id`, yhden siihen liittyvän objektin GlobalId kentässä `global_id` ja tuon objektin luokka viestissä:

- luokitusviittaus, jonka luokkaa tai ominaisuutta bSDD ei tunne; sanakirja on kentässä `rule` ja sen nimeävä
  attribuutti kentässä `attribute`, sillä malli voi käyttää sanakirjaa, jota bSDD ei ole julkaissut;
- ominaisuus, jonka `Specification` tai `Description` nimeää ominaisuuden, jota bSDD ei tunne; sanakirja on kentässä
  `rule` ja joukko ja ominaisuus kentässä `attribute`, kuten `Pset_WallCommon.FireRating`;
- IFC 4.3 -tiedostossa ominaisuusjoukko, jota bSDD:n IFC-sanakirjassa (`buildingsmart/ifc/4.3`) ei ole, tai
  ominaisuus, jota se ei luettele siinä joukossa; joukko ja ominaisuus ovat kentässä `attribute`, kuten
  `Pset_WallCommon.Colour`;
- projektin IDS-asiakirjan URI, jota bSDD ei tunne; sanakirja on kentässä `rule`, asiakirja kentässä `document_id` ja
  sen määrittely ja fasetti viestissä, mutta kenttiä `step_id` ja `global_id` ei ole, koska varoitus ei kerro
  tiedostosta mitään: se on jokaisen asiakirjaa vasten tarkistetun tiedoston raportissa, eikä muutosjoukon kokeilu
  koskaan laske sitä omiin löydöksiinsä.

bSDD julkaisee vain tuon yhden IFC-sanakirjan, joten IFC4- tai IFC2X3-tiedoston ominaisuusjoukkoja, jotka niiden
skeemat määrittelevät toisin, ei tarkisteta; eikä `Reference`-ominaisuutta, jonka IFC 4.3 antaa lähes jokaiselle
joukolle ja jonka bSDD jättää niistä kaikista pois, raportoida. Tarkistuksen `ruleset` nimeää bSDD:n palvelimen ja
sanakirjat, joita vasten tiedosto ja sen IDS-asiakirjat tarkistettiin. Se lukee tiedostosta enintään 1 000
viittausta, 1 000 bSDD:n nimeävää ominaisuutta ja 500 joukkoa sekä IDS-asiakirjasta enintään 1 000 URI:a, ja varoitus
kertoo, kun tiedostossa tai asiakirjassa on enemmän. IDS-asiakirja, jota ei voi lukea, jätetään IDS-tarkistukselle,
joka raportoi sen. Kun bSDD:hen ei saada yhteyttä tai se ei vastaa niin kuin sen API vastaa, tarkistus on `failed` ja
syy on sen kentässä `error`, ja muut tarkistukset pysyvät voimassa: bSDD:n tavoittamattomuus ei ole koskaan mallin
virhe. Ennakkotarkistus ja muutosjoukon kokeilu tekevät myös tämän tarkistuksen, ja kyvykkyysdokumentti kertoo, onko
se päällä, nimellä `bsdd` kohdassa `ifc_validation`.

### Kunkin kerroksen huoneet

Asetuksella `OPENCDE_ROOMS_ENABLED=true` lähetyksen, ennakkotarkistuksen ja kokeilun raportti saa myös kunkin
kerroksen huoneet, jotka löydetään sen seinistä samoin kuin Dataspatium ne löytää: työprosessi ajaa kopion sovelluksen
koodista IfcOpenShellillä ja shapelyllä tarkistusten jälkeen ja samoin rajoin. Seinän keskilinja on sen
`Axis`-esitys, joka Dataspatiumin tekemillä seinillä on, tai muuten sen kappaleen jalanjäljen pitkä akseli; päät
liitetään yhteen kerroksen paksuimman seinän puolikkaan ja 0,05 m:n etäisyydellä, ja keskilinjat, jotka rajaavat
vähintään 0,5 m² ja 0,5 m leveän alueen, muodostavat huoneen. Raportin `rooms` sisältää jokaisen kerroksen
korkeusjärjestyksessä, ja kussakin on:

- `rooms`: kunkin huoneen `index` kerroksessa, sen `area` (m²) ja `perimeter` (m) keskilinjoja pitkin, sen `walls`
  GlobalId-tunnisteina ja sen `neighbours` indekseinä;
- `external`: huoneiden ulkopuolta kulkevat seinät, kukin kenttineen `global_id`, `name` ja `length` sekä
  ilmansuunta, johon se on suunnattu (`facing`, `N`, `NE` … `NW`); pohjoinen tulee karttamuunnoksesta, muuten
  `TrueNorth`-suunnasta, muuten mallin y-akselista, kuten `north` kertoo (`map`, `true_north` tai `model`);
- `dangles` ja `dangling_walls`: avoimet seinänpäät, `[x, y]` metreinä mallin tasossa, ja niiden seinät;
- `closed`: onko kerroksessa huone eikä yhtään avointa päätä;
- `walls`, `unread` ja `unread_walls`: kuinka monta seinää kerroksessa on ja kuinka moni ja mitkä niistä eivät
  antaneet keskilinjaa;
- `tolerance`: kuinka kaukana toisistaan, metreinä, kaksi päätä saavat olla ja silti liittyä yhteen.

```json
"rooms": {
  "storeys": [
    {
      "storey": "Level 1", "elevation": 0.0, "closed": true,
      "rooms": [{"index": 1, "area": 60.0, "perimeter": 32.0, "walls": ["0iZ0AvLQ5C8f7TH4npBFwH", "…"], "neighbours": []}],
      "external": [{"global_id": "1pD0WEwnf1UeV30DigCQgn", "name": "North", "facing": "N", "length": 10.0}, "…"],
      "dangles": [], "dangling_walls": [], "walls": 4, "unread": 0, "unread_walls": [],
      "tolerance": 0.15, "north": "model"
    }
  ],
  "cut": false
}
```

Huoneet ovat oma osionsa eivätkä koskaan huomautus: ne eivät muuta tilaa eivätkä lukumääriä, projekti, joka hylkää
virheelliset tiedostot, ei koskaan hylkää tiedostoa sen huoneiden vuoksi, ja kokeilu on `clean` tai `issues`
huoneistaan riippumatta; ne ovat sovelletun tiedoston huoneet. Version sivu näyttää rivin jokaisesta kerroksesta,
jossa on seiniä. Luettelot katkaistaan 100 kerrokseen, 500 huoneeseen kerrosta kohden ja 200 merkintään kaikissa
muissa luetteloissa, ja `cut` kertoo siitä, eikä yli 2 000 seinän malli saa huoneita lainkaan. Kun huoneita ei voida
löytää, raportissa ei ole kenttää `rooms`, ja loki kertoo syyn (`ifc_rooms_failed`) ilman sitä, mitä tiedosto sanoo.
Oletuksena pois päältä; kyvykkyysdokumentti kertoo, onko se päällä, nimellä `rooms` kohdassa `ifc_validation`.

### Mitä muunnettu malli näyttää

Kun malli on muunnettu, raporttiin tulee oma tarkistus, `graph`, jossa on kahdenlaisia huomautuksia. Instanssi, jota
mikään GlobalId:n omaava ei tavoita eteen- eikä taaksepäin, on varoitus lajia `reachability`, ja sen STEP-tunniste on
kentässä `step_id` ja luokka viestissä: vain tuo numero nimeää sen, kuten käyttämättömän sijoituksen, joten
muutosjoukko voi osoittaa sen pelkällä STEP-tunnisteella. Tuote, jonka muotoa geometria-ajo ei pystynyt rakentamaan,
on huomautus lajia `geometry` GlobalId:nsä kanssa. Kumpikaan ei hylkää tiedostoa: ne tulevat latauksen jälkeen, ja
varoitus antaa tilaksi `warnings`. Ennen kuin malli on muunnettu, raportissa ei ole tarkistusta `graph`.
Geometrian kanssa STEP-lohkossa pidettyä instanssia, kuten irrallista pistettä, ei
luetella: tarkistus näkee vain solmut.

### Virheellisten tiedostojen hylkääminen ja tiedoston tarkistaminen etukäteen

Ylläpitäjä voi rastittaa projektin sivulla *Hylkää lähetykset, joissa on
validointivirheitä* (`block_on_validation_errors` hallinta-API:ssa).
Tarkistukset ajetaan silloin ennen kuin tiedostosta tulee versio, lähetyksen
viimeistelyssä ja lähetyssivulla, ja tiedosto, jossa on yksi tai useampi virhe,
hylätään vastauksella `422 ifc_validation_failed`; varoitukset päästetään läpi.
Hylätty tiedosto säilyy vuorokauden ennakkotarkistuksena, ja virheen `report`
kertoo, missä sen raportti on. Tiedosto, jota ei voitu tarkistaa lainkaan,
päästetään läpi tilassa `unknown`, jotta rikkinäinen validaattori ei koskaan
pysäytä työtä. Hyväksytty tiedosto tarkistetaan kerran: tuloksesta tulee
version tulos, aivan kuin tarkistus olisi ajettu jälkikäteen.

Jokainen muokkaaja tai hallinnoija voi myös tarkistaa tiedoston tekemättä siitä
versiota, samalla bearer-tunnuksella ja projektin asetuksesta riippumatta:

```http
POST /documents/1.0/projects/{project_id}/ifc-precheck
Content-Disposition: attachment; filename="model.ifc"
```

Runko on tiedosto. Vastaus on `202` ja raportin `url`, `pending` kunnes
tarkistukset ovat valmiit; sen jälkeen sillä on version raportin muoto,
tiedoston nimi ja ennakkotarkistuksen vanhenemisaika. Jokainen jäsen lukee sen
vuorokauden ajan. Kyvykkyysdokumentti ilmoittaa ennakkotarkistuksen nimellä
`ifc_precheck`.

## Graafi

Jokaisesta entiteetistä tulee `Entity`-solmu, joka kantaa luokkaansa ja
kaikkia ylätyyppejään nimiöinä, esimerkiksi `Entity:IfcWallStandardCase:IfcWall:
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
- Suhdetyypit kirjoitetaan isoin kirjaimin, ja GTIN-kopio BCF-komponentteihin on
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
`Model`-solmussa: se on graafissa, mutta Cypherin ulottumattomissa, eikä sitä voi
muuttaa siellä. Se ei voi olla tuotteiden ominaisuuksia, koska suuri osa siitä on
tuotteiden yhteistä. Asetuksella `OPENCDE_IFC_LPG_INCLUDE_GEOMETRY=true` jokaisesta
instanssista tulee sen sijaan solmu, moninkertaisella koolla ja tuontiajalla; kyselyt
kestivät suunnilleen yhtä kauan mittauksissa.
Tyylitelty kohde (`IfcStyledItem`) on aina solmu, jotta jokaista tyyliä voidaan muuttaa, ja `Model`-solmun `form_version` kertoo graafin muodon (2 IFC-LPG:n 2026-11-10 julkaisusta alkaen).

| Tiedostossa | Graafissa |
|---|---|
| Viittaus | Suhde, jolla on `position`, luetteloiden luettelossa `[rivi, sarake]`; käänteisillä suhteilla sitä ei ole |
| Viittaus lohkossa olevaan instanssiin | Sen tunnus, kuten `Representation__step: 1234` |
| Tyypitetty arvo, `IFCLABEL('3')` | `NominalValue: "3"` ja sen vieressä `NominalValue__type: "IFCLABEL"` |
| Lukujen luetteloiden luettelo | JSON-tekstiä |
| Se, millä ei ole yksinkertaista muotoa, kuten tyypitettyjen arvojen luettelo | Merkittyä JSONia, tyyppinä `$json` |
| Otsake | `ifc_header` solmussa `Model` |
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
hylkää sen, mitä se ei osaa lukea. ADR 0010 kertoo miksi ja
ADR 0011 miten tiedosto validoidaan.

`--verify` kysyy, sisältävätkö kaksi tiedostoa saman mallin määritelmän
ADR 0009 mukaan: yksi yhteen, arvo arvolta ja ilman toleranssia, sijaintitieto
raportissa nimettynä. Valinnalla `--geometry` myös jokaisen tuotteen verkko rakennetaan,
ja niitä verrataan bitti bitiltä. Mitkä tahansa kaksi tiedostoa voi verrata komennolla
`python -m ifc_lpg.equivalence first.ifc second.ifc`.

Asetuksella `OPENCDE_IFC_LPG_LOSSLESS=false` malli muunnetaan kuten ennen versiota
3.0.0: se luetaan IfcOpenShellillä, ja se, mikä ei ole solmuja, jätetään kokonaan pois.
Tällaista mallia, kuten aiemman version muuntamaakaan, ei voi kirjoittaa takaisin.

## Ylläpito

Jokainen IFC-tiedoston lähetys lisää `Conversion`-tietueen ja mallin entiteetteineen, joten
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
MATCH (:Project {project_id: $project})-[:HAS_CONVERSION]->(m:Conversion {state: 'done'})
WITH coalesce(m.document_id, m.bcf_document_guid) AS doc, m
ORDER BY m.version_index DESC, m.done_at DESC
WITH doc, collect(m)[0] AS latest
MATCH (e:IfcProduct {model_id: latest.id})
RETURN latest.file_name AS model, count(e) AS products
```

## BCF-komponenttien linkitys

Kun viewpoint luodaan komponenttien kanssa, jokainen komponentti, jonka
`ifc_guid` vastaa jonkin projektin tuodun mallin rakennusosan
`GlobalId`-arvoa, saa määritetyn ominaisuuden
(`OPENCDE_IFC_LPG_GTIN_PROPERTY_SET=Reuse`, `OPENCDE_IFC_LPG_GTIN_PROPERTY=GTIN`)
arvon kenttään `gtin`, kun rakennusosalla on sellainen: palvelin hakee
GlobalId-tunnukset mallista IFC-LPG:n `property_values`-funktiolla ja tallentaa
arvon komponenttiin eikä tee suhdetta malliin; rakennusosa löytyy
`GlobalId`-tunnuksellaan. Sama haku ajetaan projektin jokaiselle olemassa
olevalle komponentille, kun mallin tuonti valmistuu, joten myös ennen mallin
lähettämistä tai sen muuntamisen aikana luodut viewpointit saavat GTIN-arvonsa.
Tämä on vuoden 2023 tutkimusraportin käyttötapaus: tarkastus (BCF-asia), joka
osoittaa GTIN-tunnuksella yksilöityihin rakennustuotteisiin.

```cypher
// Mihin tuotteisiin tämä viewpoint viittaa, ja mitkä ovat niiden GTIN-koodit?
MATCH (:Viewpoint {guid: $viewpoint})-[:HAS_COMPONENT]->(c:Component)
MATCH (e:IfcProduct {GlobalId: c.ifc_guid})
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
MATCH (:Component {ifc_guid: $guid})<-[:HAS_COMPONENT]-(v:Viewpoint)<-[:HAS_VIEWPOINT]-(t:Topic)
RETURN DISTINCT t.server_assigned_id, t.title, t.topic_status
```

BCF-palvelu `files_information` näyttää tuotujen mallien `IfcProject`-guidin
`ifc_project`-kenttänä, minkä avulla asiakkaat voivat täyttää asian
otsakkeen tiedostot.

## Nimetyt kyselyt

Projektin jäsen esittää version mallille kysymyksiä nimeltä, samalla
bearer-tunnisteella kuin Documents API:lle; vapaa Cypher jää ylläpitäjille
(ADR 0016).
Kyselyt ovat IFC-LPG:n luettelo (`ifc_lpg.queries`), joten kirjastoon lisätty
kysely ilmestyy tänne.
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
| `storeys` | | Kerrokset, niiden korkeus tiedoston ilmoittamana ja metreinä (`elevation_m`, attribuutista tai sijoituksesta, kuten `elevation_source` kertoo), ja kuinka monta elementtiä ja tilaa kussakin on |
| `spaces` | | Tilat, niiden kerros sekä niiden netto- ja bruttopinta-ala |
| `areas` | | Kunkin kerroksen tilojen nettopinta-ala yhteenlaskettuna, ja kerroksen korkeus metreinä |
| `materials` | `class` | Kunkin elementin materiaalit: oma tai sen kerrosten, luettelon tai osien |
| `property` | `pset`, `property`, `class` | Yhden ominaisuuden arvo jokaisessa kohteessa, jolla se on, IFC-tyyppeineen |
| `entity` | `global_id` | Yksi juurrutettu entiteetti: sen luokka, jokainen literaaliattribuutti ja mihin se viittaa ja mistä siihen viitataan, kukin IFC-attribuutin, STEP-tunnisteen ja luokan kanssa |
| `site` | | Missä rakennus on: tontin viitepituus- ja leveysaste ja korkeus sekä karttamuunnos koordinaattijärjestelmineen (itä- ja pohjoiskoordinaatti, korkeus, kierto ja mittakaava), jos mallissa on sellainen |
| `changed-since` | `since` | Mikä dokumentissa on muuttunut version jälkeen: yksi rivi kunkin version muutosjoukon muutosta kohden tähän versioon asti, tai yksi rivi `whole_file`-merkinnällä kokonaisena tiedostona lähetetylle versiolle; vastataan versioista, joten graafia ei tarvita |

`class` nimeää IFC-luokan, kuten `IfcWall`, ja ottaa mukaan sen aliluokat:
pakollinen kyselylle `elements`, valinnainen muille. Vastauksessa on enintään
10 000 riviä, ja `truncated` kertoo, kun niitä oli enemmän; kysely keskeytetään
10 sekunnin jälkeen. Jokainen kysely alkaa jäsenestä ja tavoittaa mallin
projektin kautta, vain lukee ja ottaa arvonsa parametreina. Versio, jolla ei
ole mallia tai jota käyttäjä ei saa nähdä, vastaa 404, ja versio, jonka mallia
vielä muunnetaan, vastaa 409. Ominaisuusdokumentti ilmoittaa kyselyt kentässä
`ifc_queries`.

## Muutosjoukot

Ehdotettu muutos malliin kulkee BCF 3.0 -asian `bim_snippet`-kenttänä
(ADR 0021): `snippet_type` on `DataregiumIfcChangeSet`, `reference_schema` on
`GET /documents/1.0/ifc-changes/schema`, jonka kuka tahansa saa lukea, ja itse
snippet lähetetään kutsulla `PUT …/topics/{guid}/snippet`, jossa palvelin pitää
sen skeemassa ja vastaa `400` kertoen, mikä on vialla. Uusi projekti sallii
snippet-tyypin; ylläpitäjä lisää sen vanhemman projektin arvoihin.
Muutosjoukko nimeää perustaversionsa, ehdottajansa, tekoälymallin ja
työkalukutsun kun ehdottaja oli tekoäly, sekä muutoksensa, kunkin yhden
instanssin yhteen attribuuttiin. Instanssi nimetään GlobalId:llä ja polulla
juurrutetusta entiteetistä IFC:n attribuuttinimin ja indeksein, ja
STEP-tunnisteellaan vain, kun mikään GlobalId ei tavoita sitä. `set` antaa attribuutille arvon, `add` ja `remove` muuttavat yhtä
aggregaatin jäsentä, ja `copy` pyytää kopion usean jakamasta instanssista, joka
muuten muuttuisi kaikille. Arvo on skalaari, instanssi (`{"step_id": 120}` tai
GlobalId polkuineen), tyypitetty arvo
(`{"type": "IfcLengthMeasure", "value": 3.2}`), luetteloarvo
(`{"enum": "NOTDEFINED"}`) tai näiden lista. Kyvykkyysdokumentti ilmoittaa
muodon nimellä `ifc_changes`. Se, mitä muutokset tekevät mallille, tarkistetaan
ehdotusta kokeiltaessa, seuraavassa vaiheessa; tänään palvelin pitää muodon.

```json
{
  "schema": "https://cde.example/documents/1.0/ifc-changes/schema",
  "base": {"document_id": "…", "version_index": 3},
  "provenance": {"user": "anna", "ai_model": "claude-opus-5-5", "tool_call": "rename_element"},
  "changes": [
    {"guid": "1Xezbq735AdBO_4DerG66G", "attribute": "Name", "op": "set", "old": "Wall 1", "new": "Wall 1b"},
    {"guid": "1Xezbq735AdBO_4DerG66G", "path": "IsDefinedBy[0].RelatingPropertyDefinition.HasProperties[2]",
     "attribute": "NominalValue", "op": "set", "new": {"type": "IfcLengthMeasure", "value": 3.2}}
  ]
}
```

Vain projektin `editor` tai `manager` ehdottaa muutosjoukkoa (ADR 0028):
`contributor`, joka lähettää sellaisen, myös omaan asiaansa, saa vastauksen
`403` syineen, eikä mitään tallenneta, kun taas muuntyyppinen snippet lähetetään
kuten ennenkin. Sama koskee muutosjoukkoa, jonka palvelin ehdottaa jäljempänä.

`delete` poistaa STEP-tunnisteellaan osoitetun instanssin, johon mikään ei viittaa, kuten sellaisen, jota mikään GlobalId
ei tavoita; instanssi, johon jokin vielä viittaa, ohitetaan ja mainitaan kokeilussa. Palvelin ehdottaa itse tällaista
muutosjoukkoa pyynnöllä `POST /documents/1.0/projects/{id}/ifc-unreachable`, jossa versio annetaan kenttinä
`document_id` ja `version_index`: se luo asian, jonka snippet poistaa jokaisen instanssin, jonka version tarkistus
`graph` löytää ulottumattomiin, ja muutosjoukko kokeillaan ja hyväksytään kuten muutkin, joten versio, josta se tuli,
säilyttää instanssit. Vastaus nimeää asian, kuinka monta instanssia se poistaa ja missä kokeilu on; `404`, kun
versiolla ei ole muunnettua mallia, ja `409`, kun mikään siinä ei ole ulottumattomissa. Kyvykkyysasiakirja
luettelee toiminnot kentässä `ifc_changes.ops` ja osoitteen kentässä `ifc_changes.unreachable_url`.

Dataspatiumin kirjoitustyökaluilla tehty muutosjoukko kantaa myös niiden toiminnot kentässä `ops`, ja `ops_form` on
`dataspatium-tools/1`, jotta uudet elementit, poistot ja suhteet tulevat mukaan ehdotukseen. Jokainen toiminto
nimeää työkalunsa kentässä `tool` ja pitää työkalun argumentit rinnallaan, pituudet metreinä:
`create_storeys_and_grid`, `create_wall`, `create_slab`, `create_roof`, `create_opening`, `create_spaces`,
`set_properties`, `set_classification`, `assign`, `transform_elements`, `delete_elements` ja `set_site`. Palvelin
ajaa ne kopiolla sovelluksen omasta koodista (`opencde/ifcgraph/ops.py`), joten samat toiminnot antavat saman mallin
sovelluksessa ja palvelimella, tiedoston yksikössä, ja IfcOpenShellin tekemissä omistajahistorioissa ovat ehdottaja ja
palvelin. Seinä-, laatta-, katto- ja aukkotoimintojen luomat nimetään `new-1`, `new-2` … niiden järjestyksessä, ja
niin nimetään myös jokainen huone, jonka `create_spaces` luettelee. Toiminto nimeää elementin sen GlobalId:llä,
STEP-tunnisteella vain, kun mikään GlobalId ei sitä tavoita, tai tällaisella ref-tunnuksella, ja kerroksen sen
nimellä. `create_wall` antaa seinälle sen keskilinjan `Axis`-esityksenä, ja `create_spaces` tekee seinien rajaamista
huoneista, jotka löydetään samoin kuin raportin `rooms`, kerroksensa tiloja (`IfcSpace`) tiedostosta sellaisena kuin
se on tuossa vaiheessa: kukin saa huoneen ääriviivan seuraavaan kerrokseen asti, `Qto_SpaceBaseQuantities`-suureet
ja fyysiset tilarajat reunansa seiniin ja niissä oleviin oviin ja ikkunoihin; myöhemmin tällaiseen seinään tehty ovi
tai ikkuna rajaa myös tilaa. `changes` saa silloin olla tyhjä: toimintojen rinnalla muutokset
kuvaavat, mitä toiminnot tekevät olemassa oleville instansseille, sellaisena kuin sovellus sen havaitsi,
yhdistämistä varten, ja muutos, jonka toiminnot jo tekivät, lasketaan sovelletuksi. Kyvykkyysdokumentti ilmoittaa
muodon nimellä `ifc_changes.ops_form` ja työkalut nimellä `ifc_changes.ops_tools`.

```json
{
  "schema": "https://cde.example/documents/1.0/ifc-changes/schema",
  "base": {"document_id": "…", "version_index": 3},
  "provenance": {"user": "anna", "ai_model": "claude-opus-5-5", "tool_call": "create_wall,create_opening"},
  "ops_form": "dataspatium-tools/1",
  "ops": [
    {"tool": "create_wall", "storey": "Level 1", "start": [0, 0], "end": [6, 0], "thickness": 0.2, "height": 3},
    {"tool": "create_opening", "wall_id": "new-1", "offset": 1, "width": 0.9, "height": 2.1, "fill": "door"}
  ],
  "changes": []
}
```

Kokeilu soveltaa ensin toiminnot ja sitten muutokset ja laskee molemmat kenttään `change_count`. Toiminto, jota ei
voida soveltaa, on lajin `op` huomautus, jossa on sen indeksi (`op`) ja `tool`, sovelluksen koodin sanoin, jotka
voivat lainata sen argumentteja ja tiedostoa; sen jälkeisiä toimintoja ja muutoksia ei sovelleta, kuten ei
sovelluksessakaan. Kokeilu antaa myös kentän `created`, kunkin luodun elementin GlobalId:n sen ref-tunnuksen
mukaan, jotta asiakasohjelma voi yhdistää omansa, ja kentän `notes`, mitä toiminto ei voinut tehdä tiedoston
skeemassa, kuten karttamuunnosta IFC2X3:ssa.

Kun IFC-LPG-moduuli on käytössä, palvelin kokeilee jokaista muutosjoukkoa sitä
lähetettäessä: työprosessi soveltaa muutokset perustaversion tiedostoon, tulos
käy läpi lähetyksen tarkistukset (IFC-skeema, buildingSMARTin säännöt ja
projektin IDS-dokumentit), ja kokeilu on `clean`, kun jokainen muutos voitiin
soveltaa eikä yksikään huomautus ole uusi perustaversion raporttiin
verrattuna, muuten `issues`.
`GET /bcf/3.0/projects/{id}/topics/{guid}/ifc-proposal` antaa tilan, montako
muutosta sovellettiin ja uudet huomautukset, kunkin kuten version raportissa;
muutos, jota ei voitu soveltaa, on lajin `proposal` huomautus, joka kertoo
syyn lainaamatta tiedostoa. Uusi snippet korvaa kokeilun, ja kokeilu poistuu
asian mukana. Kyvykkyysdokumentin `ifc_changes` kertoo, kokeillaanko
muutosjoukkoja (`tried`) ja missä kokeilu on (`proposal_url`).

`GET /documents/1.0/documents/{id}/ifc-proposals` luettelee dokumenttia
vasten kokeillut muutosjoukot projektin jäsenelle, uusin ensin: rivillä ovat
asian guid, otsikko ja kuvauksen 200 ensimmäistä merkkiä, kokeilun tila,
perustaversio, montako muutosta joukossa on, kuka sen ehdotti, milloin
kokeilu päättyi, versio joksi se tuli, jos se hyväksyttiin, sekä kokeilun
(`proposal_url`) ja sen hyväksynnän (`approve_url`) osoitteet. Ehdotus nimeää
perustansa siitä hetkestä, kun se asetetaan jonoon, joten luettelossa se on
ennen kokeilua ja kun kokeilu epäonnistui. `$top` ja `$skip` selaavat
luetteloa kuten BCF-luetteloissa; palvelimen katkaisemassa luettelossa on
`X-Total-Count` ja `Link: <…>; rel="next"`. `404`, kun jäsen ei saa nähdä
dokumenttia, ja kun IFC-LPG-moduuli ei ole käytössä. Kyvykkyysdokumentti
antaa osoitteen nimellä `ifc_changes.ifc_proposals_url`.

`manager` hyväksyy puhtaan kokeilun kutsulla `POST …/ifc-proposal/approve`:
sovellettu tiedosto tulee perustadokumentin seuraavaksi versioksi, jonka
metatiedoissa ovat `base_version_index`, `change_set_id` (asian guid),
`proposed_by` ja `approved_by` sekä tekoälymalli ja työkalukutsu, kun
ehdottaja oli tekoäly; vastaus on uusi versio sellaisena kuin Documents API
sen antaa, ja se muunnetaan ja tarkistetaan kuten lähetys. Asia saa
kommentin, jossa on version osoite, näkymän (viewpoint), joka valitsee
muuttuneet elementit, ja tilan `Closed`, kun projektilla on se arvo. `412 version_conflict` kertoo, että dokumentti on edennyt perustan
jälkeen; `409`, ettei kokeilu ole puhdas tai se on jo hyväksytty. Tekoäly
vain ehdottaa: hyväksyntä on ihmisen.
Kun projektilla on tiimejä, kokeilu luettelee kentässä `teams` ne tiimit, joiden
osaa mallista muutosjoukko koskee: sen, mihin tiimin IDS-asiakirjan määrittelyt
kohdistuvat, perusversion tiedostossa tai muutetussa. Yhden tiimin osaa koskevan
muutosjoukon hyväksyy tiimin vastuuhenkilö yksin, ei `manager`; useamman tiimin osia
tai ei kenenkään osaa koskevan hyväksyy `manager`, samoin sellaisen, jonka osia ei
löydetty (`teams_error`).

Kun dokumentti on edennyt perustan jälkeen, palvelin yhdistää: välissä
olevien versioiden muutokset, kukin hyväksytty muutosjoukosta, verrataan
attribuutti kerrallaan ehdotuksen muutoksiin. Jos mikään ei törmää,
muutosjoukko kokeillaan heti uudelleen uusinta versiota vasten ja hyväksytään
sitä vasten, jolloin uuden version perusta on uusin. Jos jokin törmää tai
välissä oleva versio lähetettiin kokonaisena tiedostona, vastaus on
`412 version_conflict` ja törmäävät attribuutit kentässä `conflicts`
(`#123.Name`, tai GlobalId, polku ja attribuutti; `*` kokonaiselle
tiedostolle), jotta asiakas yhdistää kolmisuuntaisesti ja lähettää uudelleen.

Vertailtavina ovat instanssit, eivät asiakasohjelmien kirjoittamat avaimet:
jokainen muutos ratkaistaan siinä versiossa, jossa se tehtiin, ja nimetään
kanonisella polullaan (IFC-LPG:n `ifc_lpg.paths`), joten kaksi muutosta, jotka
saavuttavat saman jaetun instanssin eri GlobalId:stä, törmäävät silti, ja
`conflicts` nimeää instanssin tuolla polulla. Sen rinnalla `conflict_details`
antaa törmäyskohtaisesti `key`, ehdotuksen omat `guid`, `path` tai `step_id`,
`attribute` ja `op`, mitä perusversiossa oli (`base`), mitä uusimmassa
versiossa on (`theirs`), mitä ehdotus asettaa (`ours`), kaikki muutosjoukon
arvomuodossa, sekä välissä olevan version, joka muutti sitä (`version_index`);
arvo, jota ei voitu lukea, on `null`. Asiakasohjelma antaa ihmisen valita
törmäyskohtaisesti, lähettää uuden snippetin uusimpaan versioon ja hyväksyy
uudelleen. Asiakasohjelma, joka ei voi leikata yksittäistä muutosta
toiminnoistaan, lähettää ne uudelleen ja antaa avaimet, joista se luopuu,
kentässä `keep_theirs` niin kuin `conflicts` ne nimesi: palvelin kokeilee
silloin muutosjoukkoa dokumentin uusinta versiota vasten ja palauttaa kullekin
näistä attribuuteista uusimman version arvon toimintojen ja muutosten jälkeen.

Toisen version päälle rakennettu versio on solmu, jolla on vanhempi:
`parent_version_index` ja linkki vanhempaan versioon, muutosjoukosta
hyväksytyllä versiolla ja lähetyksellä, joka antoi `base_version_index`:n.
Muutosjoukosta hyväksytty versio kantaa myös `approved_by`:n, `change_set_id`:n
(asian guid) ja itse muutokset, jotka
`GET /documents/1.0/documents/{id}/versions/{index}/ifc-changes` antaa skeeman
muodossa perustan sekä ehdottajan ja hyväksyjän kanssa; kokonaisena
tiedostona lähetetty versio vastaa siellä `404`. Jokainen versio on yhä
kokonainen tiedosto, ladattavissa kuten ennen; `opencde ifc-lpg prune` poistaa
vanhempien versioiden graafit, koska pääversio ja muutosjoukkojen ketju
kertovat, mikä muuttui.

## Kahden version vertailu

Jäsen vertaa kahta IFC-versiota elementti kerrallaan samalla
bearer-tunnuksella kuin Documents API: versiota saman dokumentin toiseen
versioon tai parametrilla `?other_document_id=` projektin toisen dokumentin
versioon. Työprosessi parittaa juurrutetut entiteetit GlobalId:n mukaan ja
vastaa kentillä `added` (vain toisella on ne), `removed` (vain tällä on ne) ja
`changed` (molemmissa, mutta attribuutit eroavat); jokainen elementti nimetään
GlobalId:llä, luokalla, nimellä ja kerroksella, ja muuttuneesta luetellaan
eroavat polut vanhoine ja uusine arvoineen: suora attribuutti nimellään,
ominaisuus muodossa `Pset.Property`, `ObjectPlacement` (4×4-matriisi),
`Representation` (muodon sormenjälki), `Container` (kerros) ja `Type`.
Suhteet ja ominaisuusjoukot sulautetaan elementteihin, joihin ne kuuluvat, ja
kukin luettelo pitää enintään 10 000 elementtiä. Ero lasketaan pyynnöstä eikä
sitä koskaan tallenneta; suuri malli vie hetken. Version sivu tarjoaa saman
vertailun luetteloina, ja kyvykkyysdokumentti ilmoittaa sen nimellä
`ifc_diff`.

```http
GET /documents/1.0/documents/{document_id}/versions/{version_index}/ifc-diff/{other_index}
```

## Törmäystarkastus

Jäsen vertaa projektin kahta IFC-dokumenttiversiota törmäysten varalta samalla
bearer-tunnisteella kuin Documents API:
`POST /documents/1.0/projects/{project_id}/ifc-clash` kahdella versiolla,
tilalla (`intersection`: elementit, jotka menevät toistensa sisään syvemmälle
kuin `tolerance`; `clearance`: elementit lähempänä toisiaan kuin `clearance`,
molemmat metreinä) ja halutessa kummankin puolen IFC-luokilla. Tarkastus ajetaan
työprosessissa muunnosjonon takana; vastauksen `url` antaa raportin, hetken
kuluttua `done` tai `failed`. Jokainen törmäys nimeää molemmat elementit
(dokumentti, versio, STEP-id, GlobalId, luokka, nimi, kerros), lajinsa, syvyyden
tai etäisyyden ja pisteen, jossa se mitattiin, siinä muodossa, jonka
Dataspatiumin oma törmäysydin kirjoittaa, joten sovellus näyttää palvelimen
tuloksen kuin omansa. `POST …/ifc-clash/{id}/topics` tekee valituista
törmäyksistä BCF-aiheita, kullekin oma viewpoint, vain pyynnöstä.
Kyvykkyysdokumentti ilmoittaa tarkastuksen nimellä `ifc_clash`, kun ylläpitäjä on
asettanut `OPENCDE_IFC_LPG_CLASH_ENABLED=true`; raportti säilyttää enintään
`OPENCDE_IFC_LPG_CLASH_MAX_CLASHES` törmäystä.

```http
POST /documents/1.0/projects/{project_id}/ifc-clash
{"a": {"document_id": "…", "version_index": 1, "types": ["IfcWall"]},
 "b": {"document_id": "…", "version_index": 2},
 "mode": "intersection", "tolerance": 0.001}
```

## Rakennus toiseen malliin

Yhden mallin rakennus tulee toisen projektin malliin sen asiakirjan seuraavana
versiona; kumpikaan malli ei muutu. Malli A on tämän projektin versio, malli B
minkä tahansa sellaisen projektin versio, jonka jäsen kutsuja on, ja molempien on
oltava muunnettuja, samalla skeemalla ja pituusyksiköllä.
`POST /documents/1.0/projects/{project_id}/ifc-merge/report` kertoo kummankin
projektin jäsenelle, mitä tapahtuisi: kuinka monta objektia ja instanssia tulee
mukana, objektit, joilla on molemmissa sama GlobalId (`collisions`, kentillä `same`
ja voimassa oleva `choice`), suhteet, jotka jätetään pois, koska ne osoittavat vain
rakennuksen ulkopuolelle, sekä A:n kontekstit ja sijoitukset, joita käytetään. Kun
tällaisen objektin sisältö eroaa, sille tehdään valinta: `a` pitää A:n objektin, `b`
panee B:n objektin sen tilalle ja `new` pitää molemmat, B:n objektin uudella
GlobalId:llä; `default` antaa yhden valinnan kaikille.
Yksikkö, jonka lajia A:lla ei ole, kuten pinta-alayksikkö, tulee mukaan A:n yksiköihin
ja näkyy kentässä `units_added`; molemmilla olevan lajin yksikön on oltava sama.

Projektin `manager` käynnistää yhdistämisen kutsulla `POST …/ifc-merge` samalla
rungolla. Se ajetaan työnä muunnosjonossa, ja vastauksen `url` antaa sen tilan:
`conflict` objekteineen, joilta valinta vielä puuttuu, `failed` syineen tai `done`
kentällä `version_index`, A:n asiakirjan uusi versio. Yhdistetty malli tarkistetaan
ensin A:ta ja B:tä vasten, eikä siinä saa olla huomautusta, jota niissä ei ole; sitten
se kirjoitetaan seuraavaksi versioksi, A:n versio vanhempanaan ja metatiedoissaan
`merged_from_document`, `merged_from_version` ja `merged_building`, ja muunnetaan ja
tarkistetaan kuten lähetys. A:n version on oltava asiakirjan uusin (muuten 412
`version_conflict`). Kyvykkyysdokumentti ilmoittaa sen nimellä `ifc_merge`.

Jos B:n skeema tai pituusyksikkö ei ole A:n, raportti kertoo sen (422), ja
`editor` tai `manager` valmistelee ensin B:n kutsulla `POST …/ifc-merge/prepare`
kentillä `base` ja `other`: työ tekee B:stä kopion, joka on siirretty A:n skeemaan ja
jonka pituudet ovat A:n yksikössä. Kun työ on `done`, sen `merge_id` kentässä
`other.prepared` panee kopion B:n paikalle raportissa ja yhdistämisessä hetkeen
`expires_at` asti, vuorokauden ajan; sen jälkeen palvelin poistaa sen. Muuta eroavaa
yksikköä ei muunneta, ja työ epäonnistuu sen vuoksi.
Se, mille A:n skeemassa ei ole vastinetta, kuten IFC2X3:n IfcWindowStyle
IFC4X3:ssa tai IFC2X3:n vaatimat omistajahistoriat, vie työn tilaan `conflict`:
`report.problems` luettelee jokaisen ongelman avaimella `key`, sen, mitä se koskee,
ja sen vaihtoehdot `options` (`type`, `proxy`, `leave_out`, `polyline`, `owner`,
`virtual`, `dated`, `assignment`, `context`), ja uusi `POST …/ifc-merge/prepare` kentällä
`resolutions`, valittu vaihtoehto avainta kohden, tekee kopion. Kopio tarkistetaan
sitten B:tä vasten: kopiota, jossa on huomautus, jota B:llä ei ollut, ei tehdä, ja
työ on `failed` niine huomautuksineen kentässä `report.new`.

```http
POST /documents/1.0/projects/{project_id}/ifc-merge
{"base": {"document_id": "…", "version_index": 3},
 "other": {"project_id": "…", "document_id": "…", "version_index": 1},
 "building": "3AMeTOOFsdVLZuNV0$27s5", "choices": {"1Xezbq735AdBO_4DerG66G": "b"}}
```

## Työkopio

Arkiston rinnalla palvelin voi pitää työkopiota: toista graafia, Memgraphia
muistissa, johon jokaisen dokumentin pääversion malli tuodaan myös
(ADR 0024). Arkisto säilyttää jokaisen version ja pysyy totuutena; työkopio
pitää yhden mallin dokumenttia kohden, viimeksi muunnetun, ja vastaa sen
nimettyihin kyselyihin, jotta suuri malli luetaan muistista.
`OPENCDE_WORKCOPY_GRAPH_URI` nimeää sen (`OPENCDE_WORKCOPY_GRAPH_DIALECT`,
`_USER`, `_PASSWORD` ja `_DATABASE` sen rinnalla); peite
`docker/compose.workcopy.yaml` lisää Memgraphin mihin tahansa pinoon
julkaisematta sitä. Muunnos tuo samat tietueet molempiin graafeihin IFC-LPG:n
murreriippumattomassa muodossa, korvaa dokumentin aiemman mallin työkopiossa
eikä koskaan epäonnistu työkopion takia: kopio, jota ei voitu tehdä, merkitään
siellä tilaan `failed`, eikä arkistoon kosketa. Malli, jota arkistossa ei enää
ole, poistuu työkopiosta seuraavalla siivouskierroksella. `GET …/ifc-queries`
kertoo kentässä `workcopy`, onko version malli siellä, `/readyz` raportoi
työkopion tilan olematta siitä riippuvainen, ja kyvykkyysdokumentti kertoo
kentässä `ifcgraph.workcopy`, onko sellainen määritetty.

```sh
# .env: COMPOSE_FILE=docker/compose.yaml:docker/compose.local.yaml:docker/compose.workcopy.yaml
docker compose up -d
```

## Missä rakennusosat ovat, ja geometria

Muunnoksen jälkeen palvelin ajaa IFC-LPG:n geometriatyöläisen kerran
tiedoston yli (`python -m ifc_lpg.spatial`; `OPENCDE_IFC_LPG_SPATIAL`,
oletuksena päällä lisäosan kanssa): IfcOpenShell rakentaa jokaisen
rakennusosan muodon, ja työläinen kirjoittaa laatikon rakennusosaa kohti
projektikoordinaateissa sekä meshit, jokaisen jaetun meshin kerran. Laatikot
menevät graafiin pisteinä `bbox_min`, `bbox_max` ja `bbox_centre` rakennusosan
`Entity`-solmulle, ja `bbox_centre` saa pisteindeksin arkistossa ja
työkopiossa, jotta kysely löytää sen, mikä on lähellä pistettä tai tilavuuden
sisällä; `Model` kantaa kentät `spatial_at`, `spatial_products` ja
`spatial_failed`. Tietueet säilytetään tallennustilassa, ja
`GET …/ifc-geometry` rakentaa niistä binäärisen glTF:n, kun sitä ensimmäisen
kerran pyydetään: jokainen jaettu mesh kerran, solmu rakennusosaa kohti, joka
instantioi sen rakennusosan matriisilla, nimettynä GlobalId:llä ja luokka,
STEP-tunnus ja kerros `extras`-kentässä, kerroskohtaisen solmun alla, sekä
juuri, joka kääntää mallin IFC:n Z-ylös-suunnasta glTF:n Y-ylös-suuntaan.
`lod=box` antaa sen sijaan laatikot, yhden kuution, jonka jokainen rakennusosa
instantioi, muutaman tavun kukin; `classes` (IFC-luokat pilkuin eroteltuina)
ja `storey` (GlobalId) valitsevat rakennusosat. Tiedosto säilytetään ja sen
mukana tulee mallin ja suodattimien `ETag`, joten `If-None-Match` saa
vastauksen `304`. Geometria-ajo ei koskaan kaada muunnosta: jos se
epäonnistuu, malli merkitsee `spatial_error`-kentän ja reitti vastaa `404`;
kun versiota vielä muunnetaan, `409`. Kyvykkyysasiakirja ilmoittaa sen nimellä
`ifc_geometry`.

```http
GET /documents/1.0/documents/{document_id}/versions/{version_index}/ifc-geometry?lod=full&classes=IfcWall,IfcSlab
```

```cypher
// Rakennusosat kahden metrin säteellä seinästä, samassa mallissa
MATCH (w:Entity:IfcWall {GlobalId: $guid})
MATCH (e:Entity {model_id: w.model_id}) WHERE e.bbox_centre IS NOT NULL AND e <> w
  AND point.distance(e.bbox_centre, w.bbox_centre) < 2.0
RETURN e.GlobalId, e.ifc_class, point.distance(e.bbox_centre, w.bbox_centre) AS distance ORDER BY distance
```

## Kyselyt Dataspatiumista

[Dataspatium](https://github.com/marwiss/Dataspatium), tämän palvelimen
kanssa kehitettävä selainasiakas, ajaa Cypheriä tätä graafia vasten
Neo4j-lähteensä kautta Boltilla (WebSocket Bolt-portissa), kun ylläpitäjä
avaa tietokannan, kuten kehityspäällyste tekee osoitteessa `127.0.0.1:7697`.
Sen Dataregium-työtila käyttää yllä olevia malleja (mallit, luokat,
komponentit `GlobalId`-tunnuksella, uusin valmis malli asiakirjaa kohti);
kyselyt ovat Dataspatiumin dokumentaatiossa (`docs/grafer.md`). Tuotantopalvelin
ei julkaise Boltia; hallintarajapinnan graafikysely
(`OPENCDE_GRAPH_QUERY_ENABLED`, [client-guide.md §7](client-guide.md)) antaa
järjestelmänvalvojille lukevan Cypherin ilman porttia. Sovellus
myös piirtää graafin korttiinsa IFC-LPG tuon kyselyn kautta tai Boltilla.

## Rajat ja tila

- Yksi muunnos kerrallaan; suuret mallit jonottavat. Esimerkkimalli (248
  entiteettiä) tuodaan noin sekunnissa; 200 MB:n arkkitehtimalli vie
  minuutteja.
- `Conversion` kantaa kentät `state`, `entities`, `relationships`,
  `skipped`, `lossless`, `geometry`, `schema`, `ifc_project_guid`, aikaleimat ja `error`.
  Järjestelmänvalvojat voivat tarkastella sitä Neo4j Browserissa tai
  Memgraph Labissa:
  `MATCH (c:Conversion) RETURN c.file_name, c.state, c.entities, c.error`.
- Projektin poisto poistaa sen mallien entiteetit samalla.
- Malli palautuu identtisenä molemmista tietokannoista 224 496 instanssiin ja 19 megatavuun
  asti kaikissa mitatuissa muodoissa. Suurempia ei ole kokeiltu.
