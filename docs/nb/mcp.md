# MCP-endepunktet (utvidelse)

Gjennom `POST /mcp` leser AI-programmer som snakker Model Context Protocol
(Claude, ChatGPT, VS Code, Cursor og klientene for lokale modeller)
IFC-modellene i prosjektene en person er medlem av, i personens navn. AI-en
foreslår, og et menneske godkjenner: ingen verktøy godkjenner, publiserer, laster
opp, slår sammen, sletter eller administrerer noe (ADR 0028). Serveren kjører
ingen egen AI; programmet, modellen og budsjettet er klientens.

## Å slå det på

Endepunktet er slått av til `OPENCDE_MCP_ENABLED=true`. `opencde init --local`
slår det på i den lokale motoren, der `http://127.0.0.1:8000/mcp` bare svarer på
loopback. På en teamserver går det gjennom proxyen som API-et, med https. Mens
det er slått på, kunngjør kapabilitetsdokumentet det som `mcp`
([klientguiden](client-guide.md), §1), og autorisasjonsserveren lister scopene
`mcp` og `mcp:propose`.

## Et token for endepunktet

Endepunktet tar bare et token som er utstedt for det, og ingen REST-API tar et
slikt token:

1. Registrer programmet som klient, slik hver klient registreres: selv, der
   `OPENCDE_DYNAMIC_CLIENT_REGISTRATION` er slått på (den lokale motoren), eller
   av en administrator.
2. Programmet finner veien inn selv: `401` fra `/mcp` nevner
   `/.well-known/oauth-protected-resource/mcp`, som nevner
   autorisasjonsserveren, med metadata på
   `/.well-known/oauth-authorization-server`.
3. Det logger personen inn med `resource=<public_url>/mcp` og scopet `mcp`
   (lesing). `mcp:propose`, for endringssettene, bes om når et verktøy trenger
   det: `403 insufficient_scope` nevner begge scopene. Samtykkesiden sier hva de
   gir, og at ingenting godkjennes eller publiseres gjennom dem.

[Klientguiden](client-guide.md) (§2) har reglene for bindingen.

## Protokollen

Streamable HTTP med ett JSON-svar per forespørsel og ingen SSE. Revisjon
2026-07-28 er tilstandsløs: hver forespørsel bærer sin revisjon og klientens
kapabiliteter i `_meta`, og hodene `MCP-Protocol-Version`, `Mcp-Method` og
`Mcp-Name` gjentar det kroppen sier. Metodene er `server/discover`, `tools/list`
og `tools/call`; resultatene bærer `resultType`, og oppdagelsen og listen over
verktøy `ttlMs` (en time) og `cacheScope` (`private`). Revisjonene 2025-11-25,
2025-06-18 og 2025-03-26 får også `initialize` og `ping`, uten sesjon: serveren
lager aldri en `Mcp-Session-Id`, og hvert kall besvares for seg. En forespørsel
uten `MCP-Protocol-Version` er av revisjon 2025-03-26.

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
| `400`, `-32700` eller `-32600` | Kroppen er ikke JSON, er en batch eller er ikke én JSON-RPC-forespørsel eller -melding |
| `400`, `-32602` | `_meta` mangler revisjonen eller kapabilitetene; et ukjent verktøy; argumenter som ikke er et objekt |
| `400`, `-32020` | Et hode sier ikke det kroppen sier, eller mangler eller gis to ganger |
| `400`, `-32022` | En revisjon endepunktet ikke svarer på; `data` nevner dem det svarer på |
| `404`, `-32601` | En metode endepunktet ikke har |
| `202` | En melding (notification) |
| `401`, `403` | Ikke noe token bundet til endepunktet, eller et verktøys scope mangler |
| `403` | En `Origin` som verken er serverens egen eller nevnt i `OPENCDE_CORS_ORIGINS`; `null` og `*` teller ikke |
| `405` | `GET`, `DELETE` og hver metode unntatt `POST` |
| `413` | En kropp som er større enn 1 MB |

Håndtrykkrevisjonene besvarer feilene i en forespørsel med `200`, slik
serverne deres gjorde. `/mcp` har ingen CORS: ingen nettleser trenger den.

## Verktøyene

Hvert argument kreves, og `null` betyr "ikke oppgitt". Et avslag (et prosjekt
som ikke er den som kaller, sitt, AI-policyen, argumenter verktøyet ikke tar) er
et verktøyresultat med `isError: true` som AI-en kan lese; svaret er
`structuredContent` og den samme JSON-en som tekst.

- `list_models` (scopet `mcp`): én rad per IFC-dokument i personens prosjekter,
  eller i ett `project_id`: `project_id`, `project_name`, personens `role`,
  prosjektets `ai_policy`, `document_id`, `title` og `file_name` for den nyeste
  versjonen, dens `version_index`, dens `model_state` (`done` når modellen kan
  spørres, `queued`, `running` eller `failed`, `null` uten modell) og dens
  IFC-`schema`. Høyst 200 rader, og `truncated` når det fantes flere.

```json
{"models": [{"project_id": "…", "project_name": "Building permit", "role": "editor", "ai_policy": "cloud",
             "document_id": "…", "title": "Walls", "file_name": "walls.ifc", "version_index": 2,
             "model_state": "done", "schema": "IFC4"}],
 "truncated": false}
```

- `server_query` (scopet `mcp`): de [navngitte spørringene](ifc-lpg.md#navngitte-spørringer)
  mot en versjons modell, med `document_id` og `version_index` (`null` for den
  nyeste), slik Documents API stiller dem. `name` er en av spørringene i
  serverens katalog, og hver av parameterne deres er et eget felt (`class`,
  `pset`, `property`, `global_id`, `since`); verktøyets beskrivelse ramser opp
  spørringene med parameterne deres, så en spørring IFC-LPG legger til, dukker
  opp når serveren er oppdatert. `name: null` lister dem, med modellens
  `model_state` og `workcopy`. En spørring svarer `name`, `columns`, høyst 500
  `rows`, `count` (radene den fant, høyst 10 000) og `truncated`; en tekst i en
  rad kuttes ved 1 000 tegn.
- `get_publication` (scopet `mcp`): om en versjon er publisert, og i så fall
  `published_at`, `published_by`, `file_name`, `size_in_bytes` og `sha256`, hver
  `null` så lenge den ikke er det; aldri hvor arkivet lastes ned.
- `start_clash_check` (scopet `mcp`): en [kollisjonskontroll](ifc-lpg.md#kollisjonskontroll)
  mellom to versjoner i et prosjekt: `project_id`, `a` og `b` med
  `document_id`, `version_index` og `types` (IFC-klasser, `null` for hvert
  element med en kropp), `mode` (`intersection` eller `clearance`), og
  `tolerance` og `clearance` i meter (`null` for 0,001 og 0,05). Det svarer
  `clash_id` og `state`, og revisjonsloggen noterer `mcp.clash.started`.
- `get_clash_check` (scopet `mcp`): rapporten for en kontroll, med `project_id`
  og `clash_id`, og venter høyst `wait_seconds` (høyst 20) på en som står i kø
  eller kjører: dens `state`, forespørselen, `count`, `set_a`, `set_b`,
  `missing`, `seconds` og høyst 200 `clashes`, med `truncated` når det fantes
  flere. Begge kollisjonsverktøyene avslår uten
  `OPENCDE_IFC_LPG_CLASH_ENABLED=true`.
  De tre vises bare mens IFC-LPG-modulen er på. En bruker har høyst to
  kontroller som venter eller kjører, i alle prosjektene sine til sammen; en
  tredje avslås, og revisjonsloggen fører `mcp.denied` med grunnen `limit`.

```json
{"name": "elements", "columns": ["global_id", "class", "name", "container"],
 "rows": [["1Xezbq735AdBO_4DerG66G", "IfcWallStandardCase", "YVT-A", "1. etasje"]],
 "count": 1, "truncated": false}
```

## Endringssettene

Mens IFC-LPG-modulen er slått på (`OPENCDE_IFC_LPG_ENABLED`), som prøver
endringssettene, har listen også verktøyene som foreslår endringer i en modell,
i Dataspatiums rekkefølge. De krever scopet `mcp:propose`, rollen `editor` eller
`manager` i prosjektet, prøvd ved hvert kall slik REST-API-et prøver den, og
prosjektets AI-policy; en avvist rolle blir `mcp.denied` med grunnen `role`.
Ingen verktøy godkjenner: det gjør en person, i Dataspatium.

- `open_changeset` (`document_id`, `version_index`, `null` for den siste):
  åpner et endringssett på en versjon av et IFC-dokument og svarer med dets
  `changeset_id`, dets `base`, `expires_at` og `max_steps` (200).
- Skriveverktøyene `create_storeys_and_grid`, `create_wall`, `create_slab`,
  `create_roof`, `create_opening`, `create_spaces`, `set_properties`,
  `set_classification`, `assign`, `transform_elements`, `delete_elements` (med
  `confirm: true`) og `set_site`: Dataspatiums egne, med dets skjemaer uendret og
  `changeset_id` først. Et kall er én operasjon i endringssettets `ops` i formen
  `dataspatium-tools/1`, nøyaktig slik appen lager den (standardverdiene fylt
  inn, tallene prøvd, tekstene kuttet ved 200 tegn), eller appens feil, som AI-en
  retter. En vegg, et dekke, et tak eller en åpning får en ref, `new-1`, `new-2` …,
  og det gjør hvert rom som `create_spaces` lister opp; et element nevnes ved sin
  GlobalId, sin STEP-id eller en ref.
- `manage_changeset` (`action`: `list`, `remove_last` eller `clear`): stegene med
  sine verktøy, refs og beskrivelser; det siste steget fjernet, med sine refs;
  eller ingen igjen.
- `change_attribute` (`guid` eller `step_id`, `path`, `attribute`, `op` `set`,
  `add` eller `remove`, `index`, `old`, `new`, `copy`): én attributt på én instans
  i basen, en post i endringssettets `changes` i skjemaets form; `old` prøves når
  endringssettet prøves.
- `propose_changes` (`title`; `description`, `null` for stegenes egne linjer;
  `ai_model`, det AI-en oppgir at den er): en BCF-sak i prosjektet med
  endringssettet som snippet, som serveren setter i kø for prøving. Proveniensen
  nevner brukeren, den oppgitte `ai_model` og `tool_call` `mcp:` med stegenes
  verktøy. Kalt igjen med samme håndtak legger det endringssettet slik det er da
  på samme sak og prøver det igjen. Svarer med `project_id`, `topic_guid`,
  `state` (`queued`) og hvor mange `ops` og `changes` endringssettet har.
- `get_proposal` (`project_id`, `topic_guid`, `wait_seconds` opp til 20; scopet
  `mcp`): prøven slik `GET …/ifc-proposal` gir den, med venting mens den er
  `queued` eller `running`, med høyst 50 anmerkninger, `created` (GlobalId for
  det operasjonene laget, etter sin ref) og `notes`.
- `list_proposals` (`document_id`, `limit` opp til 50; scopet `mcp`): forslagene
  mot et dokument, nyeste først, slik `GET …/ifc-proposals` lister dem, med
  `project_id` og uten adressene.

Flyten:

1. `list_models` gir dokumentet og dets siste versjon.
2. `open_changeset` gir håndtaket, og skriveverktøyene og `change_attribute`
   fyller endringssettet steg for steg; et steg som ble feil, rettes med
   `manage_changeset` `remove_last` og et nytt steg.
3. `propose_changes` lager forslaget, og `get_proposal` svarer `clean`, `issues`
   med anmerkningene eller `failed`. Ved anmerkninger retter AI-en
   endringssettet og foreslår det igjen.
4. Ved `clean` sier AI-en fra til personen, som godkjenner det i Dataspatium: en
   manager i prosjektet eller den ansvarlige for det ene teamet hvis del det
   berører.

```json
{"ok": true, "step": 1, "ref": "new-1",
 "description": "new-1 Wall New wall on the lowest storey from (0, 0) to (4, 0), 0.2 m thick, 3 m high"}
```

Det åpne endringssettet er et utkast på serveren, brukerens eget. Håndtaket er
et navn, ikke en tillatelse: hvert kall prøver at utkastet er den som kaller,
sitt, og ligger i et av prosjektene til den som kaller. Det lukkes 24 timer etter
siste bruk, og serveren sletter det; et ukjent eller lukket håndtak er en
verktøyfeil som ber om et nytt. En bruker har høyst 10 åpne, og et endringssett
høyst 200 steg.

## AI-policyen

Et prosjekts `ai_policy` er `local`, standardverdien, eller `cloud`, og settes av
prosjektets manager eller en administrator. Den lokale motoren betjener hvert
prosjekt, fordi datamaskinen er grensen. Enhver annen server lister ikke
`local`-prosjekter i det hele tatt, og spurt om ett, med id-en eller med et av
dokumentene, avslår et verktøy, og revisjonsloggen noterer `mcp.denied`.
Serveren holder styr på hvor dataene går; hvilken modell som leser dem, er
klientens valg, og et annet program på samme maskin kan likevel sende svarene
til en modell i skyen.

## Grenser og logger

- En kropp er høyst 1 MB og et svar høyst 256 kB, med høyst 500 rader fra en
  spørring og 200 kollisjoner; navn og titler kuttes ved 200 tegn og en tekst i
  radene fra en spørring ved 1 000. `get_clash_check` venter høyst 20 sekunder.
- En bruker gjør høyst 120 verktøykall i minuttet, uansett token, i tillegg til grensen per
  adresse som alle programmer deler (`OPENCDE_RATE_LIMIT_API`); utover den
  svarer verktøyet `isError` med hvor mange sekunder det må ventes.
- Forespørselsloggen beholder metoden og verktøyets navn, aldri kroppen.
  Revisjonsloggen beholder `mcp.denied` med grunnen (`policy`, `role`, `scope` eller `limit`) og
  `mcp.clash.started` med prosjektet, kontrollen og de to versjonene, hver med
  verktøyet og klienten, aldri et argument eller en tekst fra prosjektene.
- Revisjonsloggen beholder også `mcp.changeset.opened` og
  `mcp.changeset.proposed` med prosjektet, dokumentet, basen, endringssettet,
  saken, antallet operasjoner og endringer og den oppgitte AI-modellen, kuttet
  ved 100 tegn; aldri en tittel, en beskrivelse eller et steg.

## Data, aldri instruksjoner

Alt et verktøy returnerer, er data fra prosjektene: et navn, en tittel eller en
tekst fra IFC, BCF eller et dokument kommer tilbake som den er, i et navngitt
felt, uansett hva den sier. Verktøybeskrivelsene og serverens `instructions` er
faste tekster som sier det. En person godkjenner et forslag i Dataspatium,
innlogget der; et token for endepunktet når aldri en godkjenning eller en
publisering.
