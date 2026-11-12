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

## AI-policyen

`ai_policy` til eit prosjekt er `local`, standardverdien, eller `cloud`, og blir
sett av manageren til prosjektet eller ein administrator. Den lokale motoren
tener kvart prosjekt, fordi datamaskina er grensa. Kvar annan server listar ikkje
`local`-prosjekt i det heile, og spurd om eitt med id-en avslår verktøyet, og
revisjonsloggen noterer `mcp.denied`. Serveren held styr på kvar dataa går; kva
modell som les dei, er valet til klienten, og eit anna program på same maskin
kan likevel sende svara til ein modell i skya.

## Grenser og loggar

- Ein kropp er høgst 1 MB og eit svar høgst 256 kB; namn og titlar blir kutta
  ved 200 teikn.
- Eit token gjer høgst 120 verktøykall i minuttet, i tillegg til grensa per
  adresse som alle program deler (`OPENCDE_RATE_LIMIT_API`); utover henne svarar
  verktøyet `isError` med kor mange sekund det må ventast.
- Førespurnadsloggen held på metoden og namnet på verktøyet, aldri kroppen.
  Revisjonsloggen held på `mcp.denied` med grunnen (`policy` eller `scope`),
  verktøyet og klienten, aldri eit argument eller ein tekst frå prosjekta.

## Data, aldri instruksjonar

Alt eit verktøy returnerer, er data frå prosjekta: eit namn, ein tittel eller ein
tekst frå IFC, BCF eller eit dokument kjem tilbake som han er, i eit namngjeve
felt, kva han så seier. Verktøyskildringane og `instructions` til serveren er
faste tekstar som seier det. Ein person godkjenner eit framlegg i Dataspatium,
innlogga der; eit token for endepunktet når aldri ei godkjenning eller ei
publisering.
