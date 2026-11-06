[Svenska](../../README.md) · [Dansk](../da/README.md) · [Norsk bokmål](../nb/README.md) · **Norsk nynorsk** · [Suomi](../fi/README.md) · [Íslenska](../is/README.md) · [English](../en/README.md)

<img src="../../opencde/ui/static/icon-192.png" alt="" width="64" height="64" align="left">

# Kontroll OpenCDE-server

Kontroll er ein server for **OpenCDE-API-ane** frå buildingSMART (Foundation
API 1.0, BCF API 3.0 og Documents API 1.0), bygd på ein grafdatabase, med
webadministrasjon og ein valfri IFC-grafmodul som knyter BCF-komponentar til
bygningsdelane dei peikar på. Han voks fram av ein forskingsprototyp frå 2023
for digitale kontrollplanar i svenske byggjeløyve og vart skriven om frå
grunnen av med tryggleik som fyrste krav.

![Oversikta i administrasjonen til ein Kontroll-server: talet på brukarar, prosjekt, klientar, saker og dokument, statusen til databasen og dei siste revisjonshendingane](../images/admin-overview.png)

**Innhald**

- [Last ned og kom i gang](#last-ned-og-kom-i-gang)
- [Kva som krevst](#kva-som-krevst)
- [Kva du kan gjere](#kva-du-kan-gjere)
- [Kontroll og Dataspatium](#kontroll-og-dataspatium)
- [Lær meir](#lær-meir)
- [Avgrensingar i korte trekk](#avgrensingar-i-korte-trekk)
- [Feil og framlegg](#feil-og-framlegg)
- [Utvikling](#utvikling)
- [Lisens](#lisens)

## Last ned og kom i gang

### Snøggstart (lokalt, Docker)

1. **Last ned.** Klon repoet, eller hent det publiserte imaget
   `ghcr.io/marwiss/opencdeserver` (fleire arkitekturar, skanna og med SBOM
   ved kvar utgjeving):

   ```sh
   git clone https://github.com/marwiss/Kontroll.git
   cd Kontroll
   ```

2. **Konfigurer.** Kopier `.env.example` til `.env` og set
   `OPENCDE_GRAPH_PASSWORD` (minst 16 teikn). Kvar innstilling blir forklart i
   [.env.example](../../.env.example).
3. **Start.** `docker compose -f compose.yaml -f compose.dev.yaml up -d --build`
   startar serveren på <http://localhost:8000> og ein Neo4j-database.
   `docker compose logs -f api` viser serverloggen.
4. **Sjå deg rundt.** <http://localhost:8000/docs> er den interaktive
   API-dokumentasjonen, <http://localhost:8000/readyz> beredskapskontrollen
   og <http://localhost:7484> Neo4j Browser (Bolt på `localhost:7697`;
   utviklingsoverlegget unngår standardportane til Neo4j, som ofte er opptekne
   av ein annan Neo4j på same maskin).
5. **Legg inn demodata og logg inn.**
   `docker compose -f compose.yaml -f compose.dev.yaml exec api opencde seed`
   opprettar demobrukarar og prosjekt og skriv ut passorda deira éin gong.
   Logg inn på <http://localhost:8000/signin> som `admin` og opne `/admin`.
6. **Kople til ein klient.** Registrer appen din under *Clients* (eller lat
   han registrere seg sjølv når `OPENCDE_DYNAMIC_CLIENT_REGISTRATION=true`) og
   peik han mot `http://localhost:8000`; [Dataspatium](#kontroll-og-dataspatium)
   og Python-biblioteket i [client/](../../client/) er ferdige klientar.

Utan Docker for sjølve serveren (ein database trengst framleis):

```sh
uv sync                          # installerer Python 3.13 og alle avhengnader
uv run opencde doctor            # kontrollerer konfigurasjon og database
uv run opencde serve             # http://127.0.0.1:8000
```

### Utrulling

Éi compose-fil pluss eitt overlegg per scenario:

| Scenario | Rettleiing |
|---|---|
| Lokal test på eiga maskin | [docs/nn/deploy/local.md](deploy/local.md) |
| Offentleg https-adresse for klienttestar utan eigen server (tunnel) | [docs/nn/deploy/tunnel.md](deploy/tunnel.md) |
| Produksjon på eigen server med Caddy (automatisk TLS) og nattlege tryggingskopiar | [docs/nn/deploy/vps-caddy.md](deploy/vps-caddy.md) |
| Coolify, Dokploy, Portainer | [docs/nn/deploy/paas.md](deploy/paas.md) |
| Containerteneste pluss administrert Neo4j AuraDB eller Memgraph Cloud | [docs/nn/deploy/cloud-aura.md](deploy/cloud-aura.md) |
| Tryggingskopiering og gjenoppretting (flyttbar mellom Neo4j og Memgraph) | [docs/nn/deploy/backup.md](deploy/backup.md) |

`uv run opencde init --public-url https://cde.example.org` skriv ei
produksjons-`.env` med nye løyndomar; `opencde doctor` kontrollerer
resultatet.

### Konfigurasjon

Alt blir lese frå miljøvariablar med prefikset `OPENCDE_`, frå `.env` eller
frå Docker-løyndomar i `/run/secrets/opencde_<namn>`. Den kommenterte lista
finst i [.env.example](../../.env.example). Standardverdiane er trygge:
produksjon nektar å starte utan ei offentleg `https`-adresse og eit
databasepassord, og ingenting er ope før det er konfigurert.

## Kva som krevst

- Windows, macOS eller Linux med Docker (Desktop på Windows/macOS, Engine på
  Linux), eller Python 3.11 eller nyare med [uv](https://docs.astral.sh/uv/)
  og ein eigen Neo4j 5.26- eller Memgraph 3.14-database.
- Omtrent 1 GB minne til databasecontaineren (`NEO4J_HEAP` og
  `NEO4J_PAGECACHE` i `.env`), meir med IFC-grafmodulen.
- Lokalt: port 8000 for serveren og 7484/7697 for databasen, alle bundne til
  `127.0.0.1`. I produksjon: portane 80 og 443 nåelege frå internett og eit
  DNS-namn for serveren.
- Klientar treng ei `https`-adresse i produksjon; lokalt blir
  `http://localhost` godteke som redirect-URI med
  `OPENCDE_ALLOW_LOCALHOST_REDIRECTS=true`.

## Kva du kan gjere

- **Foundation API 1.0**: oppdaging av tenester, OAuth2 authorization code med
  PKCE for kvar klient, noverande brukar, tilbakekalling av tokens og dynamisk
  klientregistrering med offentlege klientar (av som standard).
- **BCF API 3.0**: prosjekt, extensions, saker med OData-spørjingar,
  kommentarar, viewpoints med snapshots, bitmaps og komponentar, filer,
  dokumentreferansar, dokument og hendingsloggane, alt validert mot skjemaa
  frå buildingSMART.
- **Documents API 1.0**: val og nedlasting av dokument, opplasting i delar med
  websidene til serveren for metadata og val, versjonsspørjingar med ETag.
- **Administrasjon** i nettlesaren: logg inn på `/signin` med ein
  administratorkonto og opne `/admin` for å administrere brukarar og
  prosjektrollene deira, prosjekt og BCF-extension-verdiane deira,
  OAuth2-klientar, sesjonar, revisjonsloggen, den valfrie førespurnadsloggen
  og helsekontrollane til serveren. Kvar brukar har `/account` for eige
  passord, eigne appar og eigne sesjonar. Kommandolinja
  (`uv run opencde --help`) gjer det same frå ein terminal.
- **Tillegg utanfor spesifikasjonane**, kvart merkt som det: eit
  kapabilitetsdokument på `/.well-known/kontroll` som fortel klienten kva
  tillegg som er slått på, ein stabil `code` i kvar feilkropp, ein
  førespurnadslogg for feilsøking av klientar (`/admin/requests`,
  `GET /admin/api/requests` med scopet `admin`), og IFC-grafmodulen som gjer
  opplasta IFC-modellar til grafdata knytte til BCF-komponentar.
- **Eit klientbibliotek** i Python ([client/](../../client/), LGPL) med
  køyrbare døme, og dessutan Dockerfile, compose-overlegg og eit publisert
  image for kvart utrullingsscenario.
- **Status**: alle elleve etappane i planen er gjennomførte (dei tre API-ane,
  administrasjonen, klientbiblioteket, utrulling, IFC-graf,
  akseptansesjekklista og tryggingsherdinga); bidraget til IfcOpenShell er
  enno ikkje føreslått (utkast i [docs/upstream/](../upstream/)).
  [docs/inventory.md](../inventory.md) viser kva prototypen frå 2023 gjorde og
  kvar kvar funksjon står i den nye koden.

## Kontroll og Dataspatium

Kontroll (serveren) og [Dataspatium](https://github.com/marwiss/Dataspatium)
(ein dataapp som køyrer heilt i nettlesaren) er utvikla for å verke saman som
server og klient, og same utgjevingsnummer på begge tyder at dei verkar
saman: Dataspatium 2.4.0 verkar med Kontroll 2.4.0
([snøggstart](quickstart.md)). Dataspatium legg til ein
Kontroll-server som kjelde: appen oppdagar API-ane gjennom
`/foundation/versions`, loggar inn med OAuth2 authorization code og PKCE og
registrerer seg sjølv som offentleg klient når dynamisk registrering er slått
på, listar modellane og dokumenta i prosjektet, les og skriv BCF-saker med
kommentarar og viewpoints tekne frå 3D-visinga si, lastar opp datasett, filer
og arbeidsområdepakkar gjennom Documents API, spør IFC-grafen med Cypher over
Bolt når operatøren eksponerer han, og sender `X-Request-ID` på kvart kall
slik at førespurnadsloggen her og loggen i appen viser same samtale. Appen
les kapabilitetsdokumentet til serveren for å sjå kva tillegg som er slått
på, og reagerer på feilkodane serveren legg i feilkroppane sine.

Bortsett frå dei merkte tillegga går alt Dataspatium gjer mot serveren
gjennom dei tre OpenCDE-API-ane, så andre OpenCDE-klientar verkar òg, og
Kontroll tener kvar OpenCDE-klient. Dei to produkta blir installerte kvar for
seg: dette repoet buntar ikkje Dataspatium (lisensane er ulike, AGPL her og
PolyForm Strict der), og README-fila til Dataspatium fortel korleis appen
blir henta. Klientsida er skildra i README-fila til Dataspatium og
dokumentasjonen der; akseptansekøyringane til paret står i
[docs/acceptance.md](../acceptance.md) her, og kva dei to prosjekta samordnar
står i [docs/dataspatium-coordination.md](../dataspatium-coordination.md).

## Lær meir

- [docs/nn/quickstart.md](quickstart.md): Kontroll og Dataspatium saman på tjue
  minutt, frå ei tom maskin til ei sak oppretta i 3D-visinga.
- [docs/nn/client-guide.md](client-guide.md) og [docs/examples/](../examples/):
  korleis byggje ein klient, kapabilitetsdokumentet, feilkodane og køyrbare
  døme med Python-biblioteket i [client/](../../client/).
- [docs/nn/flows/](flows/): sekvensdiagram for OAuth2- og Documents API-flytane.
- [docs/nn/graph-schema.md](graph-schema.md): grafmodellen.
- [docs/nn/ifcgraph.md](ifcgraph.md): den valfrie IFC-grafmodulen og døme på Cypher-spørjingar.
- [docs/nn/ui-styleguide.md](ui-styleguide.md): reglar for sidene til serveren og merket.
- [docs/acceptance.md](../acceptance.md): sjekkliste for visuell akseptanse
  med uavhengige klientar (Bonsai, ifc-lite, Dataspatium).
- [docs/dataspatium-coordination.md](../dataspatium-coordination.md): kva
  Kontroll og Dataspatium deler, og avgjerdene til eigaren.
- [docs/inventory.md](../inventory.md): funksjonsinventar over prototypen frå
  2023 og status i omskrivinga, med merknader om særdrag i spesifikasjonane.
- [docs/adr/](../adr/): arkitekturavgjerder (grafdatabase, opake tokens,
  portabel Cypher, webgrensesnitt utan rammeverk, repostrategi).
- [docs/nn/security/](security/): trugsmålsmodell, kontrollar knytte til
  testar, OWASP ASVS nivå 2-sjekklista, personopplysningar og lagringstid, og
  korleis skannarane blir køyrde.
- [docs/upstream/](../upstream/): utkast til sak og pull request for
  IfcOpenShell (ikkje sende).
- [spec/SOURCES.md](../../spec/SOURCES.md): dei nøyaktige
  spesifikasjonsversjonane serveren blir testa mot.

Dokumentasjonen finst på dei sju språka i denne README-fila: engelsk under
`docs/`, dei andre under `docs/<språk>/`. Prosjektloggane (akseptanse, inventar,
samordning), arkitekturavgjerdene, utkasta til IfcOpenShell og CONTRIBUTING blir
haldne på engelsk.

## Avgrensingar i korte trekk

- Serveren implementerer BCF API 3.0, ikkje 2.1; berre dei tre eldre
  oppdagingsaliasa under `/bcf/` finst for eldre klientar.
- Eksport av eit prosjekt som BCFzip blir overlaten til klientane; serveren
  lagrar saker, kommentarar og viewpoints slik API-et definerer dei.
- Community-utgåvene av Neo4j og Memgraph har ingen skriveverna
  databasebrukarar, så ein eksponert Bolt-port gjev full tilgang til den som
  har passordet. Porten held seg stengd med mindre administratoren medvite
  publiserer han; den lesande grafspørjinga i administrasjons-API-et
  (`OPENCDE_GRAPH_QUERY_ENABLED`) gjev Cypher utan porten.
- IFC-grafimporten køyrer i ein eigen prosess med minne- og tidsgrenser
  (`OPENCDE_IFCGRAPH_*`); svært store modellar blir avviste i staden for å
  bli liggjande halvt importerte.
- Websidene er for administratorar og for OAuth2- og Documents API-flytane;
  sluttbrukarar arbeider i ein klient som Dataspatium eller Bonsai.
- Sidene finst på dei sju språka i denne README-fila (byt nedst på kvar side);
  kommandolinja og feilmeldingane frå API-ane er på engelsk.
- Ingen ekstern revisjon enno. OAuch- og testssl-køyringane i
  [docs/nn/security/pentest-howto.md](security/pentest-howto.md) er stega
  operatøren tek før ei produksjonsutrulling.

## Feil og framlegg

Rapporter feil og ønske som *Issues* her på GitHub. Oppgje kva serverversjon
du køyrer (`version` i `/.well-known/kontroll` eller `/healthz`), kva klient
du brukte og `X-Request-ID` for eit mislukka kall; førespurnadsloggen og
loggen til klienten deler han. Legg ikkje ved personopplysningar eller
løyndomar. Korleis endringar blir tekne imot står i
[CONTRIBUTING.md](../../CONTRIBUTING.md). Ved ein tryggingssårbarheit, følg
[SECURITY.md](../../SECURITY.md) i staden for å opne ei sak.

## Utvikling

```sh
uv run pytest                    # einings-, konformans- og tryggingstestar
uv run pytest -m integration     # startar Neo4j/Memgraph med testcontainers (krev Docker)
uv run pytest -m e2e             # klientbiblioteket mot ein køyrande server (krev Docker)
uv run pytest -m ui              # Playwright + axe-core (uv sync --group ui; playwright install chromium)
uv run ruff format . && uv run ruff check .
uv run ty check opencde client/opencde_client
```

Kode og kommentarar er på engelsk fordi serveren og klientbiblioteket skal
bidragast til IfcOpenShell, og stilen følgjer konvensjonane der (ruff, 120
kolonnar). README finst på engelsk, svensk, dansk, norsk (bokmål og nynorsk),
finsk og islandsk (`docs/<språk>/README.md`, same oppsett som Dataspatium);
dokumentasjonen og webgrensesnittet finst på dei same språka, med
engelsk alltid som eit val, og felles termar følgjer ordlista til
Dataspatium. Kvart push køyrer lint, typekontroll, testsuitene på tre
Python-versjonar, nettlesartestar med axe-core og statiske
tryggingskontrollar; nattlege jobbar køyrer OWASP ZAP, Schemathesis og Trivy.
Sjå [CONTRIBUTING.md](../../CONTRIBUTING.md).

## Lisens

Serveren er lisensiert under GNU Affero General Public License v3.0 eller
seinare ([LICENSE](../../LICENSE)): han er serverprogramvare, og
nettverksklausulen i AGPL held forbetringar av driftssette instansar opne.
Klientbiblioteket i [client/](../../client/) er LGPL-3.0-or-later.
Spesifikasjonsfilene under [spec/](../../spec/) er © buildingSMART
International og blir vidaredistribuerte uendra for testing. Sjå
[SECURITY.md](../../SECURITY.md) for korleis ein sårbarheit blir rapportert
og kva prosjektet gjer for å halde seg trygt.
