# Personuppgifter och lagringstid

Vad en Kontroll-server lagrar om personer, hur länge, och vem som kan se
det. Det här är serverns halva av en sida som delas med Dataspatium; appens
halva (vad den sparar i webbläsaren och vad den skickar) finns i Dataspatiums
dokumentation. Den som driver Kontroll åt andra är personuppgiftsansvarig för
dessa uppgifter; sidan ger fakta för de egna anteckningarna.

## Vad som lagras

| Uppgift | Var | Innehåll | Behålls |
|---|---|---|---|
| Användarkonton | `User`-noder | användarnamn, fullständigt namn, e-post (valfritt), Argon2id-hash av lösenordet, administratörsflagga, skapandetid, senaste inloggning | Tills en administratör tar bort kontot |
| Projektmedlemskap | `MEMBER_OF`-relationer | användare, projekt, roll | Tills det tas bort |
| OAuth2-tokens | noderna `AuthorizationCode`, `AccessToken`, `RefreshToken` | SHA-256-hashar (aldrig tokens i klartext), användare, klient, scope, tidpunkter | Koder 60 s, access-tokens 1 h, refresh-tokens 30 dagar (`OPENCDE_*_TTL_SECONDS`); tas bort av städjobbet när de gått ut eller återkallats |
| Webbläsarsessioner | `WebSession`-noder | användare, skapandetid och senaste aktivitet, klientadressen vid inloggningen | 8 timmar, eller 30 minuters inaktivitet; tas bort vid utloggning |
| Misslyckade inloggningar | `SignInThrottle`-noder | en hash av användarnamnet, antalet misslyckanden, när nästa försök är tillåtet | ett dygn efter det senaste misslyckandet; en lyckad inloggning tar bort den |
| OAuth2-klienter | `Client`-noder | namn, beskrivning, adress, redirect-URI:er, hashad hemlighet, `software_id`/`software_version`, vem som skapade den | Tills de tas bort; självregistrerade klienter som inte använts på 30 dagar tas bort med sina tokens |
| BCF-data | noderna `Topic`, `Comment`, `Viewpoint`, `Event` med tillhörande | titlar, beskrivningar och kommentarer som användare skrivit, användarnamn som författare och tilldelade, tidpunkter, ögonblicksbilder, komponentreferenser | Tills ärendet, kommentaren eller projektet tas bort |
| Dokument | noderna `Document` och `DocumentVersion`, filer under `OPENCDE_DATA_DIR` | titel, filnamn, storlek, SHA-256, uppladdare, tid; själva filen (som kan innehålla personuppgifter, till exempel namn i en IFC-modells ägarhistorik) | Tills versionen eller projektet tas bort; säkerhetskopior behåller kopior så länge operatören behåller säkerhetskopiorna |
| IFC-graf | `IfcModel`-noder och entiteterna i varje importerad modell | IFC-filens innehåll som grafdata, inklusive `IfcOwnerHistory` för projektet; med `OPENCDE_IFCGRAPH_LOSSLESS` hela filen, med dess header och varje owner history | Ersatta eller misslyckade modeller tas bort med `opencde ifcgraph prune`; annars med dokumentversionen |
| Revisionslogg | `AuditEvent`-noder | vad som hände (inloggning, utfärdad token, registrerad klient, ändrad roll …), vem som gjorde det, klientadressen, tid, request-id | Går inte ut av sig själv; administratörer kan exportera den som CSV och operatören tar bort enligt egen policy |
| Begärandelogg (valfri) | `RequestLog`-noder | metod, sökväg utan frågesträng, operation, status, tid, bytestorlekar, request-id, användar- eller klient-id; aldrig huvuden, kroppar eller tokens | `OPENCDE_REQUEST_LOG_RETENTION_HOURS` (72 som standard); avstängd om inte `OPENCDE_REQUEST_LOG_ENABLED=true` |
| Uppladdnings- och urvalssessioner | noderna `UploadSession`, `UploadPart`, `SelectionSession` och tillfälliga delfiler | vem som startade flödet, vilka filer, callback-adress, tidpunkter | 24 timmar för uppladdningar, 10 minuter för sidlänkarna; städas av servern |
| Serverloggar | containerns standardutmatning (JSON-rader) | request-id, sökväg, status, tid, användar- eller klient-id, klientadressen från den betrodda proxyn; aldrig kroppar, tokens, koder eller lösenord | Så länge operatören behåller containerloggar |

Säkerhetskopior gjorda med `opencde backup` eller tjänsten `backup` innehåller
allt ovan utom serverloggarna, krypterade eller inte efter operatörens val
([deploy/backup.md](../deploy/backup.md)).

## Vem ser vad

- Medlemmar i ett projekt ser dess ärenden, kommentarer, viewpoints och
  dokument genom API:erna; rollen avgör vad de får ändra. Användare utanför
  ett projekt kan inte se att det finns (404).
- Administratörer ser alla användare, projekt, klienter, sessioner,
  revisionsloggen och, när den är på, begärandeloggen, på sidorna under
  `/admin` och, med en bearer-token som har scopet `admin`, genom
  `/admin/api`.
- Varje användare ser sitt eget konto, sina applikationer och sessioner på
  `/account` och kan återkalla dem.
- Ingen ser lösenord, hemligheter eller tokens: servern lagrar bara hashar
  och visar en ny hemlighet en gång, när den skapas.
- Vem som helst kan läsa `/.well-known/kontroll`, `/foundation/versions`,
  `/foundation/1.0/auth` och `/healthz`; de innehåller konfiguration, aldrig
  personer.

## Rättigheter och åtgärder

- **Ta bort en person**: ta bort kontot under `/admin/users` (eller med
  `opencde user delete`); sessioner och tokens följer med. Namnet står kvar
  på ärenden och kommentarer personen skrivit, som projektets BCF-data; ta
  bort eller redigera dem genom API:t eller ta bort projektet.
- **Exportera**: revisionsloggen exporteras som CSV; BCF- och dokumentdata
  exporteras genom API:erna (en klient som Dataspatium kan spara ett projekt
  som BCFzip); `opencde backup` skriver hela databasen.
- **Incident**: `opencde revoke --all` avslutar alla sessioner och tokens;
  rotera databaslösenordet och den hemliga nyckeln efteråt
  ([controls.md](controls.md)).
- **Minimera**: låt begärandeloggen vara avstängd om du inte felsöker en
  klient, håll `OPENCDE_DYNAMIC_CLIENT_REGISTRATION` avstängd om du inte
  behöver den, och publicera inte databasporten
  ([deploy/bolt.md](../deploy/bolt.md)).

## I Dataspatium

Appen sparar serverns adress, klient-id:t den registrerat, användarens tokens
för sessionen och en logg över sina anrop (med request-id:n) i webbläsaren;
den sparar aldrig lösenordet. Vad av detta som lämnar webbläsaren, och hur
det rensas, står på [Dataspatiums egen sida om personuppgifter](https://github.com/marwiss/Dataspatium/blob/main/docs/sakerhet.md).
