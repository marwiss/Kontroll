# MCP-päätepiste (laajennus)

`POST /mcp`:n kautta Model Context Protocolia puhuvat tekoälyohjelmat (Claude,
ChatGPT, VS Code, Cursor ja paikallisten mallien asiakkaat) lukevat niiden
projektien IFC-malleja, joiden jäsen henkilö on, tämän henkilön nimissä. Tekoäly
ehdottaa ja ihminen hyväksyy: mikään työkalu ei hyväksy, julkaise, lataa,
yhdistä, poista eikä hallinnoi mitään (ADR 0028). Palvelin ei aja omaa
tekoälyä; ohjelma, sen malli ja sen budjetti ovat asiakkaan.

## Käyttöönotto

Päätepiste on pois päältä, kunnes `OPENCDE_MCP_ENABLED=true`. `opencde init --local`
ottaa sen käyttöön paikallisessa moottorissa, jossa `http://127.0.0.1:8000/mcp`
vastaa vain loopback-osoitteessa. Tiimipalvelimella se kulkee välityspalvelimen
kautta kuten API, https-yhteydellä. Kun se on päällä, kyvykkyysasiakirja
ilmoittaa sen nimellä `mcp` ([asiakasopas](client-guide.md), §1), ja
valtuutuspalvelin luettelee scopet `mcp` ja `mcp:propose`.

## Token päätepisteelle

Päätepiste ottaa vastaan vain sille myönnetyn tokenin, eikä mikään
REST-rajapinta ota vastaan sellaista tokenia:

1. Rekisteröi ohjelma asiakkaaksi, kuten mikä tahansa asiakas rekisteröidään:
   itse, kun `OPENCDE_DYNAMIC_CLIENT_REGISTRATION` on päällä (paikallinen
   moottori), tai ylläpitäjän toimesta.
2. Ohjelma löytää tien sisään itse: `/mcp`:n vastaus `401` nimeää osoitteen
   `/.well-known/oauth-protected-resource/mcp`, joka nimeää
   valtuutuspalvelimen, jonka metatiedot ovat osoitteessa
   `/.well-known/oauth-authorization-server`.
3. Se kirjaa henkilön sisään parametrilla `resource=<public_url>/mcp` ja
   scopella `mcp` (lukeminen). `mcp:propose`, muutosjoukkoja varten, pyydetään,
   kun työkalu tarvitsee sitä: `403 insufficient_scope` nimeää molemmat scopet.
   Suostumussivu kertoo, mitä ne antavat ja ettei niiden kautta hyväksytä eikä
   julkaista mitään.

[Asiakasopas](client-guide.md) (§2) kertoo sidonnan säännöt.

## Protokolla

Streamable HTTP, yksi JSON-vastaus pyyntöä kohden eikä SSE:tä. Versio
2026-07-28 on tilaton: jokainen pyyntö kantaa versionsa ja asiakkaan
kyvykkyydet `_meta`-kentässä, ja otsakkeet `MCP-Protocol-Version`, `Mcp-Method`
ja `Mcp-Name` toistavat sen, mitä runko sanoo. Sen metodit ovat
`server/discover`, `tools/list` ja `tools/call`; tulokset kantavat `resultType`
-kentän, ja löytäminen ja työkalujen luettelo kentät `ttlMs` (tunti) ja
`cacheScope` (`private`). Versiot 2025-11-25, 2025-06-18 ja 2025-03-26 saavat
myös `initialize`- ja `ping`-metodit, ilman istuntoa: palvelin ei koskaan luo
`Mcp-Session-Id`:tä, ja jokaiseen kutsuun vastataan erikseen. Pyyntö ilman
`MCP-Protocol-Version`-otsaketta on versiota 2025-03-26.

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

| Vastaus | Milloin |
|---|---|
| `400`, `-32700` tai `-32600` | Runko ei ole JSONia, on erä (batch) tai ei ole yksi JSON-RPC-pyyntö tai -ilmoitus |
| `400`, `-32602` | `_meta`-kentästä puuttuu versio tai kyvykkyydet; tuntematon työkalu; argumentit, jotka eivät ole objekti |
| `400`, `-32020` | Otsake ei sano samaa kuin runko, tai se puuttuu tai on annettu kahdesti |
| `400`, `-32022` | Versio, johon päätepiste ei vastaa; `data` nimeää ne, joihin se vastaa |
| `404`, `-32601` | Metodi, jota päätepisteellä ei ole |
| `202` | Ilmoitus (notification) |
| `401`, `403` | Ei päätepisteeseen sidottua tokenia, tai työkalun scope puuttuu |
| `403` | `Origin`, joka ei ole palvelimen oma eikä mainittu asetuksessa `OPENCDE_CORS_ORIGINS`; `null` ja `*` eivät kelpaa |
| `405` | `GET`, `DELETE` ja jokainen metodi paitsi `POST` |
| `413` | Yli 1 Mt:n runko |

Kättelyversiot vastaavat pyynnön virheisiin koodilla `200`, kuten niiden
palvelimet tekivät. `/mcp`:llä ei ole CORSia: mikään selain ei tarvitse sitä.

## Työkalut

Jokainen argumentti on pakollinen, ja `null` tarkoittaa "ei annettu". Hylkäys
(projekti, joka ei ole kutsujan, tekoälykäytäntö, argumentit, joita työkalu ei
ota) on työkalun tulos, jossa `isError: true` ja jonka tekoäly voi lukea;
vastaus on `structuredContent` ja sama JSON tekstinä.

- `list_models` (scope `mcp`): yksi rivi jokaista henkilön projektien
  IFC-asiakirjaa kohden, tai yhden `project_id`:n: `project_id`,
  `project_name`, henkilön `role`, projektin `ai_policy`, `document_id`,
  viimeisimmän version `title` ja `file_name`, sen `version_index`, sen
  `model_state` (`done`, kun mallia voi kysyä, `queued`, `running` tai `failed`,
  `null` ilman mallia) ja sen IFC-`schema`. Enintään 200 riviä, ja `truncated`,
  kun niitä oli enemmän.

```json
{"models": [{"project_id": "…", "project_name": "Building permit", "role": "editor", "ai_policy": "cloud",
             "document_id": "…", "title": "Walls", "file_name": "walls.ifc", "version_index": 2,
             "model_state": "done", "schema": "IFC4"}],
 "truncated": false}
```

- `server_query` (scope `mcp`): version mallin [nimetyt kyselyt](ifc-lpg.md#nimetyt-kyselyt)
  tunnisteilla `document_id` ja `version_index` (`null` viimeisimmälle), kuten
  Documents API ne kysyy. `name` on yksi palvelimen luettelon kyselyistä, ja
  kukin niiden parametreista on oma kenttänsä (`class`, `pset`, `property`,
  `global_id`, `since`); työkalun kuvaus luettelee kyselyt parametreineen, joten
  kysely, jonka IFC-LPG lisää, näkyy, kun palvelin on päivitetty. `name: null`
  luettelee ne mallin `model_state`- ja `workcopy`-tietojen kanssa. Kysely
  vastaa `name`, `columns`, enintään 500 `rows`, `count` (rivit, jotka se löysi,
  enintään 10 000) ja `truncated`; rivin teksti katkaistaan 1 000 merkkiin.
- `get_publication` (scope `mcp`): onko versio julkaistu, ja jos on,
  `published_at`, `published_by`, `file_name`, `size_in_bytes` ja `sha256`,
  kukin `null` niin kauan kuin se ei ole; ei koskaan sitä, mistä arkisto
  ladataan.
- `start_clash_check` (scope `mcp`): projektin kahden version
  [törmäystarkastus](ifc-lpg.md#törmäystarkastus): `project_id`, `a` ja `b`,
  joissa `document_id`, `version_index` ja `types` (IFC-luokat, `null` jokaiselle
  elementille, jolla on kappale), `mode` (`intersection` tai `clearance`) sekä
  `tolerance` ja `clearance` metreinä (`null` arvoille 0,001 ja 0,05). Se vastaa
  `clash_id` ja `state`, ja tarkastusloki kirjaa `mcp.clash.started`.
- `get_clash_check` (scope `mcp`): tarkastuksen raportti tunnisteilla
  `project_id` ja `clash_id`; se odottaa enintään `wait_seconds` (korkeintaan
  20) tarkastusta, joka on jonossa tai käynnissä: sen `state`, pyyntö, `count`,
  `set_a`, `set_b`, `missing`, `seconds` ja enintään 200 `clashes`, ja
  `truncated`, kun niitä oli enemmän. Kumpikin törmäystyökalu kieltäytyy, ellei
  `OPENCDE_IFC_LPG_CLASH_ENABLED=true`.

```json
{"name": "elements", "columns": ["global_id", "class", "name", "container"],
 "rows": [["1Xezbq735AdBO_4DerG66G", "IfcWallStandardCase", "YVT-A", "1. etasje"]],
 "count": 1, "truncated": false}
```

## Tekoälykäytäntö

Projektin `ai_policy` on `local`, oletusarvo, tai `cloud`, ja sen asettaa
projektin manager tai ylläpitäjä. Paikallinen moottori palvelee jokaista
projektia, koska tietokone on raja. Mikä tahansa muu palvelin ei luettele
`local`-projekteja lainkaan, ja kun sellaista kysytään sen tunnisteella tai
jollakin sen asiakirjoista, työkalu kieltäytyy ja tarkastusloki kirjaa
`mcp.denied`. Palvelin pitää huolen siitä, minne tiedot menevät; se, mikä malli
niitä lukee, on asiakkaan valinta, ja toinen ohjelma samalla tietokoneella voi
silti lähettää vastaukset pilvessä olevalle mallille.

## Rajat ja lokit

- Runko on enintään 1 Mt ja vastaus enintään 256 kt, ja siinä on enintään 500
  kyselyn riviä ja 200 törmäystä; nimet ja otsikot katkaistaan 200 merkkiin ja
  kyselyn rivien teksti 1 000 merkkiin. `get_clash_check` odottaa enintään 20
  sekuntia.
- Token tekee enintään 120 työkalukutsua minuutissa, osoitekohtaisen rajan
  lisäksi, jonka kaikki ohjelmat jakavat (`OPENCDE_RATE_LIMIT_API`); sen jälkeen
  työkalu vastaa `isError` ja kertoo, montako sekuntia on odotettava.
- Pyyntöloki säilyttää metodin ja työkalun nimen, ei koskaan runkoa.
  Tarkastusloki säilyttää `mcp.denied`-tapahtuman syineen (`policy` tai
  `scope`) ja `mcp.clash.started`-tapahtuman projekteineen, tarkastuksineen ja
  sen kahdella versiolla, kumpikin työkalun ja asiakkaan kanssa, ei koskaan
  argumenttia eikä projektien tekstiä.

## Dataa, ei koskaan ohjeita

Kaikki, mitä työkalu palauttaa, on projektien dataa: nimi, otsikko tai teksti
IFC:stä, BCF:stä tai asiakirjasta palaa sellaisenaan nimettyyn kenttään, sanoi
se mitä tahansa. Työkalujen kuvaukset ja palvelimen `instructions` ovat kiinteitä
tekstejä, jotka sanovat tämän. Henkilö hyväksyy ehdotuksen Dataspatiumissa,
sinne kirjautuneena; päätepisteen token ei koskaan ulotu hyväksyntään tai
julkaisuun.
