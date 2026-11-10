# Hurtig start: Dataregium og Dataspatium sammen

Fra en tom computer til logget ind i Dataregium fra Dataspatium, med en sag oprettet
i en 3D-visning og synlig i serverens logge. Det tager omkring tyve minutter, mest
det første byg. Følg trinene i rækkefølge, og brug adresser og porte præcis som de
står: næsten alle problemer skyldes en oversprunget indstilling eller en anden
adresse. [Fejlfinding](#fejlfinding) siger, hvad du gør, hvis noget går galt. Den
samme side findes i Dataspatiums repo; de to holdes identiske.

## Det skal du bruge

- Docker: Docker Desktop på Windows og macOS, Docker Engine med compose-tilføjelsen
  på Linux. Det skal køre: `docker version` svarer for både klient og server.
- Git, eller kildekode-ZIP'en fra Dataregiums
  [seneste udgivelse](https://github.com/marwiss/Dataregium/releases/latest) i stedet
  for `git clone` nedenfor.
- Python 3, som en lille lokal webserver.
- Microsoft Edge, Google Chrome eller Firefox.
- Portene 8000, 7484, 7697 og 8080 ledige på computeren.

Har du prøvet Dataregium på denne computer før, så begynd med
[Start forfra](#start-forfra).

## 1. Start Dataregium

```sh
git clone https://github.com/marwiss/Dataregium.git
cd Dataregium
cp .env.example .env
```

I Windows' kommandoprompt bruges `copy` i stedet for `cp`.

Åbn `.env` i en teksteditor. De fire linjer nedenfor findes allerede i filen: ret dem,
så de ser sådan ud, og gem. Vælg dit eget kodeord, mindst 16 tegn, kun bogstaver og
tal.

```ini
OPENCDE_GRAPH_PASSWORD=YourOwnPassword1234
OPENCDE_DYNAMIC_CLIENT_REGISTRATION=true
OPENCDE_REQUEST_LOG_ENABLED=true
OPENCDE_IFC_LPG_ENABLED=true
```

| Linje | Hvad den gør | Uden den |
|---|---|---|
| `OPENCDE_GRAPH_PASSWORD` | Kodeordet til grafdatabasen | Kortere end 16 tegn: databasen starter ikke |
| `OPENCDE_DYNAMIC_CLIENT_REGISTRATION` | Lader Dataspatium registrere sig selv hos serveren | Trin 3 stopper, og appen beder om et klient-id |
| `OPENCDE_REQUEST_LOG_ENABLED` | Gemmer appens kald | Forespørgselsloggen i trin 5 forbliver tom |
| `OPENCDE_IFC_LPG_ENABLED` | Gør uploadede modeller til en graf | Ingen graf i trin 5 |

Indstillingerne er til at prøve Dataregium på din egen computer, ikke til en server,
som andre bruger.

Start serveren og indlæs demodata:

```sh
docker compose up -d --build --wait
docker compose exec api opencde seed
```

Den første kommando tager et par minutter første gang og er færdig, når serveren
kører. Den anden opretter demobrugere og projekter og udskriver deres kodeord **én
gang**: gem kodeordene til `admin` og `inspection_manager` nu. Lad linjerne, der
begynder med `client`, være; Dataspatium registrerer sin egen klient.

Kontrollér, at det virker: <http://127.0.0.1:8000/readyz> svarer
`"status":"ready"`. Log ind på <http://127.0.0.1:8000/signin> som `admin`, og åbn
<http://127.0.0.1:8000/admin/projects>, som viser *Building permit* og
*Demolition permit*.

Når du senere ændrer `.env`, kører du `up`-kommandoen igen. `docker compose restart`
læser ikke filen.

## 2. Start Dataspatium

1. Hent `dataspatium-<version>.zip` fra
   [seneste udgivelse](https://github.com/marwiss/Dataspatium/releases/latest),
   og sammenlign dens SHA-256 med den i udgivelsens tekst (`Get-FileHash` i
   PowerShell, `shasum -a 256` på macOS og Linux).
2. Pak ZIP-filen ud i din egen mappe. Windows kan oprette en mappe i mappen; det, der
   tæller, er den mappe, hvor `index.html` ligger direkte.
3. Åbn en terminal i den mappe, og start en webserver på port 8080:

   ```sh
   python -m http.server 8080 --bind 127.0.0.1
   ```

   Kommandoen kan hedde `python3` på macOS og Linux og `py` på Windows. Lad terminalen
   være åben, mens du bruger appen. Angiv altid porten: uden den tager Python 8000, som er Dataregiums port.
4. Åbn <http://127.0.0.1:8080/>, skrevet præcis sådan: serveren sender browseren tilbage efter login til `127.0.0.1`, ikke til `localhost`. Dobbeltklik ikke på `index.html`: åbnet fra mappen
   kan appen ikke registrere sig selv. Appen genindlæser sig selv én gang ved første
   start.
5. Første start spørger om sprog: vælg et, og tryk *Fortsæt på …*. Denne side bruger
   de danske navne. Panelet *Velkommen til Dataspatium* tilbyder et kursus: tryk
   *Ikke nu*.

## 3. Log ind i Dataregium fra Dataspatium

1. Vælg tilstanden *Hent*. I venstre kolonne, under *Tilføj kilder*, vælger du
   *OpenCDE*.
2. Under *Adresse* skriver du `http://127.0.0.1:8000`. **Lad *Klient-id* og
   hemmeligheden være tomme**: appen registrerer sig selv, selv om teksten i dialogen
   taler om et klient-id fra administratoren. Tryk *Tilføj kilde*.
3. Appen spørger *Tillad internetadgang?* op til tre gange, én gang per formål. Her
   gælder det kun din egen server: tryk *Tillad* hver gang.
4. Kilden åbnes og vises under *Tilføjede kilder*. Linjen "Serveren: Dataregium OpenCDE
   server <version>. Tilføjelser: …" kommer fra serverens kapabilitetsdokument og
   siger, hvilke tilføjelser der er slået til. Mærket *Kræver nøgle* kan du se bort
   fra: det, der kræves, er login.
5. Tryk *Log ind*. Et pop op-vindue åbnes med serverens login-side. Hvis browseren
   blokerer det, så tillad pop op-vinduer for `http://127.0.0.1:8080`, og tryk igen.
6. Log ind som `inspection_manager` med kodeordet fra trin 1, og tryk *Tillad og log
   ind*. Brug ikke `admin`, som ikke er med i noget projekt. Vinduet lukker sig selv,
   og kilden siger *Logget ind som Certified inspection manager*.
7. *Building permit* er allerede valgt i listen *Projekt*.

Du er logget ind, indtil siden genindlæses; tryk da *Log ind* igen. Kilden bliver.

## 4. Opret en sag fra 3D-visningen

1. I kildens visning skal du finde *Filer i projektet* og trykke *Vis filer*.
   `opencde seed` lagde `three_walls_gtin.ifc` der (tre vægge med GTIN 3, 2 og 1).
   Tryk *Hent*: filen bliver et modeldatasæt.
2. Vælg tilstanden *Bearbejd*; modellen åbnes i 3D. Klik på en væg for at markere den.
3. Tryk *Sager* over 3D-visningen og derefter *Ny sag* i højre kolonne. Skriv noget
   under *Overskrift*, og tryk *Opret sag*. Sagen oprettes gennem BCF API'et, og visningen
   og den markerede væg følger med som viewpoint.
4. Under sagen skriver du noget i *Skriv en kommentar* og trykker *Send*.

## 5. Se det på serveren

Logget ind som `admin` åbner du <http://127.0.0.1:8000/admin>:

- *Projekter* viser *Building permit* med to sager (den fra `opencde seed` og din) og
  ét dokument.
- *Revisionslog* viser login og appens registrering.
- *Forespørgselslog* viser hvert kald, appen foretog, med de samme `X-Request-ID`-
  værdier som kortet *Log* nederst i kildens visning i *Hent*, så et mislykket kald
  kan findes på begge sider.

Eksempelmodellen er allerede en graf, fordi `OPENCDE_IFC_LPG_ENABLED=true` stod i
`.env`, da du kørte `opencde seed`. Neo4j Browser på <http://127.0.0.1:7484> (forbind
til `bolt://127.0.0.1:7697` som `neo4j` med kodeordet fra `.env`) svarer på denne
forespørgsel med væggen koblet til viewpointets komponent:

```cypher
MATCH (c:Component)-[:SAME_AS]->(w:IfcWall) RETURN c, w
```

En model, du sender fra Dataspatium, bliver en graf på samme måde. For at prøve det
skal du trykke *Log ud* øverst på serverens side, fordi uploadet sker som en anden
bruger:

1. I Dataspatium vælger du tilstanden *Del* og fanen *Til CDE*. Under *Hvad* vælger du
   *Originalfilen* og trykker *Send*.
2. *Gennemgang før deling* viser, hvad der følger med: tryk *Fortsæt*.
3. Serverens upload-side åbnes i et pop op-vindue. Log ind som `inspection_manager`,
   og tryk *Gem og fortsæt*. Vinduet lukker sig selv.

Inden for få sekunder finder den samme forespørgsel også væggen i den nye model.

## Fejlfinding

Hver række citerer skærmen, som den ser ud med de danske navne.

| Det ser du | Hvorfor | Gør sådan |
|---|---|---|
| `Cannot connect to the Docker daemon`, `error during connect` eller `docker: command not found` | Docker kører ikke | Start Docker Desktop, vent til det siger, at det kører, og kør kommandoen igen |
| `dependency failed to start: container dataregium-graph-1 is unhealthy` | Et kodeord på færre end 16 tegn, som Neo4j afviser (`docker compose logs graph` siger `A password must be at least 16 characters`), eller et databasevolumen fra en tidligere installation med et andet kodeord | Ret kodeordet, og kør `up`-kommandoen igen. For det gamle volumen, se [Start forfra](#start-forfra) |
| `port is already allocated`, `Ports are not available` eller `address already in use` | Et andet program har 8000, 7484 eller 7697, måske en tidligere Dataregium (`docker ps` viser det) | Stop det, eller angiv andre porte med `OPENCDE_DEV_PORT`, `OPENCDE_DEV_NEO4J_HTTP_PORT` og `OPENCDE_DEV_NEO4J_BOLT_PORT` i `.env`, og brug din port i stedet for 8000 fra da af |
| Containerne fra en anden mappe erstattes | To checkouts på én computer deler Compose-projektnavnet `dataregium` | Giv den anden `COMPOSE_PROJECT_NAME=dataregium-2` og andre `OPENCDE_DEV_*`-porte i dens `.env` |
| `the database is not empty` | `opencde seed` har allerede kørt og udskrev kodeordene dengang | Få et nyt kodeord med `docker compose exec api opencde user set-password inspection_manager`, eller [start forfra](#start-forfra) |
| `python` findes ikke, eller Microsoft Store åbnes | Kommandoen hedder noget andet på denne computer | Brug `py` eller `python3` |
| En filliste i stedet for appen | Webserveren kører i den ydre mappe | Stop den med Ctrl+C, og start den i den mappe, hvor `index.html` ligger |
| En gammel version af appen, eller noget helt andet | Noget andet svarer på port 8080; på Windows kan en anden webserver starte på samme port uden fejl | Brug en anden port, `python -m http.server 8090 --bind 127.0.0.1`, og åbn `http://127.0.0.1:8090/` |
| *Appen kan kun registrere sig selv hos serveren, når den kører fra en webserver …* | Appen blev åbnet fra mappen | Åbn `http://127.0.0.1:8080/` |
| *Kunne ikke nå 127.0.0.1:8000 …* | Dataregium kører ikke, eller adressen er skrevet forkert | <http://127.0.0.1:8000/readyz> skal svare. Adressen er `http://127.0.0.1:8000` uden noget efter |
| *Serveren tillader ikke, at appen registrerer sig selv …* | `OPENCDE_DYNAMIC_CLIENT_REGISTRATION` er ikke `true` | Ret `.env`, kør `up`-kommandoen igen, og tryk *Tilføj kilde* igen |
| *Registreringen mislykkedes:* … `Redirect URIs to http://localhost are not allowed here` | Appen blev åbnet på `localhost`, som serveren ikke godtager som vej tilbage | Åbn `http://127.0.0.1:8080/`, og tilføj kilden der |
| *Registreringen mislykkedes:* … `rate_limited` | Flere end 60 registreringer inden for en time; hver *Tilføj kilde* med tomt *Klient-id* er én | `docker compose restart api` nulstiller tælleren |
| *Internetadgang til … er ikke tilladt.* | Der blev trykket *Afvis* | Tillad det under *Håndter*, *Arbejdsområde*, *Internetadgang*, og prøv igen |
| *Browseren blokerede loginvinduet …* | Browserens blokering af pop op-vinduer | Tillad pop op-vinduer for `http://127.0.0.1:8080`, og tryk *Log ind* igen |
| I pop op-vinduet: *Kan ikke fortsætte* og *Ukendt klient.* | Serveren har glemt appens registrering, som regel efter `down -v` | Luk vinduet, og genindlæs appen, fordi *Log ind* ellers snurrer i fem minutter. Slet kilden med krydset ved siden af den under *Tilføjede kilder*, og tilføj den igen |
| I pop op-vinduet: *Kan ikke fortsætte* og *Redirect-URI'en er ikke registreret for denne klient.* | *Klient-id* blev udfyldt, for eksempel fra udskriften af `opencde seed` | Luk vinduet, og genindlæs appen. Slet kilden med krydset ved siden af den under *Tilføjede kilder*, og tilføj den igen med tomt *Klient-id* |
| I pop op-vinduet: *Brugernavnet eller kodeordet er ikke korrekt.* | Hver bruger har sit eget kodeord fra `opencde seed` | Brug det rigtige, eller få et nyt som ovenfor |
| *For mange mislykkede forsøg for dette brugernavn …* | Fem forkerte kodeord i træk får serveren til at vente, højst 15 minutter | Vent så længe, som der står, og brug kodeordet fra `opencde seed` |
| *Formularen er udløbet. Prøv igen.* på `/signin`, eller i pop op-vinduet *Kan ikke fortsætte* og *Login-formularen er udløbet eller er blevet manipuleret. Start forfra.*, selv om du lige har åbnet siden. `docker compose logs api` viser `foreign_service_worker_removed` | En service worker i din browser fra en anden webapp, der engang har kørt på `http://127.0.0.1:8000`, for eksempel startet med `python -m http.server` uden port. Den svarer med gamle kopier af Dataregiums sider | Vent et par sekunder, til siden selv er genindlæst, og prøv igen, fordi Dataregium fjerner en sådan worker. Hvis meddelelsen bliver, så fjern den i hånden: `about:debugging#/runtime/this-firefox` i Firefox, `edge://serviceworker-internals` i Edge, `chrome://serviceworker-internals` i Chrome; find `127.0.0.1:8000`, og vælg *Unregister*. Hver browser har sin egen, også en, der er indbygget i en editor. Et privat vindue har ingen, hvilket hurtigt viser, om dette er årsagen. Hold andre apps væk fra port 8000 |
| *Du er ikke medlem af noget projekt på serveren.* | Du loggede ind som `admin`, som ikke er med i noget projekt | Tryk *Log ud* og derefter *Log ind* som `inspection_manager` |
| *Log ind* bliver ved med at snurre | Vinduet blev lukket, før login var færdigt | Genindlæs siden |
| Vinduet siger *Kopiera adressen … / Copy the address …* | Det kunne ikke nå appens vindue, som måske blev lukket eller genindlæst imens | Luk vinduet, og tryk *Log ind* igen |
| *En anden konto* på upload-siden | Browseren er logget ind på serveren som `admin`, som ikke startede uploadet | Tryk *Log ud* på den side, og log ind som `inspection_manager`; uploadet fortsætter så i samme vindue |

## Start forfra

I den mappe, du startede fra (eller hvor som helst, med `-p dataregium`):

```sh
docker compose down -v
```

Det sletter databasen og demoens filer. Kør derefter `up`- og `seed`-kommandoerne i
trin 1 igen, hvilket giver nye kodeord. I Dataspatium sletter du kilden med krydset ved
siden af den under *Tilføjede kilder* og tilføjer den igen, fordi serveren har glemt
appens registrering.

For at stoppe uden at slette noget udelader du `-v`, og webserveren stopper du med
Ctrl+C.

## Næste skridt

- [docs/da/client-guide.md](client-guide.md) om API'erne,
  kapabilitetsdokumentet og fejlkoderne.
- [docs/acceptance.md](../acceptance.md) om tjeklisterne, parret testes med,
  og [docs/dataspatium-coordination.md](../dataspatium-coordination.md) om,
  hvad de to projekter samordner.
- [docs/da/deploy/](deploy/), når serveren skal køre for andre.
