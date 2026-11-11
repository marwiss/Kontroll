# IFC-LPG

Den valgfrie IFC-LPG-modulen gjør en opplastet IFC-modell til grafdata, slik
at komponentene i et BCF-viewpoint kan knyttes til bygningsdelene de peker
på, og slik at spørsmål om modellen kan stilles i Cypher ved siden av sakene
og dokumentene.

Slå den på med `OPENCDE_IFC_LPG_ENABLED=true` og installer ekstrapakken
`ifc-lpg` (`uv sync --extra ifc-lpg`). Docker-imaget inneholder ekstrapakken
som standard (`ARG OPENCDE_EXTRAS` i Dockerfile), noe som mer enn dobler
størrelsen (omkring 680 MB, eller 1,1 GB med buildingSMARTs regler, mot 300 MB); bygg med
`--build-arg OPENCDE_EXTRAS=` for et slankere image uten IfcOpenShell når
modulen forblir av.

Fram til november 2026 het modulen IFC-graph. Innstillingene het `OPENCDE_IFCGRAPH_*` og
kommandoen `opencde ifcgraph`, og begge virker fortsatt; serverens logg og
`opencde doctor` nevner de gamle innstillingene den får.

Konverteringen, skrivingen av en fil og kontrollene kommer fra biblioteket
[IFC-LPG](https://github.com/marwiss/IFC-LPG), som Dataregium installerer fra
repoet ved en fast commit, og som har en README som beskriver hvordan en modell
lagres i grafen. Serverens egen prosess bruker den delen som ikke trenger
IfcOpenShell; ekstrapakken `ifc-lpg` legger til arbeidsprosessene som gjør det.

## Hva som skjer ved opplasting

1. En Documents API-opplasting fullføres (eller en fil lastes opp fra
   utvalgssiden, eller et BCF-prosjektdokument postes) med et `.ifc`- eller
   `.ifczip`-navn.
2. Serveren oppretter en `Conversion`-post (tilstand `queued`) knyttet til
   prosjektet og starter en konvertering i bakgrunnen, én om gangen.
3. En separat arbeidsprosess (`python -m ifc_lpg.worker`) leser
   filen. Den kjører med en tidsgrense
   (`OPENCDE_IFC_LPG_TIMEOUT_SECONDS`, 15 minutter), en adresseromsgrense på
   POSIX (`OPENCDE_IFC_LPG_MEMORY_MB`, 4 GiB) og et tak for antall entiteter
   (`OPENCDE_IFC_LPG_MAX_ENTITIES`). Et krasj eller en henging dreper
   arbeidsprosessen, ikke serveren. `.ifczip` pakkes ut med opplastingens
   størrelsesgrense.
4. Postene importeres i batcher av `UNWIND … CREATE` (portabel Cypher, ingen
   APOC). `Conversion` ender i tilstanden `done` med tall og `IfcProject`-guid,
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
arbeidsprosess med de samme grensene. Som standard stopper den aldri en opplasting:
filen lagres slik den kom, uansett hva kontrollen finner; et prosjekt kan
velge annerledes ([nedenfor](#avvise-filer-med-feil-og-kontrollere-en-fil-på-forhånd)). Et BCF-prosjektdokument
kontrolleres ikke, siden det ikke har metadata.
`OPENCDE_IFC_LPG_VALIDATE_UPLOADS=false` slår kontrollen av.

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

Når `OPENCDE_IFC_LPG_GHERKIN_ENV` peker på et miljø for dem, kontrolleres
opplastinger også mot buildingSMARTs `ifc-gherkin-rules`: de normative reglene
og den bransjepraksisen som buildingSMARTs valideringstjeneste kontrollerer
utover skjemaet (ADR 0012).
De kjører etter skjemakontrollen, i samme slags arbeidsprosess med de samme
grensene, og slik regelsettets egne tester kjører dem: med behave og
IfcOpenShell 0.8.6, som regelsettets CI bruker. På regelsettets 722 testfiler
gir det utfallet testene venter for hver eneste en.

Reglene får et eget miljø, fordi en av hjelpefunksjonene deres ikke virker med
IfcOpenShell 0.9, som Dataregium bruker.
`python -m ifc_lpg.gherkin_install <mappe>` lager det av fastlåste
nedlastinger, hver kontrollert mot sin SHA-256: regelsettet ved en bestemt
commit, IfcOpenShells bygg av 0.8.6 for plattformen og Python-pakkene med
hashene sine. To små filer fra IFC-LPG erstatter regelsettets Django-deler, som
bare skriver resultater til valideringstjenestens database.
Det publiserte imaget utelater dem, siden de legger til omkring 425 MB. Imaget
med taggen `-gherkin`, som `latest-gherkin` eller `3.0.0-gherkin`, har miljøet i
`/opt/gherkin` og lar `OPENCDE_IFC_LPG_GHERKIN_ENV` peke på det, slik et image
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

### Information Delivery Specifications (IDS)

En opplasting kontrolleres også mot hvert IDS-dokument i prosjektet sitt: et
dokument der den nyeste versjonen har et navn som slutter på `.ids`, høyst 50
(ADR 0015).
IFC-LPGs kontroll leser hver IDS trygt og gir den til IfcOpenShells IfcTester,
den samme kontrollen som Dataspatium kjører i nettleseren, så de to gir samme
utfall. Den kjøres etter de andre kontrollene, i samme slags arbeidsprosess med
de samme grensene. En ny versjon av et IDS-dokument gjør at den siste versjonen av hvert IFC-dokument i prosjektet kontrolleres
på nytt, høyst 500, så rapporten følger kravene slik de er nå; eldre versjoner beholder rapporten de hadde.

Hvert krav et element ikke oppfyller, blir en anmerkning av typen `ids`, med
alvorligheten `error`, spesifikasjonens identifikator eller navn i `rule` og
IDS-dokumentet i `document_id`. Det samme gjør en påkrevd spesifikasjon som ikke
gjelder noe i filen, og et element som en forbudt spesifikasjon gjelder.
Rapportens kontroll `ids` viser dokumentene den brukte, med versjon, og hver
spesifikasjon med bruken, utfallet (`passed`, `failed` eller `not applicable`),
hvor mange elementer den gjelder, og hvor mange anmerkninger den ga. Et
IDS-dokument som ikke kan leses, for eksempel ett med en DTD, står under
`rules_not_run` med grunnen, og de andre kontrolleres likevel. Versjonens side
viser spesifikasjonene i en egen tabell.

### Det den konverterte modellen viser

Når modellen er konvertert, får rapporten en egen kontroll, `graph`, med to slags merknader. En instans som ingenting
med en GlobalId når, framover eller bakover, er en advarsel av typen `reachability`, med STEP-id-en i `step_id` og
klassen i meldingen: bare det nummeret navngir den, som en plassering ingenting bruker, så et endringssett kan peke
den ut bare med STEP-id-en. Et produkt som geometripasset ikke kunne bygge formen til, er en merknad av typen
`geometry`, med GlobalId-en. Ingen av dem avviser filen: de kommer etter opplastingen, og en advarsel gir status
`warnings`. Før modellen er konvertert, har rapporten ingen kontroll `graph`.
En instans som holdes sammen med geometrien i en STEP-blokk, som et løst punkt,
listes ikke: kontrollen ser bare nodene.

### Avvise filer med feil, og kontrollere en fil på forhånd

En administrator kan krysse av *Avvis opplastinger med valideringsfeil* på
prosjektets side (`block_on_validation_errors` i administrasjons-API-et).
Kontrollene kjører da før filen blir en versjon, i opplastingens fullføring og
på opplastingssiden, og en fil med én eller flere feil avvises med
`422 ifc_validation_failed`; advarsler slipper gjennom. Den avviste filen blir
et døgn som forhåndskontroll, og `report` i feilen sier hvor rapporten er. En
fil som ikke kunne kontrolleres i det hele tatt, slipper gjennom som
`unknown`, slik at en ødelagt validator aldri stopper arbeidet. En fil som
godkjennes, kontrolleres én gang: resultatet blir versjonens, som om kontrollen
hadde kjørt etterpå.

Enhver redaktør eller forvalter kan også kontrollere en fil uten å gjøre den
til en versjon, med samme bearer-token og uansett prosjektets innstilling:

```http
POST /documents/1.0/projects/{project_id}/ifc-precheck
Content-Disposition: attachment; filename="model.ifc"
```

Kroppen er filen. Svaret er `202` med rapportens `url`, `pending` til
kontrollene er ferdige; deretter har den samme form som en versjons rapport,
med filens navn og når forhåndskontrollen utløper. Hvert medlem leser den, i et
døgn. Kapabilitetsdokumentet annonserer forhåndskontrollen som `ifc_precheck`.

## Grafen

Hver entitet blir en `Entity`-node som bærer klassen sin og alle
supertypene sine som etiketter, for eksempel `Entity:IfcWallStandardCase:IfcWall:
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

Ingen noder som standard (`OPENCDE_IFC_LPG_INCLUDE_GEOMETRY=false`):
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
- Relasjonstypene skrives med store bokstaver, og kopien av GTIN til
  BCF-komponentene er et tillegg her.

Artikkelen påpeker at grafen dens mister rekkefølgen i lister, siden en relasjon
ikke sier hvor i en liste målet sto. Her sier `position` det.

## Skrive en modell tilbake

Grafen rommer hele modellen, og filen kan skrives tilbake fra den: de samme instansene
med de samme id-ene og de samme verdiene i samme rekkefølge, og dermed også den samme
geografiske informasjonen.

```sh
uv run opencde ifc-lpg export <modell-id> model.ifc            # skriv filen og valider den
uv run opencde ifc-lpg export <modell-id> model.ifc --verify   # og sammenlign den med den opplastede
```

Nodene er de spørringer trenger. Det de utelater, skrives ut som STEP og komprimeres
til tekst på `StepBlock`-noder som henger på `Model`: det er i grafen, men utenfor
rekkevidden til Cypher, og det kan ikke endres der. Det kan ikke være egenskaper på
produktene, siden mye av det deles mellom dem. Med
`OPENCDE_IFC_LPG_INCLUDE_GEOMETRY=true` blir hver instans en node i stedet, til flere
ganger størrelsen og importtiden; spørringer tok omtrent like lang tid i
målingene.
Et stilsatt element (`IfcStyledItem`) er alltid en node, slik at hver stil kan endres, og `form_version` på `Model` sier hvilken form grafen har (2 siden IFC-LPGs utgivelse 2026-11-10).

| I filen | I grafen |
|---|---|
| En referanse | En relasjon med `position`, `[rad, kolonne]` i en liste av lister; inverse relasjoner har ingen |
| En referanse til en instans i en blokk | Id-en dens, som i `Representation__step: 1234` |
| En typet verdi, `IFCLABEL('3')` | `NominalValue: "3"`, og `NominalValue__type: "IFCLABEL"` ved siden av |
| En liste av lister av tall | JSON-tekst |
| Det som mangler enkel form, som en liste av typede verdier | Merket JSON, med `$json` som type |
| Headeren | `ifc_header` på `Model` |
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
den ikke kan lese. ADR 0010 sier hvorfor, og ADR 0011 hvordan en
fil valideres.

`--verify` spør om de to filene rommer den samme modellen, etter definisjonen i
ADR 0009: en til en, verdi for verdi og uten toleranse, med georeferansen
navngitt i rapporten. Med `--geometry` bygges også hvert produkts mesh, og de
sammenlignes bit for bit. To vilkårlige filer kan sammenlignes med
`python -m ifc_lpg.equivalence first.ifc second.ifc`.

Med `OPENCDE_IFC_LPG_LOSSLESS=false` konverteres en modell som før 3.0.0: den leses med
IfcOpenShell, og det som ikke er noder, utelates helt. En slik modell, i likhet med en
som er konvertert av en tidligere versjon, kan ikke skrives tilbake.

## Opprydding

Hver opplasting av en IFC-fil legger til en `Conversion` og en modell med entitetene sine, så
et prosjekt som mottar nye versjoner, samler grafer ingen spør mot.
Kommandolinjen lister og fjerner dem; dokumentene og filene deres blir alltid
igjen:

```sh
uv run opencde ifc-lpg list --project <prosjekt-id>
uv run opencde ifc-lpg prune                   # feilede modeller, og ferdige modeller erstattet av en nyere
                                                # ferdig versjon av samme dokument
uv run opencde ifc-lpg prune --project <id> --all   # hver modell i ett prosjekt (en teststakk, for eksempel)
```

Modeller i kø og under kjøring fjernes aldri. Spørringer som vil ha én graf
per dokument, bør selv velge den siste ferdige modellen, siden eldre
versjoner blir igjen til de fjernes:

```cypher
MATCH (:Project {project_id: $project})-[:HAS_CONVERSION]->(m:Conversion {state: 'done'})
WITH coalesce(m.document_id, m.bcf_document_guid) AS doc, m
ORDER BY m.version_index DESC, m.done_at DESC
WITH doc, collect(m)[0] AS latest
MATCH (e:IfcProduct {model_id: latest.id})
RETURN latest.file_name AS model, count(e) AS products
```

## Kobling av BCF-komponenter

Når et viewpoint opprettes med komponenter, får hver komponent hvis
`ifc_guid` matcher `GlobalId` til en bygningsdel i en av prosjektets
importerte modeller, verdien av den konfigurerte egenskapen
(`OPENCDE_IFC_LPG_GTIN_PROPERTY_SET=Reuse`, `OPENCDE_IFC_LPG_GTIN_PROPERTY=GTIN`)
som `gtin`, når bygningsdelen har en: serveren slår opp GlobalId-ene i modellen
gjennom IFC-LPGs `property_values` og lagrer verdien på komponenten, og lager
ingen relasjon inn i modellen; bygningsdelen finnes gjennom sin `GlobalId`. Det
samme oppslaget kjører for hver eksisterende komponent i prosjektet når en
modell er ferdig importert, så viewpoints opprettet før modellen ble lastet opp,
eller mens den fortsatt ble konvertert, får også sine GTIN. Det er
brukstilfellet i forskningsrapporten fra 2023: en befaring (BCF-sak) som peker
på byggevarer identifisert med GTIN.

```cypher
// Hvilke produkter peker dette viewpointet på, og hva er GTIN-ene deres?
MATCH (:Viewpoint {guid: $viewpoint})-[:HAS_COMPONENT]->(c:Component)
MATCH (e:IfcProduct {GlobalId: c.ifc_guid})
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
MATCH (:Component {ifc_guid: $guid})<-[:HAS_COMPONENT]-(v:Viewpoint)<-[:HAS_VIEWPOINT]-(t:Topic)
RETURN DISTINCT t.server_assigned_id, t.title, t.topic_status
```

BCF-tjenesten `files_information` viser importerte modellers
`IfcProject`-guid som `ifc_project`, som lar klienter fylle inn filene i
sakens hode.

## Navngitte spørringer

Et medlem av et prosjekt stiller spørsmål til en versjons modell ved navn, med
det samme bearer-tokenet som for Documents API; fri Cypher forblir
administratorenes (ADR 0016).
Spørringene er IFC-LPGs katalog (`ifc_lpg.queries`), så en som legges til i
biblioteket, dukker opp her.
`GET /documents/1.0/documents/{id}/versions/{index}/ifc-queries` viser
spørringene med parametere og kolonner og sier i `model_state` hvor langt
konverteringen av modellen har kommet. `GET …/ifc-queries/{name}` stiller én,
med parameterne i spørrestrengen, og svarer med kolonnene og radene, hver rad
en liste i kolonnenes rekkefølge:

```http
GET /documents/1.0/documents/{id}/versions/1/ifc-queries/property?pset=Reuse&property=GTIN
```

```json
{"name": "property", "columns": ["global_id", "class", "name", "value", "type"],
 "rows": [["1Xezbq735AdBO_4DerG66G", "IfcWallStandardCase", "YVT-A", "3", "IFCLABEL"]],
 "truncated": false}
```

| Spørring | Parametere | Hva den svarer på |
|---|---|---|
| `element-classes` | | Hvor mange elementer modellen har av hver klasse |
| `elements` | `class` | Elementene av en klasse, med den romlige strukturen som inneholder hvert |
| `storeys` | | Etasjene, nivået deres og hvor mange elementer og rom hver rommer |
| `spaces` | | Rommene, etasjen deres og netto- og bruttogulvarealet deres |
| `areas` | | Nettogulvarealet til hver etasjes rom, lagt sammen |
| `materials` | `class` | Materialene til hvert element: et eget, eller lagenes, listens eller bestanddelenes |
| `property` | `pset`, `property`, `class` | Verdien av én egenskap på hvert objekt som har den, med IFC-typen |
| `entity` | `global_id` | Én rotfestet entitet: klassen, hvert literalt attributt, og hva den refererer til og refereres av, hver med IFC-attributt, STEP-id og klasse |
| `changed-since` | `since` | Hva som er endret i dokumentet siden en versjon: én rad per endring i hver versjons endringssett fram til denne, eller én rad med `whole_file` for en versjon lastet opp som hel fil; besvares fra versjonene, så den trenger ingen graf |

`class` navngir en IFC-klasse, for eksempel `IfcWall`, og tar med seg
underklassene: påkrevd for `elements`, valgfri for de andre. Et svar rommer
høyst 10 000 rader, og `truncated` sier når det var flere; en spørring stoppes
etter 10 sekunder. Hver spørring begynner ved medlemmet og når modellen gjennom
prosjektet, leser bare og tar verdiene sine som parametere. En versjon uten
modell, eller en som brukeren ikke får se, svarer 404, og en der modellen
fortsatt konverteres, svarer 409. Kapabilitetsdokumentet kunngjør spørringene
i `ifc_queries`.

## Endringssett

En foreslått endring av en modell reiser som `bim_snippet` i en BCF 3.0-sak
(ADR 0021): `snippet_type` er `DataregiumIfcChangeSet`, `reference_schema` er
`GET /documents/1.0/ifc-changes/schema`, som hvem som helst kan lese, og selve
snippeten lastes opp med `PUT …/topics/{guid}/snippet`, der serveren holder den
til skjemaet og svarer `400` med hva som er galt. Et nytt prosjekt tillater
snippettypen; en administrator legger den til blant verdiene i et eldre
prosjekt. Et endringssett oppgir basisversjonen sin, hvem som foreslo det, med
AI-modellen og verktøykallet der en AI gjorde det, og endringene sine, hver på
ett attributt hos én instans. Instansen oppgis med en GlobalId og en sti fra den
rotfestede entiteten i IFCs attributtnavn med indekser, og med STEP-id-en sin
bare der ingen GlobalId når den. `set` gir attributtet en verdi, `add` og `remove` endrer ett medlem
av et aggregat, og `copy` ber om en kopi av en instans som flere deler, og som
ellers endres for alle. En verdi er en skalar, en instans (`{"step_id": 120}`,
eller en GlobalId med sti), en typet verdi
(`{"type": "IfcLengthMeasure", "value": 3.2}`), en enumerasjon
(`{"enum": "NOTDEFINED"}`) eller en liste av dem. Kapabilitetsdokumentet
annonserer formen som `ifc_changes`. Hva endringene gjør med modellen, prøves
når forslaget prøves, det neste steget; i dag holder serveren formen.

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

`delete` fjerner en instans som pekes ut med STEP-id-en sin, og som ingenting refererer til, som en som ingen GlobalId
når; en instans som noe fortsatt refererer til, hoppes over og nevnes i prøvingen. Serveren foreslår selv et slikt
endringssett med `POST /documents/1.0/projects/{id}/ifc-unreachable` og versjonen som `document_id` og
`version_index`: den lager en sak der snippeten fjerner hver instans som versjonens kontroll `graph` finner utenfor
rekkevidde, og endringssettet prøves og godkjennes som alle andre, slik at versjonen det kom fra, beholder
instansene. Svaret navngir saken, hvor mange instanser det fjerner, og hvor prøvingen finnes; `404` når versjonen ikke
har noen konvertert modell, og `409` når ingenting i den er utenfor rekkevidde. Kapabilitetsdokumentet
viser operasjonene i `ifc_changes.ops` og adressen som `ifc_changes.unreachable_url`.

Når IFC-LPG-modulen er på, prøver serveren hvert endringssett når det lastes
opp: en arbeider bruker endringene på basisversjonens fil, resultatet går
gjennom kontrollene en opplasting får (IFC-skjemaet, buildingSMARTs regler og
prosjektets IDS-dokumenter), og prøven er `clean` når hver endring kunne
brukes og ingen anmerkning er ny sammenlignet med basisversjonens rapport,
ellers `issues`. `GET /bcf/3.0/projects/{id}/topics/{guid}/ifc-proposal` gir
tilstanden, hvor mange endringer som ble brukt, og de nye anmerkningene, hver
som i en versjons rapport; en endring som ikke kunne brukes, er en anmerkning
av slaget `proposal` som sier hvorfor, uten å sitere filen. En ny snippet
erstatter prøven, og prøven følger med saken når den slettes. `ifc_changes` i
kapabilitetsdokumentet sier om endringssett prøves (`tried`) og hvor prøven er
(`proposal_url`).

`GET /documents/1.0/documents/{id}/ifc-proposals` lister endringssettene som
er prøvd mot et dokument, for et medlem av prosjektet dets, nyeste først: per
rad sakens guid, tittel og de første 200 tegnene av beskrivelsen, prøvens
tilstand, basisversjonen, hvor mange endringer settet holder, hvem som
foreslo det, når prøven sluttet, versjonen det ble der det ble godkjent, og
adressene til prøven (`proposal_url`) og godkjenningen av den
(`approve_url`). Et forslag navngir basisen sin fra det øyeblikket det
settes i kø, så listen holder det før prøven og når prøven mislyktes. `$top`
og `$skip` blar i listen som i BCF-listene; en liste serveren har kuttet,
bærer `X-Total-Count` og `Link: <…>; rel="next"`. `404` for et dokument
medlemmet ikke får se, og når IFC-LPG-modulen er av.
Kapabilitetsdokumentet gir adressen som `ifc_changes.ifc_proposals_url`.

En `manager` godkjenner en ren prøve med `POST …/ifc-proposal/approve`: den
brukte filen blir basisdokumentets neste versjon, med `base_version_index`,
`change_set_id` (sakens guid), `proposed_by` og `approved_by` i metadataene
sine, og AI-modellen og verktøykallet der en AI foreslo den; svaret er den nye
versjonen slik Documents API gir den, og den konverteres og kontrolleres som
en opplasting. Saken får en kommentar med versjonens adresse, et viewpoint som markerer de endrede elementene, og
statusen `Closed` der prosjektet har den verdien. `412 version_conflict` sier at
dokumentet har gått videre siden basen; `409` at prøven ikke er ren, eller
allerede er godkjent. En AI foreslår bare: godkjenningen er et menneskes.
Der prosjektet har team, lister prøven i `teams` de teamene hvis del av modellen
endringssettet rører: det spesifikasjonene i et teams IDS-dokument gjelder for, i
basens fil eller den endrede. Et endringssett som rører ett teams del, godkjennes av
teamets ansvarlige alene, ikke av en `manager`; et som rører flere teams deler, eller
ingens, av en `manager`, og likeså et der delene ikke kunne finnes (`teams_error`).

Når dokumentet har gått videre siden basen, slår serveren sammen: endringene i
versjonene imellom, hver godkjent fra et endringssett, sammenlignes attributt
for attributt med forslagets. Kolliderer ingen, prøves endringssettet på nytt
mot den nyeste versjonen, med en gang, og godkjennes mot den, slik at den nye
versjonens basis er den nyeste. Kolliderer noen, eller ble en versjon imellom
lastet opp som hel fil, er svaret `412 version_conflict` med de kolliderende
attributtene i `conflicts` (`#123.Name`, eller GlobalId, sti og attributt; `*`
for en hel fil), slik at klienten slår sammen treveis og sender igjen.

Instansene sammenlignes, ikke nøklene klientene skrev: hver endring løses i
versjonen den ble laget på og navngis med sin kanoniske sti (IFC-LPGs
`ifc_lpg.paths`), slik at to endringer som når en delt instans fra ulike
GlobalId likevel kolliderer, og `conflicts` navngir instansen med den stien.
Ved siden av gir `conflict_details` per kollisjon `key`, forslagets egne
`guid`, `path` eller `step_id`, `attribute` og `op`, hva basen holdt
(`base`), hva den siste versjonen holder (`theirs`), hva forslaget setter
(`ours`), alle i endringssettets verdiform, og den mellomliggende versjonen
som endret det (`version_index`); en verdi som ikke kunne leses, er `null`.
Klienten lar en person velge per kollisjon, sender en ny snippet på den siste
versjonen og godkjenner igjen.

En versjon bygget på en annen er en node med forelderen sin:
`parent_version_index` og en lenke til forelderversjonen, på en versjon
godkjent fra et endringssett og på en opplasting som oppga
`base_version_index`. En versjon godkjent fra et endringssett bærer også
`approved_by`, `change_set_id` (sakens guid) og selve endringene, som
`GET /documents/1.0/documents/{id}/versions/{index}/ifc-changes` gir i
skjemaets form, med basisen og hvem som foreslo og godkjente den; en versjon
lastet opp som hel fil svarer `404` der. Hver versjon er fortsatt en hel fil,
hentet som før; `opencde ifc-lpg prune` fjerner eldre versjoners grafer, siden
hovedversjonen og kjeden av endringssett sier hva som ble endret.

## Sammenligne to versjoner

Et medlem sammenligner to IFC-versjoner element for element, med samme
bearer-token som Documents API: en versjon med en annen av samme dokument,
eller med `?other_document_id=` en versjon av et annet dokument i prosjektet.
Arbeideren parer de rotfestede entitetene etter GlobalId og svarer med `added`
(bare den andre har dem), `removed` (bare denne har dem) og `changed` (i
begge, med attributter som skiller seg), hvert element oppgitt med GlobalId,
klasse, navn og etasje, og for et endret de stiene som skiller seg, med gammel
og ny verdi: et direkte attributt ved navnet sitt, en egenskap som
`Pset.Property`, `ObjectPlacement` (4×4-matrisen), `Representation` (et
fingeravtrykk av formen), `Container` (etasjen) og `Type`. Relasjoner og
egenskapssett foldes inn i elementene de hører til, og hver liste holder
høyst 10 000 elementer. Forskjellen regnes ut på forespørsel og lagres aldri;
en stor modell tar en stund. Versjonens side tilbyr den samme sammenligningen
som lister, og kapabilitetsdokumentet annonserer den som `ifc_diff`.

```http
GET /documents/1.0/documents/{document_id}/versions/{version_index}/ifc-diff/{other_index}
```

## Kollisjonskontroll

Et medlem sammenligner to IFC-dokumentversjoner i et prosjekt for kollisjoner,
med samme bearer-token som Documents API:
`POST /documents/1.0/projects/{project_id}/ifc-clash` med de to versjonene,
modusen (`intersection`: elementer som går inn i hverandre dypere enn
`tolerance`; `clearance`: elementer nærmere hverandre enn `clearance`, begge i
meter) og, om ønskelig, hver sides IFC-klasser. Kontrollen kjører i en
arbeidsprosess bak konverteringskøen; svarets `url` gir rapporten, `done` eller
`failed` etter en stund. Hver kollisjon navngir begge elementene (dokument,
versjon, STEP-id, GlobalId, klasse, navn, etasje), sitt slag, dybden eller
avstanden og punktet der den ble målt, i den formen Dataspatiums egen
kollisjonskjerne skriver, så appen viser serverens resultat som sitt eget.
`POST …/ifc-clash/{id}/topics` gjør valgte kollisjoner til BCF-saker med hvert
sitt viewpoint, bare på forespørsel. Kapabilitetsdokumentet annonserer kontrollen
som `ifc_clash` når operatøren har satt `OPENCDE_IFC_LPG_CLASH_ENABLED=true`; en
rapport beholder høyst `OPENCDE_IFC_LPG_CLASH_MAX_CLASHES` kollisjoner.

```http
POST /documents/1.0/projects/{project_id}/ifc-clash
{"a": {"document_id": "…", "version_index": 1, "types": ["IfcWall"]},
 "b": {"document_id": "…", "version_index": 2},
 "mode": "intersection", "tolerance": 0.001}
```

## En bygning inn i en annen modell

En bygning fra én modell kommer inn i et annet prosjekts modell som neste versjon av
dokumentet; de to modellene endres ikke. Modell A er en versjon i dette prosjektet,
modell B en versjon i et hvilket som helst prosjekt anroperen er medlem av, og begge
må være konvertert, med samme skjema og lengdeenhet.
`POST /documents/1.0/projects/{project_id}/ifc-merge/report` viser hvert medlem av
begge prosjektene hva som ville skje: hvor mange objekter og instanser som følger
med, objektene med en GlobalId som begge har (`collisions`, med `same` og det
`choice` som gjelder), relasjonene som utelates fordi de bare peker ut av bygningen,
og kontekstene og plasseringene til A som brukes. Der innholdet i et slikt objekt er
forskjellig, tas et valg for det: `a` beholder As, `b` setter Bs i stedet, og `new`
beholder begge, Bs med en ny GlobalId; `default` gir ett valg for alle.
En enhet av et slag som A ikke har, som en arealenhet, følger med inn i As enheter og
listes i `units_added`; en enhet av et slag som begge har, må være den samme.

En `manager` i prosjektet starter sammenslåingen med `POST …/ifc-merge` og samme
kropp. Den kjører som en jobb i konverteringskøen, og svarets `url` gir tilstanden:
`conflict` med objektene som fortsatt mangler et valg, `failed` med årsaken, eller
`done` med `version_index`, den nye versjonen av As dokument. Den sammenslåtte
modellen kontrolleres først mot A og B og kan ikke ha noen anmerkning som de ikke
har; deretter skrives den ut som neste versjon, med As versjon som forelder og
`merged_from_document`, `merged_from_version` og `merged_building` i metadataene, og
konverteres og kontrolleres som en opplasting. As versjon må være dokumentets siste
(ellers 412 `version_conflict`). Kapabilitetsdokumentet annonserer den som
`ifc_merge`.

Der Bs skjema eller lengdeenhet ikke er As, sier rapporten det (422), og en
`editor` eller `manager` forbereder først B med `POST …/ifc-merge/prepare` og `base`
og `other`: en jobb som lager en kopi av B migrert til As skjema og med lengdene i
As enhet. Når den er `done`, gjør dens `merge_id`, gitt som `other.prepared`, at
kopien står for B i rapporten og sammenslåingen til `expires_at`, et døgn senere;
deretter fjerner serveren den. En annen enhet som er forskjellig, konverteres ikke,
og jobben feiler med den.
Det As skjema ikke har noe motstykke til, som IFC2X3s IfcWindowStyle i IFC4X3
eller eierhistorikkene IFC2X3 krever, gir jobben tilstanden `conflict`:
`report.problems` lister hvert problem med sin `key`, hva det rører og sine
`options` (`type`, `proxy`, `leave_out`, `polyline`, `owner`, `virtual`, `dated`,
`assignment`, `context`), og en ny `POST …/ifc-merge/prepare` med `resolutions`, det valgte
alternativet per nøkkel, lager kopien. Kopien kontrolleres så mot B: en med en
anmerkning B ikke hadde, lages ikke, og jobben blir `failed` med dem i `report.new`.

```http
POST /documents/1.0/projects/{project_id}/ifc-merge
{"base": {"document_id": "…", "version_index": 3},
 "other": {"project_id": "…", "document_id": "…", "version_index": 1},
 "building": "3AMeTOOFsdVLZuNV0$27s5", "choices": {"1Xezbq735AdBO_4DerG66G": "b"}}
```

## Arbeidskopien

Ved siden av arkivet kan serveren holde en arbeidskopi: en andre graf,
Memgraph i minnet, der hovedversjonens modell for hvert dokument også
importeres (ADR 0024). Arkivet beholder hver versjon og forblir sannheten;
arbeidskopien holder én modell per dokument, den sist konverterte, og svarer på
de navngitte spørringene for den, slik at en stor modell leses fra minnet.
`OPENCDE_WORKCOPY_GRAPH_URI` angir den (`OPENCDE_WORKCOPY_GRAPH_DIALECT`,
`_USER`, `_PASSWORD` og `_DATABASE` ved siden av); overlegget
`docker/compose.workcopy.yaml` legger Memgraph til enhver stakk, upublisert. En
konvertering importerer de samme postene i begge grafene i IFC-LPGs
dialektnøytrale form, erstatter dokumentets tidligere modell i arbeidskopien og
feiler aldri på arbeidskopiens vegne: en kopi som ikke kunne lages, merkes
`failed` der, og arkivet røres ikke. En modell arkivet ikke lenger har, forlater
arbeidskopien ved neste oppryddingsrunde. `GET …/ifc-queries` sier i
`workcopy` om versjonens modell er der, `/readyz` rapporterer arbeidskopiens
tilstand uten å avhenge av den, og kapabilitetsdokumentet sier i
`ifcgraph.workcopy` om en er konfigurert.

```sh
# .env: COMPOSE_FILE=docker/compose.yaml:docker/compose.local.yaml:docker/compose.workcopy.yaml
docker compose up -d
```

## Hvor bygningsdelene er, og geometrien

Etter en konvertering kjører serveren IFC-LPGs geometriarbeider én gang over
filen (`python -m ifc_lpg.spatial`; `OPENCDE_IFC_LPG_SPATIAL`, på som standard
med ekstraet): IfcOpenShell bygger formen til hver bygningsdel, og arbeideren
skriver en boks per bygningsdel i prosjektkoordinater og meshene, hver delt
mesh én gang. Boksene går inn i grafen som punktene `bbox_min`, `bbox_max` og
`bbox_centre` på bygningsdelens `Entity`, med en punktindeks på `bbox_centre`
i arkivet og i arbeidskopien, slik at en spørring finner det som er nær et
punkt eller inne i et volum; `Model` bærer `spatial_at`, `spatial_products`
og `spatial_failed`. Postene lagres, og `GET …/ifc-geometry` bygger en binær
glTF av dem første gang den etterspørres: hver delt mesh én gang, en node per
bygningsdel som instansierer den med bygningsdelens matrise, navngitt med sin
GlobalId og med klasse, STEP-id og etasje i `extras`, under en node per
etasje, og en rot som dreier modellen fra IFCs Z opp til glTFs Y opp.
`lod=box` gir boksene i stedet, én kube som hver bygningsdel instansierer,
noen få byte hver; `classes` (IFC-klasser, kommaseparerte) og `storey` (en
GlobalId) velger bygningsdelene. Filen lagres og kommer med en `ETag` for
modellen og filtrene, slik at `If-None-Match` besvares med `304`.
Geometripasset feller aldri en konvertering: mislykkes det, noterer modellen
`spatial_error` og ruten svarer `404`; mens versjonen fortsatt konverteres,
`409`. Kapabilitetsdokumentet annonserer det som `ifc_geometry`.

```http
GET /documents/1.0/documents/{document_id}/versions/{version_index}/ifc-geometry?lod=full&classes=IfcWall,IfcSlab
```

```cypher
// Bygningsdelene innenfor to meter fra en vegg, i samme modell
MATCH (w:Entity:IfcWall {GlobalId: $guid})
MATCH (e:Entity {model_id: w.model_id}) WHERE e.bbox_centre IS NOT NULL AND e <> w
  AND point.distance(e.bbox_centre, w.bbox_centre) < 2.0
RETURN e.GlobalId, e.ifc_class, point.distance(e.bbox_centre, w.bbox_centre) AS distance ORDER BY distance
```

## Spørringer fra Dataspatium

[Dataspatium](https://github.com/marwiss/Dataspatium), nettleserklienten som
utvikles sammen med denne serveren, kjører Cypher mot denne grafen gjennom
Neo4j-kilden sin over Bolt (WebSocket på Bolt-porten) når operatøren
eksponerer databasen, slik utviklingsoverlegget gjør på `127.0.0.1:7697`.
Dataregium-arbeidsområdet dets bruker mønstrene ovenfor (modeller, klasser,
komponenter gjennom `GlobalId`, den siste ferdige modellen per dokument);
spørringene ligger i Dataspatiums dokumentasjon (`docs/grafer.md`). En
produksjonsserver publiserer ikke Bolt; administrasjons-API-ets grafspørring
(`OPENCDE_GRAPH_QUERY_ENABLED`, [client-guide.md §7](client-guide.md)) gir
administratorer lesende Cypher uten porten. Appen tegner også
grafen, i kortet IFC-LPG, gjennom den spørringen eller over Bolt.

## Grenser og status

- Én konvertering om gangen; store modeller står i kø. Eksempelmodellen (248
  entiteter) importeres på omkring ett sekund; en arkitektmodell på 200 MB tar
  minutter.
- `Conversion` bærer `state`, `entities`, `relationships`,
  `lossless`, `geometry`, `schema`, `ifc_project_guid`, tidsstempler og `error`. Administratorer kan
  inspisere den i Neo4j Browser eller Memgraph Lab:
  `MATCH (c:Conversion) RETURN c.file_name, c.state, c.entities, c.error`.
- Sletting av et prosjekt sletter entitetene til modellene dets med det.
- En modell kommer identisk tilbake fra begge databasene opp til 224 496 instanser og 19 MB,
  i hver form som er målt. Ingenting større er prøvd.
