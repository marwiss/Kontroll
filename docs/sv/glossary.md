# Ordlista

Orden som den här dokumentationen använder, med vad de betyder här. Ärende,
kommentar, viewpoint och projekt är samma ord som i Dataspatium.

## Standarder

| Ord | Vad det betyder här |
|---|---|
| OpenCDE | buildingSMART:s API:er för en gemensam datamiljö: Foundation, BCF och Documents |
| CDE | Common data environment, gemensam datamiljö: den delade platsen för ett projekts information |
| Foundation API | Delen av OpenCDE som säger vilka API:er en server erbjuder, hur man loggar in och vem du är |
| BCF | BIM Collaboration Format, för ärenden om en byggnadsmodell. BCF API 3.0 och 2.1 är dess webb-API:er |
| Documents API | Delen av OpenCDE som laddar upp och väljer dokument via sidor i webbläsaren |
| IFC | Industry Foundation Classes, det öppna filformatet för byggnadsmodeller |

## I ett projekt

| Ord | Vad det betyder här |
|---|---|
| Projekt | Det delade utrymmet: medlemmarna, ärendena och dokumenten |
| Medlem, roll | Någon i ett projekt, som viewer, contributor, editor eller manager. Rollen avgör vad hen får göra |
| Administratör | En användare som sköter användare, projekt och klienter. Det är ingen roll i ett projekt och ger ingen tillgång till projektets innehåll |
| Tillägg (extensions) | De värden ett projekt tillåter för typ, status, prioritet, etiketter och så vidare |
| Ärende (topic) | Något att göra, kontrollera eller svara på. BCF:s ord är topic |
| Kommentar | En anmärkning på ett ärende, som kan peka på en viewpoint |
| Viewpoint | En sparad vy av modellen: kamera, komponenter och en bild |
| Komponent | En byggnadsdel som en viewpoint nämner, med sitt `GlobalId` |
| Ögonblicksbild (snapshot) | Bilden i en viewpoint |
| Händelse | En post i historiken för ett ärende eller en kommentar |
| Dokument, version | En fil med en titel; en ny uppladdning av den är en ny version |

## Inloggning

| Ord | Vad det betyder här |
|---|---|
| Klient | Ett program som arbetar för en användares räkning, registrerat på servern |
| Publik klient | En klient som inte kan hålla en hemlighet, som en webbläsar- eller datorapp |
| Konfidentiell klient | En klient på en egen server, som kan hålla en hemlighet |
| Självregistrering | Att en klient registrerar sig själv, avstängt från början |
| Redirect-URI | Adressen som servern skickar tillbaka webbläsaren till efter inloggningen |
| PKCE | Ett engångsbevis på att den som byter in koden är den som bad om den |
| Access-token | Ett kortlivat bevis som skickas med varje anrop till API:erna |
| Refresh-token | Ett längre bevis som ger en ny access-token och gäller en gång |
| Scope | Vad en token får användas till: `profile`, `bcf`, `documents` eller `admin` |

## Modellen som graf

| Ord | Vad det betyder här |
|---|---|
| IFC-graf | En uppladdad modell som noder och relationer i databasen, valfritt |
| IFC-LPG | Modulen som gör IFC-filer till en IFC-graf, fram till november 2026 kallad IFC-graph |
| `GlobalId` | Det bestående id:t för ett element i en IFC-fil |
| `SAME_AS` | Relationen från en viewpoints komponent till elementet i en modell |
| GTIN | Global Trade Item Number, en produkts nummer; här läst från egenskapsuppsättningen `Reuse` |
| Cypher | Grafdatabasens frågespråk |
| Bolt | Databasens egen anslutning, valfri för den som frågar grafen direkt |

## Att driva servern

| Ord | Vad det betyder här |
|---|---|
| Stack | Containrarna som utgör en körande server: API:et, databasen och i produktion proxyn och säkerhetskopieringen |
| Seed | `opencde seed`, som läser in demonstrationsdata i en tom databas |
| Capabilities | `/.well-known/dataregium`, som säger vad den här servern har slagit på |
| Begärandelogg | En valfri förteckning över anropen som servern har svarat på |
| Granskningslogg | Förteckningen över vem som loggat in och ändrat vad |
