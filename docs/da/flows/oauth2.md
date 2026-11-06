# OAuth2 authorization code-forløbet med PKCE

Hvordan en klient (et BCF-plugin, en viewer, et script) får en access-token på
en brugers vegne. Dette er Foundation API 2.2 med hærdningen fra RFC 9700 og
OAuth 2.1: PKCE `S256` for hver klient, nøjagtig matchning af redirect-URI
(loopback-porte undtaget, RFC 8252), engangskoder, roterende refresh-tokens. Undtagelsen er en fortrolig klient, som en administrator har
markeret, fordi den ikke kan bruge PKCE, som en klient, der kun implementerer BCF API
2.1; se [klientguiden](../client-guide.md).

```mermaid
sequenceDiagram
    autonumber
    participant C as Klientapplikation
    participant B as Brugerens browser
    participant S as OpenCDE-server
    participant G as Grafdatabase

    C->>S: GET /foundation/1.0/auth
    S-->>C: oauth2_auth_url, oauth2_token_url, forløb
    Note over C: Generér code_verifier, state;<br/>code_challenge = BASE64URL(SHA256(verifier))
    C->>B: Åbn oauth2_auth_url?response_type=code&client_id&redirect_uri&state&code_challenge&code_challenge_method=S256
    B->>S: GET /foundation/oauth2/auth
    S->>G: Indlæs klienten, tjek at redirect_uri er registreret
    S-->>B: Login- og samtykkeside (signeret formulartoken)
    B->>S: POST /foundation/oauth2/auth (brugernavn, kodeord, beslutning)
    S->>G: Verificér kodeordet (Argon2id); gem kodens hash bundet til klient, redirect_uri, challenge
    S-->>B: 302 redirect_uri?code=…&state=…&iss=…
    B->>C: Browseren lander på klientens redirect-URI
    C->>S: POST /foundation/oauth2/token grant_type=authorization_code, code, code_verifier (+ klientautentificering)
    S->>G: Match kodens hash, verificér SHA256(verifier) = challenge, markér brugt, gem tokenhashes
    S-->>C: 201 access_token, refresh_token, expires_in, scope (Cache-Control: no-store)
    C->>S: GET /bcf/3.0/projects  Authorization: Bearer access_token
    S->>G: Slå tokenhash, bruger, klient, scope op
    S-->>C: 200 projekter
    C->>S: POST /foundation/oauth2/token grant_type=refresh_token
    S->>G: Markér den gamle refresh-token brugt, udsted et nyt par i samme familie
    S-->>C: 201 ny access_token og refresh_token
```

Et gennemarbejdet eksempel på klientsiden af dette forløb i en browser er
OpenCDE-kilden i [Dataspatium](https://github.com/marwiss/Dataspatium)
(`src/api/families/opencde.js`): PKCE-verifier og -challenge, pop op-vinduet
til autorisationssiden, callback-siden, der rapporterer koden tilbage,
tokenudvekslingen som offentlig klient, refresh med rotation og
tilbagekaldelse ved logout.

En bruger med et kodeord, som en anden kender (en ny konto eller en nulstilling), får ingen kode. Serveren fører browseren til kontosiden for at skifte det og derefter tilbage til autorisationssiden med det, klienten bad om. Klienten mærker intet andet end en længere ventetid.

## Hvad hver part skal gøre

| Trin | Klient | Server |
|---|---|---|
| Opdagelse | Læs `/foundation/1.0/auth`; hardcode aldrig endepunkter | Annoncér endepunkter, `oauth2_pkce_required: true` |
| Autorisationsanmodning | Nyt `state` og ny `code_verifier` per forsøg; `code_challenge_method=S256` | Afvis ukendte klienter og uregistrerede redirect-URI'er *uden* at omdirigere; omdirigér andre fejl med `error`, `state`, `iss` |
| Login | — | Begræns login-hastigheden; generisk fejlbesked; CSRF-beskyttet formular; intet kodeord i URL eller log |
| Kode | Indløs inden for 60 sekunder; send `code_verifier` | Koden er til engangsbrug; et genbrug tilbagekalder de tokens, den gav |
| Tokens | Opbevar sikkert; send kun som `Authorization: Bearer`; forny før udløb | Opake, hashede i hvile; access 1 t, refresh 30 dage, rotation med registrering af genbrug |
| Logout | `POST /foundation/oauth2/revoke` med refresh-tokenen | Slet hele tokenfamilien |

## Fejl

Fejl fra autorisationsendepunktet går tilbage til klienten som
forespørgselsparametre (`error`, `error_description`, `state`, `iss`) ifølge
RFC 6749 §4.1.2.1, medmindre klienten eller dens redirect-URI er problemet; i
så fald viser serveren en fejlside og omdirigerer ikke nogen steder. Fejl fra
token-endepunktet bruger kroppen fra RFC 6749 §5.2 (`error`,
`error_description`) med OpenCDE-feltet `message` tilføjet.
