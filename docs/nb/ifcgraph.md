# IFC-graf

Den valgfrie IFC-grafmodulen gjør en opplastet IFC-modell til grafdata, slik
at komponentene i et BCF-viewpoint kan knyttes til bygningsdelene de peker
på, og slik at spørsmål om modellen kan stilles i Cypher ved siden av sakene
og dokumentene.

Slå den på med `OPENCDE_IFCGRAPH_ENABLED=true` og installer ekstrapakken
`ifcgraph` (`uv sync --extra ifcgraph`). Docker-imaget inneholder ekstrapakken
som standard (`ARG OPENCDE_EXTRAS` i Dockerfile), noe som mer enn dobler
størrelsen (omkring 680 MB, eller 1,1 GB med buildingSMARTs regler, mot 300 MB); bygg med
`--build-arg OPENCDE_EXTRAS=` for et slankere image uten IfcOpenShell når
modulen forblir av.

## Hva som skjer ved opplasting

1. En Documents API-opplasting fullføres (eller en fil lastes opp fra
   utvalgssiden, eller et BCF-prosjektdokument postes) med et `.ifc`- eller
   `.ifczip`-navn.
2. Serveren oppretter en `IfcModel`-node (tilstand `queued`) knyttet til
   prosjektet og starter en konvertering i bakgrunnen, én om gangen.
3. En separat arbeidsprosess (`python -m opencde.ifcgraph.worker`) leser
   filen. Den kjører med en tidsgrense
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

## Kontroll av opplastinger mot IFC-skjemaet

Hver `.ifc`- eller `.ifczip`-fil som lastes opp som dokumentversjon, kontrolleres
også mot IFC-skjemaet, med validatoren som kontrollerer en skrevet fil
([Skrive en modell tilbake](#skrive-en-modell-tilbake)): attributtenes type og
antall, enumerasjoner, inverse attributter, GlobalId og reglene i
EXPRESS-skjemaet. Kontrollen kjører i bakgrunnen før konverteringen, i en
arbeidsprosess med de samme grensene. Den stopper aldri en opplasting: filen
lagres slik den kom, uansett hva kontrollen finner. Et BCF-prosjektdokument
kontrolleres ikke, siden det ikke har metadata.
`OPENCDE_IFCGRAPH_VALIDATE_UPLOADS=false` slår kontrollen av.

Resultatet står i versjonens metadata, som enhver klient for Documents API kan lese:

| Post | Type | Verdi |
|---|---|---|
| `ifc_validation_status` | `string` | `pending` til filen er kontrollert, deretter `passed`, `warnings` når hver anmerkning er en advarsel, `issues` når minst én er en feil, eller `unknown` når den ikke kunne kontrolleres |
| `ifc_validation_issues` | `integer32` | Hvor mange anmerkninger filen har |
| `ifc_validation_checked_at` | `date-time` | Når den ble kontrollert |
| `ifc_validation_ruleset` | `string` | Hva den ble kontrollert med, én verdi per kontroll |
| `ifc_validation_report` | `url` | Hvor rapporten er |

Rapporten er en utvidelse av Documents API. Hvert medlem av prosjektet får den med
samme Bearer-token:

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
    {"name": "schema", "state": "done", "ruleset": "IfcOpenShell 0.9.0.post1: schema and EXPRESS rules", "issue_count": 1, "rules_not_run": []},
    {"name": "gherkin", "state": "done", "ruleset": "ifc-gherkin-rules 893f827 with IfcOpenShell 0.8.6", "issue_count": 1, "rules_not_run": [{"rule": "GEM004", "error": "FileNotFoundError"}]}
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

Den viser opptil 10 000 anmerkninger, hver med sin instans og, for en rotfestet
entitet, dens GlobalId, slik at en modellvisning kan finne elementet. `kind` sier
hva som fant anmerkningen: `schema`, `entity_rule`, `simpletype_rule` eller
`global_rule` i IFC-skjemaet, eller `gherkin` for en av buildingSMARTs regler,
der koden står i `rule`. `checks` holder kontrollene fra hverandre. En melding
kan sitere en linje fra filen og kortes av ved 1 000 tegn. Versjonens side i nettleseren viser de første 100 anmerkningene og tilbyr
hele rapporten som fil.

Mange filer bryter allerede en regel når de kommer fra programmet sitt: 12 av 26
eksempelfiler gjør det, én fra Tekla med 5 711 anmerkninger. Å kontrollere en
eksempelfil og den skrevne kopien tok 3 til 66 sekunder til sammen.

### buildingSMARTs ifc-gherkin-rules

Når `OPENCDE_IFCGRAPH_GHERKIN_ENV` peker på et miljø for dem, kontrolleres
opplastinger også mot buildingSMARTs `ifc-gherkin-rules`: de normative reglene
og den bransjepraksisen som buildingSMARTs valideringstjeneste kontrollerer
utover skjemaet ([ADR 0012](../adr/0012-buildingsmarts-rules-run-in-an-environment-of-their-own.md)).
De kjører etter skjemakontrollen, i samme slags arbeidsprosess med de samme
grensene, og slik regelsettets egne tester kjører dem: med behave og
IfcOpenShell 0.8.6, som regelsettets CI bruker. På regelsettets 722 testfiler
gir det utfallet testene venter for hver eneste en.

Reglene får et eget miljø, fordi en av hjelpefunksjonene deres ikke virker med
IfcOpenShell 0.9, som Kontroll bruker.
`python -m opencde.ifcgraph.gherkin_install <mappe>` lager det av fastlåste
nedlastinger, hver kontrollert mot sin SHA-256: regelsettet ved en bestemt
commit, IfcOpenShells bygg av 0.8.6 for plattformen og Python-pakkene med
hashene sine. To små filer fra Kontroll erstatter regelsettets Django-deler, som
bare skriver resultater til valideringstjenestens database.
Det publiserte imaget utelater dem, siden de legger til omkring 425 MB. Imaget
med taggen `-gherkin`, som `latest-gherkin` eller `3.0.0-gherkin`, har miljøet i
`/opt/gherkin` og lar `OPENCDE_IFCGRAPH_GHERKIN_ENV` peke på det, slik et image
bygget med `--build-arg OPENCDE_GHERKIN=1` også gjør. Med docker compose velger
`OPENCDE_IMAGE_TAG` eller `OPENCDE_GHERKIN=1` i `.env`.

Et funn fra en regel er en anmerkning av typen `gherkin`, med regelens kode, som
`IFC106`, og alvorlighetsgraden `error` eller `warning`. Regler for
bransjepraksis advarer bare, og en fil der alle anmerkningene er advarsler, får
statusen `warnings`, siden buildingSMARTs valideringstjeneste regner en slik fil
som gyldig. En regel som kastet et unntak i stedet for å finne noe, har ikke noe
utfall og står under `rules_not_run` i kontrollen sin. Kan reglene ikke kjøre i
det hele tatt, blir kontrollen deres `failed`, og skjemaets kontroll står alene.

Reglene tar lengre tid enn skjemakontrollen: på åtte eksempelmodeller fra 5
sekunder for den minste til omkring 5 minutter for den største, og mellom et
halvt og to minutter for de fleste.

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

Ingen noder som standard (`OPENCDE_IFCGRAPH_INCLUDE_GEOMETRY=false`):
representasjonselementer, representasjoner, profiler, plasseringer og stiler;
de utgjør det meste av en modell og er sjelden det en CDE-spørring trenger, og de
beholdes som tekst i grafen, jf. Skrive en modell tilbake. `IfcOwnerHistory` er en
node bare for `IfcProject`.

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

- Geometri blir ikke noder med mindre det etterspørres. Artikkelen konverterer alt og
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

Artikkelen påpeker at grafen dens mister rekkefølgen i lister, siden en relasjon
ikke sier hvor i en liste målet sto. Her sier `position` det.

## Skrive en modell tilbake

Grafen rommer hele modellen, og filen kan skrives tilbake fra den: de samme instansene
med de samme id-ene og de samme verdiene i samme rekkefølge, og dermed også den samme
geografiske informasjonen.

```sh
uv run opencde ifcgraph export <modell-id> model.ifc            # skriv filen og valider den
uv run opencde ifcgraph export <modell-id> model.ifc --verify   # og sammenlign den med den opplastede
```

Nodene er de spørringer trenger. Det de utelater, skrives ut som STEP og komprimeres
til tekst på `StepBlock`-noder som henger på `IfcModel`: det er i grafen, men utenfor
rekkevidden til Cypher, og det kan ikke endres der. Det kan ikke være egenskaper på
produktene, siden mye av det deles mellom dem. Med
`OPENCDE_IFCGRAPH_INCLUDE_GEOMETRY=true` blir hver instans en node i stedet, til flere
ganger størrelsen og importtiden; spørringer tok omtrent like lang tid i
[målingene](../adr/0010-a-lossless-graph-reads-and-writes-step-itself.md).

| I filen | I grafen |
|---|---|
| En referanse | En relasjon med `position`, `[rad, kolonne]` i en liste av lister; inverse relasjoner har ingen |
| En referanse til en instans i en blokk | Id-en dens, som i `Representation__step: 1234` |
| En typet verdi, `IFCLABEL('3')` | `NominalValue: "3"`, og `NominalValue__type: "IFCLABEL"` ved siden av |
| En liste av lister av tall | JSON-tekst |
| Det som mangler enkel form, som en liste av typede verdier | Merket JSON, med `$json` som type |
| Headeren | `ifc_header` på `IfcModel` |
| En instans i en blokk | Tekst i en `StepBlock` |

Filen skrives fra det grafen rommer og kopieres ikke, så en egenskap eller en relasjon
som endres i grafen, vises i den. En grafdatabase har ikke noe skjema å holde en endring
opp mot, så filen valideres mot IFC-standarden med validatoren til IfcOpenShell:
attributtenes type og antall, enumerasjoner, inverse attributter, GlobalId og reglene i
EXPRESS-skjemaet. Filer i bruk bryter ofte allerede en regel, så det som teller, er en
anmerkning den opplastede filen ikke har. Kommandoen viser den da og avslutter med en
feil. `--no-validate` hopper over dette. En eksport stopper også hvis en blokk mangler.

Prosjektmedlemmer får filer gjennom Documents API, og det finnes ingen annen vei ut av
serveren. En skrevet fil som skal erstatte en modell, lastes opp som en ny versjon av
dokumentet sitt, noe som også konverterer den.

Denne formen leses ikke med IfcOpenShell, som her bare står for skjemaet. IfcOpenShell
endrer noen verdier ved lesing (`.NULLENUM.` blir `$`, og `($,$)` blir `()`), og filer
fra Tekla og Archicad har slike. Derfor leser arbeidsprosessen filen selv og avviser det
den ikke kan lese. [ADR 0010](../adr/0010-a-lossless-graph-reads-and-writes-step-itself.md) sier hvorfor, og [ADR 0011](../adr/0011-a-file-written-from-the-graph-is-validated.md) hvordan en
fil valideres.

`--verify` spør om de to filene rommer den samme modellen, etter definisjonen i
[ADR 0009](../adr/0009-what-makes-two-ifc-files-the-same-model.md): en til en, verdi for verdi og uten toleranse, med georeferansen
navngitt i rapporten. Med `--geometry` bygges også hvert produkts mesh, og de
sammenlignes bit for bit. To vilkårlige filer kan sammenlignes med
`python -m opencde.ifcgraph.equivalence first.ifc second.ifc`.

Med `OPENCDE_IFCGRAPH_LOSSLESS=false` konverteres en modell som før 3.0.0: den leses med
IfcOpenShell, og det som ikke er noder, utelates helt. En slik modell, i likhet med en
som er konvertert av en tidligere versjon, kan ikke skrives tilbake.

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
spørringene ligger i Dataspatiums dokumentasjon (`docs/grafer.md`), og
live-kjøringene er listet i [acceptance.md](../acceptance.md). En
produksjonsserver publiserer ikke Bolt; administrasjons-API-ets grafspørring
(`OPENCDE_GRAPH_QUERY_ENABLED`, [client-guide.md §7](client-guide.md)) gir
administratorer lesende Cypher uten porten. Appen tegner også
grafen, i kortet IFC-graf, gjennom den spørringen eller over Bolt.

## Grenser og status

- Én konvertering om gangen; store modeller står i kø. Eksempelmodellen (248
  entiteter) importeres på omkring ett sekund; en arkitektmodell på 200 MB tar
  minutter.
- `IfcModel`-noden bærer `state`, `entities`, `relationships`, `skipped`,
  `lossless`, `schema`, `ifc_project_guid`, tidsstempler og `error`. Administratorer kan
  inspisere den i Neo4j Browser eller Memgraph Lab:
  `MATCH (m:IfcModel) RETURN m.file_name, m.state, m.entities, m.error`.
- Sletting av et prosjekt sletter entitetene til modellene dets med det.
- En modell kommer identisk tilbake fra begge databasene opp til 224 496 instanser og 19 MB,
  i hver form som er målt. Ingenting større er prøvd.
