# Publishing the database port (Bolt) in production

By default nothing but Caddy listens on a production host: the graph database
sits on the private compose network and only the server talks to it. Some
clients want to query the IFC graph directly with Cypher over Bolt, as
Dataspatium's graph view does against the development stack. This page is how
an administrator publishes the port on purpose, what it costs, and how to
close it again. The alternative that keeps the database private is the
server's read-only graph query for administrators,
`POST /admin/api/graph/query` behind `OPENCDE_GRAPH_QUERY_ENABLED`
([client-guide.md §7](../client-guide.md)); publish the port only when a
client needs Bolt itself.

## What an open port means

- **Full access.** The community editions of Neo4j and Memgraph have no
  read-only database users: whoever holds the database user and password can
  read and write everything, including users, tokens and audit records. Give
  the password only to people you would make administrators.
- **Encrypted, always.** The overlay turns on TLS for Bolt (`bolt+s://`) and
  the server refuses to announce a plain `bolt://` address in production.
  Browser clients such as Dataspatium need a certificate the browser trusts,
  so self-signed certificates do not work for them.
- **Announced to clients.** `OPENCDE_GRAPH_PUBLIC_BOLT_URL` is published in
  the capabilities document (`/.well-known/dataregium`,
  `extensions.ifcgraph.bolt`), where Dataspatium reads it, and shown on the
  administration's Settings page. Leave it empty while the port is closed.

## 1. A certificate for the Bolt port

Bolt needs a certificate for the host name clients will use, in PEM format:
`certs/bolt/public.crt` (the certificate, with its chain) and
`certs/bolt/private.key`. The container reads them as user `7474`, so they
must be world-readable (`chmod 644`), which is why they live in a directory
of their own.

With the production overlay, Caddy already holds a Let's Encrypt certificate
for `OPENCDE_DOMAIN`. Copy it out (the paths are Caddy's layout):

```sh
D=cde.example.org
mkdir -p certs/bolt
docker compose -f compose.yaml -f compose.prod.yaml cp \
  "proxy:/data/caddy/certificates/acme-v02.api.letsencrypt.org-directory/$D/$D.crt" certs/bolt/public.crt
docker compose -f compose.yaml -f compose.prod.yaml cp \
  "proxy:/data/caddy/certificates/acme-v02.api.letsencrypt.org-directory/$D/$D.key" certs/bolt/private.key
chmod 644 certs/bolt/public.crt certs/bolt/private.key
```

Let's Encrypt certificates last 90 days and Caddy renews them after about
60. Repeat the copy (a cron job or systemd timer once a month) and restart
the `graph` service; Neo4j reads the files at start.

## 2. Announce the address and start

In `.env`:

```sh
OPENCDE_GRAPH_PUBLIC_BOLT_URL=bolt+s://cde.example.org:7687
# OPENCDE_BOLT_PORT=7687          # the host port, if 7687 is taken
```

Then start with the overlay added to your usual command:

```sh
docker compose -f compose.yaml -f compose.prod.yaml -f compose.bolt.yaml up -d
```

Open the firewall for the port only to the addresses that need it (an office
range, a VPN), never to the world. Check the result:

```sh
curl -s https://cde.example.org/.well-known/dataregium | grep -o '"bolt":"[^"]*"'
```

Dataspatium's graph view, Neo4j Browser (`bolt+s://cde.example.org:7687`)
and the official drivers connect with the database user and password.

## 3. Close it again

Remove `compose.bolt.yaml` from the command line, clear
`OPENCDE_GRAPH_PUBLIC_BOLT_URL` in `.env`, and run `up -d` again. The port
disappears from the host and `bolt` goes back to `null` in the capabilities
document. Rotate the database password afterwards if it was shared more
widely than intended.

## Memgraph

With `compose.memgraph.yaml` the same overlay publishes the port, but the TLS
settings above are Neo4j's. Add Memgraph's flags to its `command` instead
(`--bolt-cert-file=/certs/bolt/public.crt --bolt-key-file=/certs/bolt/private.key`)
and mount the same directory; Memgraph then speaks Bolt over TLS on the same
port.
