# En publik https-adress för klienttester (tunnel)

BCF- och Documents-klienter kräver oftast https och en nåbar värd. En tunnel
ger din lokala stack en publik adress utan att du öppnar portar eller hyr en
server.

## Cloudflare Tunnel (gratis, stabilt värdnamn på egen domän)

1. Skapa en tunnel i Cloudflare Zero Trust → Networks → Tunnels, lägg till ett
   publikt värdnamn (till exempel `cde.example.org`) med tjänsten
   `http://api:8000` och kopiera tunnelns token.
2. I `.env`:

   ```
   OPENCDE_ENVIRONMENT=production
   OPENCDE_PUBLIC_URL=https://cde.example.org
   TUNNEL_TOKEN=<token>
   ```

   Produktionsläget kräver https-adressen, ett databaslösenord och en hemlig
   nyckel; `opencde init --public-url https://cde.example.org` skriver dem.
3. Starta:

   ```sh
   # .env: COMPOSE_FILE=docker/compose.yaml:docker/compose.tunnel.yaml
   docker compose up -d
   docker compose exec api opencde seed
   ```

Tunnelns kant terminerar TLS; servern litar på compose-nätet som sin proxy
(`OPENCDE_TRUSTED_PROXIES`) och ser klientadressen i `X-Forwarded-For`.
Registrera testklientens redirect-URI i administrationen.

## Tailscale Funnel

Med Tailscale på datorn publicerar `tailscale serve --bg 8000` följt av
`tailscale funnel 443 on` utvecklingsstacken på
`https://<dator>.<tailnet>.ts.net`. Sätt `OPENCDE_PUBLIC_URL` till den
adressen och `OPENCDE_ENVIRONMENT=production` (eller behåll `development` och
acceptera att servern tror sig vara på http: länkarna fungerar ändå eftersom
den publika adressen används för dem).

## ngrok (snabbt, värdnamn som byts)

`ngrok http 8000` skriver ut en https-adress; sätt den i `OPENCDE_PUBLIC_URL`
och starta om API:t. Bra för ett engångstest, inte för något som lagrar
adressen.

En webbläsarklient som [Dataspatium](https://github.com/marwiss/Dataspatium)
kan använda tunneladressen som serveradress medan appen själv serveras från
`http://127.0.0.1:<port>`; appens redirect-URI förblir en loopback-adress, och
CORS tillåter alla ursprung som standard.

## Efteråt

En tunnlad utvecklingsstack är en produktionslik server med demolösenord.
Stoppa den (`docker compose ... down`) eller rotera de seedade lösenorden när
testet är över.
