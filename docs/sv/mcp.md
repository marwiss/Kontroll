# MCP-ändpunkten (tillägg)

Genom `POST /mcp` läser AI-program som talar Model Context Protocol (Claude,
ChatGPT, VS Code, Cursor och klienterna för lokala modeller) IFC-modellerna i de
projekt som en person är medlem i, i den personens namn. AI:n föreslår och en
människa godkänner: inget verktyg godkänner, publicerar, laddar upp, sammanfogar,
raderar eller administrerar något (ADR 0028). Servern kör ingen egen AI;
programmet, dess modell och dess budget är klientens.

## Att slå på den

Ändpunkten är avstängd tills `OPENCDE_MCP_ENABLED=true`. `opencde init --local`
slår på den i den lokala motorn, där `http://127.0.0.1:8000/mcp` bara svarar på
loopback. På en teamserver går den genom proxyn som API:t, med https. Medan den
är på tillkännager kapabilitetsdokumentet den som `mcp`
([klientguiden](client-guide.md), §1), och auktoriseringsservern listar scopen
`mcp` och `mcp:propose`.

## En token för ändpunkten

Ändpunkten tar bara en token som utfärdats för den, och inget REST-API tar en
sådan token:

1. Registrera programmet som klient, som varje klient registreras: själv, där
   `OPENCDE_DYNAMIC_CLIENT_REGISTRATION` är på (den lokala motorn), eller av en
   administratör.
2. Programmet hittar vägen in själv: `401` från `/mcp` nämner
   `/.well-known/oauth-protected-resource/mcp`, som nämner
   auktoriseringsservern, vars metadata finns på
   `/.well-known/oauth-authorization-server`.
3. Det loggar in personen med `resource=<public_url>/mcp` och scopet `mcp`
   (läsning). `mcp:propose`, för ändringsseten, begärs när ett verktyg behöver
   det: `403 insufficient_scope` nämner båda scopen. Samtyckessidan säger vad de
   ger och att inget godkänns eller publiceras genom dem.

[Klientguiden](client-guide.md) (§2) har reglerna för bindningen.

## Protokollet

Streamable HTTP med ett JSON-svar per begäran och ingen SSE. Revision 2026-07-28
är tillståndslös: varje begäran bär sin revision och klientens kapabiliteter i
`_meta`, och rubrikerna `MCP-Protocol-Version`, `Mcp-Method` och `Mcp-Name`
upprepar det som kroppen säger. Dess metoder är `server/discover`, `tools/list`
och `tools/call`; resultaten bär `resultType`, och upptäckten och listan över
verktyg `ttlMs` (en timme) och `cacheScope` (`private`). Revisionerna
2025-11-25, 2025-06-18 och 2025-03-26 får också `initialize` och `ping`, utan
session: servern gör aldrig något `Mcp-Session-Id`, och varje anrop besvaras för
sig. En begäran utan `MCP-Protocol-Version` är av revision 2025-03-26.

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

| Svar | När |
|---|---|
| `400`, `-32700` eller `-32600` | Kroppen är inte JSON, är en sats (batch) eller är inte en JSON-RPC-begäran eller -notifiering |
| `400`, `-32602` | `_meta` saknar revisionen eller kapabiliteterna; ett okänt verktyg; argument som inte är ett objekt |
| `400`, `-32020` | En rubrik säger inte det som kroppen säger, eller saknas eller ges två gånger |
| `400`, `-32022` | En revision som ändpunkten inte svarar på; `data` nämner dem den svarar på |
| `404`, `-32601` | En metod som ändpunkten inte har |
| `202` | En notifiering |
| `401`, `403` | Ingen token bunden till ändpunkten, eller ett verktygs scope saknas |
| `403` | En `Origin` som varken är serverns egen eller nämns i `OPENCDE_CORS_ORIGINS`; `null` och `*` räknas inte |
| `405` | `GET`, `DELETE` och varje metod utom `POST` |
| `413` | En kropp som är större än 1 MB |

Handskakningsrevisionerna besvarar felen i en begäran med `200`, som deras
servrar gjorde. `/mcp` har ingen CORS: ingen webbläsare behöver den.

## Verktygen

Varje argument krävs, och `null` betyder "inte angivet". Ett avslag (ett projekt
som inte är anroparens, AI-policyn, argument som verktyget inte tar) är ett
verktygsresultat med `isError: true` som AI:n kan läsa; svaret är
`structuredContent` och samma JSON som text.

- `list_models` (scopet `mcp`): en rad per IFC-dokument i personens projekt,
  eller i ett `project_id`: `project_id`, `project_name`, personens `role`,
  projektets `ai_policy`, `document_id`, den senaste versionens `title` och
  `file_name`, dess `version_index`, dess `model_state` (`done` när modellen kan
  frågas, `queued`, `running` eller `failed`, `null` utan modell) och dess
  IFC-`schema`. Högst 200 rader, och `truncated` när det fanns fler.

```json
{"models": [{"project_id": "…", "project_name": "Building permit", "role": "editor", "ai_policy": "cloud",
             "document_id": "…", "title": "Walls", "file_name": "walls.ifc", "version_index": 2,
             "model_state": "done", "schema": "IFC4"}],
 "truncated": false}
```

- `server_query` (scopet `mcp`): de [namngivna frågorna](ifc-lpg.md#namngivna-frågor)
  om en versions modell, med `document_id` och `version_index` (`null` för den
  senaste), som Documents API ställer dem. `name` är en av frågorna i serverns
  katalog, och var och en av deras parametrar är ett eget fält (`class`,
  `pset`, `property`, `global_id`, `since`); verktygets beskrivning räknar upp
  frågorna med deras parametrar, så att en fråga som IFC-LPG lägger till syns
  när servern har uppdaterats. `name: null` listar dem, med modellens
  `model_state` och `workcopy`. En fråga svarar `name`, `columns`, högst 500
  `rows`, `count` (raderna den hittade, högst 10 000) och `truncated`; en text i
  en rad kapas vid 1 000 tecken.
- `get_publication` (scopet `mcp`): om en version är publicerad, och i så fall
  `published_at`, `published_by`, `file_name`, `size_in_bytes` och `sha256`,
  vart och ett `null` så länge den inte är det; aldrig var arkivet laddas ned.
- `start_clash_check` (scopet `mcp`): ett [krocktest](ifc-lpg.md#krocktest)
  mellan två versioner i ett projekt: `project_id`, `a` och `b` med
  `document_id`, `version_index` och `types` (IFC-klasser, `null` för varje
  element med en kropp), `mode` (`intersection` eller `clearance`), och
  `tolerance` och `clearance` i meter (`null` för 0,001 och 0,05). Det svarar
  `clash_id` och `state`, och granskningsloggen antecknar `mcp.clash.started`.
- `get_clash_check` (scopet `mcp`): rapporten för ett test, med `project_id` och
  `clash_id`, och väntar högst `wait_seconds` (som mest 20) på ett som är köat
  eller körs: dess `state`, begäran, `count`, `set_a`, `set_b`, `missing`,
  `seconds` och högst 200 `clashes`, med `truncated` när det fanns fler. Båda
  krockverktygen vägrar om inte `OPENCDE_IFC_LPG_CLASH_ENABLED=true`.
  De tre listas bara när IFC-LPG-modulen är på. En användare har högst två
  krocktester som väntar eller körs, i alla sina projekt tillsammans; ett tredje
  vägras, och granskningsloggen antecknar `mcp.denied` med skälet `limit`.

```json
{"name": "elements", "columns": ["global_id", "class", "name", "container"],
 "rows": [["1Xezbq735AdBO_4DerG66G", "IfcWallStandardCase", "YVT-A", "1. etasje"]],
 "count": 1, "truncated": false}
```

## Ändringsseten

Medan IFC-LPG-modulen är på (`OPENCDE_IFC_LPG_ENABLED`), som prövar
ändringsseten, har listan också verktygen som föreslår ändringar i en modell, i
Dataspatiums ordning. De kräver scopet `mcp:propose`, rollen `editor` eller
`manager` i projektet, prövad vid varje anrop som REST-API:t prövar den, och
projektets AI-policy; en roll som vägras blir `mcp.denied` med skälet `role`.
Inget verktyg godkänner: en person gör det, i Dataspatium.

- `open_changeset` (`document_id`, `version_index`, `null` för den senaste):
  öppnar ett ändringsset på en version av ett IFC-dokument och svarar med dess
  `changeset_id`, dess `base`, `expires_at` och `max_steps` (200).
- Skrivverktygen `create_storeys_and_grid`, `create_wall`, `create_slab`,
  `create_roof`, `create_opening`, `create_spaces`, `set_properties`,
  `set_classification`, `assign`, `transform_elements`, `delete_elements` (med
  `confirm: true`) och `set_site`: Dataspatiums egna, med dess scheman oförändrade
  och `changeset_id` först. Ett anrop är en operation i ändringssetets `ops` i
  formen `dataspatium-tools/1`, precis som appen gör den (standardvärdena
  ifyllda, talen prövade, texterna kapade vid 200 tecken), eller appens fel, som
  AI:n rättar. En vägg, ett bjälklag, ett tak eller en öppning får en ref,
  `new-1`, `new-2` …, liksom varje rum som `create_spaces` räknar upp; ett element
  nämns med sitt GlobalId, sitt STEP-id eller en ref.
- `manage_changeset` (`action`: `list`, `remove_last` eller `clear`): stegen med
  sina verktyg, refs och beskrivningar; det sista steget borttaget, med sina
  refs; eller inga kvar.
- `change_attribute` (`guid` eller `step_id`, `path`, `attribute`, `op` `set`,
  `add` eller `remove`, `index`, `old`, `new`, `copy`): ett attribut på en instans
  i basen, en post i ändringssetets `changes` i schemats form; `old` prövas när
  ändringssetet prövas.
- `propose_changes` (`title`; `description`, `null` för stegens egna rader;
  `ai_model`, det AI:n uppger att den är): ett BCF-ärende i projektet med
  ändringssetet som snippet, vars prövning servern köar. Dess proveniens nämner
  användaren, den uppgivna `ai_model` och `tool_call` `mcp:` med stegens verktyg.
  Anropat igen med samma handtag lägger det ändringssetet som det är då på samma
  ärende och prövar det igen. Svarar med `project_id`, `topic_guid`, `state`
  (`queued`) och hur många `ops` och `changes` ändringssetet har.
- `get_proposal` (`project_id`, `topic_guid`, `wait_seconds` upp till 20; scopet
  `mcp`): prövningen som `GET …/ifc-proposal` ger den, med väntan medan den är
  `queued` eller `running`, med högst 50 fynd, `created` (GlobalId för det
  operationerna skapade, efter dess ref) och `notes`.
- `list_proposals` (`document_id`, `limit` upp till 50; scopet `mcp`): förslagen
  mot ett dokument, nyaste först, som `GET …/ifc-proposals` listar dem, med
  `project_id` och utan adresserna.

Flödet:

1. `list_models` ger dokumentet och dess senaste version.
2. `open_changeset` ger handtaget, och skrivverktygen och `change_attribute`
   fyller ändringssetet steg för steg; ett steg som blev fel rättas med
   `manage_changeset` `remove_last` och ett nytt steg.
3. `propose_changes` gör förslaget, och `get_proposal` svarar `clean`, `issues`
   med fynden eller `failed`. Vid fynd rättar AI:n ändringssetet och föreslår det
   igen.
4. Vid `clean` säger AI:n till personen, som godkänner det i Dataspatium: en
   manager i projektet, eller den ansvarige för det enda team vars del det rör.

```json
{"ok": true, "step": 1, "ref": "new-1",
 "description": "new-1 Wall New wall on the lowest storey from (0, 0) to (4, 0), 0.2 m thick, 3 m high"}
```

Det öppna ändringssetet är ett utkast på servern, användarens eget. Dess handtag
är ett namn, inte en behörighet: varje anrop prövar att utkastet är den
anropandes och ligger i ett av den anropandes projekt. Det stängs 24 timmar
efter senaste användningen, och servern raderar det; ett okänt eller stängt
handtag är ett verktygsfel som ber om ett nytt. En användare har högst 10
öppna, och ett ändringsset högst 200 steg.

## AI-policyn

Ett projekts `ai_policy` är `local`, standardvärdet, eller `cloud`, och sätts av
projektets manager eller en administratör. Den lokala motorn betjänar varje
projekt, eftersom datorn är gränsen. Varje annan server listar inte
`local`-projekt alls, och tillfrågat om ett, med dess id eller med ett av dess
dokument, vägrar ett verktyg och granskningsloggen antecknar `mcp.denied`.
Servern håller var data tar vägen; vilken modell som läser dem är klientens val,
och ett annat program på samma dator kan ändå skicka svaren till en modell i
molnet.

## Gränser och loggar

- En kropp är högst 1 MB och ett svar högst 256 kB, med högst 500 rader ur en
  fråga och 200 krockar; namn och titlar kapas vid 200 tecken och en text i en
  frågas rader vid 1 000. `get_clash_check` väntar högst 20 sekunder.
- En användare gör högst 120 verktygsanrop i minuten, vilken token det än är, utöver gränsen per adress som
  alla program delar (`OPENCDE_RATE_LIMIT_API`); därutöver svarar verktyget
  `isError` med hur många sekunder som återstår att vänta.
- Begärandeloggen behåller metoden och verktygets namn, aldrig kroppen.
  Granskningsloggen behåller `mcp.denied` med skälet (`policy`, `role`, `scope` eller `limit`)
  och `mcp.clash.started` med projektet, testet och dess två versioner, var och
  en med verktyget och klienten, aldrig ett argument eller en text ur projekten.
- Granskningsloggen behåller också `mcp.changeset.opened` och
  `mcp.changeset.proposed`, med projektet, dokumentet, basen, ändringssetet,
  ärendet, antalet operationer och ändringar och den uppgivna AI-modellen, kapad
  vid 100 tecken; aldrig en titel, en beskrivning eller ett steg.

## Data, aldrig instruktioner

Allt som ett verktyg returnerar är data ur projekten: ett namn, en titel eller en
text ur IFC, BCF eller ett dokument kommer tillbaka som det är, i ett namngivet
fält, vad det än säger. Verktygsbeskrivningarna och serverns `instructions` är
fasta texter som säger det. En person godkänner ett förslag i Dataspatium,
inloggad där; en token för ändpunkten når aldrig ett godkännande eller en
publicering.
