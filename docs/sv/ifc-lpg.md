# IFC-LPG

Den valfria IFC-LPG-modulen gör en uppladdad IFC-modell till grafdata, så att
komponenterna i en BCF-viewpoint kan kopplas till de byggnadsdelar de pekar
på, och så att frågor om modellen kan ställas i Cypher bredvid ärendena och
dokumenten.

Slå på den med `OPENCDE_IFC_LPG_ENABLED=true` och installera extrapaketet
`ifc-lpg` (`uv sync --extra ifc-lpg`). Docker-avbildningen innehåller
extrapaketet som standard (`ARG OPENCDE_EXTRAS` i Dockerfile), vilket mer än
dubblar dess storlek (ungefär 680 MB, eller 1,1 GB med buildingSMARTs regler, mot 300 MB); bygg med
`--build-arg OPENCDE_EXTRAS=` för en slankare avbildning utan IfcOpenShell
när modulen förblir avstängd.

Fram till november 2026 hette modulen IFC-graph. Dess inställningar hette
`OPENCDE_IFCGRAPH_*` och kommandot `opencde ifcgraph`, och båda fungerar
fortfarande; serverns logg och `opencde doctor` nämner de gamla inställningar
den får.

Konverteringen, skrivningen av en fil och kontrollerna kommer från biblioteket
[IFC-LPG](https://github.com/marwiss/IFC-LPG), som Dataregium installerar från dess
repo vid en bestämd commit och vars README beskriver hur en modell lagras i
grafen. Serverns egen process använder den del som inte behöver IfcOpenShell;
extrapaketet `ifc-lpg` lägger till de arbetsprocesser som gör det.

## Vad som händer vid uppladdning

1. En Documents API-uppladdning slutförs (eller en fil laddas upp från
   urvalssidan, eller ett BCF-projektdokument postas) med ett `.ifc`- eller
   `.ifczip`-namn.
2. Servern skapar en `IfcModel`-nod (tillstånd `queued`) kopplad till
   projektet och startar en konvertering i bakgrunden, en i taget.
3. En separat arbetsprocess (`python -m ifc_lpg.worker`) läser
   filen. Den körs med en tidsgräns
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

## Kontroll av uppladdningar mot IFC-schemat

Varje `.ifc`- eller `.ifczip`-fil som laddas upp som dokumentversion kontrolleras
också mot IFC-schemat, med samma validerare som kontrollerar en skriven fil
([Skriva tillbaka en modell](#skriva-tillbaka-en-modell)): attributens typ och
antal, uppräkningar, inversa attribut, GlobalId och reglerna i EXPRESS-schemat.
Kontrollen körs i bakgrunden före konverteringen, i en arbetsprocess med samma
gränser. Den stoppar aldrig en uppladdning: filen sparas som den kom, vad
kontrollen än hittar. Ett BCF-projektdokument kontrolleras inte, eftersom det
saknar metadata. `OPENCDE_IFC_LPG_VALIDATE_UPLOADS=false` stänger av kontrollen.

Resultatet finns i versionens metadata, som varje klient för Documents API kan läsa:

| Post | Typ | Värde |
|---|---|---|
| `ifc_validation_status` | `string` | `pending` tills filen är kontrollerad, sedan `passed`, `warnings` när varje anmärkning är en varning, `issues` när minst en är ett fel, eller `unknown` när den inte gick att kontrollera |
| `ifc_validation_issues` | `integer32` | Hur många anmärkningar filen har |
| `ifc_validation_checked_at` | `date-time` | När den kontrollerades |
| `ifc_validation_ruleset` | `string` | Vad den kontrollerades med, ett värde per kontroll |
| `ifc_validation_report` | `url` | Var rapporten finns |

Rapporten är ett tillägg till Documents API. Varje medlem i projektet får den med
samma Bearer-token:

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

Den listar upp till 10 000 anmärkningar, var och en med sin instans och, för en
rotad entitet, dess GlobalId, så att en modellvy kan hitta elementet. `kind` säger
vad som hittade anmärkningen: `schema`, `entity_rule`, `simpletype_rule` eller
`global_rule` i IFC-schemat, eller `gherkin` för en av buildingSMARTs regler,
vars kod står i `rule`. `checks` håller isär kontrollerna. Ett meddelande kan
citera en rad ur filen och kortas vid 1 000 tecken. Versionens sida i webbläsaren visar de första 100 anmärkningarna och
erbjuder hela rapporten som fil.

Många filer bryter redan mot någon regel när de kommer från sitt program: 12 av
26 exempelfiler gör det, en från Tekla med 5 711 anmärkningar. Att kontrollera en
exempelfil och dess skrivna kopia tog 3 till 66 sekunder tillsammans.

### buildingSMARTs ifc-gherkin-rules

När `OPENCDE_IFC_LPG_GHERKIN_ENV` pekar ut en miljö för dem kontrolleras
uppladdningar också mot buildingSMARTs `ifc-gherkin-rules`: de normativa
reglerna och den branschpraxis som buildingSMARTs valideringstjänst kontrollerar
utöver schemat (ADR 0012).
De körs efter schemakontrollen, i samma slags arbetsprocess med samma gränser,
och så som regeluppsättningens egna tester kör dem: med behave och IfcOpenShell
0.8.6, som regeluppsättningens CI använder. På regeluppsättningens 722 testfiler
ger det det utslag som dess tester väntar sig för varenda en.

Reglerna får en egen miljö, eftersom en av deras hjälpfunktioner inte fungerar
med den IfcOpenShell 0.9 som Dataregium använder.
`python -m ifc_lpg.gherkin_install <mapp>` gör den av fastlåsta
nedladdningar, var och en kontrollerad mot sin SHA-256: regeluppsättningen vid
en bestämd commit, IfcOpenShells bygge av 0.8.6 för plattformen och
Python-paketen med sina hashar. Två små filer från IFC-LPG ersätter
regeluppsättningens Django-delar, som bara skriver resultat till
valideringstjänstens databas.
Den publicerade avbilden utelämnar dem, eftersom de lägger till omkring 425 MB.
Avbilden med taggen `-gherkin`, som `latest-gherkin` eller `3.0.0-gherkin`, har
miljön i `/opt/gherkin` och låter `OPENCDE_IFC_LPG_GHERKIN_ENV` peka på den,
liksom en avbild byggd med `--build-arg OPENCDE_GHERKIN=1`. Med docker compose
väljer `OPENCDE_IMAGE_TAG` eller `OPENCDE_GHERKIN=1` i `.env`.

Ett fynd av en regel är en anmärkning av sorten `gherkin`, med regelns kod, som
`IFC106`, och allvarlighetsgraden `error` eller `warning`. Regler för
branschpraxis varnar bara, och en fil vars anmärkningar alla är varningar får
statusen `warnings`, eftersom buildingSMARTs valideringstjänst håller en sådan
fil för giltig. En regel som kastade ett undantag i stället för att hitta något
saknar utslag och listas under `rules_not_run` i sin kontroll. Om reglerna inte
går att köra alls blir deras kontroll `failed`, och schemats kontroll står för
sig själv.

Reglerna tar längre tid än schemakontrollen: på åtta exempelmodeller från 5
sekunder för den minsta till omkring 5 minuter för den största, och mellan en
halv och två minuter för de flesta.

### Information Delivery Specifications (IDS)

En uppladdning kontrolleras också mot varje IDS-dokument i sitt projekt: ett
dokument vars senaste version har ett namn som slutar på `.ids`, högst 50
(ADR 0015).
IFC-LPG:s kontroll läser varje IDS säkert och lämnar den till IfcOpenShells
IfcTester, samma kontrollant som Dataspatium kör i webbläsaren, så att de två
ger samma utslag. Den körs efter de andra kontrollerna, i samma slags
arbetsprocess med samma gränser. En IDS som laddas upp senare gäller de
IFC-versioner som laddas upp efter den.

Varje krav som ett element inte uppfyller blir en anmärkning av slaget `ids`,
med allvarligheten `error`, specifikationens identifierare eller namn i `rule`
och IDS-dokumentet i `document_id`. Det blir också en obligatorisk specifikation
som inte gäller något i filen, och ett element som en förbjuden specifikation
gäller. Rapportens kontroll `ids` listar dokumenten den använde, med version,
och varje specifikation med dess användning, utslag (`passed`, `failed` eller
`not applicable`), hur många element den gäller och hur många anmärkningar den
gav. Ett IDS-dokument som inte kan läsas, till exempel ett med en DTD, listas
under `rules_not_run` med skälet, och de andra kontrolleras ändå. Versionens
sida visar specifikationerna i en egen tabell.

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

Inga noder som standard (`OPENCDE_IFC_LPG_INCLUDE_GEOMETRY=false`):
representationsobjekt, representationer, profiler, placeringar och stilar; de
utgör merparten av en modell och är sällan vad en CDE-fråga behöver, och de finns
kvar som text i grafen, enligt Skriva tillbaka en modell. `IfcOwnerHistory` är en
nod bara för `IfcProject`.

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

- Geometri blir inte noder om det inte efterfrågas. Artikeln konverterar allt och
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

Artikeln påpekar att dess graf förlorar ordningen i listor, eftersom en relation
inte säger var i en lista dess mål stod. Här säger `position` det.

## Skriva tillbaka en modell

Grafen rymmer hela modellen, och filen kan skrivas tillbaka från den: samma
instanser med samma id, och samma värden i samma ordning, alltså också samma
geografiska information.

```sh
uv run opencde ifc-lpg export <modell-id> model.ifc            # skriv filen och validera den
uv run opencde ifc-lpg export <modell-id> model.ifc --verify   # och jämför den med den uppladdade
```

Noderna är de som frågor behöver. Det de utelämnar skrivs ut som STEP och
komprimeras till text på `StepBlock`-noder som hänger på `IfcModel`: det finns i
grafen men utom räckhåll för Cypher, och det kan inte ändras där. Det kan inte vara
egenskaper på produkterna, eftersom mycket av det delas mellan dem. Med
`OPENCDE_IFC_LPG_INCLUDE_GEOMETRY=true` blir varje instans en nod i stället, till
flera gånger storleken och importtiden; frågor tog ungefär lika lång tid i
mätningarna.

| I filen | I grafen |
|---|---|
| En referens | En relation med `position`, `[rad, kolumn]` i en lista av listor; inversa relationer har ingen |
| En referens till en instans i ett block | Dess id, som i `Representation__step: 1234` |
| Ett typat värde, `IFCLABEL('3')` | `NominalValue: "3"`, och `NominalValue__type: "IFCLABEL"` bredvid |
| En lista av listor av tal | JSON-text |
| Det som saknar enkel form, som en lista av typade värden | Märkt JSON, med `$json` som typ |
| Headern | `ifc_header` på `IfcModel` |
| En instans i ett block | Text i ett `StepBlock` |

Filen skrivs från det grafen rymmer och kopieras inte, så en egenskap eller en
relation som ändras i grafen syns i den. En grafdatabas har inget schema att hålla
en ändring mot, så filen valideras mot IFC-standarden med IfcOpenShells validerare:
attributens typ och antal, uppräkningar, inversa attribut, GlobalId och reglerna i
EXPRESS-schemat. Filer som används bryter ofta redan mot någon regel, så det som
räknas är en anmärkning som den uppladdade filen inte har. Kommandot listar den då
och slutar med ett fel. `--no-validate` hoppar över detta. En export avbryts också
om ett block saknas.

Projektmedlemmar får filer genom Documents API, och det finns ingen annan väg ut ur
servern. En skriven fil som ska ersätta en modell laddas upp som en ny version av
sitt dokument, vilket också konverterar den.

Den här formen läses inte med IfcOpenShell, som här bara står för schemat.
IfcOpenShell ändrar vissa värden vid läsning (`.NULLENUM.` blir `$`, och `($,$)` blir
`()`), och filer från Tekla och Archicad har sådana. Därför läser arbetsprocessen
filen själv och refuserar det den inte kan läsa. ADR 0010 säger varför,
och ADR 0011 hur en fil valideras.

`--verify` frågar om de två filerna rymmer samma modell, enligt definitionen i
ADR 0009: ett till ett, värde för värde och utan tolerans, med
georeferensen namngiven i rapporten. Med `--geometry` byggs också varje produkts
mesh, och de jämförs bit för bit. Två valfria filer kan jämföras med
`python -m ifc_lpg.equivalence first.ifc second.ifc`.

Med `OPENCDE_IFC_LPG_LOSSLESS=false` konverteras en modell som före 3.0.0: den läses
med IfcOpenShell, och det som inte är noder utelämnas helt. En sådan modell, liksom
en som konverterats av en tidigare version, kan inte skrivas tillbaka.

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

## Namngivna frågor

En medlem i ett projekt ställer frågor till en versions modell med namn, med
samma bearer-token som för Documents API; fri Cypher förblir administratörernas
(ADR 0016).
`GET /documents/1.0/documents/{id}/versions/{index}/ifc-queries` listar
frågorna med deras parametrar och kolumner och säger i `model_state` hur långt
konverteringen av modellen har kommit. `GET …/ifc-queries/{name}` ställer en
fråga, med parametrarna i frågesträngen, och svarar med kolumnerna och raderna,
varje rad en lista i kolumnernas ordning:

```http
GET /documents/1.0/documents/{id}/versions/1/ifc-queries/property?pset=Reuse&property=GTIN
```

```json
{"name": "property", "columns": ["global_id", "class", "name", "value", "type"],
 "rows": [["1Xezbq735AdBO_4DerG66G", "IfcWallStandardCase", "YVT-A", "3", "IFCLABEL"]],
 "truncated": false}
```

| Fråga | Parametrar | Vad den svarar på |
|---|---|---|
| `element-classes` | | Hur många element modellen har av varje klass |
| `elements` | `class` | Elementen av en klass, med den rumsliga struktur som innehåller vart och ett |
| `storeys` | | Våningarna, deras nivå och hur många element och rum var och en rymmer |
| `spaces` | | Rummen, deras våning och deras netto- och bruttogolvarea |
| `areas` | | Nettogolvarean för varje vånings rum, summerad |
| `materials` | `class` | Varje elements material: ett eget, eller dess skikts, listas eller beståndsdelars |
| `property` | `pset`, `property`, `class` | Värdet av en egenskap på varje objekt som har den, med dess IFC-typ |

`class` namnger en IFC-klass, till exempel `IfcWall`, och tar med sig dess
underklasser: obligatorisk för `elements`, valfri för de andra. Ett svar rymmer
högst 10 000 rader, och `truncated` säger när det fanns fler; en fråga avbryts
efter 10 sekunder. Varje fråga börjar vid medlemmen och når modellen genom
projektet, läser bara och tar sina värden som parametrar. En version utan
modell, eller en som användaren inte får se, svarar 404, och en vars modell
fortfarande konverteras svarar 409. Kapabilitetsdokumentet annonserar frågorna
i `ifc_queries`.

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
  `lossless`, `schema`, `ifc_project_guid`, tidsstämplar och `error`. Administratörer kan
  granska den i Neo4j Browser eller Memgraph Lab:
  `MATCH (m:IfcModel) RETURN m.file_name, m.state, m.entities, m.error`.
- När ett projekt tas bort tas dess modellers entiteter bort med det.
- En modell kommer tillbaka identisk från båda databaserna upp till 224 496 instanser och
  19 MB, i varje form som mätts. Inget större har provats.
