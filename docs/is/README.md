<img src="../../opencde/ui/static/icon.svg" alt="" width="72" height="72" align="left">

# Kontroll OpenCDE-þjónn

*[English](../../README.md) · [Svenska](../sv/README.md) · [Dansk](../da/README.md) · [Norsk](../nb/README.md) · [Suomi](../fi/README.md) · Íslenska*

Þjónn fyrir **OpenCDE-forritaskil** buildingSMART, byggður á grafgagnagrunni:

- **Foundation API 1.0**: uppgötvun þjónustu, OAuth2 authorization code með PKCE, núverandi notandi
- **BCF API 3.0**: verkefni, extensions, mál, athugasemdir, viewpoint, skrár, skjalatilvísanir, skjöl, atburðir
- **Documents API 1.0**: val og niðurhal skjala, upphal í hlutum, útgáfufyrirspurnir

auk vefviðmóts til stjórnunar notenda, OAuth2-biðlara og verkefna, og
valkvæðrar IFC-grafeiningar sem breytir upphöluðum IFC-líkönum í grafgögn svo
að BCF-einingar megi tengja við byggingarhlutana sem þær vísa á.

Verkefnið spratt upp úr rannsóknarfrumgerð frá 2023 sem kannaði hvort BCF API
og IFC-graf gætu borið þær stafrænu eftirlitsáætlanir sem krafist er fyrir
byggingarleyfi í Svíþjóð. Þetta safn er endurskrif frumgerðarinnar frá grunni
með sömu virkni, nútímalegum ósjálfstæðum og öryggi sem fyrstu kröfu. Staða:
**öll 11 stig áætlunarinnar eru útfærð** (forritaskilin þrjú,
stjórnunarviðmótið, biðlarasafnið, uppsetning í rekstur, IFC-graf,
samþykktargátlistinn og öryggisherðingin); framlagið til IfcOpenShell bíður
svars umsjónarmanna (uppköst í [docs/upstream/](../upstream/)). Sjá
[docs/inventory.md](../inventory.md) um hvað frumgerðin gerði og hvar hver
aðgerð stendur í nýja kóðanum.

## Fljótleg byrjun (staðbundið, Docker)

Kröfur: Docker (Desktop á Windows/macOS, Engine á Linux) og
[uv](https://docs.astral.sh/uv/).

```sh
git clone https://github.com/marwiss/Kontroll.git
cd Kontroll
cp .env.example .env            # settu OPENCDE_GRAPH_PASSWORD (minnst 16 stafir)
docker compose -f compose.yaml -f compose.dev.yaml up -d --build
```

Opnaðu síðan <http://localhost:8000/docs> fyrir gagnvirku
API-skjölunina, <http://localhost:8000/readyz> fyrir viðbúnaðarathugunina og
<http://localhost:7484> fyrir Neo4j Browser (Bolt á `localhost:7697`;
þróunaryfirlagið sneiðir hjá sjálfgefnum gáttum Neo4j, sem annar Neo4j á
sömu tölvu tekur oft). `docker compose logs -f api` sýnir atvikaskrá þjónsins.

Án Docker fyrir þjóninn sjálfan (gagnagrunn þarf samt):

```sh
uv sync                          # setur upp Python 3.13 og öll ósjálfstæði
uv run opencde doctor            # athugar stillingar og gagnagrunn
uv run opencde serve             # http://127.0.0.1:8000
```

## Uppsetning í rekstur

Ein compose-skrá auk eins yfirlags fyrir hverja aðstæðu, og útgefin mynd
fyrir margar arkitektúrgerðir (`ghcr.io/marwiss/opencdeserver`, skönnuð og
með SBOM við hverja útgáfu):

| Aðstæður | Leiðbeiningar |
|---|---|
| Staðbundin prófun á eigin tölvu | [docs/deploy/local.md](../deploy/local.md) |
| Opinbert https-vistfang fyrir biðlaraprófanir án eigin þjóns (tunnel) | [docs/deploy/tunnel.md](../deploy/tunnel.md) |
| Rekstur á eigin þjóni með Caddy (sjálfvirkt TLS) og næturlegum öryggisafritum | [docs/deploy/vps-caddy.md](../deploy/vps-caddy.md) |
| Coolify, Dokploy, Portainer | [docs/deploy/paas.md](../deploy/paas.md) |
| Gámaþjónusta auk Neo4j AuraDB eða Memgraph Cloud í umsjón þjónustuaðila | [docs/deploy/cloud-aura.md](../deploy/cloud-aura.md) |
| Öryggisafritun og endurheimt (flytjanleg milli Neo4j og Memgraph) | [docs/deploy/backup.md](../deploy/backup.md) |

`uv run opencde init --public-url https://cde.example.org` skrifar
`.env`-skrá fyrir rekstur með nýjum leyndarmálum; `opencde doctor` athugar
niðurstöðuna.

## Stillingar

Allt er lesið úr umhverfisbreytum með forskeytinu `OPENCDE_`, úr `.env` eða úr
Docker-leyndarmálum í `/run/secrets/opencde_<nafn>`. Listinn með skýringum er
í [.env.example](../../.env.example). Sjálfgefin gildi eru örugg: í rekstri
neitar þjónninn að ræsa án opinbers `https`-vistfangs og lykilorðs að
gagnagrunninum.

## Skjölun

Skjölunin er á ensku; þýðingar á sænsku, dönsku, norsku, finnsku og íslensku
eru áætlaðar.

- [docs/inventory.md](../inventory.md): yfirlit yfir virkni frumgerðarinnar
  frá 2023 og staða í endurskrifinu, með athugasemdum um sérkenni
  forskriftanna
- [docs/client-guide.md](../client-guide.md) og [docs/examples/](../examples/):
  hvernig biðlari er smíðaður; keyranleg dæmi með Python-safninu í [client/](../../client/)
- [docs/flows/](../flows/): raðrit fyrir OAuth2- og Documents API-ferlin
- [docs/graph-schema.md](../graph-schema.md): graflíkanið
- [docs/ifcgraph.md](../ifcgraph.md): valkvæða IFC-grafeiningin og dæmi um Cypher-fyrirspurnir
- [docs/ui-styleguide.md](../ui-styleguide.md): reglur um síður þjónsins
- [docs/acceptance.md](../acceptance.md): gátlisti fyrir sjónræna samþykkt
  með óháðum biðlurum (Bonsai, ifc-lite, Dataspatium)
- [docs/dataspatium-coordination.md](../dataspatium-coordination.md): hvað
  Kontroll og Dataspatium eiga sameiginlegt og hvað meira er samræmt, með
  ákvörðunum eigandans
- [docs/adr/](../adr/): arkitektúrákvarðanir (grafgagnagrunnur, ógegnsæ
  tákn, flytjanlegt Cypher, vefviðmót án umgjarða, safnstefna)
- [docs/security/](../security/): ógnarlíkan, varnir tengdar prófunum,
  OWASP ASVS stigs 2-gátlistinn og hvernig skannarnir eru keyrðir
- [docs/upstream/](../upstream/): uppköst að máli og pull request fyrir
  IfcOpenShell (ekki send)
- [spec/SOURCES.md](../../spec/SOURCES.md): nákvæmar útgáfur forskriftanna
  sem þjónninn er prófaður gegn

## Stjórnun

Skráðu þig inn á `/signin` með stjórnendareikningi og opnaðu `/admin` til að
stjórna notendum og verkefnishlutverkum þeirra, verkefnum og BCF-extensions-
gildum þeirra, OAuth2-biðlurum, setum, endurskoðunarskránni, valkvæðu
beiðnaskránni og heilsuathugunum þjónsins. Hver notandi hefur `/account` fyrir
eigið lykilorð, eigin forrit og eigin setur. Skipanalínan
(`uv run opencde --help`) gerir það sama úr skjáhermi, og stjórnunarbiðlarar
með heimildina (scope) `admin` geta lesið beiðnaskrána á
`/admin/api/requests`.

## Kontroll og Dataspatium

Kontroll (þjónninn) og [Dataspatium](https://github.com/marwiss/Dataspatium)
(gagnaforrit sem keyrir alfarið í vafranum) eru þróuð til að vinna saman sem
þjónn og biðlari. Dataspatium bætir Kontroll-þjóni við sem uppsprettu:
forritið uppgötvar forritaskilin um `/foundation/versions`, skráir sig inn
með OAuth2 authorization code og PKCE og skráir sig sjálft sem opinberan
biðlara þegar sjálfskráning er virk, telur upp líkön og skjöl verkefnisins,
les og skrifar BCF-mál með athugasemdum og viewpoint sem tekin eru úr
þrívíddarsýn þess, hleður upp gagnasöfnum, skrám og vinnusvæðispökkum um
Documents API, spyr IFC-grafið með Cypher yfir Bolt þegar rekstraraðilinn
opnar það, og sendir `X-Request-ID` með hverju kalli svo að beiðnaskráin hér
og atvikaskráin í forritinu sýni sama samtal. Forritið les getuskjal þjónsins
(`/.well-known/kontroll`) til að sjá hvaða viðbætur eru virkar og bregst við
stöðugu villukóðunum sem þjónninn setur í villusvör sín. Fyrir utan
graffyrirspurnirnar, stjórnunarforritaskilin, getuskjalið og villukóðana, sem
eru viðbætur utan forskriftanna, fer allt sem Dataspatium gerir gagnvart
þjóninum um OpenCDE-forritaskilin þrjú, svo að aðrir OpenCDE-biðlarar virka
líka, og Kontroll þjónar hverjum þeim OpenCDE-biðlara sem er. Vörurnar tvær
eru settar upp hver fyrir sig: þetta safn pakkar Dataspatium ekki með
(leyfin eru ólík, AGPL hér og PolyForm Strict þar), og README Dataspatium
lýsir hvernig forritið er sótt. Biðlarahliðinni er lýst í README Dataspatium
og skjölun þess (`docs/kallor.md`, `docs/cad-bim.md`); samþykktarkeyrslur
parsins eru hér í [docs/acceptance.md](../acceptance.md), og það sem
verkefnin tvö samræma er í
[docs/dataspatium-coordination.md](../dataspatium-coordination.md).

## Þróun

```sh
uv run pytest                    # einingaprófanir, samræmisprófanir og öryggisprófanir
uv run pytest -m integration     # ræsir Neo4j/Memgraph með testcontainers (krefst Docker)
uv run pytest -m e2e             # biðlarasafnið gegn þjóni í keyrslu (krefst Docker)
uv run pytest -m ui              # Playwright + axe-core (uv sync --group ui; playwright install chromium)
uv run ruff format . && uv run ruff check .
uv run ty check opencde client/opencde_client
```

Kóði og athugasemdir eru á ensku því að þjónninn og biðlarasafnið eiga að
verða framlag til IfcOpenShell, en stíllinn fylgir venjum þess (ruff, 120
dálkar). README er til á ensku, sænsku, dönsku, norsku, finnsku og íslensku
(`docs/<tungumál>/README.md`, sama skipan sem Dataspatium notar); skjölunin
og vefviðmótið eiga að vera til á sömu sex tungumálum, með ensku alltaf sem
einn kostinn, og sameiginleg hugtök fylgja orðalista Dataspatium.

## Öryggi

Sjá [SECURITY.md](../../SECURITY.md) um hvernig veikleiki er tilkynntur og
hvað verkefnið gerir til að halda sér öruggu.

## Leyfi

Þjónninn er gefinn út með leyfinu GNU Affero General Public License v3.0 eða
nýrra ([LICENSE](../../LICENSE)): hann er þjónhugbúnaður og netákvæði AGPL
heldur endurbótum á hýstum uppsetningum opnum. Biðlarasafnið í
[client/](../../client/) er LGPL-3.0-or-later. Forskriftarskrárnar undir
[spec/](../../spec/) eru © buildingSMART International og er dreift
óbreyttum til prófana.
