# Hurtigstart: Kontroll og Dataspatium sammen

Tjue minutter fra ingenting til en sak opprettet i en 3D-visning og synlig i
serverens logger. Den samme siden finnes i Dataspatiums repo; de to holdes
identiske. Du trenger Docker (Desktop på Windows/macOS, Engine på Linux),
[uv](https://docs.astral.sh/uv/), Python 3 for en lokal webserver og
Microsoft Edge, Google Chrome eller Firefox.

## 1. Start Kontroll

```sh
git clone https://github.com/marwiss/Kontroll.git
cd Kontroll
cp .env.example .env
```

Åpne `.env` og sett `OPENCDE_GRAPH_PASSWORD` til en vilkårlig verdi på minst
16 tegn, `OPENCDE_DYNAMIC_CLIENT_REGISTRATION=true` slik at Dataspatium kan
registrere seg selv, og `OPENCDE_ALLOW_LOCALHOST_REDIRECTS=true` slik at en
app som serveres fra `http://localhost` får logge inn. Deretter:

```sh
docker compose -f compose.yaml -f compose.dev.yaml up -d --build
docker compose -f compose.yaml -f compose.dev.yaml exec api opencde seed
```

Den andre kommandoen oppretter demobrukere og prosjekter og skriver ut
passordene deres én gang; ta vare på passordene til `admin` og `inspection_manager`.
Kontroller <http://localhost:8000/readyz> (svarer `ready`) og logg inn på
<http://localhost:8000/signin> som `admin`: `/admin` viser prosjektene
*Building permit* og *Demolition permit*.

Hvis Compose stopper med `dependency failed to start: container
kontroll-graph-1 is unhealthy`, les `docker compose -f compose.yaml -f
compose.dev.yaml logs graph`. Den vanlige årsaken er et passord på under 16
tegn, som Neo4j avviser (`A password must be at least 16 characters`); den
andre er et databasevolum fra en tidligere installasjon med et annet passord,
som `docker compose -f compose.yaml -f compose.dev.yaml down -v` fjerner
sammen med dataene. To utsjekkinger på samme maskin deler
Compose-prosjektnavnet `kontroll`, så den andre trenger
`COMPOSE_PROJECT_NAME=kontroll-2` og andre `OPENCDE_DEV_*`-porter i sin
`.env`.

## 2. Start Dataspatium

1. Last ned `dataspatium-<version>.zip` fra
   [siste utgivelse](https://github.com/marwiss/Dataspatium/releases/latest)
   og sammenlign SHA-256 med den i utgivelsesteksten.
2. Pakk ut ZIP-filen i en egen mappe (ikke inne i ZIP-filen).
3. For alt unntatt OpenCDE-innloggingen holder det å dobbeltklikke på
   `index.html`. For OpenCDE må mappen serveres over http, fordi
   OAuth2-omdirigeringen trenger en http-adresse:

   ```sh
   cd dataspatium-<version>
   python -m http.server 8080
   ```

   og åpne <http://localhost:8080/>. Appen registrerer seg selv hos serveren
   som offentlig klient med `http://localhost:8080/oauth-callback.html` som
   redirect-URI. (Den publiserte appen på
   <https://marwiss.github.io/Dataspatium/> virker i stedet mot en server som
   tillater den adressen.)

## 3. Koble de to sammen

I Dataspatium: modusen *Inhämta* (Importer) → knappen *Lägg till källa* (Legg
til kilde) → *Typ av tjänst* (Tjenestetype): *OpenCDE (BCF, Documents)* →
*Adress* (Adresse): `http://localhost:8000` → *Lägg till* (Legg til). Kilden
åpnes i *Inhämta*: trykk *Logga in* (Logg inn) og logg inn som `inspection_manager` i
popup-vinduet, og velg deretter *Building permit* i listen *Projekt*. Linjen
under overskriften ("Servern: Kontroll OpenCDE server 2.0.0. Tillägg: …")
kommer fra serverens kapabilitetsdokument og sier hvilke tillegg som er slått
på.

## 4. Opprett en sak fra 3D-visningen

1. Hent eksempelmodellen. Seeden har allerede lagt `three_walls_gtin.ifc`
   (tre vegger med GTIN 3, 2 og 1) som et dokument i *Building permit*; i
   kildens visning i *Inhämta* har dokumentlisten en henteknapp per dokument,
   og dokumentet blir et modelldatasett. Vil du heller sende din egen fil,
   bruk modusen *Dela* (Del) → fanen *Till CDE* (Til CDE): velg kilde og
   prosjekt, *Vad* (hva: originalfil, eksport eller pakke), *Hur* (hvordan:
   Documents API eller BCF) og *Skicka* (Send); hent den så tilbake på samme
   måte.
2. Velg modellen i *Bearbeta* (Bearbeid); den åpnes automatisk i 3D. Marker
   en vegg, åpne panelet *Ärenden* (Saker) og trykk *Nytt ärende* (Ny sak):
   gi den en tittel, behold statusen og kryss av for *Lägg till vyn som
   viewpoint* (Legg til visningen som viewpoint). Saken opprettes gjennom BCF
   API med et viewpoint hvis komponent peker på veggen.
3. Skriv en kommentar i samme panel og send den.

## 5. Se det på serveren

- `/admin/projects` → *Building permit* viser to saker (den seedede og din)
  og dokumentet.
- `/admin/audit` lister innloggingen og appens registrering.
- Med `OPENCDE_REQUEST_LOG_ENABLED=true` i `.env` (og omstart) viser
  `/admin/requests` hvert kall appen gjorde, med de samme
  `X-Request-ID`-verdiene som kortet *Logg* nederst i OpenCDE-kildens visning
  i *Inhämta*, slik at et mislykket kall kan finnes på begge sider.
- Med `OPENCDE_IFCGRAPH_ENABLED=true` blir den opplastede modellen en graf;
  Neo4j Browser på <http://localhost:7484> (`bolt://localhost:7697`, bruker og
  passord fra `.env`) viser veggen som en `IfcWall`-node knyttet til
  viewpointets komponent med `SAME_AS`, og Dataspatiums grafvisning kan spørre
  den med Cypher.

## Neste steg

- [docs/client-guide.md](../client-guide.md) om API-ene,
  kapabilitetsdokumentet og feilkodene.
- [docs/acceptance.md](../acceptance.md) om sjekklistene paret testes med, og
  [docs/dataspatium-coordination.md](../dataspatium-coordination.md) om hva de
  to prosjektene samordner.
- [docs/deploy/](../deploy/) når serveren skal kjøre for andre.
