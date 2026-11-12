# MCP-endapunkturinn (viðbót)

Í gegnum `POST /mcp` lesa gervigreindarforrit sem tala Model Context Protocol
(Claude, ChatGPT, VS Code, Cursor og biðlarar staðbundinna líkana) IFC-líkön
þeirra verkefna sem manneskja er meðlimur í, í nafni hennar. Gervigreindin
leggur til og manneskja samþykkir: ekkert verkfæri samþykkir, birtir, hleður
upp, sameinar, eyðir eða stjórnar neinu (ADR 0028). Þjónninn keyrir enga eigin
gervigreind; forritið, líkan þess og fjárhagsrammi eru biðlarans.

## Að kveikja á honum

Endapunkturinn er óvirkur þar til `OPENCDE_MCP_ENABLED=true`. `opencde init --local`
kveikir á honum í staðbundnu vélinni, þar sem `http://127.0.0.1:8000/mcp`
svarar aðeins á loopback. Á teymisþjóni fer hann um milliþjóninn eins og API-ið,
með https. Meðan hann er virkur tilkynnir getuskjalið hann sem `mcp`
([biðlaraleiðbeiningarnar](client-guide.md), §1), og heimildaþjónninn telur upp
heimildirnar `mcp` og `mcp:propose`.

## Tóki fyrir endapunktinn

Endapunkturinn tekur aðeins við tóka sem gefinn er út fyrir hann, og engin
REST-forritaskil taka við slíkum tóka:

1. Skráðu forritið sem biðlara, eins og hver biðlari er skráður: sjálft, þar sem
   `OPENCDE_DYNAMIC_CLIENT_REGISTRATION` er virkt (staðbundna vélin), eða af
   stjórnanda.
2. Forritið finnur leiðina inn sjálft: `401` frá `/mcp` nefnir
   `/.well-known/oauth-protected-resource/mcp`, sem nefnir heimildaþjóninn, en
   lýsigögn hans eru á `/.well-known/oauth-authorization-server`.
3. Það skráir manneskjuna inn með `resource=<public_url>/mcp` og heimildinni
   `mcp` (lestur). Beðið er um `mcp:propose`, fyrir breytingasöfnin, þegar
   verkfæri þarf hana: `403 insufficient_scope` nefnir báðar heimildirnar.
   Samþykkissíðan segir hvað þær veita og að ekkert sé samþykkt eða birt í
   gegnum þær.

[Biðlaraleiðbeiningarnar](client-guide.md) (§2) hafa reglur bindingarinnar.

## Samskiptareglan

Streamable HTTP með einu JSON-svari á hverja beiðni og engu SSE. Útgáfa
2026-07-28 er ástandslaus: hver beiðni ber útgáfu sína og getu biðlarans í
`_meta`, og hausarnir `MCP-Protocol-Version`, `Mcp-Method` og `Mcp-Name`
endurtaka það sem meginmálið segir. Aðferðir hennar eru `server/discover`,
`tools/list` og `tools/call`; niðurstöðurnar bera `resultType`, og uppgötvunin
og listinn yfir verkfæri `ttlMs` (ein klukkustund) og `cacheScope` (`private`).
Útgáfurnar 2025-11-25, 2025-06-18 og 2025-03-26 fá líka `initialize` og `ping`,
án lotu: þjónninn býr aldrei til `Mcp-Session-Id`, og hverju kalli er svarað
fyrir sig. Beiðni án `MCP-Protocol-Version` er af útgáfu 2025-03-26.

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

| Svar | Hvenær |
|---|---|
| `400`, `-32700` eða `-32600` | Meginmálið er ekki JSON, er runa (batch) eða er ekki ein JSON-RPC-beiðni eða -tilkynning |
| `400`, `-32602` | Í `_meta` vantar útgáfuna eða getuna; óþekkt verkfæri; færibreytur sem eru ekki hlutur |
| `400`, `-32020` | Haus segir ekki það sem meginmálið segir, eða vantar eða er gefinn tvisvar |
| `400`, `-32022` | Útgáfa sem endapunkturinn svarar ekki; `data` nefnir þær sem hann svarar |
| `404`, `-32601` | Aðferð sem endapunkturinn hefur ekki |
| `202` | Tilkynning (notification) |
| `401`, `403` | Enginn tóki bundinn endapunktinum, eða heimild verkfæris vantar |
| `403` | `Origin` sem er hvorki uppruni þjónsins sjálfs né nefndur í `OPENCDE_CORS_ORIGINS`; `null` og `*` teljast ekki með |
| `405` | `GET`, `DELETE` og hver aðferð nema `POST` |
| `413` | Meginmál sem er stærra en 1 MB |

Handabandsútgáfurnar svara villum beiðni með `200`, eins og þjónar þeirra
gerðu. `/mcp` hefur ekkert CORS: enginn vafri þarf á því að halda.

## Verkfærin

Hver færibreyta er nauðsynleg, og `null` merkir „ekki gefið“. Höfnun (verkefni
sem er ekki þess sem kallar, gervigreindarstefnan, færibreytur sem verkfærið
tekur ekki) er niðurstaða verkfæris með `isError: true` sem gervigreindin getur
lesið; svarið er `structuredContent` og sama JSON sem texti.

- `list_models` (heimildin `mcp`): ein lína á hvert IFC-skjal í verkefnum
  manneskjunnar, eða í einu `project_id`: `project_id`, `project_name`, `role`
  manneskjunnar, `ai_policy` verkefnisins, `document_id`, `title` og `file_name`
  nýjustu útgáfunnar, `version_index` hennar, `model_state` hennar (`done` þegar
  hægt er að spyrja líkanið, `queued`, `running` eða `failed`, `null` án líkans)
  og IFC-`schema` hennar. Í mesta lagi 200 línur, og `truncated` þegar þær voru
  fleiri.

```json
{"models": [{"project_id": "…", "project_name": "Building permit", "role": "editor", "ai_policy": "cloud",
             "document_id": "…", "title": "Walls", "file_name": "walls.ifc", "version_index": 2,
             "model_state": "done", "schema": "IFC4"}],
 "truncated": false}
```

- `server_query` (heimildin `mcp`): [nefndu fyrirspurnirnar](ifc-lpg.md#nefndar-fyrirspurnir)
  um líkan útgáfu, með `document_id` og `version_index` (`null` fyrir þá
  nýjustu), eins og Documents API spyr þeirra. `name` er ein af fyrirspurnunum í
  skrá þjónsins, og hver færibreyta þeirra er sérstakt svæði (`class`, `pset`,
  `property`, `global_id`, `since`); lýsing verkfærisins telur fyrirspurnirnar
  upp með færibreytum þeirra, svo fyrirspurn sem IFC-LPG bætir við birtist
  þegar þjónninn hefur verið uppfærður. `name: null` telur þær upp, með
  `model_state` og `workcopy` líkansins. Fyrirspurn svarar `name`, `columns`, í
  mesta lagi 500 `rows`, `count` (línunum sem hún fann, í mesta lagi 10.000) og
  `truncated`; texti í línu er styttur við 1.000 stafi.
- `get_publication` (heimildin `mcp`): hvort útgáfa er birt, og ef svo er
  `published_at`, `published_by`, `file_name`, `size_in_bytes` og `sha256`,
  hvert `null` meðan hún er það ekki; aldrei hvaðan safnskráin er sótt.
- `start_clash_check` (heimildin `mcp`): [árekstrarprófun](ifc-lpg.md#árekstrarprófun)
  milli tveggja útgáfna verkefnis: `project_id`, `a` og `b` með `document_id`,
  `version_index` og `types` (IFC-klasar, `null` fyrir hverja einingu með
  rúmmál), `mode` (`intersection` eða `clearance`), og `tolerance` og
  `clearance` í metrum (`null` fyrir 0,001 og 0,05). Það svarar `clash_id` og
  `state`, og endurskoðunarskráin skráir `mcp.clash.started`.
- `get_clash_check` (heimildin `mcp`): skýrsla prófunar, eftir `project_id` og
  `clash_id`, og bíður í mesta lagi `wait_seconds` (20 í mesta lagi) eftir
  prófun sem er í röð eða í gangi: `state` hennar, beiðnina, `count`, `set_a`,
  `set_b`, `missing`, `seconds` og í mesta lagi 200 `clashes`, með `truncated`
  þegar þeir voru fleiri. Bæði árekstrarverkfærin hafna nema
  `OPENCDE_IFC_LPG_CLASH_ENABLED=true`.

```json
{"name": "elements", "columns": ["global_id", "class", "name", "container"],
 "rows": [["1Xezbq735AdBO_4DerG66G", "IfcWallStandardCase", "YVT-A", "1. etasje"]],
 "count": 1, "truncated": false}
```

## Gervigreindarstefnan

`ai_policy` verkefnis er `local`, sjálfgefna gildið, eða `cloud`, og hana setur
manager verkefnisins eða stjórnandi. Staðbundna vélin þjónar hverju verkefni,
því tölvan er mörkin. Sérhver annar þjónn telur `local`-verkefni alls ekki upp,
og sé spurt um eitt, með auðkenni þess eða einu skjala þess, hafnar verkfæri og
endurskoðunarskráin skráir `mcp.denied`. Þjónninn gætir þess hvert gögnin fara;
hvaða líkan les þau er val biðlarans, og annað forrit á sömu tölvu getur samt
sent svörin til líkans í skýinu.

## Mörk og skrár

- Meginmál er í mesta lagi 1 MB og svar í mesta lagi 256 kB, með í mesta lagi
  500 línum úr fyrirspurn og 200 árekstrum; nöfn og titlar eru styttir við 200
  stafi og texti í línum fyrirspurnar við 1.000. `get_clash_check` bíður í mesta
  lagi 20 sekúndur.
- Tóki gerir í mesta lagi 120 verkfærisköll á mínútu, auk marka á hvert
  vistfang sem öll forrit deila (`OPENCDE_RATE_LIMIT_API`); umfram það svarar
  verkfærið `isError` með þeim sekúndum sem bíða þarf.
- Beiðnaskráin geymir aðferðina og heiti verkfærisins, aldrei meginmálið.
  Endurskoðunarskráin geymir `mcp.denied` með ástæðunni (`policy` eða `scope`)
  og `mcp.clash.started` með verkefninu, prófuninni og tveimur útgáfum hennar,
  hvort tveggja með verkfærinu og biðlaranum, aldrei færibreytu eða texta úr
  verkefnunum.

## Gögn, aldrei fyrirmæli

Allt sem verkfæri skilar eru gögn úr verkefnunum: nafn, titill eða texti úr IFC,
BCF eða skjali kemur til baka eins og hann er, í nefndu svæði, hvað sem hann
segir. Lýsingar verkfæranna og `instructions` þjónsins eru fastir textar sem
segja það. Manneskja samþykkir tillögu í Dataspatium, innskráð þar; tóki fyrir
endapunktinn nær aldrei til samþykktar eða birtingar.
