# OAuth2 authorization code -kulku PKCE:n kanssa

Miten asiakas (BCF-lisäosa, katselin, skripti) saa access-tokenin käyttäjän
puolesta. Tämä on Foundation API 2.2 RFC 9700:n ja OAuth 2.1:n kovennuksin:
PKCE `S256` jokaiselle asiakkaalle, redirect-URIn tarkka vastaavuus
(loopback-portteja lukuun ottamatta, RFC 8252), kertakäyttöiset koodit,
kiertävät refresh-tokenit.

```mermaid
sequenceDiagram
    autonumber
    participant C as Asiakassovellus
    participant B as Käyttäjän selain
    participant S as OpenCDE-palvelin
    participant G as Graafitietokanta

    C->>S: GET /foundation/1.0/auth
    S-->>C: oauth2_auth_url, oauth2_token_url, kulut
    Note over C: Luo code_verifier, state;<br/>code_challenge = BASE64URL(SHA256(verifier))
    C->>B: Avaa oauth2_auth_url?response_type=code&client_id&redirect_uri&state&code_challenge&code_challenge_method=S256
    B->>S: GET /foundation/oauth2/auth
    S->>G: Lataa asiakas, tarkista että redirect_uri on rekisteröity
    S-->>B: Kirjautumis- ja suostumussivu (allekirjoitettu lomaketoken)
    B->>S: POST /foundation/oauth2/auth (käyttäjätunnus, salasana, päätös)
    S->>G: Tarkista salasana (Argon2id); tallenna koodin tiiviste sidottuna asiakkaaseen, redirect_uri:in, challengeen
    S-->>B: 302 redirect_uri?code=…&state=…&iss=…
    B->>C: Selain päätyy asiakkaan redirect-URIin
    C->>S: POST /foundation/oauth2/token grant_type=authorization_code, code, code_verifier (+ asiakkaan todennus)
    S->>G: Täsmää koodin tiiviste, tarkista SHA256(verifier) = challenge, merkitse käytetyksi, tallenna tokenien tiivisteet
    S-->>C: 201 access_token, refresh_token, expires_in, scope (Cache-Control: no-store)
    C->>S: GET /bcf/3.0/projects  Authorization: Bearer access_token
    S->>G: Hae tokenin tiiviste, käyttäjä, asiakas, scope
    S-->>C: 200 projektit
    C->>S: POST /foundation/oauth2/token grant_type=refresh_token
    S->>G: Merkitse vanha refresh-token käytetyksi, myönnä uusi pari samaan perheeseen
    S-->>C: 201 uusi access_token ja refresh_token
```

Työstetty esimerkki tämän kulun asiakaspuolesta selaimessa on
[Dataspatiumin](https://github.com/marwiss/Dataspatium) OpenCDE-lähde
(`src/api/families/opencde.js`): PKCE-verifier ja -challenge, ponnahdusikkuna
valtuutussivulle, callback-sivu, joka raportoi koodin takaisin, tokenien
vaihto julkisena asiakkaana, kiertävä refresh ja peruutus uloskirjautuessa.

## Mitä kunkin osapuolen on tehtävä

| Vaihe | Asiakas | Palvelin |
|---|---|---|
| Löytäminen | Lue `/foundation/1.0/auth`; älä koskaan kovakoodaa päätepisteitä | Ilmoita päätepisteet, `oauth2_pkce_required: true` |
| Valtuutuspyyntö | Uusi `state` ja `code_verifier` jokaiselle yritykselle; `code_challenge_method=S256` | Hylkää tuntemattomat asiakkaat ja rekisteröimättömät redirect-URIt *ilman* uudelleenohjausta; ohjaa muut virheet parametrein `error`, `state`, `iss` |
| Kirjautuminen | — | Rajoita kirjautumisten tahtia; yleinen virheilmoitus; CSRF-suojattu lomake; ei salasanaa URLissa tai lokissa |
| Koodi | Lunasta 60 sekunnin sisällä; lähetä `code_verifier` | Koodi on kertakäyttöinen; uudelleenkäyttö peruu sen tuottamat tokenit |
| Tokenit | Säilytä turvallisesti; lähetä vain `Authorization: Bearer`-otsakkeena; uusi ennen vanhenemista | Opaakit, tiivistetyt levossa; access 1 h, refresh 30 päivää, kierto ja uudelleenkäytön tunnistus |
| Uloskirjautuminen | `POST /foundation/oauth2/revoke` refresh-tokenilla | Poista koko tokenperhe |

## Virheet

Valtuutuspäätepisteen virheet palaavat asiakkaalle kyselyparametreina
(`error`, `error_description`, `state`, `iss`) RFC 6749 §4.1.2.1:n mukaan,
paitsi kun ongelma on asiakas tai sen redirect-URI; silloin palvelin näyttää
virhesivun eikä ohjaa minnekään. Token-päätepisteen virheet käyttävät RFC
6749 §5.2:n runkoa (`error`, `error_description`), johon on lisätty OpenCDE:n
`message`-kenttä.
