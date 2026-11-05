# En offentlig https-adresse til klienttest (tunnel)

BCF- og Documents-klienter insisterer som regel på https og en vært, der kan
nås. En tunnel giver din lokale stak en offentlig adresse uden at åbne porte
eller leje en server.

## Cloudflare Tunnel (gratis, stabilt værtsnavn på dit eget domæne)

1. Opret en tunnel i Cloudflare Zero Trust → Networks → Tunnels, tilføj et
   offentligt værtsnavn (for eksempel `cde.example.org`) med tjenesten
   `http://api:8000`, og kopiér tunnelens token.
2. I `.env`:

   ```
   OPENCDE_ENVIRONMENT=production
   OPENCDE_PUBLIC_URL=https://cde.example.org
   TUNNEL_TOKEN=<token>
   ```

   Produktionstilstanden kræver https-adressen, en databaseadgangskode og en
   hemmelig nøgle; `opencde init --public-url https://cde.example.org` skriver
   dem.
3. Start:

   ```sh
   docker compose -f compose.yaml -f compose.tunnel.yaml up -d
   docker compose -f compose.yaml -f compose.tunnel.yaml exec api opencde seed
   ```

Tunnelens kant terminerer TLS; serveren stoler på compose-netværket som sin
proxy (`OPENCDE_TRUSTED_PROXIES`) og ser klientadressen i `X-Forwarded-For`.
Registrér din testklients redirect-URI i administrationen.

## Tailscale Funnel

Med Tailscale på maskinen udgiver `tailscale serve --bg 8000` efterfulgt af
`tailscale funnel 443 on` udviklingsstakken på
`https://<maskine>.<tailnet>.ts.net`. Sæt `OPENCDE_PUBLIC_URL` til den adresse
og `OPENCDE_ENVIRONMENT=production` (eller behold `development`, og acceptér,
at serveren tror, den er på http: links virker stadig, fordi den offentlige
adresse bruges til dem).

## ngrok (hurtigt, skiftende værtsnavn)

`ngrok http 8000` udskriver en https-adresse; sæt den i `OPENCDE_PUBLIC_URL`,
og genstart API'et. Fint til en enkelt test, ikke til noget, der gemmer
adressen.

En browserklient som [Dataspatium](https://github.com/marwiss/Dataspatium)
kan bruge tunneladressen som sin serveradresse, mens appen selv serveres fra
`http://127.0.0.1:<port>`; appens redirect-URI forbliver en loopback-adresse,
og CORS tillader alle oprindelser som standard.

## Bagefter

En tunnelført udviklingsstak er en produktionslignende server med
demoadgangskoder. Stop den (`docker compose ... down`), eller rotér de seedede
adgangskoder, når testen er slut.
