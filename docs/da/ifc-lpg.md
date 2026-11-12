# IFC-LPG

Det valgfrie IFC-LPG-modul gør en uploadet IFC-model til grafdata, så
komponenterne i et BCF-viewpoint kan knyttes til de bygningsdele, de peger
på, og så spørgsmål om modellen kan stilles i Cypher ved siden af sagerne og
dokumenterne.

Slå det til med `OPENCDE_IFC_LPG_ENABLED=true`, og installér ekstrapakken
`ifc-lpg` (`uv sync --extra ifc-lpg`). Docker-imaget indeholder ekstrapakken
som standard (`ARG OPENCDE_EXTRAS` i Dockerfile), hvilket mere end fordobler
dets størrelse (omkring 680 MB, eller 1,1 GB med buildingSMARTs regler, mod 300 MB); byg med
`--build-arg OPENCDE_EXTRAS=` for et slankere image uden IfcOpenShell, når
modulet forbliver slået fra.

Indtil november 2026 hed modulet IFC-graph. Dets indstillinger hed `OPENCDE_IFCGRAPH_*` og
kommandoen `opencde ifcgraph`, og begge virker stadig; serverens log og `opencde
doctor` nævner de gamle indstillinger, den får.

Konverteringen, skrivningen af en fil og kontrollerne kommer fra biblioteket
[IFC-LPG](https://github.com/marwiss/IFC-LPG), som Dataregium installerer fra dets
repository ved en fast commit, og hvis README beskriver, hvordan en model gemmes
i grafen. Serverens egen proces bruger den del, der ikke behøver IfcOpenShell;
ekstrapakken `ifc-lpg` tilføjer de arbejdsprocesser, der gør.

## Hvad der sker ved upload

1. En Documents API-upload afsluttes (eller en fil uploades fra
   udvælgelsessiden, eller et BCF-projektdokument postes) med et `.ifc`-
   eller `.ifczip`-navn.
2. Serveren opretter en `Conversion`-post (tilstand `queued`) knyttet til
   projektet og starter en konvertering i baggrunden, én ad gangen.
3. En separat arbejdsproces (`python -m ifc_lpg.worker`) læser
   filen. Den kører med en tidsgrænse
   (`OPENCDE_IFC_LPG_TIMEOUT_SECONDS`, 15 minutter), en adresserumsgrænse på
   POSIX (`OPENCDE_IFC_LPG_MEMORY_MB`, 4 GiB) og et loft over antallet af
   entiteter (`OPENCDE_IFC_LPG_MAX_ENTITIES`). Et nedbrud eller en hængning
   dræber arbejdsprocessen, ikke serveren. `.ifczip` pakkes ud med uploadens
   størrelsesgrænse.
4. Posterne importeres i batches af `UNWIND … CREATE` (portabel Cypher, ingen
   APOC). `Conversion` ender i tilstanden `done` med tal og `IfcProject`-guid,
   eller `failed` med en fejl.
5. En konvertering, som en stoppet server har efterladt, begynder forfra: en sat i kø, så snart serveren er
   tilbage, en igangværende, når den dobbelte tidsgrænse er passeret, fordi den kan køre i en anden serverproces.

`opencde seed` konverterer eksempelmodellen på samme måde, når modulet er slået til.

## Kontrol af uploads mod IFC-skemaet

Hver `.ifc`- eller `.ifczip`-fil, der uploades som dokumentversion, kontrolleres
også mod IFC-skemaet med den validator, der kontrollerer en skrevet fil
([Skrive en model tilbage](#skrive-en-model-tilbage)): attributternes type og
antal, enumerationer, inverse attributter, GlobalId og reglerne i
EXPRESS-skemaet. Kontrollen kører i baggrunden før konverteringen, i en
arbejdsproces med de samme grænser. Som standard stopper den aldrig en upload: filen
gemmes, som den kom, hvad kontrollen end finder; et projekt kan vælge
anderledes ([nedenfor](#afvise-filer-med-fejl-og-kontrollere-en-fil-på-forhånd)). Et BCF-projektdokument kontrolleres
ikke, da det ikke har metadata. `OPENCDE_IFC_LPG_VALIDATE_UPLOADS=false` slår
kontrollen fra.

Resultatet står i versionens metadata, som enhver klient til Documents API kan læse:

| Post | Type | Værdi |
|---|---|---|
| `ifc_validation_status` | `string` | `pending`, indtil filen er kontrolleret, derefter `passed`, `warnings`, når hver anmærkning er en advarsel, `issues`, når mindst én er en fejl, eller `unknown`, når den ikke kunne kontrolleres |
| `ifc_validation_issues` | `integer32` | Hvor mange anmærkninger filen har |
| `ifc_validation_checked_at` | `date-time` | Hvornår den blev kontrolleret |
| `ifc_validation_ruleset` | `string` | Hvad den blev kontrolleret med, én værdi pr. kontrol |
| `ifc_validation_report` | `url` | Hvor rapporten er |

Rapporten er en udvidelse af Documents API. Hvert medlem af projektet får den med
det samme Bearer-token:

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

Den viser op til 10.000 anmærkninger, hver med sin instans og, for en rodfæstet
entitet, dens GlobalId, så en modelvisning kan finde elementet. `kind` siger, hvad
der fandt anmærkningen: `schema`, `entity_rule`, `simpletype_rule` eller
`global_rule` i IFC-skemaet, eller `gherkin` for en af buildingSMARTs regler,
hvis kode står i `rule`. `checks` holder kontrollerne adskilt. En meddelelse kan
citere en linje fra filen og afkortes ved 1.000 tegn. Versionens side i browseren viser de første 100 anmærkninger og tilbyder
hele rapporten som fil.

Mange filer bryder allerede en regel, når de kommer fra deres program: 12 af 26
eksempelfiler gør det, én fra Tekla med 5.711 anmærkninger. At kontrollere en
eksempelfil og dens skrevne kopi tog 3 til 66 sekunder tilsammen.

### buildingSMARTs ifc-gherkin-rules

Når `OPENCDE_IFC_LPG_GHERKIN_ENV` peger på et miljø til dem, kontrolleres
uploads også mod buildingSMARTs `ifc-gherkin-rules`: de normative regler og den
branchepraksis, som buildingSMARTs valideringstjeneste kontrollerer ud over
skemaet (ADR 0012).
De kører efter skemakontrollen, i den samme slags arbejdsproces med de samme
grænser, og sådan som regelsættets egne tests kører dem: med behave og
IfcOpenShell 0.8.6, som regelsættets CI bruger. På regelsættets 722 testfiler
giver det det udfald, som dets tests forventer, for hver eneste.

Reglerne får deres eget miljø, fordi en af deres hjælpefunktioner ikke virker
med den IfcOpenShell 0.9, som Dataregium bruger.
`python -m ifc_lpg.gherkin_install <mappe>` laver det af fastlåste
downloads, som hver kontrolleres mod sin SHA-256: regelsættet ved et bestemt
commit, IfcOpenShells build af 0.8.6 til platformen og Python-pakkerne med
deres hashes. To små filer fra IFC-LPG erstatter regelsættets Django-dele, som
kun skriver resultater til valideringstjenestens database.
Det publicerede image udelader dem, da de lægger omkring 425 MB til. Imaget med
tagget `-gherkin`, som `latest-gherkin` eller `3.0.0-gherkin`, har miljøet i
`/opt/gherkin` og lader `OPENCDE_IFC_LPG_GHERKIN_ENV` pege på det, ligesom et
image bygget med `--build-arg OPENCDE_GHERKIN=1`. Med docker compose vælger
`OPENCDE_IMAGE_TAG` eller `OPENCDE_GHERKIN=1` i `.env`.

Et fund fra en regel er en anmærkning af typen `gherkin` med reglens kode, som
`IFC106`, og alvorligheden `error` eller `warning`. Regler for branchepraksis
advarer kun, og en fil, hvis anmærkninger alle er advarsler, får status
`warnings`, da buildingSMARTs valideringstjeneste regner en sådan fil for
gyldig. En regel, der kastede en undtagelse i stedet for at finde noget, har
intet udfald og står under `rules_not_run` i sin kontrol. Kan reglerne slet ikke
køre, bliver deres kontrol `failed`, og skemaets kontrol står alene.

Reglerne tager længere tid end skemakontrollen: på otte eksempelmodeller fra 5
sekunder for den mindste til omkring 5 minutter for den største og mellem et
halvt og to minutter for de fleste.

### Information Delivery Specifications (IDS)

En upload kontrolleres også mod hvert IDS-dokument i sit projekt: et dokument,
hvis seneste version har et navn, der ender på `.ids`, højst 50
(ADR 0015).
IFC-LPG's kontrol læser hver IDS sikkert og giver den til IfcOpenShells
IfcTester, den samme kontrol, som Dataspatium kører i browseren, så de to giver
samme udfald. Den køres efter de andre kontroller, i samme slags arbejdsproces
med de samme grænser. En ny version af et IDS-dokument får den seneste version af hvert IFC-dokument i projektet kontrolleret igen,
højst 500, så dens rapport følger kravene, som de er nu; ældre versioner beholder den rapport, de havde.

Hvert krav, et element ikke opfylder, bliver en anmærkning af typen `ids`, med
alvoren `error`, specifikationens identifikator eller navn i `rule` og
IDS-dokumentet i `document_id`. Det samme gør en påkrævet specifikation, der
ikke gælder noget i filen, og et element, som en forbudt specifikation gælder.
Rapportens kontrol `ids` viser de dokumenter, den brugte, med version, og hver
specifikation med dens anvendelse, udfald (`passed`, `failed` eller
`not applicable`), hvor mange elementer den gælder, og hvor mange anmærkninger
den gav. Et IDS-dokument, der ikke kan læses, for eksempel et med en DTD, står
under `rules_not_run` med grunden, og de andre kontrolleres alligevel.
Versionens side viser specifikationerne i en tabel for sig.

### buildingSMART Data Dictionary (bSDD)

Med `OPENCDE_BSDD_ENABLED=true` kontrolleres en upload også mod buildingSMARTs Data Dictionary, efter IDS-kontrollen.
En arbejdsproces læser filens henvisninger dertil: hver `IfcClassificationReference`, hvis `Location` er en bSDD-URI,
som `https://identifier.buildingsmart.org/uri/molio/cciconstruction/1.0/class/L-BD`, eller hvis `Identification`
(`ItemReference` i IFC2X3) er en kode i den ordbog, hvis URI dens `Location` eller dens klassifikation har, med de
objekter, den sidder på; og egenskaberne i hvert egenskabssæt, der hedder `Pset_…` eller `Qto_…`. Serveren spørger
derefter bSDD's API på `OPENCDE_BSDD_API_URL` (`https://api.bsdd.buildingsmart.org`) om hver URI, med en tidsgrænse
for hvert spørgsmål (`OPENCDE_BSDD_TIMEOUT_SECONDS`, 10 sekunder) og to nye forsøg, når bSDD svarer 429 eller 5xx, og
beholder hvert svar i hukommelsen et døgn (`OPENCDE_BSDD_CACHE_SECONDS`, 86400; 0 spørger hver gang). Intet, som filen
navngiver, hentes: en URI går til bSDD's API som en parameter, og en på en anden vært end
`identifier.buildingsmart.org` rapporteres i stedet. Kontrollen er slået fra som standard, fordi den sender filens
URI'er og navnene på dens egenskabssæt til bSDD; i produktion skal adressen være https.

Alt, hvad den finder, er en advarsel af typen `bsdd`, med klassifikationsreferencen eller egenskabssættet i `step_id`,
GlobalId for et af de objekter, den sidder på, i `global_id` og objektets klasse i meddelelsen:

- en klassifikationsreference, hvis klasse eller egenskab bSDD ikke kender, med ordbogen i `rule` og den attribut, der
  navngiver den, i `attribute`; en model kan bruge en ordbog, som bSDD ikke har udgivet;
- i en fil i IFC 4.3 et egenskabssæt, som bSDD's IFC-ordbog (`buildingsmart/ifc/4.3`) ikke har, eller en egenskab, som
  den ikke viser i det sæt, med sættet og egenskaben i `attribute`, som `Pset_WallCommon.Colour`.

bSDD udgiver kun den ene IFC-ordbog, så egenskabssættene i en fil i IFC4 eller IFC2X3, hvis skemaer definerer dem
anderledes, kontrolleres ikke; og `Reference`, som IFC 4.3 giver næsten hvert egenskabssæt, og som bSDD udelader i dem
alle, rapporteres ikke. Kontrollens `ruleset` navngiver bSDD's vært og de ordbøger, filen blev kontrolleret mod. Den
læser højst 1.000 referencer og 500 egenskabssæt, og en advarsel siger til, når en fil har flere. Når bSDD ikke kan
nås, eller ikke svarer, som dens API gør, er kontrollen `failed` med grunden i sit `error`, og de andre kontroller
står ved magt: at bSDD ikke kan nås, er aldrig en fejl i modellen. Forhåndskontrollen og prøvningen af et ændringssæt
foretager også kontrollen, og kapabilitetsdokumentet siger, om den er slået til, som `bsdd` i `ifc_validation`.

### Rummene på hver etage

Med `OPENCDE_ROOMS_ENABLED=true` får rapporten for en upload, en forhåndskontrol og en prøvning også rummene på hver
etage, fundet ud fra dens vægge, som Dataspatium finder dem: en arbejdsproces kører en kopi af appens kode med
IfcOpenShell og shapely, efter kontrollerne og med de samme grænser. En vægs midterlinje er dens
`Axis`-repræsentation, som de vægge, Dataspatium laver, har, eller ellers den lange akse i dens krops fodaftryk;
enderne føjes sammen inden for halvdelen af etagens tykkeste væg plus 0,05 m, og de midterlinjer, der lukker om mindst
0,5 m² og 0,5 m i bredden, danner et rum. Rapportens `rooms` har hver etage, efter kote, med:

- `rooms`: hvert rums `index` på etagen, dets `area` (m²) og `perimeter` (m) langs midterlinjerne, GlobalId for dets
  `walls` og dets `neighbours` efter indeks;
- `external`: væggene langs rummenes yderside, hver med sit `global_id`, `name`, sin `length` dér og det verdenshjørne,
  den vender mod (`facing`, `N`, `NE` … `NW`), med nord fra kortkonverteringen, ellers `TrueNorth`, ellers modellens
  y-akse, som `north` siger (`map`, `true_north` eller `model`);
- `dangles` og `dangling_walls`: de løse vægender, `[x, y]` i meter i modellens plan, og deres vægge;
- `closed`: om etagen har et rum og ingen løs ende;
- `walls`, `unread` og `unread_walls`: hvor mange vægge etagen har, og hvor mange og hvilke der ikke gav nogen
  midterlinje;
- `tolerance`: hvor langt fra hinanden, i meter, to ender må være og stadig føjes sammen.

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

Rummene er et afsnit for sig og aldrig en anmærkning: de ændrer hverken status eller antal, et projekt, der afviser
filer med fejl, afviser aldrig en fil for dens rum, og en prøvning er `clean` eller `issues`, uanset dens rum, som er
den anvendte fils. Versionens side viser en række pr. etage med vægge. Listerne afkortes ved 100 etager, 500 rum pr.
etage og 200 poster i hver anden liste, og `cut` siger til, og en model med mere end 2.000 vægge får ingen. Når rummene
ikke kan findes, har rapporten ingen `rooms`, og loggen siger hvorfor (`ifc_rooms_failed`) uden det, filen siger.
Slået fra som standard; kapabilitetsdokumentet siger, om det er slået til, som `rooms` i `ifc_validation`.

### Det, den konverterede model viser

Når modellen er konverteret, får rapporten sin egen kontrol, `graph`, med to slags bemærkninger. En instans, som intet
med et GlobalId når, frem eller tilbage, er en advarsel af typen `reachability`, med sit STEP-id i `step_id` og sin
klasse i meddelelsen: kun det nummer navngiver den, som en placering, intet bruger, så et ændringssæt kan udpege den
alene med sit STEP-id. Et produkt, hvis form geometripasset ikke kunne bygge, er en bemærkning af typen `geometry`,
med sit GlobalId. Ingen af dem afviser filen: de kommer efter uploaden, og en advarsel giver status `warnings`. Før
modellen er konverteret, har rapporten ingen kontrol `graph`.
En instans, der holdes sammen med geometrien i en STEP-blok, som et løst punkt,
listes ikke: kontrollen ser kun noderne.

### Afvise filer med fejl, og kontrollere en fil på forhånd

En administrator kan sætte kryds ved *Afvis uploads med valideringsfejl* på
projektets side (`block_on_validation_errors` i administrations-API'et).
Kontrollerne kører så, før filen bliver en version, i uploadens afslutning og
på uploadsiden, og en fil med en eller flere fejl afvises med
`422 ifc_validation_failed`; advarsler slipper igennem. Den afviste fil bliver
et døgn som forhåndskontrol, og `report` i fejlen siger, hvor rapporten er. En
fil, der slet ikke kunne kontrolleres, slipper igennem som `unknown`, så en
defekt validator aldrig stopper arbejdet. En fil, der godkendes, kontrolleres
én gang: resultatet bliver versionens, som om kontrollen var kørt bagefter.

Enhver redaktør eller forvalter kan også kontrollere en fil uden at gøre den
til en version, med det samme bearer-token og uanset projektets indstilling:

```http
POST /documents/1.0/projects/{project_id}/ifc-precheck
Content-Disposition: attachment; filename="model.ifc"
```

Kroppen er filen. Svaret er `202` med rapportens `url`, `pending` indtil
kontrollerne er færdige; derefter har den samme form som en versions rapport,
med filens navn og hvornår forhåndskontrollen udløber. Hvert medlem læser den,
i et døgn. Kapabilitetsdokumentet annoncerer forhåndskontrollen som
`ifc_precheck`.

## Grafen

Hver entitet bliver en `Entity`-node, der bærer sin klasse og alle sine
supertyper som labels, for eksempel `Entity:IfcWallStandardCase:IfcWall:
IfcBuildingElement:IfcElement:IfcProduct:IfcObject:IfcObjectDefinition:IfcRoot`.

| Egenskab | Betydning |
|---|---|
| `id` | `<model-id>:<STEP-id>`, unik |
| `model_id`, `step_id` | modellen og `#123`-nummeret i filen |
| `ifc_class` | den konkrete klasse |
| `GlobalId`, `Name`, `Description`, `Tag`, … | hver literal attribut på entiteten, med dens IFC-navn |

Attributter, der peger på andre entiteter, bliver relationer navngivet efter
attributten, skrevet som enhver relationstype i grafen med store bogstaver og
understregninger ved ordgrænserne:
`(:IfcRelDefinesByProperties)-[:RELATING_PROPERTY_DEFINITION]->(:IfcPropertySet)-[:HAS_PROPERTIES]->(:IfcPropertySingleValue)`.
Inverse attributter bliver også relationer, så begge retninger læses
naturligt: `(:IfcWall)-[:IS_DEFINED_BY]->(:IfcRelDefinesByProperties)`.
Select-værdier pakkes ud (`IfcLabel('3')` bliver `"3"`).

Ingen noder som standard (`OPENCDE_IFC_LPG_INCLUDE_GEOMETRY=false`):
repræsentationselementer, repræsentationer, profiler, placeringer og
stilarter; de udgør det meste af en model og er sjældent det, en
CDE-forespørgsel har brug for, og de bevares som tekst i grafen, jf. Skrive en
model tilbage. `IfcOwnerHistory` er kun en node for `IfcProject`.

## Hvor metoden kommer fra

Omsætningen følger IFC-Graph-metoden af Zhu, Wu og Lei: én node pr. instans,
klassehierarkiet som labels, literale attributter som egenskaber og attributter,
der peger på andre instanser, inverse attributter medregnet, som relationer
navngivet efter attributten. Prototypen fra 2023 brugte artiklens kode. Denne
servers konvertering er skrevet på ny.

Junxiang Zhu, Peng Wu og Xiang Lei: "IFC-graph for facilitating building
information access and query". *Automation in Construction* 148 (2023), 104778.
[doi:10.1016/j.autcon.2023.104778](https://doi.org/10.1016/j.autcon.2023.104778),
frit tilgængelig under CC BY 4.0.

Den adskiller sig fra artiklen på disse punkter:

- Geometri bliver ikke noder, medmindre det ønskes. Artiklen konverterer alt og nævner
  grafens størrelse som en begrænsning.
- Posterne skrives i portioner med `CREATE` fra en separat proces. Artiklen
  fletter hver node og relation, hvilket søger efter dubletter i grafen og bliver
  langsommere, jo større grafen bliver.
- Select-værdier bliver egenskaber på deres node. Artiklen giver dem egne noder
  med en genereret identifikator.
- Flere modeller deler én database og skelnes med `model_id`. Artiklen har én
  model pr. database.
- Relationstyperne skrives med store bogstaver, og kopien af GTIN til
  BCF-komponenterne er en tilføjelse her.

Artiklen påpeger, at dens graf mister rækkefølgen i lister, da en relation ikke
siger, hvor i en liste dens mål stod. Her siger `position` det.

## Skrive en model tilbage

Grafen rummer hele modellen, og filen kan skrives tilbage fra den: de samme
instanser med de samme id'er og de samme værdier i samme rækkefølge, og dermed også
den samme geografiske information.

```sh
uv run opencde ifc-lpg export <model-id> model.ifc            # skriv filen og validér den
uv run opencde ifc-lpg export <model-id> model.ifc --verify   # og sammenlign den med den uploadede
```

Noderne er dem, forespørgsler har brug for. Det, de udelader, skrives ud som STEP og
komprimeres til tekst på `StepBlock`-noder, der hænger på `Model`: det er i grafen,
men uden for Cyphers rækkevidde, og det kan ikke ændres der. Det kan ikke være
egenskaber på produkterne, da meget af det deles mellem dem. Med
`OPENCDE_IFC_LPG_INCLUDE_GEOMETRY=true` bliver hver instans i stedet en node, til
flere gange størrelsen og importtiden; forespørgsler tog omtrent lige lang tid i
målingerne.
Et stylet element (`IfcStyledItem`) er altid en node, så hver stil kan ændres, og `form_version` på `Model` angiver, hvilken form grafen har (2 siden IFC-LPG's udgivelse 2026-11-10).

| I filen | I grafen |
|---|---|
| En reference | En relation med `position`, `[række, kolonne]` i en liste af lister; inverse relationer har ingen |
| En reference til en instans i en blok | Dens id, som i `Representation__step: 1234` |
| En typet værdi, `IFCLABEL('3')` | `NominalValue: "3"`, og `NominalValue__type: "IFCLABEL"` ved siden af |
| En liste af lister af tal | JSON-tekst |
| Det, der ikke har en enkel form, som en liste af typede værdier | Mærket JSON, med `$json` som type |
| Headeren | `ifc_header` på `Model` |
| En instans i en blok | Tekst i en `StepBlock` |

Filen skrives ud fra det, grafen rummer, og kopieres ikke, så en egenskab eller en
relation, der ændres i grafen, kan ses i den. En grafdatabase har intet skema at holde
en ændring op imod, så filen valideres mod IFC-standarden med IfcOpenShells validator:
attributternes type og antal, enumerationer, inverse attributter, GlobalId og reglerne
i EXPRESS-skemaet. Filer i brug bryder ofte allerede en regel, så det, der tæller, er
en anmærkning, som den uploadede fil ikke har. Kommandoen viser den da og slutter med
en fejl. `--no-validate` springer dette over. En eksport stopper også, hvis en blok
mangler.

Projektmedlemmer får filer gennem Documents API, og der er ingen anden vej ud af
serveren. En skrevet fil, der skal erstatte en model, uploades som en ny version af
sit dokument, hvilket også konverterer den.

Denne form læses ikke med IfcOpenShell, som her kun står for skemaet. IfcOpenShell
ændrer nogle værdier ved læsning (`.NULLENUM.` bliver `$`, og `($,$)` bliver `()`), og
filer fra Tekla og Archicad har dem. Derfor læser arbejdsprocessen selv filen og
afviser det, den ikke kan læse. ADR 0010 siger hvorfor, og
ADR 0011 hvordan en fil valideres.

`--verify` spørger, om de to filer rummer den samme model, efter definitionen i
ADR 0009: en til en, værdi for værdi og uden tolerance, med georeferencen
navngivet i rapporten. Med `--geometry` bygges også hvert produkts mesh, og de
sammenlignes bit for bit. To vilkårlige filer kan sammenlignes med
`python -m ifc_lpg.equivalence first.ifc second.ifc`.

Med `OPENCDE_IFC_LPG_LOSSLESS=false` konverteres en model som før 3.0.0: den læses med
IfcOpenShell, og det, der ikke er noder, udelades helt. En sådan model, ligesom en, der
er konverteret af en tidligere version, kan ikke skrives tilbage.

## Oprydning

Hver upload af en IFC-fil tilføjer en `Conversion` og en model med dens entiteter, så et
projekt, der modtager nye versioner, samler grafer, som ingen forespørger.
Kommandolinjen lister og fjerner dem; dokumenterne og deres filer bliver
altid:

```sh
uv run opencde ifc-lpg list --project <projekt-id>
uv run opencde ifc-lpg prune                   # fejlede modeller, og færdige modeller erstattet af en nyere
                                                # færdig version af samme dokument
uv run opencde ifc-lpg prune --project <id> --all   # hver model i ét projekt (en teststak, for eksempel)
```

Modeller i kø og under kørsel fjernes aldrig. Forespørgsler, der vil have én
graf per dokument, bør selv vælge den seneste færdige model, da ældre
versioner bliver, indtil de fjernes:

```cypher
MATCH (:Project {project_id: $project})-[:HAS_CONVERSION]->(m:Conversion {state: 'done'})
WITH coalesce(m.document_id, m.bcf_document_guid) AS doc, m
ORDER BY m.version_index DESC, m.done_at DESC
WITH doc, collect(m)[0] AS latest
MATCH (e:IfcProduct {model_id: latest.id})
RETURN latest.file_name AS model, count(e) AS products
```

## Kobling af BCF-komponenter

Når et viewpoint oprettes med komponenter, får hver komponent, hvis `ifc_guid`
matcher `GlobalId` for en bygningsdel i en af projektets importerede modeller,
værdien af den konfigurerede egenskab
(`OPENCDE_IFC_LPG_GTIN_PROPERTY_SET=Reuse`, `OPENCDE_IFC_LPG_GTIN_PROPERTY=GTIN`)
som `gtin`, når bygningsdelen har en: serveren slår GlobalId'erne op i modellen
gennem IFC-LPG's `property_values` og gemmer værdien på komponenten, og laver
ingen relation ind i modellen; bygningsdelen findes gennem sit `GlobalId`. Det
samme opslag kører for hver eksisterende komponent i projektet, når en model er
færdigimporteret, så viewpoints oprettet, før modellen blev uploadet, eller mens
den stadig blev konverteret, får også deres GTIN. Det er anvendelsestilfældet i
forskningsrapporten fra 2023: et eftersyn (BCF-sag), der peger på byggevarer
identificeret med GTIN.

```cypher
// Hvilke produkter peger dette viewpoint på, og hvad er deres GTIN?
MATCH (:Viewpoint {guid: $viewpoint})-[:HAS_COMPONENT]->(c:Component)
MATCH (e:IfcProduct {GlobalId: c.ifc_guid})
RETURN c.ifc_guid, e.Name, c.gtin
```

```cypher
// Rapportens forespørgsel, direkte på modellen: GTIN for hver væg.
MATCH (w:IfcWall)-[:IS_DEFINED_BY]->(:IfcRelDefinesByProperties)-[:RELATING_PROPERTY_DEFINITION]
      ->(:IfcPropertySet {Name: 'Reuse'})-[:HAS_PROPERTIES]->(p:IfcPropertySingleValue {Name: 'GTIN'})
RETURN w.GlobalId, w.Name, p.NominalValue
```

```cypher
// Hver sag, der berører en given bygningsdel.
MATCH (:Component {ifc_guid: $guid})<-[:HAS_COMPONENT]-(v:Viewpoint)<-[:HAS_VIEWPOINT]-(t:Topic)
RETURN DISTINCT t.server_assigned_id, t.title, t.topic_status
```

BCF-tjenesten `files_information` viser importerede modellers
`IfcProject`-guid som `ifc_project`, hvilket lader klienter udfylde filerne i
sagens hoved.

## Navngivne forespørgsler

Et medlem af et projekt stiller spørgsmål til en versions model ved navn, med
det samme bearer-token som til Documents API; fri Cypher forbliver
administratorernes (ADR 0016).
Forespørgslerne er IFC-LPG's katalog (`ifc_lpg.queries`), så en, der tilføjes i
biblioteket, dukker op her.
`GET /documents/1.0/documents/{id}/versions/{index}/ifc-queries` viser
forespørgslerne med deres parametre og kolonner og siger i `model_state`, hvor
langt konverteringen af modellen er kommet. `GET …/ifc-queries/{name}` stiller
én, med parametrene i forespørgselsstrengen, og svarer med kolonnerne og
rækkerne, hver række en liste i kolonnernes rækkefølge:

```http
GET /documents/1.0/documents/{id}/versions/1/ifc-queries/property?pset=Reuse&property=GTIN
```

```json
{"name": "property", "columns": ["global_id", "class", "name", "value", "type"],
 "rows": [["1Xezbq735AdBO_4DerG66G", "IfcWallStandardCase", "YVT-A", "3", "IFCLABEL"]],
 "truncated": false}
```

| Forespørgsel | Parametre | Hvad den svarer på |
|---|---|---|
| `element-classes` | | Hvor mange elementer modellen har af hver klasse |
| `elements` | `class` | Elementerne af en klasse med den rumlige struktur, der indeholder hvert |
| `storeys` | | Etagerne, deres kote, og hvor mange elementer og rum hver rummer |
| `spaces` | | Rummene, deres etage og deres netto- og bruttoetageareal |
| `areas` | | Nettoetagearealet af hver etages rum, lagt sammen |
| `materials` | `class` | Hvert elements materialer: et eget eller dets lags, listes eller bestanddeles |
| `property` | `pset`, `property`, `class` | Værdien af én egenskab på hvert objekt, der har den, med dens IFC-type |
| `entity` | `global_id` | Én rodfæstet entitet: dens klasse, hver literal attribut, og hvad den henviser til og henvises til af, hver med IFC-attribut, STEP-id og klasse |
| `site` | | Hvor bygningen står: grundens referencebredde, -længde og -højde, og kortomregningen med sit koordinatsystem (østlig og nordlig koordinat, højde, drejning og skala), hvor modellen har en |
| `changed-since` | `since` | Hvad der er ændret i dokumentet siden en version: én række pr. ændring i hver versions ændringssæt frem til denne, eller én række med `whole_file` for en version uploadet som hel fil; besvares ud fra versionerne, så den behøver ingen graf |

`class` navngiver en IFC-klasse, for eksempel `IfcWall`, og tager dens
underklasser med: påkrævet for `elements`, valgfri for de andre. Et svar rummer
højst 10.000 rækker, og `truncated` siger, når der var flere; en forespørgsel
stoppes efter 10 sekunder. Hver forespørgsel begynder ved medlemmet og når
modellen gennem projektet, læser kun og tager sine værdier som parametre. En
version uden model, eller en som brugeren ikke må se, svarer 404, og en hvis
model stadig konverteres, svarer 409. Kapabilitetsdokumentet annoncerer
forespørgslerne i `ifc_queries`.

## Ændringssæt

En foreslået ændring af en model rejser som `bim_snippet` i en BCF 3.0-sag
(ADR 0021): `snippet_type` er `DataregiumIfcChangeSet`, `reference_schema` er
`GET /documents/1.0/ifc-changes/schema`, som enhver må læse, og selve snippetten
uploades med `PUT …/topics/{guid}/snippet`, hvor serveren holder den til
skemaet og svarer `400` med, hvad der er galt. Et nyt projekt tillader
snippettypen; en administrator føjer den til et ældre projekts værdier. Et
ændringssæt angiver sin basisversion, hvem der foreslog det, med AI-modellen og
værktøjskaldet, hvor en AI gjorde det, og sine ændringer, hver på én attribut
hos én instans. Instansen angives med et GlobalId og en sti fra den
rodfæstede entitet i IFC's attributnavne med indeks, og med sit STEP-id kun,
når intet GlobalId når den. `set` giver
attributten en værdi, `add` og `remove` ændrer ét medlem af et aggregat, og
`copy` beder om en kopi af en instans, som flere deler, og som ellers ændres
for dem alle. En værdi er en skalar, en instans (`{"step_id": 120}` eller et
GlobalId med sti), en typet værdi (`{"type": "IfcLengthMeasure", "value": 3.2}`),
en enumeration (`{"enum": "NOTDEFINED"}`) eller en liste af dem.
Kapabilitetsdokumentet annoncerer formen som `ifc_changes`. Hvad ændringerne
gør ved modellen, prøves, når forslaget prøves, det næste trin; i dag holder
serveren formen.

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

Kun en `editor` eller en `manager` i projektet foreslår et ændringssæt (ADR
0028): en `contributor`, der uploader et, også til sin egen sag, får `403` med
begrundelsen, og intet gemmes, mens en snippet af en anden type uploades som
før. Det samme gælder det ændringssæt, serveren foreslår nedenfor.

`delete` fjerner en instans, der udpeges med sit STEP-id, og som intet refererer til, som en, intet GlobalId når; en
instans, som noget stadig refererer til, springes over og nævnes i prøvningen. Serveren foreslår selv et sådant
ændringssæt med `POST /documents/1.0/projects/{id}/ifc-unreachable` og versionen som `document_id` og
`version_index`: den laver en sag, hvis snippet fjerner hver instans, som versionens kontrol `graph` finder uden for
rækkevidde, og ændringssættet prøves og godkendes som alle andre, så den version, det kom fra, beholder instanserne.
Svaret navngiver sagen, hvor mange instanser det fjerner, og hvor prøvningen findes; `404`, når versionen ikke har
nogen konverteret model, og `409`, når intet i den er uden for rækkevidde. Kapabilitetsdokumentet viser
handlingerne i `ifc_changes.ops` og adressen som `ifc_changes.unreachable_url`.

Et ændringssæt lavet med Dataspatiums skriveværktøjer bærer også deres operationer som `ops`, med `ops_form`
`dataspatium-tools/1`, så nye elementer, sletninger og relationer kommer med i forslaget. Hver operation angiver sit
værktøj som `tool` og har værktøjets argumenter ved siden af sig, længder i meter: `create_storeys_and_grid`,
`create_wall`, `create_slab`, `create_roof`, `create_opening`, `create_spaces`, `set_properties`,
`set_classification`, `assign`, `transform_elements`, `delete_elements` og `set_site`. Serveren kører dem med en kopi
af appens egen kode (`opencde/ifcgraph/ops.py`), så de samme operationer giver den samme model i appen og på
serveren, i filens enhed, med den, der foreslog, og serveren i de ejerhistorikker, som IfcOpenShell laver. Det, som
væg-, dæk-, tag- og åbningsoperationerne skaber, hedder `new-1`, `new-2` … i deres rækkefølge, og det gør hvert rum,
som `create_spaces` opregner, også. En operation angiver et element med dets GlobalId, med dets STEP-id kun, hvor
intet GlobalId når det, eller med sådan en ref, og en etage med dens navn. `create_wall` giver en væg dens
midterlinje som en `Axis`-repræsentation, og `create_spaces` gør de rum, væggene lukker om, fundet som rapportens
`rooms` findes, til rum (`IfcSpace`) på deres etage, ud fra filen, som den er ved det trin: hvert med rummets omrids
op til næste etage, `Qto_SpaceBaseQuantities` og fysiske rumafgrænsninger mod væggene langs dets kant og mod dørene
og vinduerne i dem; en dør eller et vindue, der laves senere i sådan en væg, afgrænser også rummet.
`changes` må da være tom: ved siden af operationerne beskriver ændringerne, hvad
operationerne gør ved eksisterende instanser, som appen fandt det, til fletningen, og en ændring, som operationerne
allerede har lavet, tæller som anvendt. Kapabilitetsdokumentet annoncerer formen som `ifc_changes.ops_form` og
værktøjerne som `ifc_changes.ops_tools`.

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

Prøven anvender først operationerne og derefter ændringerne og tæller begge i `change_count`. En operation, der ikke
kan anvendes, er en anmærkning af arten `op` med sit indeks (`op`) og `tool`, med ordene i appens kode, som kan
citere dens argumenter og filen; operationerne efter den og ændringerne anvendes ikke, som i appen. Prøven giver
også `created`, GlobalId for hvert skabt element efter dets ref, så klienten kan parre sine egne, og `notes`, hvad en
operation ikke kunne gøre i filens skema, som kortkonverteringen i IFC2X3.

Når IFC-LPG-modulet er slået til, prøver serveren hvert ændringssæt, når det
uploades: en arbejder anvender ændringerne på basisversionens fil, resultatet
går gennem de kontroller, en upload får (IFC-skemaet, buildingSMARTs regler og
projektets IDS-dokumenter), og prøven er `clean`, når hver ændring kunne
anvendes, og ingen anmærkning er ny i forhold til basisversionens rapport,
ellers `issues`. `GET /bcf/3.0/projects/{id}/topics/{guid}/ifc-proposal` giver
tilstanden, hvor mange ændringer der blev anvendt, og de nye anmærkninger, hver
som i en versions rapport; en ændring, der ikke kunne anvendes, er en
anmærkning af arten `proposal`, der siger hvorfor uden at citere filen. En ny
snippet erstatter prøven, og prøven følger med sagen, når den slettes.
`ifc_changes` i kapabilitetsdokumentet siger, om ændringssæt prøves (`tried`),
og hvor prøven er (`proposal_url`).

`GET /documents/1.0/documents/{id}/ifc-proposals` lister de ændringssæt, der
er prøvet mod et dokument, for et medlem af dets projekt, nyeste først: pr.
række sagens guid, titel og de første 200 tegn af dens beskrivelse, prøvens
tilstand, basisversionen, hvor mange ændringer sættet rummer, hvem der
foreslog det, hvornår prøven sluttede, den version det blev, hvor det blev
godkendt, og adresserne på prøven (`proposal_url`) og dens godkendelse
(`approve_url`). Et forslag navngiver sin basis fra det øjeblik, det sættes i
kø, så listen rummer det før prøven, og når prøven mislykkedes. `$top` og
`$skip` blader i listen som i BCF-listerne; en liste, serveren har skåret,
bærer `X-Total-Count` og `Link: <…>; rel="next"`. `404` for et dokument,
medlemmet ikke må se, og når IFC-LPG-modulet er slået fra.
Kapabilitetsdokumentet giver adressen som `ifc_changes.ifc_proposals_url`.

En `manager` godkender en ren prøve med `POST …/ifc-proposal/approve`: den
anvendte fil bliver basisdokumentets næste version, med `base_version_index`,
`change_set_id` (sagens guid), `proposed_by` og `approved_by` i sine metadata,
og AI-modellen og værktøjskaldet, hvor en AI foreslog den; svaret er den nye
version, som Documents API giver den, og den konverteres og kontrolleres som
en upload. Sagen får en kommentar med versionens adresse, et viewpoint, der markerer de ændrede elementer, og
status `Closed`, hvor projektet har den værdi. `412 version_conflict` siger, at dokumentet er
gået videre siden basen; `409`, at prøven ikke er ren eller allerede er
godkendt. En AI foreslår kun: godkendelsen er et menneskes.
Hvor projektet har hold, lister prøven i `teams` de hold, hvis del af modellen
ændringssættet rører: det, specifikationerne i et holds IDS-dokument gælder for, i
basens fil eller den ændrede. Et ændringssæt, der rører ét holds del, godkendes af
holdets ansvarlige alene, ikke af en `manager`; et, der rører flere holds dele eller
ingens, af en `manager`, og ligeså et, hvis dele ikke kunne findes (`teams_error`).

Når dokumentet er gået videre siden basen, fletter serveren: ændringerne i
versionerne derimellem, hver godkendt fra et ændringssæt, sammenlignes attribut
for attribut med forslagets. Kolliderer ingen, prøves ændringssættet igen mod
den seneste version, med det samme, og godkendes mod den, så den nye versions
basis er den seneste. Kolliderer nogle, eller blev en version derimellem
uploadet som hel fil, er svaret `412 version_conflict` med de kolliderende
attributter i `conflicts` (`#123.Name`, eller GlobalId, sti og attribut; `*`
for en hel fil), så klienten kan flette trevejs og sende igen.

Instanserne sammenlignes, ikke de nøgler, klienterne skrev: hver ændring
opløses i den version, den blev lavet på, og navngives med sin kanoniske sti
(IFC-LPG's `ifc_lpg.paths`), så to ændringer, der når en delt instans fra
forskellige GlobalId, alligevel kolliderer, og `conflicts` navngiver instansen
med den sti. Ved siden af giver `conflict_details` pr. kollision `key`,
forslagets egne `guid`, `path` eller `step_id`, `attribute` og `op`, hvad
basen holdt (`base`), hvad den seneste version holder (`theirs`), hvad
forslaget sætter (`ours`), alle i ændringssættets værdiform, og den
mellemliggende version, der ændrede det (`version_index`); en værdi, der ikke
kunne læses, er `null`. Klienten lader en person vælge pr. kollision, sender
en ny snippet på den seneste version og godkender igen. En klient, der ikke kan
skære én ændring ud af sine operationer, sender dem igen med de nøgler, den
opgiver, i `keep_theirs`, som `conflicts` navngav dem: serveren prøver så
ændringssættet mod dokumentets seneste version og giver hver af de attributter
den seneste versions værdi tilbage efter operationerne og ændringerne.

En version bygget på en anden er en knude med sin forælder:
`parent_version_index` og et link til forælderversionen, på en version
godkendt fra et ændringssæt og på en upload, der angav `base_version_index`.
En version godkendt fra et ændringssæt bærer også `approved_by`,
`change_set_id` (sagens guid) og selve ændringerne, som
`GET /documents/1.0/documents/{id}/versions/{index}/ifc-changes` giver i
skemaets form, med basen og hvem der foreslog og godkendte den; en version
uploadet som hel fil svarer `404` dér. Hver version er stadig en hel fil,
hentet som før; `opencde ifc-lpg prune` fjerner ældre versioners grafer, da
hovedversionen og kæden af ændringssæt siger, hvad der ændrede sig.

## Sammenligne to versioner

Et medlem sammenligner to IFC-versioner element for element med det samme
bearer-token som Documents API: en version med en anden af samme dokument,
eller med `?other_document_id=` en version af et andet dokument i projektet.
Arbejderen parrer de rodfæstede entiteter efter GlobalId og svarer med
`added` (kun den anden har dem), `removed` (kun denne har dem) og `changed` (i
begge, med attributter, der afviger), hvert element angivet med GlobalId,
klasse, navn og etage, og for et ændret de stier, der afviger, med gammel og
ny værdi: en direkte attribut ved sit navn, en egenskab som `Pset.Property`,
`ObjectPlacement` (4×4-matricen), `Representation` (et fingeraftryk af
formen), `Container` (etagen) og `Type`. Relationer og egenskabssæt foldes
ind i de elementer, de hører til, og hver liste rummer højst 10.000 elementer.
Forskellen beregnes på forespørgsel og gemmes aldrig; en stor model tager et
stykke tid. Versionens side tilbyder den samme sammenligning som lister, og
kapabilitetsdokumentet annoncerer den som `ifc_diff`.

```http
GET /documents/1.0/documents/{document_id}/versions/{version_index}/ifc-diff/{other_index}
```

## Kollisionskontrol

Et medlem sammenligner to IFC-dokumentversioner i et projekt for kollisioner,
med det samme bearer-token som Documents API:
`POST /documents/1.0/projects/{project_id}/ifc-clash` med de to versioner,
tilstanden (`intersection`: elementer, der går ind i hinanden dybere end
`tolerance`; `clearance`: elementer tættere på hinanden end `clearance`, begge i
meter) og, hvis man vil, hver sides IFC-klasser. Kontrollen kører i en
arbejdsproces bag konverteringskøen; svarets `url` giver rapporten, `done` eller
`failed` efter et stykke tid. Hver kollision navngiver begge elementer (dokument,
version, STEP-id, GlobalId, klasse, navn, etage), sin art, dybden eller
afstanden og punktet, hvor den blev målt, i den form Dataspatiums egen
kollisionskerne skriver, så appen viser serverens resultat som sit eget.
`POST …/ifc-clash/{id}/topics` gør valgte kollisioner til BCF-sager med hver sit
viewpoint, kun på forespørgsel. Kapabilitetsdokumentet annoncerer kontrollen som
`ifc_clash`, når operatøren har sat `OPENCDE_IFC_LPG_CLASH_ENABLED=true`; en
rapport beholder højst `OPENCDE_IFC_LPG_CLASH_MAX_CLASHES` kollisioner.

```http
POST /documents/1.0/projects/{project_id}/ifc-clash
{"a": {"document_id": "…", "version_index": 1, "types": ["IfcWall"]},
 "b": {"document_id": "…", "version_index": 2},
 "mode": "intersection", "tolerance": 0.001}
```

## En bygning ind i en anden model

En bygning fra én model kommer ind i et andet projekts model som den næste version
af dets dokument; de to modeller ændres ikke. Model A er en version i dette projekt,
model B en version i et hvilket som helst projekt, som kalderen er medlem af, og
begge skal være konverteret, med samme skema og længdeenhed.
`POST /documents/1.0/projects/{project_id}/ifc-merge/report` viser ethvert medlem af
begge projekter, hvad der ville ske: hvor mange objekter og instanser der følger med,
objekterne med et GlobalId, som begge har (`collisions`, med `same` og det `choice`,
der gælder), de relationer, der udelades, fordi de kun peger ud af bygningen, og A's
kontekster og placeringer, der bruges. Hvor indholdet af et sådant objekt er
forskelligt, træffes et valg for det: `a` beholder A's, `b` sætter B's i stedet, og
`new` beholder begge, B's med et nyt GlobalId; `default` giver ét valg for dem alle.
En enhed af en art, som A ikke har, som en arealenhed, følger med ind i A's enheder og
listes i `units_added`; en enhed af en art, som begge har, skal være den samme.

En `manager` i projektet starter sammenfletningen med `POST …/ifc-merge` og samme
krop. Den kører som et job i konverteringskøen, og svarets `url` giver dens tilstand:
`conflict` med de objekter, der stadig mangler et valg, `failed` med årsagen, eller
`done` med `version_index`, den nye version af A's dokument. Den sammenflettede model
kontrolleres først mod A og B og må ikke have nogen anmærkning, som de ikke har;
derefter skrives den ud som den næste version, med A's version som forælder og
`merged_from_document`, `merged_from_version` og `merged_building` i sine metadata,
og konverteres og kontrolleres som en upload. A's version skal være dokumentets
seneste (ellers 412 `version_conflict`). Kapabilitetsdokumentet annoncerer den som
`ifc_merge`.

Hvor B's skema eller længdeenhed ikke er A's, siger rapporten det (422), og en
`editor` eller `manager` forbereder først B med `POST …/ifc-merge/prepare` og `base`
og `other`: et job, der laver en kopi af B migreret til A's skema og med sine længder
i A's enhed. Når det er `done`, får dets `merge_id`, givet som `other.prepared`,
kopien til at stå for B i rapporten og sammenfletningen indtil `expires_at`, et døgn
senere; derefter fjerner serveren den. En anden enhed, der er forskellig, konverteres
ikke, og jobbet fejler med den.
Det, A's skema ikke har et modstykke til, som IFC2X3's IfcWindowStyle i IFC4X3
eller de ejerhistorikker, IFC2X3 kræver, giver jobbet tilstanden `conflict`:
`report.problems` lister hvert problem med sin `key`, hvad det rører, og sine
`options` (`type`, `proxy`, `leave_out`, `polyline`, `owner`, `virtual`, `dated`,
`assignment`, `context`), og et nyt `POST …/ifc-merge/prepare` med `resolutions`, det valgte
alternativ pr. nøgle, laver kopien. Kopien kontrolleres derefter mod B: en med en
anmærkning, B ikke havde, laves ikke, og jobbet bliver `failed` med dem i `report.new`.

```http
POST /documents/1.0/projects/{project_id}/ifc-merge
{"base": {"document_id": "…", "version_index": 3},
 "other": {"project_id": "…", "document_id": "…", "version_index": 1},
 "building": "3AMeTOOFsdVLZuNV0$27s5", "choices": {"1Xezbq735AdBO_4DerG66G": "b"}}
```

## Arbejdskopien

Ved siden af arkivet kan serveren holde en arbejdskopi: en anden graf,
Memgraph i hukommelsen, hvor hovedversionens model for hvert dokument også
importeres (ADR 0024). Arkivet beholder hver version og forbliver sandheden;
arbejdskopien holder én model pr. dokument, den senest konverterede, og
besvarer de navngivne forespørgsler for den, så en stor model læses fra
hukommelsen. `OPENCDE_WORKCOPY_GRAPH_URI` angiver den
(`OPENCDE_WORKCOPY_GRAPH_DIALECT`, `_USER`, `_PASSWORD` og `_DATABASE` ved siden
af); overlejringen `docker/compose.workcopy.yaml` føjer Memgraph til enhver
stak, uden at den offentliggøres. En konvertering importerer de samme poster i
begge grafer i IFC-LPG's dialektneutrale form, erstatter dokumentets tidligere
model i arbejdskopien og fejler aldrig på arbejdskopiens vegne: en kopi, der
ikke kunne laves, markeres `failed` dér, og arkivet røres ikke. En model,
arkivet ikke længere har, forlader arbejdskopien ved næste oprydningsrunde.
`GET …/ifc-queries` siger i `workcopy`, om versionens model er der, `/readyz`
rapporterer arbejdskopiens tilstand uden at afhænge af den, og
kapabilitetsdokumentet siger i `ifcgraph.workcopy`, om en er konfigureret.

```sh
# .env: COMPOSE_FILE=docker/compose.yaml:docker/compose.local.yaml:docker/compose.workcopy.yaml
docker compose up -d
```

## Hvor bygningsdelene er, og geometrien

Efter en konvertering kører serveren IFC-LPG's geometriarbejder én gang over
filen (`python -m ifc_lpg.spatial`; `OPENCDE_IFC_LPG_SPATIAL`, slået til som
standard med ekstraet): IfcOpenShell bygger hver bygningsdels form, og
arbejderen skriver en kasse pr. bygningsdel i projektkoordinater og meshene,
hver delt mesh én gang. Kasserne går ind i grafen som punkterne `bbox_min`,
`bbox_max` og `bbox_centre` på bygningsdelens `Entity`, med et punktindeks på
`bbox_centre` i arkivet og i arbejdskopien, så en forespørgsel finder det, der
er nær et punkt eller inde i et volumen; `Model` bærer `spatial_at`,
`spatial_products` og `spatial_failed`. Posterne gemmes i lageret, og
`GET …/ifc-geometry` bygger en binær glTF af dem, første gang der spørges
efter den: hver delt mesh én gang, en node pr. bygningsdel, der instantierer
den med bygningsdelens matrix, navngivet med sit GlobalId og med klasse,
STEP-id og etage i `extras`, under en node pr. etage, og en rod, der drejer
modellen fra IFC's Z op til glTF's Y op. `lod=box` giver kasserne i stedet, én
terning, som hver bygningsdel instantierer, nogle få byte hver; `classes`
(IFC-klasser, kommaseparerede) og `storey` (et GlobalId) vælger
bygningsdelene. Filen gemmes og kommer med et `ETag` for modellen og filtrene,
så `If-None-Match` besvares med `304`. Geometrigennemløbet fælder aldrig en
konvertering: mislykkes det, noterer modellen `spatial_error`, og ruten
svarer `404`; mens versionen stadig konverteres, `409`. Kapabilitetsdokumentet
annoncerer det som `ifc_geometry`.

```http
GET /documents/1.0/documents/{document_id}/versions/{version_index}/ifc-geometry?lod=full&classes=IfcWall,IfcSlab
```

```cypher
// Bygningsdelene inden for to meter fra en væg, i samme model
MATCH (w:Entity:IfcWall {GlobalId: $guid})
MATCH (e:Entity {model_id: w.model_id}) WHERE e.bbox_centre IS NOT NULL AND e <> w
  AND point.distance(e.bbox_centre, w.bbox_centre) < 2.0
RETURN e.GlobalId, e.ifc_class, point.distance(e.bbox_centre, w.bbox_centre) AS distance ORDER BY distance
```

## Forespørgsler fra Dataspatium

[Dataspatium](https://github.com/marwiss/Dataspatium), browserklienten, der
udvikles sammen med denne server, kører Cypher mod denne graf gennem sin
Neo4j-kilde over Bolt (WebSocket på Bolt-porten), når operatøren eksponerer
databasen, som udviklingsoverlejringen gør på `127.0.0.1:7697`. Dets
Dataregium-arbejdsområde bruger mønstrene ovenfor (modeller, klasser,
komponenter gennem `GlobalId`, den seneste færdige model per dokument);
forespørgslerne findes i Dataspatiums dokumentation (`docs/grafer.md`). En
produktionsserver offentliggør ikke Bolt; administrations-API'ets
grafforespørgsel (`OPENCDE_GRAPH_QUERY_ENABLED`,
[client-guide.md §7](client-guide.md)) giver administratorer læsende Cypher
uden porten. Appen tegner også grafen, i sit
kort IFC-LPG, gennem den forespørgsel eller over Bolt.

## Grænser og status

- Én konvertering ad gangen; store modeller sættes i kø. Eksempelmodellen
  (248 entiteter) importeres på omkring et sekund; en arkitektmodel på 200 MB
  tager minutter.
- `Conversion` bærer `state`, `entities`, `relationships`,
  `lossless`, `geometry`, `schema`, `ifc_project_guid`, tidsstempler og `error`. Administratorer kan
  inspicere den i Neo4j Browser eller Memgraph Lab:
  `MATCH (c:Conversion) RETURN c.file_name, c.state, c.entities, c.error`.
- Sletning af et projekt sletter dets modellers entiteter med det.
- En model kommer identisk tilbage fra begge databaser op til 224.496 instanser og 19 MB, i
  hver form, der er målt. Intet større er prøvet.
