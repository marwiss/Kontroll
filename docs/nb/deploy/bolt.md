# Publisere databaseporten (Bolt) i produksjon

Som standard lytter ingenting annet enn Caddy på en produksjonsvert:
grafdatabasen ligger på det private compose-nettverket, og bare serveren
snakker med den. Noen klienter vil spørre IFC-grafen direkte med Cypher over
Bolt, slik Dataspatiums grafvisning gjør mot utviklingsstakken. Denne siden
beskriver hvordan en administrator publiserer porten med hensikt, hva det
koster, og hvordan den lukkes igjen. Alternativet som holder databasen privat,
er serverens skrivebeskyttede grafspørring for administratorer,
`POST /admin/api/graph/query` bak `OPENCDE_GRAPH_QUERY_ENABLED`
([client-guide.md §7](../client-guide.md)); publiser porten bare når en
klient trenger selve Bolt.

## Hva en åpen port betyr

- **Full tilgang.** Community-utgavene av Neo4j og Memgraph har ingen
  skrivebeskyttede databasebrukere: den som har databasebrukeren og passordet,
  kan lese og skrive alt, inkludert brukere, tokens og revisjonsposter. Gi
  passordet bare til personer du ville gjort til administratorer.
- **Alltid kryptert.** Overlegget slår på TLS for Bolt (`bolt+s://`), og
  serveren nekter å annonsere en ukryptert `bolt://`-adresse i produksjon.
  Nettleserklienter som Dataspatium trenger et sertifikat nettleseren stoler
  på, så selvsignerte sertifikater virker ikke for dem.
- **Annonsert til klienter.** `OPENCDE_GRAPH_PUBLIC_BOLT_URL` publiseres i
  kapabilitetsdokumentet (`/.well-known/dataregium`, `extensions.ifcgraph.bolt`),
  der Dataspatium leser den, og vises på administrasjonens side Innstillinger.
  La den stå tom mens porten er lukket.

## 1. Et sertifikat for Bolt-porten

Bolt trenger et sertifikat for vertsnavnet klientene skal bruke, i PEM-format:
`certs/bolt/public.crt` (sertifikatet med kjeden sin) og
`certs/bolt/private.key`. Containeren leser dem som bruker `7474`, så de må
kunne leses av alle (`chmod 644`), og derfor ligger de i en egen mappe.

Med produksjonsoverlegget har Caddy allerede et Let's Encrypt-sertifikat for
`OPENCDE_DOMAIN`. Kopier det ut (stiene er Caddys oppsett):

```sh
D=cde.example.org
mkdir -p certs/bolt
docker compose cp \
  "proxy:/data/caddy/certificates/acme-v02.api.letsencrypt.org-directory/$D/$D.crt" certs/bolt/public.crt
docker compose cp \
  "proxy:/data/caddy/certificates/acme-v02.api.letsencrypt.org-directory/$D/$D.key" certs/bolt/private.key
chmod 644 certs/bolt/public.crt certs/bolt/private.key
```

Let's Encrypt-sertifikater varer 90 dager, og Caddy fornyer dem etter omtrent
60. Gjenta kopieringen (en cron-jobb eller en systemd-timer én gang i måneden)
og start tjenesten `graph` på nytt; Neo4j leser filene ved start.

## 2. Annonser adressen og start

I `.env`:

```sh
OPENCDE_GRAPH_PUBLIC_BOLT_URL=bolt+s://cde.example.org:7687
# OPENCDE_BOLT_PORT=7687          # vertsporten, hvis 7687 er opptatt
```

Start deretter med overlegget lagt til den vanlige kommandoen din:

```sh
# .env: COMPOSE_FILE=docker/compose.yaml:docker/compose.prod.yaml:docker/compose.bolt.yaml
docker compose up -d
```

Åpne brannmuren for porten bare mot adressene som trenger den (et
kontornettverk, en VPN), aldri mot hele verden. Sjekk resultatet:

```sh
curl -s https://cde.example.org/.well-known/dataregium | grep -o '"bolt":"[^"]*"'
```

Dataspatiums grafvisning, Neo4j Browser (`bolt+s://cde.example.org:7687`) og
de offisielle driverne kobler til med databasebrukeren og passordet.

## 3. Lukk den igjen

Fjern `docker/compose.bolt.yaml` fra `COMPOSE_FILE`, tøm
`OPENCDE_GRAPH_PUBLIC_BOLT_URL` i `.env`, og kjør `up -d` igjen. Porten
forsvinner fra verten, og `bolt` går tilbake til `null` i
kapabilitetsdokumentet. Roter databasepassordet etterpå hvis det ble delt
bredere enn tiltenkt.

## Memgraph

Med `docker/compose.memgraph.yaml` publiserer det samme overlegget porten, men
TLS-innstillingene over er Neo4js. Legg i stedet Memgraphs flagg til dens
`command` (`--bolt-cert-file=/certs/bolt/public.crt
--bolt-key-file=/certs/bolt/private.key`) og monter den samme mappen; Memgraph
snakker da Bolt over TLS på den samme porten.
