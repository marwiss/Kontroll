# IFC-LPG

Valkvæða IFC-LPG-einingin breytir upphlöðnu IFC-líkani í grafgögn, svo að
einingar BCF-viewpoints megi tengja við byggingarhlutana sem þær vísa á, og
svo að spyrja megi um líkanið í Cypher við hlið málanna og skjalanna.

Kveiktu á henni með `OPENCDE_IFC_LPG_ENABLED=true` og settu upp aukapakkann
`ifc-lpg` (`uv sync --extra ifc-lpg`). Docker-myndin inniheldur aukapakkann
sjálfgefið (`ARG OPENCDE_EXTRAS` í Dockerfile), sem meira en tvöfaldar stærð
hennar (um 680 MB á móti 300 MB); byggðu með `--build-arg OPENCDE_EXTRAS=`
fyrir grennri mynd án IfcOpenShell þegar einingin er áfram óvirk.

Fram í nóvember 2026 hét einingin IFC-graph. Stillingar hennar hétu `OPENCDE_IFCGRAPH_*`
og skipunin `opencde ifcgraph`, og hvort tveggja virkar enn; atvikaskrá þjónsins
og `opencde doctor` nefna gömlu stillingarnar sem hann fær.

## Hvað gerist við upphal

1. Documents API-upphali lýkur (eða skrá er hlaðið upp frá valsíðunni, eða
   BCF-verkefnisskjal er póstað) með `.ifc`- eða `.ifczip`-heiti.
2. Þjónninn býr til `IfcModel`-hnút (staða `queued`) tengdan verkefninu og
   hefur umbreytingu í bakgrunni, eina í einu.
3. Sérstakt vinnuferli (`python -m opencde.ifcgraph.worker`) þáttar skrána
   með IfcOpenShell. Það keyrir með tímamörkum
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

Sleppt sjálfgefið (`OPENCDE_IFC_LPG_INCLUDE_GEOMETRY=false`):
framsetningaratriði, framsetningar, snið, staðsetningar og stílar; þau eru
meirihluti líkans og sjaldan það sem CDE-fyrirspurn þarf. `IfcOwnerHistory`
er aðeins haldið fyrir `IfcProject`.

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

- Rúmfræði er sleppt nema beðið sé um hana. Greinin umbreytir öllu og nefnir
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

Röð í listum glatast líka hér, eins og greinin bendir á um sitt eigið graf: vensl
segja ekki hvar í lista markmið þeirra stóð.

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
  `schema`, `ifc_project_guid`, tímastimpla og `error`. Stjórnendur geta
  skoðað hann í Neo4j Browser eða Memgraph Lab:
  `MATCH (m:IfcModel) RETURN m.file_name, m.state, m.entities, m.error`.
- Að eyða verkefni eyðir einingum líkana þess með því.
