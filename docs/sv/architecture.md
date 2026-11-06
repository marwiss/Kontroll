# Arkitektur

Kontroll är en webbserver framför en grafdatabas. Den här sidan visar hur delarna
hänger ihop, vad som händer med ett anrop och var allt finns i koden. Läs den om
du vill driva servern med trygghet, ändra den eller bygga vidare på den. Orden
förklaras i [ordlistan](glossary.md).

## Delarna

```mermaid
flowchart LR
    apps["Klienter: Dataspatium, BIM-verktyg, skript"] -- "HTTPS: Foundation, BCF, Documents" --> api
    people["Webbläsare: inloggning, uppladdning, administration"] -- "HTTPS: sidor" --> api
    subgraph kontroll ["Kontroll"]
        api["Webbserver"]
        worker["Konverteringsprocess"]
        api -- "startar" --> worker
    end
    api -- "Bolt" --> graph[("Grafdatabas")]
    api -- "filer" --> files[("Fillagring")]
    worker -- "läser en modell" --> files
```

| Del | Vad den gör | Kod |
|---|---|---|
| Foundation API | Säger vilka API:er servern erbjuder, hur man loggar in och vem du är | `opencde/foundation/` |
| Inloggning | OAuth2 med PKCE, token, klienter, inloggningssidorna och väntetiden efter misslyckade försök | `opencde/auth/`, `opencde/web/` |
| BCF API | Ärenden, kommentarer, viewpoints, händelser, relaterade ärenden och projektdokument | `opencde/bcf/` |
| Documents API | Uppladdning och urval via sidor i webbläsaren, versioner och metadata | `opencde/documents/` |
| Konton | Användare, projekt, medlemskap och roller | `opencde/accounts/` |
| Administration | Sidor och ett API för administratörer, hälsokontroller och begärandeloggen | `opencde/admin/`, `opencde/requestlog.py` |
| IFC-graf | Gör uppladdade modeller till noder och länkar viewpoint-komponenter till dem | `opencde/ifcgraph/` |
| Graflagret | Drivrutinen, de två databasdialekterna, schemat och det som löper ut | `opencde/graph/` |
| Sidor | Mallar, stilar, skript och språkkatalogerna | `opencde/ui/` |

## Ett anrops väg

1. uvicorn tar emot anropet. Den tror på `X-Forwarded-For` bara från proxyerna i
   `OPENCDE_TRUSTED_PROXIES`, så klientens adress är den riktiga.
2. Middleware i `opencde/main.py` ger anropet ett id, loggar det utan innehåll och
   token, begränsar storleken, svarar på CORS och villkorliga anrop, lägger till
   säkerhetshuvudena och tillämpar gränsen för antal anrop.
3. Routens beroenden tar reda på vem som frågar: en bearer-token för API:erna
   (`opencde/auth/dependencies.py`), en sessionskaka för sidorna
   (`opencde/web/dependencies.py`).
4. Ett repository frågar grafen, bara med parametrar. Varje fråga efter projektdata
   börjar i användarens nod och går genom `MEMBER_OF`, så det en användare inte är
   medlem i finns inte för hen och svarar 404.
5. Svaret följer schemana i `spec/`, och alla fel har samma form
   (`opencde/errors.py`).

## Var data finns

| Vad | Var | Läs mer |
|---|---|---|
| Användare, projekt, ärenden, kommentarer, viewpoints, dokumentmetadata, klienter och granskningsloggen | Grafdatabasen | [Grafschema](graph-schema.md) |
| Token, koder och klienthemligheter som SHA-256-hashar; lösenord som Argon2id-hashar | Grafdatabasen | [Säkerhetskontroller](security/controls.md) |
| Uppladdade filer och viewpoint-bilder, under namn som servern väljer | Fillagringen i `OPENCDE_DATA_DIR` | [Documents API-flöden](flows/documents.md) |
| Modeller som noder och relationer | Grafdatabasen | [IFC-graf](ifcgraph.md) |
| Serverns egna inställningar och hemligheter | `.env` eller `/run/secrets` | [Lokalt test](deploy/local.md) |

## Arbete utanför anropen

- Varje minut (`OPENCDE_CLEANUP_INTERVAL_SECONDS`) tar servern bort det som löpt ut,
  som koder, token, sessioner och oavslutade uppladdningar, och tar upp
  konverteringar som en stoppad server lämnat efter sig.
- IFC-konverteringar körs en i taget i en egen process, med gränser för tid och
  minne, så att en trasig modell inte kan fälla servern.
- När begärandeloggen är på (`OPENCDE_REQUEST_LOG_ENABLED`) sparar en skrivare
  anropen i grafen i omgångar och tar bort de gamla.

## Säker från början

- Inget är öppet förrän någon öppnar det: självregistrering av klienter, IFC-grafen,
  begärandeloggen och graffrågor är avstängda från början.
- I produktion vägrar servern starta utan https och databaslösenord.
- Sidorna har inga inbäddade skript eller stilar, varje formulär har en signerad
  token och varje sida fungerar utan JavaScript.

[Hotmodellen](security/threat-model.md) säger vad det här skyddar mot, och
[kontrollerna](security/controls.md) nämner provet bakom varje åtgärd.

## Två databaser

Servern kör på Neo4j eller Memgraph med samma Cypher. Bara schemasatserna skiljer
sig, och de finns i `opencde/graph/dialect.py` tillsammans med listan över
funktioner som koden inte får använda. Skälen står i
[ADR 0003](../adr/0003-dialect-neutral-cypher.md).

## Så provas den

| Mapp | Vad den visar | När den körs |
|---|---|---|
| `tests/unit` | Funktioner och dokument, utan databas | Vid varje push |
| `tests/conformance` | Routes och svar mot schemana i `spec/` | Vid varje push |
| `tests/security` | Huvuden, token, gränser och att varje operation kräver token | Vid varje push |
| `tests/integration` | Allt mot en riktig databas i Docker | Vid varje push; även på Memgraph varje natt |
| `tests/ui` | Sidorna i en riktig webbläsare, med tillgänglighetskontroll | Vid varje push |
| `tests/e2e` | Klientbiblioteket mot en körande server, genererade anrop och en omstart av hela stacken | Vid varje push; de långa körningarna varje natt |

## Läs vidare

- [Snabbstart](quickstart.md): servern och Dataspatium på din egen dator.
- [Bygga en klient](client-guide.md): det som en klient behöver.
- [Flöden](flows/oauth2.md): inloggning, [dokument](flows/documents.md) och
  [BCF-viewpoints](flows/bcf-viewpoint.md) som sekvensdiagram.
- [Arkitekturbeslut](../adr/): varför det är byggt så här.
