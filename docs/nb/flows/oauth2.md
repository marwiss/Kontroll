# OAuth2 authorization code-flyten med PKCE

Hvordan en klient (et BCF-tillegg, en viewer, et skript) får et access-token
på en brukers vegne. Dette er Foundation API 2.2 med herdingen fra RFC 9700 og
OAuth 2.1: PKCE `S256` for hver klient, nøyaktig matching av redirect-URI
(loopback-porter unntatt, RFC 8252), engangskoder, roterende refresh-tokens.

```mermaid
sequenceDiagram
    autonumber
    participant C as Klientapplikasjon
    participant B as Brukerens nettleser
    participant S as OpenCDE-server
    participant G as Grafdatabase

    C->>S: GET /foundation/1.0/auth
    S-->>C: oauth2_auth_url, oauth2_token_url, flyter
    Note over C: Generer code_verifier, state;<br/>code_challenge = BASE64URL(SHA256(verifier))
    C->>B: Åpne oauth2_auth_url?response_type=code&client_id&redirect_uri&state&code_challenge&code_challenge_method=S256
    B->>S: GET /foundation/oauth2/auth
    S->>G: Last klienten, sjekk at redirect_uri er registrert
    S-->>B: Innloggings- og samtykkeside (signert skjematoken)
    B->>S: POST /foundation/oauth2/auth (brukernavn, passord, beslutning)
    S->>G: Verifiser passordet (Argon2id); lagre kodens hash bundet til klient, redirect_uri, challenge
    S-->>B: 302 redirect_uri?code=…&state=…&iss=…
    B->>C: Nettleseren lander på klientens redirect-URI
    C->>S: POST /foundation/oauth2/token grant_type=authorization_code, code, code_verifier (+ klientautentisering)
    S->>G: Match kodens hash, verifiser SHA256(verifier) = challenge, merk som brukt, lagre tokenhasher
    S-->>C: 201 access_token, refresh_token, expires_in, scope (Cache-Control: no-store)
    C->>S: GET /bcf/3.0/projects  Authorization: Bearer access_token
    S->>G: Slå opp tokenhash, bruker, klient, scope
    S-->>C: 200 prosjekter
    C->>S: POST /foundation/oauth2/token grant_type=refresh_token
    S->>G: Merk det gamle refresh-tokenet som brukt, utsted et nytt par i samme familie
    S-->>C: 201 nytt access_token og refresh_token
```

Et gjennomarbeidet eksempel på klientsiden av denne flyten i en nettleser er
OpenCDE-kilden i [Dataspatium](https://github.com/marwiss/Dataspatium)
(`src/api/families/opencde.js`): PKCE-verifier og -challenge, popup-vinduet
til autorisasjonssiden, callback-siden som rapporterer koden tilbake,
tokenutvekslingen som offentlig klient, refresh med rotasjon og
tilbaketrekking ved utlogging.

En bruker med et passord noen andre kjenner (en ny konto eller en tilbakestilling), får ingen kode. Serveren tar nettleseren til kontosiden for å bytte det, og deretter tilbake til autorisasjonssiden med det klienten ba om. Klienten merker ikke annet enn en lengre ventetid.

## Hva hver part må gjøre

| Steg | Klient | Server |
|---|---|---|
| Oppdagelse | Les `/foundation/1.0/auth`; hardkod aldri endepunkter | Annonser endepunkter, `oauth2_pkce_required: true` |
| Autorisasjonsforespørsel | Ny `state` og ny `code_verifier` per forsøk; `code_challenge_method=S256` | Avvis ukjente klienter og uregistrerte redirect-URI-er *uten* å omdirigere; omdiriger andre feil med `error`, `state`, `iss` |
| Innlogging | — | Begrens innloggingstakten; generisk feilmelding; CSRF-beskyttet skjema; ingen passord i URL eller logg |
| Kode | Løs inn innen 60 sekunder; send `code_verifier` | Koden er til engangsbruk; et gjenbruk trekker tilbake tokenene den ga |
| Tokens | Lagre sikkert; send bare som `Authorization: Bearer`; forny før utløp | Opake, hashet i ro; access 1 t, refresh 30 dager, rotasjon med oppdaging av gjenbruk |
| Utlogging | `POST /foundation/oauth2/revoke` med refresh-tokenet | Slett hele tokenfamilien |

## Feil

Feil fra autorisasjonsendepunktet går tilbake til klienten som
spørreparametere (`error`, `error_description`, `state`, `iss`) etter RFC
6749 §4.1.2.1, med mindre klienten eller dens redirect-URI er problemet; da
viser serveren en feilside og omdirigerer ikke noe sted. Feil fra
token-endepunktet bruker kroppen fra RFC 6749 §5.2 (`error`,
`error_description`) med OpenCDE-feltet `message` lagt til.
