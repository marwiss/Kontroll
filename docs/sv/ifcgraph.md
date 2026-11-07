# IFC-graf

Den valfria IFC-grafmodulen gör en uppladdad IFC-modell till grafdata, så att
komponenterna i en BCF-viewpoint kan kopplas till de byggnadsdelar de pekar
på, och så att frågor om modellen kan ställas i Cypher bredvid ärendena och
dokumenten.

Slå på den med `OPENCDE_IFCGRAPH_ENABLED=true` och installera extrapaketet
`ifcgraph` (`uv sync --extra ifcgraph`). Docker-avbildningen innehåller
extrapaketet som standard (`ARG OPENCDE_EXTRAS` i Dockerfile), vilket mer än
dubblar dess storlek (ungefär 680 MB mot 300 MB); bygg med
`--build-arg OPENCDE_EXTRAS=` för en slankare avbildning utan IfcOpenShell
när modulen förblir avstängd.

## Vad som händer vid uppladdning

1. En Documents API-uppladdning slutförs (eller en fil laddas upp från
   urvalssidan, eller ett BCF-projektdokument postas) med ett `.ifc`- eller
   `.ifczip`-namn.
2. Servern skapar en `IfcModel`-nod (tillstånd `queued`) kopplad till
   projektet och startar en konvertering i bakgrunden, en i taget.
3. En separat arbetsprocess (`python -m opencde.ifcgraph.worker`) tolkar
   filen med IfcOpenShell. Den körs med en tidsgräns
   (`OPENCDE_IFCGRAPH_TIMEOUT_SECONDS`, 15 minuter), en adressrymdsgräns på
   POSIX (`OPENCDE_IFCGRAPH_MEMORY_MB`, 4 GiB) och ett tak för antalet
   entiteter (`OPENCDE_IFCGRAPH_MAX_ENTITIES`). En krasch eller en hängning
   dödar arbetsprocessen, inte servern. `.ifczip` packas upp med
   uppladdningens storleksgräns.
4. Posterna importeras i batchar av `UNWIND … CREATE` (portabel Cypher,
   ingen APOC). `IfcModel` hamnar i tillståndet `done` med antal och
   `IfcProject`-guid, eller `failed` med ett fel.
5. En konvertering som en stoppad server lämnat efter sig börjar om: en köad så snart servern är tillbaka, en
   pågående när dubbla tidsgränsen har passerat, eftersom den kan pågå i en annan serverprocess.

`opencde seed` konverterar exempelmodellen på samma sätt när modulen är på.

## Grafen

Varje entitet blir en `IfcEntity`-nod som bär sin klass och alla sina
supertyper som etiketter, till exempel `IfcEntity:IfcWallStandardCase:IfcWall:
IfcBuildingElement:IfcElement:IfcProduct:IfcObject:IfcObjectDefinition:IfcRoot`.

| Egenskap | Betydelse |
|---|---|
| `id` | `<modell-id>:<STEP-id>`, unikt |
| `model_id`, `step_id` | modellen och `#123`-numret i filen |
| `ifc_class` | den konkreta klassen |
| `GlobalId`, `Name`, `Description`, `Tag`, … | varje literalt attribut hos entiteten, med sitt IFC-namn |

Attribut som pekar på andra entiteter blir relationer namngivna efter
attributet, skrivna som varje relationstyp i grafen med versaler och
understreck vid ordgränserna:
`(:IfcRelDefinesByProperties)-[:RELATING_PROPERTY_DEFINITION]->(:IfcPropertySet)-[:HAS_PROPERTIES]->(:IfcPropertySingleValue)`.
Inversa attribut blir också relationer, så att båda riktningarna läses
naturligt: `(:IfcWall)-[:IS_DEFINED_BY]->(:IfcRelDefinesByProperties)`.
Select-värden packas upp (`IfcLabel('3')` blir `"3"`).

Utelämnas som standard (`OPENCDE_IFCGRAPH_INCLUDE_GEOMETRY=false`):
representationsobjekt, representationer, profiler, placeringar och stilar; de
utgör merparten av en modell och är sällan vad en CDE-fråga behöver.
`IfcOwnerHistory` behålls bara för `IfcProject`.

## Varifrån metoden kommer

Omvandlingen följer IFC-Graph-metoden av Zhu, Wu och Lei: en nod per instans,
klasshierarkin som etiketter, literala attribut som egenskaper och attribut som
pekar på andra instanser, inversa attribut inräknade, som relationer namngivna
efter attributet. Prototypen från 2023 använde artikelns kod. Den här serverns
konvertering är nyskriven.

Junxiang Zhu, Peng Wu och Xiang Lei: "IFC-graph for facilitating building
information access and query". *Automation in Construction* 148 (2023), 104778.
[doi:10.1016/j.autcon.2023.104778](https://doi.org/10.1016/j.autcon.2023.104778),
öppet tillgänglig under CC BY 4.0.

Den skiljer sig från artikeln på dessa punkter:

- Geometri utelämnas om den inte efterfrågas. Artikeln konverterar allt och
  nämner grafens storlek som en begränsning.
- Posterna skrivs i omgångar med `CREATE` från en separat process. Artikeln slår
  samman varje nod och relation, vilket söker efter dubbletter i grafen och går
  långsammare ju större grafen blir.
- Select-värden blir egenskaper på sin nod. Artikeln ger dem egna noder med en
  genererad identifierare.
- Flera modeller delar en databas och skiljs åt med `model_id`. Artikeln har en
  modell per databas.
- Relationstyperna skrivs med versaler, och `SAME_AS` och kopian av GTIN är
  tillägg här.

Ordningen i listor går förlorad även här, vilket artikeln påpekar om sin egen
graf: en relation säger inte var i en lista dess mål stod. Formen under Skriva
tillbaka en modell behåller den.

## Skriva tillbaka en modell

Med `OPENCDE_IFCGRAPH_LOSSLESS=true` konverteras en modell så att grafen
rymmer hela den, och filen kan skrivas tillbaka från grafen: samma instanser
med samma id, och samma värden i samma ordning, alltså också samma geografiska
information. Det är avstängt som standard. En modell som konverterats utan det
behåller sin form och kan inte skrivas tillbaka.

```sh
uv run opencde ifcgraph export <modell-id> model.ifc            # skriv filen
uv run opencde ifcgraph export <modell-id> model.ifc --verify   # och jämför den med den uppladdade
```

Noderna förblir den vanliga formens, med samma egenskaper och relationer, så
frågorna på den här sidan fungerar på båda. Det den formen utelämnar skrivs ut
som STEP och komprimeras till text på `StepBlock`-noder som hänger på `IfcModel`:
det finns i grafen men utom räckhåll för Cypher. Det kan inte vara egenskaper på
produkterna, eftersom mycket av det delas mellan dem. Med
`OPENCDE_IFCGRAPH_INCLUDE_GEOMETRY=true` blir varje instans en nod i stället, till
flera gånger storleken och importtiden; frågor tog ungefär lika lång tid i
[mätningarna](../adr/0010-a-lossless-graph-reads-and-writes-step-itself.md).

Filen skrivs från det grafen rymmer och kopieras inte, så en egenskap eller en
relation som ändras i grafen syns i den; det som ligger i ett block kan inte
ändras så. Inget kontrollerar att en ändrad modell fortfarande är giltig. En
export avbryts om ett block saknas. Detta tillkommer till det den vanliga formen har:

| I filen | I grafen |
|---|---|
| En referens | En relation med `position`, `[rad, kolumn]` i en lista av listor; inversa relationer har ingen |
| Ett typat värde, `IFCLABEL('3')` | `NominalValue: "3"`, och `NominalValue__type: "IFCLABEL"` bredvid |
| En lista av listor av tal | JSON-text |
| Det som saknar enkel form, som en lista av typade värden | Märkt JSON, med `$json` som typ |
| Headern | `ifc_header` på `IfcModel` |
| En instans i ett block | Text i ett `StepBlock`; det som refererar till den har dess id i märkt JSON |

Den här formen läses inte med IfcOpenShell, som här bara står för schemat. Det
ändrar vissa värden vid läsning (`.NULLENUM.` blir `$`, och `($,$)` blir `()`),
och filer från Tekla och Archicad har sådana. Därför läser arbetsprocessen filen
själv och refuserar det den inte kan läsa.
[ADR 0010](../adr/0010-a-lossless-graph-reads-and-writes-step-itself.md) säger varför.

`--verify` frågar om de två filerna rymmer samma modell, enligt definitionen i
[ADR 0009](../adr/0009-what-makes-two-ifc-files-the-same-model.md): ett till ett,
värde för värde och utan tolerans, med georeferensen namngiven i rapporten. Med
`--geometry` byggs också varje produkts mesh, och de jämförs bit för bit. Två valfria filer kan jämföras med
`python -m opencde.ifcgraph.equivalence first.ifc second.ifc`.

## Underhåll

Varje uppladdning av en IFC-fil lägger till en `IfcModel` med sina entiteter,
så ett projekt som får nya versioner samlar på sig grafer som ingen frågar.
Kommandoraden listar och rensar dem; dokumenten och deras filer finns alltid
kvar:

```sh
uv run opencde ifcgraph list --project <projekt-id>
uv run opencde ifcgraph prune                   # misslyckade modeller, och färdiga modeller ersatta av en nyare
                                                # färdig version av samma dokument
uv run opencde ifcgraph prune --project <id> --all   # varje modell i ett projekt (en teststack, till exempel)
```

Köade och pågående modeller rensas aldrig. Frågor som vill ha en graf per
dokument bör själva välja den senaste färdiga modellen, eftersom äldre
versioner finns kvar tills de rensas:

```cypher
MATCH (:Project {project_id: $project})-[:HAS_MODEL]->(m:IfcModel {state: 'done'})
WITH coalesce(m.document_id, m.bcf_document_guid) AS doc, m
ORDER BY m.version_index DESC, m.done_at DESC
WITH doc, collect(m)[0] AS latest
MATCH (e:IfcProduct {model_id: latest.id})
RETURN latest.file_name AS model, count(e) AS products
```

## Koppla BCF-komponenter

När en viewpoint skapas med komponenter får varje komponent vars `ifc_guid`
matchar `GlobalId` hos en byggnadsdel i någon av projektets importerade
modeller en `SAME_AS`-relation till den. Samma koppling körs för varje
befintlig komponent i projektet när en modell blir färdigimporterad, så
viewpoints som skapats innan modellen laddades upp, eller medan den ännu
konverterades, kopplas också. Om byggnadsdelen bär den konfigurerade
egenskapen (`OPENCDE_IFCGRAPH_GTIN_PROPERTY_SET=Reuse`,
`OPENCDE_IFCGRAPH_GTIN_PROPERTY=GTIN`) kopieras dess värde till komponenten
som `gtin`. Detta är användningsfallet i forskningsrapporten från 2023: en
kontroll (BCF-ärende) som pekar på byggprodukter identifierade med GTIN.

```cypher
// Vilka produkter pekar den här viewpointen på, och vilka GTIN har de?
MATCH (:Viewpoint {guid: $viewpoint})-[:HAS_COMPONENT]->(c:Component)-[:SAME_AS]->(e:IfcProduct)
RETURN c.ifc_guid, e.Name, c.gtin
```

```cypher
// Rapportens fråga, direkt på modellen: GTIN för varje vägg.
MATCH (w:IfcWall)-[:IS_DEFINED_BY]->(:IfcRelDefinesByProperties)-[:RELATING_PROPERTY_DEFINITION]
      ->(:IfcPropertySet {Name: 'Reuse'})-[:HAS_PROPERTIES]->(p:IfcPropertySingleValue {Name: 'GTIN'})
RETURN w.GlobalId, w.Name, p.NominalValue
```

```cypher
// Varje ärende som berör en given byggnadsdel.
MATCH (e:IfcEntity {GlobalId: $guid})<-[:SAME_AS]-(:Component)<-[:HAS_COMPONENT]-(v:Viewpoint)<-[:HAS_VIEWPOINT]-(t:Topic)
RETURN DISTINCT t.server_assigned_id, t.title, t.topic_status
```

BCF-tjänsten `files_information` visar importerade modellers
`IfcProject`-guid som `ifc_project`, vilket låter klienter fylla i filerna i
ärendets huvud.

## Fråga från Dataspatium

[Dataspatium](https://github.com/marwiss/Dataspatium), webbläsarklienten som
utvecklas tillsammans med den här servern, kör Cypher mot den här grafen
genom sin Neo4j-källa över Bolt (WebSocket på Bolt-porten) när operatören
exponerar databasen, som utvecklingsöverlagringen gör på `127.0.0.1:7697`.
Dess Kontroll-arbetsyta använder mönstren ovan (modeller, klasser,
komponenter via `SAME_AS`, den senaste färdiga modellen per dokument);
frågorna finns i Dataspatiums dokumentation (`docs/grafer.md`), och
live-körningarna listas i [acceptance.md](../acceptance.md). En
produktionsserver publicerar inte Bolt; administrations-API:ts graffråga
(`OPENCDE_GRAPH_QUERY_ENABLED`, [client-guide.md §7](client-guide.md)) ger
administratörer läsande Cypher utan porten. Appen ritar också
grafen, i sitt kort IFC-graf, genom den frågan eller över Bolt.

## Gränser och status

- En konvertering i taget; stora modeller köas. Exempelmodellen (248
  entiteter) importeras på ungefär en sekund; en arkitektmodell på 200 MB tar
  minuter.
- `IfcModel`-noden bär `state`, `entities`, `relationships`, `skipped`,
  `lossless`, `schema`, `ifc_project_guid`, tidsstämplar och `error`. Administratörer kan
  granska den i Neo4j Browser eller Memgraph Lab:
  `MATCH (m:IfcModel) RETURN m.file_name, m.state, m.entities, m.error`.
- När ett projekt tas bort tas dess modellers entiteter bort med det.
- En modell kommer tillbaka identisk från båda databaserna upp till 224 496 instanser och
  19 MB, i varje form som mätts. Inget större har provats.
