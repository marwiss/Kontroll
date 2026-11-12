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

## AI-policyen

Et prosjekts `ai_policy` er `local`, standardverdien, eller `cloud`, og settes av
prosjektets manager eller en administrator. Den lokale motoren betjener hvert
prosjekt, fordi datamaskinen er grensen. Enhver annen server lister ikke
`local`-prosjekter i det hele tatt, og spurt om ett med id-en avslår verktøyet,
og revisjonsloggen noterer `mcp.denied`. Serveren holder styr på hvor dataene
går; hvilken modell som leser dem, er klientens valg, og et annet program på
samme maskin kan likevel sende svarene til en modell i skyen.

## Grenser og logger

- En kropp er høyst 1 MB og et svar høyst 256 kB; navn og titler kuttes ved 200
  tegn.
- Et token gjør høyst 120 verktøykall i minuttet, i tillegg til grensen per
  adresse som alle programmer deler (`OPENCDE_RATE_LIMIT_API`); utover den
  svarer verktøyet `isError` med hvor mange sekunder det må ventes.
- Forespørselsloggen beholder metoden og verktøyets navn, aldri kroppen.
  Revisjonsloggen beholder `mcp.denied` med grunnen (`policy` eller `scope`),
  verktøyet og klienten, aldri et argument eller en tekst fra prosjektene.

## Data, aldri instruksjoner

Alt et verktøy returnerer, er data fra prosjektene: et navn, en tittel eller en
tekst fra IFC, BCF eller et dokument kommer tilbake som den er, i et navngitt
felt, uansett hva den sier. Verktøybeskrivelsene og serverens `instructions` er
faste tekster som sier det. En person godkjenner et forslag i Dataspatium,
innlogget der; et token for endepunktet når aldri en godkjenning eller en
publisering.
