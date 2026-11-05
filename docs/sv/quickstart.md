# Snabbstart: Kontroll och Dataspatium tillsammans

Tjugo minuter från ingenting till ett ärende skapat i en 3D-vy och synligt i
serverns loggar. Samma sida finns i Dataspatiums repo; de två hålls
identiska. Du behöver Docker (Desktop på Windows/macOS, Engine på Linux),
[uv](https://docs.astral.sh/uv/), Python 3 för en lokal webbserver, och
Microsoft Edge, Google Chrome eller Firefox.

## 1. Starta Kontroll

```sh
git clone https://github.com/marwiss/Kontroll.git
cd Kontroll
cp .env.example .env
```

Öppna `.env` och sätt `OPENCDE_GRAPH_PASSWORD` till valfritt värde på minst
16 tecken, `OPENCDE_DYNAMIC_CLIENT_REGISTRATION=true` så att Dataspatium kan
registrera sig själv, och `OPENCDE_ALLOW_LOCALHOST_REDIRECTS=true` så att en
app som serveras från `http://localhost` får logga in. Sedan:

```sh
docker compose -f compose.yaml -f compose.dev.yaml up -d --build
docker compose -f compose.yaml -f compose.dev.yaml exec api opencde seed
```

Det andra kommandot skapar demoanvändare och projekt och skriver ut deras
lösenord en gång; spara lösenorden för `admin` och `inspection_manager`. Kontrollera
<http://localhost:8000/readyz> (svarar `ready`) och logga in på
<http://localhost:8000/signin> som `admin`: `/admin` visar projekten
*Building permit* och *Demolition permit*.

Om Compose stannar med `dependency failed to start: container kontroll-graph-1
is unhealthy`, läs `docker compose -f compose.yaml -f compose.dev.yaml logs
graph`. Den vanliga orsaken är ett lösenord kortare än 16 tecken, som Neo4j
vägrar (`A password must be at least 16 characters`); den andra är en
databasvolym från en tidigare installation med ett annat lösenord, som
`docker compose -f compose.yaml -f compose.dev.yaml down -v` tar bort
tillsammans med dess data. Två utcheckningar på samma dator delar
Compose-projektnamnet `kontroll`, så den andra behöver
`COMPOSE_PROJECT_NAME=kontroll-2` och andra `OPENCDE_DEV_*`-portar i sin
`.env`.

## 2. Starta Dataspatium

1. Hämta `dataspatium-<version>.zip` från
   [senaste utgåvan](https://github.com/marwiss/Dataspatium/releases/latest)
   och jämför dess SHA-256 med den i utgåvans text.
2. Packa upp ZIP-filen i en egen mapp (inte inuti ZIP-filen).
3. För allt utom OpenCDE-inloggningen räcker det att dubbelklicka på
   `index.html`. För OpenCDE, servera mappen över http, eftersom
   OAuth2-återhoppet behöver en http-adress:

   ```sh
   cd dataspatium-<version>
   python -m http.server 8080
   ```

   och öppna <http://localhost:8080/>. Appen registrerar sig själv hos
   servern som publik klient med `http://localhost:8080/oauth-callback.html`
   som redirect-URI. (Den webbpublicerade appen på
   <https://marwiss.github.io/Dataspatium/> fungerar i stället mot en server
   som tillåter den adressen.)

## 3. Koppla ihop dem

Appen måste vara öppnad via `http://localhost:8080` (steg 2). Öppnad från
mappen kan den inte registrera sig själv, utan då måste ett klient-id från
`/admin/clients` fyllas i.

I Dataspatium: läget *Inhämta* → under *Lägg till källor* valet *OpenCDE* → *Adress*: `http://localhost:8000` →
*Lägg till* (lämna *Klient-id* tomt, så registrerar appen sig själv). Källan öppnas i *Inhämta* och hamnar under
*Tillagda källor*: tryck *Logga in* och logga in som
`inspection_manager` i popup-fönstret, och välj sedan *Building permit* i listan
*Projekt*. Raden under rubriken ("Servern: Kontroll OpenCDE server 2.0.0.
Tillägg: …") kommer ur serverns kapabilitetsdokument och säger vilka tillägg
som är påslagna.

## 4. Skapa ett ärende från 3D-vyn

1. Hämta exempelmodellen. Seeden har redan lagt `three_walls_gtin.ifc` (tre
   väggar med GTIN 3, 2 och 1) som ett dokument i *Building permit*; i
   källans vy i *Inhämta* har dokumentlistan en hämtaknapp per dokument, och
   dokumentet blir en modelldatamängd. Vill du i stället skicka en egen fil,
   använd läget *Dela* → fliken *Till CDE*: välj källa och projekt, *Vad*
   (originalfil, export eller paket), *Hur* (Documents API eller BCF) och
   *Skicka*; hämta sedan tillbaka den på samma sätt.
2. Välj modellen i *Bearbeta*; den öppnas automatiskt i 3D. Markera en vägg,
   öppna panelen *Ärenden* och tryck *Nytt ärende*: ge det en titel, behåll
   statusen och kryssa i *Lägg till vyn som viewpoint*. Ärendet skapas genom
   BCF API med en viewpoint vars komponent pekar på väggen.
3. Skriv en kommentar i samma panel och skicka den.

## 5. Se det på servern

- `/admin/projects` → *Building permit* visar två ärenden (det seedade och
  ditt) och dokumentet.
- `/admin/audit` listar inloggningen och appens registrering.
- Med `OPENCDE_REQUEST_LOG_ENABLED=true` i `.env` (och omstart) visar
  `/admin/requests` varje anrop appen gjorde, med samma `X-Request-ID`-värden
  som kortet *Logg* längst ned i OpenCDE-källans vy i *Inhämta*, så att ett
  misslyckat anrop hittas på båda sidor.
- Med `OPENCDE_IFCGRAPH_ENABLED=true` blir den uppladdade modellen en graf;
  Neo4j Browser på <http://localhost:7484> (`bolt://localhost:7697`,
  användare och lösenord ur `.env`) visar väggen som en `IfcWall`-nod kopplad
  till viewpointens komponent med `SAME_AS`, och Dataspatiums grafvy kan
  fråga den med Cypher.

## Nästa steg

- [docs/client-guide.md](client-guide.md) för API:erna,
  kapabilitetsdokumentet och felkoderna.
- [docs/acceptance.md](../acceptance.md) för checklistorna paret testas med,
  och [docs/dataspatium-coordination.md](../dataspatium-coordination.md) för
  vad de två projekten samordnar.
- [docs/deploy/](../deploy/) när servern ska köras för andra.
