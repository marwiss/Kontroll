[Svenska](../../README.md) · **Dansk** · [Norsk bokmål](../nb/README.md) · [Norsk nynorsk](../nn/README.md) · [Suomi](../fi/README.md) · [Íslenska](../is/README.md) · [English](../en/README.md)

<img src="../../opencde/ui/static/icon-192.png" alt="" width="64" height="64" align="left">

# Kontroll OpenCDE-server

Kontroll er en server til buildingSMARTs **OpenCDE-API'er** (Foundation API
1.0, BCF API 3.0 og Documents API 1.0), bygget på en grafdatabase, med
webadministration og et valgfrit IFC-grafmodul, der knytter BCF-komponenter
til de bygningsdele, de peger på. Den voksede ud af en forskningsprototype
fra 2023 til digitale kontrolplaner i svenske byggetilladelser og blev
skrevet om fra bunden med sikkerhed som første krav.

![Administrationens oversigt i en Kontroll-server: antal brugere, projekter, klienter, sager og dokumenter, databasens status og de seneste revisionshændelser](../images/admin-overview.png)

**Indhold**

- [Download og kom i gang](#download-og-kom-i-gang)
- [Hvad der kræves](#hvad-der-kræves)
- [Hvad du kan](#hvad-du-kan)
- [Kontroll og Dataspatium](#kontroll-og-dataspatium)
- [Lær mere](#lær-mere)
- [Begrænsninger i korte træk](#begrænsninger-i-korte-træk)
- [Fejl og forslag](#fejl-og-forslag)
- [Udvikling](#udvikling)
- [Licens](#licens)

## Download og kom i gang

### Hurtig start (lokalt, Docker)

1. **Download.** Klon repoet, eller hent det udgivne image
   `ghcr.io/marwiss/opencdeserver` (flere arkitekturer, scannet og med SBOM
   ved hver udgivelse):

   ```sh
   git clone https://github.com/marwiss/Kontroll.git
   cd Kontroll
   ```

2. **Konfigurer.** Kopiér `.env.example` til `.env`, og sæt
   `OPENCDE_GRAPH_PASSWORD` (mindst 16 tegn). Hver indstilling forklares i
   [.env.example](../../.env.example).
3. **Start.** `docker compose -f compose.yaml -f compose.dev.yaml up -d --build`
   starter serveren på <http://localhost:8000> og en Neo4j-database.
   `docker compose logs -f api` viser serverloggen.
4. **Se dig omkring.** <http://localhost:8000/docs> er den interaktive
   API-dokumentation, <http://localhost:8000/readyz> beredskabskontrollen og
   <http://localhost:7484> Neo4j Browser (Bolt på `localhost:7697`;
   udviklingsoverlejringen undgår Neo4js standardporte, som ofte er optaget af
   en anden Neo4j på samme maskine).
5. **Tilføj demodata, og log ind.**
   `docker compose -f compose.yaml -f compose.dev.yaml exec api opencde seed`
   opretter demobrugere og projekter og udskriver deres kodeord én gang. Log
   ind på <http://localhost:8000/signin> som `admin`, og åbn `/admin`.
6. **Tilslut en klient.** Registrér din app under *Clients* (eller lad den
   registrere sig selv, når `OPENCDE_DYNAMIC_CLIENT_REGISTRATION=true`), og
   peg den mod `http://localhost:8000`; [Dataspatium](#kontroll-og-dataspatium)
   og Python-biblioteket i [client/](../../client/) er færdige klienter.

Uden Docker til selve serveren (en database er stadig nødvendig):

```sh
uv sync                          # installerer Python 3.13 og alle afhængigheder
uv run opencde doctor            # kontrollerer konfiguration og database
uv run opencde serve             # http://127.0.0.1:8000
```

### Udrulning

Én compose-fil plus én overlejring pr. scenarie:

| Scenarie | Vejledning |
|---|---|
| Lokal test på din egen maskine | [docs/da/deploy/local.md](deploy/local.md) |
| Offentlig https-adresse til klienttest uden egen server (tunnel) | [docs/da/deploy/tunnel.md](deploy/tunnel.md) |
| Produktion på egen server med Caddy (automatisk TLS) og natlige sikkerhedskopier | [docs/da/deploy/vps-caddy.md](deploy/vps-caddy.md) |
| Coolify, Dokploy, Portainer | [docs/da/deploy/paas.md](deploy/paas.md) |
| Containertjeneste plus administreret Neo4j AuraDB eller Memgraph Cloud | [docs/da/deploy/cloud-aura.md](deploy/cloud-aura.md) |
| Sikkerhedskopiering og gendannelse (flytbar mellem Neo4j og Memgraph) | [docs/da/deploy/backup.md](deploy/backup.md) |

`uv run opencde init --public-url https://cde.example.org` skriver en
produktions-`.env` med nye hemmeligheder; `opencde doctor` kontrollerer
resultatet.

### Konfiguration

Alt læses fra miljøvariabler med præfikset `OPENCDE_`, fra `.env` eller fra
Docker-hemmeligheder i `/run/secrets/opencde_<navn>`. Den kommenterede liste
findes i [.env.example](../../.env.example). Standardværdierne er sikre:
produktion nægter at starte uden en offentlig `https`-adresse og et
databasekodeord, og intet er åbent, før det er konfigureret.

## Hvad der kræves

- Windows, macOS eller Linux med Docker (Desktop på Windows/macOS, Engine på
  Linux), eller Python 3.11 eller nyere med [uv](https://docs.astral.sh/uv/)
  og en egen Neo4j 5.26- eller Memgraph 3.14-database.
- Omkring 1 GB hukommelse til databasecontaineren (`NEO4J_HEAP` og
  `NEO4J_PAGECACHE` i `.env`), mere med IFC-grafmodulet.
- Lokalt: port 8000 til serveren og 7484/7697 til databasen, alle bundet til
  `127.0.0.1`. I produktion: portene 80 og 443 tilgængelige fra internettet og
  et DNS-navn til serveren.
- Klienter har brug for en `https`-adresse i produktion; lokalt accepteres
  `http://localhost` som redirect-URI med `OPENCDE_ALLOW_LOCALHOST_REDIRECTS=true`.

## Hvad du kan

- **Foundation API 1.0**: tjenesteopdagelse, OAuth2 authorization code med
  PKCE for hver klient, aktuel bruger, tilbagekaldelse af tokens og dynamisk
  klientregistrering med offentlige klienter (slået fra som standard).
- **BCF API 3.0**: projekter, extensions, sager med OData-forespørgsler,
  kommentarer, viewpoints med snapshots, bitmaps og komponenter, filer,
  dokumentreferencer, dokumenter og hændelsesloggene, alt valideret mod
  buildingSMARTs skemaer.
- **Documents API 1.0**: valg og download af dokumenter, upload i dele med
  serverens websider til metadata og valg, versionsforespørgsler med ETag.
- **Administration** i browseren: log ind på `/signin` med en
  administratorkonto, og åbn `/admin` for at administrere brugere og deres
  projektroller, projekter og deres BCF-extension-værdier, OAuth2-klienter,
  sessioner, revisionsloggen, den valgfrie forespørgselslog og serverens
  sundhedstjek. Hver bruger har `/account` til sit eget kodeord, sine apps og
  sine sessioner. Kommandolinjen (`uv run opencde --help`) gør det samme fra
  en terminal.
- **Udvidelser uden for specifikationerne**, hver markeret som sådan: et
  kapabilitetsdokument på `/.well-known/kontroll`, der fortæller klienten,
  hvilke udvidelser der er slået til, en stabil `code` i hvert fejlsvar, en
  forespørgselslog til fejlsøgning af klienter (`/admin/requests`,
  `GET /admin/api/requests` med scopet `admin`), og IFC-grafmodulet, der gør
  uploadede IFC-modeller til grafdata knyttet til BCF-komponenter.
- **Et klientbibliotek** i Python ([client/](../../client/), LGPL) med
  kørbare eksempler, samt Dockerfile, compose-overlejringer og et udgivet
  image til hvert udrulningsscenarie.
- **Status**: alle elleve etaper i planen er gennemført (de tre API'er,
  administrationen, klientbiblioteket, udrulning, IFC-graf, accepttjeklisten
  og sikkerhedshærdningen); bidraget til IfcOpenShell afventer
  vedligeholdernes svar (udkast i [docs/upstream/](../upstream/)).
  [docs/inventory.md](../inventory.md) viser, hvad prototypen fra 2023
  gjorde, og hvor hver funktion står i den nye kode.

## Kontroll og Dataspatium

Kontroll (serveren) og [Dataspatium](https://github.com/marwiss/Dataspatium)
(en data-app, der kører helt i browseren) er udviklet til at arbejde sammen
som server og klient, og samme udgivelsesnummer på begge betyder, at de
fungerer sammen: Dataspatium 2.2.0 fungerer med Kontroll 2.2.0
([hurtig start](quickstart.md)). Dataspatium
tilføjer en Kontroll-server som kilde: appen opdager API'erne gennem
`/foundation/versions`, logger ind med OAuth2 authorization code og PKCE og
registrerer sig selv som offentlig klient, når dynamisk registrering er slået
til, lister projektets modeller og dokumenter, læser og skriver BCF-sager med
kommentarer og viewpoints taget fra sin 3D-visning, uploader datasæt, filer og
arbejdsområdepakker gennem Documents API, forespørger IFC-grafen med Cypher
over Bolt, når operatøren eksponerer den, og sender `X-Request-ID` på hvert
kald, så forespørgselsloggen her og loggen i appen viser den samme samtale.
Appen læser serverens kapabilitetsdokument for at se, hvilke udvidelser der
er slået til, og reagerer på de fejlkoder, serveren lægger i sine fejlsvar.

Bortset fra de markerede udvidelser går alt, hvad Dataspatium gør mod
serveren, gennem de tre OpenCDE-API'er, så andre OpenCDE-klienter virker også,
og Kontroll betjener enhver OpenCDE-klient. De to produkter installeres hver
for sig: dette repo bundter ikke Dataspatium (licenserne er forskellige, AGPL
her og PolyForm Strict der), og Dataspatiums README beskriver, hvordan appen
hentes. Klientsiden beskrives i Dataspatiums README og dens dokumentation;
parrets acceptkørsler står i [docs/acceptance.md](../acceptance.md) her, og
hvad de to projekter samordner, står i
[docs/dataspatium-coordination.md](../dataspatium-coordination.md).

## Lær mere

- [docs/da/quickstart.md](quickstart.md): Kontroll og Dataspatium sammen på tyve
  minutter, fra en tom maskine til en sag oprettet i 3D-visningen.
- [docs/da/client-guide.md](client-guide.md) og [docs/examples/](../examples/):
  hvordan man bygger en klient, kapabilitetsdokumentet, fejlkoderne og kørbare
  eksempler med Python-biblioteket i [client/](../../client/).
- [docs/da/flows/](flows/): sekvensdiagrammer for OAuth2- og Documents API-forløbene.
- [docs/da/graph-schema.md](graph-schema.md): grafmodellen.
- [docs/da/ifcgraph.md](ifcgraph.md): det valgfrie IFC-grafmodul og eksempler på Cypher-forespørgsler.
- [docs/da/ui-styleguide.md](ui-styleguide.md): regler for serverens sider og mærket.
- [docs/acceptance.md](../acceptance.md): tjekliste til visuel accept med
  uafhængige klienter (Bonsai, ifc-lite, Dataspatium).
- [docs/dataspatium-coordination.md](../dataspatium-coordination.md): hvad
  Kontroll og Dataspatium deler, hvad mere der samordnes, og ejerens beslutninger.
- [docs/inventory.md](../inventory.md): funktionsoversigt over prototypen fra
  2023 og status i omskrivningen, med noter om specifikationernes særheder.
- [docs/adr/](../adr/): arkitekturbeslutninger (grafdatabase, opake tokens,
  portabel Cypher, webgrænseflade uden frameworks, repostrategi).
- [docs/da/security/](security/): trusselsmodel, kontroller knyttet til
  tests, OWASP ASVS niveau 2-tjeklisten, personoplysninger og opbevaring, og
  hvordan scannerne køres.
- [docs/upstream/](../upstream/): udkast til issue og pull request til
  IfcOpenShell (ikke sendt).
- [spec/SOURCES.md](../../spec/SOURCES.md): de præcise specifikationsversioner,
  serveren testes mod.

Dokumentationen findes på denne READMEs syv sprog: engelsk under `docs/`, de
andre under `docs/<sprog>/`. Projektloggene (accept, inventar, samordning),
arkitekturbeslutningerne, udkastene til IfcOpenShell og CONTRIBUTING holdes på
engelsk.

## Begrænsninger i korte træk

- Serveren implementerer BCF API 3.0, ikke 2.1; kun de tre ældre
  opdagelsesaliaser under `/bcf/` findes til ældre klienter.
- Eksport af et projekt som BCFzip overlades til klienterne; serveren gemmer
  sager, kommentarer og viewpoints, som API'et definerer dem.
- Community-udgaverne af Neo4j og Memgraph har ingen skrivebeskyttede
  databasebrugere, så en eksponeret Bolt-port giver fuld adgang til den, der
  har kodeordet. Porten forbliver lukket, medmindre administratoren bevidst
  offentliggør den; administrations-API'ets læsende grafforespørgsel
  (`OPENCDE_GRAPH_QUERY_ENABLED`) giver Cypher uden porten.
- IFC-grafimporten kører i en separat proces med hukommelses- og tidsgrænser
  (`OPENCDE_IFCGRAPH_*`); meget store modeller afvises i stedet for at blive
  efterladt halvt importeret.
- Websiderne er til administratorer og til OAuth2- og Documents API-forløbene;
  slutbrugere arbejder i en klient som Dataspatium eller Bonsai.
- Siderne findes på denne READMEs syv sprog (skift nederst på hver side);
  kommandolinjen og API'ernes fejlbeskeder er på engelsk.
- Ingen ekstern revision endnu. OAuch- og testssl-kørslerne i
  [docs/da/security/pentest-howto.md](security/pentest-howto.md) er
  operatørens skridt før en produktionsudrulning.

## Fejl og forslag

Rapportér fejl og ønsker som *Issues* her på GitHub. Angiv, hvilken
serverversion du kører (`version` i `/.well-known/kontroll` eller `/healthz`),
hvilken klient du brugte, og `X-Request-ID` for et mislykket kald;
forespørgselsloggen og klientens log deler det. Vedhæft ingen personoplysninger
og ingen hemmeligheder. Hvordan ændringer modtages, står i
[CONTRIBUTING.md](../../CONTRIBUTING.md). Ved en sikkerhedssårbarhed, følg
[SECURITY.md](../../SECURITY.md) i stedet for at åbne et issue.

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
dokumentationen og webgrænsefladen findes på de samme sprog, med engelsk
altid som en mulighed, og fælles termer følger Dataspatiums ordliste. Hvert
push kører lint, typekontrol, testsuiterne på tre Python-versioner,
browsertests med axe-core og statiske sikkerhedstjek; natlige job kører OWASP
ZAP, Schemathesis og Trivy. Se [CONTRIBUTING.md](../../CONTRIBUTING.md).

## Licens

Serveren er licenseret under GNU Affero General Public License v3.0 eller
senere ([LICENSE](../../LICENSE)): den er serversoftware, og AGPL's
netværksklausul holder forbedringer af hostede instanser åbne.
Klientbiblioteket i [client/](../../client/) er LGPL-3.0-or-later.
Specifikationsfilerne under [spec/](../../spec/) er © buildingSMART
International og videredistribueres uændret til test. Se
[SECURITY.md](../../SECURITY.md) for, hvordan en sårbarhed rapporteres, og
hvad projektet gør for at forblive sikkert.
