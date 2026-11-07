# IFC-graf

Det valgfrie IFC-grafmodul gør en uploadet IFC-model til grafdata, så
komponenterne i et BCF-viewpoint kan knyttes til de bygningsdele, de peger
på, og så spørgsmål om modellen kan stilles i Cypher ved siden af sagerne og
dokumenterne.

Slå det til med `OPENCDE_IFCGRAPH_ENABLED=true`, og installér ekstrapakken
`ifcgraph` (`uv sync --extra ifcgraph`). Docker-imaget indeholder ekstrapakken
som standard (`ARG OPENCDE_EXTRAS` i Dockerfile), hvilket mere end fordobler
dets størrelse (omkring 680 MB mod 300 MB); byg med
`--build-arg OPENCDE_EXTRAS=` for et slankere image uden IfcOpenShell, når
modulet forbliver slået fra.

## Hvad der sker ved upload

1. En Documents API-upload afsluttes (eller en fil uploades fra
   udvælgelsessiden, eller et BCF-projektdokument postes) med et `.ifc`-
   eller `.ifczip`-navn.
2. Serveren opretter en `IfcModel`-node (tilstand `queued`) knyttet til
   projektet og starter en konvertering i baggrunden, én ad gangen.
3. En separat arbejdsproces (`python -m opencde.ifcgraph.worker`) læser
   filen. Den kører med en tidsgrænse
   (`OPENCDE_IFCGRAPH_TIMEOUT_SECONDS`, 15 minutter), en adresserumsgrænse på
   POSIX (`OPENCDE_IFCGRAPH_MEMORY_MB`, 4 GiB) og et loft over antallet af
   entiteter (`OPENCDE_IFCGRAPH_MAX_ENTITIES`). Et nedbrud eller en hængning
   dræber arbejdsprocessen, ikke serveren. `.ifczip` pakkes ud med uploadens
   størrelsesgrænse.
4. Posterne importeres i batches af `UNWIND … CREATE` (portabel Cypher, ingen
   APOC). `IfcModel` ender i tilstanden `done` med tal og `IfcProject`-guid,
   eller `failed` med en fejl.
5. En konvertering, som en stoppet server har efterladt, begynder forfra: en sat i kø, så snart serveren er
   tilbage, en igangværende, når den dobbelte tidsgrænse er passeret, fordi den kan køre i en anden serverproces.

`opencde seed` konverterer eksempelmodellen på samme måde, når modulet er slået til.

## Grafen

Hver entitet bliver en `IfcEntity`-node, der bærer sin klasse og alle sine
supertyper som labels, for eksempel `IfcEntity:IfcWallStandardCase:IfcWall:
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

Ingen noder som standard (`OPENCDE_IFCGRAPH_INCLUDE_GEOMETRY=false`):
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
uv run opencde ifcgraph export <model-id> model.ifc            # skriv filen og validér den
uv run opencde ifcgraph export <model-id> model.ifc --verify   # og sammenlign den med den uploadede
```

Noderne er dem, forespørgsler har brug for. Det, de udelader, skrives ud som STEP og
komprimeres til tekst på `StepBlock`-noder, der hænger på `IfcModel`: det er i grafen,
men uden for Cyphers rækkevidde, og det kan ikke ændres der. Det kan ikke være
egenskaber på produkterne, da meget af det deles mellem dem. Med
`OPENCDE_IFCGRAPH_INCLUDE_GEOMETRY=true` bliver hver instans i stedet en node, til
flere gange størrelsen og importtiden; forespørgsler tog omtrent lige lang tid i
[målingerne](../adr/0010-a-lossless-graph-reads-and-writes-step-itself.md).

| I filen | I grafen |
|---|---|
| En reference | En relation med `position`, `[række, kolonne]` i en liste af lister; inverse relationer har ingen |
| En reference til en instans i en blok | Dens id, som i `Representation__step: 1234` |
| En typet værdi, `IFCLABEL('3')` | `NominalValue: "3"`, og `NominalValue__type: "IFCLABEL"` ved siden af |
| En liste af lister af tal | JSON-tekst |
| Det, der ikke har en enkel form, som en liste af typede værdier | Mærket JSON, med `$json` som type |
| Headeren | `ifc_header` på `IfcModel` |
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
afviser det, den ikke kan læse. [ADR 0010](../adr/0010-a-lossless-graph-reads-and-writes-step-itself.md) siger hvorfor, og
[ADR 0011](../adr/0011-a-file-written-from-the-graph-is-validated.md) hvordan en fil valideres.

`--verify` spørger, om de to filer rummer den samme model, efter definitionen i
[ADR 0009](../adr/0009-what-makes-two-ifc-files-the-same-model.md): en til en, værdi for værdi og uden tolerance, med georeferencen
navngivet i rapporten. Med `--geometry` bygges også hvert produkts mesh, og de
sammenlignes bit for bit. To vilkårlige filer kan sammenlignes med
`python -m opencde.ifcgraph.equivalence first.ifc second.ifc`.

Med `OPENCDE_IFCGRAPH_LOSSLESS=false` konverteres en model som før 3.0.0: den læses med
IfcOpenShell, og det, der ikke er noder, udelades helt. En sådan model, ligesom en, der
er konverteret af en tidligere version, kan ikke skrives tilbage.

## Oprydning

Hver upload af en IFC-fil tilføjer en `IfcModel` med dens entiteter, så et
projekt, der modtager nye versioner, samler grafer, som ingen forespørger.
Kommandolinjen lister og fjerner dem; dokumenterne og deres filer bliver
altid:

```sh
uv run opencde ifcgraph list --project <projekt-id>
uv run opencde ifcgraph prune                   # fejlede modeller, og færdige modeller erstattet af en nyere
                                                # færdig version af samme dokument
uv run opencde ifcgraph prune --project <id> --all   # hver model i ét projekt (en teststak, for eksempel)
```

Modeller i kø og under kørsel fjernes aldrig. Forespørgsler, der vil have én
graf per dokument, bør selv vælge den seneste færdige model, da ældre
versioner bliver, indtil de fjernes:

```cypher
MATCH (:Project {project_id: $project})-[:HAS_MODEL]->(m:IfcModel {state: 'done'})
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
(`OPENCDE_IFCGRAPH_GTIN_PROPERTY_SET=Reuse`,
`OPENCDE_IFCGRAPH_GTIN_PROPERTY=GTIN`), kopieres dens værdi til komponenten
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
MATCH (e:IfcEntity {GlobalId: $guid})<-[:SAME_AS]-(:Component)<-[:HAS_COMPONENT]-(v:Viewpoint)<-[:HAS_VIEWPOINT]-(t:Topic)
RETURN DISTINCT t.server_assigned_id, t.title, t.topic_status
```

BCF-tjenesten `files_information` viser importerede modellers
`IfcProject`-guid som `ifc_project`, hvilket lader klienter udfylde filerne i
sagens hoved.

## Forespørgsler fra Dataspatium

[Dataspatium](https://github.com/marwiss/Dataspatium), browserklienten, der
udvikles sammen med denne server, kører Cypher mod denne graf gennem sin
Neo4j-kilde over Bolt (WebSocket på Bolt-porten), når operatøren eksponerer
databasen, som udviklingsoverlejringen gør på `127.0.0.1:7697`. Dets
Kontroll-arbejdsområde bruger mønstrene ovenfor (modeller, klasser,
komponenter via `SAME_AS`, den seneste færdige model per dokument);
forespørgslerne findes i Dataspatiums dokumentation (`docs/grafer.md`), og
live-kørslerne er listet i [acceptance.md](../acceptance.md). En
produktionsserver offentliggør ikke Bolt; administrations-API'ets
grafforespørgsel (`OPENCDE_GRAPH_QUERY_ENABLED`,
[client-guide.md §7](client-guide.md)) giver administratorer læsende Cypher
uden porten. Appen tegner også grafen, i sit
kort IFC-graf, gennem den forespørgsel eller over Bolt.

## Grænser og status

- Én konvertering ad gangen; store modeller sættes i kø. Eksempelmodellen
  (248 entiteter) importeres på omkring et sekund; en arkitektmodel på 200 MB
  tager minutter.
- `IfcModel`-noden bærer `state`, `entities`, `relationships`, `skipped`,
  `lossless`, `schema`, `ifc_project_guid`, tidsstempler og `error`. Administratorer kan
  inspicere den i Neo4j Browser eller Memgraph Lab:
  `MATCH (m:IfcModel) RETURN m.file_name, m.state, m.entities, m.error`.
- Sletning af et projekt sletter dets modellers entiteter med det.
- En model kommer identisk tilbage fra begge databaser op til 224.496 instanser og 19 MB, i
  hver form, der er målt. Intet større er prøvet.
