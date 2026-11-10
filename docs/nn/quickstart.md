# Snøggstart: Dataregium og Dataspatium saman

Frå ei tom datamaskin til innlogga i Dataregium frå Dataspatium, med ei sak oppretta i
ei 3D-vising og synleg i loggane til serveren. Det tek omtrent tjue minutt, mest det
første bygget. Følg stega i rekkjefølgje, og bruk adresser og portar nøyaktig slik dei
står: nesten alle problem kjem av ei overhoppa innstilling eller ei anna adresse.
[Feilsøking](#feilsøking) seier kva du gjer om noko går gale. Den same sida finst i
repoet til Dataspatium; dei to blir haldne identiske.

## Dette treng du

- Docker: Docker Desktop på Windows og macOS, Docker Engine med compose-tillegget på
  Linux. Det må køyre: `docker version` svarar for både klient og server.
- Git, eller kjeldekode-ZIP-en frå den
  [siste utgåva](https://github.com/marwiss/Dataregium/releases/latest) av Dataregium i
  staden for `git clone` nedanfor.
- Python 3, som ein liten lokal webserver.
- Microsoft Edge, Google Chrome eller Firefox.
- Portane 8000, 7484, 7697 og 8080 ledige på maskina.

Har du prøvd Dataregium på denne maskina før, byrj med
[Start på nytt](#start-på-nytt).

## 1. Start Dataregium

```sh
git clone https://github.com/marwiss/Dataregium.git
cd Dataregium
cp .env.example .env
```

I ledeteksten i Windows blir `copy` brukt i staden for `cp`.

Opne `.env` i eit tekstredigeringsprogram. Dei fire linjene nedanfor finst allereie i
fila: endre dei slik at dei ser slik ut, og lagre. Vel ditt eige passord, minst 16
teikn, berre bokstavar og tal.

```ini
OPENCDE_GRAPH_PASSWORD=YourOwnPassword1234
OPENCDE_DYNAMIC_CLIENT_REGISTRATION=true
OPENCDE_REQUEST_LOG_ENABLED=true
OPENCDE_IFC_LPG_ENABLED=true
```

| Linje | Kva ho gjer | Utan ho |
|---|---|---|
| `OPENCDE_GRAPH_PASSWORD` | Passordet til grafdatabasen | Kortare enn 16 teikn: databasen startar ikkje |
| `OPENCDE_DYNAMIC_CLIENT_REGISTRATION` | Lèt Dataspatium registrere seg sjølv hos serveren | Steg 3 stoppar, og appen ber om ein klient-id |
| `OPENCDE_REQUEST_LOG_ENABLED` | Lagrar kalla frå appen | Førespurnadsloggen i steg 5 blir verande tom |
| `OPENCDE_IFC_LPG_ENABLED` | Gjer opplasta modellar til ein graf | Ingen graf i steg 5 |

Innstillingane er for å prøve Dataregium på di eiga maskin, ikkje for ein server som
andre bruker.

Start serveren og last inn demodata:

```sh
docker compose up -d --build --wait
docker compose exec api opencde seed
```

Den første kommandoen tek nokre minutt første gongen og er ferdig når serveren køyrer.
Den andre opprettar demobrukarar og prosjekt og skriv ut passorda deira **éin gong**:
ta vare på passorda til `admin` og `inspection_manager` no. La linjene som byrjar med
`client`, vere; Dataspatium registrerer sin eigen klient.

Kontroller at det verkar: <http://127.0.0.1:8000/readyz> svarar `"status":"ready"`.
Logg inn på <http://127.0.0.1:8000/signin> som `admin`, og opne
<http://127.0.0.1:8000/admin/projects>, som viser *Building permit* og
*Demolition permit*.

Når du seinare endrar `.env`, køyrer du `up`-kommandoen på nytt. `docker compose
restart` les ikkje fila.

## 2. Start Dataspatium

1. Last ned `dataspatium-<version>.zip` frå den
   [siste utgåva](https://github.com/marwiss/Dataspatium/releases/latest),
   og samanlikn SHA-256-summen med den i utgåveteksten (`Get-FileHash` i PowerShell,
   `shasum -a 256` på macOS og Linux).
2. Pakk ut ZIP-fila i di eiga mappe. Windows kan opprette ei mappe i mappa; det som
   tel, er mappa der `index.html` ligg direkte.
3. Opne ein terminal i den mappa, og start ein webserver på port 8080:

   ```sh
   python -m http.server 8080 --bind 127.0.0.1
   ```

   Kommandoen kan heite `python3` på macOS og Linux og `py` på Windows. La terminalen
   vere open medan du bruker appen. Oppgje alltid porten: utan han tek Python 8000, som er porten til Dataregium.
4. Opne <http://127.0.0.1:8080/>, skrive akkurat slik: serveren sender nettlesaren tilbake etter innlogginga til `127.0.0.1`, ikkje til `localhost`. Ikkje dobbeltklikk på `index.html`: opna frå mappa
   kan ikkje appen registrere seg sjølv. Appen lastar seg sjølv på nytt éin gong ved
   første start.
5. Første start spør om språk: vel eitt, og trykk *Hald fram på …*. Denne sida bruker
   dei nynorske namna. Panelet *Velkomen til Dataspatium* tilbyr eit kurs: trykk
   *Ikkje no*.

## 3. Logg inn i Dataregium frå Dataspatium

1. Vel modusen *Hent*. I venstre kolonne, under *Legg til kjelder*, vel du *OpenCDE*.
2. Under *Adresse* skriv du `http://127.0.0.1:8000`. **La *Klient-id* og hemmelegheita
   stå tomme**: appen registrerer seg sjølv, sjølv om teksten i dialogen snakkar om ein
   klient-id frå administratoren. Trykk *Legg til kjelde*.
3. Appen spør *Tillate internettilgang?* opptil tre gonger, éin gong per føremål. Her
   gjeld det berre din eigen server: trykk *Tillat* kvar gong.
4. Kjelda blir opna og vist under *Tillagde kjelder*. Linja "Tenaren: Dataregium OpenCDE
   server <version>. Tillegg: …" kjem frå kapabilitetsdokumentet til serveren og seier
   kva tillegg som er slått på. Merket *Krev nøkkel* kan du sjå bort frå: det som
   trengst, er innlogginga.
5. Trykk *Logg inn*. Eit popup-vindauge blir opna med innloggingssida til serveren. Om
   nettlesaren blokkerer det, tillat popup-vindauge for `http://127.0.0.1:8080`, og
   trykk igjen.
6. Logg inn som `inspection_manager` med passordet frå steg 1, og trykk *Tillat og logg
   inn*. Ikkje bruk `admin`, som ikkje er med i noko prosjekt. Vindauget lukkar seg
   sjølv, og kjelda seier *Innlogga som Certified inspection manager*.
7. *Building permit* er allereie vald i lista *Prosjekt*.

Du er innlogga til sida blir lasta på nytt; trykk då *Logg inn* igjen. Kjelda blir
verande.

## 4. Opprett ei sak frå 3D-visinga

1. I visinga av kjelda finn du *Filer i prosjektet* og trykkjer *Vis filer*.
   `opencde seed` la `three_walls_gtin.ifc` der (tre veggar med GTIN 3, 2 og 1). Trykk
   *Hent*: fila blir eit modelldatasett.
2. Vel modusen *Bearbeid*; modellen blir opna i 3D. Klikk på ein vegg for å merke han.
3. Trykk *Saker* over 3D-visinga og deretter *Ny sak* i høgre kolonne. Skriv noko under
   *Tittel*, og trykk *Opprett sak*. Saka blir oppretta gjennom BCF-API-et, og visinga
   og den merkte veggen følgjer med som viewpoint.
4. Under saka skriv du noko i *Skriv ein kommentar* og trykkjer *Send*.

## 5. Sjå det på serveren

Innlogga som `admin` opnar du <http://127.0.0.1:8000/admin>:

- *Prosjekt* viser *Building permit* med to saker (den frå `opencde seed` og di) og eitt
  dokument.
- *Revisjonslogg* viser innlogginga og registreringa av appen.
- *Førespurnadslogg* viser kvart kall appen gjorde, med dei same
  `X-Request-ID`-verdiane som kortet *Logg* nedst i visinga av kjelda i *Hent*, slik at
  eit mislukka kall kan finnast på begge sider.

Eksempelmodellen er allereie ein graf, fordi `OPENCDE_IFC_LPG_ENABLED=true` stod i
`.env` då du køyrde `opencde seed`. Neo4j Browser på <http://127.0.0.1:7484> (kople til
`bolt://127.0.0.1:7697` som `neo4j` med passordet frå `.env`) svarar på denne
spørjinga med veggen kopla til komponenten i viewpointen:

```cypher
MATCH (c:Component)-[:SAME_AS]->(w:IfcWall) RETURN c, w
```

Ein modell du sender frå Dataspatium, blir ein graf på same måte. For å prøve det,
trykk *Logg ut* øvst på sida til serveren, fordi opplastinga blir gjord som ein annan
brukar:

1. I Dataspatium vel du modusen *Del* og fana *Til CDE*. Under *Kva* vel du
   *Originalfila* og trykkjer *Send*.
2. *Gjennomgang før deling* viser kva som følgjer med: trykk *Hald fram*.
3. Opplastingssida til serveren blir opna i eit popup-vindauge. Logg inn som
   `inspection_manager`, og trykk *Lagre og hald fram*. Vindauget lukkar seg sjølv.

I løpet av nokre sekund finn same spørjinga òg veggen i den nye modellen.

## Feilsøking

Kvar rad siterer skjermen slik han ser ut med dei nynorske namna.

| Dette ser du | Kvifor | Gjer slik |
|---|---|---|
| `Cannot connect to the Docker daemon`, `error during connect` eller `docker: command not found` | Docker køyrer ikkje | Start Docker Desktop, vent til det seier at det køyrer, og køyr kommandoen på nytt |
| `dependency failed to start: container dataregium-graph-1 is unhealthy` | Eit passord på færre enn 16 teikn, som Neo4j avviser (`docker compose logs graph` seier `A password must be at least 16 characters`), eller eit databasevolum att frå ein tidlegare installasjon med eit anna passord | Rett passordet, og køyr `up`-kommandoen på nytt. For det gamle volumet, sjå [Start på nytt](#start-på-nytt) |
| `port is already allocated`, `Ports are not available` eller `address already in use` | Eit anna program har 8000, 7484 eller 7697, kanskje ein tidlegare Dataregium (`docker ps` viser det) | Stopp det, eller oppgje andre portar med `OPENCDE_DEV_PORT`, `OPENCDE_DEV_NEO4J_HTTP_PORT` og `OPENCDE_DEV_NEO4J_BOLT_PORT` i `.env`, og bruk din port i staden for 8000 frå då av |
| Containerane frå ei anna mappe blir erstatta | To utsjekkingar på éi maskin deler Compose-prosjektnamnet `dataregium` | Gi den andre `COMPOSE_PROJECT_NAME=dataregium-2` og andre `OPENCDE_DEV_*`-portar i `.env`-fila si |
| `the database is not empty` | `opencde seed` har allereie køyrt og skreiv ut passorda då | Få eit nytt passord med `docker compose exec api opencde user set-password inspection_manager`, eller [start på nytt](#start-på-nytt) |
| `python` finst ikkje, eller Microsoft Store blir opna | Kommandoen heiter noko anna på denne maskina | Bruk `py` eller `python3` |
| Ei filliste i staden for appen | Webserveren køyrer i den ytre mappa | Stopp han med Ctrl+C, og start han i mappa der `index.html` ligg |
| Ein gammal versjon av appen, eller noko heilt anna | Noko anna svarar på port 8080; på Windows kan ein andre webserver starte på same port utan feil | Bruk ein annan port, `python -m http.server 8090 --bind 127.0.0.1`, og opne `http://127.0.0.1:8090/` |
| *Appen kan registrere seg sjølv hos tenaren berre når han køyrer frå ein webserver …* | Appen vart opna frå mappa | Opne `http://127.0.0.1:8080/` |
| *Kunne ikkje nå 127.0.0.1:8000 …* | Dataregium køyrer ikkje, eller adressa er feilskriven | <http://127.0.0.1:8000/readyz> må svare. Adressa er `http://127.0.0.1:8000` utan noko etter |
| *Tenaren tillèt ikkje at appen registrerer seg sjølv …* | `OPENCDE_DYNAMIC_CLIENT_REGISTRATION` er ikkje `true` | Endre `.env`, køyr `up`-kommandoen på nytt, og trykk *Legg til kjelde* igjen |
| *Registreringa mislukkast:* … `Redirect URIs to http://localhost are not allowed here` | Appen vart opna på `localhost`, som serveren ikkje godtek som veg tilbake | Opne `http://127.0.0.1:8080/`, og legg til kjelda der |
| *Registreringa mislukkast:* … `rate_limited` | Fleire enn 60 registreringar innan ein time; kvar *Legg til kjelde* med tom *Klient-id* er éi | `docker compose restart api` nullstiller teljaren |
| *Internettilgang for … er ikkje tillaten.* | Det vart trykt *Avslå* | Tillat det under *Handter*, *Arbeidsområde*, *Internettilgang*, og prøv igjen |
| *Nettlesaren blokkerte innloggingsvindauget …* | Blokkeringa av popup-vindauge i nettlesaren | Tillat popup-vindauge for `http://127.0.0.1:8080`, og trykk *Logg inn* igjen |
| I popup-vindauget: *Kan ikkje halde fram* og *Ukjend klient.* | Serveren har gløymt registreringa av appen, som regel etter `down -v` | Lukk vindauget, og last appen på nytt, fordi *Logg inn* elles spinn i fem minutt. Slett kjelda med krysset ved sida av ho under *Tillagde kjelder*, og legg ho til igjen |
| I popup-vindauget: *Kan ikkje halde fram* og *Redirect-URI-en er ikkje registrert for denne klienten.* | *Klient-id* vart fylt ut, til dømes frå utskrifta av `opencde seed` | Lukk vindauget, og last appen på nytt. Slett kjelda med krysset ved sida av ho under *Tillagde kjelder*, og legg ho til igjen med tom *Klient-id* |
| I popup-vindauget: *Brukarnamnet eller passordet er ikkje rett.* | Kvar brukar har sitt eige passord frå `opencde seed` | Bruk det rette, eller få eit nytt som ovanfor |
| *For mange mislukka forsøk for dette brukarnamnet …* | Fem feil passord på rad får serveren til å vente, høgst 15 minutt | Vent så lenge det står, og bruk passordet frå `opencde seed` |
| *Skjemaet har gått ut. Prøv igjen.* på `/signin`, eller i popup-vindauget *Kan ikkje halde fram* og *Innloggingsskjemaet har gått ut eller er endra. Start på nytt.*, sjølv om du nettopp opna sida. `docker compose logs api` viser `foreign_service_worker_removed` | Ein service worker i nettlesaren din frå ein annan webapp som ein gong har køyrt på `http://127.0.0.1:8000`, til dømes starta med `python -m http.server` utan port. Han svarar med gamle kopiar av sidene til Dataregium | Vent nokre sekund til sida har lasta seg på nytt, og prøv igjen, fordi Dataregium fjernar ein slik worker. Om meldinga blir ståande, fjern han for hand: `about:debugging#/runtime/this-firefox` i Firefox, `edge://serviceworker-internals` i Edge, `chrome://serviceworker-internals` i Chrome; finn `127.0.0.1:8000`, og vel *Unregister*. Kvar nettlesar har sin eigen, også ein som er innebygd i ein editor. Eit privat vindauge har ingen, noko som raskt viser om dette er årsaka. Hald andre appar borte frå port 8000 |
| *Du er ikkje medlem i noko prosjekt på tenaren.* | Du logga inn som `admin`, som ikkje er med i noko prosjekt | Trykk *Logg ut* og deretter *Logg inn* som `inspection_manager` |
| *Logg inn* held fram med å spinne | Vindauget vart lukka før innlogginga var ferdig | Last sida på nytt |
| Vindauget seier *Kopiera adressen … / Copy the address …* | Det kunne ikkje nå vindauget til appen, som kanskje vart lukka eller lasta på nytt i mellomtida | Lukk vindauget, og trykk *Logg inn* igjen |
| *Ein annan konto* på opplastingssida | Nettlesaren er logga inn på serveren som `admin`, som ikkje starta opplastinga | Trykk *Logg ut* på den sida, og logg inn som `inspection_manager`; opplastinga held så fram i same vindauge |

## Start på nytt

I mappa du starta frå (eller kvar som helst, med `-p dataregium`):

```sh
docker compose down -v
```

Det slettar databasen og filene til demoen. Køyr deretter `up`- og `seed`-kommandoane i
steg 1 på nytt, noko som gir nye passord. I Dataspatium slettar du kjelda med krysset
ved sida av ho under *Tillagde kjelder* og legg ho til igjen, fordi serveren har gløymt
registreringa av appen.

For å stoppe utan å slette noko utelèt du `-v`, og webserveren stoppar du med Ctrl+C.

## Neste steg

- [docs/nn/client-guide.md](client-guide.md) om API-ane,
  kapabilitetsdokumentet og feilkodane.
- [docs/nn/deploy/](deploy/) når serveren skal køyre for andre.
