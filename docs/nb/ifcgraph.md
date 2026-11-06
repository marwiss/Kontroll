# IFC-graf

Den valgfrie IFC-grafmodulen gjør en opplastet IFC-modell til grafdata, slik
at komponentene i et BCF-viewpoint kan knyttes til bygningsdelene de peker
på, og slik at spørsmål om modellen kan stilles i Cypher ved siden av sakene
og dokumentene.

Slå den på med `OPENCDE_IFCGRAPH_ENABLED=true` og installer ekstrapakken
`ifcgraph` (`uv sync --extra ifcgraph`). Docker-imaget inneholder ekstrapakken
som standard (`ARG OPENCDE_EXTRAS` i Dockerfile), noe som mer enn dobler
størrelsen (omkring 680 MB mot 300 MB); bygg med
`--build-arg OPENCDE_EXTRAS=` for et slankere image uten IfcOpenShell når
modulen forblir av.

## Hva som skjer ved opplasting

1. En Documents API-opplasting fullføres (eller en fil lastes opp fra
   utvalgssiden, eller et BCF-prosjektdokument postes) med et `.ifc`- eller
   `.ifczip`-navn.
2. Serveren oppretter en `IfcModel`-node (tilstand `queued`) knyttet til
   prosjektet og starter en konvertering i bakgrunnen, én om gangen.
3. En separat arbeidsprosess (`python -m opencde.ifcgraph.worker`) parser
   filen med IfcOpenShell. Den kjører med en tidsgrense
   (`OPENCDE_IFCGRAPH_TIMEOUT_SECONDS`, 15 minutter), en adresseromsgrense på
   POSIX (`OPENCDE_IFCGRAPH_MEMORY_MB`, 4 GiB) og et tak for antall entiteter
   (`OPENCDE_IFCGRAPH_MAX_ENTITIES`). Et krasj eller en henging dreper
   arbeidsprosessen, ikke serveren. `.ifczip` pakkes ut med opplastingens
   størrelsesgrense.
4. Postene importeres i batcher av `UNWIND … CREATE` (portabel Cypher, ingen
   APOC). `IfcModel` ender i tilstanden `done` med tall og `IfcProject`-guid,
   eller `failed` med en feil.
5. En konvertering som en stoppet server har etterlatt, begynner på nytt: en køet så snart serveren er tilbake,
   en pågående når dobbel tidsgrense er passert, fordi den kan kjøre i en annen serverprosess.

`opencde seed` konverterer eksempelmodellen på samme måte når modulen er på.

## Grafen

Hver entitet blir en `IfcEntity`-node som bærer klassen sin og alle
supertypene sine som etiketter, for eksempel `IfcEntity:IfcWallStandardCase:IfcWall:
IfcBuildingElement:IfcElement:IfcProduct:IfcObject:IfcObjectDefinition:IfcRoot`.

| Egenskap | Betydning |
|---|---|
| `id` | `<modell-id>:<STEP-id>`, unik |
| `model_id`, `step_id` | modellen og `#123`-nummeret i filen |
| `ifc_class` | den konkrete klassen |
| `GlobalId`, `Name`, `Description`, `Tag`, … | hvert literalt attributt på entiteten, med IFC-navnet sitt |

Attributter som peker på andre entiteter, blir relasjoner navngitt etter
attributtet, skrevet som enhver relasjonstype i grafen med store bokstaver og
understreker ved ordgrensene:
`(:IfcRelDefinesByProperties)-[:RELATING_PROPERTY_DEFINITION]->(:IfcPropertySet)-[:HAS_PROPERTIES]->(:IfcPropertySingleValue)`.
Inverse attributter blir også relasjoner, så begge retninger leses naturlig:
`(:IfcWall)-[:IS_DEFINED_BY]->(:IfcRelDefinesByProperties)`.
Select-verdier pakkes ut (`IfcLabel('3')` blir `"3"`).

Utelatt som standard (`OPENCDE_IFCGRAPH_INCLUDE_GEOMETRY=false`):
representasjonselementer, representasjoner, profiler, plasseringer og stiler;
de utgjør det meste av en modell og er sjelden det en CDE-spørring trenger.
`IfcOwnerHistory` beholdes bare for `IfcProject`.

## Hvor metoden kommer fra

Konverteringen følger IFC-Graph-metoden til Zhu, Wu og Lei: én node per instans,
klassehierarkiet som etiketter, literale attributter som egenskaper og
attributter som peker på andre instanser, inverse attributter medregnet, som
relasjoner navngitt etter attributtet. Prototypen fra 2023 brukte artikkelens
kode. Konverteringen i denne serveren er skrevet på nytt.

Junxiang Zhu, Peng Wu og Xiang Lei: "IFC-graph for facilitating building
information access and query". *Automation in Construction* 148 (2023), 104778.
[doi:10.1016/j.autcon.2023.104778](https://doi.org/10.1016/j.autcon.2023.104778),
fritt tilgjengelig under CC BY 4.0.

Den skiller seg fra artikkelen på disse punktene:

- Geometri utelates med mindre den etterspørres. Artikkelen konverterer alt og
  nevner størrelsen på grafen som en begrensning.
- Postene skrives i puljer med `CREATE` fra en egen prosess. Artikkelen slår
  sammen hver node og relasjon, noe som søker etter duplikater i grafen og går
  tregere jo større grafen blir.
- Select-verdier blir egenskaper på noden sin. Artikkelen gir dem egne noder med
  en generert identifikator.
- Flere modeller deler én database og skilles med `model_id`. Artikkelen har én
  modell per database.
- Relasjonstypene skrives med store bokstaver, og `SAME_AS` og kopien av GTIN er
  tillegg her.

Rekkefølgen i lister går tapt også her, slik artikkelen påpeker om sin egen graf:
en relasjon sier ikke hvor i en liste målet sto.

## Opprydding

Hver opplasting av en IFC-fil legger til en `IfcModel` med entitetene sine, så
et prosjekt som mottar nye versjoner, samler grafer ingen spør mot.
Kommandolinjen lister og fjerner dem; dokumentene og filene deres blir alltid
igjen:

```sh
uv run opencde ifcgraph list --project <prosjekt-id>
uv run opencde ifcgraph prune                   # feilede modeller, og ferdige modeller erstattet av en nyere
                                                # ferdig versjon av samme dokument
uv run opencde ifcgraph prune --project <id> --all   # hver modell i ett prosjekt (en teststakk, for eksempel)
```

Modeller i kø og under kjøring fjernes aldri. Spørringer som vil ha én graf
per dokument, bør selv velge den siste ferdige modellen, siden eldre
versjoner blir igjen til de fjernes:

```cypher
MATCH (:Project {project_id: $project})-[:HAS_MODEL]->(m:IfcModel {state: 'done'})
WITH coalesce(m.document_id, m.bcf_document_guid) AS doc, m
ORDER BY m.version_index DESC, m.done_at DESC
WITH doc, collect(m)[0] AS latest
MATCH (e:IfcProduct {model_id: latest.id})
RETURN latest.file_name AS model, count(e) AS products
```

## Kobling av BCF-komponenter

Når et viewpoint opprettes med komponenter, får hver komponent hvis
`ifc_guid` matcher `GlobalId` til en bygningsdel i en av prosjektets
importerte modeller, en `SAME_AS`-relasjon til den. Den samme koblingen
kjører for hver eksisterende komponent i prosjektet når en modell er ferdig
importert, så viewpoints opprettet før modellen ble lastet opp, eller mens
den fortsatt ble konvertert, kobles også. Hvis bygningsdelen bærer den
konfigurerte egenskapen (`OPENCDE_IFCGRAPH_GTIN_PROPERTY_SET=Reuse`,
`OPENCDE_IFCGRAPH_GTIN_PROPERTY=GTIN`), kopieres verdien til komponenten som
`gtin`. Dette er bruksområdet fra forskningsrapporten fra 2023: en kontroll
(BCF-sak) som peker på byggevarer identifisert med GTIN.

```cypher
// Hvilke produkter peker dette viewpointet på, og hva er GTIN-ene deres?
MATCH (:Viewpoint {guid: $viewpoint})-[:HAS_COMPONENT]->(c:Component)-[:SAME_AS]->(e:IfcProduct)
RETURN c.ifc_guid, e.Name, c.gtin
```

```cypher
// Rapportens spørring, direkte på modellen: GTIN for hver vegg.
MATCH (w:IfcWall)-[:IS_DEFINED_BY]->(:IfcRelDefinesByProperties)-[:RELATING_PROPERTY_DEFINITION]
      ->(:IfcPropertySet {Name: 'Reuse'})-[:HAS_PROPERTIES]->(p:IfcPropertySingleValue {Name: 'GTIN'})
RETURN w.GlobalId, w.Name, p.NominalValue
```

```cypher
// Hver sak som berører en gitt bygningsdel.
MATCH (e:IfcEntity {GlobalId: $guid})<-[:SAME_AS]-(:Component)<-[:HAS_COMPONENT]-(v:Viewpoint)<-[:HAS_VIEWPOINT]-(t:Topic)
RETURN DISTINCT t.server_assigned_id, t.title, t.topic_status
```

BCF-tjenesten `files_information` viser importerte modellers
`IfcProject`-guid som `ifc_project`, som lar klienter fylle inn filene i
sakens hode.

## Spørringer fra Dataspatium

[Dataspatium](https://github.com/marwiss/Dataspatium), nettleserklienten som
utvikles sammen med denne serveren, kjører Cypher mot denne grafen gjennom
Neo4j-kilden sin over Bolt (WebSocket på Bolt-porten) når operatøren
eksponerer databasen, slik utviklingsoverlegget gjør på `127.0.0.1:7697`.
Kontroll-arbeidsområdet dets bruker mønstrene ovenfor (modeller, klasser,
komponenter via `SAME_AS`, den siste ferdige modellen per dokument);
spørringene ligger i Dataspatiums dokumentasjon (`docs/cad-bim.md`), og
live-kjøringene er listet i [acceptance.md](../acceptance.md). En
produksjonsserver publiserer ikke Bolt; administrasjons-API-ets grafspørring
(`OPENCDE_GRAPH_QUERY_ENABLED`, [client-guide.md §7](client-guide.md)) gir
administratorer lesende Cypher uten porten.

## Grenser og status

- Én konvertering om gangen; store modeller står i kø. Eksempelmodellen (248
  entiteter) importeres på omkring ett sekund; en arkitektmodell på 200 MB tar
  minutter.
- `IfcModel`-noden bærer `state`, `entities`, `relationships`, `skipped`,
  `schema`, `ifc_project_guid`, tidsstempler og `error`. Administratorer kan
  inspisere den i Neo4j Browser eller Memgraph Lab:
  `MATCH (m:IfcModel) RETURN m.file_name, m.state, m.entities, m.error`.
- Sletting av et prosjekt sletter entitetene til modellene dets med det.
