# Hurtigstart: Kontroll og Dataspatium sammen

Fra en tom datamaskin til innlogget i Kontroll fra Dataspatium, med en sak opprettet
i en 3D-visning og synlig i serverens logger. Det tar omtrent tjue minutter, mest det
første bygget. Følg trinnene i rekkefølge, og bruk adresser og porter nøyaktig slik
de står: nesten alle problemer kommer av en overhoppet innstilling eller en annen
adresse. [Feilsøking](#feilsøking) sier hva du gjør hvis noe går galt. Den samme
siden finnes i Dataspatiums repo; de to holdes identiske.

## Dette trenger du

- Docker: Docker Desktop på Windows og macOS, Docker Engine med compose-tillegget på
  Linux. Det må kjøre: `docker version` svarer for både klient og server.
- Git, eller kildekode-ZIP-en fra Kontrolls
  [siste utgivelse](https://github.com/marwiss/Kontroll/releases/latest) i stedet for
  `git clone` nedenfor.
- Python 3, som en liten lokal webserver.
- Microsoft Edge, Google Chrome eller Firefox.
- Portene 8000, 7484, 7697 og 8080 ledige på maskinen.

Har du prøvd Kontroll på denne maskinen før, begynn med
[Start på nytt](#start-på-nytt).

## 1. Start Kontroll

```sh
git clone https://github.com/marwiss/Kontroll.git
cd Kontroll
cp .env.example .env
```

I Windows' ledetekst brukes `copy` i stedet for `cp`.

Åpne `.env` i et tekstredigeringsprogram. De fem linjene nedenfor finnes allerede i
filen: endre dem slik at de ser slik ut, og lagre. Velg ditt eget passord, minst 16
tegn, bare bokstaver og tall.

```ini
OPENCDE_GRAPH_PASSWORD=YourOwnPassword1234
OPENCDE_DYNAMIC_CLIENT_REGISTRATION=true
OPENCDE_ALLOW_LOCALHOST_REDIRECTS=true
OPENCDE_REQUEST_LOG_ENABLED=true
OPENCDE_IFCGRAPH_ENABLED=true
```

| Linje | Hva den gjør | Uten den |
|---|---|---|
| `OPENCDE_GRAPH_PASSWORD` | Passordet til grafdatabasen | Kortere enn 16 tegn: databasen starter ikke |
| `OPENCDE_DYNAMIC_CLIENT_REGISTRATION` | Lar Dataspatium registrere seg selv hos serveren | Trinn 3 stopper, og appen ber om en klient-id |
| `OPENCDE_ALLOW_LOCALHOST_REDIRECTS` | Lar en app som er åpnet på `http://localhost`, logge inn | Trinn 3 stopper med en mislykket registrering |
| `OPENCDE_REQUEST_LOG_ENABLED` | Lagrer appens kall | Forespørselsloggen i trinn 5 forblir tom |
| `OPENCDE_IFCGRAPH_ENABLED` | Gjør opplastede modeller til en graf | Ingen graf i trinn 5 |

Innstillingene er for å prøve Kontroll på din egen maskin, ikke for en server som
andre bruker.

Start serveren og last inn demodata:

```sh
docker compose -f compose.yaml -f compose.dev.yaml up -d --build --wait
docker compose -f compose.yaml -f compose.dev.yaml exec api opencde seed
```

Den første kommandoen tar noen minutter første gang og er ferdig når serveren kjører.
Den andre oppretter demobrukere og prosjekter og skriver ut passordene deres **én
gang**: ta vare på passordene til `admin` og `inspection_manager` nå. La linjene som
begynner med `client`, være; Dataspatium registrerer sin egen klient.

Kontroller at det virker: <http://localhost:8000/readyz> svarer `"status":"ready"`.
Logg inn på <http://localhost:8000/signin> som `admin`, og åpne
<http://localhost:8000/admin/projects>, som viser *Building permit* og
*Demolition permit*.

Når du senere endrer `.env`, kjører du `up`-kommandoen igjen. `docker compose restart`
leser ikke filen.

## 2. Start Dataspatium

1. Last ned `dataspatium-<version>.zip` fra
   [siste utgivelse](https://github.com/marwiss/Dataspatium/releases/latest),
   og sammenlign SHA-256-summen med den i utgivelsesteksten (`Get-FileHash` i
   PowerShell, `shasum -a 256` på macOS og Linux).
2. Pakk ut ZIP-filen i din egen mappe. Windows kan opprette en mappe i mappen; det som
   teller, er mappen der `index.html` ligger direkte.
3. Åpne en terminal i den mappen, og start en webserver på port 8080:

   ```sh
   python -m http.server 8080 --bind 127.0.0.1
   ```

   Kommandoen kan hete `python3` på macOS og Linux og `py` på Windows. La terminalen
   være åpen mens du bruker appen. Oppgi alltid porten: uten den tar Python 8000, som
   er Kontrolls port, og appen legger da igjen en service worker i nettleseren din som
   ødelegger Kontrolls sider (se [Feilsøking](#feilsøking)).
4. Åpne <http://localhost:8080/>. Ikke dobbeltklikk på `index.html`: åpnet fra mappen
   kan ikke appen registrere seg selv. Appen laster seg selv på nytt én gang ved
   første start.
5. Første start spør om språk: velg ett, og trykk *Fortsett på …*. Denne siden bruker
   de norske navnene. Panelet *Velkommen til Dataspatium* tilbyr et kurs: trykk
   *Ikke nå*.

## 3. Logg inn i Kontroll fra Dataspatium

1. Velg modusen *Hent*. I venstre kolonne, under *Legg til kilder*, velger du
   *OpenCDE*.
2. Under *Adresse* skriver du `http://localhost:8000`. **La *Klient-id* og
   hemmeligheten stå tomme**: appen registrerer seg selv, selv om teksten i dialogen
   snakker om en klient-id fra administratoren. Trykk *Legg til kilde*.
3. Appen spør *Tillate internettilgang?* opptil tre ganger, én gang per formål. Her
   gjelder det bare din egen server: trykk *Tillat* hver gang.
4. Kilden åpnes og vises under *Tillagte kilder*. Linjen "Serveren: Kontroll OpenCDE
   server <version>. Tillegg: …" kommer fra serverens kapabilitetsdokument og sier
   hvilke tillegg som er slått på. Merket *Krever nøkkel* kan du se bort fra: det som
   kreves, er innloggingen.
5. Trykk *Logg inn*. Et popup-vindu åpnes med serverens innloggingsside. Hvis
   nettleseren blokkerer det, tillat popup-vinduer for `http://localhost:8080`, og
   trykk igjen.
6. Logg inn som `inspection_manager` med passordet fra trinn 1, og trykk *Tillat og
   logg inn*. Ikke bruk `admin`, som ikke er med i noe prosjekt. Vinduet lukker seg
   selv, og kilden sier *Innlogget som Certified inspection manager*.
7. *Building permit* er allerede valgt i listen *Prosjekt*.

Du er innlogget til siden lastes på nytt; trykk da *Logg inn* igjen. Kilden blir
værende.

## 4. Opprett en sak fra 3D-visningen

1. I kildens visning finner du *Filer i prosjektet* og trykker *Vis filer*.
   `opencde seed` la `three_walls_gtin.ifc` der (tre vegger med GTIN 3, 2 og 1). Trykk
   *Hent*: filen blir et modelldatasett.
2. Velg modusen *Bearbeid*; modellen åpnes i 3D. Klikk på en vegg for å markere den.
3. Trykk *Saker* over 3D-visningen og deretter *Ny sak* i høyre kolonne. Skriv noe
   under *Tittel*, og trykk *Opprett sak*. Saken opprettes gjennom BCF-API-et, og
   visningen og den markerte veggen følger med som viewpoint.
4. Under saken skriver du noe i *Skriv en kommentar* og trykker *Send*.

## 5. Se det på serveren

Innlogget som `admin` åpner du <http://localhost:8000/admin>:

- *Prosjekter* viser *Building permit* med to saker (den fra `opencde seed` og din) og
  ett dokument.
- *Revisjonslogg* viser innloggingen og appens registrering.
- *Forespørselslogg* viser hvert kall appen gjorde, med de samme
  `X-Request-ID`-verdiene som kortet *Logg* nederst i kildens visning i *Hent*, slik
  at et mislykket kall kan finnes på begge sider.

Trykk deretter *Logg ut* øverst på serverens side, fordi opplastingen nedenfor gjøres
som en annen bruker.

Grafen bygges av opplastede modeller, ikke av den fra `opencde seed`. For å se den
sender du modellen til serveren:

1. I Dataspatium velger du modusen *Del* og fanen *Til CDE*. Under *Hva* velger du
   *Originalfilen* og trykker *Send*.
2. *Gjennomgang før deling* viser hva som følger med: trykk *Fortsett*.
3. Serverens opplastingsside åpnes i et popup-vindu. Logg inn som `inspection_manager`,
   og trykk *Lagre og fortsett*. Vinduet lukker seg selv.

I løpet av noen sekunder svarer Neo4j Browser på <http://localhost:7484> (koble til
`bolt://localhost:7697` som `neo4j` med passordet fra `.env`) på denne spørringen med
veggen koblet til viewpointets komponent:

```cypher
MATCH (c:Component)-[:SAME_AS]->(w:IfcWall) RETURN c, w
```

## Feilsøking

Hver rad siterer skjermen slik den ser ut med de norske navnene.

| Dette ser du | Hvorfor | Gjør slik |
|---|---|---|
| `Cannot connect to the Docker daemon`, `error during connect` eller `docker: command not found` | Docker kjører ikke | Start Docker Desktop, vent til det sier at det kjører, og kjør kommandoen igjen |
| `dependency failed to start: container kontroll-graph-1 is unhealthy` | Et passord på færre enn 16 tegn, som Neo4j avviser (`docker compose -f compose.yaml -f compose.dev.yaml logs graph` sier `A password must be at least 16 characters`), eller et databasevolum igjen fra en tidligere installasjon med et annet passord | Rett passordet, og kjør `up`-kommandoen igjen. For det gamle volumet, se [Start på nytt](#start-på-nytt) |
| `port is already allocated`, `Ports are not available` eller `address already in use` | Et annet program har 8000, 7484 eller 7697, kanskje en tidligere Kontroll (`docker ps` viser det) | Stopp det, eller oppgi andre porter med `OPENCDE_DEV_PORT`, `OPENCDE_DEV_NEO4J_HTTP_PORT` og `OPENCDE_DEV_NEO4J_BOLT_PORT` i `.env`, og bruk din port i stedet for 8000 fra da av |
| Containerne fra en annen mappe erstattes | To utsjekkinger på én maskin deler Compose-prosjektnavnet `kontroll` | Gi den andre `COMPOSE_PROJECT_NAME=kontroll-2` og andre `OPENCDE_DEV_*`-porter i dens `.env` |
| `the database is not empty` | `opencde seed` har allerede kjørt og skrev ut passordene da | Få et nytt passord med `docker compose -f compose.yaml -f compose.dev.yaml exec api opencde user set-password inspection_manager`, eller [start på nytt](#start-på-nytt) |
| `python` finnes ikke, eller Microsoft Store åpnes | Kommandoen heter noe annet på denne maskinen | Bruk `py` eller `python3` |
| En filliste i stedet for appen | Webserveren kjører i den ytre mappen | Stopp den med Ctrl+C, og start den i mappen der `index.html` ligger |
| En gammel versjon av appen, eller noe helt annet | Noe annet svarer på port 8080; på Windows kan en andre webserver starte på samme port uten feil | Bruk en annen port, `python -m http.server 8090 --bind 127.0.0.1`, og åpne `http://localhost:8090/` |
| *Appen kan registrere seg selv hos serveren bare når den kjører fra en webserver …* | Appen ble åpnet fra mappen | Åpne `http://localhost:8080/` |
| *Kunne ikke nå localhost:8000 …* | Kontroll kjører ikke, eller adressen er feilskrevet | <http://localhost:8000/readyz> må svare. Adressen er `http://localhost:8000` uten noe etter |
| *Serveren tillater ikke at appen registrerer seg selv …* | `OPENCDE_DYNAMIC_CLIENT_REGISTRATION` er ikke `true` | Endre `.env`, kjør `up`-kommandoen igjen, og trykk *Legg til kilde* igjen |
| *Registreringen mislyktes:* … `http redirect URIs are only allowed for the loopback address` | `OPENCDE_ALLOW_LOCALHOST_REDIRECTS` er ikke `true` | Endre `.env`, kjør `up`-kommandoen igjen, og trykk *Legg til kilde* igjen |
| *Registreringen mislyktes:* … `rate_limited` | Flere enn fem registreringer innen en time; hver *Legg til kilde* med tom *Klient-id* er én | `docker compose -f compose.yaml -f compose.dev.yaml restart api` nullstiller telleren |
| *Internettilgang for … er ikke tillatt.* | Det ble trykket *Avslå* | Tillat det under *Håndter*, *Arbeidsområde*, *Internettilgang*, og prøv igjen |
| *Nettleseren blokkerte innloggingsvinduet …* | Nettleserens blokkering av popup-vinduer | Tillat popup-vinduer for `http://localhost:8080`, og trykk *Logg inn* igjen |
| I popup-vinduet: *Kan ikke fortsette* og *Ukjent klient.* | Serveren har glemt appens registrering, som regel etter `down -v` | Lukk vinduet, og last appen på nytt, fordi *Logg inn* ellers spinner i fem minutter. Slett kilden med krysset ved siden av den under *Tillagte kilder*, og legg den til igjen |
| I popup-vinduet: *Kan ikke fortsette* og *Redirect-URI-en er ikke registrert for denne klienten.* | *Klient-id* ble fylt ut, for eksempel fra utskriften av `opencde seed` | Lukk vinduet, og last appen på nytt. Slett kilden med krysset ved siden av den under *Tillagte kilder*, og legg den til igjen med tom *Klient-id* |
| I popup-vinduet: *Brukernavnet eller passordet er ikke riktig.* | Hver bruker har sitt eget passord fra `opencde seed` | Bruk det riktige, eller få et nytt som ovenfor |
| *Skjemaet er utløpt. Prøv igjen.* på `/signin`, eller i popup-vinduet *Kan ikke fortsette* og *Innloggingsskjemaet er utløpt eller er endret. Start på nytt.*, selv om du nettopp åpnet siden. `docker compose -f compose.yaml -f compose.dev.yaml logs api` viser `GET /sw.js` med 404 | En service worker i nettleseren din fra en annen webapp som en gang har kjørt på `http://localhost:8000`, for eksempel startet med `python -m http.server` uten port. Den svarer med gamle kopier av Kontrolls sider | Fjern den: `about:debugging#/runtime/this-firefox` i Firefox, `edge://serviceworker-internals` i Edge, `chrome://serviceworker-internals` i Chrome; finn `localhost:8000`, og velg *Unregister*. Hver nettleser har sin egen, også en som er innebygd i en editor. Et privat vindu har ingen, noe som raskt viser om dette er årsaken. Hold andre apper borte fra port 8000 |
| *Du er ikke medlem i noe prosjekt på serveren.* | Du logget inn som `admin`, som ikke er med i noe prosjekt | Trykk *Logg ut* og deretter *Logg inn* som `inspection_manager` |
| *Logg inn* fortsetter å spinne | Vinduet ble lukket før innloggingen var ferdig | Last siden på nytt |
| Vinduet sier *Kopiera adressen … / Copy the address …* | Det kunne ikke nå appens vindu, som kanskje ble lukket eller lastet på nytt imens | Lukk vinduet, og trykk *Logg inn* igjen |
| *En annen konto* på opplastingssiden | Nettleseren er logget inn på serveren som `admin`, som ikke startet opplastingen | Trykk *Logg ut* på den siden, og lukk vinduet. Last appen på nytt, fordi *Send* ellers forblir opptatt, trykk *Logg inn* i kildens visning, velg modellen i venstre kolonne i *Del*, og send igjen |

## Start på nytt

I mappen du startet fra (eller hvor som helst, med `-p kontroll` i stedet for de to
`-f`-flaggene):

```sh
docker compose -f compose.yaml -f compose.dev.yaml down -v
```

Det sletter databasen og demoens filer. Kjør deretter `up`- og `seed`-kommandoene i
trinn 1 igjen, noe som gir nye passord. I Dataspatium sletter du kilden med krysset ved
siden av den under *Tillagte kilder* og legger den til igjen, fordi serveren har glemt
appens registrering.

For å stoppe uten å slette noe utelater du `-v`, og webserveren stopper du med Ctrl+C.

## Neste steg

- [docs/client-guide.md](client-guide.md) om API-ene,
  kapabilitetsdokumentet og feilkodene.
- [docs/acceptance.md](../acceptance.md) om sjekklistene paret testes med, og
  [docs/dataspatium-coordination.md](../dataspatium-coordination.md) om hva de
  to prosjektene samordner.
- [docs/deploy/](deploy/) når serveren skal kjøre for andre.
