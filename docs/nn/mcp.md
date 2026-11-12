# MCP-endepunktet (utviding)

Gjennom `POST /mcp` les AI-program som talar Model Context Protocol (Claude,
ChatGPT, VS Code, Cursor og klientane for lokale modellar) IFC-modellane i dei
prosjekta som ein person er medlem i, i namnet til personen. AI-en gjer framlegg,
og eit menneske godkjenner: ingen verktøy godkjenner, publiserer, lastar opp,
slår saman, slettar eller administrerer noko (ADR 0028). Serveren køyrer ingen
eigen AI; programmet, modellen og budsjettet er klienten sine.

## Å slå det på

Endepunktet er slått av til `OPENCDE_MCP_ENABLED=true`. `opencde init --local`
slår det på i den lokale motoren, der `http://127.0.0.1:8000/mcp` berre svarar
på loopback. På ein teamserver går det gjennom proxyen som API-et, med https.
Medan det er slått på, kunngjer kapabilitetsdokumentet det som `mcp`
([klientguiden](client-guide.md), §1), og autorisasjonsserveren listar scopa
`mcp` og `mcp:propose`.

## Eit token for endepunktet

Endepunktet tek berre eit token som er skrive ut for det, og ingen REST-API tek
eit slikt token:

1. Registrer programmet som klient, slik kvar klient blir registrert: sjølv, der
   `OPENCDE_DYNAMIC_CLIENT_REGISTRATION` er slått på (den lokale motoren), eller
   av ein administrator.
2. Programmet finn vegen inn sjølv: `401` frå `/mcp` nemner
   `/.well-known/oauth-protected-resource/mcp`, som nemner
   autorisasjonsserveren, med metadata på
   `/.well-known/oauth-authorization-server`.
3. Det loggar personen inn med `resource=<public_url>/mcp` og scopet `mcp`
   (lesing). `mcp:propose`, for endringssetta, blir bede om når eit verktøy
   treng det: `403 insufficient_scope` nemner begge scopa. Samtykkesida seier kva
   dei gjev, og at ingenting blir godkjent eller publisert gjennom dei.

[Klientguiden](client-guide.md) (§2) har reglane for bindinga.

## Å kople til eit AI-program

Programmet treng berre adressa til endepunktet; det registrerer seg, loggar
personen inn og finn scopa sjølv, som ovanfor.

- Den lokale motoren: `http://127.0.0.1:8000/mcp`, for program på same
  datamaskin, som når kvart prosjekt.
- Ein teamserver: `https://cde.example.org/mcp` med det eigne namnet til serveren, som berre når dei
  prosjekta der AI-policyen er `cloud`. Eit program som køyrer i skya, som ei
  kopling i Claude eller ChatGPT, når ein teamserver på internett og aldri den
  lokale motoren.

Slik dei eigne rettleiingane til programma skildrar det, legg Claude Code han
til med ein kommando, VS Code i `.vscode/mcp.json` og Cursor i
`~/.cursor/mcp.json`:

```sh
claude mcp add --transport http dataregium https://cde.example.org/mcp
```

```json
{"servers": {"dataregium": {"type": "http", "url": "https://cde.example.org/mcp"}}}
```

```json
{"mcpServers": {"dataregium": {"url": "https://cde.example.org/mcp"}}}
```

Det første kallet opnar innloggingssida til serveren i nettlesaren; etter
samtykket listar programmet verktøya. Ein god start er `list_models` og så
`server_query` med `name` null for spørjingane ein modell svarar på. For å
føreslå ber programmet om `mcp:propose` ved det første verktøyet for
endringssett, og personen er editor eller manager i prosjektet. Der serveren
ikkje registrerer klientar sjølv, registrerer ein administrator programmet med
omdirigeringsadressa det gjev: `http://127.0.0.1` med valfri port blir godteken,
`http://localhost` berre der `OPENCDE_ALLOW_LOCALHOST_REDIRECTS` er på, noko
produksjon avslår.

## Protokollen

Streamable HTTP med eitt JSON-svar per førespurnad og ingen SSE. Revisjon
2026-07-28 er tilstandslaus: kvar førespurnad ber revisjonen sin og
kapabilitetane til klienten i `_meta`, og hovuda `MCP-Protocol-Version`,
`Mcp-Method` og `Mcp-Name` gjentek det kroppen seier. Metodane er
`server/discover`, `tools/list` og `tools/call`; resultata ber `resultType`, og
oppdaginga og lista over verktøy `ttlMs` (ein time) og `cacheScope` (`private`).
Revisjonane 2025-11-25, 2025-06-18 og 2025-03-26 får òg `initialize` og `ping`,
utan sesjon: serveren lagar aldri ein `Mcp-Session-Id`, og kvart kall blir svara
for seg. Ein førespurnad utan `MCP-Protocol-Version` er av revisjon 2025-03-26.

```http
POST /mcp HTTP/1.1
Authorization: Bearer <a token bound to the endpoint>
Content-Type: application/json
MCP-Protocol-Version: 2026-07-28
Mcp-Method: tools/call
Mcp-Name: list_models

{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
 "params": {"name": "list_models", "arguments": {"project_id": null},
            "_meta": {"io.modelcontextprotocol/protocolVersion": "2026-07-28",
                      "io.modelcontextprotocol/clientCapabilities": {}}}}
```

| Svar | Når |
|---|---|
| `400`, `-32700` eller `-32600` | Kroppen er ikkje JSON, er ein batch eller er ikkje éin JSON-RPC-førespurnad eller -melding |
| `400`, `-32602` | `_meta` manglar revisjonen eller kapabilitetane; eit ukjent verktøy; argument som ikkje er eit objekt |
| `400`, `-32020` | Eit hovud seier ikkje det kroppen seier, eller manglar eller blir gjeve to gonger |
| `400`, `-32022` | Ein revisjon endepunktet ikkje svarar på; `data` nemner dei det svarar på |
| `404`, `-32601` | Ein metode endepunktet ikkje har |
| `202` | Ei melding (notification) |
| `401`, `403` | Ikkje noko token bunde til endepunktet, eller scopet til eit verktøy manglar |
| `403` | Ein `Origin` som verken er den eigne til serveren eller nemnd i `OPENCDE_CORS_ORIGINS`; `null` og `*` tel ikkje |
| `405` | `GET`, `DELETE` og kvar metode utanom `POST` |
| `413` | Ein kropp som er større enn 1 MB |

Handtrykkrevisjonane svarar på feila i ein førespurnad med `200`, slik
serverane deira gjorde. `/mcp` har ingen CORS: ingen nettlesar treng han.

## Verktøya

Kvart argument er kravd, og `null` tyder "ikkje oppgjeve". Eit avslag (eit
prosjekt som ikkje er det til den som kallar, AI-policyen, argument verktøyet
ikkje tek) er eit verktøyresultat med `isError: true` som AI-en kan lese; svaret
er `structuredContent` og den same JSON-en som tekst.

- `list_models` (scopet `mcp`): éi rad per IFC-dokument i prosjekta til
  personen, eller i eitt `project_id`: `project_id`, `project_name`, `role` til
  personen, `ai_policy` til prosjektet, `document_id`, `title` og `file_name` for
  den nyaste versjonen, `version_index`, `model_state` (`done` når modellen kan
  spørjast, `queued`, `running` eller `failed`, `null` utan modell) og
  IFC-`schema`. Høgst 200 rader, og `truncated` når det fanst fleire.

```json
{"models": [{"project_id": "…", "project_name": "Building permit", "role": "editor", "ai_policy": "cloud",
             "document_id": "…", "title": "Walls", "file_name": "walls.ifc", "version_index": 2,
             "model_state": "done", "schema": "IFC4"}],
 "truncated": false}
```

- `server_query` (scopet `mcp`): dei [namngjevne spørjingane](ifc-lpg.md#namngjevne-spørjingar)
  mot modellen til ein versjon, med `document_id` og `version_index` (`null` for
  den nyaste), slik Documents API stiller dei. `name` er ei av spørjingane i
  katalogen til serveren, og kvar av parametrane deira er eit eige felt
  (`class`, `pset`, `property`, `global_id`, `since`); skildringa av verktøyet
  ramsar opp spørjingane med parametrane deira, så ei spørjing IFC-LPG legg til,
  dukkar opp når serveren er oppdatert. `name: null` listar dei, med
  `model_state` og `workcopy` til modellen. Ei spørjing svarar `name`,
  `columns`, høgst 500 `rows`, `count` (radene ho fann, høgst 10 000) og
  `truncated`; ein tekst i ei rad blir kutta ved 1 000 teikn.
- `get_publication` (scopet `mcp`): om ein versjon er publisert, og i så fall
  `published_at`, `published_by`, `file_name`, `size_in_bytes` og `sha256`,
  kvar `null` så lenge han ikkje er det; aldri kvar arkivet blir lasta ned.
- `start_clash_check` (scopet `mcp`): ein [kollisjonskontroll](ifc-lpg.md#kollisjonskontroll)
  mellom to versjonar i eit prosjekt: `project_id`, `a` og `b` med
  `document_id`, `version_index` og `types` (IFC-klassar, `null` for kvart
  element med ein kropp), `mode` (`intersection` eller `clearance`), og
  `tolerance` og `clearance` i meter (`null` for 0,001 og 0,05). Det svarar
  `clash_id` og `state`, og revisjonsloggen noterer `mcp.clash.started`.
- `get_clash_check` (scopet `mcp`): rapporten for ein kontroll, med `project_id`
  og `clash_id`, og ventar høgst `wait_seconds` (høgst 20) på ein som står i kø
  eller køyrer: `state`, førespurnaden, `count`, `set_a`, `set_b`, `missing`,
  `seconds` og høgst 200 `clashes`, med `truncated` når det fanst fleire. Begge
  kollisjonsverktøya avslår utan `OPENCDE_IFC_LPG_CLASH_ENABLED=true`.
  Dei tre blir viste berre medan IFC-LPG-modulen er på. Ein brukar har høgst to
  kontrollar som ventar eller køyrer, i alle prosjekta sine til saman; ein
  tredje blir avslått, og revisjonsloggen fører `mcp.denied` med grunnen `limit`.

```json
{"name": "elements", "columns": ["global_id", "class", "name", "container"],
 "rows": [["1Xezbq735AdBO_4DerG66G", "IfcWallStandardCase", "YVT-A", "1. etasje"]],
 "count": 1, "truncated": false}
```

## Endringssetta

Medan IFC-LPG-modulen er slått på (`OPENCDE_IFC_LPG_ENABLED`), som prøver
endringssetta, har lista òg verktøya som føreslår endringar i ein modell, i
rekkjefølgja til Dataspatium. Dei krev scopet `mcp:propose`, rolla `editor` eller
`manager` i prosjektet, prøvd ved kvart kall slik REST-API-et prøver ho, og
AI-policyen til prosjektet; ei rolle som vert avvist, vert `mcp.denied` med
grunnen `role`. Ingen verktøy godkjenner: det gjer ein person, i Dataspatium.

- `open_changeset` (`document_id`, `version_index`, `null` for den siste): opnar
  eit endringssett på ein versjon av eit IFC-dokument og svarar med
  `changeset_id`, `base`, `expires_at` og `max_steps` (200).
- Skriveverktøya `create_storeys_and_grid`, `define_type`, `create_wall`,
  `create_slab`, `create_roof`, `create_opening`, `create_element`,
  `create_spaces`, `set_properties`, `set_classification`, `assign`,
  `edit_element`, `transform_elements`, `delete_elements` (med `confirm: true`) og
  `set_site`: dei Dataspatium sjølv har, med skjemaa uendra og `changeset_id`
  først. Eit kall er éin operasjon i `ops` i endringssettet i forma
  `dataspatium-tools/1`, nøyaktig slik appen lagar han (standardverdiane fylte
  inn, tala prøvde, tekstane kutta ved 200 teikn, eit valfritt felt berre når det
  er oppgjeve), eller feilen til appen, som AI-en rettar. Ein type, ein vegg, eit
  dekke, eit tak, ei opning eller ein bygningsdel får ein ref, `new-1`, `new-2` …,
  og det gjer kvart rom som `create_spaces` listar opp; eit element eller ein type
  vert nemnt ved GlobalId-en sin, STEP-id-en sin eller ein ref. Skildringane
  utelèt leseverktøya `search_ifc_class` og `get_parameters` i appen, som dette
  endepunktet ikkje tilbyr, og `set_properties` svarar med rådet frå rettleiinga
  om namnet på eit eige sett som `note`.
- `manage_changeset` (`action`: `list`, `remove_last` eller `clear`): stega med
  verktøya, refs og skildringane sine; det siste steget fjerna, med refs; eller
  ingen att.
- `change_attribute` (`guid` eller `step_id`, `path`, `attribute`, `op` `set`,
  `add` eller `remove`, `index`, `old`, `new`, `copy`): éin attributt på éin
  instans i basen, ein post i `changes` i endringssettet i forma til skjemaet;
  `old` vert prøvd når endringssettet vert prøvd.
- `propose_changes` (`title`; `description`, `null` for dei eigne linjene til
  stega; `ai_model`, det AI-en oppgjev at han er): ei BCF-sak i prosjektet med
  endringssettet som snippet, som tenaren set i kø for prøving. Proveniensen
  nemner brukaren, den oppgjevne `ai_model` og `tool_call` `mcp:` med verktøya til
  stega. Kalla att med same handtak legg det endringssettet slik det er då på
  same sak og prøver det att. Svarar med `project_id`, `topic_guid`, `state`
  (`queued`) og kor mange `ops` og `changes` endringssettet har.
- `get_proposal` (`project_id`, `topic_guid`, `wait_seconds` opp til 20; scopet
  `mcp`): prøven slik `GET …/ifc-proposal` gjev han, med venting medan han er
  `queued` eller `running`, med høgst 50 merknader, `created` (GlobalId-en til
  det operasjonane laga, etter ref-en) og `notes`.
- `list_proposals` (`document_id`, `limit` opp til 50; scopet `mcp`): framlegga
  mot eit dokument, nyaste først, slik `GET …/ifc-proposals` listar dei, med
  `project_id` og utan adressene.

Flyten:

1. `list_models` gjev dokumentet og den siste versjonen av det.
2. `open_changeset` gjev handtaket, og skriveverktøya og `change_attribute` fyller
   endringssettet steg for steg; eit steg som vart feil, vert retta med
   `manage_changeset` `remove_last` og eit nytt steg.
3. `propose_changes` lagar framlegget, og `get_proposal` svarar `clean`, `issues`
   med merknadene eller `failed`. Ved merknader rettar AI-en endringssettet og
   føreslår det att.
4. Ved `clean` seier AI-en frå til personen, som godkjenner det i Dataspatium: ein
   manager i prosjektet eller den ansvarlege for det eine teamet som delen det
   rører ved, høyrer til.

```json
{"ok": true, "step": 1, "ref": "new-1",
 "description": "new-1 Wall New wall on the lowest storey from (0, 0) to (4, 0), 0.2 m thick, 3 m high"}
```

Det opne endringssettet er eit utkast på tenaren, brukaren sitt eige. Handtaket
er eit namn, ikkje ei løyve: kvart kall prøver at utkastet er det til den som
kallar, og ligg i eitt av prosjekta til den som kallar. Det vert lukka 24 timar
etter siste bruk, og tenaren slettar det; eit ukjent eller lukka handtak er ein
verktøyfeil som ber om eit nytt. Ein brukar har høgst 10 opne, og eit
endringssett høgst 200 steg.

## AI-policyen

`ai_policy` til eit prosjekt er `local`, standardverdien, eller `cloud`, og blir
sett av manageren til prosjektet eller ein administrator. Den lokale motoren
tener kvart prosjekt, fordi datamaskina er grensa. Kvar annan server listar ikkje
`local`-prosjekt i det heile, og spurd om eitt, med id-en eller med eitt av
dokumenta, avslår eit verktøy, og revisjonsloggen noterer `mcp.denied`. Serveren
held styr på kvar dataa går; kva modell som les dei, er valet til klienten, og
eit anna program på same maskin kan likevel sende svara til ein modell i skya.

## Grenser og loggar

- Ein kropp er høgst 1 MB og eit svar høgst 256 kB, med høgst 500 rader frå ei
  spørjing og 200 kollisjonar; namn og titlar blir kutta ved 200 teikn og ein
  tekst i radene frå ei spørjing ved 1 000. `get_clash_check` ventar høgst 20
  sekund.
- Ein brukar gjer høgst 120 verktøykall i minuttet, same kva token, i tillegg til grensa per
  adresse som alle program deler (`OPENCDE_RATE_LIMIT_API`); utover henne svarar
  verktøyet `isError` med kor mange sekund det må ventast.
- Førespurnadsloggen held på metoden og namnet på verktøyet, aldri kroppen.
  Revisjonsloggen held på `mcp.denied` med grunnen (`policy`, `role`, `scope` eller `limit`) og
  `mcp.clash.started` med prosjektet, kontrollen og dei to versjonane, kvar med
  verktøyet og klienten, aldri eit argument eller ein tekst frå prosjekta.
- Revisjonsloggen held òg på `mcp.changeset.opened` og
  `mcp.changeset.proposed` med prosjektet, dokumentet, basen, endringssettet,
  saka, talet på operasjonar og endringar og den oppgjevne AI-modellen, kutta
  ved 100 teikn; aldri ein tittel, ei skildring eller eit steg.

## Data, aldri instruksjonar

Alt eit verktøy returnerer, er data frå prosjekta: eit namn, ein tittel eller ein
tekst frå IFC, BCF eller eit dokument kjem tilbake som han er, i eit namngjeve
felt, kva han så seier. Verktøyskildringane og `instructions` til serveren er
faste tekstar som seier det. Ein person godkjenner eit framlegg i Dataspatium,
innlogga der; eit token for endepunktet når aldri ei godkjenning eller ei
publisering.
