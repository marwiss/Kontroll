# Snøggstart: Kontroll og Dataspatium saman

Tjue minutt frå ingenting til ei sak oppretta i ei 3D-vising og synleg i
loggane til serveren. Den same sida finst i repoet til Dataspatium; dei to
blir haldne identiske. Du treng Docker (Desktop på Windows/macOS, Engine på
Linux), [uv](https://docs.astral.sh/uv/), Python 3 for ein lokal webserver
og Microsoft Edge, Google Chrome eller Firefox.

## 1. Start Kontroll

```sh
git clone https://github.com/marwiss/Kontroll.git
cd Kontroll
cp .env.example .env
```

Opne `.env` og set `OPENCDE_GRAPH_PASSWORD` til ein vilkårleg verdi på minst
16 teikn, `OPENCDE_DYNAMIC_CLIENT_REGISTRATION=true` slik at Dataspatium kan
registrere seg sjølv, og `OPENCDE_ALLOW_LOCALHOST_REDIRECTS=true` slik at ein
app som blir servert frå `http://localhost` får logge inn. Deretter:

```sh
docker compose -f compose.yaml -f compose.dev.yaml up -d --build
docker compose -f compose.yaml -f compose.dev.yaml exec api opencde seed
```

Den andre kommandoen opprettar demobrukarar og prosjekt og skriv ut passorda
deira éin gong; ta vare på passorda til `admin` og `inspection_manager`. Kontroller
<http://localhost:8000/readyz> (svarar `ready`) og logg inn på
<http://localhost:8000/signin> som `admin`: `/admin` viser prosjekta
*Building permit* og *Demolition permit*.

Om Compose stoppar med `dependency failed to start: container
kontroll-graph-1 is unhealthy`, les `docker compose -f compose.yaml -f
compose.dev.yaml logs graph`. Den vanlege årsaka er eit passord på under 16
teikn, som Neo4j avviser (`A password must be at least 16 characters`); den
andre er eit databasevolum frå ei tidlegare installasjon med eit anna passord,
som `docker compose -f compose.yaml -f compose.dev.yaml down -v` fjernar saman
med dataa. To utsjekkingar på same maskin deler Compose-prosjektnamnet
`kontroll`, så den andre treng `COMPOSE_PROJECT_NAME=kontroll-2` og andre
`OPENCDE_DEV_*`-portar i si `.env`.

## 2. Start Dataspatium

1. Last ned `dataspatium-<version>.zip` frå
   [siste utgjeving](https://github.com/marwiss/Dataspatium/releases/latest)
   og samanlikn SHA-256 med den i utgjevingsteksten.
2. Pakk ut ZIP-fila i ei eiga mappe (ikkje inne i ZIP-fila).
3. For alt unnateke OpenCDE-innlogginga held det å dobbeltklikke på
   `index.html`. For OpenCDE må mappa serverast over http, fordi
   OAuth2-omdirigeringa treng ei http-adresse:

   ```sh
   cd dataspatium-<version>
   python -m http.server 8080
   ```

   og opne <http://localhost:8080/>. Appen registrerer seg sjølv hos serveren
   som offentleg klient med `http://localhost:8080/oauth-callback.html` som
   redirect-URI. (Den publiserte appen på
   <https://marwiss.github.io/Dataspatium/> verkar i staden mot ein server som
   tillèt den adressa.)

## 3. Kople dei to saman

Appen må vere opna via `http://localhost:8080` (steg 2). Opna frå mappa kan
han ikkje registrere seg sjølv, og då må ein klient-id frå `/admin/clients`
fyllast inn i staden.

I Dataspatium: modusen *Inhämta* (Importer) → knappen *Lägg till källa* (Legg
til kjelde) → kortet *Lägg till databaskälla* (Legg til databasekjelde) →
*Typ av tjänst* (Tenestetype): *OpenCDE (BCF, Documents)* →
*Adress* (Adresse): `http://localhost:8000` → *Lägg till* (Legg til). Kjelda
opnar seg i *Inhämta*: trykk *Logga in* (Logg inn) og logg inn som `inspection_manager` i
popup-vindauget, og vel deretter *Building permit* i lista *Projekt*. Lina
under overskrifta ("Servern: Kontroll OpenCDE server 2.0.0. Tillägg: …") kjem
frå kapabilitetsdokumentet til serveren og seier kva tillegg som er slått på.

## 4. Opprett ei sak frå 3D-visinga

1. Hent dømemodellen. Seeden har alt lagt `three_walls_gtin.ifc` (tre veggar
   med GTIN 3, 2 og 1) som eit dokument i *Building permit*; i visinga til
   kjelda i *Inhämta* har dokumentlista ein henteknapp per dokument, og
   dokumentet blir eit modelldatasett. Vil du heller sende di eiga fil, bruk
   modusen *Dela* (Del) → fana *Till CDE* (Til CDE): vel kjelde og prosjekt,
   *Vad* (kva: originalfil, eksport eller pakke), *Hur* (korleis: Documents
   API eller BCF) og *Skicka* (Send); hent henne så tilbake på same måte.
2. Vel modellen i *Bearbeta* (Arbeid med); han opnar seg automatisk i 3D.
   Marker ein vegg, opne panelet *Ärenden* (Saker) og trykk *Nytt ärende* (Ny
   sak): gje henne ein tittel, behald statusen og kryss av for *Lägg till vyn
   som viewpoint* (Legg til visinga som viewpoint). Saka blir oppretta
   gjennom BCF API med eit viewpoint der komponenten peikar på veggen.
3. Skriv ein kommentar i same panel og send han.

## 5. Sjå det på serveren

- `/admin/projects` → *Building permit* viser to saker (den seeda og di) og
  dokumentet.
- `/admin/audit` listar innlogginga og registreringa av appen.
- Med `OPENCDE_REQUEST_LOG_ENABLED=true` i `.env` (og omstart) viser
  `/admin/requests` kvart kall appen gjorde, med dei same
  `X-Request-ID`-verdiane som kortet *Logg* nedst i visinga til OpenCDE-kjelda
  i *Inhämta*, slik at eit mislukka kall kan finnast på begge sider.
- Med `OPENCDE_IFCGRAPH_ENABLED=true` blir den opplasta modellen ein graf;
  Neo4j Browser på <http://localhost:7484> (`bolt://localhost:7697`, brukar og
  passord frå `.env`) viser veggen som ein `IfcWall`-node knytt til
  komponenten i viewpointet med `SAME_AS`, og grafvisinga i Dataspatium kan
  spørje han med Cypher.

## Neste steg

- [docs/client-guide.md](../client-guide.md) om API-ane,
  kapabilitetsdokumentet og feilkodane.
- [docs/acceptance.md](../acceptance.md) om sjekklistene paret blir testa
  med, og [docs/dataspatium-coordination.md](../dataspatium-coordination.md)
  om kva dei to prosjekta samordnar.
- [docs/deploy/](../deploy/) når serveren skal køyre for andre.
