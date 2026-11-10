# En offentlig https-adresse for klienttester (tunnel)

BCF- og Documents-klienter insisterer som regel på https og en vert som kan
nås. En tunnel gir den lokale stakken din en offentlig adresse uten å åpne
porter eller leie en server.

## Cloudflare Tunnel (gratis, stabilt vertsnavn på eget domene)

1. Opprett en tunnel i Cloudflare Zero Trust → Networks → Tunnels, legg til et
   offentlig vertsnavn (for eksempel `cde.example.org`) med tjenesten
   `http://api:8000`, og kopier tunnelens token.
2. I `.env`:

   ```
   OPENCDE_ENVIRONMENT=production
   OPENCDE_PUBLIC_URL=https://cde.example.org
   TUNNEL_TOKEN=<token>
   ```

   Produksjonsmodus krever https-adressen, et databasepassord og en hemmelig
   nøkkel; `opencde init --public-url https://cde.example.org` skriver dem.
3. Start:

   ```sh
   # .env: COMPOSE_FILE=docker/compose.yaml:docker/compose.tunnel.yaml
   docker compose up -d
   docker compose exec api opencde seed
   ```

Tunnelens kant terminerer TLS; serveren stoler på compose-nettverket som sin
proxy (`OPENCDE_TRUSTED_PROXIES`) og ser klientadressen i `X-Forwarded-For`.
Registrer testklientens redirect-URI i administrasjonen.

## Tailscale Funnel

Med Tailscale på maskinen publiserer `tailscale serve --bg 8000` etterfulgt av
`tailscale funnel 443 on` utviklingsstakken på
`https://<maskin>.<tailnet>.ts.net`. Sett `OPENCDE_PUBLIC_URL` til den
adressen og `OPENCDE_ENVIRONMENT=production` (eller behold `development` og
godta at serveren tror den er på http: lenkene virker likevel fordi den
offentlige adressen brukes til dem).

## ngrok (raskt, skiftende vertsnavn)

`ngrok http 8000` skriver ut en https-adresse; sett den i `OPENCDE_PUBLIC_URL`
og start API-et på nytt. Greit for en engangstest, ikke for noe som lagrer
adressen.

En nettleserklient som [Dataspatium](https://github.com/marwiss/Dataspatium)
kan bruke tunneladressen som serveradresse mens appen selv serveres fra
`http://127.0.0.1:<port>`; appens redirect-URI forblir en loopback-adresse, og
CORS tillater alle opprinnelser som standard.

## Etterpå

En tunnelert utviklingsstakk er en produksjonslignende server med demopassord.
Stopp den (`docker compose ... down`) eller roter de seedede passordene når
testen er over.
