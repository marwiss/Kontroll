<img src="../../opencde/ui/static/icon.svg" alt="" width="72" height="72" align="left">

# Kontroll OpenCDE-server

*[English](../../README.md) · [Svenska](../sv/README.md) · Dansk · [Norsk bokmål](../nb/README.md) · [Norsk nynorsk](../nn/README.md) · [Suomi](../fi/README.md) · [Íslenska](../is/README.md)*

En server til buildingSMARTs **OpenCDE-API'er**, bygget på en grafdatabase:

- **Foundation API 1.0**: tjenesteopdagelse, OAuth2 authorization code med PKCE, aktuel bruger
- **BCF API 3.0**: projekter, extensions, sager, kommentarer, viewpoints, filer, dokumentreferencer, dokumenter, hændelser
- **Documents API 1.0**: valg og download af dokumenter, upload i dele, versionsforespørgsler

samt en webgrænseflade til administration af brugere, OAuth2-klienter og
projekter, og et valgfrit IFC-grafmodul, der gør uploadede IFC-modeller til
grafdata, så BCF-komponenter kan knyttes til de bygningsdele, de peger på.

Projektet voksede ud af en forskningsprototype fra 2023, der afprøvede, om BCF
API og IFC-graf kan bære de digitale kontrolplaner, der kræves til
byggetilladelser i Sverige. Dette repo er en omskrivning af prototypen fra
bunden med samme funktioner, moderne afhængigheder og sikkerhed som første
krav. Status: **alle 11 etaper i planen er gennemført** (de tre API'er,
administrationsgrænsefladen, klientbiblioteket, udrulning, IFC-graf,
accepttjeklisten og sikkerhedshærdningen); bidraget til IfcOpenShell afventer
vedligeholdernes svar (udkast i [docs/upstream/](../upstream/)). Se
[docs/inventory.md](../inventory.md) for, hvad prototypen gjorde, og hvor hver
funktion står i den nye kode.

## Hurtig start (lokalt, Docker)

Krav: Docker (Desktop på Windows/macOS, Engine på Linux) og
[uv](https://docs.astral.sh/uv/).

```sh
git clone https://github.com/marwiss/Kontroll.git
cd Kontroll
cp .env.example .env            # sæt OPENCDE_GRAPH_PASSWORD (mindst 16 tegn)
docker compose -f compose.yaml -f compose.dev.yaml up -d --build
```

Åbn derefter <http://localhost:8000/docs> for den interaktive
API-dokumentation, <http://localhost:8000/readyz> for beredskabskontrollen og
<http://localhost:7484> for Neo4j Browser (Bolt på `localhost:7697`;
udviklingsoverlejringen undgår Neo4js standardporte, som ofte er optaget af
en anden Neo4j på samme maskine). `docker compose logs -f api` viser
serverloggen.

Uden Docker til selve serveren (en database er stadig nødvendig):

```sh
uv sync                          # installerer Python 3.13 og alle afhængigheder
uv run opencde doctor            # kontrollerer konfiguration og database
uv run opencde serve             # http://127.0.0.1:8000
```

## Udrulning

Én compose-fil plus én overlejring pr. scenarie, og et udgivet image til flere
arkitekturer (`ghcr.io/marwiss/opencdeserver`, scannet og med SBOM ved hver
udgivelse):

| Scenarie | Vejledning |
|---|---|
| Lokal test på din egen maskine | [docs/deploy/local.md](../deploy/local.md) |
| Offentlig https-adresse til klienttest uden egen server (tunnel) | [docs/deploy/tunnel.md](../deploy/tunnel.md) |
| Produktion på egen server med Caddy (automatisk TLS) og natlige sikkerhedskopier | [docs/deploy/vps-caddy.md](../deploy/vps-caddy.md) |
| Coolify, Dokploy, Portainer | [docs/deploy/paas.md](../deploy/paas.md) |
| Containertjeneste plus administreret Neo4j AuraDB eller Memgraph Cloud | [docs/deploy/cloud-aura.md](../deploy/cloud-aura.md) |
| Sikkerhedskopiering og gendannelse (flytbar mellem Neo4j og Memgraph) | [docs/deploy/backup.md](../deploy/backup.md) |

`uv run opencde init --public-url https://cde.example.org` skriver en
produktions-`.env` med nye hemmeligheder; `opencde doctor` kontrollerer
resultatet.

## Konfiguration

Alt læses fra miljøvariabler med præfikset `OPENCDE_`, fra `.env` eller fra
Docker-hemmeligheder i `/run/secrets/opencde_<navn>`. Den kommenterede liste
findes i [.env.example](../../.env.example). Standardværdierne er sikre:
produktion nægter at starte uden en offentlig `https`-adresse og et
databasekodeord.

## Dokumentation

Dokumentationen er på engelsk; oversættelser til svensk, dansk, norsk (bokmål
og nynorsk), finsk og islandsk er planlagt.

- [docs/inventory.md](../inventory.md): funktionsoversigt over prototypen fra
  2023 og status i omskrivningen, med noter om specifikationernes særheder
- [docs/client-guide.md](../client-guide.md) og [docs/examples/](../examples/):
  hvordan man bygger en klient; kørbare eksempler med Python-biblioteket i [client/](../../client/)
- [docs/flows/](../flows/): sekvensdiagrammer for OAuth2- og Documents API-forløbene
- [docs/graph-schema.md](../graph-schema.md): grafmodellen
- [docs/ifcgraph.md](../ifcgraph.md): det valgfrie IFC-grafmodul og eksempler på Cypher-forespørgsler
- [docs/ui-styleguide.md](../ui-styleguide.md): regler for serverens sider
- [docs/acceptance.md](../acceptance.md): tjekliste til visuel accept med
  uafhængige klienter (Bonsai, ifc-lite, Dataspatium)
- [docs/dataspatium-coordination.md](../dataspatium-coordination.md): hvad
  Kontroll og Dataspatium deler, og hvad mere der samordnes, med ejerens beslutninger
- [docs/adr/](../adr/): arkitekturbeslutninger (grafdatabase, opake tokens,
  portabel Cypher, webgrænseflade uden frameworks, repostrategi)
- [docs/security/](../security/): trusselsmodel, kontroller knyttet til
  tests, OWASP ASVS niveau 2-tjeklisten og hvordan scannerne køres
- [docs/upstream/](../upstream/): udkast til issue og pull request til
  IfcOpenShell (ikke sendt)
- [spec/SOURCES.md](../../spec/SOURCES.md): de præcise specifikationsversioner,
  serveren testes mod

## Administration

Log ind på `/signin` med en administratorkonto, og åbn `/admin` for at
administrere brugere og deres projektroller, projekter og deres BCF-extension-
værdier, OAuth2-klienter, sessioner, revisionsloggen, den valgfrie
forespørgselslog og serverens sundhedstjek. Hver bruger har `/account` til sit
eget kodeord, sine apps og sine sessioner. Kommandolinjen
(`uv run opencde --help`) gør det samme fra en terminal, og
administrationsklienter med scopet `admin` kan læse forespørgselsloggen på
`/admin/api/requests`.

## Kontroll og Dataspatium

Kontroll (serveren) og [Dataspatium](https://github.com/marwiss/Dataspatium)
(en data-app, der kører helt i browseren) er udviklet til at arbejde sammen
som server og klient. Dataspatium tilføjer en Kontroll-server som kilde:
appen opdager API'erne gennem `/foundation/versions`, logger ind med OAuth2
authorization code og PKCE og registrerer sig selv som offentlig klient, når
selvregistrering er slået til, lister projektets modeller og dokumenter,
læser og skriver BCF-sager med kommentarer og viewpoints taget fra sin
3D-visning, uploader datasæt, filer og arbejdsområdepakker gennem Documents
API, forespørger IFC-grafen med Cypher over Bolt, når operatøren eksponerer
den, og sender `X-Request-ID` på hvert kald, så forespørgselsloggen her og
loggen i appen viser den samme samtale. Appen læser serverens
kapabilitetsdokument (`/.well-known/kontroll`) for at se, hvilke udvidelser
der er slået til, og reagerer på de stabile fejlkoder, serveren lægger i sine
fejlsvar. Bortset fra grafforespørgslerne, administrations-API'et,
kapabilitetsdokumentet og fejlkoderne, som er udvidelser uden for
specifikationerne, går alt, hvad Dataspatium gør mod serveren, gennem de tre
OpenCDE-API'er, så andre OpenCDE-klienter virker også, og Kontroll betjener
enhver OpenCDE-klient. De to produkter installeres hver for sig: dette repo
bundter ikke Dataspatium (licenserne er forskellige, AGPL her og PolyForm
Strict der), og Dataspatiums README beskriver, hvordan appen hentes.
Klientsiden beskrives i Dataspatiums README og dens dokumentation
(`docs/kallor.md`, `docs/cad-bim.md`); parrets acceptkørsler står i
[docs/acceptance.md](../acceptance.md) her, og hvad de to projekter
samordner, står i
[docs/dataspatium-coordination.md](../dataspatium-coordination.md).

## Udvikling

```sh
uv run pytest                    # enheds-, konformans- og sikkerhedstests
uv run pytest -m integration     # starter Neo4j/Memgraph med testcontainers (kræver Docker)
uv run pytest -m e2e             # klientbiblioteket mod en kørende server (kræver Docker)
uv run pytest -m ui              # Playwright + axe-core (uv sync --group ui; playwright install chromium)
uv run ruff format . && uv run ruff check .
uv run ty check opencde client/opencde_client
```

Kode og kommentarer er på engelsk, fordi serveren og klientbiblioteket skal
bidrages til IfcOpenShell, hvis konventioner (ruff, 120 kolonner) følges.
README findes på engelsk, svensk, dansk, norsk (bokmål og nynorsk), finsk og
islandsk (`docs/<sprog>/README.md`, samme opbygning som Dataspatium);
dokumentationen og webgrænsefladen skal findes på de samme sprog, med engelsk
altid som en mulighed, og fælles termer følger Dataspatiums ordliste.

## Sikkerhed

Se [SECURITY.md](../../SECURITY.md) for, hvordan en sårbarhed rapporteres, og
hvad projektet gør for at forblive sikkert.

## Licens

Serveren er licenseret under GNU Affero General Public License v3.0 eller
senere ([LICENSE](../../LICENSE)): den er serversoftware, og AGPL's
netværksklausul holder forbedringer af hostede instanser åbne.
Klientbiblioteket i [client/](../../client/) er LGPL-3.0-or-later.
Specifikationsfilerne under [spec/](../../spec/) er © buildingSMART
International og videredistribueres uændret til test.
