# Hurtig start: Kontroll og Dataspatium sammen

Tyve minutter fra ingenting til en sag oprettet i en 3D-visning og synlig i
serverens logge. Den samme side findes i Dataspatiums repo; de to holdes
identiske. Du skal bruge Docker (Desktop på Windows/macOS, Engine på Linux),
[uv](https://docs.astral.sh/uv/), Python 3 til en lokal webserver og
Microsoft Edge, Google Chrome eller Firefox.

## 1. Start Kontroll

```sh
git clone https://github.com/marwiss/Kontroll.git
cd Kontroll
cp .env.example .env
```

Åbn `.env`, og sæt `OPENCDE_GRAPH_PASSWORD` til en vilkårlig værdi på mindst
16 tegn, `OPENCDE_DYNAMIC_CLIENT_REGISTRATION=true`, så Dataspatium kan
registrere sig selv, og `OPENCDE_ALLOW_LOCALHOST_REDIRECTS=true`, så en app,
der serveres fra `http://localhost`, må logge ind. Derefter:

```sh
docker compose -f compose.yaml -f compose.dev.yaml up -d --build
docker compose -f compose.yaml -f compose.dev.yaml exec api opencde seed
```

Den anden kommando opretter demobrugere og projekter og udskriver deres
kodeord én gang; gem kodeordene til `admin` og `inspection_manager`. Kontrollér
<http://localhost:8000/readyz> (svarer `ready`), og log ind på
<http://localhost:8000/signin> som `admin`: `/admin` viser projekterne
*Building permit* og *Demolition permit*.

Hvis Compose stopper med `dependency failed to start: container
kontroll-graph-1 is unhealthy`, så læs `docker compose -f compose.yaml -f
compose.dev.yaml logs graph`. Den sædvanlige årsag er en adgangskode på under
16 tegn, som Neo4j afviser (`A password must be at least 16 characters`); den
anden er en databasevolume fra en tidligere installation med en anden
adgangskode, som `docker compose -f compose.yaml -f compose.dev.yaml down -v`
fjerner sammen med dens data. To checkouts på samme maskine deler
Compose-projektnavnet `kontroll`, så det andet skal have
`COMPOSE_PROJECT_NAME=kontroll-2` og andre `OPENCDE_DEV_*`-porte i sin `.env`.

## 2. Start Dataspatium

1. Download `dataspatium-<version>.zip` fra
   [seneste udgivelse](https://github.com/marwiss/Dataspatium/releases/latest),
   og sammenlign dens SHA-256 med den i udgivelsesteksten.
2. Pak ZIP-filen ud i en egen mappe (ikke inde i ZIP-filen).
3. Til alt undtagen OpenCDE-login er det nok at dobbeltklikke på
   `index.html`. Til OpenCDE skal mappen serveres over http, fordi
   OAuth2-omdirigeringen kræver en http-adresse:

   ```sh
   cd dataspatium-<version>
   python -m http.server 8080
   ```

   og åbn <http://localhost:8080/>. Appen registrerer sig selv hos serveren
   som offentlig klient med `http://localhost:8080/oauth-callback.html` som
   redirect-URI. (Den hostede app på <https://marwiss.github.io/Dataspatium/>
   virker i stedet mod en server, der tillader den adresse.)

## 3. Forbind de to

I Dataspatium: tilstanden *Inhämta* (Importér) → knappen *Lägg till källa*
(Tilføj kilde) → *Typ av tjänst* (Tjenestetype): *OpenCDE (BCF, Documents)*
→ *Adress* (Adresse): `http://localhost:8000` → *Lägg till* (Tilføj). Kilden
åbnes i *Inhämta*: tryk på *Logga in* (Log ind), og log ind som `inspection_manager` i
popup-vinduet, og vælg derefter *Building permit* i listen *Projekt*. Linjen
under overskriften ("Servern: Kontroll OpenCDE server 2.0.0. Tillägg: …")
kommer fra serverens kapabilitetsdokument og siger, hvilke udvidelser der er
slået til.

## 4. Opret en sag fra 3D-visningen

1. Hent eksempelmodellen. Seedet har allerede lagt `three_walls_gtin.ifc`
   (tre vægge med GTIN 3, 2 og 1) som et dokument i *Building permit*; i
   kildens visning i *Inhämta* har dokumentlisten en hent-knap pr. dokument,
   og dokumentet bliver et modeldatasæt. Vil du i stedet sende din egen fil,
   så brug tilstanden *Dela* (Del) → fanen *Till CDE* (Til CDE): vælg kilde
   og projekt, *Vad* (hvad: originalfil, eksport eller pakke), *Hur*
   (hvordan: Documents API eller BCF) og *Skicka* (Send); hent den derefter
   tilbage på samme måde.
2. Vælg modellen i *Bearbeta* (Bearbejd); den åbnes automatisk i 3D. Markér
   en væg, åbn panelet *Ärenden* (Sager), og tryk på *Nytt ärende* (Ny sag):
   giv den en titel, behold status, og sæt kryds i *Lägg till vyn som
   viewpoint* (Tilføj visningen som viewpoint). Sagen oprettes gennem BCF API
   med et viewpoint, hvis komponent peger på væggen.
3. Skriv en kommentar i samme panel, og send den.

## 5. Se det på serveren

- `/admin/projects` → *Building permit* viser to sager (den seedede og din)
  og dokumentet.
- `/admin/audit` lister login og appens registrering.
- Med `OPENCDE_REQUEST_LOG_ENABLED=true` i `.env` (og genstart) viser
  `/admin/requests` hvert kald, appen foretog, med de samme
  `X-Request-ID`-værdier som kortet *Logg* nederst i OpenCDE-kildens visning
  i *Inhämta*, så et mislykket kald kan findes på begge sider.
- Med `OPENCDE_IFCGRAPH_ENABLED=true` bliver den uploadede model en graf;
  Neo4j Browser på <http://localhost:7484> (`bolt://localhost:7697`, bruger og
  kodeord fra `.env`) viser væggen som en `IfcWall`-knude forbundet til
  viewpointets komponent med `SAME_AS`, og Dataspatiums grafvisning kan
  forespørge den med Cypher.

## Næste skridt

- [docs/client-guide.md](../client-guide.md) om API'erne,
  kapabilitetsdokumentet og fejlkoderne.
- [docs/acceptance.md](../acceptance.md) om tjeklisterne, parret testes med,
  og [docs/dataspatium-coordination.md](../dataspatium-coordination.md) om,
  hvad de to projekter samordner.
- [docs/deploy/](../deploy/), når serveren skal køre for andre.
