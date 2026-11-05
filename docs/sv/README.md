**Svenska** · [Dansk](../da/README.md) · [Norsk bokmål](../nb/README.md) · [Norsk nynorsk](../nn/README.md) · [Suomi](../fi/README.md) · [Íslenska](../is/README.md) · [English](../../README.md)

<img src="../../opencde/ui/static/icon-192.png" alt="" width="64" height="64" align="left">

# Kontroll OpenCDE-server

Kontroll är en server för buildingSMARTs **OpenCDE-API:er** (Foundation API
1.0, BCF API 3.0 och Documents API 1.0), byggd på en grafdatabas, med
webbadministration och en valfri IFC-grafmodul som kopplar BCF-komponenter
till de byggdelar de pekar på. Den växte fram ur en forskningsprototyp från
2023 för digitala kontrollplaner i svenska bygglov och skrevs om från grunden
med säkerhet som första krav.

![Administrationens översikt i en Kontroll-server: antal användare, projekt, klienter, ärenden och dokument, databasens status och de senaste revisionshändelserna](../images/admin-overview.png)

**Innehåll**

- [Ladda ned och kom igång](#ladda-ned-och-kom-igång)
- [Vad som krävs](#vad-som-krävs)
- [Vad du kan göra](#vad-du-kan-göra)
- [Kontroll och Dataspatium](#kontroll-och-dataspatium)
- [Lär dig mer](#lär-dig-mer)
- [Begränsningar i korthet](#begränsningar-i-korthet)
- [Fel och förslag](#fel-och-förslag)
- [Utveckling](#utveckling)
- [Licens](#licens)

## Ladda ned och kom igång

### Snabbstart (lokalt, Docker)

1. **Ladda ned.** Klona repot, eller hämta den publicerade imagen
   `ghcr.io/marwiss/opencdeserver` (flera arkitekturer, skannad och med SBOM
   vid varje utgåva):

   ```sh
   git clone https://github.com/marwiss/Kontroll.git
   cd Kontroll
   ```

2. **Konfigurera.** Kopiera `.env.example` till `.env` och sätt
   `OPENCDE_GRAPH_PASSWORD` (minst 16 tecken). Varje inställning förklaras i
   [.env.example](../../.env.example).
3. **Starta.** `docker compose -f compose.yaml -f compose.dev.yaml up -d --build`
   startar servern på <http://localhost:8000> och en Neo4j-databas.
   `docker compose logs -f api` visar serverloggen.
4. **Se dig omkring.** <http://localhost:8000/docs> är den interaktiva
   API-dokumentationen, <http://localhost:8000/readyz> beredskapskontrollen
   och <http://localhost:7484> Neo4j Browser (Bolt på `localhost:7697`;
   utvecklingsöverlagringen undviker Neo4j:s standardportar, som ofta upptas
   av en annan Neo4j på samma dator).
5. **Lägg in demodata och logga in.**
   `docker compose -f compose.yaml -f compose.dev.yaml exec api opencde seed`
   skapar demoanvändare och projekt och skriver ut deras lösenord en gång.
   Logga in på <http://localhost:8000/signin> som `admin` och öppna `/admin`.
6. **Anslut en klient.** Registrera din app under *Clients* (eller låt den
   registrera sig själv när `OPENCDE_DYNAMIC_CLIENT_REGISTRATION=true`) och
   peka den mot `http://localhost:8000`; [Dataspatium](#kontroll-och-dataspatium)
   och Python-biblioteket i [client/](../../client/) är färdiga klienter.

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
| Lokalt test på din dator | [docs/deploy/local.md](../deploy/local.md) |
| Publik https-adress för klienttester utan egen server (tunnel) | [docs/deploy/tunnel.md](../deploy/tunnel.md) |
| Produktion på egen server med Caddy (automatisk TLS) och nattliga säkerhetskopior | [docs/deploy/vps-caddy.md](../deploy/vps-caddy.md) |
| Coolify, Dokploy, Portainer | [docs/deploy/paas.md](../deploy/paas.md) |
| Containertjänst plus hanterad Neo4j AuraDB eller Memgraph Cloud | [docs/deploy/cloud-aura.md](../deploy/cloud-aura.md) |
| Säkerhetskopiering och återställning (flyttbar mellan Neo4j och Memgraph) | [docs/deploy/backup.md](../deploy/backup.md) |

`uv run opencde init --public-url https://cde.example.org` skriver en
produktions-`.env` med nya hemligheter; `opencde doctor` kontrollerar
resultatet.

### Konfiguration

Allt läses från miljövariabler med prefixet `OPENCDE_`, från `.env` eller
från Docker-hemligheter i `/run/secrets/opencde_<namn>`. Den kommenterade
listan finns i [.env.example](../../.env.example). Standardvärdena är säkra:
produktion vägrar starta utan en publik `https`-adress och ett
databaslösenord, och inget är öppet förrän det har konfigurerats.

## Vad som krävs

- Windows, macOS eller Linux med Docker (Desktop på Windows/macOS, Engine på
  Linux), eller Python 3.11 eller senare med [uv](https://docs.astral.sh/uv/)
  och en egen Neo4j 5.26- eller Memgraph 3.14-databas.
- Ungefär 1 GB minne för databascontainern (`NEO4J_HEAP` och
  `NEO4J_PAGECACHE` i `.env`), mer med IFC-grafmodulen.
- Lokalt: port 8000 för servern och 7484/7697 för databasen, alla bundna till
  `127.0.0.1`. I produktion: portarna 80 och 443 nåbara från internet och ett
  DNS-namn för servern.
- Klienter behöver en `https`-adress i produktion; lokalt accepteras
  `http://localhost` som redirect-URI med `OPENCDE_ALLOW_LOCALHOST_REDIRECTS=true`.

## Vad du kan göra

- **Foundation API 1.0**: tjänsteupptäckt, OAuth2 authorization code med PKCE
  för varje klient, aktuell användare, återkallelse av tokens och dynamisk
  klientregistrering med publika klienter (avstängd som standard).
- **BCF API 3.0**: projekt, extensions, ärenden med OData-frågor, kommentarer,
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
  kapabilitetsdokument på `/.well-known/kontroll` som berättar för klienten
  vilka tillägg som är påslagna, ett stabilt `code` i varje felkropp, en
  begärandelogg för felsökning av klienter (`/admin/requests`,
  `GET /admin/api/requests` med scopet `admin`), och IFC-grafmodulen som gör
  uppladdade IFC-modeller till grafdata kopplade till BCF-komponenter.
- **Ett klientbibliotek** i Python ([client/](../../client/), LGPL) med
  körbara exempel, samt Dockerfile, compose-överlagringar och en publicerad
  image för varje driftsättningsscenario.
- **Status**: alla elva etapper i planen är genomförda (de tre API:erna,
  administrationen, klientbiblioteket, driftsättning, IFC-graf,
  acceptanschecklistan och säkerhetshärdningen); bidraget till IfcOpenShell
  väntar på underhållarnas svar (utkast i [docs/upstream/](../upstream/)).
  [docs/inventory.md](../inventory.md) visar vad prototypen från 2023 gjorde
  och var varje funktion står i den nya koden.

## Kontroll och Dataspatium

Kontroll (servern) och [Dataspatium](https://github.com/marwiss/Dataspatium)
(en dataapp som körs helt i webbläsaren) är utvecklade för att fungera
tillsammans som server och klient, och samma utgåvenummer på båda betyder
att de fungerar ihop: Dataspatium 2.0.0 fungerar med Kontroll 2.0.0.
Dataspatium lägger till en Kontroll-server som källa: appen upptäcker
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

Bortsett från de markerade tilläggen går allt Dataspatium gör mot servern
genom de tre OpenCDE-API:erna, så andra OpenCDE-klienter fungerar också, och
Kontroll betjänar vilken OpenCDE-klient som helst. De två produkterna
installeras var för sig: det här repot buntar inte Dataspatium (licenserna
skiljer sig, AGPL här och PolyForm Strict där), och Dataspatiums README
beskriver hur appen hämtas. Klientsidan beskrivs i Dataspatiums README och
dess dokumentation; parets acceptanskörningar står i
[docs/acceptance.md](../acceptance.md) här, och vad de två projekten samordnar
står i [docs/dataspatium-coordination.md](../dataspatium-coordination.md).

## Lär dig mer

- [docs/quickstart.md](quickstart.md): Kontroll och Dataspatium tillsammans på
  tjugo minuter, från tom dator till ett ärende skapat i 3D-vyn.
- [docs/client-guide.md](../client-guide.md) och [docs/examples/](../examples/):
  hur man bygger en klient, kapabilitetsdokumentet, felkoderna och körbara
  exempel med Python-biblioteket i [client/](../../client/).
- [docs/flows/](../flows/): sekvensdiagram för OAuth2- och Documents API-flödena.
- [docs/graph-schema.md](../graph-schema.md): grafmodellen.
- [docs/ifcgraph.md](../ifcgraph.md): den valfria IFC-grafmodulen och exempel på Cypher-frågor.
- [docs/ui-styleguide.md](../ui-styleguide.md): regler för serverns sidor och märket.
- [docs/acceptance.md](../acceptance.md): checklista för visuell acceptans med
  oberoende klienter (Bonsai, ifc-lite, Dataspatium).
- [docs/dataspatium-coordination.md](../dataspatium-coordination.md): vad
  Kontroll och Dataspatium delar, vad mer som samordnas och ägarens beslut.
- [docs/inventory.md](../inventory.md): funktionsinventering av prototypen
  från 2023 och status i omskrivningen, med noteringar om specifikationernas
  egenheter.
- [docs/adr/](../adr/): arkitekturbeslut (grafdatabas, opaka tokens, portabel
  Cypher, webbgränssnitt utan ramverk, repostrategi).
- [docs/security/](../security/): hotmodell, kontroller kopplade till tester,
  OWASP ASVS nivå 2-checklistan och hur skannrarna körs.
- [docs/upstream/](../upstream/): utkast till ärende och pull request för
  IfcOpenShell (inte skickade).
- [spec/SOURCES.md](../../spec/SOURCES.md): de exakta specifikationsversioner
  som servern testas mot.

Dokumentationen är på engelska; översättningar till svenska, danska, norska
(bokmål och nynorsk), finska och isländska är planerade.

## Begränsningar i korthet

- Servern implementerar BCF API 3.0, inte 2.1; bara de tre äldre
  upptäcktsaliasen under `/bcf/` finns för äldre klienter.
- Export av ett projekt som BCFzip överlåts åt klienterna; servern lagrar
  ärenden, kommentarer och viewpoints så som API:t definierar dem.
- Gemenskapsutgåvorna av Neo4j och Memgraph saknar läsbegränsade
  databasanvändare, så en exponerad Bolt-port ger full åtkomst åt den som
  har lösenordet. Porten förblir stängd om inte administratören avsiktligt
  publicerar den; en läsande fråge-ändpunkt är planerad i stället.
- IFC-grafimporten körs i en separat process med minnes- och tidsgränser
  (`OPENCDE_IFCGRAPH_*`); mycket stora modeller avvisas i stället för att
  lämnas halvimporterade.
- Webbsidorna är till för administratörer och för OAuth2- och Documents
  API-flödena; slutanvändare arbetar i en klient som Dataspatium eller Bonsai.
- Sidorna finns på den här README-filens sju språk (byt längst ned på varje
  sida); meddelanden från serverns valideringskod är på engelska tills vidare.
- Ingen extern granskning ännu. OAuch- och testssl-körningarna i
  [docs/security/pentest-howto.md](../security/pentest-howto.md) är
  operatörens steg före en produktionsdriftsättning.

## Fel och förslag

Rapportera fel och önskemål som *Issues* här på GitHub. Ange vilken
serverversion du kör (`version` i `/.well-known/kontroll` eller `/healthz`),
vilken klient du använde och `X-Request-ID` för ett misslyckat anrop;
begärandeloggen och klientens logg delar det. Bifoga inga personuppgifter och
inga hemligheter. Hur ändringar tas emot står i
[CONTRIBUTING.md](../../CONTRIBUTING.md). För en säkerhetssårbarhet, följ
[SECURITY.md](../../SECURITY.md) i stället för att öppna ett ärende.

## Utveckling

```sh
uv run pytest                    # enhets-, konformans- och säkerhetstester
uv run pytest -m integration     # startar Neo4j/Memgraph med testcontainers (kräver Docker)
uv run pytest -m e2e             # klientbiblioteket mot en körande server (kräver Docker)
uv run pytest -m ui              # Playwright + axe-core (uv sync --group ui; playwright install chromium)
uv run ruff format . && uv run ruff check .
uv run ty check opencde client/opencde_client
```

Kod och kommentarer är på engelska eftersom servern och klientbiblioteket
ska bidras till IfcOpenShell, vars konventioner (ruff, 120 kolumner) följs.
README finns på engelska, svenska, danska, norska (bokmål och nynorsk),
finska och isländska (`docs/<språk>/README.md`, samma upplägg som
Dataspatium); dokumentationen och webbgränssnittet ska finnas på samma språk,
med engelska alltid som ett val, och gemensamma termer följer Dataspatiums
ordlista. Varje push kör lint, typkontroll, testsviterna på tre
Python-versioner, webbläsartester med axe-core och statiska
säkerhetskontroller; nattliga jobb kör OWASP ZAP, Schemathesis och Trivy. Se
[CONTRIBUTING.md](../../CONTRIBUTING.md).

## Licens

Servern är licensierad under GNU Affero General Public License v3.0 eller
senare ([LICENSE](../../LICENSE)): den är servermjukvara, och AGPL:s
nätverksklausul håller förbättringar av driftsatta instanser öppna.
Klientbiblioteket i [client/](../../client/) är LGPL-3.0-or-later.
Specifikationsfilerna under [spec/](../../spec/) är © buildingSMART
International och vidaredistribueras oförändrade för testning. Se
[SECURITY.md](../../SECURITY.md) för hur en sårbarhet rapporteras och vad
projektet gör för att förbli säkert.
