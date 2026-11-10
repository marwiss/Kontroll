# IFC-LPG

Den valfrie IFC-LPG-modulen gjer ein opplasta IFC-modell til grafdata, slik
at komponentane i eit BCF-viewpoint kan knytast til bygningsdelane dei peikar
på, og slik at spørsmål om modellen kan stillast i Cypher ved sida av sakene
og dokumenta.

Slå han på med `OPENCDE_IFC_LPG_ENABLED=true` og installer ekstrapakken
`ifc-lpg` (`uv sync --extra ifc-lpg`). Docker-imaget inneheld ekstrapakken
som standard (`ARG OPENCDE_EXTRAS` i Dockerfile), noko som meir enn doblar
storleiken (omkring 680 MB, eller 1,1 GB med reglane frå buildingSMART, mot 300 MB); bygg med
`--build-arg OPENCDE_EXTRAS=` for eit slankare image utan IfcOpenShell når
modulen held fram med å vere av.

Fram til november 2026 heitte modulen IFC-graph. Innstillingane heitte `OPENCDE_IFCGRAPH_*`
og kommandoen `opencde ifcgraph`, og begge verkar framleis; loggen til tenaren
og `opencde doctor` nemner dei gamle innstillingane han får.

Konverteringa, skrivinga av ei fil og kontrollane kjem frå biblioteket
[IFC-LPG](https://github.com/marwiss/IFC-LPG), som Dataregium installerer frå
repoet ved ein fast commit, og som har ein README som skildrar korleis ein modell
blir lagra i grafen. Den eigne prosessen til tenaren bruker den delen som ikkje
treng IfcOpenShell; ekstrapakken `ifc-lpg` legg til arbeidsprosessane som gjer
det.

## Kva som skjer ved opplasting

1. Ei Documents API-opplasting blir fullført (eller ei fil blir lasta opp frå
   utvalssida, eller eit BCF-prosjektdokument blir posta) med eit `.ifc`-
   eller `.ifczip`-namn.
2. Serveren opprettar ein `IfcModel`-node (tilstand `queued`) knytt til
   prosjektet og startar ei konvertering i bakgrunnen, éi om gongen.
3. Ein separat arbeidsprosess (`python -m ifc_lpg.worker`) les
   fila. Han køyrer med ei tidsgrense
   (`OPENCDE_IFC_LPG_TIMEOUT_SECONDS`, 15 minutt), ei adresseromsgrense på
   POSIX (`OPENCDE_IFC_LPG_MEMORY_MB`, 4 GiB) og eit tak for talet på
   entitetar (`OPENCDE_IFC_LPG_MAX_ENTITIES`). Eit krasj eller ei henging
   drep arbeidsprosessen, ikkje serveren. `.ifczip` blir pakka ut med
   storleiksgrensa for opplastinga.
4. Postane blir importerte i batchar av `UNWIND … CREATE` (portabel Cypher,
   ingen APOC). `IfcModel` endar i tilstanden `done` med tal og
   `IfcProject`-guid, eller `failed` med ein feil.
5. Ei konvertering som ein stoppa server har late etter seg, byrjar på nytt: ei køa så snart serveren er tilbake,
   ei pågåande når dobbel tidsgrense er passert, fordi ho kan køyre i ein annan serverprosess.

`opencde seed` konverterer eksempelmodellen på same måte når modulen er på.

## Kontroll av opplastingar mot IFC-skjemaet

Kvar `.ifc`- eller `.ifczip`-fil som blir lasta opp som dokumentversjon, blir òg
kontrollert mot IFC-skjemaet, med validatoren som kontrollerer ei skriven fil
([Skrive ein modell tilbake](#skrive-ein-modell-tilbake)): typen og talet på
attributt, enumerasjonar, inverse attributt, GlobalId og reglane i
EXPRESS-skjemaet. Kontrollen køyrer i bakgrunnen før konverteringa, i ein
arbeidsprosess med dei same grensene. Som standard stoppar han aldri ei opplasting: fila
blir lagra slik ho kom, kva kontrollen enn finn; eit prosjekt kan velje
annleis ([nedanfor](#avvise-filer-med-feil-og-kontrollere-ei-fil-på-førehand)). Eit BCF-prosjektdokument blir ikkje
kontrollert, sidan det ikkje har metadata.
`OPENCDE_IFC_LPG_VALIDATE_UPLOADS=false` slår kontrollen av.

Resultatet står i metadataa til versjonen, som kvar klient for Documents API kan lese:

| Post | Type | Verdi |
|---|---|---|
| `ifc_validation_status` | `string` | `pending` til fila er kontrollert, deretter `passed`, `warnings` når kvar merknad er ei åtvaring, `issues` når minst éin er ein feil, eller `unknown` når ho ikkje kunne kontrollerast |
| `ifc_validation_issues` | `integer32` | Kor mange merknader fila har |
| `ifc_validation_checked_at` | `date-time` | Når ho vart kontrollert |
| `ifc_validation_ruleset` | `string` | Kva ho vart kontrollert med, éin verdi per kontroll |
| `ifc_validation_report` | `url` | Kvar rapporten er |

Rapporten er ei utviding av Documents API. Kvart medlem av prosjektet får han med
det same Bearer-tokenet:

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

Han viser opptil 10 000 merknader, kvar med instansen sin og, for ei rotfesta
entitet, GlobalId-en hennar, slik at ei modellvising kan finne elementet. `kind`
seier kva slags kontroll merknaden kjem frå: `schema`, `entity_rule`,
`simpletype_rule` eller `global_rule` i IFC-skjemaet, eller `gherkin` for ein av
reglane frå buildingSMART, der koden står i `rule`. `checks` held kontrollane
frå kvarandre. Ei melding kan sitere ei linje frå fila og blir korta av ved
1 000 teikn. Sida til versjonen i nettlesaren viser dei første
100 merknadene og tilbyr heile rapporten som fil.

Mange filer bryt alt ein regel når dei kjem frå programmet sitt: 12 av 26
eksempelfiler gjer det, éi frå Tekla med 5 711 merknader. Å kontrollere ei
eksempelfil og den skrivne kopien tok 3 til 66 sekund til saman.

### ifc-gherkin-rules frå buildingSMART

Når `OPENCDE_IFC_LPG_GHERKIN_ENV` peikar ut eit miljø for dei, blir
opplastingar òg kontrollerte mot `ifc-gherkin-rules` frå buildingSMART: dei
normative reglane og den bransjepraksisen som valideringstenesta til
buildingSMART kontrollerer ut over skjemaet (ADR 0012).
Dei køyrer etter skjemakontrollen, i same slags arbeidsprosess med dei same
grensene, og slik dei eigne testane til regelsettet køyrer dei: med behave og
IfcOpenShell 0.8.6, som CI-en til regelsettet bruker. På dei 722 testfilene til
regelsettet gir det utfallet testane ventar for kvar einaste ei.

Reglane får eit eige miljø, fordi ein av hjelpefunksjonane deira ikkje verkar
med IfcOpenShell 0.9, som Dataregium bruker.
`python -m ifc_lpg.gherkin_install <mappe>` lagar det av fastlåste
nedlastingar, kvar kontrollert mot SHA-256-en sin: regelsettet ved ein bestemd
commit, bygget av IfcOpenShell 0.8.6 for plattforma og Python-pakkane med
hashane sine. To små filer frå IFC-LPG erstattar Django-delane til regelsettet,
som berre skriv resultat til databasen til valideringstenesta.
Det publiserte imaget slepper dei, sidan dei legg til om lag 425 MB. Imaget med
taggen `-gherkin`, som `latest-gherkin` eller `3.0.0-gherkin`, har miljøet i
`/opt/gherkin` og lèt `OPENCDE_IFC_LPG_GHERKIN_ENV` peike på det, slik eit
image bygd med `--build-arg OPENCDE_GHERKIN=1` òg gjer. Med docker compose vel
`OPENCDE_IMAGE_TAG` eller `OPENCDE_GHERKIN=1` i `.env`.

Eit funn frå ein regel er ein merknad av typen `gherkin`, med koden til regelen,
som `IFC106`, og alvorsgraden `error` eller `warning`. Reglar for bransjepraksis
åtvarar berre, og ei fil der alle merknadene er åtvaringar, får statusen
`warnings`, sidan valideringstenesta til buildingSMART reknar ei slik fil som
gyldig. Ein regel som kasta eit unntak i staden for å finne noko, har ikkje noko
utfall og står under `rules_not_run` i kontrollen sin. Kan reglane ikkje køyre i
det heile, blir kontrollen deira `failed`, og kontrollen til skjemaet står
åleine.

Reglane tek lengre tid enn skjemakontrollen: på åtte eksempelmodellar frå 5
sekund for den minste til om lag 5 minutt for den største, og mellom eit halvt
og to minutt for dei fleste.

### Information Delivery Specifications (IDS)

Ei opplasting blir òg kontrollert mot kvart IDS-dokument i prosjektet sitt: eit
dokument der den nyaste versjonen har eit namn som sluttar på `.ids`, høgst 50
(ADR 0015).
Kontrollen i IFC-LPG les kvar IDS trygt og gir han til IfcTester frå
IfcOpenShell, den same kontrollen som Dataspatium køyrer i nettlesaren, så dei
to gir same utfall. Han køyrer etter dei andre kontrollane, i same slags
arbeidsprosess med dei same grensene. Ein IDS som blir lasta opp seinare, gjeld
IFC-versjonane som blir lasta opp etter han.

Kvart krav eit element ikkje oppfyller, blir ein merknad av typen `ids`, med
alvoret `error`, identifikatoren eller namnet til spesifikasjonen i `rule` og
IDS-dokumentet i `document_id`. Det same gjer ein påkravd spesifikasjon som ikkje
gjeld noko i fila, og eit element som ein forboden spesifikasjon gjeld.
Kontrollen `ids` i rapporten viser dokumenta han brukte, med versjon, og kvar
spesifikasjon med bruken, utfallet (`passed`, `failed` eller `not applicable`),
kor mange element han gjeld, og kor mange merknader han gav. Eit IDS-dokument
som ikkje kan lesast, til dømes eitt med ein DTD, står under `rules_not_run` med
grunnen, og dei andre blir kontrollerte likevel. Sida til versjonen viser
spesifikasjonane i ein eigen tabell.

### Avvise filer med feil, og kontrollere ei fil på førehand

Ein administrator kan krysse av *Avvis opplastingar med valideringsfeil* på
sida til prosjektet (`block_on_validation_errors` i administrasjons-API-et).
Kontrollane køyrer då før fila blir ein versjon, i fullføringa av opplastinga
og på opplastingssida, og ei fil med éin eller fleire feil blir avvist med
`422 ifc_validation_failed`; åtvaringar slepp gjennom. Den avviste fila blir
verande eit døgn som førehandskontroll, og `report` i feilen seier kvar
rapporten er. Ei fil som ikkje kunne kontrollerast i det heile, slepp gjennom
som `unknown`, slik at ein øydelagd validator aldri stoppar arbeidet. Ei fil
som blir godkjend, blir kontrollert éin gong: resultatet blir versjonen sitt,
som om kontrollen hadde køyrt etterpå.

Kvar redaktør eller forvaltar kan òg kontrollere ei fil utan å gjere henne til
ein versjon, med same bearer-token og uansett innstillinga til prosjektet:

```http
POST /documents/1.0/projects/{project_id}/ifc-precheck
Content-Disposition: attachment; filename="model.ifc"
```

Kroppen er fila. Svaret er `202` med `url` til rapporten, `pending` til
kontrollane er ferdige; deretter har han same form som rapporten til ein
versjon, med namnet på fila og når førehandskontrollen går ut. Kvar medlem les
han, i eit døgn. Kapabilitetsdokumentet annonserer førehandskontrollen som
`ifc_precheck`.

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

Ingen nodar som standard (`OPENCDE_IFC_LPG_INCLUDE_GEOMETRY=false`):
representasjonselement, representasjonar, profilar, plasseringar og stilar;
dei utgjer det meste av ein modell og er sjeldan det ei CDE-spørjing treng, og dei
blir haldne på som tekst i grafen, jf. Skrive ein modell tilbake. `IfcOwnerHistory`
er ein node berre for `IfcProject`.

## Kvar metoden kjem frå

Konverteringa følgjer IFC-Graph-metoden til Zhu, Wu og Lei: éin node per instans,
klassehierarkiet som etikettar, literale attributt som eigenskapar og attributt
som peikar på andre instansar, inverse attributt medrekna, som relasjonar
namngjevne etter attributtet. Prototypen frå 2023 brukte koden i artikkelen.
Konverteringa i denne serveren er skriven på nytt.

Junxiang Zhu, Peng Wu og Xiang Lei: "IFC-graph for facilitating building
information access and query". *Automation in Construction* 148 (2023), 104778.
[doi:10.1016/j.autcon.2023.104778](https://doi.org/10.1016/j.autcon.2023.104778),
fritt tilgjengeleg under CC BY 4.0.

Ho skil seg frå artikkelen på desse punkta:

- Geometri blir ikkje nodar dersom det ikkje blir etterspurt. Artikkelen konverterer
  alt og nemner storleiken på grafen som ei avgrensing.
- Postane blir skrivne i puljar med `CREATE` frå ein eigen prosess. Artikkelen
  slår saman kvar node og relasjon, noko som søkjer etter duplikat i grafen og går
  seinare di større grafen blir.
- Select-verdiar blir eigenskapar på noden sin. Artikkelen gjev dei eigne nodar
  med ein generert identifikator.
- Fleire modellar deler éin database og blir skilde med `model_id`. Artikkelen har
  éin modell per database.
- Relasjonstypane blir skrivne med store bokstavar, og `SAME_AS` og kopien av GTIN
  er tillegg her.

Artikkelen peikar på at grafen hans mistar rekkjefølgja i lister, sidan ein relasjon
ikkje seier kvar i ei liste målet stod. Her seier `position` det.

## Skrive ein modell tilbake

Grafen rommar heile modellen, og fila kan skrivast tilbake frå han: dei same instansane
med dei same id-ane og dei same verdiane i same rekkjefølgje, og dermed òg den same
geografiske informasjonen.

```sh
uv run opencde ifc-lpg export <modell-id> model.ifc            # skriv fila og valider ho
uv run opencde ifc-lpg export <modell-id> model.ifc --verify   # og samanlikn ho med den opplasta
```

Nodane er dei spørjingar treng. Det dei utelèt, blir skrive ut som STEP og komprimert
til tekst på `StepBlock`-nodar som heng på `IfcModel`: det er i grafen, men utanfor
rekkjevidda til Cypher, og det kan ikkje endrast der. Det kan ikkje vere eigenskapar på
produkta, sidan mykje av det blir delt mellom dei. Med
`OPENCDE_IFC_LPG_INCLUDE_GEOMETRY=true` blir kvar instans ein node i staden, til fleire
gonger storleiken og importtida; spørjingar tok omtrent like lang tid i
målingane.

| I fila | I grafen |
|---|---|
| Ein referanse | Ein relasjon med `position`, `[rad, kolonne]` i ei liste av lister; inverse relasjonar har ingen |
| Ein referanse til ein instans i ei blokk | Id-en hans, som i `Representation__step: 1234` |
| Ein typa verdi, `IFCLABEL('3')` | `NominalValue: "3"`, og `NominalValue__type: "IFCLABEL"` ved sida av |
| Ei liste av lister av tal | JSON-tekst |
| Det som manglar enkel form, som ei liste av typa verdiar | Merkt JSON, med `$json` som type |
| Headeren | `ifc_header` på `IfcModel` |
| Ein instans i ei blokk | Tekst i ei `StepBlock` |

Fila blir skriven frå det grafen rommar og blir ikkje kopiert, så ein eigenskap eller ein
relasjon som blir endra i grafen, syner i ho. Ein grafdatabase har ikkje noko skjema å
halde ei endring opp mot, så fila blir validert mot IFC-standarden med validatoren til
IfcOpenShell: typen og talet på attributt, enumerasjonar, inverse attributt, GlobalId og
reglane i EXPRESS-skjemaet. Filer i bruk bryt ofte alt ein regel, så det som tel, er ei
merknad den opplasta fila ikkje har. Kommandoen viser ho då og sluttar med ein feil.
`--no-validate` hoppar over dette. Ein eksport stoppar òg om ei blokk manglar.

Prosjektmedlemmer får filer gjennom Documents API, og det finst inga anna vegen ut av
serveren. Ei skriven fil som skal erstatte ein modell, blir lasta opp som ein ny versjon
av dokumentet sitt, noko som òg konverterer henne.

Denne forma blir ikkje lesen med IfcOpenShell, som her berre står for skjemaet.
IfcOpenShell endrar nokre verdiar ved lesing (`.NULLENUM.` blir `$`, og `($,$)` blir
`()`), og filer frå Tekla og Archicad har slike. Difor les arbeidsprosessen fila sjølv og
avviser det han ikkje kan lese. ADR 0010 seier kvifor, og
ADR 0011 korleis ei fil blir validert.

`--verify` spør om dei to filene rommar den same modellen, etter definisjonen i
ADR 0009: ein til ein, verdi for verdi og utan toleranse, med georeferansen
namngjeven i rapporten. Med `--geometry` blir òg meshen til kvart produkt bygd, og dei
blir samanlikna bit for bit. To vilkårlege filer kan samanliknast med
`python -m ifc_lpg.equivalence first.ifc second.ifc`.

Med `OPENCDE_IFC_LPG_LOSSLESS=false` blir ein modell konvertert som før 3.0.0: han blir
lesen med IfcOpenShell, og det som ikkje er nodar, blir utelate heilt. Ein slik modell,
i likskap med ein som er konvertert av ein tidlegare versjon, kan ikkje skrivast tilbake.

## Opprydding

Kvar opplasting av ei IFC-fil legg til ein `IfcModel` med entitetane sine, så
eit prosjekt som får nye versjonar, samlar grafar ingen spør mot.
Kommandolinja listar og fjernar dei; dokumenta og filene deira blir alltid
att:

```sh
uv run opencde ifc-lpg list --project <prosjekt-id>
uv run opencde ifc-lpg prune                   # mislukka modellar, og ferdige modellar erstatta av ein nyare
                                                # ferdig versjon av same dokument
uv run opencde ifc-lpg prune --project <id> --all   # kvar modell i eitt prosjekt (ein teststakk, til dømes)
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
konfigurerte eigenskapen (`OPENCDE_IFC_LPG_GTIN_PROPERTY_SET=Reuse`,
`OPENCDE_IFC_LPG_GTIN_PROPERTY=GTIN`), blir verdien kopiert til komponenten
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

## Namngjevne spørjingar

Eit medlem av eit prosjekt stiller spørsmål til modellen i ein versjon ved
namn, med det same bearer-tokenet som for Documents API; fri Cypher blir
verande hos administratorane (ADR 0016).
`GET /documents/1.0/documents/{id}/versions/{index}/ifc-queries` viser
spørjingane med parametrar og kolonnar og seier i `model_state` kor langt
konverteringa av modellen har kome. `GET …/ifc-queries/{name}` stiller éi,
med parametrane i spørjestrengen, og svarar med kolonnane og radene, kvar rad
ei liste i rekkjefølgja til kolonnane:

```http
GET /documents/1.0/documents/{id}/versions/1/ifc-queries/property?pset=Reuse&property=GTIN
```

```json
{"name": "property", "columns": ["global_id", "class", "name", "value", "type"],
 "rows": [["1Xezbq735AdBO_4DerG66G", "IfcWallStandardCase", "YVT-A", "3", "IFCLABEL"]],
 "truncated": false}
```

| Spørjing | Parametrar | Kva ho svarar på |
|---|---|---|
| `element-classes` | | Kor mange element modellen har av kvar klasse |
| `elements` | `class` | Elementa av ein klasse, med den romlege strukturen som inneheld kvart |
| `storeys` | | Etasjane, nivået deira og kor mange element og rom kvar rommar |
| `spaces` | | Romma, etasjen deira og netto- og bruttogolvarealet deira |
| `areas` | | Nettogolvarealet til romma i kvar etasje, lagt saman |
| `materials` | `class` | Materiala til kvart element: eit eige, eller laga, lista eller bestanddelane sine |
| `property` | `pset`, `property`, `class` | Verdien av éin eigenskap på kvart objekt som har han, med IFC-typen |

`class` namngjev ein IFC-klasse, til dømes `IfcWall`, og tek med seg
underklassane: påkravd for `elements`, valfri for dei andre. Eit svar rommar
høgst 10 000 rader, og `truncated` seier når det var fleire; ei spørjing blir
stoppa etter 10 sekund. Kvar spørjing byrjar ved medlemmen og når modellen
gjennom prosjektet, les berre og tek verdiane sine som parametrar. Ein versjon
utan modell, eller ein som brukaren ikkje får sjå, svarar 404, og ein der
modellen framleis blir konvertert, svarar 409. Kapabilitetsdokumentet kunngjer
spørjingane i `ifc_queries`.

## Endringssett

Ei føreslått endring av ein modell reiser som `bim_snippet` i ei BCF 3.0-sak
(ADR 0021): `snippet_type` er `DataregiumIfcChangeSet`, `reference_schema` er
`GET /documents/1.0/ifc-changes/schema`, som kven som helst kan lese, og sjølve
snippeten blir lasta opp med `PUT …/topics/{guid}/snippet`, der serveren held
han til skjemaet og svarar `400` med kva som er gale. Eit nytt prosjekt tillèt
snippettypen; ein administrator legg han til mellom verdiane i eit eldre
prosjekt. Eit endringssett oppgjev basisversjonen sin, kven som føreslo det, med
AI-modellen og verktøykallet der ein AI gjorde det, og endringane sine, kvar på
eitt attributt hos éin instans. Instansen blir oppgjeven med STEP-id-en sin,
eller med ein GlobalId og ein sti frå den rotfesta entiteten i attributtnamna
til IFC med indeksar. `set` gjev attributtet ein verdi, `add` og `remove`
endrar éin medlem av eit aggregat, og `copy` ber om ein kopi av ein instans som
fleire deler, og som elles blir endra for alle. Ein verdi er ein skalar, ein
instans (`{"step_id": 120}`, eller ein GlobalId med sti), ein typa verdi
(`{"type": "IfcLengthMeasure", "value": 3.2}`), ein enumerasjon
(`{"enum": "NOTDEFINED"}`) eller ei liste av dei. Kapabilitetsdokumentet
annonserer forma som `ifc_changes`. Kva endringane gjer med modellen, blir
prøvd når forslaget blir prøvd, det neste steget; i dag held serveren forma.

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

Når IFC-LPG-modulen er på, prøver serveren kvart endringssett når det blir
lasta opp: ein arbeidar bruker endringane på fila til basisversjonen,
resultatet går gjennom kontrollane ei opplasting får (IFC-skjemaet, reglane til
buildingSMART og IDS-dokumenta i prosjektet), og prøven er `clean` når kvar
endring kunne brukast og ingen merknad er ny samanlikna med rapporten til
basisversjonen, elles `issues`.
`GET /bcf/3.0/projects/{id}/topics/{guid}/ifc-proposal` gjev tilstanden, kor
mange endringar som vart brukte, og dei nye merknadene, kvar som i rapporten
til ein versjon; ei endring som ikkje kunne brukast, er ein merknad av slaget
`proposal` som seier kvifor, utan å sitere fila. Ein ny snippet erstattar
prøven, og prøven følgjer med saka når ho blir sletta. `ifc_changes` i
kapabilitetsdokumentet seier om endringssett blir prøvde (`tried`) og kvar
prøven er (`proposal_url`).

Ein `manager` godkjenner ei rein prøve med `POST …/ifc-proposal/approve`: den
brukte fila blir den neste versjonen av basisdokumentet, med
`base_version_index`, `change_set_id` (guid-en til saka), `proposed_by` og
`approved_by` i metadataa sine, og AI-modellen og verktøykallet der ein AI
føreslo henne; svaret er den nye versjonen slik Documents API gjev han, og han
blir konvertert og kontrollert som ei opplasting. Saka får ein kommentar med
adressa til versjonen, og statusen `Closed` der prosjektet har den verdien.
`412 version_conflict` seier at dokumentet har gått vidare sidan basen; `409`
at prøven ikkje er rein, eller alt er godkjend. Ein AI føreslår berre:
godkjenninga er eit menneske si.

## Kollisjonskontroll

Ein medlem samanliknar to IFC-dokumentversjonar i eit prosjekt for kollisjonar,
med same bearer-token som Documents API:
`POST /documents/1.0/projects/{project_id}/ifc-clash` med dei to versjonane,
modusen (`intersection`: element som går inn i kvarandre djupare enn
`tolerance`; `clearance`: element nærare kvarandre enn `clearance`, begge i
meter) og, om ein vil, IFC-klassane til kvar side. Kontrollen køyrer i ein
arbeidsprosess bak konverteringskøen; `url` i svaret gjev rapporten, `done`
eller `failed` etter ei stund. Kvar kollisjon namngjev begge elementa (dokument,
versjon, STEP-id, GlobalId, klasse, namn, etasje), slaget sitt, djupna eller
avstanden og punktet der han vart målt, i den forma Dataspatium sin eigen
kollisjonskjerne skriv, så appen viser resultatet frå serveren som sitt eige.
`POST …/ifc-clash/{id}/topics` gjer valde kollisjonar til BCF-saker med kvart
sitt viewpoint, berre på førespurnad. Kapabilitetsdokumentet annonserer
kontrollen som `ifc_clash` når operatøren har sett
`OPENCDE_IFC_LPG_CLASH_ENABLED=true`; ein rapport held på høgst
`OPENCDE_IFC_LPG_CLASH_MAX_CLASHES` kollisjonar.

```http
POST /documents/1.0/projects/{project_id}/ifc-clash
{"a": {"document_id": "…", "version_index": 1, "types": ["IfcWall"]},
 "b": {"document_id": "…", "version_index": 2},
 "mode": "intersection", "tolerance": 0.001}
```

## Spørjingar frå Dataspatium

[Dataspatium](https://github.com/marwiss/Dataspatium), nettlesarklienten som
blir utvikla saman med denne serveren, køyrer Cypher mot denne grafen gjennom
Neo4j-kjelda si over Bolt (WebSocket på Bolt-porten) når operatøren
eksponerer databasen, slik utviklingsoverlegget gjer på `127.0.0.1:7697`.
Dataregium-arbeidsområdet der brukar mønstera ovanfor (modellar, klassar,
komponentar via `SAME_AS`, den siste ferdige modellen per dokument);
spørjingane ligg i dokumentasjonen til Dataspatium (`docs/grafer.md`). Ein
produksjonsserver publiserer ikkje Bolt; grafspørjinga i
administrasjons-API-et (`OPENCDE_GRAPH_QUERY_ENABLED`,
[client-guide.md §7](client-guide.md)) gjev administratorar lesande Cypher
utan porten. Appen teiknar òg grafen, i kortet
IFC-LPG, gjennom den spørjinga eller over Bolt.

## Grenser og status

- Éi konvertering om gongen; store modellar står i kø. Dømemodellen (248
  entitetar) blir importert på omkring eitt sekund; ein arkitektmodell på
  200 MB tek minutt.
- `IfcModel`-noden ber `state`, `entities`, `relationships`, `skipped`,
  `lossless`, `geometry`, `schema`, `ifc_project_guid`, tidsstempel og `error`. Administratorar kan
  inspisere han i Neo4j Browser eller Memgraph Lab:
  `MATCH (m:IfcModel) RETURN m.file_name, m.state, m.entities, m.error`.
- Sletting av eit prosjekt slettar entitetane til modellane i det.
- Ein modell kjem identisk tilbake frå begge databasane opp til 224 496 instansar og 19 MB, i
  kvar form som er målt. Ingenting større er prøvd.
