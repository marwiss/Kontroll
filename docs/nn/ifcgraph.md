# IFC-graf

Den valfrie IFC-grafmodulen gjer ein opplasta IFC-modell til grafdata, slik
at komponentane i eit BCF-viewpoint kan knytast til bygningsdelane dei peikar
på, og slik at spørsmål om modellen kan stillast i Cypher ved sida av sakene
og dokumenta.

Slå han på med `OPENCDE_IFCGRAPH_ENABLED=true` og installer ekstrapakken
`ifcgraph` (`uv sync --extra ifcgraph`). Docker-imaget inneheld ekstrapakken
som standard (`ARG OPENCDE_EXTRAS` i Dockerfile), noko som meir enn doblar
storleiken (omkring 680 MB mot 300 MB); bygg med
`--build-arg OPENCDE_EXTRAS=` for eit slankare image utan IfcOpenShell når
modulen held fram med å vere av.

## Kva som skjer ved opplasting

1. Ei Documents API-opplasting blir fullført (eller ei fil blir lasta opp frå
   utvalssida, eller eit BCF-prosjektdokument blir posta) med eit `.ifc`-
   eller `.ifczip`-namn.
2. Serveren opprettar ein `IfcModel`-node (tilstand `queued`) knytt til
   prosjektet og startar ei konvertering i bakgrunnen, éi om gongen.
3. Ein separat arbeidsprosess (`python -m opencde.ifcgraph.worker`) parsar
   fila med IfcOpenShell. Han køyrer med ei tidsgrense
   (`OPENCDE_IFCGRAPH_TIMEOUT_SECONDS`, 15 minutt), ei adresseromsgrense på
   POSIX (`OPENCDE_IFCGRAPH_MEMORY_MB`, 4 GiB) og eit tak for talet på
   entitetar (`OPENCDE_IFCGRAPH_MAX_ENTITIES`). Eit krasj eller ei henging
   drep arbeidsprosessen, ikkje serveren. `.ifczip` blir pakka ut med
   storleiksgrensa for opplastinga.
4. Postane blir importerte i batchar av `UNWIND … CREATE` (portabel Cypher,
   ingen APOC). `IfcModel` endar i tilstanden `done` med tal og
   `IfcProject`-guid, eller `failed` med ein feil.
5. Ei konvertering som ein stoppa server har late etter seg, byrjar på nytt: ei køa så snart serveren er tilbake,
   ei pågåande når dobbel tidsgrense er passert, fordi ho kan køyre i ein annan serverprosess.

`opencde seed` konverterer eksempelmodellen på same måte når modulen er på.

## Grafen

Kvar entitet blir ein `IfcEntity`-node som ber klassen sin og alle
supertypane sine som etikettar, til dømes `IfcEntity:IfcWallStandardCase:IfcWall:
IfcBuildingElement:IfcElement:IfcProduct:IfcObject:IfcObjectDefinition:IfcRoot`.

| Eigenskap | Tyding |
|---|---|
| `id` | `<modell-id>:<STEP-id>`, unik |
| `model_id`, `step_id` | modellen og `#123`-nummeret i fila |
| `ifc_class` | den konkrete klassen |
| `GlobalId`, `Name`, `Description`, `Tag`, … | kvart literalt attributt på entiteten, med IFC-namnet sitt |

Attributt som peikar på andre entitetar, blir relasjonar namngjevne etter
attributtet, skrivne som kvar relasjonstype i grafen med store bokstavar og
understrekar ved ordgrensene:
`(:IfcRelDefinesByProperties)-[:RELATING_PROPERTY_DEFINITION]->(:IfcPropertySet)-[:HAS_PROPERTIES]->(:IfcPropertySingleValue)`.
Inverse attributt blir òg relasjonar, så begge retningane les naturleg:
`(:IfcWall)-[:IS_DEFINED_BY]->(:IfcRelDefinesByProperties)`.
Select-verdiar blir pakka ut (`IfcLabel('3')` blir `"3"`).

Utelate som standard (`OPENCDE_IFCGRAPH_INCLUDE_GEOMETRY=false`):
representasjonselement, representasjonar, profilar, plasseringar og stilar;
dei utgjer det meste av ein modell og er sjeldan det ei CDE-spørjing treng.
`IfcOwnerHistory` blir halden på berre for `IfcProject`.

## Opprydding

Kvar opplasting av ei IFC-fil legg til ein `IfcModel` med entitetane sine, så
eit prosjekt som får nye versjonar, samlar grafar ingen spør mot.
Kommandolinja listar og fjernar dei; dokumenta og filene deira blir alltid
att:

```sh
uv run opencde ifcgraph list --project <prosjekt-id>
uv run opencde ifcgraph prune                   # mislukka modellar, og ferdige modellar erstatta av ein nyare
                                                # ferdig versjon av same dokument
uv run opencde ifcgraph prune --project <id> --all   # kvar modell i eitt prosjekt (ein teststakk, til dømes)
```

Modellar i kø og under køyring blir aldri fjerna. Spørjingar som vil ha éin
graf per dokument, bør sjølve velje den siste ferdige modellen, sidan eldre
versjonar blir att til dei blir fjerna:

```cypher
MATCH (:Project {project_id: $project})-[:HAS_MODEL]->(m:IfcModel {state: 'done'})
WITH coalesce(m.document_id, m.bcf_document_guid) AS doc, m
ORDER BY m.version_index DESC, m.done_at DESC
WITH doc, collect(m)[0] AS latest
MATCH (e:IfcProduct {model_id: latest.id})
RETURN latest.file_name AS model, count(e) AS products
```

## Kopling av BCF-komponentar

Når eit viewpoint blir oppretta med komponentar, får kvar komponent der
`ifc_guid` matchar `GlobalId` til ein bygningsdel i ein av dei importerte
modellane i prosjektet, ein `SAME_AS`-relasjon til han. Den same koplinga
køyrer for kvar eksisterande komponent i prosjektet når ein modell er ferdig
importert, så viewpoints oppretta før modellen vart lasta opp, eller medan
han framleis vart konvertert, blir òg kopla. Om bygningsdelen ber den
konfigurerte eigenskapen (`OPENCDE_IFCGRAPH_GTIN_PROPERTY_SET=Reuse`,
`OPENCDE_IFCGRAPH_GTIN_PROPERTY=GTIN`), blir verdien kopiert til komponenten
som `gtin`. Dette er bruksområdet frå forskingsrapporten frå 2023: ein
kontroll (BCF-sak) som peikar på byggjevarer identifiserte med GTIN.

```cypher
// Kva produkt peikar dette viewpointet på, og kva er GTIN-ane deira?
MATCH (:Viewpoint {guid: $viewpoint})-[:HAS_COMPONENT]->(c:Component)-[:SAME_AS]->(e:IfcProduct)
RETURN c.ifc_guid, e.Name, c.gtin
```

```cypher
// Spørjinga frå rapporten, direkte på modellen: GTIN for kvar vegg.
MATCH (w:IfcWall)-[:IS_DEFINED_BY]->(:IfcRelDefinesByProperties)-[:RELATING_PROPERTY_DEFINITION]
      ->(:IfcPropertySet {Name: 'Reuse'})-[:HAS_PROPERTIES]->(p:IfcPropertySingleValue {Name: 'GTIN'})
RETURN w.GlobalId, w.Name, p.NominalValue
```

```cypher
// Kvar sak som rører ved ein gjeven bygningsdel.
MATCH (e:IfcEntity {GlobalId: $guid})<-[:SAME_AS]-(:Component)<-[:HAS_COMPONENT]-(v:Viewpoint)<-[:HAS_VIEWPOINT]-(t:Topic)
RETURN DISTINCT t.server_assigned_id, t.title, t.topic_status
```

BCF-tenesta `files_information` viser `IfcProject`-guid-en til importerte
modellar som `ifc_project`, som lèt klientar fylle inn filene i hovudet til
saka.

## Spørjingar frå Dataspatium

[Dataspatium](https://github.com/marwiss/Dataspatium), nettlesarklienten som
blir utvikla saman med denne serveren, køyrer Cypher mot denne grafen gjennom
Neo4j-kjelda si over Bolt (WebSocket på Bolt-porten) når operatøren
eksponerer databasen, slik utviklingsoverlegget gjer på `127.0.0.1:7697`.
Kontroll-arbeidsområdet der brukar mønstera ovanfor (modellar, klassar,
komponentar via `SAME_AS`, den siste ferdige modellen per dokument);
spørjingane ligg i dokumentasjonen til Dataspatium (`docs/cad-bim.md`), og
live-køyringane er lista i [acceptance.md](../acceptance.md). Ein
produksjonsserver publiserer ikkje Bolt; grafspørjinga i
administrasjons-API-et (`OPENCDE_GRAPH_QUERY_ENABLED`,
[client-guide.md §7](client-guide.md)) gjev administratorar lesande Cypher
utan porten.

## Grenser og status

- Éi konvertering om gongen; store modellar står i kø. Dømemodellen (248
  entitetar) blir importert på omkring eitt sekund; ein arkitektmodell på
  200 MB tek minutt.
- `IfcModel`-noden ber `state`, `entities`, `relationships`, `skipped`,
  `schema`, `ifc_project_guid`, tidsstempel og `error`. Administratorar kan
  inspisere han i Neo4j Browser eller Memgraph Lab:
  `MATCH (m:IfcModel) RETURN m.file_name, m.state, m.entities, m.error`.
- Sletting av eit prosjekt slettar entitetane til modellane i det.
