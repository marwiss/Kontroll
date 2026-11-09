# Ordliste

Ordene denne dokumentasjonen bruker, med hva de betyr her. Sak, kommentar,
viewpoint og prosjekt er de samme ordene som i Dataspatium.

## Standarder

| Ord | Hva det betyr her |
|---|---|
| OpenCDE | buildingSMARTs API-er for et felles datamiljø: Foundation, BCF og Documents |
| CDE | Common data environment, felles datamiljø: det delte stedet for et prosjekts informasjon |
| Foundation API | Delen av OpenCDE som sier hvilke API-er en server tilbyr, hvordan man logger inn, og hvem du er |
| BCF | BIM Collaboration Format, for saker om en bygningsmodell. BCF API 3.0 og 2.1 er web-API-ene |
| Documents API | Delen av OpenCDE som laster opp og velger dokumenter via sider i nettleseren |
| IFC | Industry Foundation Classes, det åpne filformatet for bygningsmodeller |

## I et prosjekt

| Ord | Hva det betyr her |
|---|---|
| Prosjekt | Det delte rommet: medlemmene, sakene og dokumentene |
| Medlem, rolle | Noen i et prosjekt, som viewer, contributor, editor eller manager. Rollen avgjør hva vedkommende får gjøre |
| Administrator | En bruker som styrer brukere, prosjekter og klienter. Det er ingen rolle i et prosjekt og gir ikke tilgang til prosjektets innhold |
| Utvidelser (extensions) | Verdiene et prosjekt tillater for type, status, prioritet, etiketter og så videre |
| Sak (topic) | Noe å gjøre, sjekke eller svare på. BCFs ord er topic |
| Kommentar | En merknad til en sak, som kan peke på et viewpoint |
| Viewpoint | En lagret visning av modellen: kamera, komponenter og et bilde |
| Komponent | En bygningsdel et viewpoint nevner, med sin `GlobalId` |
| Øyeblikksbilde (snapshot) | Bildet i et viewpoint |
| Hendelse | En post i historikken for en sak eller en kommentar |
| Dokument, versjon | En fil med en tittel; en ny opplasting av den er en ny versjon |

## Innlogging

| Ord | Hva det betyr her |
|---|---|
| Klient | Et program som arbeider på vegne av en bruker, registrert på serveren |
| Offentlig klient | En klient som ikke kan holde på en hemmelighet, som en nettleser- eller datamaskinapp |
| Konfidensiell klient | En klient på sin egen server, som kan holde på en hemmelighet |
| Selvregistrering | At en klient registrerer seg selv, av fra start |
| Redirect-URI | Adressen serveren sender nettleseren tilbake til etter innloggingen |
| PKCE | Et engangsbevis på at den som løser inn koden, er den som ba om den |
| Access-token | Et kortlivet bevis som sendes med hver forespørsel til API-ene |
| Refresh-token | Et lengre bevis som gir et nytt access-token og gjelder én gang |
| Scope | Hva et token kan brukes til: `profile`, `bcf`, `documents` eller `admin` |

## Modellen som graf

| Ord | Hva det betyr her |
|---|---|
| IFC-graf | En opplastet modell som noder og relasjoner i databasen, valgfritt |
| IFC-LPG | Modulen som gjør IFC-filer til en IFC-graf, fram til november 2026 kalt IFC-graph |
| `GlobalId` | Den varige id-en til et element i en IFC-fil |
| `SAME_AS` | Relasjonen fra en viewpoint-komponent til elementet i en modell |
| GTIN | Global Trade Item Number, et produkts nummer; her lest fra egenskapssettet `Reuse` |
| Cypher | Spørrespråket til grafdatabasen |
| Bolt | Databasens egen forbindelse, valgfri for dem som spør grafen direkte |

## Å drive serveren

| Ord | Hva det betyr her |
|---|---|
| Stakk | Containerne som utgjør en kjørende server: API-et, databasen og i produksjon proxyen og sikkerhetskopieringen |
| Seed | `opencde seed`, som laster demonstrasjonsdata inn i en tom database |
| Capabilities | `/.well-known/dataregium`, som sier hva denne serveren har slått på |
| Forespørselslogg | En valgfri oversikt over forespørslene serveren har svart på |
| Revisjonslogg | Oversikten over hvem som har logget inn og endret hva |
