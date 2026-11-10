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
2. Serveren opretter en `Model`-node (tilstand `queued`) knyttet til
   projektet og starter en konvertering i baggrunden, én ad gangen.
3. En separat arbejdsproces (`python -m ifc_lpg.worker`) læser
   filen. Den kører med en tidsgrænse
   (`OPENCDE_IFC_LPG_TIMEOUT_SECONDS`, 15 minutter), en adresserumsgrænse på
   POSIX (`OPENCDE_IFC_LPG_MEMORY_MB`, 4 GiB) og et loft over antallet af
   entiteter (`OPENCDE_IFC_LPG_MAX_ENTITIES`). Et nedbrud eller en hængning
   dræber arbejdsprocessen, ikke serveren. `.ifczip` pakkes ud med uploadens
   størrelsesgrænse.
4. Posterne importeres i batches af `UNWIND … CREATE` (portabel Cypher, ingen
   APOC). `Model` ender i tilstanden `done` med tal og `IfcProject`-guid,
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
med de samme grænser. En IDS, der uploades senere, gælder de IFC-versioner, der
uploades efter den.

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

### Det, den konverterede model viser

Når modellen er konverteret, får rapporten sin egen kontrol, `graph`, med to slags bemærkninger. En instans, som intet
med et GlobalId når, frem eller tilbage, er en advarsel af typen `reachability`, med sit STEP-id i `step_id` og sin
klasse i meddelelsen: kun det nummer navngiver den, som en placering, intet bruger, så et ændringssæt kan udpege den
alene med sit STEP-id. Et produkt, hvis form geometripasset ikke kunne bygge, er en bemærkning af typen `geometry`,
med sit GlobalId. Ingen af dem afviser filen: de kommer efter uploaden, og en advarsel giver status `warnings`. Før
modellen er konverteret, har rapporten ingen kontrol `graph`.

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
- Relationstyperne skrives med store bogstaver, og `SAME_AS` og kopien af GTIN er
  tilføjelser her.

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

Hver upload af en IFC-fil tilføjer en `Model` med dens entiteter, så et
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
MATCH (:Project {project_id: $project})-[:HAS_MODEL]->(m:Model {state: 'done'})
WITH coalesce(m.document_id, m.bcf_document_guid) AS doc, m
ORDER BY m.version_index DESC, m.done_at DESC
WITH doc, collect(m)[0] AS latest
MATCH (e:IfcProduct {model_id: latest.id})
RETURN latest.file_name AS model, count(e) AS products
```

## Kobling af BCF-komponenter

Når et viewpoint oprettes med komponenter, får hver komponent, hvis `ifc_guid`
matcher `GlobalId` for en bygningsdel i en af projektets importerede modeller,
en `SAME_AS`-relation til den. Den samme kobling kører for hver eksisterende
komponent i projektet, når en model er færdigimporteret, så viewpoints
oprettet, før modellen blev uploadet, eller mens den stadig blev konverteret,
kobles også. Hvis bygningsdelen bærer den konfigurerede egenskab
(`OPENCDE_IFC_LPG_GTIN_PROPERTY_SET=Reuse`,
`OPENCDE_IFC_LPG_GTIN_PROPERTY=GTIN`), kopieres dens værdi til komponenten
som `gtin`. Det er anvendelsen fra forskningsrapporten fra 2023: en kontrol
(BCF-sag), der peger på byggeprodukter identificeret med GTIN.

```cypher
// Hvilke produkter peger dette viewpoint på, og hvad er deres GTIN?
MATCH (:Viewpoint {guid: $viewpoint})-[:HAS_COMPONENT]->(c:Component)-[:SAME_AS]->(e:IfcProduct)
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
MATCH (e:Entity {GlobalId: $guid})<-[:SAME_AS]-(:Component)<-[:HAS_COMPONENT]-(v:Viewpoint)<-[:HAS_VIEWPOINT]-(t:Topic)
RETURN DISTINCT t.server_assigned_id, t.title, t.topic_status
```

BCF-tjenesten `files_information` viser importerede modellers
`IfcProject`-guid som `ifc_project`, hvilket lader klienter udfylde filerne i
sagens hoved.

## Navngivne forespørgsler

Et medlem af et projekt stiller spørgsmål til en versions model ved navn, med
det samme bearer-token som til Documents API; fri Cypher forbliver
administratorernes (ADR 0016).
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

`delete` fjerner en instans, der udpeges med sit STEP-id, og som intet refererer til, som en, intet GlobalId når; en
instans, som noget stadig refererer til, springes over og nævnes i prøvningen. Serveren foreslår selv et sådant
ændringssæt med `POST /documents/1.0/projects/{id}/ifc-unreachable` og versionen som `document_id` og
`version_index`: den laver en sag, hvis snippet fjerner hver instans, som versionens kontrol `graph` finder uden for
rækkevidde, og ændringssættet prøves og godkendes som alle andre, så den version, det kom fra, beholder instanserne.
Svaret navngiver sagen, hvor mange instanser det fjerner, og hvor prøvningen findes; `404`, når versionen ikke har
nogen konverteret model, og `409`, når intet i den er uden for rækkevidde.

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

En `manager` godkender en ren prøve med `POST …/ifc-proposal/approve`: den
anvendte fil bliver basisdokumentets næste version, med `base_version_index`,
`change_set_id` (sagens guid), `proposed_by` og `approved_by` i sine metadata,
og AI-modellen og værktøjskaldet, hvor en AI foreslog den; svaret er den nye
version, som Documents API giver den, og den konverteres og kontrolleres som
en upload. Sagen får en kommentar med versionens adresse, et viewpoint, der markerer de ændrede elementer, og
status `Closed`, hvor projektet har den værdi. `412 version_conflict` siger, at dokumentet er
gået videre siden basen; `409`, at prøven ikke er ren eller allerede er
godkendt. En AI foreslår kun: godkendelsen er et menneskes.

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
en ny snippet på den seneste version og godkender igen.

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
komponenter via `SAME_AS`, den seneste færdige model per dokument);
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
- `Model`-noden bærer `state`, `entities`, `relationships`, `skipped`,
  `lossless`, `geometry`, `schema`, `ifc_project_guid`, tidsstempler og `error`. Administratorer kan
  inspicere den i Neo4j Browser eller Memgraph Lab:
  `MATCH (m:Model) RETURN m.file_name, m.state, m.entities, m.error`.
- Sletning af et projekt sletter dets modellers entiteter med det.
- En model kommer identisk tilbage fra begge databaser op til 224.496 instanser og 19 MB, i
  hver form, der er målt. Intet større er prøvet.
