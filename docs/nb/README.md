<img src="../../opencde/ui/static/icon.svg" alt="" width="72" height="72" align="left">

# Kontroll OpenCDE-server

*[English](../../README.md) · [Svenska](../sv/README.md) · [Dansk](../da/README.md) · Norsk · [Suomi](../fi/README.md) · [Íslenska](../is/README.md)*

En server for buildingSMARTs **OpenCDE-API-er**, bygget på en grafdatabase:

- **Foundation API 1.0**: tjenesteoppdagelse, OAuth2 authorization code med PKCE, gjeldende bruker
- **BCF API 3.0**: prosjekter, extensions, saker, kommentarer, viewpoints, filer, dokumentreferanser, dokumenter, hendelser
- **Documents API 1.0**: valg og nedlasting av dokumenter, opplasting i deler, versjonsspørringer

samt et webgrensesnitt for administrasjon av brukere, OAuth2-klienter og
prosjekter, og en valgfri IFC-grafmodul som gjør opplastede IFC-modeller til
grafdata, slik at BCF-komponenter kan knyttes til bygningsdelene de peker på.

Prosjektet vokste fram av en forskningsprototyp fra 2023 som prøvde ut om BCF
API og IFC-graf kan bære de digitale kontrollplanene som kreves for
byggetillatelser i Sverige. Dette repoet er en omskriving av prototypen fra
grunnen av, med samme funksjoner, moderne avhengigheter og sikkerhet som
første krav. Status: **alle 11 etapper i planen er gjennomført** (de tre
API-ene, administrasjonsgrensesnittet, klientbiblioteket, utrulling, IFC-graf,
akseptansesjekklisten og sikkerhetsherdingen); bidraget til IfcOpenShell
venter på svar fra vedlikeholderne (utkast i [docs/upstream/](../upstream/)).
Se [docs/inventory.md](../inventory.md) for hva prototypen gjorde og hvor hver
funksjon står i den nye koden.

## Hurtigstart (lokalt, Docker)

Krav: Docker (Desktop på Windows/macOS, Engine på Linux) og
[uv](https://docs.astral.sh/uv/).

```sh
git clone https://github.com/marwiss/Kontroll.git
cd Kontroll
cp .env.example .env            # sett OPENCDE_GRAPH_PASSWORD (minst 16 tegn)
docker compose -f compose.yaml -f compose.dev.yaml up -d --build
```

Åpne deretter <http://localhost:8000/docs> for den interaktive
API-dokumentasjonen, <http://localhost:8000/readyz> for beredskapskontrollen
og <http://localhost:7484> for Neo4j Browser (Bolt på `localhost:7697`;
utviklingsoverlegget unngår Neo4js standardporter, som ofte er opptatt av en
annen Neo4j på samme maskin). `docker compose logs -f api` viser serverloggen.

Uten Docker for selve serveren (en database trengs fortsatt):

```sh
uv sync                          # installerer Python 3.13 og alle avhengigheter
uv run opencde doctor            # kontrollerer konfigurasjon og database
uv run opencde serve             # http://127.0.0.1:8000
```

## Utrulling

Én compose-fil pluss ett overlegg per scenario, og et publisert image for
flere arkitekturer (`ghcr.io/marwiss/opencdeserver`, skannet og med SBOM ved
hver utgivelse):

| Scenario | Veiledning |
|---|---|
| Lokal test på egen maskin | [docs/deploy/local.md](../deploy/local.md) |
| Offentlig https-adresse for klienttester uten egen server (tunnel) | [docs/deploy/tunnel.md](../deploy/tunnel.md) |
| Produksjon på egen server med Caddy (automatisk TLS) og nattlige sikkerhetskopier | [docs/deploy/vps-caddy.md](../deploy/vps-caddy.md) |
| Coolify, Dokploy, Portainer | [docs/deploy/paas.md](../deploy/paas.md) |
| Containertjeneste pluss administrert Neo4j AuraDB eller Memgraph Cloud | [docs/deploy/cloud-aura.md](../deploy/cloud-aura.md) |
| Sikkerhetskopiering og gjenoppretting (flyttbar mellom Neo4j og Memgraph) | [docs/deploy/backup.md](../deploy/backup.md) |

`uv run opencde init --public-url https://cde.example.org` skriver en
produksjons-`.env` med nye hemmeligheter; `opencde doctor` kontrollerer
resultatet.

## Konfigurasjon

Alt leses fra miljøvariabler med prefikset `OPENCDE_`, fra `.env` eller fra
Docker-hemmeligheter i `/run/secrets/opencde_<navn>`. Den kommenterte listen
finnes i [.env.example](../../.env.example). Standardverdiene er trygge:
produksjon nekter å starte uten en offentlig `https`-adresse og et
databasepassord.

## Dokumentasjon

Dokumentasjonen er på engelsk; oversettelser til svensk, dansk, norsk, finsk
og islandsk er planlagt.

- [docs/inventory.md](../inventory.md): funksjonsinventar over prototypen fra
  2023 og status i omskrivingen, med merknader om særtrekk i spesifikasjonene
- [docs/client-guide.md](../client-guide.md) og [docs/examples/](../examples/):
  hvordan bygge en klient; kjørbare eksempler med Python-biblioteket i [client/](../../client/)
- [docs/flows/](../flows/): sekvensdiagrammer for OAuth2- og Documents API-flytene
- [docs/graph-schema.md](../graph-schema.md): grafmodellen
- [docs/ifcgraph.md](../ifcgraph.md): den valgfrie IFC-grafmodulen og eksempler på Cypher-spørringer
- [docs/ui-styleguide.md](../ui-styleguide.md): regler for serverens sider
- [docs/acceptance.md](../acceptance.md): sjekkliste for visuell akseptanse
  med uavhengige klienter (Bonsai, ifc-lite, Dataspatium)
- [docs/dataspatium-coordination.md](../dataspatium-coordination.md): hva
  Kontroll og Dataspatium deler og hva mer som samordnes, med eierens beslutninger
- [docs/adr/](../adr/): arkitekturbeslutninger (grafdatabase, opake tokens,
  portabel Cypher, webgrensesnitt uten rammeverk, repostrategi)
- [docs/security/](../security/): trusselmodell, kontroller knyttet til
  tester, OWASP ASVS nivå 2-sjekklisten og hvordan skannerne kjøres
- [docs/upstream/](../upstream/): utkast til sak og pull request for
  IfcOpenShell (ikke sendt)
- [spec/SOURCES.md](../../spec/SOURCES.md): de nøyaktige
  spesifikasjonsversjonene serveren testes mot

## Administrasjon

Logg inn på `/signin` med en administratorkonto og åpne `/admin` for å
administrere brukere og prosjektrollene deres, prosjekter og BCF-extension-
verdiene deres, OAuth2-klienter, sesjoner, revisjonsloggen, den valgfrie
forespørselsloggen og serverens helsekontroller. Hver bruker har `/account`
for eget passord, egne apper og egne sesjoner. Kommandolinjen
(`uv run opencde --help`) gjør det samme fra en terminal, og
administrasjonsklienter med scopet `admin` kan lese forespørselsloggen på
`/admin/api/requests`.

## Kontroll og Dataspatium

Kontroll (serveren) og [Dataspatium](https://github.com/marwiss/Dataspatium)
(en dataapp som kjører helt i nettleseren) er utviklet for å virke sammen som
server og klient. Dataspatium legger til en Kontroll-server som kilde: appen
oppdager API-ene gjennom `/foundation/versions`, logger inn med OAuth2
authorization code og PKCE og registrerer seg selv som offentlig klient når
selvregistrering er slått på, lister prosjektets modeller og dokumenter, leser
og skriver BCF-saker med kommentarer og viewpoints tatt fra 3D-visningen sin,
laster opp datasett, filer og arbeidsområdepakker gjennom Documents API, spør
IFC-grafen med Cypher over Bolt når operatøren eksponerer den, og sender
`X-Request-ID` på hvert kall slik at forespørselsloggen her og loggen i appen
viser samme samtale. Appen leser serverens kapabilitetsdokument
(`/.well-known/kontroll`) for å se hvilke tillegg som er slått på, og
reagerer på de stabile feilkodene serveren legger i feilkroppene sine.
Bortsett fra grafspørringene, administrasjons-API-et, kapabilitetsdokumentet
og feilkodene, som er tillegg utenfor spesifikasjonene, går alt Dataspatium
gjør mot serveren gjennom de tre OpenCDE-API-ene, så andre OpenCDE-klienter
virker også, og Kontroll betjener enhver OpenCDE-klient. De to produktene
installeres hver for seg: dette repoet bunter ikke Dataspatium (lisensene er
forskjellige, AGPL her og PolyForm Strict der), og Dataspatiums README
beskriver hvordan appen hentes. Klientsiden beskrives i Dataspatiums README
og dokumentasjonen der (`docs/kallor.md`, `docs/cad-bim.md`); parets
akseptansekjøringer står i [docs/acceptance.md](../acceptance.md) her, og hva
de to prosjektene samordner står i
[docs/dataspatium-coordination.md](../dataspatium-coordination.md).

## Utvikling

```sh
uv run pytest                    # enhets-, konformans- og sikkerhetstester
uv run pytest -m integration     # starter Neo4j/Memgraph med testcontainers (krever Docker)
uv run pytest -m e2e             # klientbiblioteket mot en kjørende server (krever Docker)
uv run pytest -m ui              # Playwright + axe-core (uv sync --group ui; playwright install chromium)
uv run ruff format . && uv run ruff check .
uv run ty check opencde client/opencde_client
```

Kode og kommentarer er på engelsk fordi serveren og klientbiblioteket skal
bidras til IfcOpenShell, hvis konvensjoner (ruff, 120 kolonner) følges.
README finnes på engelsk, svensk, dansk, norsk, finsk og islandsk
(`docs/<språk>/README.md`, samme oppsett som Dataspatium); dokumentasjonen og
webgrensesnittet skal finnes på de samme seks språkene, med engelsk alltid som
et valg, og felles termer følger Dataspatiums ordliste.

## Sikkerhet

Se [SECURITY.md](../../SECURITY.md) for hvordan en sårbarhet rapporteres og
hva prosjektet gjør for å holde seg sikkert.

## Lisens

Serveren er lisensiert under GNU Affero General Public License v3.0 eller
senere ([LICENSE](../../LICENSE)): den er serverprogramvare, og AGPLs
nettverksklausul holder forbedringer av driftssatte instanser åpne.
Klientbiblioteket i [client/](../../client/) er LGPL-3.0-or-later.
Spesifikasjonsfilene under [spec/](../../spec/) er © buildingSMART
International og videredistribueres uendret for testing.
