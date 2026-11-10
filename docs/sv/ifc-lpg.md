# IFC-LPG

Den valfria IFC-LPG-modulen gör en uppladdad IFC-modell till grafdata, så att
komponenterna i en BCF-viewpoint kan kopplas till de byggnadsdelar de pekar
på, och så att frågor om modellen kan ställas i Cypher bredvid ärendena och
dokumenten.

Slå på den med `OPENCDE_IFC_LPG_ENABLED=true` och installera extrapaketet
`ifc-lpg` (`uv sync --extra ifc-lpg`). Docker-avbildningen innehåller
extrapaketet som standard (`ARG OPENCDE_EXTRAS` i Dockerfile), vilket mer än
dubblar dess storlek (ungefär 680 MB mot 300 MB); bygg med
`--build-arg OPENCDE_EXTRAS=` för en slankare avbildning utan IfcOpenShell
när modulen förblir avstängd.

Fram till november 2026 hette modulen IFC-graph. Dess inställningar hette
`OPENCDE_IFCGRAPH_*` och kommandot `opencde ifcgraph`, och båda fungerar
fortfarande; serverns logg och `opencde doctor` nämner de gamla inställningar
den får.

## Vad som händer vid uppladdning

1. En Documents API-uppladdning slutförs (eller en fil laddas upp från
   urvalssidan, eller ett BCF-projektdokument postas) med ett `.ifc`- eller
   `.ifczip`-namn.
2. Servern skapar en `IfcModel`-nod (tillstånd `queued`) kopplad till
   projektet och startar en konvertering i bakgrunden, en i taget.
3. En separat arbetsprocess (`python -m opencde.ifcgraph.worker`) tolkar
   filen med IfcOpenShell. Den körs med en tidsgräns
   (`OPENCDE_IFC_LPG_TIMEOUT_SECONDS`, 15 minuter), en adressrymdsgräns på
   POSIX (`OPENCDE_IFC_LPG_MEMORY_MB`, 4 GiB) och ett tak för antalet
   entiteter (`OPENCDE_IFC_LPG_MAX_ENTITIES`). En krasch eller en hängning
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

Utelämnas som standard (`OPENCDE_IFC_LPG_INCLUDE_GEOMETRY=false`):
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
graf: en relation säger inte var i en lista dess mål stod.

## Underhåll

Varje uppladdning av en IFC-fil lägger till en `IfcModel` med sina entiteter,
så ett projekt som får nya versioner samlar på sig grafer som ingen frågar.
Kommandoraden listar och rensar dem; dokumenten och deras filer finns alltid
kvar:

```sh
uv run opencde ifc-lpg list --project <projekt-id>
uv run opencde ifc-lpg prune                   # misslyckade modeller, och färdiga modeller ersatta av en nyare
                                                # färdig version av samma dokument
uv run opencde ifc-lpg prune --project <id> --all   # varje modell i ett projekt (en teststack, till exempel)
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
egenskapen (`OPENCDE_IFC_LPG_GTIN_PROPERTY_SET=Reuse`,
`OPENCDE_IFC_LPG_GTIN_PROPERTY=GTIN`) kopieras dess värde till komponenten
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
Dess Dataregium-arbetsyta använder mönstren ovan (modeller, klasser,
komponenter via `SAME_AS`, den senaste färdiga modellen per dokument);
frågorna finns i Dataspatiums dokumentation (`docs/grafer.md`). En
produktionsserver publicerar inte Bolt; administrations-API:ts graffråga
(`OPENCDE_GRAPH_QUERY_ENABLED`, [client-guide.md §7](client-guide.md)) ger
administratörer läsande Cypher utan porten. Appen ritar också
grafen, i sitt kort IFC-LPG, genom den frågan eller över Bolt.

## Gränser och status

- En konvertering i taget; stora modeller köas. Exempelmodellen (248
  entiteter) importeras på ungefär en sekund; en arkitektmodell på 200 MB tar
  minuter.
- `IfcModel`-noden bär `state`, `entities`, `relationships`, `skipped`,
  `schema`, `ifc_project_guid`, tidsstämplar och `error`. Administratörer kan
  granska den i Neo4j Browser eller Memgraph Lab:
  `MATCH (m:IfcModel) RETURN m.file_name, m.state, m.entities, m.error`.
- När ett projekt tas bort tas dess modellers entiteter bort med det.
