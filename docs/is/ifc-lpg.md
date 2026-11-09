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
2. Þjónninn býr til `IfcModel`-hnút (staða `queued`) tengdan verkefninu og
   hefur umbreytingu í bakgrunni, eina í einu.
3. Sérstakt vinnuferli (`python -m ifc_lpg.worker`) les skrána. Það keyrir með tímamörkum
   (`OPENCDE_IFC_LPG_TIMEOUT_SECONDS`, 15 mínútur), vistfangarýmismörkum á
   POSIX (`OPENCDE_IFC_LPG_MEMORY_MB`, 4 GiB) og hámarki eininga
   (`OPENCDE_IFC_LPG_MAX_ENTITIES`). Hrun eða frysting drepur vinnuferlið,
   ekki þjóninn. `.ifczip` er pakkað upp innan stærðarmarka upphalsins.
4. Færslurnar eru fluttar inn í lotum með `UNWIND … CREATE` (flytjanlegt
   Cypher, ekkert APOC). `IfcModel` endar í stöðunni `done` með talningum og
   `IfcProject`-guid, eða `failed` með villu.
5. Umbreyting sem stöðvaður þjónn skildi eftir byrjar upp á nýtt: sú sem bíður í röð um leið og þjónninn er
   kominn aftur, sú sem var í gangi þegar tvöföld tímamörk eru liðin, því að hún gæti verið í gangi í öðru þjónsferli.

`opencde seed` umbreytir sýnilíkaninu á sama hátt þegar einingin er virk.

## Prófun upphalaðra skráa gagnvart IFC-skemanu

Sérhver `.ifc`- eða `.ifczip`-skrá sem hlaðið er upp sem útgáfu skjals er einnig
prófuð gagnvart IFC-skemanu, með sama sannprófara og prófar skrifaða skrá
([Að skrifa líkan til baka](#að-skrifa-líkan-til-baka)): tag og fjöldi eiginda,
upptalningar, andhverf eigindi, GlobalId og reglur EXPRESS-skemans. Prófunin
keyrir í bakgrunni á undan umbreytingunni, í vinnsluferli með sömu mörkum. Hún
stöðvar aldrei upphal: skráin er vistuð eins og hún kom, hvað sem prófunin finnur.
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
buildingSMART prófar umfram skemað ([ADR 0012](../adr/0012-buildingsmarts-rules-run-in-an-environment-of-their-own.md)).
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
([ADR 0015](../adr/0015-uploads-are-checked-against-the-projects-ids-documents.md)).
Prófun IFC-LPG les hvert IDS á öruggan hátt og afhendir það IfcTester frá
IfcOpenShell, sama prófara og Dataspatium keyrir í vafranum, svo að hvort
tveggja gefi sömu niðurstöðu. Hún keyrir á eftir hinum prófununum, í sams konar
vinnsluferli með sömu mörkum. IDS sem er hlaðið upp síðar gildir um þær
IFC-útgáfur sem er hlaðið upp á eftir því.

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

## Grafið

Hver eining verður `IfcEntity`-hnútur sem ber flokk sinn og allar yfirgerðir
sínar sem merkimiða, til dæmis `IfcEntity:IfcWallStandardCase:IfcWall:
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
- Venslagerðir eru skrifaðar með hástöfum, og `SAME_AS` og afrit af GTIN eru
  viðbætur hér.

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
þjappað í texta á `StepBlock`-hnúta sem hanga á `IfcModel`: það er í grafinu en utan
seilingar Cypher, og því er ekki hægt að breyta þar. Það getur ekki verið eiginleikar
vörunna, því að stór hluti þess er sameiginlegur með þeim. Með
`OPENCDE_IFC_LPG_INCLUDE_GEOMETRY=true` verður hvert tilvik hnútur í staðinn, með
margfaldri stærð og innflutningstíma; fyrirspurnir tóku álíka langan tíma í
[mælingunum](../adr/0010-a-lossless-graph-reads-and-writes-step-itself.md).

| Í skránni | Í grafinu |
|---|---|
| Tilvísun | Vensl með `position`, `[röð, dálkur]` í lista af listum; andhverf vensl hafa það ekki |
| Tilvísun í tilvik í blokk | Auðkenni þess, eins og í `Representation__step: 1234` |
| Tagað gildi, `IFCLABEL('3')` | `NominalValue: "3"`, og `NominalValue__type: "IFCLABEL"` við hliðina |
| Listi af listum af tölum | JSON-texti |
| Það sem hefur ekkert einfalt form, eins og listi af töguðum gildum | Merkt JSON, með `$json` sem tag |
| Hausinn | `ifc_header` á `IfcModel` |
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
það getur ekki lesið. [ADR 0010](../adr/0010-a-lossless-graph-reads-and-writes-step-itself.md) segir hvers vegna og [ADR 0011](../adr/0011-a-file-written-from-the-graph-is-validated.md) hvernig
skrá er sannprófuð.

`--verify` spyr hvort skrárnar tvær rúmi sama líkan, samkvæmt skilgreiningunni í
[ADR 0009](../adr/0009-what-makes-two-ifc-files-the-same-model.md): eitt á móti einu, gildi fyrir gildi og án vikmarka, með staðsetningu
nefnda í skýrslunni. Með `--geometry` er möskvi hverrar vöru líka byggður og þeir bornir saman
bita fyrir bita. Hvaða tvær skrár sem er má bera saman með
`python -m ifc_lpg.equivalence first.ifc second.ifc`.

Með `OPENCDE_IFC_LPG_LOSSLESS=false` er líkani umbreytt eins og fyrir 3.0.0: það er lesið með
IfcOpenShell og því sem ekki eru hnútar er sleppt alveg. Slíkt líkan, eins og líkan sem fyrri
útgáfa umbreytti, er ekki hægt að skrifa til baka.

## Umhirða

Hvert upphal IFC-skrár bætir við `IfcModel` með einingum sínum, svo verkefni
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
MATCH (:Project {project_id: $project})-[:HAS_MODEL]->(m:IfcModel {state: 'done'})
WITH coalesce(m.document_id, m.bcf_document_guid) AS doc, m
ORDER BY m.version_index DESC, m.done_at DESC
WITH doc, collect(m)[0] AS latest
MATCH (e:IfcProduct {model_id: latest.id})
RETURN latest.file_name AS model, count(e) AS products
```

## Tenging BCF-eininga

Þegar viewpoint er búið til með einingum fær hver eining, þar sem `ifc_guid`
passar við `GlobalId` byggingarhluta í einu af innfluttum líkönum
verkefnisins, `SAME_AS`-vensl við hann. Sama tenging keyrir fyrir hverja
fyrirliggjandi einingu verkefnisins þegar innflutningi líkans lýkur, svo
viewpoint sem voru búin til áður en líkaninu var hlaðið upp, eða meðan það
var enn í umbreytingu, eru tengd líka. Ef byggingarhlutinn ber stillta
eiginleikann (`OPENCDE_IFC_LPG_GTIN_PROPERTY_SET=Reuse`,
`OPENCDE_IFC_LPG_GTIN_PROPERTY=GTIN`), er gildi hans afritað á eininguna
sem `gtin`. Þetta er notkunartilvik rannsóknarskýrslunnar frá 2023: skoðun
(BCF-mál) sem vísar á byggingarvörur sem eru auðkenndar með GTIN.

```cypher
// Á hvaða vörur vísar þetta viewpoint, og hvaða GTIN hafa þær?
MATCH (:Viewpoint {guid: $viewpoint})-[:HAS_COMPONENT]->(c:Component)-[:SAME_AS]->(e:IfcProduct)
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
MATCH (e:IfcEntity {GlobalId: $guid})<-[:SAME_AS]-(:Component)<-[:HAS_COMPONENT]-(v:Viewpoint)<-[:HAS_VIEWPOINT]-(t:Topic)
RETURN DISTINCT t.server_assigned_id, t.title, t.topic_status
```

BCF-þjónustan `files_information` sýnir `IfcProject`-guid innfluttra líkana
sem `ifc_project`, sem gerir biðlurum kleift að fylla inn skrárnar í haus
málsins.

## Nefndar fyrirspurnir

Meðlimur verkefnis spyr líkan útgáfu spurninga eftir nafni, með sama
bearer-tóka og fyrir Documents API; frjáls Cypher er áfram hjá stjórnendum
([ADR 0016](../adr/0016-members-ask-the-ifc-graph-named-queries.md)).
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

`class` nefnir IFC-flokk, svo sem `IfcWall`, og tekur undirflokka hans með:
áskilin fyrir `elements`, valfrjáls fyrir hinar. Svar hefur mest 10.000 raðir,
og `truncated` segir þegar þær voru fleiri; fyrirspurn er stöðvuð eftir 10
sekúndur. Hver fyrirspurn hefst hjá meðlimnum og nær líkaninu gegnum
verkefnið, les aðeins og tekur gildi sín sem færibreytur. Útgáfa án líkans,
eða sem notandinn má ekki sjá, svarar 404, og útgáfa þar sem enn er verið að
umbreyta líkaninu svarar 409. Getuskjalið kynnir fyrirspurnirnar í
`ifc_queries`.

## Fyrirspurnir frá Dataspatium

[Dataspatium](https://github.com/marwiss/Dataspatium), vafrabiðlarinn sem er
þróaður samhliða þessum þjóni, keyrir Cypher gegn þessu grafi um
Neo4j-uppsprettu sína yfir Bolt (WebSocket á Bolt-gáttinni) þegar
rekstraraðilinn opnar gagnagrunninn, eins og þróunaryfirlagið gerir á
`127.0.0.1:7697`. Dataregium-vinnusvæði þess notar mynstrin að ofan (líkön,
flokka, einingar um `SAME_AS`, nýjasta lokna líkanið á hvert skjal);
fyrirspurnirnar eru í skjölun Dataspatium (`docs/grafer.md`), og lifandi
keyrslurnar eru taldar upp í [acceptance.md](../acceptance.md).
Framleiðsluþjónn birtir ekki Bolt; graffyrirspurn stjórnunarforritaskilanna
(`OPENCDE_GRAPH_QUERY_ENABLED`, [client-guide.md §7](client-guide.md)) gefur
stjórnendum lesandi Cypher án gáttarinnar. Forritið teiknar líka grafið, í
spjaldinu IFC-LPG, í gegnum þá fyrirspurn eða yfir Bolt.

## Takmörk og staða

- Ein umbreyting í einu; stór líkön fara í biðröð. Sýnilíkanið (248 einingar)
  er flutt inn á um einni sekúndu; 200 MB arkitektalíkan tekur mínútur.
- `IfcModel`-hnúturinn ber `state`, `entities`, `relationships`, `skipped`,
  `lossless`, `schema`, `ifc_project_guid`, tímastimpla og `error`. Stjórnendur geta
  skoðað hann í Neo4j Browser eða Memgraph Lab:
  `MATCH (m:IfcModel) RETURN m.file_name, m.state, m.entities, m.error`.
- Að eyða verkefni eyðir einingum líkana þess með því.
- Líkan kemur eins til baka úr báðum gagnagrunnum upp að 224.496 tilvikum og 19 MB, í hverju
  formi sem var mælt. Ekkert stærra hefur verið prófað.
