<img src="../../opencde/ui/static/icon.svg" alt="" width="72" height="72" align="left">

# Kontroll OpenCDE-server

*[English](../../README.md) · [Svenska](../sv/README.md) · [Dansk](../da/README.md) · [Norsk bokmål](../nb/README.md) · Norsk nynorsk · [Suomi](../fi/README.md) · [Íslenska](../is/README.md)*

Ein server for **OpenCDE-API-ane** frå buildingSMART, bygd på ein grafdatabase:

- **Foundation API 1.0**: oppdaging av tenester, OAuth2 authorization code med PKCE, noverande brukar
- **BCF API 3.0**: prosjekt, extensions, saker, kommentarar, viewpoints, filer, dokumentreferansar, dokument, hendingar
- **Documents API 1.0**: val og nedlasting av dokument, opplasting i delar, versjonsspørjingar

og dessutan eit webgrensesnitt for administrasjon av brukarar, OAuth2-klientar
og prosjekt, og ein valfri IFC-grafmodul som gjer opplasta IFC-modellar til
grafdata, slik at BCF-komponentar kan knytast til bygningsdelane dei peikar på.

Prosjektet voks fram av ein forskingsprototyp frå 2023 som prøvde ut om BCF
API og IFC-graf kan bere dei digitale kontrollplanane som krevst for
byggjeløyve i Sverige. Dette repoet er ei omskriving av prototypen frå grunnen
av, med same funksjonar, moderne avhengnader og tryggleik som fyrste krav.
Status: **alle 11 etappane i planen er gjennomførte** (dei tre API-ane,
administrasjonsgrensesnittet, klientbiblioteket, utrulling, IFC-graf,
akseptansesjekklista og tryggingsherdinga); bidraget til IfcOpenShell ventar
på svar frå vedlikehaldarane (utkast i [docs/upstream/](../upstream/)). Sjå
[docs/inventory.md](../inventory.md) for kva prototypen gjorde og kvar kvar
funksjon står i den nye koden.

## Snøggstart (lokalt, Docker)

Krav: Docker (Desktop på Windows/macOS, Engine på Linux) og
[uv](https://docs.astral.sh/uv/).

```sh
git clone https://github.com/marwiss/Kontroll.git
cd Kontroll
cp .env.example .env            # set OPENCDE_GRAPH_PASSWORD (minst 16 teikn)
docker compose -f compose.yaml -f compose.dev.yaml up -d --build
```

Opne deretter <http://localhost:8000/docs> for den interaktive
API-dokumentasjonen, <http://localhost:8000/readyz> for
beredskapskontrollen og <http://localhost:7484> for Neo4j Browser (Bolt på
`localhost:7697`; utviklingsoverlegget unngår standardportane til Neo4j, som
ofte er opptekne av ein annan Neo4j på same maskin). `docker compose logs -f
api` viser serverloggen.

Utan Docker for sjølve serveren (ein database trengst framleis):

```sh
uv sync                          # installerer Python 3.13 og alle avhengnader
uv run opencde doctor            # kontrollerer konfigurasjon og database
uv run opencde serve             # http://127.0.0.1:8000
```

## Utrulling

Éi compose-fil pluss eitt overlegg per scenario, og eit publisert image for
fleire arkitekturar (`ghcr.io/marwiss/opencdeserver`, skanna og med SBOM ved
kvar utgjeving):

| Scenario | Rettleiing |
|---|---|
| Lokal test på eiga maskin | [docs/deploy/local.md](../deploy/local.md) |
| Offentleg https-adresse for klienttestar utan eigen server (tunnel) | [docs/deploy/tunnel.md](../deploy/tunnel.md) |
| Produksjon på eigen server med Caddy (automatisk TLS) og nattlege tryggingskopiar | [docs/deploy/vps-caddy.md](../deploy/vps-caddy.md) |
| Coolify, Dokploy, Portainer | [docs/deploy/paas.md](../deploy/paas.md) |
| Containerteneste pluss administrert Neo4j AuraDB eller Memgraph Cloud | [docs/deploy/cloud-aura.md](../deploy/cloud-aura.md) |
| Tryggingskopiering og gjenoppretting (flyttbar mellom Neo4j og Memgraph) | [docs/deploy/backup.md](../deploy/backup.md) |

`uv run opencde init --public-url https://cde.example.org` skriv ei
produksjons-`.env` med nye løyndomar; `opencde doctor` kontrollerer
resultatet.

## Konfigurasjon

Alt blir lese frå miljøvariablar med prefikset `OPENCDE_`, frå `.env` eller
frå Docker-løyndomar i `/run/secrets/opencde_<namn>`. Den kommenterte lista
finst i [.env.example](../../.env.example). Standardverdiane er trygge:
produksjon nektar å starte utan ei offentleg `https`-adresse og eit
databasepassord.

## Dokumentasjon

Dokumentasjonen er på engelsk; omsetjingar til svensk, dansk, norsk (bokmål
og nynorsk), finsk og islandsk er planlagde.

- [docs/inventory.md](../inventory.md): funksjonsinventar over prototypen frå
  2023 og status i omskrivinga, med merknader om særdrag i spesifikasjonane
- [docs/client-guide.md](../client-guide.md) og [docs/examples/](../examples/):
  korleis byggje ein klient; køyrbare døme med Python-biblioteket i [client/](../../client/)
- [docs/flows/](../flows/): sekvensdiagram for OAuth2- og Documents API-flytane
- [docs/graph-schema.md](../graph-schema.md): grafmodellen
- [docs/ifcgraph.md](../ifcgraph.md): den valfrie IFC-grafmodulen og døme på Cypher-spørjingar
- [docs/ui-styleguide.md](../ui-styleguide.md): reglar for sidene til serveren
- [docs/acceptance.md](../acceptance.md): sjekkliste for visuell akseptanse
  med uavhengige klientar (Bonsai, ifc-lite, Dataspatium)
- [docs/dataspatium-coordination.md](../dataspatium-coordination.md): kva
  Kontroll og Dataspatium deler og kva meir som blir samordna, med avgjerdene til eigaren
- [docs/adr/](../adr/): arkitekturavgjerder (grafdatabase, opake tokens,
  portabel Cypher, webgrensesnitt utan rammeverk, repostrategi)
- [docs/security/](../security/): trugsmålsmodell, kontrollar knytte til
  testar, OWASP ASVS nivå 2-sjekklista og korleis skannarane blir køyrde
- [docs/upstream/](../upstream/): utkast til sak og pull request for
  IfcOpenShell (ikkje sende)
- [spec/SOURCES.md](../../spec/SOURCES.md): dei nøyaktige
  spesifikasjonsversjonane serveren blir testa mot

## Administrasjon

Logg inn på `/signin` med ein administratorkonto og opne `/admin` for å
administrere brukarar og prosjektrollene deira, prosjekt og BCF-extension-
verdiane deira, OAuth2-klientar, sesjonar, revisjonsloggen, den valfrie
førespurnadsloggen og helsekontrollane til serveren. Kvar brukar har
`/account` for eige passord, eigne appar og eigne sesjonar. Kommandolinja
(`uv run opencde --help`) gjer det same frå ein terminal, og
administrasjonsklientar med scopet `admin` kan lese førespurnadsloggen på
`/admin/api/requests`.

## Kontroll og Dataspatium

Kontroll (serveren) og [Dataspatium](https://github.com/marwiss/Dataspatium)
(ein dataapp som køyrer heilt i nettlesaren) er utvikla for å verke saman som
server og klient. Dataspatium legg til ein Kontroll-server som kjelde: appen
oppdagar API-ane gjennom `/foundation/versions`, loggar inn med OAuth2
authorization code og PKCE og registrerer seg sjølv som offentleg klient når
sjølvregistrering er slått på, listar modellane og dokumenta i prosjektet,
les og skriv BCF-saker med kommentarar og viewpoints tekne frå 3D-visinga si,
lastar opp datasett, filer og arbeidsområdepakkar gjennom Documents API, spør
IFC-grafen med Cypher over Bolt når operatøren eksponerer han, og sender
`X-Request-ID` på kvart kall slik at førespurnadsloggen her og loggen i appen
viser same samtale. Appen les kapabilitetsdokumentet til serveren
(`/.well-known/kontroll`) for å sjå kva tillegg som er slått på, og reagerer
på dei stabile feilkodane serveren legg i feilkroppane sine. Bortsett frå
grafspørjingane, administrasjons-API-et, kapabilitetsdokumentet og
feilkodane, som er tillegg utanfor spesifikasjonane, går alt Dataspatium gjer
mot serveren gjennom dei tre OpenCDE-API-ane, så andre OpenCDE-klientar
verkar òg, og Kontroll tener kvar OpenCDE-klient. Dei to produkta blir
installerte kvar for seg: dette repoet buntar ikkje Dataspatium (lisensane er
ulike, AGPL her og PolyForm Strict der), og README-fila til Dataspatium
fortel korleis appen blir henta. Klientsida er skildra i README-fila til
Dataspatium og dokumentasjonen der (`docs/kallor.md`, `docs/cad-bim.md`);
akseptansekøyringane til paret står i [docs/acceptance.md](../acceptance.md)
her, og kva dei to prosjekta samordnar står i
[docs/dataspatium-coordination.md](../dataspatium-coordination.md).

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
dokumentasjonen og webgrensesnittet skal finnast på dei same språka, med
engelsk alltid som eit val, og felles termar følgjer ordlista til Dataspatium.

## Tryggleik

Sjå [SECURITY.md](../../SECURITY.md) for korleis ein sårbarheit blir
rapportert og kva prosjektet gjer for å halde seg trygt.

## Lisens

Serveren er lisensiert under GNU Affero General Public License v3.0 eller
seinare ([LICENSE](../../LICENSE)): han er serverprogramvare, og
nettverksklausulen i AGPL held forbetringar av driftssette instansar opne.
Klientbiblioteket i [client/](../../client/) er LGPL-3.0-or-later.
Spesifikasjonsfilene under [spec/](../../spec/) er © buildingSMART
International og blir vidaredistribuerte uendra for testing.
