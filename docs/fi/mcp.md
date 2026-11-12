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
  Nämä kolme näkyvät luettelossa vain, kun IFC-LPG-moduuli on päällä.
  Käyttäjällä voi olla enintään kaksi odottavaa tai käynnissä olevaa
  tarkastusta kaikissa projekteissaan yhteensä; kolmas torjutaan, ja
  tarkastusloki kirjaa `mcp.denied`-tapahtuman syyllä `limit`.

```json
{"name": "elements", "columns": ["global_id", "class", "name", "container"],
 "rows": [["1Xezbq735AdBO_4DerG66G", "IfcWallStandardCase", "YVT-A", "1. etasje"]],
 "count": 1, "truncated": false}
```

## Muutosjoukot

Kun IFC-LPG-moduuli on käytössä (`OPENCDE_IFC_LPG_ENABLED`) ja kokeilee
muutosjoukot, luettelossa ovat myös työkalut, jotka ehdottavat muutoksia
malliin, Dataspatiumin järjestyksessä. Ne vaativat scopen `mcp:propose`, roolin
`editor` tai `manager` projektissa, tarkistettuna jokaisessa kutsussa kuten
REST-API tarkistaa sen, ja projektin tekoälykäytännön; hylätty rooli kirjataan
`mcp.denied`-tapahtumaksi syynä `role`. Mikään työkalu ei hyväksy: sen tekee
henkilö, Dataspatiumissa.

- `open_changeset` (`document_id`, `version_index`, `null` uusimmalle): avaa
  muutosjoukon IFC-dokumentin versioon ja vastaa sen `changeset_id`:llä,
  `base`:lla, `expires_at`:lla ja `max_steps`:llä (200).
- Kirjoitustyökalut `create_storeys_and_grid`, `create_wall`, `create_slab`,
  `create_roof`, `create_opening`, `create_spaces`, `set_properties`,
  `set_classification`, `assign`, `transform_elements`, `delete_elements`
  (`confirm: true` -arvolla) ja `set_site`: Dataspatiumin omat, sen skeemat
  muuttamattomina ja `changeset_id` ensimmäisenä. Kutsu on yksi operaatio
  muutosjoukon `ops`-luettelossa muodossa `dataspatium-tools/1` täsmälleen
  niin kuin sovellus sen tekee (oletusarvot täytettyinä, luvut tarkistettuina,
  tekstit katkaistuina 200 merkkiin), tai sovelluksen virhe, jonka tekoäly
  korjaa. Seinä, laatta, katto tai aukko saa refin, `new-1`, `new-2` …, samoin
  jokainen huone, jonka `create_spaces` luettelee; elementti nimetään
  GlobalId:llä, STEP-id:llä tai refillä.
- `manage_changeset` (`action`: `list`, `remove_last` tai `clear`): vaiheet
  työkaluineen, refeineen ja kuvauksineen; viimeinen vaihe poistettuna refeineen;
  tai ei yhtään jäljellä.
- `change_attribute` (`guid` tai `step_id`, `path`, `attribute`, `op` `set`,
  `add` tai `remove`, `index`, `old`, `new`, `copy`): yksi perustan instanssin
  attribuutti, muutosjoukon `changes`-luettelon kohta skeeman muodossa; `old`
  tarkistetaan, kun muutosjoukkoa kokeillaan.
- `propose_changes` (`title`; `description`, `null` vaiheiden omille riveille;
  `ai_model`, mikä tekoäly ilmoittaa olevansa): BCF-asia projektissa, jonka
  snippet on muutosjoukko ja jonka kokeilun palvelin asettaa jonoon. Sen alkuperä
  nimeää käyttäjän, ilmoitetun `ai_model`:n ja `tool_call`:n `mcp:` vaiheiden
  työkaluineen. Kun se kutsutaan uudelleen samalla kahvalla, se panee
  muutosjoukon sellaisena kuin se silloin on samaan asiaan ja kokeilee sen
  uudelleen. Vastaa `project_id`:llä, `topic_guid`:lla, `state`:lla (`queued`)
  ja sillä, montako `ops`- ja `changes`-kohtaa muutosjoukossa on.
- `get_proposal` (`project_id`, `topic_guid`, `wait_seconds` enintään 20; scope
  `mcp`): kokeilu niin kuin `GET …/ifc-proposal` sen antaa, odottaen sen ollessa
  `queued` tai `running`, enintään 50 huomautusta, `created` (operaatioiden
  luomien GlobalId:t refin mukaan) ja `notes`.
- `list_proposals` (`document_id`, `limit` enintään 50; scope `mcp`): dokumenttia
  koskevat ehdotukset, uusin ensin, niin kuin `GET …/ifc-proposals` ne
  luettelee, `project_id`:n kanssa ja ilman osoitteita.

Kulku:

1. `list_models` antaa dokumentin ja sen uusimman version.
2. `open_changeset` antaa kahvan, ja kirjoitustyökalut ja `change_attribute`
   täyttävät muutosjoukon vaihe vaiheelta; väärin mennyt vaihe korjataan
   `manage_changeset`-työkalun `remove_last`-toiminnolla ja uudella vaiheella.
3. `propose_changes` tekee ehdotuksen, ja `get_proposal` vastaa `clean`,
   `issues` huomautuksineen tai `failed`. Huomautusten kanssa tekoäly korjaa
   muutosjoukon ja ehdottaa sitä uudelleen.
4. Tilassa `clean` tekoäly kertoo henkilölle, joka hyväksyy sen Dataspatiumissa:
   projektin manager tai sen ainoan tiimin vastuuhenkilö, jonka osaa se koskee.

```json
{"ok": true, "step": 1, "ref": "new-1",
 "description": "new-1 Wall New wall on the lowest storey from (0, 0) to (4, 0), 0.2 m thick, 3 m high"}
```

Avoin muutosjoukko on luonnos palvelimella, käyttäjän oma. Sen kahva on nimi,
ei oikeus: jokainen kutsu tarkistaa, että luonnos on kutsujan ja jossakin
kutsujan projekteista. Se sulkeutuu 24 tuntia viimeisen käytön jälkeen, ja
palvelin poistaa sen; tuntematon tai suljettu kahva on työkaluvirhe, joka pyytää
uutta. Käyttäjällä on enintään 10 avointa, ja muutosjoukossa enintään 200
vaihetta.

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
- Käyttäjä tekee enintään 120 työkalukutsua minuutissa tokenista riippumatta, osoitekohtaisen rajan
  lisäksi, jonka kaikki ohjelmat jakavat (`OPENCDE_RATE_LIMIT_API`); sen jälkeen
  työkalu vastaa `isError` ja kertoo, montako sekuntia on odotettava.
- Pyyntöloki säilyttää metodin ja työkalun nimen, ei koskaan runkoa.
  Tarkastusloki säilyttää `mcp.denied`-tapahtuman syineen (`policy`, `role`,
  `scope` tai `limit`) ja `mcp.clash.started`-tapahtuman projekteineen, tarkastuksineen ja
  sen kahdella versiolla, kumpikin työkalun ja asiakkaan kanssa, ei koskaan
  argumenttia eikä projektien tekstiä.
- Tarkastusloki säilyttää myös `mcp.changeset.opened`- ja
  `mcp.changeset.proposed`-tapahtumat projektin, dokumentin, perustan,
  muutosjoukon, asian, operaatioiden ja muutosten määrän sekä ilmoitetun
  tekoälymallin kanssa, katkaistuna 100 merkkiin; ei koskaan otsikkoa, kuvausta
  eikä vaihetta.

## Dataa, ei koskaan ohjeita

Kaikki, mitä työkalu palauttaa, on projektien dataa: nimi, otsikko tai teksti
IFC:stä, BCF:stä tai asiakirjasta palaa sellaisenaan nimettyyn kenttään, sanoi
se mitä tahansa. Työkalujen kuvaukset ja palvelimen `instructions` ovat kiinteitä
tekstejä, jotka sanovat tämän. Henkilö hyväksyy ehdotuksen Dataspatiumissa,
sinne kirjautuneena; päätepisteen token ei koskaan ulotu hyväksyntään tai
julkaisuun.
