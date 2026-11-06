# Snabbstart: Kontroll och Dataspatium tillsammans

Från en tom dator till inloggad i Kontroll från Dataspatium, med ett ärende skapat
i en 3D-vy och synligt i serverns loggar. Det tar ungefär tjugo minuter, det mesta
är det första bygget. Följ stegen i ordning och använd adresser och portar precis
som de står: nästan alla problem kommer av en överhoppad inställning eller en annan
adress. [Felsökning](#felsökning) säger vad du gör om något går fel. Samma sida
finns i Dataspatiums repo; de två hålls identiska.

## Det här behöver du

- Docker: Docker Desktop på Windows och macOS, Docker Engine med
  compose-tillägget på Linux. Det måste vara igång: `docker version` svarar för både
  klient och server.
- Git, eller källkods-ZIP:en från Kontrolls
  [senaste utgåva](https://github.com/marwiss/Kontroll/releases/latest) i stället för
  `git clone` nedan.
- Python 3, som en liten lokal webbserver.
- Microsoft Edge, Google Chrome eller Firefox.
- Portarna 8000, 7484, 7697 och 8080 lediga på datorn.

Har du provat Kontroll på den här datorn förut, börja med
[Börja om](#börja-om).

## 1. Starta Kontroll

```sh
git clone https://github.com/marwiss/Kontroll.git
cd Kontroll
cp .env.example .env
```

I Windows kommandotolk används `copy` i stället för `cp`.

Öppna `.env` i en textredigerare. De fyra raderna nedan finns redan i filen: ändra
dem så att de ser ut så här, och spara. Välj ett eget lösenord, minst 16 tecken,
bara bokstäver och siffror.

```ini
OPENCDE_GRAPH_PASSWORD=YourOwnPassword1234
OPENCDE_DYNAMIC_CLIENT_REGISTRATION=true
OPENCDE_REQUEST_LOG_ENABLED=true
OPENCDE_IFCGRAPH_ENABLED=true
```

| Rad | Vad den gör | Utan den |
|---|---|---|
| `OPENCDE_GRAPH_PASSWORD` | Lösenordet till grafdatabasen | Kortare än 16 tecken: databasen startar inte |
| `OPENCDE_DYNAMIC_CLIENT_REGISTRATION` | Låter Dataspatium registrera sig själv hos servern | Steg 3 stannar, och appen frågar efter ett klient-id |
| `OPENCDE_REQUEST_LOG_ENABLED` | Sparar appens anrop | Begärandeloggen i steg 5 förblir tom |
| `OPENCDE_IFCGRAPH_ENABLED` | Gör uppladdade modeller till en graf | Ingen graf i steg 5 |

Inställningarna är till för att prova Kontroll på din egen dator, inte för en
server som andra använder.

Starta servern och lägg in demodata:

```sh
docker compose -f compose.yaml -f compose.dev.yaml up -d --build --wait
docker compose -f compose.yaml -f compose.dev.yaml exec api opencde seed
```

Det första kommandot tar några minuter första gången och är klart när servern kör.
Det andra skapar demoanvändare och projekt och skriver ut deras lösenord **en
gång**: spara lösenorden för `admin` och `inspection_manager` nu. Bry dig inte om
raderna som börjar med `client`; Dataspatium registrerar en egen klient.

Kontrollera att det fungerar: <http://127.0.0.1:8000/readyz> svarar
`"status":"ready"`. Logga in på <http://127.0.0.1:8000/signin> som `admin` och öppna
<http://127.0.0.1:8000/admin/projects>, som listar *Building permit* och
*Demolition permit*.

När du ändrar `.env` senare kör du `up`-kommandot igen. `docker compose restart`
läser inte filen.

## 2. Starta Dataspatium

1. Ladda ned `dataspatium-<version>.zip` från
   [senaste utgåvan](https://github.com/marwiss/Dataspatium/releases/latest)
   och jämför dess SHA-256 med den i utgåvans text (`Get-FileHash` i PowerShell,
   `shasum -a 256` på macOS och Linux).
2. Packa upp ZIP-filen i en egen mapp. Windows kan skapa en mapp i mappen; det som
   räknas är mappen där `index.html` ligger direkt.
3. Öppna en terminal i den mappen och starta en webbserver på port 8080:

   ```sh
   python -m http.server 8080 --bind 127.0.0.1
   ```

   Kommandot kan heta `python3` på macOS och Linux och `py` på Windows. Låt
   terminalen vara öppen medan du använder appen. Ange alltid porten: utan den tar Python 8000, som är Kontrolls port.
4. Öppna <http://127.0.0.1:8080/>, skrivet precis så: servern skickar tillbaka webbläsaren efter inloggningen till `127.0.0.1`, inte till `localhost`. Dubbelklicka inte på `index.html`: öppnad från
   mappen kan appen inte registrera sig själv. Appen laddar om sig en gång vid
   första starten.
5. Första starten frågar efter språk: välj ett och tryck *Fortsätt på …*. Den här
   sidan använder de svenska namnen. Panelen *Välkommen till Dataspatium* erbjuder en
   kurs: tryck *Inte nu*.

## 3. Logga in i Kontroll från Dataspatium

1. Välj läget *Inhämta*. I vänsterkolumnen, under *Lägg till källor*, väljer du
   *OpenCDE*.
2. Under *Adress* skriver du `http://127.0.0.1:8000`. **Lämna *Klient-id* och
   hemligheten tomma**: appen registrerar sig själv, även om texten i dialogen talar
   om ett klient-id från administratören. Tryck *Lägg till källa*.
3. Appen frågar *Tillåta internetåtkomst?* upp till tre gånger, en gång per ändamål.
   Här gäller det bara din egen server: tryck *Tillåt* varje gång.
4. Källan öppnas och listas under *Tillagda källor*. Raden "Servern: Kontroll
   OpenCDE server <version>. Tillägg: …" kommer från serverns kapabilitetsdokument
   och säger vilka tillägg som är påslagna. Märket *Kräver nyckel* kan du bortse
   från: det som krävs är inloggningen.
5. Tryck *Logga in*. Ett popup-fönster öppnas med serverns inloggningssida. Om
   webbläsaren blockerar det, tillåt popup-fönster för `http://127.0.0.1:8080` och
   tryck igen.
6. Logga in som `inspection_manager` med lösenordet från steg 1 och tryck *Tillåt
   och logga in*. Använd inte `admin`, som inte är med i något projekt. Fönstret
   stänger sig självt, och källan säger *Inloggad som Certified inspection manager*.
7. *Building permit* är redan valt i listan *Projekt*.

Du är inloggad tills sidan laddas om; tryck då *Logga in* igen. Källan finns kvar.

## 4. Skapa ett ärende från 3D-vyn

1. I källans vy, leta upp *Filer i projektet* och tryck *Visa filer*. `opencde seed`
   lade `three_walls_gtin.ifc` där (tre väggar med GTIN 3, 2 och 1). Tryck *Hämta*:
   filen blir en modelldatamängd.
2. Välj läget *Bearbeta*; modellen öppnas i 3D. Klicka på en vägg för att markera
   den.
3. Tryck *Ärenden* ovanför 3D-vyn och sedan *Nytt ärende* i högerkolumnen. Skriv
   något under *Rubrik* och tryck *Skapa ärende*. Ärendet skapas genom BCF API:t, och
   vyn och den markerade väggen följer med som viewpoint.
4. Under ärendet, skriv något i *Skriv en kommentar* och tryck *Skicka*.

## 5. Se det på servern

Inloggad som `admin`, öppna <http://127.0.0.1:8000/admin>:

- *Projekt* visar *Building permit* med två ärenden (det från `opencde seed` och
  ditt) och ett dokument.
- *Revisionslogg* listar inloggningen och appens registrering.
- *Begärandelogg* visar varje anrop appen gjorde, med samma `X-Request-ID`-värden
  som kortet *Logg* längst ned i källans vy i *Inhämta*, så att ett misslyckat anrop
  kan hittas på båda sidor.

Exempelmodellen är redan en graf, eftersom `OPENCDE_IFCGRAPH_ENABLED=true` fanns i
`.env` när du körde `opencde seed`. Neo4j Browser på <http://127.0.0.1:7484> (anslut
till `bolt://127.0.0.1:7697` som `neo4j` med lösenordet från `.env`) svarar på den här
frågan med väggen kopplad till viewpointens komponent:

```cypher
MATCH (c:Component)-[:SAME_AS]->(w:IfcWall) RETURN c, w
```

En modell som du skickar från Dataspatium blir en graf på samma sätt. För att prova,
tryck *Logga ut* högst upp på serverns sida, eftersom uppladdningen görs som en annan
användare:

1. I Dataspatium, välj läget *Dela* och fliken *Till CDE*. Under *Vad* väljer du
   *Originalfilen*, och trycker *Skicka*.
2. *Granskning före delning* listar vad som följer med: tryck *Fortsätt*.
3. Serverns uppladdningssida öppnas i ett popup-fönster. Logga in som
   `inspection_manager` och tryck *Spara och fortsätt*. Fönstret stänger sig självt.

Inom några sekunder hittar samma fråga väggen i den nya modellen också.

## Felsökning

Varje rad citerar skärmen som den ser ut med de svenska namnen.

| Det här ser du | Varför | Gör så här |
|---|---|---|
| `Cannot connect to the Docker daemon`, `error during connect` eller `docker: command not found` | Docker är inte igång | Starta Docker Desktop, vänta tills det säger att det kör, och kör kommandot igen |
| `dependency failed to start: container kontroll-graph-1 is unhealthy` | Ett lösenord på färre än 16 tecken, som Neo4j vägrar (`docker compose -f compose.yaml -f compose.dev.yaml logs graph` säger `A password must be at least 16 characters`), eller en databasvolym kvar från en tidigare installation med ett annat lösenord | Rätta lösenordet och kör `up`-kommandot igen. För den gamla volymen, se [Börja om](#börja-om) |
| `port is already allocated`, `Ports are not available` eller `address already in use` | Ett annat program har 8000, 7484 eller 7697, kanske en tidigare Kontroll (`docker ps` visar det) | Stoppa det, eller ange andra portar med `OPENCDE_DEV_PORT`, `OPENCDE_DEV_NEO4J_HTTP_PORT` och `OPENCDE_DEV_NEO4J_BOLT_PORT` i `.env` och använd din port i stället för 8000 från och med då |
| Containrarna från en annan mapp ersätts | Två utcheckningar på en dator delar Compose-projektnamnet `kontroll` | Ge den andra `COMPOSE_PROJECT_NAME=kontroll-2` och andra `OPENCDE_DEV_*`-portar i dess `.env` |
| `the database is not empty` | `opencde seed` har redan körts och skrev ut lösenorden då | Hämta ett nytt lösenord med `docker compose -f compose.yaml -f compose.dev.yaml exec api opencde user set-password inspection_manager`, eller [börja om](#börja-om) |
| `python` hittas inte, eller Microsoft Store öppnas | Kommandot heter något annat på den här datorn | Använd `py` eller `python3` |
| En fillista i stället för appen | Webbservern kör i den yttre mappen | Stoppa den med Ctrl+C och starta den i mappen där `index.html` ligger |
| En gammal version av appen, eller något helt annat | Något annat svarar på port 8080; på Windows kan en andra webbserver starta på samma port utan fel | Använd en annan port, `python -m http.server 8090 --bind 127.0.0.1`, och öppna `http://127.0.0.1:8090/` |
| *Appen kan registrera sig själv hos servern bara när den körs från en webbserver …* | Appen öppnades från mappen | Öppna `http://127.0.0.1:8080/` |
| *Kunde inte nå 127.0.0.1:8000 …* | Kontroll kör inte, eller adressen är felskriven | <http://127.0.0.1:8000/readyz> måste svara. Adressen är `http://127.0.0.1:8000` utan något efter |
| *Servern tillåter inte att appen registrerar sig själv …* | `OPENCDE_DYNAMIC_CLIENT_REGISTRATION` är inte `true` | Ändra `.env`, kör `up`-kommandot igen och tryck *Lägg till källa* igen |
| *Registreringen misslyckades:* … `Redirect URIs to http://localhost are not allowed here` | Appen öppnades på `localhost`, som servern inte godtar som väg tillbaka | Öppna `http://127.0.0.1:8080/` och lägg till källan där |
| *Registreringen misslyckades:* … `rate_limited` | Fler än 60 registreringar inom en timme; varje *Lägg till källa* med tomt *Klient-id* är en | `docker compose -f compose.yaml -f compose.dev.yaml restart api` nollställer räknaren |
| *Internetåtkomst för … är inte tillåten.* | *Neka* trycktes | Tillåt det under *Hantera*, *Arbetsyta*, *Internetåtkomst*, och försök igen |
| *Webbläsaren blockerade inloggningsfönstret …* | Webbläsarens popup-blockering | Tillåt popup-fönster för `http://127.0.0.1:8080` och tryck *Logga in* igen |
| I popup-fönstret: *Kan inte fortsätta* och *Okänd klient.* | Servern har glömt appens registrering, oftast efter `down -v` | Stäng fönstret och ladda om appen, eftersom *Logga in* annars snurrar i fem minuter. Ta bort källan med krysset bredvid den under *Tillagda källor* och lägg till den igen |
| I popup-fönstret: *Kan inte fortsätta* och *Redirect-URI:n är inte registrerad för den här klienten.* | *Klient-id* fylldes i, till exempel från utskriften av `opencde seed` | Stäng fönstret och ladda om appen. Ta bort källan med krysset bredvid den under *Tillagda källor* och lägg till den igen med tomt *Klient-id* |
| I popup-fönstret: *Användarnamnet eller lösenordet är inte korrekt.* | Varje användare har sitt eget lösenord från `opencde seed` | Använd rätt lösenord, eller hämta ett nytt enligt ovan |
| *För många misslyckade försök för det här användarnamnet …* | Fem felaktiga lösenord i rad får servern att vänta, högst 15 minuter | Vänta så länge det står, och använd lösenordet från `opencde seed` |
| *Formuläret har gått ut. Försök igen.* på `/signin`, eller i popup-fönstret *Kan inte fortsätta* och *Inloggningsformuläret har gått ut eller manipulerats. Börja om.*, trots att du nyss öppnade sidan. `docker compose -f compose.yaml -f compose.dev.yaml logs api` visar `foreign_service_worker_removed` | En service worker i din webbläsare från en annan webbapp som en gång kört på `http://127.0.0.1:8000`, till exempel startad med `python -m http.server` utan port. Den svarar med gamla kopior av Kontrolls sidor | Vänta några sekunder tills sidan har laddat om sig själv och försök igen, eftersom Kontroll tar bort en sådan worker. Om meddelandet finns kvar, ta bort den för hand: `about:debugging#/runtime/this-firefox` i Firefox, `edge://serviceworker-internals` i Edge, `chrome://serviceworker-internals` i Chrome; leta upp `127.0.0.1:8000` och välj *Unregister*. Varje webbläsare har sin egen, även en som är inbyggd i en editor. Ett privat fönster har ingen, vilket snabbt visar om det här är orsaken. Håll andra appar borta från port 8000 |
| *Du är inte medlem i något projekt på servern.* | Du loggade in som `admin`, som inte är med i något projekt | Tryck *Logga ut* och sedan *Logga in* som `inspection_manager` |
| *Logga in* snurrar och snurrar | Fönstret stängdes innan inloggningen var klar | Ladda om sidan |
| Fönstret säger *Kopiera adressen … / Copy the address …* | Det kunde inte nå appens fönster, som kanske stängdes eller laddades om under tiden | Stäng fönstret och tryck *Logga in* igen |
| *Ett annat konto* på uppladdningssidan | Webbläsaren är inloggad på servern som `admin`, som inte startade uppladdningen | Tryck *Logga ut* på den sidan och logga in som `inspection_manager`; uppladdningen fortsätter sedan i samma fönster |

## Börja om

I mappen du startade från (eller var som helst, med `-p kontroll` i stället för de
två `-f`-flaggorna):

```sh
docker compose -f compose.yaml -f compose.dev.yaml down -v
```

Det raderar databasen och demons filer. Kör sedan `up`- och `seed`-kommandona i
steg 1 igen, vilket ger nya lösenord. I Dataspatium tar du bort källan med krysset
bredvid den under *Tillagda källor* och lägger till den igen, eftersom servern har
glömt appens registrering.

För att stoppa utan att radera något utelämnar du `-v`, och webbservern stoppar du
med Ctrl+C.

## Nästa steg

- [docs/client-guide.md](client-guide.md) för API:erna,
  kapabilitetsdokumentet och felkoderna.
- [docs/acceptance.md](../acceptance.md) för checklistorna paret testas med,
  och [docs/dataspatium-coordination.md](../dataspatium-coordination.md) för
  vad de två projekten samordnar.
- [docs/deploy/](deploy/) när servern ska köras för andra.
