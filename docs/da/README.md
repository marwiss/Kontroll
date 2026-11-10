[Svenska](../../README.md) · **Dansk** · [Norsk bokmål](../nb/README.md) · [Norsk nynorsk](../nn/README.md) · [Suomi](../fi/README.md) · [Íslenska](../is/README.md) · [English](../en/README.md)

<img src="../../opencde/ui/static/icon-192.png" alt="" width="64" height="64" align="left">

# Dataregium OpenCDE-server

*Dataregium hed Kontroll indtil 8. november 2026.*

Dataregium er en server, hvor et byggeprojekt samler sine modeller, dokumenter og
sager, så alle i projektet arbejder ud fra det samme grundlag og ser den samme
historik. Du arbejder med den gennem en app, for eksempel
[Dataspatium](https://github.com/marwiss/Dataspatium) i browseren; serveren har
selv kun sider til login, upload og administration. Den, der driver serveren,
bestemmer, hvem der må logge ind, og hvad hver enkelt må gøre i hvert projekt.

Teknisk er Dataregium en server for buildingSMARTs åbne **OpenCDE-API'er**
(Foundation API 1.0, BCF API 3.0 og 2.1 samt Documents API 1.0), bygget på
grafdatabasen Neo4j eller Memgraph. I 3-serien bliver hver uploadet IFC-model en
tabsfri graf gennem biblioteket [IFC-LPG](https://github.com/marwiss/IFC-LPG), med
versioner, kontroller og ændringsforslag. Serveren blev skrevet om fra bunden ud fra
en forskningsprototype fra 2023, med sikkerhed som det første krav, og enhver klient,
der følger specifikationerne, kan forbinde sig.

![Administrationens oversigt i en Dataregium-server: antal brugere, projekter, klienter, sager og dokumenter, databasens status og de seneste revisionshændelser](../images/admin-overview.png)

**Indhold**

- [Download og kom i gang](#download-og-kom-i-gang)
- [Hvad der kræves](#hvad-der-kræves)
- [Ord du bør kende](#ord-du-bør-kende)
- [Hvad du kan](#hvad-du-kan)
- [OpenCDE-API'erne og deres klienter](#opencde-apierne-og-deres-klienter)
- [Dataregium og Dataspatium](#dataregium-og-dataspatium)
- [Lær mere](#lær-mere)
- [Begrænsninger i korte træk](#begrænsninger-i-korte-træk)
- [Personoplysninger](#personoplysninger)
- [Det næste i 3-serien](#det-næste-i-3-serien)
- [Fejl og forslag](#fejl-og-forslag)
- [Udvikling](#udvikling)
- [Licens](#licens)

## Download og kom i gang

Skal du kun bruge Dataregium, behøver du ikke installere noget: bed den, der driver
serveren, om adressen og en konto, og log ind fra Dataspatium eller en anden
OpenCDE-app. Vil du prøve serveren på din egen computer, følger du den hurtige start
nedenfor. Den tager omkring tyve minutter og kræver Docker Desktop eller Podman. Er
du vant til containere og Python, står den korte vej under
[For den teknisk kyndige](#for-den-teknisk-kyndige).

### Hurtig start (lokalt, Docker eller Podman)

En container er et færdigpakket program, der kører afskærmet på computeren, og
Docker og Podman er programmer, der starter containere. Den hurtige start starter
to: serveren og dens database.

1. **Download.** Hent koden med git, eller som ZIP-fil under *Code > Download ZIP*
   på GitHub. Grenen `main` er 3-serien; `release-2` og `release-1` er 2- og
   1-serien.

   ```sh
   git clone https://github.com/marwiss/Dataregium.git
   cd Dataregium
   ```

2. **Indstil.** Kopiér `.env.example` til `.env`, filen med serverens
   indstillinger, og sæt `OPENCDE_GRAPH_PASSWORD` til din egen adgangskode på
   mindst 16 tegn. Skal du prøve med Dataspatium og modeller, så sæt også
   `OPENCDE_DYNAMIC_CLIENT_REGISTRATION=true`, `OPENCDE_REQUEST_LOG_ENABLED=true`
   og `OPENCDE_IFC_LPG_ENABLED=true`; [den hurtige start med Dataspatium](quickstart.md)
   forklarer hvorfor. Hver indstilling er forklaret i [.env.example](../../.env.example).
3. **Start.** De samme compose-filer virker med Docker og med Podman; vælg den, du har:

   <details open>
   <summary><b>Docker</b></summary>

   ```sh
   docker compose up -d --build
   ```

   starter serveren på <http://127.0.0.1:8000> og en Neo4j-database; første gang tager et par minutter. `docker compose logs -f api` viser serverloggen.

   </details>

   <details>
   <summary><b>Podman</b></summary>

   ```sh
   podman compose up -d --build
   ```

   gør det samme med Podman 5 (rootless, uden daemon); `podman compose logs -f api` viser serverloggen. Se [deploy/local.md](deploy/local.md) for Podmans særpræg.

   </details>

   <details>
   <summary><b>Uden container</b></summary>

   ```sh
   uv sync --extra ifc-lpg          # installerer Python 3.13 og alle afhængigheder, med IFC-LPG
   uv run opencde doctor            # kontrollerer konfigurationen og databasen
   uv run opencde serve             # http://127.0.0.1:8000
   ```

   kører serveren fra udtjekningen med [uv](https://docs.astral.sh/uv/); der skal stadig være en database (Neo4j Desktop, Memgraph Lab eller databasen fra compose-filerne).

   </details>

4. **Se dig omkring.** <http://127.0.0.1:8000/docs> viser hvert kald, serveren
   tager imod, og lader dig prøve dem, <http://127.0.0.1:8000/readyz> siger, om
   serveren og databasen er klar, og <http://127.0.0.1:7484> er Neo4j Browser, hvor
   du ser databasen (Bolt på `127.0.0.1:7697`; udviklingsoverlejringen undgår
   Neo4js standardporte, som ofte er optaget af en anden Neo4j på samme computer).
5. **Indlæs demodata og log ind.**

   <details open>
   <summary><b>Docker</b></summary>

   ```sh
   docker compose exec api opencde seed
   ```

   </details>

   <details>
   <summary><b>Podman</b></summary>

   ```sh
   podman compose exec api opencde seed
   ```

   </details>

   <details>
   <summary><b>Uden container</b></summary>

   ```sh
   uv run opencde seed
   ```

   </details>

   Kommandoen opretter demobrugere, projekter, klienter og en sag, og med IFC-LPG
   slået til også en eksempelmodel som graf. Adgangskoderne udskrives én gang. Log
   ind på <http://127.0.0.1:8000/signin> som `admin` og åbn `/admin`.
6. **Forbind en klient.** Registrér din app under *Klienter* (eller lad den
   registrere sig selv, når `OPENCDE_DYNAMIC_CLIENT_REGISTRATION=true`) og peg den
   mod `http://127.0.0.1:8000`; [Dataspatium](#dataregium-og-dataspatium) og
   Python-biblioteket i [client/](../../client/) er færdige klienter. Skal du logge
   ind fra Dataspatium, så følg [den hurtige start](quickstart.md): den gennemgår
   alle de indstillinger, der kræves, og hvad du gør, hvis noget går galt.

### Udrulning

Skal andre bruge serveren, skal den ligge på en computer, der altid er tændt og kan
nås fra internettet, med sin egen adresse og https. Tabellen viser måderne at gøre
det på; den, der ikke selv driver servere, overlader det til en, der gør. Hver måde
er én compose-fil plus en overlejring:

| Scenarie | Vejledning |
|---|---|
| Lokal test på din computer | [deploy/local.md](deploy/local.md) |
| Offentlig https-adresse til klienttest uden egen server (tunnel) | [deploy/tunnel.md](deploy/tunnel.md) |
| Produktion på egen server med Caddy (automatisk TLS) og natlige sikkerhedskopier | [deploy/vps-caddy.md](deploy/vps-caddy.md) |
| Ved siden af det, der allerede kører på en server, bag dens nginx | [deploy/proxied.md](deploy/proxied.md) |
| Coolify, Dokploy, Portainer | [deploy/paas.md](deploy/paas.md) |
| Din egen region hos AWS, Azure eller Google Cloud: én maskine, sat op af en cloud-init-fil | [deploy/cloud.md](deploy/cloud.md) |
| En containertjeneste plus en administreret Neo4j AuraDB eller Memgraph Cloud | [deploy/cloud-aura.md](deploy/cloud-aura.md) |
| Sikkerhedskopiering og gendannelse (flytbar mellem Neo4j og Memgraph) | [deploy/backup.md](deploy/backup.md) |

`uv run opencde init --public-url https://cde.example.org` skriver en
produktions-`.env` med nye hemmeligheder; `opencde doctor` kontrollerer resultatet.

### Konfiguration

Alt læses fra miljøvariabler med præfikset `OPENCDE_`, fra `.env` eller fra
Docker-hemmeligheder i `/run/secrets/opencde_<navn>`. Den kommenterede liste findes
i [.env.example](../../.env.example). Standardværdierne er sikre: produktion nægter
at starte uden en offentlig `https`-adresse og en databaseadgangskode, og intet er
åbent, før det er konfigureret.

### For den teknisk kyndige

- **Image**: `ghcr.io/marwiss/opencdeserver` til amd64 og arm64, scannet med Trivy
  og med SBOM. Taggene er `3.0.0` og `latest` for 3-serien, `3.0.0-gherkin` og
  `latest-gherkin` med buildingSMARTs ifc-gherkin-rules, `2.0.0` og `1.0.0`;
  `OPENCDE_IMAGE_TAG` vælger i compose-filerne.
- **Compose**: `docker/compose.yaml` plus overlejringer til udvikling, produktion
  med Caddy, bag en eksisterende proxy, Memgraph, en ekstern database, Bolt med TLS,
  en tunnel, den lokale motor og arbejdskopien. `COMPOSE_FILE` i `.env` vælger dem,
  så kommandoerne er uden `-f`.
- **Uden container**: Python 3.11 eller nyere med uv (afprøvet på 3.11, 3.13 og
  3.14), `uv sync --extra ifc-lpg`, og Neo4j 5.26 eller Memgraph 3.14 på `OPENCDE_GRAPH_URI`.
- **De vigtigste indstillinger**: `OPENCDE_APIS` vælger API'erne (alle tre som
  standard, `["documents"]` i 1.0.0); `OPENCDE_IFC_LPG_ENABLED=true` slår grafen til
  og alt i 2- og 3-serien, der handler om modeller; `OPENCDE_ENVIRONMENT` er
  `development`, `production` eller `local` (den lokale motor, `opencde init --local`).
- **Endepunkter**: `/.well-known/dataregium` (versionen og de udvidelser, der er
  slået til), `/foundation/versions`, `/openapi.json` og `/docs`, `/healthz` og
  `/readyz`, `/admin/api` (administration) og `/manage/1.0` (projektadministration). 3-seriens udvidelser ligger under `/documents/1.0/`
  (versionernes `ifc-queries`, `ifc-diff`, `ifc-changes` og `ifc-geometry`,
  projekternes `ifc-precheck` og `ifc-clash`) og under en BCF 3.0-sag (`snippet` og
  `ifc-proposal/approve`).
- **Kommandolinjen**: `opencde serve`, `init`, `doctor`, `seed`, `backup`,
  `restore`, `revoke`, `cleanup` og grupperne `user`, `project`, `client` og
  `ifcgraph`; `uv run opencde --help`.
- **At bygge en klient**: [klientguiden](client-guide.md) har flowene,
  kapabilitetsdokumentet, fejlkoderne og udvidelserne, og [docs/examples/](../examples/)
  kørbare eksempler.

## Hvad der kræves

Den, der kun bruger Dataregium gennem en app, behøver en browser og en konto. For selv
at køre serveren:

- Windows, macOS eller Linux med Docker (Desktop på Windows/macOS, Engine på Linux)
  eller Podman 5, eller Python 3.11 eller nyere med [uv](https://docs.astral.sh/uv/)
  og en egen Neo4j 5.26- eller Memgraph 3.14-database.
- Omkring 1 GB hukommelse til databasecontaineren (`NEO4J_HEAP` og
  `NEO4J_PAGECACHE` i `.env`), og mere til store modeller med IFC-LPG.
- Lokalt: port 8000 til serveren og 7484/7697 til databasen, alle bundet til
  `127.0.0.1`. I produktion: portene 80 og 443 tilgængelige fra internettet og et
  DNS-navn til serveren.
- Klienter skal have en `https`-adresse i produktion; lokalt accepteres
  `http://127.0.0.1` som redirect-URI, og `http://localhost` med `OPENCDE_ALLOW_LOCALHOST_REDIRECTS=true`.

## Ord du bør kende

De ord, denne README bruger, på almindeligt dansk; hele ordlisten findes i
[glossary.md](glossary.md).

- **BIM**: at bygge og forvalte med en digital model af bygningen, hvor hver væg,
  dør og hvert rum er et objekt med egenskaber og ikke bare streger på en tegning.
- **CAD**: programmer til tegninger og modeller; en BIM-model laves i et CAD-program.
- **IFC**: det åbne filformat for BIM-modeller, som de store programmer kan læse og skrive.
- **BCF og sager**: et åbent format for spørgsmål og bemærkninger om en model, med
  kommentarer og en visning (viewpoint), der viser, hvor i modellen det gælder.
- **IDS**: et krav til, hvad en model skal indeholde, for eksempel at hver dør har en
  brandklasse; serveren kontrollerer modellerne mod projektets krav.
- **OpenCDE**: buildingSMARTs åbne regler for, hvordan apps og servere i et
  byggeprojekt taler sammen. CDE betyder fælles datamiljø.
- **API**: den måde, en app taler med serveren på, med faste spørgsmål og svar.
- **Server og klient**: serveren gemmer og deler projektets grundlag; klienten er den
  app, du arbejder i, for eksempel Dataspatium.
- **Database og graf**: databasen er der, hvor serveren gemmer alt. En grafdatabase
  gemmer ting og forbindelserne mellem dem, som en væg, der står på en etage, og kan
  derfor svare på spørgsmål om, hvordan delene hænger sammen.
- **Container**: et færdigpakket program, der kører afskærmet på computeren; Docker og
  Podman starter dem.
- **OAuth2**: den sikre måde at logge ind fra en app på, uden at appen får din adgangskode.
- **Version og ændringssæt**: hver gang en model gemmes på serveren, bliver det en ny
  version. Et ændringssæt er et forslag til ændringer, som en ansvarlig godkender, før
  det bliver den næste version.

## Hvad du kan

Det, der virker i én version, virker også i den næste. Hver version hører sammen
med den samme version af Dataspatium.

### Version 1 (med Dataspatium 1)

- **Dokumenter ét sted** (Documents API 1.0): vælge, uploade og hente dokumenter og
  deres versioner gennem serverens sider, fra en app som Dataspatium.
- **Login og apps** (Foundation API 1.0): én konto pr. person, login med OAuth2 og
  PKCE, og apps, som en administrator registrerer, eller som registrerer sig selv,
  når operatøren tillader det (se [klientguiden](client-guide.md)).
- **Administration** i browseren (`/admin`) og på kommandolinjen: brugere og deres
  projektroller, projekter, klienter, sessioner, revisionsloggen og
  helbredstjekkene; hver bruger har `/account` til sin adgangskode og sine apps.
- **Hjælp til den, der bygger en app**, markeret som udvidelser: et
  kapabilitetsdokument (`/.well-known/dataregium`), en stabil fejlkode i hvert
  fejlsvar og en forespørgselslog.
- **Et klientbibliotek** i Python ([client/](../../client/)) med kørbare eksempler,
  og et publiceret image til hver udrulning.
- **Projektansvarlige administrerer deres projekt**: en `manager` tilføjer og fjerner
  medlemmer, skifter deres roller og omdøber projektet, uden at være
  serveradministrator.

### Også i version 2 (med Dataspatium 2)

- **Sager om modellen** (BCF API 3.0 og 2.1): spørgsmål og bemærkninger med
  kommentarer, billeder og visninger, der udpeger bygningsdele, med filtre og en
  hændelseslog, valideret mod buildingSMARTs skemaer.
- **Modellen som graf** (IFC-LPG-modulet, slået til med `OPENCDE_IFC_LPG_ENABLED`):
  en uploadet IFC-model bliver til en graf i databasen, knyttet til bygningsdelene i
  sagernes visninger (se [IFC-LPG](ifc-lpg.md)).

### Også i version 3 (med Dataspatium 3)

- **En tabsfri model**: grafen kommer fra biblioteket IFC-LPG og rummer alt i filen,
  så den kan skrives tilbage, som den kom.
- **Kontrol af hver upload** mod IFC-skemaet, buildingSMARTs regler og projektets
  IDS-krav; et projekt kan afvise filer med fejl, og en fil kan kontrolleres på
  forhånd uden at blive gemt.
- **Forespørgsler og sammenligninger**: navngivne forespørgsler for medlemmer, hvad
  der er ændret siden en version, sammenligning af to versioner (også på en side på
  serveren) og kollisionskontrol, hvis kollisioner kan blive sager.
- **Ændringer som forslag**: hver ny version angiver sin basis, og et ændringssæt i
  en BCF-sag prøves og godkendes af en `manager` til den næste version, flettet pr.
  instans med det, der kom imellem; en reel kollision viser basens, den seneste
  versions og forslagets værdi.
- **Publicering**: en `manager` publicerer en version, hvis kontrol ikke fandt fejl, og
  serveren gemmer den som én hel `.ifczip`, som alle i projektet kan downloade.
- **En bygning ind i en anden model**: bygningen fra én model kommer ind i et andet
  projekts model som dens næste version, med en rapport først om, hvad der følger med,
  og et valg for hvert objekt, som begge har i forskellig form; en `manager` gør det.
- **Geometrien som glTF**: hver version som binær glTF med delte meshes og en node
  pr. bygningsdel, og en kasse pr. bygningsdel i grafen til spørgsmål om, hvad der er nær.
- **En lokal motor og din egen region**: Dataregium på din egen computer bag
  Dataspatium, med en arbejdskopi i hukommelsen til store modeller, og færdige
  opskrifter til en egen maskine hos AWS, Azure eller Google Cloud eller ved siden af
  en eksisterende nginx.

<img src="../images/upload.png" alt="Upload-siden, hvor brugeren giver filen titel og version" width="340">

## OpenCDE-API'erne og deres klienter

OpenCDE er buildingSMART Internationals familie af åbne web-API'er til et fælles
datamiljø, det sted, hvor et projekt deler sine modeller, dokumenter og sager. En
klient og en server, der følger de samme specifikationer, kan arbejde sammen, uanset
hvem der har bygget dem. Dataregium implementerer alle tre:

| API | Hvad det er til | Specifikation |
|---|---|---|
| Foundation API 1.0 | Siger, hvilke API'er en server tilbyder, hvordan man logger ind, og hvem brugeren er | [foundation-API](https://github.com/buildingSMART/foundation-API) |
| BCF API 3.0 og 2.1 | Sager om en model, med kommentarer og viewpoints med kamera, komponenter og billeder | [BCF-API](https://github.com/buildingSMART/BCF-API) |
| Documents API 1.0 | At vælge, hente og uploade dokumenter og deres versioner via sider på serveren | [documents-API](https://github.com/buildingSMART/documents-API) |

**Dataspatium er en klient, ikke den eneste.** Enhver klient, der følger disse
specifikationer, skal kunne forbinde sig: intet på serveren afhænger af Dataspatium, og
udvidelserne uden for specifikationerne er valgfrie, så en klient, der ikke kender dem,
ikke mærker dem. En klient har brug for tre ting:

- en registrering på serveren, foretaget af en administrator under *Klienter* eller af
  klienten selv, når `OPENCDE_DYNAMIC_CLIENT_REGISTRATION=true`;
- OAuth2 authorization code med PKCE `S256`, som serveren kræver af hver klient undtagen en fortrolig, som en administrator har markeret;
- BCF API 3.0, eller 2.1 for en klient, der kun kan den version. `GET /foundation/versions` lister begge, og
  [klientguiden](client-guide.md) fortæller, hvad der adskiller dem.

Så langt er det vist: serverens svar testes mod buildingSMARTs skemaer ved hvert push,
og Dataspatium og Python-biblioteket i [client/](../../client/) kører mod serveren. Uafhængige
klienter som Bonsai og ifc-lite har en færdig tjekliste, som endnu ikke er kørt. Hvis du prøver en klient, så
fortæl, hvordan det gik, under [Fejl og forslag](#fejl-og-forslag). Når en klient og en specifikation
ikke stemmer overens, afgør specifikationen. [docs/da/client-guide.md](client-guide.md) er til dem, der
bygger en klient.

## Dataregium og Dataspatium

Dataspatium er den app, du arbejder i, og Dataregium er den server, hvor projektets
fælles grundlag ligger. [Dataspatium](https://github.com/marwiss/Dataspatium) kører
helt i browseren, og de to er udviklet til at arbejde sammen. Det samme
udgivelsesnummer betyder, at de virker sammen: Dataspatium 3.0.0 virker med
Dataregium 3.0.0 ([hurtig start](quickstart.md)).

Dataspatium tilføjer en Dataregium-server som kilde: appen opdager API'erne gennem
`/foundation/versions`, logger ind med OAuth2 authorization code og PKCE og
registrerer sig selv som offentlig klient, når dynamisk registrering er slået til,
viser projektets modeller og dokumenter, læser og skriver BCF-sager med kommentarer
og viewpoints taget fra sin 3D-visning og uploader datasæt, filer og
arbejdsområdepakker gennem Documents API. I 3-serien publicerer appen versioner med
basisversion og forhåndskontrol, sender ændringssæt, som serveren prøver, lader den
projektansvarlige godkende dem og afgøre kollisioner, sammenligner versioner i 3D og
stiller grafen navngivne forespørgsler; en administrator kan også forespørge grafen
med Cypher gennem serverens læsende endepunkt. Appen sender `X-Request-ID` med hvert
kald, så forespørgselsloggen her og loggen i appen viser den samme samtale, læser
serverens kapabilitetsdokument for at se, hvilke udvidelser der er slået til, og
reagerer på de fejlkoder, serveren lægger i sine fejlsvar.

Sådan hænger de sammen:

```mermaid
flowchart LR
    subgraph app ["Dataspatium, i browseren"]
        source["Kilde og login"]
        issues["Sager i 3D-visningen"]
        files["Modeller og dokumenter"]
        queries["Forespørgsler mod IFC-grafen"]
        log["Loggen i appen"]
        admin["Kortet Administration"]
    end
    subgraph server ["Dataregium, serveren"]
        foundation["Foundation API, OAuth2"]
        bcf["BCF API"]
        documents["Documents API"]
        ifcgraph[("IFC-graf")]
        requests["Forespørgselslog"]
        adminapi["Administrations-API"]
    end
    source <--> foundation
    issues <--> bcf
    files <--> documents
    queries --> ifcgraph
    log <-- "X-Request-ID" --> requests
    admin --> adminapi
```

Bortset fra de markerede udvidelser går alt, hvad Dataspatium gør mod serveren,
gennem de tre OpenCDE-API'er, så appen bruger intet, som en anden klient ikke kan
bruge; se [OpenCDE-API'erne og deres klienter](#opencde-apierne-og-deres-klienter).
De to produkter installeres hver for sig: dette repository samler ikke Dataspatium
(licenserne er forskellige, AGPL her og PolyForm Strict der), og Dataspatiums README
beskriver, hvordan appen hentes og bruges.

### Udgivelserne 1, 2 og 3

Der er én udgivelse pr. hovednummer, og den udgives igen, når den vokser; kun den
seneste i hver serie rettes. Dataregium og Dataspatium med det samme nummer hører sammen:

| Dataregium | Hvad den har | Image | Hører sammen med |
|---|---|---|---|
| 1.0.0 | En dokumentserver: Foundation API og Documents API, webadministrationen på syv sprog, projektadministrationen for den projektansvarlige og forespørgselsloggen. Den er 2.0.0-koden med kun Documents API slået til (`OPENCDE_APIS`) | `1.0.0` | Dataspatium 1.0.0 |
| 2.0.0 | Også BCF API 3.0 og 2.1 på de samme data og IFC-LPG-modulet, der laver en graf af hver uploadet IFC-fil | `2.0.0` | Dataspatium 2.0.0 |
| 3.0.0 | Også den tabsfri graf fra biblioteket IFC-LPG, kontrollen af hver upload, forespørgslerne, sammenligningerne og kollisionskontrollen, versioner med ændringsforslag, der prøves, godkendes og flettes, geometrien som glTF, den lokale motor og opskrifterne til skyen og nginx | `3.0.0`, `latest`, `3.0.0-gherkin` | Dataspatium 3.0.0 |

## Lær mere

- [quickstart.md](quickstart.md): Dataregium og Dataspatium sammen på tyve minutter,
  fra en tom computer til en sag oprettet i 3D-visningen.
- [client-guide.md](client-guide.md) og [docs/examples/](../examples/): hvordan man
  bygger en klient, kapabilitetsdokumentet, fejlkoderne, 3-seriens udvidelser og
  kørbare eksempler med Python-biblioteket i [client/](../../client/).
- [architecture.md](architecture.md): hvordan delene hænger sammen, hvad der sker med et kald, og hvor alt findes i koden.
- [glossary.md](glossary.md): de ord, dokumentationen bruger.
- [flows/](flows/): sekvensdiagrammer for OAuth2-, Documents API- og BCF-viewpoint-flowene.
- [graph-schema.md](graph-schema.md): grafmodellen.
- [ifc-lpg.md](ifc-lpg.md): IFC-LPG-modulet, kontrollerne, versionerne, ændringssættene, geometrien og eksempler på Cypher-forespørgsler.
- Arkitekturbeslutninger, der ligger fast: en grafdatabase som eneste lager, opake
  tokens i stedet for JWT, portabel Cypher til Neo4j og Memgraph, en webgrænseflade
  uden framework, sikkerhedskopi på applikationsniveau, BCF API 2.1 ved siden af 3.0,
  en tabsfri IFC-graf, der selv læser og skriver STEP og valideres, når den skrives,
  buildingSMARTs regler i et eget miljø, IFC-LPG som bibliotek, kontrol mod projektets
  IDS, navngivne forespørgsler for medlemmer, kollisionskontrol på serveren med
  IfcClash, versioner som noder med ændringer og en basis, en lokal motor, der kun
  svarer på din egen computer, og en arbejdskopi i hukommelsen ved siden af arkivet.
- [spec/SOURCES.md](../../spec/SOURCES.md): de præcise specifikationsversioner, som
  serveren testes mod.

Dokumentationen findes på denne README's syv sprog, hvert sprog under
`docs/<sprog>/`; engelsk under `docs/en/` er kilden. CONTRIBUTING er på engelsk.

### Videre læsning

- [BCF API](https://github.com/buildingSMART/BCF-API), [Foundation API](https://github.com/buildingSMART/foundation-API) og [Documents API](https://github.com/buildingSMART/documents-API):
  de specifikationer, serveren følger.
- [IFC](https://github.com/buildingSMART/IFC4.x-development): filformatet for bygningsmodeller, og [IDS](https://github.com/buildingSMART/IDS): kravspecifikationer, som modeller kontrolleres mod.
- [RFC 9700](https://www.rfc-editor.org/rfc/rfc9700): nutidens bedste praksis for sikkerhed i OAuth 2.0, og
  [OAuth 2.1](https://datatracker.ietf.org/doc/draft-ietf-oauth-v2-1/), udkastet, der samler den.
- [RFC 7636](https://www.rfc-editor.org/rfc/rfc7636) (PKCE), [RFC 8252](https://www.rfc-editor.org/rfc/rfc8252) (apps på computeren eller telefonen) og
  [RFC 7591](https://www.rfc-editor.org/rfc/rfc7591) (registrering af klienter).
- [OWASP ASVS](https://owasp.org/www-project-application-security-verification-standard/): tjeklisten for sikkerhedsarbejdet.

## Begrænsninger i korte træk

- Alt, der handler om modeller, i 2- og 3-serien, kræver IFC-LPG-modulet, som er slået
  fra, indtil `OPENCDE_IFC_LPG_ENABLED=true`. buildingSMARTs regler kører kun med
  imaget `-gherkin`; uden det kontrolleres skemaet og IDS.
- Serveren implementerer BCF API 3.0 og 2.1, ikke 1.0, hvis ressourcer ser anderledes ud.
- Eksport af et projekt som BCFzip overlades til klienterne; serveren gemmer sager,
  kommentarer og viewpoints, som API'et definerer dem.
- Community-udgaverne af Neo4j og Memgraph mangler databasebrugere med kun
  læseadgang, så en eksponeret Bolt-port giver fuld adgang til den, der har
  adgangskoden. Porten forbliver lukket, medmindre administratoren bevidst
  publicerer den; administrations-API'ets læsende grafforespørgsel
  (`OPENCDE_GRAPH_QUERY_ENABLED`) giver Cypher uden porten.
- IFC-LPG-importen, kontrollerne og prøvningen af ændringssæt kører i separate
  processer med hukommelses- og tidsgrænser (`OPENCDE_IFC_LPG_*`); meget store
  modeller afvises i stedet for at blive efterladt halvt importeret, eller håndteres
  af den lokale motor.
- Websiderne er til login, administration, upload og valg af dokumenter og til en
  versions kontrol og sammenligning; slutbrugere arbejder i en klient som
  Dataspatium eller Bonsai.
- Siderne findes på denne README's syv sprog (skift nederst på hver side);
  kommandolinjen og API'ernes fejlmeddelelser er på engelsk.
- Ingen ekstern gennemgang endnu. OAuch- og testssl-kørslerne er operatørens trin før
  en produktionsudrulning.

## Personoplysninger

Den, der driver Dataregium for andre, er dataansvarlig for dette. Serveren gemmer
brugerkonti (brugernavn, navn, valgfri e-mail, adgangskodehash), projektmedlemskaber,
sager og kommentarer med forfatternes navne, uploadede filer med uploaderen,
IFC-grafen med filens ejerhistorik, versionerne med forfatter og godkender,
ændringsforslagene med, hvem der foreslog dem, og, hvor en AI gjorde det, hvilken
AI-model og hvilket værktøjskald, og en revisionslog over, hvem der gjorde hvad og
fra hvilken adresse. Adgangskoder, tokens og hemmeligheder gemmes kun som hashes.
Tokens, sessioner, upload-sessioner og ubrugte selvregistrerede klienter udløber og
ryddes op af serveren; revisionsloggen beskæres af operatøren. En administrator
sletter en konto under `/admin/users`, og dens sessioner og tokens følger med; navnet
står tilbage på de sager og versioner, personen skrev, indtil de slettes.
Revisionsloggen eksporteres som CSV, BCF- og dokumentdata gennem API'erne og hele
databasen med `opencde backup`. Hvad Dataspatium gemmer i browseren, står i appens
egen dokumentation.

## Det næste i 3-serien

3.0.0 er 3-seriens eneste udgivelse og udgives igen, når den vokser; det, den har i
dag, står under [Hvad du kan](#hvad-du-kan). De officielle OpenCDE-API'er forbliver,
som buildingSMART definerer dem; det, serien tilføjer, er udvidelser til dem, under
egne navne og med en egen OpenAPI. Dette afsnit siger, hvad der er besluttet, for den,
menneske eller AI-agent, der fører en del af det videre. Arbejdsgangene står i
[CONTRIBUTING.md](../../CONTRIBUTING.md) og IFC-grafen i [ifc-lpg.md](ifc-lpg.md).

### Besluttet

- **Redigering af modeller i Native IFC.** Create er uploaden, Read de navngivne
  forespørgsler, Update og Delete et ændringssæt (sætte, tilføje, fjerne og kopiere
  instanser), der prøves og godkendes, og Export at skrive STEP tilbage. Dataene
  holder sig til IFC, ifc-gherkin-rules og projektets IDS, ved import og efter hver
  ændring.
- **Versionshistorik i databasen, ikke i git**, i samme ånd som Bruno Postles
  [ifcmerge](https://github.com/brunopostle/ifcmerge). Hver godkendt version er en
  node med sin forælder, forfatter, godkender og ændringer; grafen rummer den seneste
  version, og enhver version skrives ud på forespørgsel. En ændring føres ind, når
  filen, der skrives ud fra den, ikke har nogen bemærkning, som versionen før den manglede.
- **BIM-snippets som en fungerende demonstration.** En foreslået ændring rejser som
  `bim_snippet` i en BCF 3.0-sag, med et publiceret skema bag dens `reference_schema`,
  så ændringen, diskussionen og beslutningen findes ét sted. buildingSMARTs
  uudgivne udviklingsgrene har fjernet dem; Dataregium bygger dem for at vise, hvordan
  de kunne virke. En snippet udpeger det, den ændrer, med et GlobalId og en sti af
  IFC's attributnavne derfra, med STEP-id kun der, hvor intet GlobalId når frem;
  GlobalId og sti nåede 98 til 100 procent af instanserne i 28 prøvefiler.
- **Hvem der må ændre hvad.** `editor` foreslår, `manager` godkender, og en AI
  foreslår kun; hver ændring bærer, hvem der foreslog den, og hvilken AI-model og
  hvilket værktøjskald, hvor en AI gjorde det. Ansvarsregler, der udpeger en del af
  modellen med et IDS-udvalg, som ISO 19650's ansvarlige teams gør, kommer senere.
- **Kollisionskontrol begge steder**: på serveren med IfcOpenShells IfcClash og i
  Dataspatium med dens egen kerne i JavaScript.
- **Det næste**: et endepunkt til AI-værktøjer (MCP) på din egen computer, hvor AI
  foreslår, og et menneske godkender; kontrol af klassifikationer og egenskaber mod
  bSDD; en ny kontrol af versionerne, når projektets IDS ændres, med buildingSMARTs
  fund knyttet til bygningsdele; proprietære formater gennem kildeprogrammernes
  IFC-eksport; og en testsuite mod promptinjektion i snippets og MCP.

## Fejl og forslag

Rapportér fejl og ønsker som *Issues* her på GitHub. Angiv, hvilken
serverversion du kører (`version` i `/.well-known/dataregium` eller `/healthz`),
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

Kode og kommentarer er på engelsk, og stilen følger IfcOpenShells
konventioner (ruff, 120 kolonner), så det forbliver muligt at bidrage med
serveren til IfcOpenShell.
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
