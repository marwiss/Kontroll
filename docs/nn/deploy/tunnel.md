# Ei offentleg https-adresse for klienttestar (tunnel)

BCF- og Documents-klientar insisterer som regel på https og ein vert som kan
nåast. Ein tunnel gjev den lokale stakken din ei offentleg adresse utan å opne
portar eller leige ein server.

## Cloudflare Tunnel (gratis, stabilt vertsnamn på eige domene)

1. Opprett ein tunnel i Cloudflare Zero Trust → Networks → Tunnels, legg til
   eit offentleg vertsnamn (til dømes `cde.example.org`) med tenesta
   `http://api:8000`, og kopier tokenet til tunnelen.
2. I `.env`:

   ```
   OPENCDE_ENVIRONMENT=production
   OPENCDE_PUBLIC_URL=https://cde.example.org
   TUNNEL_TOKEN=<token>
   ```

   Produksjonsmodus krev https-adressa, eit databasepassord og ein løynd
   nøkkel; `opencde init --public-url https://cde.example.org` skriv dei.
3. Start:

   ```sh
   docker compose -f compose.yaml -f compose.tunnel.yaml up -d
   docker compose -f compose.yaml -f compose.tunnel.yaml exec api opencde seed
   ```

Kanten til tunnelen terminerer TLS; serveren stolar på compose-nettverket som
sin proxy (`OPENCDE_TRUSTED_PROXIES`) og ser klientadressa i
`X-Forwarded-For`. Registrer redirect-URI-en til testklienten i
administrasjonen.

## Tailscale Funnel

Med Tailscale på maskina publiserer `tailscale serve --bg 8000` etterfølgt av
`tailscale funnel 443 on` utviklingsstakken på
`https://<maskin>.<tailnet>.ts.net`. Set `OPENCDE_PUBLIC_URL` til den adressa
og `OPENCDE_ENVIRONMENT=production` (eller hald på `development` og godta at
serveren trur han er på http: lenkjene verkar likevel fordi den offentlege
adressa vert brukt til dei).

## ngrok (raskt, skiftande vertsnamn)

`ngrok http 8000` skriv ut ei https-adresse; set henne i `OPENCDE_PUBLIC_URL`
og start API-et på nytt. Greitt for ein eingongstest, ikkje for noko som lagrar
adressa.

Ein nettlesarklient som [Dataspatium](https://github.com/marwiss/Dataspatium)
kan bruke tunneladressa som serveradresse medan appen sjølv vert servert frå
`http://127.0.0.1:<port>`; redirect-URI-en til appen held fram å vere ei
loopback-adresse, og CORS tillèt alle opphav som standard.

## Etterpå

Ein tunnelert utviklingsstakk er ein produksjonsliknande server med
demopassord. Stopp han (`docker compose ... down`) eller roter dei seeda
passorda når testen er over.
