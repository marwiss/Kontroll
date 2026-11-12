# Ordliste

De ord, denne dokumentation bruger, med hvad de betyder her. Sag, kommentar,
viewpoint og projekt er de samme ord som i Dataspatium.

## Standarder

| Ord | Hvad det betyder her |
|---|---|
| OpenCDE | buildingSMART's API'er til et fælles datamiljø: Foundation, BCF og Documents |
| CDE | Common data environment, fælles datamiljø: det delte sted for et projekts information |
| Foundation API | Den del af OpenCDE, der siger, hvilke API'er en server tilbyder, hvordan man logger ind, og hvem du er |
| BCF | BIM Collaboration Format, til sager om en bygningsmodel. BCF API 3.0 og 2.1 er dets web-API'er |
| Documents API | Den del af OpenCDE, der uploader og vælger dokumenter via sider i browseren |
| IFC | Industry Foundation Classes, det åbne filformat til bygningsmodeller |

## I et projekt

| Ord | Hvad det betyder her |
|---|---|
| Projekt | Det delte rum: medlemmerne, sagerne og dokumenterne |
| Medlem, rolle | En person i et projekt, som viewer, contributor, editor eller manager. Rollen afgør, hvad vedkommende må |
| Administrator | En bruger, der styrer brugere, projekter og klienter. Det er ikke en rolle i et projekt og giver ikke adgang til projektets indhold |
| Udvidelser (extensions) | De værdier, et projekt tillader for type, status, prioritet, etiketter og så videre |
| Sag (topic) | Noget at gøre, tjekke eller svare på. BCF's ord er topic |
| Kommentar | En bemærkning til en sag, som kan pege på et viewpoint |
| Viewpoint | En gemt visning af modellen: kamera, komponenter og et billede |
| Komponent | En bygningsdel, som et viewpoint nævner, med sit `GlobalId` |
| Øjebliksbillede (snapshot) | Billedet i et viewpoint |
| Hændelse | En post i historikken for en sag eller en kommentar |
| Dokument, version | En fil med en titel; en ny upload af den er en ny version |

## Login

| Ord | Hvad det betyder her |
|---|---|
| Klient | Et program, der arbejder på en brugers vegne, registreret på serveren |
| Offentlig klient | En klient, der ikke kan holde på en hemmelighed, som en browser- eller computerapp |
| Fortrolig klient | En klient på sin egen server, som kan holde på en hemmelighed |
| Selvregistrering | At en klient registrerer sig selv, slået fra fra start |
| Redirect-URI | Adressen, serveren sender browseren tilbage til efter login |
| PKCE | Et engangsbevis på, at den, der indløser koden, er den, der bad om den |
| Access-token | Et kortlivet bevis, der sendes med hver forespørgsel til API'erne |
| Refresh-token | Et længerevarende bevis, der giver en ny access-token og gælder én gang |
| Scope | Hvad en token må bruges til: `profile`, `bcf`, `documents` eller `admin` |

## Modellen som graf

| Ord | Hvad det betyder her |
|---|---|
| IFC-graf | En uploadet model som noder og relationer i databasen, valgfrit |
| IFC-DB | Modulet, der gør IFC-filer til en IFC-graf og tilbage, indtil november 2026 kaldet IFC-graph og siden IFC-LPG |
| `GlobalId` | Det varige id for et element i en IFC-fil |
| `gtin` | GTIN for det element, et viewpoints komponent nævner, læst fra modellen og gemt på komponenten |
| GTIN | Global Trade Item Number, et produkts nummer; her læst fra egenskabssættet `Reuse` |
| Cypher | Grafdatabasens forespørgselssprog |
| Bolt | Databasens egen forbindelse, valgfri for dem, der spørger grafen direkte |

## At drive serveren

| Ord | Hvad det betyder her |
|---|---|
| Stak | De containere, der udgør en kørende server: API'et, databasen og i produktion proxyen og sikkerhedskopieringen |
| Seed | `opencde seed`, der indlæser demonstrationsdata i en tom database |
| Capabilities | `/.well-known/dataregium`, som siger, hvad denne server har slået til |
| Forespørgselslog | En valgfri fortegnelse over de forespørgsler, serveren har besvaret |
| Revisionslog | Fortegnelsen over, hvem der har logget ind og ændret hvad |
