# MCP-endepunktet (udvidelse)

Gennem `POST /mcp` læser AI-programmer, der taler Model Context Protocol (Claude,
ChatGPT, VS Code, Cursor og klienterne til lokale modeller), IFC-modellerne i de
projekter, som en person er medlem af, i personens navn. AI'en foreslår, og et
menneske godkender: intet værktøj godkender, publicerer, uploader, fletter,
sletter eller administrerer noget (ADR 0028). Serveren kører ingen egen AI;
programmet, dets model og dets budget er klientens.

## At slå det til

Endepunktet er slået fra, indtil `OPENCDE_MCP_ENABLED=true`. `opencde init --local`
slår det til i den lokale motor, hvor `http://127.0.0.1:8000/mcp` kun svarer på
loopback. På en teamserver går det gennem proxyen som API'et, med https. Mens det
er slået til, annoncerer kapabilitetsdokumentet det som `mcp`
([klientguiden](client-guide.md), §1), og autorisationsserveren lister scopes
`mcp` og `mcp:propose`.

## En token til endepunktet

Endepunktet tager kun en token, der er udstedt til det, og intet REST-API tager
sådan en token:

1. Registrér programmet som klient, som enhver klient registreres: selv, hvor
   `OPENCDE_DYNAMIC_CLIENT_REGISTRATION` er slået til (den lokale motor), eller
   af en administrator.
2. Programmet finder selv vejen ind: `401` fra `/mcp` nævner
   `/.well-known/oauth-protected-resource/mcp`, som nævner
   autorisationsserveren, hvis metadata findes på
   `/.well-known/oauth-authorization-server`.
3. Det logger personen ind med `resource=<public_url>/mcp` og scopet `mcp`
   (læsning). `mcp:propose`, til ændringssættene, bedes der om, når et værktøj
   har brug for det: `403 insufficient_scope` nævner begge scopes. Samtykkesiden
   siger, hvad de giver, og at intet godkendes eller publiceres gennem dem.

[Klientguiden](client-guide.md) (§2) har reglerne for bindingen.

## Protokollen

Streamable HTTP med ét JSON-svar pr. anmodning og ingen SSE. Revision 2026-07-28
er tilstandsløs: hver anmodning bærer sin revision og klientens kapabiliteter i
`_meta`, og headerne `MCP-Protocol-Version`, `Mcp-Method` og `Mcp-Name`
gentager det, som kroppen siger. Dens metoder er `server/discover`, `tools/list`
og `tools/call`; resultaterne bærer `resultType`, og opdagelsen og listen over
værktøjer `ttlMs` (en time) og `cacheScope` (`private`). Revisionerne
2025-11-25, 2025-06-18 og 2025-03-26 får også `initialize` og `ping`, uden
session: serveren laver aldrig et `Mcp-Session-Id`, og hvert kald besvares for
sig. En anmodning uden `MCP-Protocol-Version` er af revision 2025-03-26.

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

| Svar | Hvornår |
|---|---|
| `400`, `-32700` eller `-32600` | Kroppen er ikke JSON, er en batch eller er ikke én JSON-RPC-anmodning eller -notifikation |
| `400`, `-32602` | `_meta` mangler revisionen eller kapabiliteterne; et ukendt værktøj; argumenter, der ikke er et objekt |
| `400`, `-32020` | En header siger ikke det, som kroppen siger, eller mangler eller gives to gange |
| `400`, `-32022` | En revision, som endepunktet ikke svarer på; `data` nævner dem, det svarer på |
| `404`, `-32601` | En metode, som endepunktet ikke har |
| `202` | En notifikation |
| `401`, `403` | Ingen token bundet til endepunktet, eller et værktøjs scope mangler |
| `403` | En `Origin`, der hverken er serverens egen eller nævnt i `OPENCDE_CORS_ORIGINS`; `null` og `*` tæller ikke |
| `405` | `GET`, `DELETE` og enhver metode undtagen `POST` |
| `413` | En krop, der er større end 1 MB |

Håndtrykrevisionerne besvarer fejlene i en anmodning med `200`, som deres
servere gjorde. `/mcp` har ingen CORS: ingen browser har brug for den.

## Værktøjerne

Hvert argument er påkrævet, og `null` betyder "ikke angivet". Et afslag (et
projekt, der ikke er den kaldendes, AI-politikken, argumenter, som værktøjet ikke
tager) er et værktøjsresultat med `isError: true`, som AI'en kan læse; svaret er
`structuredContent` og den samme JSON som tekst.

- `list_models` (scopet `mcp`): én række pr. IFC-dokument i personens
  projekter, eller i ét `project_id`: `project_id`, `project_name`, personens
  `role`, projektets `ai_policy`, `document_id`, den seneste versions `title` og
  `file_name`, dens `version_index`, dens `model_state` (`done`, når modellen kan
  forespørges, `queued`, `running` eller `failed`, `null` uden model) og dens
  IFC-`schema`. Højst 200 rækker, og `truncated`, når der var flere.

```json
{"models": [{"project_id": "…", "project_name": "Building permit", "role": "editor", "ai_policy": "cloud",
             "document_id": "…", "title": "Walls", "file_name": "walls.ifc", "version_index": 2,
             "model_state": "done", "schema": "IFC4"}],
 "truncated": false}
```

- `server_query` (scopet `mcp`): de [navngivne forespørgsler](ifc-lpg.md#navngivne-forespørgsler)
  på en versions model, med `document_id` og `version_index` (`null` for den
  seneste), som Documents API stiller dem. `name` er en af forespørgslerne i
  serverens katalog, og hver af deres parametre er et felt for sig (`class`,
  `pset`, `property`, `global_id`, `since`); værktøjets beskrivelse opregner
  forespørgslerne med deres parametre, så en forespørgsel, som IFC-LPG tilføjer,
  viser sig, når serveren er opdateret. `name: null` lister dem, med modellens
  `model_state` og `workcopy`. En forespørgsel svarer `name`, `columns`, højst
  500 `rows`, `count` (de rækker, den fandt, højst 10.000) og `truncated`; en
  tekst i en række afkortes ved 1.000 tegn.
- `get_publication` (scopet `mcp`): om en version er publiceret, og i så fald
  `published_at`, `published_by`, `file_name`, `size_in_bytes` og `sha256`, hver
  `null`, så længe den ikke er det; aldrig hvor arkivet downloades.
- `start_clash_check` (scopet `mcp`): en [kollisionskontrol](ifc-lpg.md#kollisionskontrol)
  mellem to versioner i et projekt: `project_id`, `a` og `b` med `document_id`,
  `version_index` og `types` (IFC-klasser, `null` for hvert element med en
  krop), `mode` (`intersection` eller `clearance`), og `tolerance` og
  `clearance` i meter (`null` for 0,001 og 0,05). Det svarer `clash_id` og
  `state`, og revisionsloggen noterer `mcp.clash.started`.
- `get_clash_check` (scopet `mcp`): rapporten for en kontrol, med `project_id`
  og `clash_id`, og venter højst `wait_seconds` (højst 20) på en, der er i kø
  eller kører: dens `state`, anmodningen, `count`, `set_a`, `set_b`, `missing`,
  `seconds` og højst 200 `clashes`, med `truncated`, når der var flere. Begge
  kollisionsværktøjer afviser, medmindre `OPENCDE_IFC_LPG_CLASH_ENABLED=true`.

```json
{"name": "elements", "columns": ["global_id", "class", "name", "container"],
 "rows": [["1Xezbq735AdBO_4DerG66G", "IfcWallStandardCase", "YVT-A", "1. etasje"]],
 "count": 1, "truncated": false}
```

## Ændringssættene

Mens IFC-LPG-modulet er slået til (`OPENCDE_IFC_LPG_ENABLED`), som afprøver
ændringssættene, har listen også de værktøjer, der foreslår ændringer i en
model, i Dataspatiums rækkefølge. De kræver scopet `mcp:propose`, rollen
`editor` eller `manager` i projektet, prøvet ved hvert kald, som REST-API'et
prøver den, og projektets AI-politik; en afvist rolle bliver `mcp.denied` med
grunden `role`. Intet værktøj godkender: det gør en person, i Dataspatium.

- `open_changeset` (`document_id`, `version_index`, `null` for den seneste):
  åbner et ændringssæt på en version af et IFC-dokument og svarer med dets
  `changeset_id`, dets `base`, `expires_at` og `max_steps` (200).
- Skriveværktøjerne `create_storeys_and_grid`, `create_wall`, `create_slab`,
  `create_roof`, `create_opening`, `create_spaces`, `set_properties`,
  `set_classification`, `assign`, `transform_elements`, `delete_elements` (med
  `confirm: true`) og `set_site`: Dataspatiums egne, med dets skemaer uændrede og
  `changeset_id` først. Et kald er én operation i ændringssættets `ops` i formen
  `dataspatium-tools/1`, præcis som appen laver den (standardværdierne udfyldt,
  tallene prøvet, teksterne afkortet ved 200 tegn), eller appens fejl, som AI'en
  retter. En væg, et dæk, et tag eller en åbning får en ref, `new-1`, `new-2` …,
  og det gør hvert rum, som `create_spaces` opregner; et element nævnes ved sit
  GlobalId, sit STEP-id eller en ref.
- `manage_changeset` (`action`: `list`, `remove_last` eller `clear`): trinnene
  med deres værktøjer, refs og beskrivelser; det sidste trin fjernet, med dets
  refs; eller ingen tilbage.
- `change_attribute` (`guid` eller `step_id`, `path`, `attribute`, `op` `set`,
  `add` eller `remove`, `index`, `old`, `new`, `copy`): én attribut på én instans
  i basen, en post i ændringssættets `changes` i skemaets form; `old` prøves, når
  ændringssættet afprøves.
- `propose_changes` (`title`; `description`, `null` for trinnenes egne linjer;
  `ai_model`, det AI'en oplyser, at den er): en BCF-sag i projektet med
  ændringssættet som snippet, hvis afprøvning serveren sætter i kø. Dets
  proveniens nævner brugeren, den oplyste `ai_model` og `tool_call` `mcp:` med
  trinnenes værktøjer. Kaldt igen med samme håndtag lægger det ændringssættet,
  som det er da, på samme sag og afprøver det igen. Svarer med `project_id`,
  `topic_guid`, `state` (`queued`) og hvor mange `ops` og `changes` ændringssættet
  har.
- `get_proposal` (`project_id`, `topic_guid`, `wait_seconds` op til 20; scopet
  `mcp`): prøven, som `GET …/ifc-proposal` giver den, med venten, mens den er
  `queued` eller `running`, med højst 50 anmærkninger, `created` (GlobalId for
  det, operationerne skabte, efter dets ref) og `notes`.
- `list_proposals` (`document_id`, `limit` op til 50; scopet `mcp`): forslagene
  mod et dokument, nyeste først, som `GET …/ifc-proposals` lister dem, med
  `project_id` og uden adresserne.

Forløbet:

1. `list_models` giver dokumentet og dets seneste version.
2. `open_changeset` giver håndtaget, og skriveværktøjerne og `change_attribute`
   fylder ændringssættet trin for trin; et trin, der blev forkert, rettes med
   `manage_changeset` `remove_last` og et nyt trin.
3. `propose_changes` laver forslaget, og `get_proposal` svarer `clean`, `issues`
   med anmærkningerne eller `failed`. Ved anmærkninger retter AI'en
   ændringssættet og foreslår det igen.
4. Ved `clean` siger AI'en det til personen, som godkender det i Dataspatium: en
   manager i projektet eller den ansvarlige for det ene team, hvis del det
   berører.

```json
{"ok": true, "step": 1, "ref": "new-1",
 "description": "new-1 Wall New wall on the lowest storey from (0, 0) to (4, 0), 0.2 m thick, 3 m high"}
```

Det åbne ændringssæt er et udkast på serveren, brugerens eget. Dets håndtag er
et navn, ikke en tilladelse: hvert kald prøver, at udkastet er den kaldendes og
ligger i et af den kaldendes projekter. Det lukkes 24 timer efter seneste brug,
og serveren sletter det; et ukendt eller lukket håndtag er en værktøjsfejl, der
beder om et nyt. En bruger har højst 10 åbne, og et ændringssæt højst 200 trin.

## AI-politikken

Et projekts `ai_policy` er `local`, standardværdien, eller `cloud` og sættes af
projektets manager eller en administrator. Den lokale motor betjener hvert
projekt, fordi computeren er grænsen. Enhver anden server lister slet ikke
`local`-projekter, og spurgt om et, med dets id eller med et af dets
dokumenter, afviser et værktøj, og revisionsloggen noterer `mcp.denied`.
Serveren holder styr på, hvor data går hen; hvilken model der læser dem, er
klientens valg, og et andet program på samme computer kan stadig sende svarene
til en model i skyen.

## Grænser og logge

- En krop er højst 1 MB og et svar højst 256 kB, med højst 500 rækker fra en
  forespørgsel og 200 kollisioner; navne og titler afkortes ved 200 tegn og en
  tekst i en forespørgsels rækker ved 1.000. `get_clash_check` venter højst 20
  sekunder.
- En token laver højst 120 værktøjskald i minuttet, ud over grænsen pr. adresse,
  som alle programmer deler (`OPENCDE_RATE_LIMIT_API`); derudover svarer
  værktøjet `isError` med det antal sekunder, der skal ventes.
- Forespørgselsloggen beholder metoden og værktøjets navn, aldrig kroppen.
  Revisionsloggen beholder `mcp.denied` med grunden (`policy`, `role`, `scope` eller `limit`) og
  `mcp.clash.started` med projektet, kontrollen og dens to versioner, hver med
  værktøjet og klienten, aldrig et argument eller en tekst fra projekterne.
- Revisionsloggen beholder også `mcp.changeset.opened` og
  `mcp.changeset.proposed` med projektet, dokumentet, basen, ændringssættet,
  sagen, antallet af operationer og ændringer og den oplyste AI-model, afkortet
  ved 100 tegn; aldrig en titel, en beskrivelse eller et trin.

## Data, aldrig instruktioner

Alt, hvad et værktøj returnerer, er data fra projekterne: et navn, en titel eller
en tekst fra IFC, BCF eller et dokument kommer tilbage, som den er, i et navngivet
felt, uanset hvad den siger. Værktøjsbeskrivelserne og serverens `instructions`
er faste tekster, der siger det. En person godkender et forslag i Dataspatium,
logget ind der; en token til endepunktet når aldrig en godkendelse eller en
publicering.
