# Ordliste

Orda denne dokumentasjonen brukar, med kva dei tyder her. Sak, kommentar,
viewpoint og prosjekt er dei same orda som i Dataspatium.

## Standardar

| Ord | Kva det tyder her |
|---|---|
| OpenCDE | API-a til buildingSMART for eit felles datamiljø: Foundation, BCF og Documents |
| CDE | Common data environment, felles datamiljø: den delte staden for informasjonen til eit prosjekt |
| Foundation API | Delen av OpenCDE som seier kva API-ar ein server tilbyr, korleis ein loggar inn, og kven du er |
| BCF | BIM Collaboration Format, for saker om ein bygningsmodell. BCF API 3.0 og 2.1 er vev-API-a |
| Documents API | Delen av OpenCDE som lastar opp og vel dokument via sider i nettlesaren |
| IFC | Industry Foundation Classes, det opne filformatet for bygningsmodellar |

## I eit prosjekt

| Ord | Kva det tyder her |
|---|---|
| Prosjekt | Det delte rommet: medlemmene, sakene og dokumenta |
| Medlem, rolle | Nokon i eit prosjekt, som viewer, contributor, editor eller manager. Rolla avgjer kva vedkomande får gjere |
| Administrator | Ein brukar som styrer brukarar, prosjekt og klientar. Det er inga rolle i eit prosjekt og gjev ikkje tilgang til innhaldet i prosjektet |
| Utvidingar (extensions) | Verdiane eit prosjekt tillèt for type, status, prioritet, etikettar og så vidare |
| Sak (topic) | Noko å gjere, sjekke eller svare på. Ordet i BCF er topic |
| Kommentar | Ein merknad til ei sak, som kan peike på eit viewpoint |
| Viewpoint | Ei lagra vising av modellen: kamera, komponentar og eit bilete |
| Komponent | Ein bygningsdel eit viewpoint nemner, med sin `GlobalId` |
| Augneblinksbilete (snapshot) | Biletet i eit viewpoint |
| Hending | Ein post i historikken for ei sak eller ein kommentar |
| Dokument, versjon | Ei fil med ein tittel; ei ny opplasting av ho er ein ny versjon |

## Innlogging

| Ord | Kva det tyder her |
|---|---|
| Klient | Eit program som arbeider på vegner av ein brukar, registrert på serveren |
| Offentleg klient | Ein klient som ikkje kan halde på ein løyndom, som ein nettlesar- eller datamaskinapp |
| Konfidensiell klient | Ein klient på sin eigen server, som kan halde på ein løyndom |
| Sjølvregistrering | At ein klient registrerer seg sjølv, av frå start |
| Redirect-URI | Adressa serveren sender nettlesaren tilbake til etter innlogginga |
| PKCE | Eit eingongsprov på at den som løyser inn koden, er den som bad om han |
| Access-token | Eit kortliva prov som blir sendt med kvar førespurnad til API-a |
| Refresh-token | Eit lengre prov som gjev eit nytt access-token og gjeld éin gong |
| Scope | Kva eit token kan brukast til: `profile`, `bcf`, `documents` eller `admin` |

## Modellen som graf

| Ord | Kva det tyder her |
|---|---|
| IFC-graf | Ein opplasta modell som nodar og relasjonar i databasen, valfritt |
| IFC-LPG | Modulen som gjer IFC-filer til ein IFC-graf og tilbake, fram til november 2026 kalla IFC-graph |
| `GlobalId` | Den varige id-en til eit element i ei IFC-fil |
| `SAME_AS` | Relasjonen frå ein viewpoint-komponent til elementet i ein modell |
| GTIN | Global Trade Item Number, nummeret til eit produkt; her lese frå eigenskapssettet `Reuse` |
| Cypher | Spørjespråket til grafdatabasen |
| Bolt | Den eigne tilkoplinga til databasen, valfri for dei som spør grafen direkte |

## Å drive serveren

| Ord | Kva det tyder her |
|---|---|
| Stakk | Containerane som utgjer ein køyrande server: API-et, databasen og i produksjon proxyen og tryggingskopieringa |
| Seed | `opencde seed`, som lastar demonstrasjonsdata inn i ein tom database |
| Capabilities | `/.well-known/dataregium`, som seier kva denne serveren har slått på |
| Førespurnadslogg | Ei valfri oversikt over førespurnadene serveren har svart på |
| Revisjonslogg | Oversikta over kven som har logga inn og endra kva |
