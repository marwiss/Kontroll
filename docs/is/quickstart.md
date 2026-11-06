# Fljótleg byrjun: Kontroll og Dataspatium saman

Frá tómri tölvu að innskráningu í Kontroll úr Dataspatium, með máli sem er búið til í
þrívíddarsýn og sést í atvikaskrám þjónsins. Það tekur um tuttugu mínútur, mest fyrsta
smíðin. Fylgdu skrefunum í röð og notaðu vistföng og gáttir nákvæmlega eins og þau eru
skrifuð: nánast öll vandamál stafa af stillingu sem var sleppt eða öðru vistfangi.
[Bilanaleit](#bilanaleit) segir hvað þú gerir ef eitthvað fer úrskeiðis. Sama síða er í
safni Dataspatium; þeim tveimur er haldið eins.

## Það sem þú þarft

- Docker: Docker Desktop á Windows og macOS, Docker Engine með compose-viðbótinni á
  Linux. Það verður að vera í gangi: `docker version` svarar bæði fyrir biðlara og þjón.
- Git, eða frumkóða-ZIP úr
  [nýjustu útgáfu](https://github.com/marwiss/Kontroll/releases/latest) Kontroll í stað
  `git clone` hér á eftir.
- Python 3, sem lítinn staðbundinn vefþjón.
- Microsoft Edge, Google Chrome eða Firefox.
- Gáttirnar 8000, 7484, 7697 og 8080 lausar á tölvunni.

Ef þú hefur prófað Kontroll á þessari tölvu áður skaltu byrja á
[Byrjaðu aftur](#byrjaðu-aftur).

## 1. Ræstu Kontroll

```sh
git clone https://github.com/marwiss/Kontroll.git
cd Kontroll
cp .env.example .env
```

Í skipanaglugga Windows er `copy` notað í stað `cp`.

Opnaðu `.env` í textaritli. Línurnar fjórar hér á eftir eru þegar í skránni: breyttu þeim
þannig að þær líti svona út og vistaðu. Veldu eigið lykilorð, minnst 16 stafi, aðeins
bókstafi og tölustafi.

```ini
OPENCDE_GRAPH_PASSWORD=YourOwnPassword1234
OPENCDE_DYNAMIC_CLIENT_REGISTRATION=true
OPENCDE_REQUEST_LOG_ENABLED=true
OPENCDE_IFCGRAPH_ENABLED=true
```

| Lína | Hvað hún gerir | Án hennar |
|---|---|---|
| `OPENCDE_GRAPH_PASSWORD` | Lykilorð grafgagnagrunnsins | Styttra en 16 stafir: gagnagrunnurinn ræsist ekki |
| `OPENCDE_DYNAMIC_CLIENT_REGISTRATION` | Leyfir Dataspatium að skrá sig sjálft hjá þjóninum | Skref 3 stöðvast, og forritið biður um biðlaraauðkenni |
| `OPENCDE_REQUEST_LOG_ENABLED` | Vistar köll forritsins | Beiðnaskráin í skrefi 5 er áfram tóm |
| `OPENCDE_IFCGRAPH_ENABLED` | Gerir upphlaðin líkön að grafi | Ekkert graf í skrefi 5 |

Stillingarnar eru til að prófa Kontroll á eigin tölvu, ekki fyrir þjón sem aðrir nota.

Ræstu þjóninn og hladdu inn sýnigögnum:

```sh
docker compose -f compose.yaml -f compose.dev.yaml up -d --build --wait
docker compose -f compose.yaml -f compose.dev.yaml exec api opencde seed
```

Fyrri skipunin tekur nokkrar mínútur í fyrsta sinn og lýkur þegar þjónninn er í gangi. Sú
síðari býr til sýninotendur og verkefni og prentar lykilorð þeirra **einu sinni**: geymdu
lykilorð `admin` og `inspection_manager` núna. Láttu línurnar sem byrja á `client`
eiga sig; Dataspatium skráir eigin biðlara.

Athugaðu að það virki: <http://127.0.0.1:8000/readyz> svarar `"status":"ready"`. Skráðu
þig inn á <http://127.0.0.1:8000/signin> sem `admin` og opnaðu
<http://127.0.0.1:8000/admin/projects>, sem sýnir *Building permit* og
*Demolition permit*.

Þegar þú breytir `.env` síðar keyrir þú `up`-skipunina aftur. `docker compose restart`
les ekki skrána.

## 2. Ræstu Dataspatium

1. Sæktu `dataspatium-<version>.zip` úr
   [nýjustu útgáfu](https://github.com/marwiss/Dataspatium/releases/latest)
   og berðu SHA-256-summu hennar saman við þá í texta útgáfunnar (`Get-FileHash` í
   PowerShell, `shasum -a 256` á macOS og Linux).
2. Taktu ZIP-skrána upp í eigin möppu. Windows getur búið til möppu inni í möppunni; það
   sem skiptir máli er mappan þar sem `index.html` er beint.
3. Opnaðu skipanaglugga í þeirri möppu og ræstu vefþjón á gátt 8080:

   ```sh
   python -m http.server 8080 --bind 127.0.0.1
   ```

   Skipunin getur heitið `python3` á macOS og Linux og `py` á Windows. Hafðu gluggann
   opinn meðan þú notar forritið. Gefðu alltaf upp gáttina: án hennar tekur Python 8000, sem er gátt Kontroll.
4. Opnaðu <http://127.0.0.1:8080/>, skrifað nákvæmlega svona: þjónninn sendir vafrann til baka eftir innskráningu á `127.0.0.1`, ekki á `localhost`. Ekki tvísmella á `index.html`: opnað úr möppunni getur
   forritið ekki skráð sig sjálft. Forritið endurhleður sig einu sinni við fyrstu ræsingu.
5. Fyrsta ræsing spyr um tungumál: veldu eitt og ýttu á *Halda áfram á …*. Þessi síða
   notar íslensku heitin. Spjaldið *Velkomin í Dataspatium* býður námskeið: ýttu á
   *Ekki núna*.

## 3. Skráðu þig inn í Kontroll úr Dataspatium

1. Veldu haminn *Sækja*. Í vinstri dálki, undir *Bæta við uppsprettum*, velur þú
   *OpenCDE*.
2. Undir *Vistfang* skrifar þú `http://127.0.0.1:8000`. **Hafðu *Biðlaraauðkenni (client
   id)* og leyndarmálið tóm**: forritið skráir sig sjálft, jafnvel þótt textinn í
   glugganum tali um biðlaraauðkenni frá stjórnanda. Ýttu á *Bæta við uppsprettu*.
3. Forritið spyr *Leyfa netaðgang?* allt að þrisvar, einu sinni fyrir hvern tilgang. Hér
   varðar það aðeins þinn eigin þjón: ýttu á *Leyfa* í hvert sinn.
4. Uppsprettan opnast og birtist undir *Viðbættar uppsprettur*. Línan "Þjónn: Kontroll
   OpenCDE server <version>. Viðbætur: …" kemur úr getuskjali þjónsins og segir hvaða
   viðbætur eru virkar. Merkið *Krefst lykils* má hunsa: það sem þarf er innskráningin.
5. Ýttu á *Skrá inn*. Sprettigluggi opnast með innskráningarsíðu þjónsins. Ef vafrinn lokar
   á hann skaltu leyfa sprettiglugga fyrir `http://127.0.0.1:8080` og ýta aftur.
6. Skráðu þig inn sem `inspection_manager` með lykilorðinu úr skrefi 1 og ýttu á *Leyfa og
   skrá inn*. Ekki nota `admin`, sem er ekki í neinu verkefni. Glugginn lokast sjálfur, og
   uppsprettan segir *Innskráð sem Certified inspection manager*.
7. *Building permit* er þegar valið í listanum *Verkefni*.

Þú ert innskráð(ur) þar til síðan er endurhlaðin; ýttu þá aftur á *Skrá inn*. Uppsprettan
helst.

## 4. Búðu til mál úr þrívíddarsýninni

1. Í sýn uppsprettunnar finnur þú *Skrár í verkefninu* og ýtir á *Sýna skrár*.
   `opencde seed` setti `three_walls_gtin.ifc` þar (þrír veggir með GTIN 3, 2 og 1). Ýttu á
   *Sækja*: skráin verður að líkangagnasafni.
2. Veldu haminn *Vinna*; líkanið opnast í þrívídd. Smelltu á vegg til að merkja hann.
3. Ýttu á *Mál* fyrir ofan þrívíddarsýnina og svo á *Nýtt mál* í hægri dálki. Skrifaðu
   eitthvað undir *Fyrirsögn* og ýttu á *Búa til mál*. Málið er búið til í gegnum BCF API, og
   sýnin og merkti veggurinn fylgja með sem viewpoint.
4. Undir málinu skrifar þú eitthvað í *Skrifa athugasemd* og ýtir á *Senda*.

## 5. Sjáðu það á þjóninum

Innskráð(ur) sem `admin` opnar þú <http://127.0.0.1:8000/admin>:

- *Verkefni* sýnir *Building permit* með tvö mál (það frá `opencde seed` og þitt) og eitt
  skjal.
- *Endurskoðunarskrá* sýnir innskráninguna og skráningu forritsins.
- *Beiðnaskrá* sýnir hvert kall sem forritið gerði, með sömu `X-Request-ID`-gildum og
  spjaldið *Skrá* neðst í sýn uppsprettunnar í *Sækja*, svo að misheppnað kall finnist á
  báðum hliðum.

Ýttu síðan á *Skrá út* efst á síðu þjónsins, þar sem upphleðslan hér á eftir er gerð sem
annar notandi.

Grafið er byggt úr upphlöðnum líkönum, ekki úr því frá `opencde seed`. Til að sjá það sendir
þú líkanið til þjónsins:

1. Í Dataspatium velur þú haminn *Deila* og flipann *Til CDE*. Undir *Hvað* velur þú
   *Upprunalega skráin* og ýtir á *Senda*.
2. *Yfirferð fyrir deilingu* sýnir hvað fylgir með: ýttu á *Halda áfram*.
3. Upphleðslusíða þjónsins opnast í sprettiglugga. Skráðu þig inn sem `inspection_manager`
   og ýttu á *Vista og halda áfram*. Glugginn lokast sjálfur.

Innan fárra sekúndna svarar Neo4j Browser á <http://127.0.0.1:7484> (tengdu við
`bolt://127.0.0.1:7697` sem `neo4j` með lykilorðinu úr `.env`) þessari fyrirspurn með
veggnum tengdum við íhlut viewpointsins:

```cypher
MATCH (c:Component)-[:SAME_AS]->(w:IfcWall) RETURN c, w
```

## Bilanaleit

Hver lína vitnar í skjáinn eins og hann lítur út með íslensku heitunum.

| Þetta sérðu | Hvers vegna | Gerðu svona |
|---|---|---|
| `Cannot connect to the Docker daemon`, `error during connect` eða `docker: command not found` | Docker er ekki í gangi | Ræstu Docker Desktop, bíddu þar til það segist vera í gangi og keyrðu skipunina aftur |
| `dependency failed to start: container kontroll-graph-1 is unhealthy` | Lykilorð með færri en 16 stafi, sem Neo4j hafnar (`docker compose -f compose.yaml -f compose.dev.yaml logs graph` segir `A password must be at least 16 characters`), eða gagnagrunnsbindi frá fyrri uppsetningu með öðru lykilorði | Leiðréttu lykilorðið og keyrðu `up`-skipunina aftur. Um gamla bindið, sjá [Byrjaðu aftur](#byrjaðu-aftur) |
| `port is already allocated`, `Ports are not available` eða `address already in use` | Annað forrit heldur 8000, 7484 eða 7697, kannski fyrri Kontroll (`docker ps` sýnir það) | Stöðvaðu það, eða gefðu upp aðrar gáttir með `OPENCDE_DEV_PORT`, `OPENCDE_DEV_NEO4J_HTTP_PORT` og `OPENCDE_DEV_NEO4J_BOLT_PORT` í `.env` og notaðu þína gátt í stað 8000 upp frá því |
| Gámum úr annarri möppu er skipt út | Tvö eintök á einni tölvu deila Compose-verkefnisheitinu `kontroll` | Gefðu því síðara `COMPOSE_PROJECT_NAME=kontroll-2` og aðrar `OPENCDE_DEV_*`-gáttir í `.env` þess |
| `the database is not empty` | `opencde seed` hefur þegar keyrt og prentaði lykilorðin þá | Fáðu nýtt lykilorð með `docker compose -f compose.yaml -f compose.dev.yaml exec api opencde user set-password inspection_manager`, eða [byrjaðu aftur](#byrjaðu-aftur) |
| `python` finnst ekki, eða Microsoft Store opnast | Skipunin heitir eitthvað annað á þessari tölvu | Notaðu `py` eða `python3` |
| Skráalisti í stað forritsins | Vefþjónninn keyrir í ytri möppunni | Stöðvaðu hann með Ctrl+C og ræstu hann í möppunni þar sem `index.html` er |
| Gömul útgáfa forritsins, eða eitthvað allt annað | Eitthvað annað svarar á gátt 8080; á Windows getur annar vefþjónn ræst á sömu gátt án villu | Notaðu aðra gátt, `python -m http.server 8090 --bind 127.0.0.1`, og opnaðu `http://127.0.0.1:8090/` |
| *Forritið getur aðeins skráð sig sjálft hjá þjóninum þegar það keyrir frá vefþjóni …* | Forritið var opnað úr möppunni | Opnaðu `http://127.0.0.1:8080/` |
| *Náðist ekki í 127.0.0.1:8000 …* | Kontroll er ekki í gangi, eða vistfangið er rangt skrifað | <http://127.0.0.1:8000/readyz> verður að svara. Vistfangið er `http://127.0.0.1:8000` án nokkurs á eftir |
| *Þjónninn leyfir ekki að forritið skrái sig sjálft …* | `OPENCDE_DYNAMIC_CLIENT_REGISTRATION` er ekki `true` | Breyttu `.env`, keyrðu `up`-skipunina aftur og ýttu aftur á *Bæta við uppsprettu* |
| *Skráning mistókst:* … `http redirect URIs are only allowed for the loopback address` | Forritið var opnað á `localhost`, sem þjónninn samþykkir ekki sem leið til baka | Opnaðu `http://127.0.0.1:8080/` og bættu uppsprettunni við þar |
| *Skráning mistókst:* … `rate_limited` | Fleiri en fimm skráningar innan klukkustundar; hvert *Bæta við uppsprettu* með tómt *Biðlaraauðkenni (client id)* er ein | `docker compose -f compose.yaml -f compose.dev.yaml restart api` núllstillir teljarann |
| *Netaðgangur fyrir … er ekki leyfður.* | Ýtt var á *Hafna* | Leyfðu það undir *Umsjón*, *Vinnusvæði*, *Netaðgangur* og reyndu aftur |
| *Vafrinn lokaði á innskráningargluggann …* | Sprettigluggavörn vafrans | Leyfðu sprettiglugga fyrir `http://127.0.0.1:8080` og ýttu aftur á *Skrá inn* |
| Í sprettiglugganum: *Ekki er hægt að halda áfram* og *Óþekktur biðlari.* | Þjónninn hefur gleymt skráningu forritsins, oftast eftir `down -v` | Lokaðu glugganum og endurhladdu forritið, því annars snýst *Skrá inn* í fimm mínútur. Eyddu uppsprettunni með krossinum við hliðina á henni undir *Viðbættar uppsprettur* og bættu henni við aftur |
| Í sprettiglugganum: *Ekki er hægt að halda áfram* og *Þetta redirect-URI er ekki skráð fyrir þennan biðlara.* | *Biðlaraauðkenni (client id)* var fyllt út, til dæmis úr úttaki `opencde seed` | Lokaðu glugganum og endurhladdu forritið. Eyddu uppsprettunni með krossinum við hliðina á henni undir *Viðbættar uppsprettur* og bættu henni við aftur með tómt auðkenni |
| Í sprettiglugganum: *Notandanafnið eða lykilorðið er ekki rétt.* | Hver notandi hefur eigið lykilorð frá `opencde seed` | Notaðu rétt lykilorð, eða fáðu nýtt eins og að ofan |
| *Eyðublaðið er útrunnið. Reyndu aftur.* á `/signin`, eða í sprettiglugganum *Ekki er hægt að halda áfram* og *Innskráningareyðublaðið er útrunnið eða hefur verið átt við það. Byrjaðu aftur.*, þótt þú hafir rétt opnað síðuna. `docker compose -f compose.yaml -f compose.dev.yaml logs api` sýnir `GET /sw.js` með 404 | Service worker í vafranum þínum frá öðru vefforriti sem einhvern tíma hefur keyrt á `http://127.0.0.1:8000`, til dæmis ræst með `python -m http.server` án gáttar. Hann svarar með gömlum afritum af síðum Kontroll | Endurhladdu síðuna og reyndu aftur, því síður Kontroll fjarlægja slíkan worker sjálfar. Ef skilaboðin hverfa ekki skaltu fjarlægja hann handvirkt: `about:debugging#/runtime/this-firefox` í Firefox, `edge://serviceworker-internals` í Edge, `chrome://serviceworker-internals` í Chrome; finndu `127.0.0.1:8000` og veldu *Unregister*. Hver vafri hefur sinn eigin, líka sá sem er innbyggður í ritil. Einkagluggi hefur engan, sem sýnir fljótt hvort þetta er orsökin. Haltu öðrum forritum frá gátt 8000 |
| *Þú ert ekki þátttakandi í neinu verkefni á þjóninum.* | Þú skráðir þig inn sem `admin`, sem er ekki í neinu verkefni | Ýttu á *Skrá út* og svo á *Skrá inn* sem `inspection_manager` |
| *Skrá inn* heldur áfram að snúast | Glugganum var lokað áður en innskráningu var lokið | Endurhladdu síðuna |
| Glugginn segir *Kopiera adressen … / Copy the address …* | Hann náði ekki í glugga forritsins, sem var kannski lokað eða endurhlaðið á meðan | Lokaðu glugganum og ýttu aftur á *Skrá inn* |
| *Annar reikningur* á upphleðslusíðunni | Vafrinn er skráður inn á þjóninn sem `admin`, sem hóf ekki upphleðsluna | Ýttu á *Skrá út* á þeirri síðu og lokaðu glugganum. Endurhladdu forritið, því annars er *Senda* áfram upptekið, ýttu á *Skrá inn* í sýn uppsprettunnar, veldu líkanið í vinstri dálki í *Deila* og sendu aftur |

## Byrjaðu aftur

Í möppunni sem þú ræstir úr (eða hvar sem er, með `-p kontroll` í stað `-f`-rofanna tveggja):

```sh
docker compose -f compose.yaml -f compose.dev.yaml down -v
```

Það eyðir gagnagrunninum og skrám sýningarinnar. Keyrðu síðan `up`- og `seed`-skipanirnar
í skrefi 1 aftur, sem gefur ný lykilorð. Í Dataspatium eyðir þú uppsprettunni með krossinum
við hliðina á henni undir *Viðbættar uppsprettur* og bætir henni við aftur, þar sem þjónninn
hefur gleymt skráningu forritsins.

Til að stöðva án þess að eyða neinu sleppir þú `-v`, og vefþjóninn stöðvar þú með Ctrl+C.

## Næstu skref

- [docs/client-guide.md](client-guide.md) um forritaskilin, getuskjalið og
  villukóðana.
- [docs/acceptance.md](../acceptance.md) um gátlistana sem parið er prófað
  með, og [docs/dataspatium-coordination.md](../dataspatium-coordination.md)
  um það sem verkefnin tvö samræma.
- [docs/deploy/](deploy/) þegar þjónninn á að keyra fyrir aðra.
