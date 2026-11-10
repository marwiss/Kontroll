[Svenska](../../README.md) · [Dansk](../da/README.md) · [Norsk bokmål](../nb/README.md) · **Norsk nynorsk** · [Suomi](../fi/README.md) · [Íslenska](../is/README.md) · [English](../en/README.md)

<img src="../../opencde/ui/static/icon-192.png" alt="" width="64" height="64" align="left">

# Dataregium OpenCDE-server

*Dataregium heitte Kontroll fram til 8. november 2026.*

Dataregium er ein server for **OpenCDE-API-ane** frå buildingSMART (Foundation
API 1.0, BCF API 3.0 og 2.1 og Documents API 1.0), bygd på ein grafdatabase, med
webadministrasjon og ein valfri IFC-LPG-modul som knyter BCF-komponentar til
bygningsdelane dei peikar på. Han voks fram av ein forskingsprototyp frå 2023
for digitale kontrollplanar i svenske byggjeløyve og vart skriven om frå
grunnen av med tryggleik som fyrste krav.
Klientar som følgjer spesifikasjonane, skal kunne kople seg til, så serveren
ikkje er bunden til eitt bestemt program.

![Oversikta i administrasjonen til ein Dataregium-server: talet på brukarar, prosjekt, klientar, saker og dokument, statusen til databasen og dei siste revisjonshendingane](../images/admin-overview.png)

**Innhald**

- [Last ned og kom i gang](#last-ned-og-kom-i-gang)
- [Kva som krevst](#kva-som-krevst)
- [Kva du kan gjere](#kva-du-kan-gjere)
- [OpenCDE-API-a og klientane deira](#opencde-api-a-og-klientane-deira)
- [Dataregium og Dataspatium](#dataregium-og-dataspatium)
- [Lær meir](#lær-meir)
- [Avgrensingar i korte trekk](#avgrensingar-i-korte-trekk)
- [Personopplysningar](#personopplysningar)
- [Det neste i 3-serien](#det-neste-i-3-serien)
- [Feil og framlegg](#feil-og-framlegg)
- [Utvikling](#utvikling)
- [Lisens](#lisens)

## Last ned og kom i gang

### Snøggstart (lokalt, Docker eller Podman)

1. **Last ned.** Klon repoet, eller hent det publiserte imaget
   `ghcr.io/marwiss/opencdeserver` (fleire arkitekturar, skanna og med SBOM
   ved kvar utgjeving):

   ```sh
   git clone https://github.com/marwiss/Dataregium.git
   cd Dataregium
   ```

2. **Konfigurer.** Kopier `.env.example` til `.env` og set
   `OPENCDE_GRAPH_PASSWORD` (minst 16 teikn). Kvar innstilling blir forklart i
   [.env.example](../../.env.example).
3. **Start.** Dei same compose-filene verkar med Docker og med Podman; vel den du har:

   <details open>
   <summary><b>Docker</b></summary>

   ```sh
   docker compose up -d --build
   ```

   startar serveren på <http://127.0.0.1:8000> og ein Neo4j-database; `docker compose logs -f api` viser serverloggen.

   </details>

   <details>
   <summary><b>Podman</b></summary>

   ```sh
   podman compose up -d --build
   ```

   gjer det same med Podman 5 (rootless, utan daemon); `podman compose logs -f api` viser serverloggen. Sjå [docs/nn/deploy/local.md](deploy/local.md) for det som er særeige for Podman.

   </details>

   <details>
   <summary><b>Utan container</b></summary>

   ```sh
   uv sync                          # installerer Python 3.13 og alle avhengnader
   uv run opencde doctor            # kontrollerer konfigurasjon og database
   uv run opencde serve             # http://127.0.0.1:8000
   ```

   køyrer serveren frå utsjekkinga med [uv](https://docs.astral.sh/uv/); ein database trengst framleis (Neo4j Desktop, Memgraph Lab eller databasen frå compose-filene).

   </details>

4. **Sjå deg rundt.** <http://127.0.0.1:8000/docs> er den interaktive
   API-dokumentasjonen, <http://127.0.0.1:8000/readyz> beredskapskontrollen
   og <http://127.0.0.1:7484> Neo4j Browser (Bolt på `127.0.0.1:7697`;
   utviklingsoverlegget unngår standardportane til Neo4j, som ofte er opptekne
   av ein annan Neo4j på same maskin).
5. **Legg inn demodata og logg inn.**

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
   <summary><b>Utan container</b></summary>

   ```sh
   uv run opencde seed
   ```

   </details>

   Kommandoen opprettar demobrukarar og prosjekt og skriv ut passorda deira éin gong. Logg inn på <http://127.0.0.1:8000/signin> som `admin` og opne `/admin`.
6. **Kople til ein klient.** Registrer appen din under *Klientar* (eller lat
   han registrere seg sjølv når `OPENCDE_DYNAMIC_CLIENT_REGISTRATION=true`) og
   peik han mot `http://127.0.0.1:8000`; [Dataspatium](#dataregium-og-dataspatium)
   og Python-biblioteket i [client/](../../client/) er ferdige klientar.
   Skal du logge inn frå Dataspatium, følg [snøggstarten](quickstart.md): han tek for
   seg alle innstillingane som trengst, og kva du gjer om noko går gale.

### Utrulling

Éi compose-fil pluss eitt overlegg per scenario:

| Scenario | Rettleiing |
|---|---|
| Lokal test på eiga maskin | [docs/nn/deploy/local.md](deploy/local.md) |
| Offentleg https-adresse for klienttestar utan eigen server (tunnel) | [docs/nn/deploy/tunnel.md](deploy/tunnel.md) |
| Produksjon på eigen server med Caddy (automatisk TLS) og nattlege tryggingskopiar | [docs/nn/deploy/vps-caddy.md](deploy/vps-caddy.md) |
| Ved sida av det som alt køyrer på ein server, bak nginx-en der | [docs/nn/deploy/proxied.md](deploy/proxied.md) |
| Coolify, Dokploy, Portainer | [docs/nn/deploy/paas.md](deploy/paas.md) |
| Din eigen region hos AWS, Azure eller Google Cloud: éi maskin, sett opp av éi cloud-init-fil | [docs/nn/deploy/cloud.md](deploy/cloud.md) |
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
  `NEO4J_PAGECACHE` i `.env`), meir med IFC-LPG-modulen.
- Lokalt: port 8000 for serveren og 7484/7697 for databasen, alle bundne til
  `127.0.0.1`. I produksjon: portane 80 og 443 nåelege frå internett og eit
  DNS-namn for serveren.
- Klientar treng ei `https`-adresse i produksjon; lokalt blir
  `http://127.0.0.1` godteke som redirect-URI, og `http://localhost` med `OPENCDE_ALLOW_LOCALHOST_REDIRECTS=true`.

## Kva du kan gjere

Det som verkar i éin versjon, verkar òg i den neste. Kvar versjon høyrer saman
med den same versjonen av Dataspatium.

### Versjon 1 (med Dataspatium 1)

- **Foundation API 1.0**: tenesteoppdaging, innlogging med OAuth2 og PKCE,
  gjeldande brukar, tilbakekalling av token og sjølvregistrering av klientar når
  operatøren tillèt det (sjå [klientguiden](client-guide.md)).
- **Documents API 1.0**: velje, laste opp og hente dokument og versjonane deira,
  med sidene til serveren for metadata og val.
- **Administrasjon** i nettlesaren (`/admin`) og på kommandolinja: brukarar og
  prosjektrollene deira, prosjekt, klientar, sesjonar, revisjonsloggen og
  helsekontrollane; kvar brukar har `/account` for eige passord og eigne appar.
  Ein `manager` administrerer medlemmene og rollene i sitt eige prosjekt.
- **Tillegg**, merkte som det: eit kapabilitetsdokument
  (`/.well-known/dataregium`), ein stabil feilkode i kvart feilsvar og ein
  førespurnadslogg for feilsøking av klientar.
- **Eit klientbibliotek** i Python ([client/](../../client/)) med køyrbare døme,
  og eit publisert image for kvar utrulling.

### Òg i versjon 2 (med Dataspatium 2)

- **BCF API 3.0 og 2.1**: saker med OData-spørjingar, kommentarar, viewpointar
  med snapshots og komponentar, dokumentreferansar og hendingsloggar, validerte
  mot skjemaa til buildingSMART.
- **IFC-LPG-modulen**: opplasta IFC-modellar blir ein graf i databasen, knytt
  til komponentane i viewpointane til sakene (sjå [IFC-LPG](ifc-lpg.md)).

### Òg i versjon 3 (med Dataspatium 3)

- **Ein tapsfri IFC-graf** frå IFC-LPG, eit eige bibliotek: fila kan skrivast
  tilbake slik ho kom.
- **Kontrollerte opplastingar** mot IFC-skjemaet, reglane til buildingSMART og
  IDS-en til prosjektet; eit prosjekt kan avvise filer med feil, og ei fil kan
  kontrollerast først.
- **Spørsmål til modellen** for medlemmer: namngjevne spørjingar, kva som er
  endra sidan ein versjon, samanlikning av to versjonar og kollisjonskontroll.
- **Geometrien som glTF**: kvar versjon som binær glTF med delte meshar og ein
  node per bygningsdel, og ein boks per bygningsdel i grafen for spørsmål om kva
  som er nær.
- **Endringar som framlegg**: eit endringssett i ei BCF-sak blir prøvd mot
  basisversjonen sin, og ein `manager` godkjenner det til neste versjon, slått
  saman med det som kom imellom; ein kollisjon viser verdien i basen, i den
  siste versjonen og i framlegget.
- **Ein lokal motor** på di eiga datamaskin bak Dataspatium, med ein arbeidskopi
  i minnet for store modellar, og opplasting utan nettsida for godkjende
  klientar.

**Status**: alle elleve etappane i planen er gjennomførte; eit bidrag av
serveren til IfcOpenShell er enno ikkje føreslått.

<img src="../images/upload.png" alt="Opplastingssida, der brukaren gjev fila tittel og versjon" width="340">

## OpenCDE-API-a og klientane deira

OpenCDE er familien til buildingSMART International av opne web-API-ar for eit felles
datamiljø, staden der eit prosjekt deler modellar, dokument og saker. Ein klient og ein
server som følgjer dei same spesifikasjonane, kan arbeide saman, same kven som har bygd
dei. Dataregium implementerer alle tre:

| API | Kva det er til | Spesifikasjon |
|---|---|---|
| Foundation API 1.0 | Seier kva API-ar ein server tilbyr, korleis ein loggar inn, og kven brukaren er | [foundation-API](https://github.com/buildingSMART/foundation-API) |
| BCF API 3.0 og 2.1 | Saker om ein modell, med kommentarar og viewpointar med kamera, komponentar og bilete | [BCF-API](https://github.com/buildingSMART/BCF-API) |
| Documents API 1.0 | Å velje, hente og laste opp dokument og versjonane deira, via sider på serveren | [documents-API](https://github.com/buildingSMART/documents-API) |

**Dataspatium er éin klient, ikkje den einaste.** Kvar klient som følgjer desse
spesifikasjonane, skal kunne kople seg til: ingenting på serveren er avhengig av
Dataspatium, og utvidingane utanfor spesifikasjonane er valfrie, så ein klient som ikkje
kjenner dei, merkar dei ikkje. Ein klient treng tre ting:

- ei registrering på serveren, gjord av ein administrator under *Klientar* eller av klienten
  sjølv når `OPENCDE_DYNAMIC_CLIENT_REGISTRATION=true`;
- OAuth2 authorization code med PKCE `S256`, som serveren krev av kvar klient unnateke ein konfidensiell som ein administrator har merkt;
- BCF API 3.0, eller 2.1 for ein klient som berre kan den versjonen. `GET /foundation/versions` listar begge, og
  [klientguiden](client-guide.md) fortel kva som skil dei.

Så langt er det vist: svara frå serveren blir testa mot skjemaa til buildingSMART ved kvar
push, og Dataspatium og Python-biblioteket i [client/](../../client/) køyrer mot serveren.
Uavhengige klientar som Bonsai og ifc-lite har ei ferdig sjekkliste som enno ikkje er køyrd. Om du prøver ein klient, fortel
korleis det gjekk under [Feil og framlegg](#feil-og-framlegg). Når ein klient og ein spesifikasjon ikkje
stemmer overeins, avgjer spesifikasjonen. [docs/nn/client-guide.md](client-guide.md) er for dei som byggjer
ein klient.

## Dataregium og Dataspatium

Dataregium (serveren) og [Dataspatium](https://github.com/marwiss/Dataspatium)
(ein dataapp som køyrer heilt i nettlesaren) er utvikla for å verke saman som
server og klient, og same utgjevingsnummer på begge tyder at dei verkar
saman: Dataspatium 3.0.0 verkar med Dataregium 3.0.0
([snøggstart](quickstart.md)). Dataspatium legg til ein
Dataregium-server som kjelde: appen oppdagar API-ane gjennom
`/foundation/versions`, loggar inn med OAuth2 authorization code og PKCE og
registrerer seg sjølv som offentleg klient når dynamisk registrering er slått
på, listar modellane og dokumenta i prosjektet, les og skriv BCF-saker med
kommentarar og viewpoints tekne frå 3D-visinga si, lastar opp datasett, filer
og arbeidsområdepakkar gjennom Documents API, spør IFC-grafen med Cypher over
Bolt når operatøren eksponerer han, og sender `X-Request-ID` på kvart kall
slik at førespurnadsloggen her og loggen i appen viser same samtale. Appen
les kapabilitetsdokumentet til serveren for å sjå kva tillegg som er slått
på, og reagerer på feilkodane serveren legg i feilkroppane sine.

Slik heng dei saman:

```mermaid
flowchart LR
    subgraph app ["Dataspatium, i nettlesaren"]
        source["Kjelde og innlogging"]
        issues["Saker i 3D-visinga"]
        files["Modellar og dokument"]
        queries["Spørjingar mot IFC-grafen"]
        log["Loggen i appen"]
        admin["Kortet Administrasjon"]
    end
    subgraph server ["Dataregium, serveren"]
        foundation["Foundation API, OAuth2"]
        bcf["BCF API"]
        documents["Documents API"]
        ifcgraph[("IFC-graf")]
        requests["Førespurnadslogg"]
        adminapi["Administrasjons-API"]
    end
    source <--> foundation
    issues <--> bcf
    files <--> documents
    queries --> ifcgraph
    log <-- "X-Request-ID" --> requests
    admin --> adminapi
```

Bortsett frå dei merkte tillegga går alt Dataspatium gjer mot serveren
gjennom dei tre OpenCDE-API-ane, så appen brukar ingenting ein annan klient
ikkje kan bruke, sjå [OpenCDE-API-a og klientane deira](#opencde-api-a-og-klientane-deira). Dei to produkta blir installerte kvar for
seg: dette repoet buntar ikkje Dataspatium (lisensane er ulike, AGPL her og
PolyForm Strict der), og README-fila til Dataspatium fortel korleis appen
blir henta. Klientsida er skildra i README-fila til Dataspatium og
dokumentasjonen der.

### Utgåvene 1, 2 og 3

Kvart hovudnummer er éi utgåve som blir gjeven ut på nytt etter kvart som ho
veks, og det same nummeret av Dataspatium høyrer til henne. Dei tre skil seg
slik:

- **1.0.0** er ein dokumenttenar: Foundation API 1.0 (versjonar, innlogging med
  OAuth2 og PKCE, gjeldande brukar, sjølvregistrering av klientar når operatøren
  tillèt det) og Documents API 1.0 (velje, laste opp og hente dokument og
  versjonane deira), med webadministrasjonen på sju språk og førespurnadsloggen.
  Det er 2.0.0-koden med berre Documents API slått på (`OPENCDE_APIS`), for
  Dataspatium 1.
- **2.0.0** legg til BCF API 3.0 og 2.1 på dei same dataa (saker, kommentarar,
  viewpoints, dokument) og den valfrie IFC-LPG-modulen som lagar ein graf av
  kvar opplasta IFC-fil, for Dataspatium 2.
- **3.0.0** gjer grafen tapsfri slik at fila kan skrivast tilbake, kontrollerer
  kvar opplasting mot IFC-skjemaet, reglane til buildingSMART og
  IDS-dokumenta i prosjektet, gjev medlemmer namngjevne spørjingar,
  kollisjonskontroll mellom to versjonar, basisversjon ved opplasting, ei
  sperre mot valideringsfeil med førehandskontroll, og endringssett som blir
  prøvde og godkjende til nye versjonar, for Dataspatium 3. IFC-LPG er eit
  eige bibliotek.

## Lær meir

- [docs/nn/quickstart.md](quickstart.md): Dataregium og Dataspatium saman på tjue
  minutt, frå ei tom maskin til ei sak oppretta i 3D-visinga.
- [docs/nn/client-guide.md](client-guide.md) og [docs/examples/](../examples/):
  korleis byggje ein klient, kapabilitetsdokumentet, feilkodane og køyrbare
  døme med Python-biblioteket i [client/](../../client/).
- [docs/nn/architecture.md](architecture.md): korleis delane heng saman, kva som skjer med ein førespurnad, og kvar alt finst i koden.
- [docs/nn/glossary.md](glossary.md): orda dokumentasjonen brukar.
- [docs/nn/flows/](flows/): sekvensdiagram for OAuth2-, Documents API- og BCF-viewpoint-flytane.
- [docs/nn/graph-schema.md](graph-schema.md): grafmodellen.
- [docs/nn/ifc-lpg.md](ifc-lpg.md): den valfrie IFC-LPG-modulen og døme på Cypher-spørjingar.
- Arkitekturavgjerder som ligg fast: grafdatabase som einaste lager, opake token
  i staden for JWT, portabel Cypher for Neo4j og Memgraph, webgrensesnitt utan
  rammeverk, tryggingskopi på applikasjonsnivå, BCF API 2.1 ved sida av 3.0, ein
  tapsfri IFC-graf som sjølv les og skriv STEP og blir validert når han blir
  skriven, reglane til buildingSMART i eit eige miljø, IFC-LPG som bibliotek,
  kontroll mot IDS-en til prosjektet og namngjevne spørjingar for medlemmer.
- [spec/SOURCES.md](../../spec/SOURCES.md): dei nøyaktige
  spesifikasjonsversjonane serveren blir testa mot.

Dokumentasjonen finst på dei sju språka i denne README-fila, kvart språk under
`docs/<språk>/`; engelsk under `docs/en/` er kjelda. CONTRIBUTING er på engelsk.

### Vidare lesing

- [BCF API](https://github.com/buildingSMART/BCF-API), [Foundation API](https://github.com/buildingSMART/foundation-API) og [Documents API](https://github.com/buildingSMART/documents-API):
  spesifikasjonane serveren følgjer.
- [IFC](https://github.com/buildingSMART/IFC4.x-development): filformatet for bygningsmodellar, og [IDS](https://github.com/buildingSMART/IDS): kravspesifikasjonar som modellar vert kontrollerte mot.
- [RFC 9700](https://www.rfc-editor.org/rfc/rfc9700): dagens beste praksis for tryggleik i OAuth 2.0, og
  [OAuth 2.1](https://datatracker.ietf.org/doc/draft-ietf-oauth-v2-1/), utkastet som samlar han.
- [RFC 7636](https://www.rfc-editor.org/rfc/rfc7636) (PKCE), [RFC 8252](https://www.rfc-editor.org/rfc/rfc8252) (appar på datamaskin eller telefon) og
  [RFC 7591](https://www.rfc-editor.org/rfc/rfc7591) (registrering av klientar).
- [OWASP ASVS](https://owasp.org/www-project-application-security-verification-standard/): sjekklista for tryggingsarbeidet.

## Avgrensingar i korte trekk

- Serveren implementerer BCF API 3.0 og 2.1, ikkje 1.0, der ressursane ser annleis ut.
- Eksport av eit prosjekt som BCFzip blir overlaten til klientane; serveren
  lagrar saker, kommentarar og viewpoints slik API-et definerer dei.
- Community-utgåvene av Neo4j og Memgraph har ingen skriveverna
  databasebrukarar, så ein eksponert Bolt-port gjev full tilgang til den som
  har passordet. Porten held seg stengd med mindre administratoren medvite
  publiserer han; den lesande grafspørjinga i administrasjons-API-et
  (`OPENCDE_GRAPH_QUERY_ENABLED`) gjev Cypher utan porten.
- IFC-LPG-importen køyrer i ein eigen prosess med minne- og tidsgrenser
  (`OPENCDE_IFC_LPG_*`); svært store modellar blir avviste i staden for å
  bli liggjande halvt importerte.
- Websidene er for administratorar og for OAuth2- og Documents API-flytane;
  sluttbrukarar arbeider i ein klient som Dataspatium eller Bonsai.
- Sidene finst på dei sju språka i denne README-fila (byt nedst på kvar side);
  kommandolinja og feilmeldingane frå API-ane er på engelsk.
- Ingen ekstern revisjon enno. OAuch- og testssl-køyringane er stega
  operatøren tek før ei produksjonsutrulling.

## Personopplysningar

Den som driv Dataregium for andre, er behandlingsansvarleg for desse dataa.
Serveren lagrar brukarkontoar (brukarnamn, namn, valfri e-post, passordhash),
prosjektmedlemskap, saker og kommentarar med namna til forfattarane, opplasta
filer med opplastar, IFC-grafen med eigarhistorikken til fila og ein
revisjonslogg over kven som gjorde kva og frå kva adresse. Passord, token og
løyndommar blir berre lagra som hashar. Token, økter, opplastingsøkter og
ubrukte sjølvregistrerte klientar går ut og blir rydda av serveren;
revisjonsloggen blir skoren ned av operatøren. Ein administrator slettar ein
konto under `/admin/users`, og øktene og tokena følgjer med; namnet står att på
sakene personen skreiv til dei blir sletta. Revisjonsloggen blir eksportert som
CSV, BCF- og dokumentdata gjennom API-a og heile databasen med `opencde backup`.
Kva Dataspatium lagrar i nettlesaren, står i dokumentasjonen til appen.

## Det neste i 3-serien

3.0.0 er den første utgåva i 3-serien, laga saman med Dataspatium 3.0.0:
IFC-grafen som ein tapsfri modell, kontrollen av kvar opplasting og dei
namngjevne spørjingane, slik [Kva du kan gjere](#kva-du-kan-gjere) skildrar.
Sidan 2026-11-10 rommar ho òg kollisjonskontrollen mellom to versjonar,
basisversjonen ved opplasting, avvisinga av opplastingar med valideringsfeil og
førehandskontrollen av ei fil. Som kvart hovudnummer har serien éi utgåve, som
blir gjeven ut på nytt etter kvart som ho veks. Det som følgjer, gjer grafen til
ein modell som kan redigerast og versjonshandterast i databasen, med Dataspatium
som klienten som redigerer han og viser versjonane. Dei offisielle OpenCDE-API-a
blir verande slik buildingSMART definerer dei; det serien legg til, er
utvidingar av dei under eigne namn. Denne delen seier kva som er avgjort, for
den, menneske eller AI-agent, som fører ein del av det vidare. Avgjerdene står i
korte trekk under [Lær meir](#lær-meir), arbeidsmåtane i
[CONTRIBUTING.md](../../CONTRIBUTING.md) og IFC-grafen i
[docs/nn/ifc-lpg.md](ifc-lpg.md).

### Avgjort

- **Redigering av modellar i Native IFC.** Create er opplastinga og Read dei
  namngjevne spørjingane, begge i 3.0.0. Update er ei endring som ein klient
  føreslår gjennom API-et, og som blir prøvd før ho blir ført inn. Delete
  fjernar valde delar av grafen: ein entitet, ein bygning eller eit prosjekt.
  Export skriv STEP tilbake, som no.
- **Versjonshistorikk i databasen, ikkje i git**, i same ånd som
  [ifcmerge](https://github.com/brunopostle/ifcmerge) av Bruno Postle: kva som
  vart endra, kven som føreslo det, og kven som godkjende det. Dataa må halde
  seg til IFC, ifc-gherkin-rules og IDS-en til prosjektet ved import og etter
  kvar endring.
- **BIM-snippets som ein fungerande demonstrasjon.** Ei føreslått endring reiser
  som `bim_snippet` i ei BCF 3.0-sak, med eit publisert skjema bak
  `reference_schema`, så endringa, diskusjonen og avgjerda er på éin stad.
  Ingen programvare bruker ein snippet i dag, og dei ikkje utgjevne
  utviklingsgreinene til buildingSMART har fjerna dei; Dataregium byggjer dei for
  å vise korleis dei kunne verke. Ein snippet peikar ut det han endrar med
  GlobalId og ein sti derifrå, og med STEP-id berre der ingen GlobalId når. STEP-ida når alltid ein
  instans; GlobalId og sti nådde 98 til 100 prosent av instansane i 28
  prøvefiler, med steg tilbake gjennom inverse attributt.
- **Utvidingar, ikkje nye versjonar av API-a.** BCF-saker med `bim_snippet`,
  metadataa og versjonane i Documents API og kapabilitetsdokumentet ber det
  serien legg til, skildra av ein eigen OpenAPI.
- **Kollisjonskontroll begge stader**: på serveren med IfcClash frå IfcOpenShell
  og i Dataspatium med den eigne kjernen i JavaScript.
- **Administrasjon av eit prosjekt av prosjektleiaren**, som ikkje treng vere
  serveradministrator, og team med ansvar utover prosjektrollene.
- **Korleis ein versjon blir lagra** (avgjort 2026-11-10). Kvar godkjend
  versjon er ein node med forelder, forfattar, godkjennar og endringar per
  GlobalId, sti og attributt; grafen held hovudversjonen; ein versjon blir lagra som
  endringa si, med ei heil fil, som `.ifczip`, berre når han blir publisert, og
  kva versjon som helst blir skriven på førespurnad; to endringar blir slegne
  saman attributt for attributt, slik ifcmerge gjer, og ei endring blir ført
  inn når fila som blir skriven frå ho, ikkje har nokon merknad som versjonen
  før ho mangla. I 3.0.0: basisversjonen ved opplasting (`412` ved konflikt),
  avvisinga av opplastingar med valideringsfeil og førehandskontrollen av ei
  fil. Versjonsnodane og samanslåinga kjem deretter.
- **Kven som får endre kva** (avgjort). Prosjektrollene først: `editor`
  føreslår, `manager` godkjenner, og ein AI føreslår berre. Ansvarsreglar som
  peikar ut ein del av modellen med IDS-utval som klasse, eigenskap,
  klassifikasjon eller etasje, slik dei ansvarlege teama i ISO 19650 gjer, kjem
  seinare.
- **Detaljane i snippeten** (avgjort). Ein sti blir skriven med attributtnamna
  i IFC med indeksar, frå ein GlobalId, med STEP-id berre der ingen GlobalId når; ei endring av
  ein instans som fleire deler, endrar han for alle, og ein eigen kopi må bedast
  om; kvar endring ber kven som føreslo henne, og kva AI-modell og kva
  verktøykall, der ein AI gjorde det.

## Feil og framlegg

Rapporter feil og ønske som *Issues* her på GitHub. Oppgje kva serverversjon
du køyrer (`version` i `/.well-known/dataregium` eller `/healthz`), kva klient
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

Kode og kommentarar er på engelsk, og stilen følgjer konvensjonane til
IfcOpenShell (ruff, 120 kolonnar), slik at det held fram med å vere mogleg å
bidra med serveren til IfcOpenShell. README finst på engelsk, svensk, dansk, norsk (bokmål og nynorsk),
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
