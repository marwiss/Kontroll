# OAuth2 authorization code-flyten med PKCE

Korleis ein klient (eit BCF-tillegg, ein visar, eit skript) får eit
access-token på vegner av ein brukar. Dette er Foundation API 2.2 med
herdinga frå RFC 9700 og OAuth 2.1: PKCE `S256` for kvar klient, nøyaktig
matching av redirect-URI (loopback-portar unnatekne, RFC 8252),
eingongskodar, roterande refresh-tokens.

```mermaid
sequenceDiagram
    autonumber
    participant C as Klientapplikasjon
    participant B as Nettlesaren til brukaren
    participant S as OpenCDE-server
    participant G as Grafdatabase

    C->>S: GET /foundation/1.0/auth
    S-->>C: oauth2_auth_url, oauth2_token_url, flytar
    Note over C: Generer code_verifier, state;<br/>code_challenge = BASE64URL(SHA256(verifier))
    C->>B: Opne oauth2_auth_url?response_type=code&client_id&redirect_uri&state&code_challenge&code_challenge_method=S256
    B->>S: GET /foundation/oauth2/auth
    S->>G: Last klienten, sjekk at redirect_uri er registrert
    S-->>B: Innloggings- og samtykkeside (signert skjematoken)
    B->>S: POST /foundation/oauth2/auth (brukarnamn, passord, avgjerd)
    S->>G: Verifiser passordet (Argon2id); lagre hashen til koden bunden til klient, redirect_uri, challenge
    S-->>B: 302 redirect_uri?code=…&state=…&iss=…
    B->>C: Nettlesaren landar på redirect-URI-en til klienten
    C->>S: POST /foundation/oauth2/token grant_type=authorization_code, code, code_verifier (+ klientautentisering)
    S->>G: Match hashen til koden, verifiser SHA256(verifier) = challenge, merk som brukt, lagre tokenhashar
    S-->>C: 201 access_token, refresh_token, expires_in, scope (Cache-Control: no-store)
    C->>S: GET /bcf/3.0/projects  Authorization: Bearer access_token
    S->>G: Slå opp tokenhash, brukar, klient, scope
    S-->>C: 200 prosjekt
    C->>S: POST /foundation/oauth2/token grant_type=refresh_token
    S->>G: Merk det gamle refresh-tokenet som brukt, utferd eit nytt par i same familie
    S-->>C: 201 nytt access_token og refresh_token
```

Eit gjennomarbeidd døme på klientsida av denne flyten i ein nettlesar er
OpenCDE-kjelda i [Dataspatium](https://github.com/marwiss/Dataspatium)
(`src/api/families/opencde.js`): PKCE-verifier og -challenge,
popup-vindauget til autorisasjonssida, callback-sida som rapporterer koden
tilbake, tokenutvekslinga som offentleg klient, refresh med rotasjon og
tilbaketrekking ved utlogging.

Ein brukar med eit passord nokon andre kjenner (ein ny konto eller ei tilbakestilling), får ingen kode. Serveren tek nettlesaren til kontosida for å byte det, og deretter tilbake til autorisasjonssida med det klienten bad om. Klienten merkar ikkje anna enn ei lengre ventetid.

## Kva kvar part må gjere

| Steg | Klient | Server |
|---|---|---|
| Oppdaging | Les `/foundation/1.0/auth`; hardkod aldri endepunkt | Annonser endepunkt, `oauth2_pkce_required: true` |
| Autorisasjonsførespurnad | Ny `state` og ny `code_verifier` per forsøk; `code_challenge_method=S256` | Avvis ukjende klientar og uregistrerte redirect-URI-ar *utan* å omdirigere; omdiriger andre feil med `error`, `state`, `iss` |
| Innlogging | — | Avgrens innloggingstakten; generisk feilmelding; CSRF-verna skjema; ingen passord i URL eller logg |
| Kode | Løys inn innan 60 sekund; send `code_verifier` | Koden er til eingongsbruk; eit gjenbruk trekkjer tilbake tokena han gav |
| Tokens | Lagre trygt; send berre som `Authorization: Bearer`; forny før utgang | Opake, hasha i ro; access 1 t, refresh 30 dagar, rotasjon med oppdaging av gjenbruk |
| Utlogging | `POST /foundation/oauth2/revoke` med refresh-tokenet | Slett heile tokenfamilien |

## Feil

Feil frå autorisasjonsendepunktet går tilbake til klienten som
spørjeparametrar (`error`, `error_description`, `state`, `iss`) etter RFC
6749 §4.1.2.1, med mindre klienten eller redirect-URI-en hans er problemet;
då viser serveren ei feilside og omdirigerer ikkje nokon stad. Feil frå
token-endepunktet brukar kroppen frå RFC 6749 §5.2 (`error`,
`error_description`) med OpenCDE-feltet `message` lagt til.
