# Fljótleg byrjun: Kontroll og Dataspatium saman

Tuttugu mínútur frá engu að máli sem er búið til í þrívíddarsýn og sést í
atvikaskrám þjónsins. Sama síða er í safni Dataspatium; þeim tveimur er haldið
eins. Þú þarft Docker (Desktop á Windows/macOS, Engine á Linux),
[uv](https://docs.astral.sh/uv/), Python 3 fyrir staðbundinn vefþjón, og
Microsoft Edge, Google Chrome eða Firefox.

## 1. Ræstu Kontroll

```sh
git clone https://github.com/marwiss/Kontroll.git
cd Kontroll
cp .env.example .env
```

Opnaðu `.env` og settu `OPENCDE_GRAPH_PASSWORD` sem hvaða gildi sem er með
minnst 16 stöfum, `OPENCDE_DYNAMIC_CLIENT_REGISTRATION=true` svo að
Dataspatium geti skráð sig sjálft, og `OPENCDE_ALLOW_LOCALHOST_REDIRECTS=true`
svo að forrit sem er þjónað frá `http://localhost` megi skrá sig inn. Síðan:

```sh
docker compose -f compose.yaml -f compose.dev.yaml up -d --build
docker compose -f compose.yaml -f compose.dev.yaml exec api opencde seed
```

Seinni skipunin býr til sýninotendur og -verkefni og prentar lykilorð þeirra
einu sinni; geymdu lykilorð `admin` og `editor`. Athugaðu
<http://localhost:8000/readyz> (svarar `ready`) og skráðu þig inn á
<http://localhost:8000/signin> sem `admin`: `/admin` sýnir verkefnin
*Building permit* og *Demolition permit*.

## 2. Ræstu Dataspatium

1. Sæktu `dataspatium-<version>.zip` úr
   [nýjustu útgáfunni](https://github.com/marwiss/Dataspatium/releases/latest)
   og berðu SHA-256 hennar saman við það sem stendur í útgáfutextanum.
2. Taktu ZIP-skrána upp í eigin möppu (ekki inni í ZIP-skránni).
3. Fyrir allt nema OpenCDE-innskráninguna nægir að tvísmella á `index.html`.
   Fyrir OpenCDE þarf að þjóna möppunni yfir http, því að OAuth2-áframsendingin
   þarf http-vistfang:

   ```sh
   cd dataspatium-<version>
   python -m http.server 8080
   ```

   og opnaðu <http://localhost:8080/>. Forritið skráir sig sjálft hjá
   þjóninum sem opinberan biðlara með `http://localhost:8080/oauth-callback.html`
   sem redirect-URI. (Hýsta forritið á <https://marwiss.github.io/Dataspatium/>
   virkar í staðinn gegn þjóni sem leyfir það vistfang.)

## 3. Tengdu þau saman

Í Dataspatium: hamurinn *Inhämta* (Sækja inn) → hnappurinn *Lägg till källa*
(Bæta við uppsprettu) → *Typ av tjänst* (Tegund þjónustu): *OpenCDE (BCF,
Documents)* → *Adress* (Vistfang): `http://localhost:8000` → *Lägg till*
(Bæta við). Uppsprettan opnast í *Inhämta*: ýttu á *Logga in* (Skrá inn) og
skráðu þig inn sem `editor` í sprettiglugganum, og veldu svo *Building permit*
í listanum *Projekt*. Línan undir fyrirsögninni ("Servern: Kontroll OpenCDE
server 2.0.0. Tillägg: …") kemur úr getuskjali þjónsins og segir hvaða
viðbætur eru virkar.

## 4. Búðu til mál úr þrívíddarsýninni

1. Sæktu sýnilíkanið. Sáningin hefur þegar sett `three_walls_gtin.ifc` (þrír
   veggir með GTIN 3, 2 og 1) sem skjal í *Building permit*; í sýn
   uppsprettunnar í *Inhämta* hefur skjalalistinn sækja-hnapp fyrir hvert
   skjal, og skjalið verður að líkansgagnasafni. Viljirðu frekar senda eigin
   skrá, notaðu haminn *Dela* (Deila) → flipann *Till CDE* (Til CDE): veldu
   uppsprettu og verkefni, *Vad* (hvað: upprunaskrá, útflutning eða pakka),
   *Hur* (hvernig: Documents API eða BCF) og *Skicka* (Senda); sæktu hana svo
   til baka á sama hátt.
2. Veldu líkanið í *Bearbeta* (Vinna með); það opnast sjálfkrafa í þrívídd.
   Veldu vegg, opnaðu spjaldið *Ärenden* (Mál) og ýttu á *Nytt ärende* (Nýtt
   mál): gefðu því titil, haltu stöðunni og hakaðu við *Lägg till vyn som
   viewpoint* (Bæta sýninni við sem viewpoint). Málið er búið til um BCF API
   með viewpoint þar sem einingin vísar á vegginn.
3. Skrifaðu athugasemd í sama spjaldi og sendu hana.

## 5. Sjáðu það á þjóninum

- `/admin/projects` → *Building permit* sýnir tvö mál (það sáða og þitt) og
  skjalið.
- `/admin/audit` telur upp innskráninguna og skráningu forritsins.
- Með `OPENCDE_REQUEST_LOG_ENABLED=true` í `.env` (og endurræsingu) sýnir
  `/admin/requests` hvert kall sem forritið gerði, með sömu
  `X-Request-ID`-gildum og spjaldið *Logg* neðst í sýn OpenCDE-uppsprettunnar
  í *Inhämta*, svo að kall sem mistókst finnst á báðum hliðum.
- Með `OPENCDE_IFCGRAPH_ENABLED=true` verður upphalaða líkanið að grafi; Neo4j
  Browser á <http://localhost:7484> (`bolt://localhost:7697`, notandi og
  lykilorð úr `.env`) sýnir vegginn sem `IfcWall`-hnút tengdan einingu
  viewpoint-sins með `SAME_AS`, og grafsýn Dataspatium getur spurt hann með
  Cypher.

## Næstu skref

- [docs/client-guide.md](../client-guide.md) um forritaskilin, getuskjalið og
  villukóðana.
- [docs/acceptance.md](../acceptance.md) um gátlistana sem parið er prófað
  með, og [docs/dataspatium-coordination.md](../dataspatium-coordination.md)
  um það sem verkefnin tvö samræma.
- [docs/deploy/](../deploy/) þegar þjónninn á að keyra fyrir aðra.
