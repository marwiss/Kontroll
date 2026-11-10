# A public https URL for client tests (tunnel)

BCF and Documents clients usually insist on https and a reachable host. A
tunnel gives your local stack a public URL without opening ports or renting a
server.

## Cloudflare Tunnel (free, stable hostname on your own domain)

1. In Cloudflare Zero Trust → Networks → Tunnels, create a tunnel, add a
   public hostname (for example `cde.example.org`) with service
   `http://api:8000`, and copy the tunnel token.
2. In `.env`:

   ```
   OPENCDE_ENVIRONMENT=production
   OPENCDE_PUBLIC_URL=https://cde.example.org
   TUNNEL_TOKEN=<the token>
   ```

   Production mode requires the https URL, a database password and a secret key;
   `opencde init --public-url https://cde.example.org` writes them.
3. Start:

   ```sh
   # .env: COMPOSE_FILE=docker/compose.yaml:docker/compose.tunnel.yaml
   docker compose up -d
   docker compose exec api opencde seed
   ```

The tunnel's edge terminates TLS; the server trusts the compose network as its
proxy (`OPENCDE_TRUSTED_PROXIES`) and sees the client address in
`X-Forwarded-For`. Register your test client's redirect URI in the admin UI.

## Tailscale Funnel

With Tailscale on the machine: `tailscale serve --bg 8000` followed by
`tailscale funnel 443 on` publishes the development stack at
`https://<machine>.<tailnet>.ts.net`. Set `OPENCDE_PUBLIC_URL` to that URL and
`OPENCDE_ENVIRONMENT=production` (or keep `development` and accept that the
server believes it is on http: links still work because the public URL is used
for them).

## ngrok (quick, changing hostname)

`ngrok http 8000` prints an https URL; put it in `OPENCDE_PUBLIC_URL` and restart
the API. Fine for a one-off test, not for anything that stores the URL.

A browser client such as [Dataspatium](https://github.com/marwiss/Dataspatium)
can use the tunnel URL as its server address while the app itself is served
from `http://127.0.0.1:<port>`; the app's redirect URI stays a loopback
address, and CORS allows every origin by default.

## Afterwards

A tunnelled development stack is a production-like server with demo passwords.
Stop it (`docker compose ... down`) or rotate the seeded passwords when the test
is over.
