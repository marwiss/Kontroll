# OAuth2 authorization code flow with PKCE

How a client (a BCF plugin, a viewer, a script) obtains an access token on a
user's behalf. This is Foundation API 2.2 with the hardening of RFC 9700 and
OAuth 2.1: PKCE `S256` for every client, exact redirect URI matching (loopback
ports excepted, RFC 8252), one-time codes, rotating refresh tokens. The exception is a confidential client an administrator has
marked because it cannot use PKCE, such as one that implements only BCF API 2.1; see
the [client guide](../client-guide.md).

```mermaid
sequenceDiagram
    autonumber
    participant C as Client application
    participant B as User's browser
    participant S as OpenCDE server
    participant G as Graph database

    C->>S: GET /foundation/1.0/auth
    S-->>C: oauth2_auth_url, oauth2_token_url, flows
    Note over C: Generate code_verifier, state;<br/>code_challenge = BASE64URL(SHA256(verifier))
    C->>B: Open oauth2_auth_url?response_type=code&client_id&redirect_uri&state&code_challenge&code_challenge_method=S256
    B->>S: GET /foundation/oauth2/auth
    S->>G: Load client, check redirect_uri is registered
    S-->>B: Sign-in and consent page (signed form token)
    B->>S: POST /foundation/oauth2/auth (user name, password, decision)
    S->>G: Verify password (Argon2id); store code hash bound to client, redirect_uri, challenge
    S-->>B: 302 redirect_uri?code=…&state=…&iss=…
    B->>C: Browser lands on the client's redirect URI
    C->>S: POST /foundation/oauth2/token grant_type=authorization_code, code, code_verifier (+ client auth)
    S->>G: Match code hash, verify SHA256(verifier) = challenge, mark spent, store token hashes
    S-->>C: 201 access_token, refresh_token, expires_in, scope (Cache-Control: no-store)
    C->>S: GET /bcf/3.0/projects  Authorization: Bearer access_token
    S->>G: Look up token hash, user, client, scope
    S-->>C: 200 projects
    C->>S: POST /foundation/oauth2/token grant_type=refresh_token
    S->>G: Mark old refresh token spent, issue a new pair in the same family
    S-->>C: 201 new access_token and refresh_token
```

A worked example of the client side of this flow in a browser is the OpenCDE
source of [Dataspatium](https://github.com/marwiss/Dataspatium)
(`src/api/families/opencde.js`): PKCE verifier and challenge, the popup to the
authorization page, the callback page that reports the code back, the token
exchange as a public client, refresh with rotation and revocation at sign-out.

A user with a password someone else knows (a new account, or a reset) gets no code. The server takes the browser to the account page to change it, and then back to the authorization page with what the client asked for. The client notices nothing but a longer wait.

## What each party must do

| Step | Client | Server |
|---|---|---|
| Discovery | Read `/foundation/1.0/auth`; never hard-code endpoints | Advertise endpoints, `oauth2_pkce_required: true` |
| Authorization request | Fresh `state` and `code_verifier` per attempt; `code_challenge_method=S256` | Refuse unknown clients and unregistered redirect URIs *without* redirecting; redirect other errors with `error`, `state`, `iss` |
| Sign-in | — | Rate-limit sign-ins; generic error message; CSRF-protected form; no password in URL or log |
| Code | Exchange within 60 seconds; send `code_verifier` | Code is single-use; a replay revokes the tokens it produced |
| Tokens | Store securely; send only as `Authorization: Bearer`; refresh before expiry | Opaque, hashed at rest; access 1 h, refresh 30 days, rotation with reuse detection |
| Sign-out | `POST /foundation/oauth2/revoke` with the refresh token | Delete the whole token family |

## Errors

Authorization endpoint errors go back to the client as query parameters
(`error`, `error_description`, `state`, `iss`) per RFC 6749 §4.1.2.1, unless
the client or its redirect URI is the problem, in which case the server shows
an error page and does not redirect anywhere. Token endpoint errors use the
RFC 6749 §5.2 body (`error`, `error_description`) with the OpenCDE `message`
field added.
