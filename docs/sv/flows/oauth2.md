# OAuth2 authorization code-flödet med PKCE

Hur en klient (ett BCF-tillägg, en visare, ett skript) får en access-token på
en användares vägnar. Detta är Foundation API 2.2 med härdningen i RFC 9700
och OAuth 2.1: PKCE `S256` för varje klient, exakt matchning av redirect-URI
(loopback-portar undantagna, RFC 8252), engångskoder, roterande
refresh-tokens.

```mermaid
sequenceDiagram
    autonumber
    participant C as Klientapplikation
    participant B as Användarens webbläsare
    participant S as OpenCDE-server
    participant G as Grafdatabas

    C->>S: GET /foundation/1.0/auth
    S-->>C: oauth2_auth_url, oauth2_token_url, flöden
    Note over C: Generera code_verifier, state;<br/>code_challenge = BASE64URL(SHA256(verifier))
    C->>B: Öppna oauth2_auth_url?response_type=code&client_id&redirect_uri&state&code_challenge&code_challenge_method=S256
    B->>S: GET /foundation/oauth2/auth
    S->>G: Läs klienten, kontrollera att redirect_uri är registrerad
    S-->>B: Inloggnings- och samtyckessida (signerad formulärtoken)
    B->>S: POST /foundation/oauth2/auth (användarnamn, lösenord, beslut)
    S->>G: Verifiera lösenordet (Argon2id); lagra kodens hash bunden till klient, redirect_uri, challenge
    S-->>B: 302 redirect_uri?code=…&state=…&iss=…
    B->>C: Webbläsaren landar på klientens redirect-URI
    C->>S: POST /foundation/oauth2/token grant_type=authorization_code, code, code_verifier (+ klientautentisering)
    S->>G: Matcha kodens hash, verifiera SHA256(verifier) = challenge, markera förbrukad, lagra tokenhashar
    S-->>C: 201 access_token, refresh_token, expires_in, scope (Cache-Control: no-store)
    C->>S: GET /bcf/3.0/projects  Authorization: Bearer access_token
    S->>G: Slå upp tokenhash, användare, klient, scope
    S-->>C: 200 projekt
    C->>S: POST /foundation/oauth2/token grant_type=refresh_token
    S->>G: Markera den gamla refresh-tokenen förbrukad, utfärda ett nytt par i samma familj
    S-->>C: 201 ny access_token och refresh_token
```

Ett utarbetat exempel på klientsidan av det här flödet i en webbläsare är
OpenCDE-källan i [Dataspatium](https://github.com/marwiss/Dataspatium)
(`src/api/families/opencde.js`): PKCE-verifier och -challenge, popup-fönstret
till auktoriseringssidan, callback-sidan som rapporterar koden tillbaka,
tokenutbytet som publik klient, refresh med rotation och återkallning vid
utloggning.

## Vad varje part måste göra

| Steg | Klient | Server |
|---|---|---|
| Upptäckt | Läs `/foundation/1.0/auth`; hårdkoda aldrig endpoints | Annonsera endpoints, `oauth2_pkce_required: true` |
| Auktoriseringsbegäran | Nytt `state` och ny `code_verifier` per försök; `code_challenge_method=S256` | Avvisa okända klienter och oregistrerade redirect-URI:er *utan* att omdirigera; omdirigera andra fel med `error`, `state`, `iss` |
| Inloggning | — | Begränsa inloggningstakten; generiskt felmeddelande; CSRF-skyddat formulär; inget lösenord i URL eller logg |
| Kod | Lös in inom 60 sekunder; skicka `code_verifier` | Koden är engångs; en återanvändning återkallar de tokens den gav |
| Tokens | Lagra säkert; skicka bara som `Authorization: Bearer`; förnya före utgång | Opaka, hashade i vila; access 1 h, refresh 30 dagar, rotation med upptäckt av återanvändning |
| Utloggning | `POST /foundation/oauth2/revoke` med refresh-tokenen | Ta bort hela tokenfamiljen |

## Fel

Fel från auktoriseringsendpointen går tillbaka till klienten som
frågeparametrar (`error`, `error_description`, `state`, `iss`) enligt RFC
6749 §4.1.2.1, utom när klienten eller dess redirect-URI är problemet, då
servern visar en felsida och inte omdirigerar någonstans. Fel från
token-endpointen använder kroppen i RFC 6749 §5.2 (`error`,
`error_description`) med OpenCDE-fältet `message` tillagt.
