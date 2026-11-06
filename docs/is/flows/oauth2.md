# OAuth2 authorization code-ferlið með PKCE

Hvernig biðlari (BCF-viðbót, skoðari, skrifta) fær aðgangstóka fyrir hönd
notanda. Þetta er Foundation API 2.2 með herðingu RFC 9700 og OAuth 2.1:
PKCE `S256` fyrir hvern biðlara, nákvæm samsvörun redirect-URI
(loopback-gáttir undanskildar, RFC 8252), einnota kóðar, endurnýjunartókar
sem skiptast.

```mermaid
sequenceDiagram
    autonumber
    participant C as Biðlaraforrit
    participant B as Vafri notandans
    participant S as OpenCDE-þjónn
    participant G as Grafgagnagrunnur

    C->>S: GET /foundation/1.0/auth
    S-->>C: oauth2_auth_url, oauth2_token_url, ferli
    Note over C: Búa til code_verifier, state;<br/>code_challenge = BASE64URL(SHA256(verifier))
    C->>B: Opna oauth2_auth_url?response_type=code&client_id&redirect_uri&state&code_challenge&code_challenge_method=S256
    B->>S: GET /foundation/oauth2/auth
    S->>G: Hlaða biðlara, athuga að redirect_uri sé skráð
    S-->>B: Innskráningar- og samþykkissíða (undirritaður eyðublaðstóki)
    B->>S: POST /foundation/oauth2/auth (notandanafn, lykilorð, ákvörðun)
    S->>G: Sannreyna lykilorð (Argon2id); geyma tætigildi kóðans bundið við biðlara, redirect_uri, challenge
    S-->>B: 302 redirect_uri?code=…&state=…&iss=…
    B->>C: Vafrinn lendir á redirect-URI biðlarans
    C->>S: POST /foundation/oauth2/token grant_type=authorization_code, code, code_verifier (+ auðkenning biðlara)
    S->>G: Para tætigildi kóðans, sannreyna SHA256(verifier) = challenge, merkja notaðan, geyma tætigildi tóka
    S-->>C: 201 access_token, refresh_token, expires_in, scope (Cache-Control: no-store)
    C->>S: GET /bcf/3.0/projects  Authorization: Bearer access_token
    S->>G: Fletta upp tætigildi tóka, notanda, biðlara, scope
    S-->>C: 200 verkefni
    C->>S: POST /foundation/oauth2/token grant_type=refresh_token
    S->>G: Merkja gamla endurnýjunartókann notaðan, gefa út nýtt par í sömu fjölskyldu
    S-->>C: 201 nýr access_token og refresh_token
```

Útfært dæmi um biðlarahlið þessa ferlis í vafra er OpenCDE-uppruni
[Dataspatium](https://github.com/marwiss/Dataspatium)
(`src/api/families/opencde.js`): PKCE-verifier og -challenge, sprettiglugginn
á heimildarsíðuna, callback-síðan sem skilar kóðanum til baka, tókaskiptin
sem opinber biðlari, endurnýjun með skiptum og afturköllun við útskráningu.

Notandi með lykilorð sem einhver annar þekkir (nýr reikningur eða endurstilling) fær engan kóða. Þjónninn fer með vafrann á reikningssíðuna til að skipta um það og síðan aftur á heimildarsíðuna með því sem biðlarinn bað um. Biðlarinn verður ekki var við annað en lengri bið.

## Hvað hver aðili þarf að gera

| Skref | Biðlari | Þjónn |
|---|---|---|
| Uppgötvun | Lesa `/foundation/1.0/auth`; aldrei harðkóða endapunkta | Auglýsa endapunkta, `oauth2_pkce_required: true` |
| Heimildarbeiðni | Nýtt `state` og `code_verifier` í hverri tilraun; `code_challenge_method=S256` | Hafna óþekktum biðlurum og óskráðum redirect-URI *án* þess að áframsenda; áframsenda aðrar villur með `error`, `state`, `iss` |
| Innskráning | — | Takmarka tíðni innskráninga; almenn villuboð; CSRF-varið eyðublað; ekkert lykilorð í URL eða atvikaskrá |
| Kóði | Innleysa innan 60 sekúndna; senda `code_verifier` | Kóðinn er einnota; endurnotkun afturkallar tókana sem hann gaf |
| Tókar | Geyma á öruggan hátt; senda aðeins sem `Authorization: Bearer`; endurnýja áður en rennur út | Ógegnsæir, tættir í hvíld; aðgangur 1 klst., endurnýjun 30 dagar, skipti með greiningu endurnotkunar |
| Útskráning | `POST /foundation/oauth2/revoke` með endurnýjunartókanum | Eyða allri tókafjölskyldunni |

## Villur

Villur frá heimildarendapunktinum fara aftur til biðlarans sem
fyrirspurnarstikar (`error`, `error_description`, `state`, `iss`) samkvæmt
RFC 6749 §4.1.2.1, nema biðlarinn eða redirect-URI hans sé vandinn; þá sýnir
þjónninn villusíðu og áframsendir ekki neitt. Villur frá tókaendapunktinum
nota meginmál RFC 6749 §5.2 (`error`, `error_description`) með
OpenCDE-sviðinu `message` bætt við.
