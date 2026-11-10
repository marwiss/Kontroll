**Svenska** · [Dansk](docs/da/README.md) · [Norsk bokmål](docs/nb/README.md) · [Norsk nynorsk](docs/nn/README.md) · [Suomi](docs/fi/README.md) · [Íslenska](docs/is/README.md) · [English](docs/en/README.md)

<img src="opencde/ui/static/icon-192.png" alt="" width="64" height="64" align="left">

# Dataregium OpenCDE-server

*Dataregium hette Kontroll fram till den 8 november 2026.*

Dataregium är en server för buildingSMARTs **OpenCDE-API:er** (Foundation API
1.0, BCF API 3.0 och 2.1 samt Documents API 1.0), byggd på en grafdatabas, med
webbadministration och en valfri IFC-LPG-modul som kopplar BCF-komponenter
till de byggdelar de pekar på. Den växte fram ur en forskningsprototyp från
2023 för digitala kontrollplaner i svenska bygglov och skrevs om från grunden
med säkerhet som första krav.
Klienter som följer specifikationerna ska kunna ansluta, så servern är
inte bunden till något enskilt program.

![Administrationens översikt i en Dataregium-server: antal användare, projekt, klienter, ärenden och dokument, databasens status och de senaste revisionshändelserna](docs/images/admin-overview.png)

**Innehåll**

- [Ladda ned och kom igång](#ladda-ned-och-kom-igång)
- [Vad som krävs](#vad-som-krävs)
- [Vad du kan göra](#vad-du-kan-göra)
- [OpenCDE-API:erna och deras klienter](#opencde-apierna-och-deras-klienter)
- [Dataregium och Dataspatium](#dataregium-och-dataspatium)
- [Lär dig mer](#lär-dig-mer)
- [Begränsningar i korthet](#begränsningar-i-korthet)
- [Nästa i 3-serien](#nästa-i-3-serien)
- [Fel och förslag](#fel-och-förslag)
- [Utveckling](#utveckling)
- [Licens](#licens)

## Ladda ned och kom igång

### Snabbstart (lokalt, Docker)

1. **Ladda ned.** Klona repot, eller hämta den publicerade imagen
   `ghcr.io/marwiss/opencdeserver` (flera arkitekturer, skannad och med SBOM
   vid varje utgåva):

   ```sh
   git clone https://github.com/marwiss/Dataregium.git
   cd Dataregium
   ```

2. **Konfigurera.** Kopiera `.env.example` till `.env` och sätt
   `OPENCDE_GRAPH_PASSWORD` (minst 16 tecken). Varje inställning förklaras i
   [.env.example](.env.example).
3. **Starta.** `docker compose up -d --build`
   startar servern på <http://127.0.0.1:8000> och en Neo4j-databas.
   `docker compose logs -f api` visar serverloggen.
4. **Se dig omkring.** <http://127.0.0.1:8000/docs> är den interaktiva
   API-dokumentationen, <http://127.0.0.1:8000/readyz> beredskapskontrollen
   och <http://127.0.0.1:7484> Neo4j Browser (Bolt på `127.0.0.1:7697`;
   utvecklingsöverlagringen undviker Neo4j:s standardportar, som ofta upptas
   av en annan Neo4j på samma dator).
5. **Lägg in demodata och logga in.**
   `docker compose exec api opencde seed`
   skapar demoanvändare och projekt och skriver ut deras lösenord en gång.
   Logga in på <http://127.0.0.1:8000/signin> som `admin` och öppna `/admin`.
6. **Anslut en klient.** Registrera din app under *Klienter* (eller låt den
   registrera sig själv när `OPENCDE_DYNAMIC_CLIENT_REGISTRATION=true`) och
   peka den mot `http://127.0.0.1:8000`; [Dataspatium](#dataregium-och-dataspatium)
   och Python-biblioteket i [client/](client/) är färdiga klienter.
   Ska du logga in från Dataspatium, följ [snabbstarten](docs/sv/quickstart.md): den
   tar upp alla inställningar som krävs och vad du gör om något går fel.

Utan Docker för själva servern (en databas behövs fortfarande):

```sh
uv sync                          # installerar Python 3.13 och alla beroenden
uv run opencde doctor            # kontrollerar konfiguration och databas
uv run opencde serve             # http://127.0.0.1:8000
```

### Driftsättning

En compose-fil plus en överlagring per scenario:

| Scenario | Guide |
|---|---|
| Lokalt test på din dator | [docs/sv/deploy/local.md](docs/sv/deploy/local.md) |
| Publik https-adress för klienttester utan egen server (tunnel) | [docs/sv/deploy/tunnel.md](docs/sv/deploy/tunnel.md) |
| Produktion på egen server med Caddy (automatisk TLS) och nattliga säkerhetskopior | [docs/sv/deploy/vps-caddy.md](docs/sv/deploy/vps-caddy.md) |
| Coolify, Dokploy, Portainer | [docs/sv/deploy/paas.md](docs/sv/deploy/paas.md) |
| Containertjänst plus hanterad Neo4j AuraDB eller Memgraph Cloud | [docs/sv/deploy/cloud-aura.md](docs/sv/deploy/cloud-aura.md) |
| Säkerhetskopiering och återställning (flyttbar mellan Neo4j och Memgraph) | [docs/sv/deploy/backup.md](docs/sv/deploy/backup.md) |

`uv run opencde init --public-url https://cde.example.org` skriver en
produktions-`.env` med nya hemligheter; `opencde doctor` kontrollerar
resultatet.

### Konfiguration

Allt läses från miljövariabler med prefixet `OPENCDE_`, från `.env` eller
från Docker-hemligheter i `/run/secrets/opencde_<namn>`. Den kommenterade
listan finns i [.env.example](.env.example). Standardvärdena är säkra:
produktion vägrar starta utan en publik `https`-adress och ett
databaslösenord, och inget är öppet förrän det har konfigurerats.

## Vad som krävs

- Windows, macOS eller Linux med Docker (Desktop på Windows/macOS, Engine på
  Linux), eller Python 3.11 eller senare med [uv](https://docs.astral.sh/uv/)
  och en egen Neo4j 5.26- eller Memgraph 3.14-databas.
- Ungefär 1 GB minne för databascontainern (`NEO4J_HEAP` och
  `NEO4J_PAGECACHE` i `.env`), mer med IFC-LPG-modulen.
- Lokalt: port 8000 för servern och 7484/7697 för databasen, alla bundna till
  `127.0.0.1`. I produktion: portarna 80 och 443 nåbara från internet och ett
  DNS-namn för servern.
- Klienter behöver en `https`-adress i produktion; lokalt accepteras
  `http://127.0.0.1` som redirect-URI, och `http://localhost` med `OPENCDE_ALLOW_LOCALHOST_REDIRECTS=true`.

## Vad du kan göra

- **Foundation API 1.0**: tjänsteupptäckt, OAuth2 authorization code med PKCE,
  aktuell användare, återkallelse av tokens och dynamisk
  klientregistrering med publika klienter (avstängd som standard).
- **BCF API 3.0 och 2.1**: projekt, extensions, ärenden med OData-frågor, kommentarer,
  viewpoints med snapshots, bitmaps och komponenter, filer,
  dokumentreferenser, dokument och händelseloggarna, allt validerat mot
  buildingSMARTs scheman.
- **Documents API 1.0**: val och nedladdning av dokument, uppladdning i delar
  med serverns webbsidor för metadata och urval, versionsfrågor med ETag.
- **Administration** i webbläsaren: logga in på `/signin` med ett
  administratörskonto och öppna `/admin` för att hantera användare och deras
  projektroller, projekt och deras BCF-extensionsvärden, OAuth2-klienter,
  sessioner, revisionsloggen, den valfria begärandeloggen och serverns
  hälsokontroller. Varje användare har `/account` för sitt eget lösenord,
  sina appar och sina sessioner. Kommandoraden (`uv run opencde --help`) gör
  samma sak från en terminal.
- **Tillägg utanför specifikationerna**, vart och ett markerat som sådant: ett
  kapabilitetsdokument på `/.well-known/dataregium` som berättar för klienten
  vilka tillägg som är påslagna, ett stabilt `code` i varje felkropp, en
  begärandelogg för felsökning av klienter (`/admin/requests`,
  `GET /admin/api/requests` med scopet `admin`), och IFC-LPG-modulen som gör
  uppladdade IFC-modeller till grafdata kopplade till BCF-komponenter. Sedan
  3.0.0 är grafen förlustfri och kan skrivas tillbaka som fil, varje
  uppladdning kontrolleras mot IFC-schemat, buildingSMARTs regler och
  projektets IDS, och medlemmar ställer namngivna frågor till den.
- **Ett klientbibliotek** i Python ([client/](client/), LGPL) med
  körbara exempel, samt Dockerfile, compose-överlagringar och en publicerad
  image för varje driftsättningsscenario.
- **Status**: alla elva etapper i planen är genomförda (de tre API:erna,
  administrationen, klientbiblioteket, driftsättning, IFC-LPG,
  acceptanschecklistan och säkerhetshärdningen); ett bidrag av servern till
  IfcOpenShell är inte föreslaget.

<img src="docs/images/signin.png" alt="Inloggningssidan som en klient öppnar" width="240">
<img src="docs/images/upload.png" alt="Uppladdningssidan, där användaren ger filen titel och version" width="340">
<img src="docs/images/admin-project.png" alt="Ett projekt i administrationen, med medlemmar och roller" width="440">
<img src="docs/images/admin-settings.png" alt="Hälsokontrollerna på inställningssidan" width="440">

## OpenCDE-API:erna och deras klienter

OpenCDE är buildingSMART Internationals familj av öppna webb-API:er för en gemensam
datamiljö, den plats där ett projekt delar sina modeller, dokument och ärenden. En
klient och en server som följer samma specifikationer kan arbeta tillsammans, vem som
än har byggt dem. Dataregium implementerar alla tre:

| API | Vad det är till för | Specifikation |
|---|---|---|
| Foundation API 1.0 | Säger vilka API:er en server erbjuder, hur man loggar in och vem användaren är | [foundation-API](https://github.com/buildingSMART/foundation-API) |
| BCF API 3.0 och 2.1 | Ärenden om en modell, med kommentarer och viewpoints med kamera, komponenter och bilder | [BCF-API](https://github.com/buildingSMART/BCF-API) |
| Documents API 1.0 | Att välja, hämta och ladda upp dokument och deras versioner, via sidor på servern | [documents-API](https://github.com/buildingSMART/documents-API) |

**Dataspatium är en klient, inte den enda.** Varje klient som följer de här
specifikationerna ska kunna ansluta: inget på servern är beroende av Dataspatium, och
tilläggen utanför specifikationerna är valfria, så en klient som inte känner till dem
märker dem inte. En klient behöver tre saker:

- en registrering på servern, gjord av en administratör under *Klienter* eller av klienten
  själv när `OPENCDE_DYNAMIC_CLIENT_REGISTRATION=true`;
- OAuth2 authorization code med PKCE `S256`, som servern kräver av varje klient utom en konfidentiell som en administratör har märkt;
- BCF API 3.0, eller 2.1 för en klient som bara kan den versionen. `GET /foundation/versions` listar båda, och
  [klientguiden](docs/sv/client-guide.md) säger vad som skiljer dem åt.

Så långt är det visat: serverns svar provas mot buildingSMARTs scheman vid varje push,
och Dataspatium och Python-biblioteket i [client/](client/) körs mot servern. Oberoende
klienter som Bonsai och ifc-lite har en färdig checklista som ännu inte är körd. Om du provar en klient, berätta
hur det gick under [Fel och förslag](#fel-och-förslag). När en klient och en specifikation inte
stämmer överens avgör specifikationen. [docs/sv/client-guide.md](docs/sv/client-guide.md) är till för den som bygger
en klient.

## Dataregium och Dataspatium

Dataregium (servern) och [Dataspatium](https://github.com/marwiss/Dataspatium)
(en dataapp som körs helt i webbläsaren) är utvecklade för att fungera
tillsammans som server och klient, och samma utgåvenummer på båda betyder
att de fungerar ihop: Dataspatium 3.0.0 fungerar med Dataregium 3.0.0
([snabbstart](docs/sv/quickstart.md)).
Dataspatium lägger till en Dataregium-server som källa: appen upptäcker
API:erna genom `/foundation/versions`, loggar in med OAuth2 authorization
code och PKCE och registrerar sig själv som publik klient när dynamisk
registrering är påslagen, listar projektets modeller och dokument, läser och
skriver BCF-ärenden med kommentarer och viewpoints tagna ur sin 3D-vy, laddar
upp datamängder, filer och arbetsytepaket genom Documents API, frågar
IFC-grafen med Cypher över Bolt när operatören exponerar den, och skickar
`X-Request-ID` på varje anrop så att begärandeloggen här och loggen i appen
visar samma samtal. Appen läser serverns kapabilitetsdokument för att se
vilka tillägg som är påslagna och reagerar på de felkoder servern lägger i
sina felkroppar.

Så här hänger de ihop:

```mermaid
flowchart LR
    subgraph app ["Dataspatium, i webbläsaren"]
        source["Källa och inloggning"]
        issues["Ärenden i 3D-vyn"]
        files["Modeller och dokument"]
        queries["Frågor mot IFC-grafen"]
        log["Loggen i appen"]
        admin["Kortet Administration"]
    end
    subgraph server ["Dataregium, servern"]
        foundation["Foundation API, OAuth2"]
        bcf["BCF API"]
        documents["Documents API"]
        ifcgraph[("IFC-graf")]
        requests["Begärandelogg"]
        adminapi["Administrations-API"]
    end
    source <--> foundation
    issues <--> bcf
    files <--> documents
    queries --> ifcgraph
    log <-- "X-Request-ID" --> requests
    admin --> adminapi
```

Bortsett från de markerade tilläggen går allt Dataspatium gör mot servern
genom de tre OpenCDE-API:erna, så appen använder inget som en annan klient
inte kan använda, se [OpenCDE-API:erna och deras klienter](#opencde-apierna-och-deras-klienter). De två produkterna
installeras var för sig: det här repot buntar inte Dataspatium (licenserna
skiljer sig, AGPL här och PolyForm Strict där), och Dataspatiums README
beskriver hur appen hämtas. Klientsidan beskrivs i Dataspatiums README och
dess dokumentation.

## Lär dig mer

- [docs/sv/quickstart.md](docs/sv/quickstart.md): Dataregium och Dataspatium tillsammans på
  tjugo minuter, från tom dator till ett ärende skapat i 3D-vyn.
- [docs/sv/client-guide.md](docs/sv/client-guide.md) och [docs/examples/](docs/examples/):
  hur man bygger en klient, kapabilitetsdokumentet, felkoderna och körbara
  exempel med Python-biblioteket i [client/](client/).
- [docs/sv/architecture.md](docs/sv/architecture.md): hur delarna hänger ihop, vad som händer med ett anrop och var allt finns i koden.
- [docs/sv/glossary.md](docs/sv/glossary.md): orden som dokumentationen använder.
- [docs/sv/flows/](docs/sv/flows/): sekvensdiagram för OAuth2-, Documents API- och BCF-viewpoint-flödena.
- [docs/sv/graph-schema.md](docs/sv/graph-schema.md): grafmodellen.
- [docs/sv/ifc-lpg.md](docs/sv/ifc-lpg.md): den valfria IFC-LPG-modulen och exempel på Cypher-frågor.
- Arkitekturbeslut som ligger fast: grafdatabas som enda lager, opaka token i
  stället för JWT, portabel Cypher för Neo4j och Memgraph, webbgränssnitt utan
  ramverk, säkerhetskopia på applikationsnivå, BCF API 2.1 bredvid 3.0, en
  förlustfri IFC-graf som läser och skriver STEP själv och valideras när den
  skrivs, buildingSMARTs regler i en egen miljö, IFC-LPG som bibliotek, kontroll
  mot projektets IDS och namngivna frågor för medlemmar.
- [spec/SOURCES.md](spec/SOURCES.md): de exakta specifikationsversioner
  som servern testas mot.

Dokumentationen finns på den här README-filens sju språk, varje språk under
`docs/<språk>/`; engelskan under `docs/en/` är källan. CONTRIBUTING är på engelska.

### Vidare läsning

- [BCF API](https://github.com/buildingSMART/BCF-API), [Foundation API](https://github.com/buildingSMART/foundation-API) och [Documents API](https://github.com/buildingSMART/documents-API):
  specifikationerna som servern följer.
- [IFC](https://github.com/buildingSMART/IFC4.x-development): filformatet för byggnadsmodeller.
- [RFC 9700](https://www.rfc-editor.org/rfc/rfc9700): dagens bästa praxis för säkerhet i OAuth 2.0, och
  [OAuth 2.1](https://datatracker.ietf.org/doc/draft-ietf-oauth-v2-1/), utkastet som samlar den.
- [RFC 7636](https://www.rfc-editor.org/rfc/rfc7636) (PKCE), [RFC 8252](https://www.rfc-editor.org/rfc/rfc8252) (appar i datorn eller telefonen) och
  [RFC 7591](https://www.rfc-editor.org/rfc/rfc7591) (registrering av klienter).
- [OWASP ASVS](https://owasp.org/www-project-application-security-verification-standard/): checklistan för säkerhetsarbetet.

## Begränsningar i korthet

- Servern implementerar BCF API 3.0 och 2.1, inte 1.0, vars resurser ser annorlunda ut.
- Export av ett projekt som BCFzip överlåts åt klienterna; servern lagrar
  ärenden, kommentarer och viewpoints så som API:t definierar dem.
- Gemenskapsutgåvorna av Neo4j och Memgraph saknar läsbegränsade
  databasanvändare, så en exponerad Bolt-port ger full åtkomst åt den som
  har lösenordet. Porten förblir stängd om inte administratören avsiktligt
  publicerar den; administrations-API:ts läsande graffråga
  (`OPENCDE_GRAPH_QUERY_ENABLED`) ger Cypher utan porten.
- IFC-LPG-importen körs i en separat process med minnes- och tidsgränser
  (`OPENCDE_IFC_LPG_*`); mycket stora modeller avvisas i stället för att
  lämnas halvimporterade.
- Webbsidorna är till för administratörer och för OAuth2- och Documents
  API-flödena; slutanvändare arbetar i en klient som Dataspatium eller Bonsai.
- Sidorna finns på den här README-filens sju språk (byt längst ned på varje
  sida); kommandoraden och API:ernas felmeddelanden är på engelska.
- Ingen extern granskning ännu. OAuch- och testssl-körningarna är
  operatörens steg före en produktionsdriftsättning.

## Personuppgifter

Den som driver Dataregium åt andra är personuppgiftsansvarig för det här. Servern
lagrar användarkonton (användarnamn, namn, valfri e-post, lösenordshash),
projektmedlemskap, ärenden och kommentarer med författarnas namn, uppladdade
filer med uppladdare, IFC-grafen med filens ägarhistorik och en granskningslogg
över vem som gjorde vad och från vilken adress. Lösenord, token och hemligheter
lagras bara som hashar. Token, sessioner, uppladdningssessioner och oanvända
självregistrerade klienter går ut och städas av servern; granskningsloggen
gallras av operatören. En administratör tar bort ett konto under `/admin/users`,
och dess sessioner och token följer med; namnet står kvar på de ärenden personen
skrev tills de tas bort. Granskningsloggen exporteras som CSV, BCF- och
dokumentdata genom API:erna och hela databasen med `opencde backup`. Vad
Dataspatium sparar i webbläsaren står i appens egen dokumentation.

## Nästa i 3-serien

3.0.0 är 3-seriens första utgåva, gjord tillsammans med Dataspatium 3.0.0:
IFC-grafen som en förlustfri modell, kontrollen av varje uppladdning och de
namngivna frågorna, som [Vad du kan göra](#vad-du-kan-göra) beskriver. Sedan
2026-11-10 rymmer den också krocktestet mellan två versioner, basversionen vid
uppladdning, avvisningen av uppladdningar med valideringsfel och
förhandskontrollen av en fil. Som varje huvudnummer har serien en enda utgåva,
som ges ut igen när den växer. Det som följer gör grafen till en modell som kan
redigeras och versionshanteras i databasen, med Dataspatium som klienten som
redigerar den och visar dess versioner. De officiella OpenCDE-API:erna förblir
som buildingSMART definierar dem; det serien lägger till är tillägg till dem,
under egna namn. Det här avsnittet säger vad som är beslutat och vad som bara är
föreslaget, för den, människa eller AI-agent, som för en del av det vidare.
Besluten finns i korthet under [Lär dig mer](#lär-dig-mer), arbetssätten i
[CONTRIBUTING.md](CONTRIBUTING.md) och IFC-grafen i
[docs/sv/ifc-lpg.md](docs/sv/ifc-lpg.md).

### Beslutat

- **Redigering av modeller i Native IFC.** Create är uppladdningen och Read de
  namngivna frågorna, båda i 3.0.0. Update är en ändring som en klient föreslår
  genom API:et och som prövas innan den förs in. Delete tar bort valda delar av
  grafen: en entitet, en byggnad eller ett projekt. Export skriver STEP
  tillbaka, som nu.
- **Versionshistorik i databasen, inte i git**, i samma anda som Bruno Postles
  [ifcmerge](https://github.com/brunopostle/ifcmerge): vad som ändrades, vem
  som föreslog det och vem som godkände det. Datan måste hålla sig till IFC,
  ifc-gherkin-rules och projektets IDS, vid import och efter varje ändring.
- **BIM-snippets som en fungerande demonstration.** En föreslagen ändring
  färdas som `bim_snippet` i ett BCF 3.0-ärende, med ett publicerat schema
  bakom dess `reference_schema`, så att ändringen, diskussionen och beslutet
  finns på ett ställe. Ingen programvara tillämpar en snippet i dag, och
  buildingSMARTs outgivna utvecklingsgrenar har strukit dem; Dataregium bygger
  dem för att visa hur de skulle kunna fungera. En snippet pekar ut det den
  ändrar med GlobalId och en sökväg därifrån, med STEP-id bara där inget GlobalId når. STEP-id når
  alltid en instans; GlobalId och sökväg nådde 98 till 100 procent av
  instanserna i 28 provfiler, med steg bakåt genom inversa attribut.
- **Tillägg, inte nya versioner av API:erna.** BCF-ärenden med `bim_snippet`,
  Documents API:ts metadata och versioner och kapabilitetsdokumentet bär det
  serien lägger till, beskrivet av en egen OpenAPI.
- **Krocktest på båda ställena**: på servern med IfcOpenShells IfcClash och i
  Dataspatium med dess egen kärna i JavaScript.
- **Administration av ett projekt av dess projektansvarige**, som inte behöver
  vara serveradministratör, och team med ansvar utöver projektrollerna.
- **Hur en version lagras** (beslutat 2026-11-10). Varje godkänd version är en
  nod med sin förälder, författare, godkännare och ändringar per GlobalId,
  sökväg och attribut; grafen håller huvudversionen; en version lagras som sin ändring,
  med en hel fil, som `.ifczip`, bara när den publiceras, och vilken version
  som helst skrivs på begäran; två ändringar sammanfogas attribut för attribut,
  som ifcmerge gör, och en ändring förs in när filen som skrivs från den inte
  har någon anmärkning som versionen före den saknade. I 3.0.0: basversionen
  vid uppladdning (`412` vid konflikt), avvisningen av uppladdningar med
  valideringsfel och förhandskontrollen av en fil. Versionsnoderna och
  sammanfogningen kommer härnäst.
- **Vem som får ändra vad** (beslutat). Projektrollerna först: `editor`
  föreslår, `manager` godkänner, och en AI föreslår bara. Ansvarsregler som
  pekar ut en del av modellen med IDS-urval, som klass, egenskap,
  klassificering eller våning, som ISO 19650:s ansvariga team gör, kommer
  senare.
- **Snippetens detaljer** (beslutat). En sökväg skrivs med IFC:s attributnamn
  med index, från ett GlobalId, med STEP-id bara där inget GlobalId når; en ändring av en
  instans som flera delar ändrar den för alla, och en egen kopia måste begäras;
  varje ändring bär vem som föreslog den, och vilken AI-modell och vilket
  verktygsanrop, där en AI gjorde det.

### Föreslaget, inte beslutat

Inget just nu: versionsmodellen, rättigheterna och snippetens detaljer
beslutades 2026-11-10, som listan ovan säger. Nya förslag samlas här innan de
beslutas.

## Fel och förslag

Rapportera fel och önskemål som *Issues* här på GitHub. Ange vilken
serverversion du kör (`version` i `/.well-known/dataregium` eller `/healthz`),
vilken klient du använde och `X-Request-ID` för ett misslyckat anrop;
begärandeloggen och klientens logg delar det. Bifoga inga personuppgifter och
inga hemligheter. Hur ändringar tas emot står i
[CONTRIBUTING.md](CONTRIBUTING.md). För en säkerhetssårbarhet, följ
[SECURITY.md](SECURITY.md) i stället för att öppna ett ärende.

## Utveckling

```sh
uv run pytest                    # enhets-, konformans- och säkerhetstester
uv run pytest -m integration     # startar Neo4j/Memgraph med testcontainers (kräver Docker)
uv run pytest -m e2e             # klientbiblioteket mot en körande server (kräver Docker)
uv run pytest -m ui              # Playwright + axe-core (uv sync --group ui; playwright install chromium)
uv run ruff format . && uv run ruff check .
uv run ty check opencde client/opencde_client
```

Kod och kommentarer är på engelska, och stilen följer IfcOpenShells
konventioner (ruff, 120 kolumner), så att det förblir möjligt att bidra med
servern till IfcOpenShell.
README finns på engelska, svenska, danska, norska (bokmål och nynorsk),
finska och isländska (`docs/<språk>/README.md`, samma upplägg som
Dataspatium); dokumentationen och webbgränssnittet finns på samma språk,
med engelska alltid som ett val, och gemensamma termer följer Dataspatiums
ordlista. Varje push kör lint, typkontroll, testsviterna på tre
Python-versioner, webbläsartester med axe-core och statiska
säkerhetskontroller; nattliga jobb kör OWASP ZAP, Schemathesis och Trivy. Se
[CONTRIBUTING.md](CONTRIBUTING.md).

## Licens

Servern är licensierad under GNU Affero General Public License v3.0 eller
senare ([LICENSE](LICENSE)): den är servermjukvara, och AGPL:s
nätverksklausul håller förbättringar av driftsatta instanser öppna.
Klientbiblioteket i [client/](client/) är LGPL-3.0-or-later.
Specifikationsfilerna under [spec/](spec/) är © buildingSMART
International och vidaredistribueras oförändrade för testning. Se
[SECURITY.md](SECURITY.md) för hur en sårbarhet rapporteras och vad
projektet gör för att förbli säkert.
