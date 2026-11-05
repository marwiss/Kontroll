<img src="opencde/ui/static/icon.svg" alt="" width="72" height="72" align="left">

# Kontroll OpenCDE-server

*Svenska · [English](README.md)*

En server för buildingSMARTs **OpenCDE-API:er**, byggd på en grafdatabas:

- **Foundation API 1.0**: tjänsteupptäckt, OAuth2 authorization code med PKCE, aktuell användare
- **BCF API 3.0**: projekt, extensions, ärenden, kommentarer, viewpoints, filer, dokumentreferenser, dokument, händelser
- **Documents API 1.0**: val och nedladdning av dokument, uppladdning i delar, versionsfrågor

samt ett webbgränssnitt för administration av användare, OAuth2-klienter och
projekt, och en valfri IFC-grafmodul som gör uppladdade IFC-modeller till
grafdata så att BCF-komponenter kan kopplas till de byggdelar de pekar på.

Projektet växte fram ur en forskningsprototyp från 2023 som prövade om BCF
API och IFC-graf kan bära de digitala kontrollplaner som krävs för bygglov i
Sverige. Det här repot är en omskrivning av prototypen från grunden med samma
funktioner, moderna beroenden och säkerhet som första krav. Status: **alla
11 etapper i planen är genomförda** (de tre API:erna, administrationsgräns-
snittet, klientbiblioteket, driftsättning, IFC-graf, acceptanschecklistan och
säkerhetshärdningen); bidraget till IfcOpenShell väntar på underhållarnas
svar (utkast i [docs/upstream/](docs/upstream/)). Se
[docs/inventory.md](docs/inventory.md) för vad prototypen gjorde och var
varje funktion står i den nya koden.

## Snabbstart (lokalt, Docker)

Krav: Docker (Desktop på Windows/macOS, Engine på Linux) och
[uv](https://docs.astral.sh/uv/).

```sh
git clone https://github.com/marwiss/Kontroll.git
cd Kontroll
cp .env.example .env            # sätt OPENCDE_GRAPH_PASSWORD (minst 16 tecken)
docker compose -f compose.yaml -f compose.dev.yaml up -d --build
```

Öppna sedan <http://localhost:8000/docs> för den interaktiva API-dokumentationen,
<http://localhost:8000/readyz> för beredskapskontrollen och
<http://localhost:7484> för Neo4j Browser (Bolt på `localhost:7697`;
utvecklingsöverlagringen undviker Neo4j:s standardportar, som ofta upptas av en
annan Neo4j på samma dator). `docker compose logs -f api` visar serverloggen.

Utan Docker för själva servern (en databas behövs fortfarande):

```sh
uv sync                          # installerar Python 3.13 och alla beroenden
uv run opencde doctor            # kontrollerar konfiguration och databas
uv run opencde serve             # http://127.0.0.1:8000
```

## Driftsättning

En compose-fil plus en överlagring per scenario, och en publicerad image för
flera arkitekturer (`ghcr.io/marwiss/opencdeserver`, skannad och med SBOM vid
varje release):

| Scenario | Guide |
|---|---|
| Lokalt test på din dator | [docs/deploy/local.md](docs/deploy/local.md) |
| Publik https-adress för klienttester utan egen server (tunnel) | [docs/deploy/tunnel.md](docs/deploy/tunnel.md) |
| Produktion på egen server med Caddy (automatisk TLS) och nattliga säkerhetskopior | [docs/deploy/vps-caddy.md](docs/deploy/vps-caddy.md) |
| Coolify, Dokploy, Portainer | [docs/deploy/paas.md](docs/deploy/paas.md) |
| Containertjänst plus hanterad Neo4j AuraDB eller Memgraph Cloud | [docs/deploy/cloud-aura.md](docs/deploy/cloud-aura.md) |
| Säkerhetskopiering och återställning (flyttbar mellan Neo4j och Memgraph) | [docs/deploy/backup.md](docs/deploy/backup.md) |

`uv run opencde init --public-url https://cde.example.org` skriver en
produktions-`.env` med nya hemligheter; `opencde doctor` kontrollerar
resultatet.

## Konfiguration

Allt läses från miljövariabler med prefixet `OPENCDE_`, från `.env` eller
från Docker-hemligheter i `/run/secrets/opencde_<namn>`. Den kommenterade
listan finns i [.env.example](.env.example). Standardvärdena är säkra:
produktion vägrar starta utan en publik `https`-adress och ett
databaslösenord.

## Dokumentation

Dokumentationen är på engelska; översättningar till svenska, norska, danska,
finska och isländska är planerade.

- [docs/inventory.md](docs/inventory.md): funktionsinventering av prototypen
  från 2023 och status i omskrivningen, med noteringar om specifikationernas
  egenheter
- [docs/client-guide.md](docs/client-guide.md) och [docs/examples/](docs/examples/):
  hur man bygger en klient; körbara exempel med Python-biblioteket i [client/](client/)
- [docs/flows/](docs/flows/): sekvensdiagram för OAuth2- och Documents API-flödena
- [docs/graph-schema.md](docs/graph-schema.md): grafmodellen
- [docs/ifcgraph.md](docs/ifcgraph.md): den valfria IFC-grafmodulen och exempel på Cypher-frågor
- [docs/ui-styleguide.md](docs/ui-styleguide.md): regler för serverns sidor
- [docs/acceptance.md](docs/acceptance.md): checklista för visuell acceptans
  med oberoende klienter (Bonsai, ifc-lite, Dataspatium)
- [docs/adr/](docs/adr/): arkitekturbeslut (grafdatabas, opaka tokens,
  portabel Cypher, webbgränssnitt utan ramverk, repostrategi)
- [docs/security/](docs/security/): hotmodell, kontroller kopplade till
  tester, OWASP ASVS nivå 2-checklistan och hur skannrarna körs
- [docs/upstream/](docs/upstream/): utkast till ärende och pull request för
  IfcOpenShell (inte skickade)
- [spec/SOURCES.md](spec/SOURCES.md): de exakta specifikationsversioner som
  servern testas mot

## Administration

Logga in på `/signin` med ett administratörskonto och öppna `/admin` för att
hantera användare och deras projektroller, projekt och deras BCF-
extensionsvärden, OAuth2-klienter, sessioner, revisionsloggen, den valfria
begärandeloggen och serverns hälsokontroller. Varje användare har `/account`
för sitt eget lösenord, sina appar och sina sessioner. Kommandoraden
(`uv run opencde --help`) gör samma sak från en terminal, och
administrationsklienter med scopet `admin` kan läsa begärandeloggen på
`/admin/api/requests`.

## Kontroll och Dataspatium

Kontroll (servern) och [Dataspatium](https://github.com/marwiss/Dataspatium)
(en dataapp som körs helt i webbläsaren) är utvecklade för att fungera
tillsammans som server och klient. Dataspatium lägger till en Kontroll-server
som källa: appen upptäcker API:erna genom `/foundation/versions`, loggar in
med OAuth2 authorization code och PKCE och registrerar sig själv som publik
klient när dynamisk registrering är påslagen, listar projektets modeller och
dokument, läser och skriver BCF-ärenden med kommentarer och viewpoints tagna
ur sin 3D-vy, laddar upp datamängder, filer och arbetsytepaket genom
Documents API, frågar IFC-grafen med Cypher över Bolt när operatören exponerar
den, och skickar `X-Request-ID` på varje anrop så att begärandeloggen här och
loggen i appen visar samma samtal. Bortsett från graffrågorna och
administrations-API:t, som är tillägg utanför specifikationerna, går allt
Dataspatium gör mot servern genom de tre OpenCDE-API:erna, så andra
OpenCDE-klienter fungerar också, och Kontroll betjänar vilken OpenCDE-klient
som helst. Klientsidan beskrivs i Dataspatiums README och dess dokumentation
(`docs/kallor.md`, `docs/cad-bim.md`); parets acceptanskörningar står i
[docs/acceptance.md](docs/acceptance.md) här.

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
README finns på engelska och svenska; dokumentationen och webbgränssnittet
ska finnas på svenska, norska, danska, finska, isländska och engelska, med
engelska alltid som ett val.

## Säkerhet

Se [SECURITY.md](SECURITY.md) för hur en sårbarhet rapporteras och vad
projektet gör för att förbli säkert.

## Licens

Servern är licensierad under GNU Affero General Public License v3.0 eller
senare ([LICENSE](LICENSE)): den är servermjukvara, och AGPL:s nätverksklausul
håller förbättringar av driftsatta instanser öppna. Klientbiblioteket i
[client/](client/) är LGPL-3.0-or-later. Specifikationsfilerna under
[spec/](spec/) är © buildingSMART International och vidaredistribueras
oförändrade för testning.
