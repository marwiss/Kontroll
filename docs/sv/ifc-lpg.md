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
2. Servern skapar en `Conversion`-post (tillstånd `queued`) kopplad till
   projektet och startar en konvertering i bakgrunden, en i taget.
3. En separat arbetsprocess (`python -m ifc_lpg.worker`) läser
   filen. Den körs med en tidsgräns
   (`OPENCDE_IFC_LPG_TIMEOUT_SECONDS`, 15 minuter), en adressrymdsgräns på
   POSIX (`OPENCDE_IFC_LPG_MEMORY_MB`, 4 GiB) och ett tak för antalet
   entiteter (`OPENCDE_IFC_LPG_MAX_ENTITIES`). En krasch eller en hängning
   dödar arbetsprocessen, inte servern. `.ifczip` packas upp med
   uppladdningens storleksgräns.
4. Posterna importeras i batchar av `UNWIND … CREATE` (portabel Cypher,
   ingen APOC). `Conversion` hamnar i tillståndet `done` med antal och
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
gränser. Som standard stoppar den aldrig en uppladdning: filen sparas som den kom,
vad kontrollen än hittar; ett projekt kan välja annorlunda ([nedan](#avvisa-filer-med-fel-och-kontrollera-en-fil-i-förväg)). Ett BCF-projektdokument kontrolleras inte, eftersom det
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

Ett fynd som pekar ut en instans har också dess klass i `ifc_class` och, i
`root_global_id`, GlobalId för den närmaste rotade entitet som når den: dess
eget för en rotad entitet, och för en `IfcPolyline` i konturen till en väggs
kropp, som GEM111 hittar, väggens. Den når instansen som IFC-LPG:s sökvägar
gör, framåt genom attribut och bakåt genom inversa attribut. En arbetsprocess
läser båda ur filen, så modellen behöver inte vara konverterad, medan
`global_id` förblir instansens eget. Versionens sida visar klassen bredvid
instansen, och elementets GlobalId där instansen saknar ett, så att också en
klient kan peka ut elementet. Ett fynd som inte pekar ut någon instans står
kvar som det är, och ett vars instans ingenting når har bara sin klass.

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
arbetsprocess med samma gränser. En ny version av ett IDS-dokument gör att den senaste versionen av varje IFC-dokument i projektet kontrolleras
om, högst 500, så att dess rapport följer kraven som de är nu; äldre versioner behåller den rapport de hade.

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

### buildingSMART Data Dictionary (bSDD)

Med `OPENCDE_BSDD_ENABLED=true` kontrolleras en uppladdning också mot buildingSMARTs Data Dictionary, efter
IDS-kontrollen. En arbetsprocess läser filens hänvisningar dit: varje `IfcClassificationReference` vars `Location` är
en bSDD-URI, som `https://identifier.buildingsmart.org/uri/molio/cciconstruction/1.0/class/L-BD`, eller vars
`Identification` (`ItemReference` i IFC2X3) är en kod i den ordbok vars URI dess `Location` eller dess klassificering
har, med objekten den sitter på; varje egenskap i en egenskapsmängd vars `Specification` (IFC 4.3), eller
`Description` i ett tidigare schema, är URI:n för en egenskap i bSDD, som
`https://identifier.buildingsmart.org/uri/buildingsmart/ifc/4.3/prop/FireRating`, med objekten som dess mängd sitter
på; och egenskaperna i varje egenskapsmängd som heter `Pset_…` eller `Qto_…`. En annan arbetsprocess läser de
bSDD-URI:er som projektets IDS-dokument anger i `uri` på sina klassificerings- och egenskapsfacetter, en gång för
varje version av ett dokument och på samma sätt som IDS-kontrollen läser det. Servern frågar sedan bSDD:s API på
`OPENCDE_BSDD_API_URL` (`https://api.bsdd.buildingsmart.org`) om varje URI, med en tidsgräns för varje fråga
(`OPENCDE_BSDD_TIMEOUT_SECONDS`, 10 sekunder) och två nya försök när bSDD svarar 429 eller 5xx, och behåller varje
svar i minnet ett dygn (`OPENCDE_BSDD_CACHE_SECONDS`, 86400; 0 frågar varje gång), så att bSDD bara tillfrågas en gång
om en URI som flera filer eller IDS-dokument namnger. Inget som filen namnger hämtas: en URI går till bSDD:s API som
en parameter, och en på en annan värd än `identifier.buildingsmart.org` rapporteras i stället. Kontrollen är avstängd
som standard, eftersom den skickar URI:erna i filen och i IDS-dokumenten, och namnen på filens egenskapsmängder, till
bSDD; i produktion måste adressen vara https.

Allt den hittar är en varning av slaget `bsdd`, med klassificeringsreferensen, egenskapen eller egenskapsmängden i
`step_id`, GlobalId för ett av objekten den sitter på i `global_id` och objektets klass i meddelandet:

- en klassificeringsreferens vars klass eller egenskap bSDD inte känner till, med ordboken i `rule` och attributet som
  namnger den i `attribute`; en modell kan använda en ordbok som bSDD inte har publicerat;
- en egenskap vars `Specification` eller `Description` namnger en egenskap som bSDD inte känner till, med ordboken i
  `rule` och mängden och egenskapen i `attribute`, som `Pset_WallCommon.FireRating`;
- i en fil i IFC 4.3, en egenskapsmängd som bSDD:s IFC-ordbok (`buildingsmart/ifc/4.3`) inte har, eller en egenskap
  som den inte listar i den mängden, med mängden och egenskapen i `attribute`, som `Pset_WallCommon.Colour`;
- en URI i ett av projektets IDS-dokument som bSDD inte känner till, med ordboken i `rule`, dokumentet i
  `document_id` och dess specifikation och facett i meddelandet, men varken `step_id` eller `global_id`, eftersom den
  inte säger något om filen: den står i rapporten för varje fil som kontrolleras mot dokumentet, och prövningen av ett
  ändringsset räknar den aldrig till sina egna fynd.

bSDD publicerar bara den IFC-ordboken, så egenskapsmängderna i en fil i IFC4 eller IFC2X3, vars scheman definierar dem
på annat sätt, kontrolleras inte; och `Reference`, som IFC 4.3 ger nästan varje egenskapsmängd och bSDD utelämnar ur
dem alla, rapporteras inte. Kontrollens `ruleset` namnger bSDD:s värd och ordböckerna som filen och dess IDS-dokument
kontrollerades mot. Den läser högst 1 000 referenser, 1 000 egenskaper som namnger bSDD och 500 egenskapsmängder i en
fil, och 1 000 URI:er i ett IDS-dokument, och en varning säger till när en fil eller ett dokument har fler. Ett
IDS-dokument som inte går att läsa lämnas åt IDS-kontrollen, som rapporterar det. När bSDD inte går att nå, eller inte
svarar som dess API gör, är kontrollen `failed` med skälet i sitt `error`, och de andra kontrollerna står sig: att
bSDD inte går att nå är aldrig ett fel i modellen. Förhandskontrollen och prövningen av ett ändringsset gör också
kontrollen, och kapabilitetsdokumentet säger om den är på, som `bsdd` i `ifc_validation`.

### Rummen på varje våning

Med `OPENCDE_ROOMS_ENABLED=true` får rapporten för en uppladdning, en förhandskontroll och en prövning också rummen på
varje våning, funna ur dess väggar så som Dataspatium finner dem: en arbetsprocess kör en kopia av appens kod med
IfcOpenShell och shapely, efter kontrollerna och med samma gränser. En väggs mittlinje är dess `Axis`-representation,
som väggarna Dataspatium gör har, eller annars den långa axeln i dess kropps fotavtryck; ändarna fogas samman inom
halva våningens tjockaste vägg plus 0,05 m, och de mittlinjer som sluter minst 0,5 m² och 0,5 m i bredd bildar ett
rum. Rapportens `rooms` har varje våning, i höjdordning, med:

- `rooms`: varje rums `index` på våningen, dess `area` (m²) och `perimeter` (m) längs mittlinjerna, GlobalId för dess
  `walls` och dess `neighbours` efter index;
- `external`: väggarna längs rummens utsida, var och en med sitt `global_id`, `name`, sin `length` där och det
  väderstreck den vetter mot (`facing`, `N`, `NE` … `NW`), med norr från kartkonverteringen, annars `TrueNorth`,
  annars modellens y-axel, som `north` säger (`map`, `true_north` eller `model`);
- `dangles` och `dangling_walls`: de lösa väggändarna, `[x, y]` i meter i modellens plan, och deras väggar;
- `closed`: om våningen har ett rum och ingen lös ände;
- `walls`, `unread` och `unread_walls`: hur många väggar våningen har, och hur många och vilka som inte gav någon
  mittlinje;
- `tolerance`: hur långt isär, i meter, två ändar får vara och ändå fogas samman.

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

Rummen är ett eget avsnitt och aldrig en anmärkning: de ändrar varken status eller antal, ett projekt som avvisar
filer med fel avvisar aldrig en fil för dess rum, och en prövning är `clean` eller `issues` hur dess rum än ser ut; de
är den tillämpade filens. Versionens sida visar en rad per våning med väggar. Listorna kapas vid 100 våningar, 500 rum
per våning och 200 poster i varje annan lista, och `cut` säger till, och en modell med fler än 2 000 väggar får inga.
När rummen inte går att hitta saknar rapporten `rooms`, och loggen säger varför (`ifc_rooms_failed`) utan det som
filen säger. Avstängt som standard; kapabilitetsdokumentet säger om det är på, som `rooms` i `ifc_validation`.

### Det den konverterade modellen visar

När modellen är konverterad får rapporten en egen kontroll, `graph`, med två slags anmärkningar. En instans som inget
med ett GlobalId når, framåt eller bakåt, är en varning av slaget `reachability`, med sitt STEP-id i `step_id` och sin
klass i meddelandet: bara det numret namnger den, som en placering som inget använder, så ett ändringsset kan peka ut
den bara med sitt STEP-id. En produkt vars form geometripasset inte kunde bygga är en anmärkning av slaget `geometry`,
med sitt GlobalId. Ingen av dem avvisar filen: de kommer efter uppladdningen, och en varning ger statusen `warnings`.
Innan modellen är konverterad har rapporten ingen kontroll `graph`.
En instans som hålls med geometrin i ett STEP-block, som en lös punkt, listas inte:
kontrollen ser bara noderna.

### Avvisa filer med fel, och kontrollera en fil i förväg

En administratör kan kryssa i *Avvisa uppladdningar med valideringsfel* på
projektets sida (`block_on_validation_errors` i administrations-API:et).
Kontrollerna körs då innan filen blir en version, i uppladdningens avslut och
på uppladdningssidan, och en fil med ett eller flera fel avvisas med
`422 ifc_validation_failed`; varningar släpps igenom. Den avvisade filen finns
kvar ett dygn som förhandskontroll, och `report` i felet säger var rapporten
finns. En fil som inte alls kunde kontrolleras släpps igenom, som `unknown`, så
att en trasig validerare aldrig stoppar arbetet. En fil som godkänns
kontrolleras en gång: resultatet blir versionens, som om kontrollen hade körts
efteråt.

Varje redaktör eller förvaltare kan också kontrollera en fil utan att göra den
till en version, med samma bearer-token och oavsett projektets inställning:

```http
POST /documents/1.0/projects/{project_id}/ifc-precheck
Content-Disposition: attachment; filename="model.ifc"
```

Kroppen är filen. Svaret är `202` med rapportens `url`, `pending` tills
kontrollerna är klara; sedan har den samma form som en versions rapport, med
filens namn och när förhandskontrollen går ut. Varje medlem läser den, i ett
dygn. Kapabilitetsdokumentet annonserar förhandskontrollen som `ifc_precheck`.

## Grafen

Varje entitet blir en `Entity`-nod som bär sin klass och alla sina
supertyper som etiketter, till exempel `Entity:IfcWallStandardCase:IfcWall:
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
- Relationstyperna skrivs med versaler, och kopian av GTIN till BCF-komponenterna
  är ett tillägg här.

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
komprimeras till text på `StepBlock`-noder som hänger på `Model`: det finns i
grafen men utom räckhåll för Cypher, och det kan inte ändras där. Det kan inte vara
egenskaper på produkterna, eftersom mycket av det delas mellan dem. Med
`OPENCDE_IFC_LPG_INCLUDE_GEOMETRY=true` blir varje instans en nod i stället, till
flera gånger storleken och importtiden; frågor tog ungefär lika lång tid i
mätningarna.
En stilsatt post (`IfcStyledItem`) är alltid en nod, så att varje stil kan ändras, och `form_version` på `Model` anger vilken form grafen har (2 sedan IFC-LPG:s utgåva 2026-11-10).

| I filen | I grafen |
|---|---|
| En referens | En relation med `position`, `[rad, kolumn]` i en lista av listor; inversa relationer har ingen |
| En referens till en instans i ett block | Dess id, som i `Representation__step: 1234` |
| Ett typat värde, `IFCLABEL('3')` | `NominalValue: "3"`, och `NominalValue__type: "IFCLABEL"` bredvid |
| En lista av listor av tal | JSON-text |
| Det som saknar enkel form, som en lista av typade värden | Märkt JSON, med `$json` som typ |
| Headern | `ifc_header` på `Model` |
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

Varje uppladdning av en IFC-fil lägger till en `Conversion` och en modell med sina entiteter,
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
MATCH (:Project {project_id: $project})-[:HAS_CONVERSION]->(m:Conversion {state: 'done'})
WITH coalesce(m.document_id, m.bcf_document_guid) AS doc, m
ORDER BY m.version_index DESC, m.done_at DESC
WITH doc, collect(m)[0] AS latest
MATCH (e:IfcProduct {model_id: latest.id})
RETURN latest.file_name AS model, count(e) AS products
```

## Koppla BCF-komponenter

När en viewpoint skapas med komponenter får varje komponent vars `ifc_guid`
matchar `GlobalId` hos en byggnadsdel i någon av projektets importerade
modeller värdet av den konfigurerade egenskapen
(`OPENCDE_IFC_LPG_GTIN_PROPERTY_SET=Reuse`, `OPENCDE_IFC_LPG_GTIN_PROPERTY=GTIN`)
som `gtin`, när byggnadsdelen har en: servern slår upp GlobalId i modellen
genom IFC-LPG:s `property_values` och sparar värdet på komponenten, och gör
ingen relation in i modellen; byggnadsdelen hittas genom sitt `GlobalId`. Samma
uppslag körs för varje befintlig komponent i projektet när en modell blir
färdigimporterad, så viewpoints som skapats innan modellen laddades upp, eller
medan den ännu konverterades, får också sina GTIN. Det är användningsfallet i
forskningsrapporten från 2023: en besiktning (BCF-ärende) som pekar på
byggprodukter identifierade med GTIN.

```cypher
// Vilka produkter pekar den här viewpointen på, och vilka GTIN har de?
MATCH (:Viewpoint {guid: $viewpoint})-[:HAS_COMPONENT]->(c:Component)
MATCH (e:IfcProduct {GlobalId: c.ifc_guid})
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
MATCH (:Component {ifc_guid: $guid})<-[:HAS_COMPONENT]-(v:Viewpoint)<-[:HAS_VIEWPOINT]-(t:Topic)
RETURN DISTINCT t.server_assigned_id, t.title, t.topic_status
```

BCF-tjänsten `files_information` visar importerade modellers
`IfcProject`-guid som `ifc_project`, vilket låter klienter fylla i filerna i
ärendets huvud.

## Namngivna frågor

En medlem i ett projekt ställer frågor till en versions modell med namn, med
samma bearer-token som för Documents API; fri Cypher förblir administratörernas
(ADR 0016).
Frågorna är IFC-LPG:s katalog (`ifc_lpg.queries`), så en som läggs till i
biblioteket dyker upp här.
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
| `storeys` | | Våningarna, deras nivå som filen anger den och i meter (`elevation_m`, ur attributet eller placeringen som `elevation_source` säger), och hur många element och rum var och en rymmer |
| `spaces` | | Rummen, deras våning och deras netto- och bruttogolvarea |
| `areas` | | Nettogolvarean för varje vånings rum, summerad, med våningens nivå i meter |
| `materials` | `class` | Varje elements material: ett eget, eller dess skikts, listas eller beståndsdelars |
| `property` | `pset`, `property`, `class` | Värdet av en egenskap på varje objekt som har den, med dess IFC-typ |
| `entity` | `global_id` | En rotad entitet: dess klass, varje literalt attribut och vad den refererar till och refereras av, var och en med IFC-attribut, STEP-id och klass |
| `site` | | Var byggnaden står: tomtens referenslatitud, -longitud och -höjd, och kartomvandlingen med sitt koordinatsystem (östlig och nordlig koordinat, höjd, vridning och skala) där modellen har en |
| `changed-since` | `since` | Vad som ändrats i dokumentet sedan en version: en rad per ändring i varje versions ändringsset fram till den här, eller en rad med `whole_file` för en version som laddats upp som hel fil; svaras ur versionerna, så den behöver ingen graf |

`class` namnger en IFC-klass, till exempel `IfcWall`, och tar med sig dess
underklasser: obligatorisk för `elements`, valfri för de andra. Ett svar rymmer
högst 10 000 rader, och `truncated` säger när det fanns fler; en fråga avbryts
efter 10 sekunder. Varje fråga börjar vid medlemmen och når modellen genom
projektet, läser bara och tar sina värden som parametrar. En version utan
modell, eller en som användaren inte får se, svarar 404, och en vars modell
fortfarande konverteras svarar 409. Kapabilitetsdokumentet annonserar frågorna
i `ifc_queries`.

## Ändringsset

En föreslagen ändring av en modell färdas som `bim_snippet` i ett BCF 3.0-ärende
(ADR 0021): `snippet_type` är `DataregiumIfcChangeSet`, `reference_schema` är
`GET /documents/1.0/ifc-changes/schema`, som vem som helst får läsa, och själva
snippeten laddas upp med `PUT …/topics/{guid}/snippet`, där servern håller den
till schemat och svarar `400` med vad som är fel. Ett nytt projekt tillåter
snippettypen; en administratör lägger till den bland ett äldre projekts värden.
Ett ändringsset anger sin basversion, vem som föreslog det, med AI-modellen och
verktygsanropet där en AI gjorde det, och sina ändringar, var och en på ett
attribut hos en instans. Instansen anges med ett GlobalId och en sökväg
från den rotade entiteten i IFC:s attributnamn med index, och med sitt STEP-id
bara när inget GlobalId når den. `set` ger attributet ett värde, `add` och `remove` ändrar en medlem i
ett aggregat, och `copy` begär en kopia av en instans som flera delar, som
annars ändras för alla. Ett värde är ett skalärt värde, en instans
(`{"step_id": 120}`, eller ett GlobalId med sökväg), ett typat värde
(`{"type": "IfcLengthMeasure", "value": 3.2}`), en uppräkning
(`{"enum": "NOTDEFINED"}`) eller en lista av dem. Kapabilitetsdokumentet
annonserar formen som `ifc_changes`. Vad ändringarna gör med modellen prövas när
förslaget prövas, nästa steg; i dag håller servern formen.

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

Bara en `editor` eller en `manager` i projektet föreslår ett ändringsset (ADR
0028): en `contributor` som laddar upp ett, också till ett eget ärende, får
`403` med skälet, och inget sparas, medan en snippet av en annan typ laddas upp
som förut. Detsamma gäller ändringssetet som servern föreslår nedan.

`delete` tar bort en instans som pekas ut med sitt STEP-id och som inget refererar till, som en som inget GlobalId
når; en instans som något fortfarande refererar till hoppas över och nämns i prövningen. Servern föreslår själv ett
sådant ändringsset med `POST /documents/1.0/projects/{id}/ifc-unreachable` och versionen som `document_id` och
`version_index`: den gör ett ärende vars snippet tar bort varje instans som versionens kontroll `graph` finner utom
räckhåll, och ändringssetet prövas och godkänns som alla andra, så versionen det kom från behåller instanserna. Svaret
namnger ärendet, hur många instanser det tar bort och var prövningen finns; `404` när versionen inte har någon
konverterad modell, och `409` när inget i den är utom räckhåll. Kapabilitetsdokumentet listar åtgärderna i
`ifc_changes.ops` och adressen som `ifc_changes.unreachable_url`.

Ett ändringsset som gjorts med Dataspatiums skrivverktyg bär också deras operationer som `ops`, med `ops_form`
`dataspatium-tools/1`, så att nya element, raderingar och samband kommer med i förslaget. Varje operation anger sitt
verktyg som `tool` och har verktygets argument bredvid sig, längder i meter: `create_storeys_and_grid`,
`create_wall`, `create_slab`, `create_roof`, `create_opening`, `create_spaces`, `set_properties`,
`set_classification`, `assign`, `transform_elements`, `delete_elements` och `set_site`. Servern kör dem med en kopia
av appens egen kod (`opencde/ifcgraph/ops.py`), så att samma operationer ger samma modell i appen och på servern, i
filens enhet, med den som föreslog och servern i de ägarhistoriker som IfcOpenShell gör. Det som vägg-, bjälklags-,
tak- och öppningsoperationerna skapar heter `new-1`, `new-2` … i deras ordning, och så gör varje rum som
`create_spaces` listar. En operation anger ett element med dess GlobalId, med dess STEP-id bara där inget GlobalId
når det, eller med en sådan ref, och en våning med dess namn. `create_wall` ger en vägg dess mittlinje som en
`Axis`-representation, och `create_spaces` gör rummen som väggarna sluter, funna så som rapportens `rooms` finns, till
utrymmen (`IfcSpace`) på sin våning, ur filen som den är vid det steget: vart och ett med rummets kontur upp till
nästa våning, `Qto_SpaceBaseQuantities` och fysiska utrymmesgränser mot väggarna längs dess kant och mot dörrarna och
fönstren i dem; en dörr eller ett fönster som görs senare i en sådan vägg gränsar också mot utrymmet.
`changes` får då vara tom: bredvid operationerna beskriver ändringarna vad operationerna gör
med befintliga instanser, så som appen fann det, för sammanfogningen, och en ändring som operationerna redan gjort
räknas som tillämpad. Kapabilitetsdokumentet annonserar formen som `ifc_changes.ops_form` och verktygen som
`ifc_changes.ops_tools`.

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

Prövningen tillämpar först operationerna och sedan ändringarna, och räknar båda i `change_count`. En operation som
inte kan tillämpas är en anmärkning av slaget `op` med sitt index (`op`) och `tool`, med orden i appens kod, som kan
citera dess argument och filen; operationerna efter den och ändringarna tillämpas inte, som i appen. Prövningen ger
också `created`, GlobalId för varje skapat element efter dess ref, så att klienten kan para ihop sina egna, och
`notes`, vad en operation inte kunde göra i filens schema, som kartkonverteringen i IFC2X3.

När IFC-LPG-modulen är på prövar servern varje ändringsset när det laddas upp:
en arbetare tillämpar ändringarna på basversionens fil, resultatet går genom
de kontroller en uppladdning får (IFC-schemat, buildingSMARTs regler och
projektets IDS-dokument), och prövningen är `clean` när varje ändring kunde
tillämpas och ingen anmärkning är ny jämfört med basversionens rapport, annars
`issues`. `GET /bcf/3.0/projects/{id}/topics/{guid}/ifc-proposal` ger
tillståndet, hur många ändringar som tillämpades och de nya anmärkningarna, var
och en som i en versions rapport; en ändring som inte kunde tillämpas är en
anmärkning av slaget `proposal` som säger varför, utan att citera filen. En ny
snippet ersätter prövningen, och prövningen följer med ärendet när det tas
bort. `ifc_changes` i kapabilitetsdokumentet säger om ändringsset prövas
(`tried`) och var prövningen finns (`proposal_url`).

`GET /documents/1.0/documents/{id}/ifc-proposals` listar de ändringsset som
prövats mot ett dokument, för en medlem i dess projekt, nyast först: per rad
ärendets guid, titel och de första 200 tecknen av dess beskrivning,
prövningens tillstånd, basversionen, hur många ändringar setet håller, vem
som föreslog det, när prövningen slutade, versionen det blev där det
godkändes, och adresserna till prövningen (`proposal_url`) och dess
godkännande (`approve_url`). Ett förslag namnger sin bas från det ögonblick
det köas, så listan håller det före prövningen och när prövningen
misslyckades. `$top` och `$skip` bläddrar i listan som i BCF-listorna; en
lista servern kapat bär `X-Total-Count` och `Link: <…>; rel="next"`. `404`
för ett dokument medlemmen inte får se, och när IFC-LPG-modulen är av.
Kapabilitetsdokumentet ger adressen som `ifc_changes.ifc_proposals_url`.

En `manager` godkänner en ren prövning med `POST …/ifc-proposal/approve`:
den tillämpade filen blir basdokumentets nästa version, med
`base_version_index`, `change_set_id` (ärendets guid), `proposed_by` och
`approved_by` i sina metadata, och AI-modellen och verktygsanropet där en AI
föreslog den; svaret är den nya versionen som Documents API ger den, och den
konverteras och kontrolleras som en uppladdning. Ärendet får en kommentar med
versionens adress, en viewpoint som markerar de ändrade elementen, och
statusen `Closed` där projektet har det värdet.
`412 version_conflict` säger att dokumentet har gått vidare sedan basen; `409`
att prövningen inte är ren, eller redan är godkänd. En AI föreslår bara:
godkännandet är en människas.
Där projektet har team listar prövningen i `teams` de team vars del av modellen
ändringssetet rör: det som specifikationerna i ett teams IDS-dokument gäller för, i
basens fil eller den ändrade. Ett ändringsset som rör ett enda teams del godkänns av
teamets ansvarige ensam, inte av en `manager`; ett som rör flera teams delar, eller
ingens, av en `manager`, och likaså ett vars delar inte kunde hittas (`teams_error`).

När dokumentet har gått vidare sedan basen sammanfogar servern: ändringarna i
versionerna däremellan, var och en godkänd från ett ändringsset, jämförs
attribut för attribut med förslagets. Krockar inga prövas ändringssetet på nytt
mot den senaste versionen, på en gång, och godkänns mot den, så att den nya
versionens bas är den senaste. Krockar några, eller laddades en version
däremellan upp som hel fil, är svaret `412 version_conflict` med de krockande
attributen i `conflicts` (`#123.Name`, eller GlobalId, sökväg och attribut; `*`
för en hel fil), så att klienten sammanfogar trevägs och skickar igen.

Instanserna jämförs, inte nycklarna klienterna skrev: varje ändring löses i
den version den gjordes på och namnges med sin kanoniska sökväg (IFC-LPG:s
`ifc_lpg.paths`), så att två ändringar som når en delad instans från olika
GlobalId ändå kolliderar, och `conflicts` namnger instansen med den sökvägen.
Bredvid ger `conflict_details` per kollision `key`, förslagets egna `guid`,
`path` eller `step_id`, `attribute` och `op`, vad basen höll (`base`), vad den
senaste versionen håller (`theirs`), vad förslaget sätter (`ours`), alla i
ändringssetets värdeform, och den mellanliggande version som ändrade det
(`version_index`); ett värde som inte kunde läsas är `null`. Klienten låter en
person välja per kollision, skickar en ny snippet på den senaste versionen och
godkänner igen. En klient som inte kan skära ut en enda ändring ur sina
operationer skickar dem igen med de nycklar den ger upp i `keep_theirs`, som
`conflicts` namngav dem: servern prövar då ändringssetet mot dokumentets
senaste version och ger vart och ett av de attributen tillbaka den senaste
versionens värde efter operationerna och ändringarna.

En version som bygger på en annan är en nod med sin förälder:
`parent_version_index` och en länk till förälderversionen, på en version
godkänd från ett ändringsset och på en uppladdning som angav
`base_version_index`. En version godkänd från ett ändringsset bär också
`approved_by`, `change_set_id` (ärendets guid) och själva ändringarna, som
`GET /documents/1.0/documents/{id}/versions/{index}/ifc-changes` ger i
schemats form, med basen och vem som föreslog och godkände den; en version
som laddats upp som hel fil svarar `404` där. Varje version är fortfarande en
hel fil, hämtad som förut; `opencde ifc-lpg prune` tar bort äldre versioners
grafer, eftersom huvudversionen och kedjan av ändringsset säger vad som
ändrades.

## Jämföra två versioner

En medlem jämför två IFC-versioner element för element, med samma bearer-token
som Documents API: en version med en annan av samma dokument, eller med
`?other_document_id=` en version av ett annat dokument i projektet.
Arbetaren parar de rotade entiteterna efter GlobalId och svarar med `added`
(bara den andra har dem), `removed` (bara den här har dem) och `changed` (i
båda, med attribut som skiljer sig), varje element angivet med GlobalId,
klass, namn och våning, och för ett ändrat de sökvägar som skiljer sig med
gammalt och nytt värde: ett direkt attribut med sitt namn, en egenskap som
`Pset.Property`, `ObjectPlacement` (4×4-matrisen), `Representation` (ett
fingeravtryck av formen), `Container` (våningen) och `Type`. Samband och
egenskapsmängder vävs in i elementen de hör till, och varje lista håller högst
10 000 element. Skillnaden räknas fram på begäran och lagras aldrig; en stor
modell tar en stund. Versionens sida erbjuder samma jämförelse som listor, och
kapabilitetsdokumentet annonserar den som `ifc_diff`.

```http
GET /documents/1.0/documents/{document_id}/versions/{version_index}/ifc-diff/{other_index}
```

## Krocktest

En medlem jämför två IFC-dokumentversioner i ett projekt med avseende på
krockar, med samma bearer-token som Documents API:
`POST /documents/1.0/projects/{project_id}/ifc-clash` med de två versionerna,
läget (`intersection`: element som går in i varandra djupare än `tolerance`;
`clearance`: element närmare varandra än `clearance`, båda i meter) och, om man
vill, varje sidas IFC-klasser. Testet körs i en arbetsprocess bakom
konverteringskön; svarets `url` ger rapporten, `done` eller `failed` efter en
stund. Varje krock namnger båda elementen (dokument, version, STEP-id, GlobalId,
klass, namn, våning), sitt slag, djupet eller avståndet och punkten där det
mättes, i den form Dataspatiums egen krockkärna skriver, så att appen visar
serverns resultat som sitt eget. `POST …/ifc-clash/{id}/topics` gör valda
krockar till BCF-ärenden med varsin viewpoint, bara på begäran.
Kapabilitetsdokumentet annonserar testet som `ifc_clash` när operatören har satt
`OPENCDE_IFC_LPG_CLASH_ENABLED=true`; en rapport behåller högst
`OPENCDE_IFC_LPG_CLASH_MAX_CLASHES` krockar.

```http
POST /documents/1.0/projects/{project_id}/ifc-clash
{"a": {"document_id": "…", "version_index": 1, "types": ["IfcWall"]},
 "b": {"document_id": "…", "version_index": 2},
 "mode": "intersection", "tolerance": 0.001}
```

## En byggnad in i en annan modell

En byggnad ur en modell kommer in i ett annat projekts modell som nästa version av
dess dokument; de två modellerna ändras inte. Modell A är en version i det här
projektet, modell B en version i vilket projekt som helst som anroparen är medlem i,
och båda ska vara konverterade, med samma schema och längdenhet.
`POST /documents/1.0/projects/{project_id}/ifc-merge/report` visar varje medlem av
båda projekten vad som skulle hända: hur många objekt och instanser som följer med,
objekten med ett GlobalId som båda har (`collisions`, med `same` och det `choice`
som gäller), sambanden som lämnas utanför för att de bara pekar ut ur byggnaden, och
A:s kontexter och placeringar som används. Där innehållet i ett sådant objekt
skiljer sig görs ett val för det: `a` behåller A:s, `b` sätter B:s i dess ställe, och
`new` behåller båda, B:s med ett nytt GlobalId; `default` ger ett val för alla.
En enhet av ett slag som A saknar, som en areaenhet, följer med in i A:s enheter och
listas i `units_added`; en enhet av ett slag som båda har måste vara densamma.

En `manager` i projektet startar sammanfogningen med `POST …/ifc-merge` och samma
kropp. Den körs som ett jobb i konverteringskön, och svarets `url` ger dess
tillstånd: `conflict` med objekten som ännu saknar val, `failed` med orsaken, eller
`done` med `version_index`, den nya versionen av A:s dokument. Den sammanfogade
modellen kontrolleras först mot A och B och får inte ha någon anmärkning som de
saknar; sedan skrivs den ut som nästa version, med A:s version som förälder och
`merged_from_document`, `merged_from_version` och `merged_building` i sin metadata,
och konverteras och kontrolleras som en uppladdning. A:s version måste vara
dokumentets senaste (annars 412 `version_conflict`). Kapabilitetsdokumentet
annonserar den som `ifc_merge`.

Där B:s schema eller längdenhet inte är A:s säger rapporten det (422), och en
`editor` eller `manager` förbereder först B med `POST …/ifc-merge/prepare` och `base`
och `other`: ett jobb som gör en kopia av B migrerad till A:s schema och med sina
längder i A:s enhet. När det är `done` gör dess `merge_id`, givet som
`other.prepared`, att kopian står för B i rapporten och sammanfogningen till
`expires_at`, ett dygn senare; sedan tar servern bort den. En annan enhet som skiljer
sig konverteras inte, och jobbet misslyckas med den.
Det som A:s schema saknar motsvarighet till, som IFC2X3:s IfcWindowStyle i IFC4X3
eller de ägarhistoriker IFC2X3 kräver, ger jobbet läget `conflict`:
`report.problems` listar varje problem med sin `key`, vad det rör och sina
`options` (`type`, `proxy`, `leave_out`, `polyline`, `owner`, `virtual`, `dated`,
`assignment`, `context`), och ett nytt `POST …/ifc-merge/prepare` med `resolutions`, det valda
alternativet per nyckel, gör kopian. Kopian kontrolleras sedan mot B: en med en
anmärkning som B inte hade görs inte, och jobbet blir `failed` med dem i `report.new`.

```http
POST /documents/1.0/projects/{project_id}/ifc-merge
{"base": {"document_id": "…", "version_index": 3},
 "other": {"project_id": "…", "document_id": "…", "version_index": 1},
 "building": "3AMeTOOFsdVLZuNV0$27s5", "choices": {"1Xezbq735AdBO_4DerG66G": "b"}}
```

## Arbetskopian

Bredvid arkivet kan servern hålla en arbetskopia: en andra graf, Memgraph i
minnet, dit huvudversionens modell för varje dokument också importeras
(ADR 0024). Arkivet behåller varje version och förblir sanningen; arbetskopian
håller en modell per dokument, den senast konverterade, och svarar på de
namngivna frågorna för den, så att en stor modell läses ur minnet.
`OPENCDE_WORKCOPY_GRAPH_URI` anger den (`OPENCDE_WORKCOPY_GRAPH_DIALECT`,
`_USER`, `_PASSWORD` och `_DATABASE` bredvid); överlägget
`docker/compose.workcopy.yaml` lägger Memgraph till vilken stack som helst,
opublicerad. En konvertering importerar samma poster i båda graferna i IFC-LPG:s
dialektneutrala form, ersätter dokumentets tidigare modell i arbetskopian och
misslyckas aldrig på arbetskopians grund: en kopia som inte kunde göras
märks `failed` där och arkivet rörs inte. En modell som arkivet inte längre har
lämnar arbetskopian vid nästa städomgång. `GET …/ifc-queries` säger i
`workcopy` om versionens modell finns där, `/readyz` rapporterar
arbetskopians tillstånd utan att bero på den, och kapabilitetsdokumentet säger
i `ifcgraph.workcopy` om en är konfigurerad.

```sh
# .env: COMPOSE_FILE=docker/compose.yaml:docker/compose.local.yaml:docker/compose.workcopy.yaml
docker compose up -d
```

## Serverns egna data skilda från IFC-grafen

Servern håller sina egna data (konton, projekt, team, dokument och deras
versioner, ärenden, kommentarer och vypunkter, och sina jobb: kontroller,
förhandskontroller, provningar, krocktester, sammanslagningar och
konverteringar) skilda från IFC-grafen, som håller IFC-LPG:s modeller
(`Model`, `Entity`, `StepBlock`); de två möts bara genom värden, som en
konverterings `model_id` och en komponents GlobalId (ADR 0027). Som standard
delar de IFC-grafens anslutning. `OPENCDE_STORE_GRAPH_URI` ger serverns egna
data en egen graf, med `OPENCDE_STORE_GRAPH_DIALECT` (`neo4j` som standard),
`_USER`, `_PASSWORD` och `_DATABASE` bredvid; produktion och den lokala miljön
kräver lösenordet. Lagret och IFC-grafen kan vara olika databaser i samma
produkt, två Neo4j eller två Memgraph, eller i olika produkter, som serverns
egna data i Neo4j och modellerna i Memgraph; Neo4j:s community-utgåva håller en
databas per server, så där är två databaser två servrar. IFC-LPG-tjänsten
skriver modellerna till IFC-grafen och sina poster till lagret, och varje annan
rutt läser och skriver lagret. Kommandoraden öppnar lagret för det som rör
serverns egna data och båda för `seed`, `backup`, `restore`, `ifc-lpg prune`
och `ifc-lpg export`; `opencde doctor` och sidan Inställningar kontrollerar
båda, och `/readyz` säger i `store` om lagret är `shared`, `ok` eller
`unavailable`, och är redo bara när båda svarar. En publicerad Bolt-port
([deploy/bolt.md](deploy/bolt.md)) och administrationens graffråga når en graf
var: porten IFC-grafen, frågan lagret. Servern flyttar inte det en databas
redan håller: sätt lagret på en ny installation, eller flytta data med
`opencde backup` och `opencde restore` ([deploy/backup.md](deploy/backup.md)).

```sh
# .env
OPENCDE_STORE_GRAPH_URI=bolt://store:7687
OPENCDE_STORE_GRAPH_DIALECT=neo4j
OPENCDE_STORE_GRAPH_USER=neo4j
OPENCDE_STORE_GRAPH_PASSWORD=<ett eget lösenord>
OPENCDE_STORE_GRAPH_DATABASE=neo4j
```

## Var byggdelarna är, och geometrin

Efter en konvertering kör servern IFC-LPG:s geometriarbetare en gång över
filen (`python -m ifc_lpg.spatial`; `OPENCDE_IFC_LPG_SPATIAL`, på som standard
med extrat): IfcOpenShell bygger varje byggdels form, och arbetaren skriver en
låda per byggdel i projektkoordinater och mesherna, varje delad mesh en gång.
Lådorna går in i grafen som punkterna `bbox_min`, `bbox_max` och `bbox_centre`
på byggdelens `Entity`, med ett punktindex på `bbox_centre` i arkivet och i
arbetskopian, så att en fråga hittar det som är nära en punkt eller inuti en
volym; `Model` bär `spatial_at`, `spatial_products` och `spatial_failed`.
Posterna sparas i lagringen, och `GET …/ifc-geometry` bygger en binär glTF ur
dem första gången den efterfrågas: varje delad mesh en gång, en nod per
byggdel som instansierar den med byggdelens matris, namngiven med sitt
GlobalId och med klass, STEP-id och våning i `extras`, under en nod per
våning, och en rot som vrider modellen från IFC:s Z upp till glTF:s Y upp.
`lod=box` ger lådorna i stället, en kub som varje byggdel instansierar, några
byte var; `classes` (IFC-klasser, kommaseparerade) och `storey` (ett GlobalId)
väljer byggdelarna. Filen sparas och kommer med en `ETag` för modellen och
filtren, så att `If-None-Match` besvaras med `304`. Geometripasset fäller
aldrig en konvertering: misslyckas det antecknar modellen `spatial_error` och
rutten svarar `404`; medan versionen ännu konverteras, `409`.
Kapabilitetsdokumentet annonserar det som `ifc_geometry`.

```http
GET /documents/1.0/documents/{document_id}/versions/{version_index}/ifc-geometry?lod=full&classes=IfcWall,IfcSlab
```

```cypher
// Byggdelarna inom två meter från en vägg, i samma modell
MATCH (w:Entity:IfcWall {GlobalId: $guid})
MATCH (e:Entity {model_id: w.model_id}) WHERE e.bbox_centre IS NOT NULL AND e <> w
  AND point.distance(e.bbox_centre, w.bbox_centre) < 2.0
RETURN e.GlobalId, e.ifc_class, point.distance(e.bbox_centre, w.bbox_centre) AS distance ORDER BY distance
```

## Fråga från Dataspatium

[Dataspatium](https://github.com/marwiss/Dataspatium), webbläsarklienten som
utvecklas tillsammans med den här servern, kör Cypher mot den här grafen
genom sin Neo4j-källa över Bolt (WebSocket på Bolt-porten) när operatören
exponerar databasen, som utvecklingsöverlagringen gör på `127.0.0.1:7697`.
Dess Dataregium-arbetsyta använder mönstren ovan (modeller, klasser,
komponenter genom `GlobalId`, den senaste färdiga modellen per dokument);
frågorna finns i Dataspatiums dokumentation (`docs/grafer.md`). En
produktionsserver publicerar inte Bolt; administrations-API:ts graffråga
(`OPENCDE_GRAPH_QUERY_ENABLED`, [client-guide.md §7](client-guide.md)) ger
administratörer läsande Cypher utan porten. Appen ritar också
grafen, i sitt kort IFC-LPG, genom den frågan eller över Bolt.

## Gränser och status

- En konvertering i taget; stora modeller köas. Exempelmodellen (248
  entiteter) importeras på ungefär en sekund; en arkitektmodell på 200 MB tar
  minuter.
- `Conversion` bär `state`, `entities`, `relationships`,
  `lossless`, `geometry`, `schema`, `ifc_project_guid`, tidsstämplar och `error`. Administratörer kan
  granska den i Neo4j Browser eller Memgraph Lab:
  `MATCH (c:Conversion) RETURN c.file_name, c.state, c.entities, c.error`.
- När ett projekt tas bort tas dess modellers entiteter bort med det.
- En modell kommer tillbaka identisk från båda databaserna upp till 224 496 instanser och
  19 MB, i varje form som mätts. Inget större har provats.
