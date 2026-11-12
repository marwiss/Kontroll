# IFC-LPG

Valkvæða IFC-LPG-einingin breytir upphlöðnu IFC-líkani í grafgögn, svo að
einingar BCF-viewpoints megi tengja við byggingarhlutana sem þær vísa á, og
svo að spyrja megi um líkanið í Cypher við hlið málanna og skjalanna.

Kveiktu á henni með `OPENCDE_IFC_LPG_ENABLED=true` og settu upp aukapakkann
`ifc-lpg` (`uv sync --extra ifc-lpg`). Docker-myndin inniheldur aukapakkann
sjálfgefið (`ARG OPENCDE_EXTRAS` í Dockerfile), sem meira en tvöfaldar stærð
hennar (um 680 MB, eða 1,1 GB með reglum buildingSMART, á móti 300 MB); byggðu með `--build-arg OPENCDE_EXTRAS=`
fyrir grennri mynd án IfcOpenShell þegar einingin er áfram óvirk.

Fram í nóvember 2026 hét einingin IFC-graph. Stillingar hennar hétu `OPENCDE_IFCGRAPH_*`
og skipunin `opencde ifcgraph`, og hvort tveggja virkar enn; atvikaskrá þjónsins
og `opencde doctor` nefna gömlu stillingarnar sem hann fær.

Umbreytingin, ritun skrár og prófanirnar koma úr safninu
[IFC-LPG](https://github.com/marwiss/IFC-LPG), sem Dataregium setur upp úr
geymslu þess við fasta útgáfu (commit), og README-skrá þess lýsir því hvernig
líkan er geymt í grafinu. Eigið ferli þjónsins notar þann hluta sem þarf ekki
IfcOpenShell; aukapakkinn `ifc-lpg` bætir við vinnsluferlunum sem þurfa það.

## Hvað gerist við upphal

1. Documents API-upphali lýkur (eða skrá er hlaðið upp frá valsíðunni, eða
   BCF-verkefnisskjal er póstað) með `.ifc`- eða `.ifczip`-heiti.
2. Þjónninn býr til `Conversion`-færslu (staða `queued`) tengda verkefninu og
   hefur umbreytingu í bakgrunni, eina í einu.
3. Sérstakt vinnuferli (`python -m ifc_lpg.worker`) les skrána. Það keyrir með tímamörkum
   (`OPENCDE_IFC_LPG_TIMEOUT_SECONDS`, 15 mínútur), vistfangarýmismörkum á
   POSIX (`OPENCDE_IFC_LPG_MEMORY_MB`, 4 GiB) og hámarki eininga
   (`OPENCDE_IFC_LPG_MAX_ENTITIES`). Hrun eða frysting drepur vinnuferlið,
   ekki þjóninn. `.ifczip` er pakkað upp innan stærðarmarka upphalsins.
4. Færslurnar eru fluttar inn í lotum með `UNWIND … CREATE` (flytjanlegt
   Cypher, ekkert APOC). `Conversion` endar í stöðunni `done` með talningum og
   `IfcProject`-guid, eða `failed` með villu.
5. Umbreyting sem stöðvaður þjónn skildi eftir byrjar upp á nýtt: sú sem bíður í röð um leið og þjónninn er
   kominn aftur, sú sem var í gangi þegar tvöföld tímamörk eru liðin, því að hún gæti verið í gangi í öðru þjónsferli.

`opencde seed` umbreytir sýnilíkaninu á sama hátt þegar einingin er virk.

## Prófun upphalaðra skráa gagnvart IFC-skemanu

Sérhver `.ifc`- eða `.ifczip`-skrá sem hlaðið er upp sem útgáfu skjals er einnig
prófuð gagnvart IFC-skemanu, með sama sannprófara og prófar skrifaða skrá
([Að skrifa líkan til baka](#að-skrifa-líkan-til-baka)): tag og fjöldi eiginda,
upptalningar, andhverf eigindi, GlobalId og reglur EXPRESS-skemans. Prófunin
keyrir í bakgrunni á undan umbreytingunni, í vinnsluferli með sömu mörkum. Sjálfgefið
stöðvar hún aldrei upphal: skráin er vistuð eins og hún kom, hvað sem prófunin
finnur; verkefni getur valið annað ([neðar](#að-hafna-skrám-með-villum-og-prófa-skrá-fyrirfram)).
Verkefnisskjal BCF er ekki prófað, þar sem það hefur engin lýsigögn.
`OPENCDE_IFC_LPG_VALIDATE_UPLOADS=false` slekkur á prófuninni.

Niðurstaðan er í lýsigögnum útgáfunnar, sem sérhver biðlari Documents API getur lesið:

| Færsla | Tegund | Gildi |
|---|---|---|
| `ifc_validation_status` | `string` | `pending` þar til skráin hefur verið prófuð, síðan `passed`, `warnings` þegar hver athugasemd er viðvörun, `issues` þegar að minnsta kosti ein er villa, eða `unknown` þegar ekki tókst að prófa hana |
| `ifc_validation_issues` | `integer32` | Hve margar athugasemdir skráin hefur |
| `ifc_validation_checked_at` | `date-time` | Hvenær hún var prófuð |
| `ifc_validation_ruleset` | `string` | Með hverju hún var prófuð, eitt gildi fyrir hverja prófun |
| `ifc_validation_report` | `url` | Hvar skýrslan er |

Skýrslan er viðbót við Documents API. Sérhver meðlimur verkefnisins fær hana með
sama Bearer-tóka:

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

Hún telur upp allt að 10.000 athugasemdir, hverja með tilviki sínu og, fyrir eind
með rót, GlobalId hennar, svo að líkansýn geti fundið hlutinn. `kind` segir hvað
fann athugasemdina: `schema`, `entity_rule`, `simpletype_rule` eða `global_rule`
IFC-skemans, eða `gherkin` fyrir eina af reglum buildingSMART, og kóði hennar er
í `rule`. `checks` heldur prófununum aðskildum. Skilaboð geta vitnað í línu úr
skránni og eru stytt við 1.000 stafi. Síða
útgáfunnar í vafranum sýnir fyrstu 100 athugasemdirnar og býður alla skýrsluna sem
skrá.

Margar skrár brjóta þegar einhverja reglu þegar þær koma úr forriti sínu: 12 af 26
sýnidæmum gera það, eitt frá Tekla með 5.711 athugasemdir. Að prófa sýnidæmi og
skrifað afrit þess tók 3 til 66 sekúndur samanlagt.

### ifc-gherkin-rules frá buildingSMART

Þegar `OPENCDE_IFC_LPG_GHERKIN_ENV` vísar á umhverfi fyrir þær eru upphöl
einnig prófuð gagnvart `ifc-gherkin-rules` frá buildingSMART: þeim
staðalbundnu reglum og þeirri venju greinarinnar sem sannprófunarþjónusta
buildingSMART prófar umfram skemað (ADR 0012).
Þær keyra á eftir skemaprófuninni, í sams konar vinnsluferli með sömu mörkum,
og eins og eigin prófanir reglusafnsins keyra þær: með behave og IfcOpenShell
0.8.6, sem CI reglusafnsins notar. Á 722 prófunarskrám reglusafnsins gefur það
þá niðurstöðu sem prófanir þess búast við fyrir hverja einustu.

Reglurnar fá eigið umhverfi, þar sem eitt af hjálparföllum þeirra virkar ekki
með IfcOpenShell 0.9, sem Dataregium notar.
`python -m ifc_lpg.gherkin_install <mappa>` býr það til úr festum
niðurhölum, og hvert þeirra er borið saman við SHA-256 sitt: reglusafnið við
ákveðið commit, smíð IfcOpenShell af 0.8.6 fyrir verkvanginn og Python-pakkana
með tætigildum sínum. Tvær litlar skrár frá IFC-LPG koma í stað Django-hluta
reglusafnsins, sem skrifa aðeins niðurstöður í gagnagrunn
sannprófunarþjónustunnar.
Útgefna myndin sleppir þeim, þar sem þær bæta við um 425 MB. Myndin með merkið
`-gherkin`, eins og `latest-gherkin` eða `3.0.0-gherkin`, hefur umhverfið í
`/opt/gherkin` og lætur `OPENCDE_IFC_LPG_GHERKIN_ENV` vísa á það, eins og mynd
sem er smíðuð með `--build-arg OPENCDE_GHERKIN=1`. Með docker compose velur
`OPENCDE_IMAGE_TAG` eða `OPENCDE_GHERKIN=1` í `.env`.

Það sem regla finnur er athugasemd af tegundinni `gherkin`, með kóða reglunnar,
eins og `IFC106`, og alvarleikanum `error` eða `warning`. Reglur um venju
greinarinnar vara aðeins við, og skrá þar sem allar athugasemdir eru viðvaranir
fær stöðuna `warnings`, þar sem sannprófunarþjónusta buildingSMART telur slíka
skrá gilda. Regla sem kastaði undantekningu í stað þess að finna eitthvað hefur
enga niðurstöðu og er talin upp undir `rules_not_run` í prófun sinni. Ef
reglurnar geta alls ekki keyrt verður prófun þeirra `failed`, og prófun
skemans stendur ein.

Reglurnar taka lengri tíma en skemaprófunin: á átta sýnilíkönum frá 5 sekúndum
fyrir það minnsta til um 5 mínútna fyrir það stærsta, og frá hálfri mínútu upp í
tvær fyrir flest.

### Information Delivery Specifications (IDS)

Upphal er líka prófað gegn hverju IDS-skjali verkefnisins: skjali þar sem
nýjasta útgáfan ber nafn sem endar á `.ids`, mest 50
(ADR 0015).
Prófun IFC-LPG les hvert IDS á öruggan hátt og afhendir það IfcTester frá
IfcOpenShell, sama prófara og Dataspatium keyrir í vafranum, svo að hvort
tveggja gefi sömu niðurstöðu. Hún keyrir á eftir hinum prófununum, í sams konar
vinnsluferli með sömu mörkum. Ný útgáfa IDS-skjals lætur prófa aftur nýjustu útgáfu hvers IFC-skjals í verkefninu, í mesta lagi 500, svo
að skýrsla hennar fylgi kröfunum eins og þær eru núna; eldri útgáfur halda skýrslunni sem þær höfðu.

Hver krafa sem eining uppfyllir ekki verður athugasemd af gerðinni `ids`, með
alvarleikann `error`, auðkenni eða heiti forskriftarinnar í `rule` og
IDS-skjalið í `document_id`. Það sama á við um áskilda forskrift sem á ekki við
neitt í skránni og einingu sem bönnuð forskrift á við. Prófunin `ids` í
skýrslunni telur upp skjölin sem hún notaði, með útgáfu, og hverja forskrift
með notkun hennar, stöðu (`passed`, `failed` eða `not applicable`), hve mörgum
einingum hún á við og hve margar athugasemdir hún gaf. IDS-skjal sem ekki er
hægt að lesa, til dæmis með DTD, er talið upp undir `rules_not_run` ásamt
ástæðunni, og hin eru samt prófuð. Síða útgáfunnar sýnir forskriftirnar í
sérstakri töflu.

### buildingSMART Data Dictionary (bSDD)

Með `OPENCDE_BSDD_ENABLED=true` er upphal líka prófað gegn Data Dictionary frá buildingSMART, á eftir IDS-prófuninni.
Vinnsluferli les tilvísanir skrárinnar þangað: hverja `IfcClassificationReference` þar sem `Location` er bSDD-URI,
eins og `https://identifier.buildingsmart.org/uri/molio/cciconstruction/1.0/class/L-BD`, eða þar sem `Identification`
(`ItemReference` í IFC2X3) er kóði í orðabókinni sem URI í `Location` hennar eða í flokkun hennar vísar á, ásamt
hlutunum sem hún er á; og eiginleika hvers eiginleikasafns sem heitir `Pset_…` eða `Qto_…`. Þjónninn spyr síðan API
bSDD á `OPENCDE_BSDD_API_URL` (`https://api.bsdd.buildingsmart.org`) um hvert URI, með tímamörkum á hverri spurningu
(`OPENCDE_BSDD_TIMEOUT_SECONDS`, 10 sekúndur) og tveimur endurtekningum þegar bSDD svarar 429 eða 5xx, og geymir hvert
svar í minni í sólarhring (`OPENCDE_BSDD_CACHE_SECONDS`, 86400; 0 spyr í hvert sinn). Ekkert sem skráin nefnir er
sótt: URI fer til API bSDD sem færibreyta, og URI á öðrum hýsli en `identifier.buildingsmart.org` er tilkynnt í
staðinn. Prófunin er sjálfgefið af, þar sem hún sendir URI skrárinnar og heiti eiginleikasafna hennar til bSDD; í
framleiðslu verður vistfangið að vera https.

Allt sem hún finnur er viðvörun af gerðinni `bsdd`, með flokkunartilvísunina eða eiginleikasafnið í `step_id`,
GlobalId eins af hlutunum sem tilvísunin eða safnið er á í `global_id` og flokk þess hlutar í skilaboðunum:

- flokkunartilvísun þar sem bSDD þekkir ekki flokkinn eða eiginleikann, með orðabókina í `rule` og eigindið sem nefnir
  hann í `attribute`; líkan getur notað orðabók sem bSDD hefur ekki gefið út;
- í skrá í IFC 4.3, eiginleikasafn sem IFC-orðabók bSDD (`buildingsmart/ifc/4.3`) hefur ekki, eða eiginleiki sem hún
  telur ekki upp í því safni, með safnið og eiginleikann í `attribute`, eins og `Pset_WallCommon.Colour`.

bSDD gefur aðeins út þessa einu IFC-orðabók, svo eiginleikasöfn í skrá í IFC4 eða IFC2X3, sem skemu þeirra skilgreina
á annan hátt, eru ekki prófuð; og `Reference`, sem IFC 4.3 gefur nær hverju eiginleikasafni og bSDD sleppir úr þeim
öllum, er ekki tilkynnt. `ruleset` prófunarinnar nefnir hýsil bSDD og orðabækurnar sem skráin var prófuð gegn. Hún les
í mesta lagi 1.000 tilvísanir og 500 eiginleikasöfn, og viðvörun segir til þegar skrá hefur fleiri. Þegar ekki næst í
bSDD, eða það svarar ekki eins og API þess gerir, er prófunin `failed` með ástæðunni í `error`, og hinar prófanirnar
standa: að ekki náist í bSDD er aldrei villa í líkaninu. Forprófunin og prófun breytingasafns gera líka prófunina, og
getuskjalið segir hvort hún er á, sem `bsdd` í `ifc_validation`.

### Herbergin á hverri hæð

Með `OPENCDE_ROOMS_ENABLED=true` fær skýrsla upphals, forprófunar og prófunar líka herbergin á hverri hæð, fundin út
frá veggjum hennar eins og Dataspatium finnur þau: vinnsluferli keyrir afrit af kóða appsins með IfcOpenShell og
shapely, á eftir prófununum og með sömu mörkum. Miðlína veggjar er `Axis`-framsetning hans, sem veggirnir sem
Dataspatium býr til hafa, eða annars langás fótspors búks hans; endarnir eru tengdir saman innan helmings þykkasta
veggjar hæðarinnar að viðbættum 0,05 m, og þær miðlínur sem loka minnst 0,5 m² og 0,5 m breiðu svæði mynda herbergi.
`rooms` í skýrslunni hefur hverja hæð, í hæðarröð, með:

- `rooms`: `index` hvers herbergis á hæðinni, `area` þess (m²) og `perimeter` (m) eftir miðlínunum, GlobalId fyrir
  `walls` þess og `neighbours` þess eftir vísi;
- `external`: veggirnir meðfram ytri hlið herbergjanna, hver með `global_id`, `name`, `length` sína þar og áttina sem
  hann snýr að (`facing`, `N`, `NE` … `NW`), með norður úr kortavörpuninni, annars `TrueNorth`, annars y-ás
  líkansins, eins og `north` segir (`map`, `true_north` eða `model`);
- `dangles` og `dangling_walls`: lausu veggendarnir, `[x, y]` í metrum í grunnfleti líkansins, og veggir þeirra;
- `closed`: hvort hæðin hefur herbergi og engan lausan enda;
- `walls`, `unread` og `unread_walls`: hve marga veggi hæðin hefur, og hve margir og hverjir gáfu enga miðlínu;
- `tolerance`: hve langt, í metrum, tveir endar mega vera hvor frá öðrum og samt tengjast saman.

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

Herbergin eru sérstakur hluti og aldrei athugasemd: þau breyta hvorki stöðu né fjölda, verkefni sem hafnar skrám með
villum hafnar aldrei skrá vegna herbergja hennar, og prófun er `clean` eða `issues` hvernig sem herbergi hennar eru,
en þau eru herbergi skrárinnar sem breytingunum var beitt á. Síða útgáfunnar sýnir eina línu fyrir hverja hæð með
veggjum. Listarnir eru styttir við 100 hæðir, 500 herbergi á hæð og 200 færslur í hverjum öðrum lista, og `cut` segir
til, og líkan með fleiri en 2.000 veggi fær engin. Þegar ekki tekst að finna herbergin hefur skýrslan engin `rooms`, og
skráningin segir hvers vegna (`ifc_rooms_failed`) án þess sem skráin segir. Sjálfgefið af; getuskjalið segir hvort það
er á, sem `rooms` í `ifc_validation`.

### Það sem umbreytta líkanið sýnir

Þegar líkanið hefur verið umbreytt fær skýrslan eigin prófun, `graph`, með tvenns konar athugasemdum. Tilvik sem
ekkert með GlobalId nær, áfram eða aftur á bak, er viðvörun af gerðinni `reachability`, með STEP-auðkenni sitt í
`step_id` og flokk sinn í skilaboðunum: aðeins það númer nefnir það, eins og staðsetningu sem ekkert notar, svo
breytingasafn getur bent á það með STEP-auðkenninu einu. Vara sem rúmfræðikeyrslan gat ekki byggt lögun fyrir er
athugasemd af gerðinni `geometry`, með GlobalId sitt. Hvorug hafnar skránni: þær koma eftir upphleðsluna, og viðvörun
gefur stöðuna `warnings`. Áður en líkanið er umbreytt hefur skýrslan enga prófun `graph`.
Tilvik sem er geymt með rúmfræðinni í STEP-bálki, eins og laus punktur, er ekki
listað: prófunin sér aðeins hnútana.

### Að hafna skrám með villum, og prófa skrá fyrirfram

Kerfisstjóri getur hakað við *Hafna upphölum með sannprófunarvillum* á síðu
verkefnisins (`block_on_validation_errors` í stjórnunar-API). Prófanirnar keyra
þá áður en skráin verður útgáfa, í frágangi upphalsins og á upphalssíðunni, og
skrá með einni eða fleiri villum er hafnað með `422 ifc_validation_failed`;
viðvaranir sleppa í gegn. Skráin sem var hafnað stendur í sólarhring sem
forprófun, og `report` í villunni segir hvar skýrslan er. Skrá sem alls ekki
var hægt að prófa sleppur í gegn sem `unknown`, svo að bilaður sannprófari
stöðvi aldrei vinnuna. Skrá sem stenst er prófuð einu sinni: niðurstaðan verður
útgáfunnar, eins og prófunin hefði keyrt á eftir.

Sérhver ritstjóri eða umsjónarmaður getur líka prófað skrá án þess að gera
hana að útgáfu, með sama bearer-tákni og óháð stillingu verkefnisins:

```http
POST /documents/1.0/projects/{project_id}/ifc-precheck
Content-Disposition: attachment; filename="model.ifc"
```

Meginmálið er skráin. Svarið er `202` með `url` skýrslunnar, `pending` þar til
prófununum er lokið; þá hefur hún sama form og skýrsla útgáfu, með nafni
skrárinnar og hvenær forprófunin rennur út. Sérhver þátttakandi les hana, í
sólarhring. Getuskjalið tilkynnir forprófunina sem `ifc_precheck`.

## Grafið

Hver eining verður `Entity`-hnútur sem ber flokk sinn og allar yfirgerðir
sínar sem merkimiða, til dæmis `Entity:IfcWallStandardCase:IfcWall:
IfcBuildingElement:IfcElement:IfcProduct:IfcObject:IfcObjectDefinition:IfcRoot`.

| Eiginleiki | Merking |
|---|---|
| `id` | `<líkansauðkenni>:<STEP-auðkenni>`, einkvæmt |
| `model_id`, `step_id` | líkanið og `#123`-númerið í skránni |
| `ifc_class` | hlutstæði flokkurinn |
| `GlobalId`, `Name`, `Description`, `Tag`, … | hvert bókstaflegt eigindi einingarinnar, með IFC-heiti sínu |

Eigindi sem vísa á aðrar einingar verða vensl nefnd eftir eigindinu, skrifuð
eins og hver venslagerð í grafinu með hástöfum og undirstrikum á orðaskilum:
`(:IfcRelDefinesByProperties)-[:RELATING_PROPERTY_DEFINITION]->(:IfcPropertySet)-[:HAS_PROPERTIES]->(:IfcPropertySingleValue)`.
Andhverf eigindi verða líka vensl, svo báðar áttir lesist eðlilega:
`(:IfcWall)-[:IS_DEFINED_BY]->(:IfcRelDefinesByProperties)`.
Select-gildi eru tekin úr umbúðum (`IfcLabel('3')` verður `"3"`).

Engir hnútar sjálfgefið (`OPENCDE_IFC_LPG_INCLUDE_GEOMETRY=false`):
framsetningaratriði, framsetningar, snið, staðsetningar og stílar; þau eru
meirihluti líkans og sjaldan það sem CDE-fyrirspurn þarf, og þau eru geymd sem
texti í grafinu, sjá Að skrifa líkan til baka. `IfcOwnerHistory` er aðeins hnútur
fyrir `IfcProject`.

## Hvaðan aðferðin kemur

Umbreytingin fylgir IFC-Graph-aðferð Zhu, Wu og Lei: einn hnútur fyrir hvert
tilvik, flokkastigveldið sem merkimiðar, bókstafleg eigindi sem eiginleikar og
eigindi sem vísa á önnur tilvik, andhverf eigindi meðtalin, sem vensl nefnd eftir
eigindinu. Frumgerðin frá 2023 notaði kóða greinarinnar. Umbreyting þessa þjóns
er skrifuð að nýju.

Junxiang Zhu, Peng Wu og Xiang Lei: "IFC-graph for facilitating building
information access and query". *Automation in Construction* 148 (2023), 104778.
[doi:10.1016/j.autcon.2023.104778](https://doi.org/10.1016/j.autcon.2023.104778),
í opnum aðgangi samkvæmt CC BY 4.0.

Hún er frábrugðin greininni á þennan hátt:

- Rúmfræði verður ekki að hnútum nema beðið sé um það. Greinin umbreytir öllu og nefnir
  stærð grafsins sem takmörkun.
- Færslur eru skrifaðar í lotum með `CREATE` úr sérstöku ferli. Greinin sameinar
  hvern hnút og hver vensl, sem leitar að tvítekningum í grafinu og hægir á sér
  eftir því sem grafið stækkar.
- Select-gildi verða eiginleikar hnútar síns. Greinin gefur þeim eigin hnúta með
  búnu til auðkenni.
- Mörg líkön deila einum gagnagrunni og eru aðgreind með `model_id`. Greinin hefur
  eitt líkan í hverjum gagnagrunni.
- Venslagerðir eru skrifaðar með hástöfum, og afrit af GTIN á BCF-einingar er
  viðbót hér.

Greinin bendir á að graf hennar glati röð í listum, því að vensl segja ekki hvar í
lista markmið þeirra stóð. Hér segir `position` það.

## Að skrifa líkan til baka

Grafið rúmar allt líkanið og hægt er að skrifa skrána til baka úr því: sömu tilvik með
sömu auðkenni og sömu gildi í sömu röð, og þar með sömu landfræðilegu upplýsingar.

```sh
uv run opencde ifc-lpg export <líkansauðkenni> model.ifc            # skrifa skrána og sannprófa hana
uv run opencde ifc-lpg export <líkansauðkenni> model.ifc --verify   # og bera hana saman við þá sem var hlaðið upp
```

Hnútarnir eru þeir sem fyrirspurnir þurfa. Það sem þeir sleppa er skrifað út sem STEP og
þjappað í texta á `StepBlock`-hnúta sem hanga á `Model`: það er í grafinu en utan
seilingar Cypher, og því er ekki hægt að breyta þar. Það getur ekki verið eiginleikar
vörunna, því að stór hluti þess er sameiginlegur með þeim. Með
`OPENCDE_IFC_LPG_INCLUDE_GEOMETRY=true` verður hvert tilvik hnútur í staðinn, með
margfaldri stærð og innflutningstíma; fyrirspurnir tóku álíka langan tíma í
mælingunum.
Stílað atriði (`IfcStyledItem`) er alltaf hnútur, svo að hægt er að breyta hverjum stíl, og `form_version` á `Model` segir hvaða lögun netið hefur (2 frá útgáfu IFC-LPG 2026-11-10).

| Í skránni | Í grafinu |
|---|---|
| Tilvísun | Vensl með `position`, `[röð, dálkur]` í lista af listum; andhverf vensl hafa það ekki |
| Tilvísun í tilvik í blokk | Auðkenni þess, eins og í `Representation__step: 1234` |
| Tagað gildi, `IFCLABEL('3')` | `NominalValue: "3"`, og `NominalValue__type: "IFCLABEL"` við hliðina |
| Listi af listum af tölum | JSON-texti |
| Það sem hefur ekkert einfalt form, eins og listi af töguðum gildum | Merkt JSON, með `$json` sem tag |
| Hausinn | `ifc_header` á `Model` |
| Tilvik í blokk | Texti í `StepBlock` |

Skráin er skrifuð úr því sem grafið rúmar, ekki afrituð, svo að eiginleiki eða vensl sem
breytt er í grafinu sjást í henni. Grafgagnagrunnur hefur ekkert skema til að bera breytingu
saman við, svo að skráin er sannprófuð gegn IFC-staðlinum með sannprófara IfcOpenShell: tag
og fjöldi eiginda, upptalningar, andhverf eigindi, GlobalId og reglur EXPRESS-skemans. Skrár í
notkun brjóta oft þegar einhverja reglu, svo að það sem gildir er athugasemd sem skráin sem var
hlaðið upp hefur ekki. Skipunin birtir hana þá og endar með villu. `--no-validate` sleppir þessu.
Útflutningur stöðvast líka ef blokk vantar.

Verkefnismeðlimir fá skrár í gegnum Documents API og engin önnur leið er út úr þjóninum.
Skrifuð skrá sem á að koma í stað líkans er hlaðið upp sem nýrri útgáfu af skjali sínu, sem
umbreytir henni líka.

Þetta form er ekki lesið með IfcOpenShell, sem hér leggur aðeins til skemað. IfcOpenShell
breytir sumum gildum við lestur (`.NULLENUM.` verður `$`, og `($,$)` verður `()`), og skrár
frá Tekla og Archicad hafa slík gildi. Því les vinnsluferlið skrána sjálft og hafnar því sem
það getur ekki lesið. ADR 0010 segir hvers vegna og ADR 0011 hvernig
skrá er sannprófuð.

`--verify` spyr hvort skrárnar tvær rúmi sama líkan, samkvæmt skilgreiningunni í
ADR 0009: eitt á móti einu, gildi fyrir gildi og án vikmarka, með staðsetningu
nefnda í skýrslunni. Með `--geometry` er möskvi hverrar vöru líka byggður og þeir bornir saman
bita fyrir bita. Hvaða tvær skrár sem er má bera saman með
`python -m ifc_lpg.equivalence first.ifc second.ifc`.

Með `OPENCDE_IFC_LPG_LOSSLESS=false` er líkani umbreytt eins og fyrir 3.0.0: það er lesið með
IfcOpenShell og því sem ekki eru hnútar er sleppt alveg. Slíkt líkan, eins og líkan sem fyrri
útgáfa umbreytti, er ekki hægt að skrifa til baka.

## Umhirða

Hvert upphal IFC-skrár bætir við `Conversion` og líkani með einingum sínum, svo verkefni
sem fær nýjar útgáfur safnar gröfum sem enginn spyr um. Skipanalínan telur
þau upp og grisjar; skjölin og skrár þeirra haldast alltaf:

```sh
uv run opencde ifc-lpg list --project <verkefnisauðkenni>
uv run opencde ifc-lpg prune                   # misheppnuð líkön, og lokin líkön sem nýrri lokin útgáfa
                                                # sama skjals hefur leyst af hólmi
uv run opencde ifc-lpg prune --project <id> --all   # hvert líkan eins verkefnis (prófunarstafli, til dæmis)
```

Líkön í bið eða í keyrslu eru aldrei grisjuð. Fyrirspurnir sem vilja eitt
graf á hvert skjal ættu sjálfar að velja nýjasta lokna líkanið, þar sem eldri
útgáfur haldast þar til þær eru grisjaðar:

```cypher
MATCH (:Project {project_id: $project})-[:HAS_CONVERSION]->(m:Conversion {state: 'done'})
WITH coalesce(m.document_id, m.bcf_document_guid) AS doc, m
ORDER BY m.version_index DESC, m.done_at DESC
WITH doc, collect(m)[0] AS latest
MATCH (e:IfcProduct {model_id: latest.id})
RETURN latest.file_name AS model, count(e) AS products
```

## Tenging BCF-eininga

Þegar viewpoint er búið til með einingum fær hver eining, þar sem `ifc_guid`
passar við `GlobalId` byggingarhluta í einu af innfluttum líkönum
verkefnisins, gildi stilltu eigindarinnar
(`OPENCDE_IFC_LPG_GTIN_PROPERTY_SET=Reuse`, `OPENCDE_IFC_LPG_GTIN_PROPERTY=GTIN`)
sem `gtin`, þegar byggingarhlutinn hefur það: þjónninn flettir GlobalId-unum
upp í líkaninu með `property_values` í IFC-LPG og geymir gildið á einingunni, og
býr engin vensl til inn í líkanið; byggingarhlutinn finnst með `GlobalId` sínu.
Sama uppfletting keyrir fyrir hverja fyrirliggjandi einingu verkefnisins þegar
innflutningi líkans lýkur, svo viewpoint sem voru búin til áður en líkaninu var
hlaðið upp, eða meðan það var enn í umbreytingu, fá líka GTIN sín. Þetta er
notkunartilvikið í rannsóknarskýrslunni frá 2023: skoðun (BCF-mál) sem bendir á
byggingarvörur auðkenndar með GTIN.

```cypher
// Á hvaða vörur vísar þetta viewpoint, og hvaða GTIN hafa þær?
MATCH (:Viewpoint {guid: $viewpoint})-[:HAS_COMPONENT]->(c:Component)
MATCH (e:IfcProduct {GlobalId: c.ifc_guid})
RETURN c.ifc_guid, e.Name, c.gtin
```

```cypher
// Fyrirspurn skýrslunnar, beint á líkanið: GTIN hvers veggjar.
MATCH (w:IfcWall)-[:IS_DEFINED_BY]->(:IfcRelDefinesByProperties)-[:RELATING_PROPERTY_DEFINITION]
      ->(:IfcPropertySet {Name: 'Reuse'})-[:HAS_PROPERTIES]->(p:IfcPropertySingleValue {Name: 'GTIN'})
RETURN w.GlobalId, w.Name, p.NominalValue
```

```cypher
// Hvert mál sem snertir tiltekinn byggingarhluta.
MATCH (:Component {ifc_guid: $guid})<-[:HAS_COMPONENT]-(v:Viewpoint)<-[:HAS_VIEWPOINT]-(t:Topic)
RETURN DISTINCT t.server_assigned_id, t.title, t.topic_status
```

BCF-þjónustan `files_information` sýnir `IfcProject`-guid innfluttra líkana
sem `ifc_project`, sem gerir biðlurum kleift að fylla inn skrárnar í haus
málsins.

## Nefndar fyrirspurnir

Meðlimur verkefnis spyr líkan útgáfu spurninga eftir nafni, með sama
bearer-tóka og fyrir Documents API; frjáls Cypher er áfram hjá stjórnendum
(ADR 0016).
Fyrirspurnirnar eru skrá IFC-LPG (`ifc_lpg.queries`), svo ein sem bætt er við
safnið birtist hér.
`GET /documents/1.0/documents/{id}/versions/{index}/ifc-queries` telur
upp fyrirspurnirnar með færibreytum og dálkum og segir í `model_state` hve
langt umbreyting líkansins er komin. `GET …/ifc-queries/{name}` ber eina
fram, með færibreyturnar í fyrirspurnarstrengnum, og svarar með dálkunum og
röðunum, hver röð listi í röð dálkanna:

```http
GET /documents/1.0/documents/{id}/versions/1/ifc-queries/property?pset=Reuse&property=GTIN
```

```json
{"name": "property", "columns": ["global_id", "class", "name", "value", "type"],
 "rows": [["1Xezbq735AdBO_4DerG66G", "IfcWallStandardCase", "YVT-A", "3", "IFCLABEL"]],
 "truncated": false}
```

| Fyrirspurn | Færibreytur | Hverju hún svarar |
|---|---|---|
| `element-classes` | | Hve margar einingar líkanið hefur af hverjum flokki |
| `elements` | `class` | Einingar flokks, með rýmisskipaninni sem hver er í |
| `storeys` | | Hæðirnar, hæðarkóti þeirra og hve margar einingar og rými hver hefur |
| `spaces` | | Rýmin, hæð þeirra og nettó- og brúttógólfflötur þeirra |
| `areas` | | Nettógólfflötur rýma hverrar hæðar, lagður saman |
| `materials` | `class` | Efni hverrar einingar: eigið, eða laga hennar, lista eða efnisþátta |
| `property` | `pset`, `property`, `class` | Gildi eins eiginleika á hverjum hlut sem hefur hann, með IFC-gerð hans |
| `entity` | `global_id` | Ein rótfest eining: flokkur hennar, hver bókstafleg eigind, og það sem hún vísar til og er vísað til hennar af, hvert með IFC-eigind, STEP-auðkenni og flokki |
| `site` | | Hvar byggingin stendur: viðmiðunarbreidd, -lengd og -hæð lóðarinnar, og kortavörpunin með hnitakerfi sínu (austur- og norðurhnit, hæð, snúningur og kvarði) þar sem líkanið hefur hana |
| `changed-since` | `since` | Hvað hefur breyst í skjalinu síðan útgáfu: ein lína fyrir hverja breytingu í breytingasetti hverrar útgáfu fram að þessari, eða ein lína með `whole_file` fyrir útgáfu sem hlaðið var upp sem heilli skrá; svarað úr útgáfunum, svo ekkert graf þarf |

`class` nefnir IFC-flokk, svo sem `IfcWall`, og tekur undirflokka hans með:
áskilin fyrir `elements`, valfrjáls fyrir hinar. Svar hefur mest 10.000 raðir,
og `truncated` segir þegar þær voru fleiri; fyrirspurn er stöðvuð eftir 10
sekúndur. Hver fyrirspurn hefst hjá meðlimnum og nær líkaninu gegnum
verkefnið, les aðeins og tekur gildi sín sem færibreytur. Útgáfa án líkans,
eða sem notandinn má ekki sjá, svarar 404, og útgáfa þar sem enn er verið að
umbreyta líkaninu svarar 409. Getuskjalið kynnir fyrirspurnirnar í
`ifc_queries`.

## Breytingasett

Tillaga að breytingu á líkani ferðast sem `bim_snippet` í BCF 3.0-máli
(ADR 0021): `snippet_type` er `DataregiumIfcChangeSet`, `reference_schema` er
`GET /documents/1.0/ifc-changes/schema`, sem hver sem er má lesa, og snippetið
sjálft er sent með `PUT …/topics/{guid}/snippet`, þar sem þjónninn heldur því
að skemanu og svarar `400` með því sem er rangt. Nýtt verkefni leyfir
snippet-tegundina; kerfisstjóri bætir henni við gildi eldra verkefnis.
Breytingasett nefnir grunnútgáfu sína, hver lagði það til, með
gervigreindarlíkaninu og verkfærakallinu þar sem gervigreind gerði það, og
breytingar sínar, hverja á einni eigind eins tilviks. Tilvikið er nefnt með
GlobalId og slóð frá rótfestu einingunni í eigindaheitum IFC með vísum, og með
STEP-auðkenni sínu aðeins þar sem ekkert GlobalId nær því. `set` gefur eigindinni gildi, `add` og `remove`
breyta einum lið safns, og `copy` biður um afrit af tilviki sem fleiri deila og
breytist annars fyrir öll. Gildi er einfalt gildi, tilvik (`{"step_id": 120}`,
eða GlobalId með slóð), gildi af tagi
(`{"type": "IfcLengthMeasure", "value": 3.2}`), upptalning
(`{"enum": "NOTDEFINED"}`) eða listi af þeim. Getuskjalið tilkynnir formið sem
`ifc_changes`. Hvað breytingarnar gera við líkanið er prófað þegar tillagan er
reynd, næsta skref; í dag heldur þjónninn forminu.

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

Aðeins `editor` eða `manager` verkefnisins leggur til breytingasafn (ADR 0028):
`contributor` sem sendir það, líka í eigið mál, fær `403` með ástæðunni og
ekkert er geymt, en snippet af annarri gerð er sent eins og áður. Hið sama
gildir um breytingasafnið sem þjónninn leggur til hér á eftir.

`delete` fjarlægir tilvik sem bent er á með STEP-auðkenni sínu og ekkert vísar til, eins og tilvik sem ekkert GlobalId
nær; tilvik sem eitthvað vísar enn til er sleppt og nefnt í prófuninni. Þjónninn leggur sjálfur til slíkt
breytingasafn með `POST /documents/1.0/projects/{id}/ifc-unreachable` og útgáfunni sem `document_id` og
`version_index`: hann býr til mál þar sem snippet fjarlægir hvert tilvik sem prófunin `graph` á útgáfunni finnur utan
seilingar, og breytingasafnið er prófað og samþykkt eins og önnur, svo útgáfan sem það kom úr heldur tilvikunum.
Svarið nefnir málið, hve mörg tilvik það fjarlægir og hvar prófunin er; `404` þegar útgáfan hefur ekkert umbreytt
líkan, og `409` þegar ekkert í henni er utan seilingar. Getuskjalið telur upp aðgerðirnar í
`ifc_changes.ops` og vefslóðina sem `ifc_changes.unreachable_url`.

Breytingasafn sem gert er með skrifverkfærum Dataspatium ber líka aðgerðir þeirra sem `ops`, með `ops_form`
`dataspatium-tools/1`, svo að nýjar einingar, eyðingar og tengsl fylgi tillögunni. Hver aðgerð nefnir verkfæri sitt
sem `tool` og hefur rök verkfærisins við hliðina, lengdir í metrum: `create_storeys_and_grid`, `create_wall`,
`create_slab`, `create_roof`, `create_opening`, `create_spaces`, `set_properties`, `set_classification`, `assign`,
`transform_elements`, `delete_elements` og `set_site`. Þjónninn keyrir þær með afriti af eigin kóða appsins
(`opencde/ifcgraph/ops.py`), svo að sömu aðgerðir gefa sama líkan í appinu og á þjóninum, í einingu skrárinnar,
með þann sem lagði til og þjóninn í eigendasögunum sem IfcOpenShell býr til. Það sem vegg-, plötu-, þak- og
opsaðgerðirnar búa til heitir `new-1`, `new-2` … í röð þeirra, og það gerir líka hvert herbergi sem `create_spaces`
telur upp. Aðgerð nefnir einingu með GlobalId hennar, með STEP-auðkenni hennar aðeins þar sem ekkert GlobalId nær
henni, eða með slíku ref, og hæð með nafni sínu. `create_wall` gefur vegg miðlínu hans sem `Axis`-framsetningu, og
`create_spaces` gerir herbergin sem veggirnir loka, fundin eins og `rooms` skýrslunnar finnast, að rýmum
(`IfcSpace`) á hæð sinni, út frá skránni eins og hún er á því skrefi: hvert með útlínu herbergisins upp að næstu hæð,
`Qto_SpaceBaseQuantities` og efnislegum rýmismörkum að veggjunum meðfram brún þess og að dyrum og gluggum í þeim; dyr
eða gluggi sem gerður er síðar í slíkum vegg afmarkar líka rýmið. `changes`
má þá vera tómt: við hlið aðgerðanna lýsa breytingarnar því sem aðgerðirnar gera við tilvik sem eru til, eins og
appið fann það, fyrir sameininguna, og breyting sem aðgerðirnar hafa þegar gert telst beitt. Getuskjalið auglýsir
sniðið sem `ifc_changes.ops_form` og verkfærin sem `ifc_changes.ops_tools`.

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

Prófunin beitir fyrst aðgerðunum og síðan breytingunum, og telur hvort tveggja í `change_count`. Aðgerð sem ekki er
hægt að beita er athugasemd af taginu `op` með vísi sínum (`op`) og `tool`, með orðum kóða appsins, sem geta vitnað í
rök hennar og skrána; aðgerðunum á eftir henni og breytingunum er ekki beitt, eins og í appinu. Prófunin gefur
líka `created`, GlobalId hverrar einingar sem búin var til eftir ref hennar, svo að biðlarinn geti parað sínar eigin,
og `notes`, það sem aðgerð gat ekki gert í skema skrárinnar, eins og kortaumbreytinguna í IFC2X3.

Þegar IFC-LPG-einingin er á reynir þjónninn hvert breytingasett þegar því er
hlaðið upp: vinnsluferli beitir breytingunum á skrá grunnútgáfunnar,
niðurstaðan fer í gegnum prófanirnar sem upphal fær (IFC-skemað, reglur
buildingSMART og IDS-skjöl verkefnisins), og prófunin er `clean` þegar hverri
breytingu var hægt að beita og engin athugasemd er ný miðað við skýrslu
grunnútgáfunnar, annars `issues`.
`GET /bcf/3.0/projects/{id}/topics/{guid}/ifc-proposal` gefur stöðuna, hve
mörgum breytingum var beitt og nýju athugasemdirnar, hverja eins og í skýrslu
útgáfu; breyting sem ekki var hægt að beita er athugasemd af taginu `proposal`
sem segir hvers vegna, án þess að vitna í skrána. Nýtt snippet kemur í stað
prófunarinnar, og prófunin fer með málinu þegar því er eytt. `ifc_changes` í
getuskjalinu segir hvort breytingasett eru reynd (`tried`) og hvar prófunin er
(`proposal_url`).

`GET /documents/1.0/documents/{id}/ifc-proposals` telur upp breytingasettin
sem reynd hafa verið gegn skjali, fyrir meðlim í verkefni þess, nýjast fyrst:
í hverri línu eru guid málsins, titill þess og fyrstu 200 stafir lýsingarinnar,
staða prófunarinnar, grunnútgáfan, hve margar breytingar settið geymir, hver
lagði það til, hvenær prófuninni lauk, útgáfan sem það varð þar sem það var
samþykkt, og vistföng prófunarinnar (`proposal_url`) og samþykktar hennar
(`approve_url`). Tillaga nefnir grunn sinn frá því augnabliki sem hún er sett
í röð, svo listinn geymir hana fyrir prófunina og þegar prófunin mistókst.
`$top` og `$skip` fletta listanum eins og í BCF-listunum; listi sem þjónninn
skar ber `X-Total-Count` og `Link: <…>; rel="next"`. `404` fyrir skjal sem
meðlimurinn má ekki sjá, og þegar slökkt er á IFC-LPG-einingunni. Getuskjalið
gefur vistfangið sem `ifc_changes.ifc_proposals_url`.

`manager` samþykkir hreina prófun með `POST …/ifc-proposal/approve`: skráin
sem breytingunum var beitt á verður næsta útgáfa grunnskjalsins, með
`base_version_index`, `change_set_id` (guid málsins), `proposed_by` og
`approved_by` í lýsigögnum sínum, og gervigreindarlíkaninu og verkfærakallinu
þar sem gervigreind lagði hana til; svarið er nýja útgáfan eins og Documents
API gefur hana, og henni er umbreytt og hún prófuð eins og upphal. Málið fær
athugasemd með heimilisfangi útgáfunnar, sjónarhorn (viewpoint) sem velur
breyttu einingarnar, og stöðuna `Closed` þar sem verkefnið hefur það gildi. `412 version_conflict` segir að skjalið hafi haldið áfram
síðan grunnurinn var; `409` að prófunin sé ekki hrein, eða þegar samþykkt.
Gervigreind leggur aðeins til: samþykktin er manneskju.
Þar sem verkefnið hefur teymi telur prófunin upp í `teams` þau teymi sem
breytingasafnið snertir hluta líkansins hjá: það sem forskriftir IDS-skjals teymis
eiga við, í skrá grunnsins eða þeirri breyttu. Breytingasafn sem snertir hluta eins
teymis samþykkir ábyrgðarmaður teymisins einn, ekki `manager`; það sem snertir hluta
fleiri teyma, eða engra, samþykkir `manager`, og eins það þar sem hlutarnir fundust
ekki (`teams_error`).

Þegar skjalið hefur haldið áfram síðan grunnurinn var sameinar þjónninn:
breytingar útgáfnanna þar á milli, hver samþykkt úr breytingasetti, eru bornar
saman eigind fyrir eigind við breytingar tillögunnar. Rekist engar á er
breytingasettið reynt aftur á nýjustu útgáfuna, strax, og samþykkt á hana, svo
að grunnur nýju útgáfunnar er sú nýjasta. Rekist einhverjar á, eða var útgáfu
þar á milli hlaðið upp sem heilli skrá, er svarið `412 version_conflict` með
eigindunum sem rekast á í `conflicts` (`#123.Name`, eða GlobalId, slóð og
eigind; `*` fyrir heila skrá), svo að biðlarinn sameini þríátta og sendi
aftur.

Tilvikin eru borin saman, ekki lyklarnir sem biðlararnir skrifuðu: hver
breyting er leyst í útgáfunni sem hún var gerð á og nefnd með kanónískri slóð
sinni (`ifc_lpg.paths` í IFC-LPG), svo að tvær breytingar sem ná sama samnýtta
tilviki frá ólíkum GlobalId rekast samt á, og `conflicts` nefnir tilvikið með
þeirri slóð. Við hliðina gefur `conflict_details` fyrir hvern árekstur `key`,
eigin `guid`, `path` eða `step_id` tillögunnar, `attribute` og `op`, hvað
grunnurinn hafði (`base`), hvað nýjasta útgáfan hefur (`theirs`), hvað
tillagan setur (`ours`), öll á gildisformi breytingasafnsins, og útgáfuna á
milli sem breytti því (`version_index`); gildi sem ekki tókst að lesa er
`null`. Biðlarinn lætur manneskju velja fyrir hvern árekstur, sendir nýjan
snippet á nýjustu útgáfuna og samþykkir aftur. Biðlari sem getur ekki skorið
eina breytingu úr aðgerðum sínum sendir þær aftur með lyklunum sem hann gefur
eftir í `keep_theirs`, eins og `conflicts` nefndi þá: þjónninn reynir þá
breytingasettið á nýjustu útgáfu skjalsins og gefur hverri þessara eiginda
aftur gildi nýjustu útgáfunnar eftir aðgerðirnar og breytingarnar.

Útgáfa sem byggir á annarri er hnútur með foreldri sínu:
`parent_version_index` og tengill á foreldrisútgáfuna, á útgáfu sem samþykkt
var úr breytingasetti og á upphali sem gaf `base_version_index`. Útgáfa
samþykkt úr breytingasetti ber líka `approved_by`, `change_set_id` (guid
málsins) og breytingarnar sjálfar, sem
`GET /documents/1.0/documents/{id}/versions/{index}/ifc-changes` gefur í formi
skemans, með grunninum og hver lagði til og samþykkti; útgáfa sem hlaðið var
upp sem heilli skrá svarar `404` þar. Hver útgáfa er enn heil skrá, sótt eins
og áður; `opencde ifc-lpg prune` fjarlægir gröf eldri útgáfna, því að
aðalútgáfan og keðja breytingasettanna segja hvað breyttist.

## Að bera saman tvær útgáfur

Þátttakandi ber saman tvær IFC-útgáfur einingu fyrir einingu, með sama
bearer-tákni og Documents API: útgáfu við aðra útgáfu sama skjals, eða með
`?other_document_id=` útgáfu annars skjals í verkefninu. Vinnsluferlið parar
rótfestu einingarnar eftir GlobalId og svarar með `added` (aðeins hin hefur
þær), `removed` (aðeins þessi hefur þær) og `changed` (í báðum, með eigindum
sem eru ólíkar), hver eining nefnd með GlobalId, flokki, nafni og hæð, og
fyrir breytta einingu slóðirnar sem eru ólíkar með gamla og nýja gildinu: bein
eigind með nafni sínu, eiginleiki sem `Pset.Property`, `ObjectPlacement`
(4×4-fylkið), `Representation` (fingrafar lögunarinnar), `Container` (hæðin)
og `Type`. Vensl og eiginleikasöfn eru felld inn í einingarnar sem þau
tilheyra, og hver listi geymir mest 10.000 einingar. Munurinn er reiknaður
eftir beiðni og aldrei vistaður; stórt líkan tekur sinn tíma. Síða
útgáfunnar býður sömu samanburð sem lista, og getuskjalið tilkynnir hann sem
`ifc_diff`.

```http
GET /documents/1.0/documents/{document_id}/versions/{version_index}/ifc-diff/{other_index}
```

## Árekstrarprófun

Félagi ber saman tvær IFC-skjalaútgáfur verkefnis með tilliti til árekstra, með
sama bearer-tóka og Documents API:
`POST /documents/1.0/projects/{project_id}/ifc-clash` með útgáfunum tveimur,
hamnum (`intersection`: einingar sem ganga inn í hvor aðra dýpra en `tolerance`;
`clearance`: einingar nær hvor annarri en `clearance`, bæði í metrum) og, ef
vill, IFC-klösum hvorrar hliðar. Prófunin keyrir í vinnuferli á eftir
umbreytingarröðinni; `url` svarsins gefur skýrsluna, `done` eða `failed` eftir
stund. Hver árekstur nefnir báðar einingarnar (skjal, útgáfu, STEP-auðkenni,
GlobalId, klasa, heiti, hæð), tegund sína, dýpt eða fjarlægð og punktinn þar sem
hann var mældur, á því formi sem árekstrarkjarni Dataspatium sjálfs skrifar, svo
forritið sýnir niðurstöðu þjónsins eins og sína eigin.
`POST …/ifc-clash/{id}/topics` gerir valda árekstra að BCF-málum með sitt hvert
viewpoint, aðeins að beiðni. Getuskjalið tilkynnir prófunina sem `ifc_clash`
þegar rekstraraðilinn hefur sett `OPENCDE_IFC_LPG_CLASH_ENABLED=true`; skýrsla
heldur í mesta lagi `OPENCDE_IFC_LPG_CLASH_MAX_CLASHES` árekstrum.

```http
POST /documents/1.0/projects/{project_id}/ifc-clash
{"a": {"document_id": "…", "version_index": 1, "types": ["IfcWall"]},
 "b": {"document_id": "…", "version_index": 2},
 "mode": "intersection", "tolerance": 0.001}
```

## Bygging inn í annað líkan

Bygging úr einu líkani kemur inn í líkan annars verkefnis sem næsta útgáfa skjals
þess; hvorugt líkanið breytist. Líkan A er útgáfa í þessu verkefni, líkan B útgáfa í
hvaða verkefni sem er sem kallandinn er meðlimur í, og bæði verða að vera umbreytt,
með sama skema og lengdareiningu.
`POST /documents/1.0/projects/{project_id}/ifc-merge/report` sýnir hverjum meðlimi
beggja verkefna hvað myndi gerast: hve margir hlutir og tilvik fylgja með, hlutirnir
með GlobalId sem bæði hafa (`collisions`, með `same` og því `choice` sem gildir),
venslin sem eru skilin eftir af því að þau vísa aðeins út úr byggingunni, og
samhengi og staðsetningar A sem eru notuð. Þar sem innihald slíks hlutar er ólíkt er
valið fyrir hann: `a` heldur hlut A, `b` setur hlut B í hans stað, og `new` heldur
báðum, hlut B með nýtt GlobalId; `default` gefur eitt val fyrir þá alla.
Eining af tegund sem A hefur enga af, eins og flatarmálseining, fylgir með inn í
einingar A og er talin upp í `units_added`; eining af tegund sem bæði hafa verður að vera sú sama.

`manager` verkefnisins ræsir sameininguna með `POST …/ifc-merge` og sama meginmáli.
Hún keyrir sem verk í umbreytingarbiðröðinni, og `url` svarsins gefur stöðu hennar:
`conflict` með hlutunum sem enn vantar val, `failed` með ástæðunni, eða `done` með
`version_index`, nýju útgáfunni af skjali A. Sameinaða líkanið er fyrst prófað
gagnvart A og B og má ekki hafa neina athugasemd sem þau hafa ekki; síðan er það
skrifað út sem næsta útgáfa, með útgáfu A sem foreldri og `merged_from_document`,
`merged_from_version` og `merged_building` í lýsigögnum sínum, og umbreytt og prófað
eins og upphal. Útgáfa A verður að vera nýjasta útgáfa skjalsins (annars 412
`version_conflict`). Getuskjalið tilkynnir hana sem `ifc_merge`.

Þar sem skema eða lengdareining B er ekki sú sama og A segir skýrslan það (422), og
`editor` eða `manager` undirbýr fyrst B með `POST …/ifc-merge/prepare` og `base` og
`other`: verk sem gerir afrit af B, flutt yfir í skema A og með lengdir sínar í
einingu A. Þegar það er `done` lætur `merge_id` þess, gefið sem `other.prepared`,
afritið koma í stað B í skýrslunni og sameiningunni þar til `expires_at`, sólarhring
síðar; þá fjarlægir þjónninn það. Önnur eining sem er ólík er ekki umreiknuð, og
verkið mistekst á henni.
Það sem skema A á sér enga hliðstæðu við, eins og IfcWindowStyle úr IFC2X3 í
IFC4X3 eða eigendasögurnar sem IFC2X3 krefst, setur verkið í stöðuna `conflict`:
`report.problems` telur upp hvert vandamál með `key`, hvað það snertir og `options`
(`type`, `proxy`, `leave_out`, `polyline`, `owner`, `virtual`, `dated`,
`assignment`, `context`), og nýtt `POST …/ifc-merge/prepare` með `resolutions`, valda kostinum
fyrir hvern lykil, býr til afritið. Afritið er síðan prófað gagnvart B: afrit með
athugasemd sem B hafði ekki er ekki búið til, og verkið er `failed` með þeim í
`report.new`.

```http
POST /documents/1.0/projects/{project_id}/ifc-merge
{"base": {"document_id": "…", "version_index": 3},
 "other": {"project_id": "…", "document_id": "…", "version_index": 1},
 "building": "3AMeTOOFsdVLZuNV0$27s5", "choices": {"1Xezbq735AdBO_4DerG66G": "b"}}
```

## Vinnueintakið

Við hlið safnsins getur þjónninn haldið vinnueintaki: öðru grafi, Memgraph í
minni, þangað sem líkan aðalútgáfu hvers skjals er líka flutt inn (ADR 0024).
Safnið heldur hverri útgáfu og er áfram sannleikurinn; vinnueintakið heldur
einu líkani á hvert skjal, því síðast umbreytta, og svarar nefndu
fyrirspurnunum fyrir það, svo að stórt líkan sé lesið úr minni.
`OPENCDE_WORKCOPY_GRAPH_URI` nefnir það (`OPENCDE_WORKCOPY_GRAPH_DIALECT`,
`_USER`, `_PASSWORD` og `_DATABASE` við hliðina); yfirlagið
`docker/compose.workcopy.yaml` bætir Memgraph við hvaða stafla sem er, óbirtu.
Umbreyting flytur sömu færslur inn í bæði gröfin í máltækishlutlausu formi
IFC-LPG, kemur í stað fyrra líkans skjalsins í vinnueintakinu og bregst aldrei
vegna vinnueintaksins: afrit sem ekki var hægt að gera er merkt `failed` þar
og safnið er ósnert. Líkan sem safnið hefur ekki lengur yfirgefur vinnueintakið
í næstu tiltekt. `GET …/ifc-queries` segir í `workcopy` hvort líkan útgáfunnar
sé þar, `/readyz` greinir frá ástandi vinnueintaksins án þess að vera háð því,
og getuskjalið segir í `ifcgraph.workcopy` hvort eitt sé stillt.

```sh
# .env: COMPOSE_FILE=docker/compose.yaml:docker/compose.local.yaml:docker/compose.workcopy.yaml
docker compose up -d
```

## Hvar byggingarhlutarnir eru, og rúmfræðin

Eftir umbreytingu keyrir þjónninn rúmfræðivinnslu IFC-LPG einu sinni yfir
skrána (`python -m ifc_lpg.spatial`; `OPENCDE_IFC_LPG_SPATIAL`, sjálfgefið á
með viðbótinni): IfcOpenShell byggir lögun hvers byggingarhluta og vinnslan
skrifar kassa á hvern byggingarhluta í verkefnishnitum og möskvana, hvern
samnýttan möskva einu sinni. Kassarnir fara inn í netið sem punktarnir
`bbox_min`, `bbox_max` og `bbox_centre` á `Entity` byggingarhlutans, með
punktatriðaskrá á `bbox_centre` í safninu og í vinnueintakinu, svo að
fyrirspurn finni það sem er nálægt punkti eða innan rúmmáls; `Model` ber
`spatial_at`, `spatial_products` og `spatial_failed`. Færslurnar eru geymdar
og `GET …/ifc-geometry` byggir tvíundar-glTF úr þeim þegar fyrst er beðið um
hana: hvern samnýttan möskva einu sinni, hnút á hvern byggingarhluta sem
tilvikar hann með fylki byggingarhlutans, nefndan með GlobalId og með flokk,
STEP-auðkenni og hæð í `extras`, undir hnút á hverja hæð, og rót sem snýr
líkaninu frá Z upp í IFC yfir í Y upp í glTF. `lod=box` gefur kassana í
staðinn, einn tening sem hver byggingarhluti tilvikar, nokkur bæti hver;
`classes` (IFC-flokkar, aðskildir með kommum) og `storey` (GlobalId) velja
byggingarhlutana. Skráin er geymd og fylgir `ETag` fyrir líkanið og síurnar,
svo að `If-None-Match` fær svarið `304`. Rúmfræðiumferðin fellir aldrei
umbreytingu: mistakist hún skráir líkanið `spatial_error` og leiðin svarar
`404`; meðan útgáfan er enn í umbreytingu, `409`. Getuskjalið tilkynnir hana
sem `ifc_geometry`.

```http
GET /documents/1.0/documents/{document_id}/versions/{version_index}/ifc-geometry?lod=full&classes=IfcWall,IfcSlab
```

```cypher
// Byggingarhlutar innan tveggja metra frá vegg, í sama líkani
MATCH (w:Entity:IfcWall {GlobalId: $guid})
MATCH (e:Entity {model_id: w.model_id}) WHERE e.bbox_centre IS NOT NULL AND e <> w
  AND point.distance(e.bbox_centre, w.bbox_centre) < 2.0
RETURN e.GlobalId, e.ifc_class, point.distance(e.bbox_centre, w.bbox_centre) AS distance ORDER BY distance
```

## Fyrirspurnir frá Dataspatium

[Dataspatium](https://github.com/marwiss/Dataspatium), vafrabiðlarinn sem er
þróaður samhliða þessum þjóni, keyrir Cypher gegn þessu grafi um
Neo4j-uppsprettu sína yfir Bolt (WebSocket á Bolt-gáttinni) þegar
rekstraraðilinn opnar gagnagrunninn, eins og þróunaryfirlagið gerir á
`127.0.0.1:7697`. Dataregium-vinnusvæði þess notar mynstrin að ofan (líkön,
flokka, einingar með `GlobalId`, nýjasta lokna líkanið á hvert skjal);
fyrirspurnirnar eru í skjölun Dataspatium (`docs/grafer.md`).
Framleiðsluþjónn birtir ekki Bolt; graffyrirspurn stjórnunarforritaskilanna
(`OPENCDE_GRAPH_QUERY_ENABLED`, [client-guide.md §7](client-guide.md)) gefur
stjórnendum lesandi Cypher án gáttarinnar. Forritið teiknar líka grafið, í
spjaldinu IFC-LPG, í gegnum þá fyrirspurn eða yfir Bolt.

## Takmörk og staða

- Ein umbreyting í einu; stór líkön fara í biðröð. Sýnilíkanið (248 einingar)
  er flutt inn á um einni sekúndu; 200 MB arkitektalíkan tekur mínútur.
- `Conversion` ber `state`, `entities`, `relationships`,
  `lossless`, `geometry`, `schema`, `ifc_project_guid`, tímastimpla og `error`. Stjórnendur geta
  skoðað hann í Neo4j Browser eða Memgraph Lab:
  `MATCH (c:Conversion) RETURN c.file_name, c.state, c.entities, c.error`.
- Að eyða verkefni eyðir einingum líkana þess með því.
- Líkan kemur eins til baka úr báðum gagnagrunnum upp að 224.496 tilvikum og 19 MB, í hverju
  formi sem var mælt. Ekkert stærra hefur verið prófað.
