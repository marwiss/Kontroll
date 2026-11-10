# Publisere databaseporten (Bolt) i produksjon

Som standard lyttar ingenting anna enn Caddy på ein produksjonsvert:
grafdatabasen ligg på det private compose-nettverket, og berre serveren
snakkar med han. Nokre klientar vil spørje IFC-grafen direkte med Cypher over
Bolt, slik grafvisinga i Dataspatium gjer mot utviklingsstakken. Denne sida
fortel korleis ein administrator publiserer porten med hensikt, kva det
kostar, og korleis han blir lukka igjen. Alternativet som held databasen
privat, er den skriveverna grafspørjinga i serveren for administratorar,
`POST /admin/api/graph/query` bak `OPENCDE_GRAPH_QUERY_ENABLED`
([client-guide.md §7](../client-guide.md)); publiser porten berre når ein
klient treng sjølve Bolt.

## Kva ein open port tyder

- **Full tilgang.** Community-utgåvene av Neo4j og Memgraph har ingen
  skriveverna databasebrukarar: den som har databasebrukaren og passordet, kan
  lese og skrive alt, inkludert brukarar, tokens og revisjonspostar. Gje
  passordet berre til personar du ville gjort til administratorar.
- **Alltid kryptert.** Overlegget slår på TLS for Bolt (`bolt+s://`), og
  serveren nektar å annonsere ei ukryptert `bolt://`-adresse i produksjon.
  Nettlesarklientar som Dataspatium treng eit sertifikat nettlesaren stolar
  på, så sjølvsignerte sertifikat verkar ikkje for dei.
- **Annonsert til klientar.** `OPENCDE_GRAPH_PUBLIC_BOLT_URL` blir publisert i
  kapabilitetsdokumentet (`/.well-known/dataregium`, `extensions.ifcgraph.bolt`),
  der Dataspatium les han, og vist på sida Innstillingar i administrasjonen.
  Lat han stå tom medan porten er lukka.

## 1. Eit sertifikat for Bolt-porten

Bolt treng eit sertifikat for vertsnamnet klientane skal bruke, i PEM-format:
`certs/bolt/public.crt` (sertifikatet med kjeda si) og
`certs/bolt/private.key`. Containeren les dei som brukar `7474`, så dei må
kunne lesast av alle (`chmod 644`), og difor ligg dei i ei eiga mappe.

Med produksjonsoverlegget har Caddy alt eit Let's Encrypt-sertifikat for
`OPENCDE_DOMAIN`. Kopier det ut (stigane er oppsettet til Caddy):

```sh
D=cde.example.org
mkdir -p certs/bolt
docker compose -f compose.yaml -f compose.prod.yaml cp \
  "proxy:/data/caddy/certificates/acme-v02.api.letsencrypt.org-directory/$D/$D.crt" certs/bolt/public.crt
docker compose -f compose.yaml -f compose.prod.yaml cp \
  "proxy:/data/caddy/certificates/acme-v02.api.letsencrypt.org-directory/$D/$D.key" certs/bolt/private.key
chmod 644 certs/bolt/public.crt certs/bolt/private.key
```

Let's Encrypt-sertifikat varer 90 dagar, og Caddy fornyar dei etter om lag 60.
Gjenta kopieringa (ein cron-jobb eller ein systemd-timer éin gong i månaden)
og start tenesta `graph` på nytt; Neo4j les filene ved start.

## 2. Annonser adressa og start

I `.env`:

```sh
OPENCDE_GRAPH_PUBLIC_BOLT_URL=bolt+s://cde.example.org:7687
# OPENCDE_BOLT_PORT=7687          # vertsporten, om 7687 er oppteken
```

Start deretter med overlegget lagt til den vanlege kommandoen din:

```sh
docker compose -f compose.yaml -f compose.prod.yaml -f compose.bolt.yaml up -d
```

Opne brannmuren for porten berre mot adressene som treng han (eit
kontornettverk, ein VPN), aldri mot heile verda. Sjekk resultatet:

```sh
curl -s https://cde.example.org/.well-known/dataregium | grep -o '"bolt":"[^"]*"'
```

Grafvisinga i Dataspatium, Neo4j Browser (`bolt+s://cde.example.org:7687`) og
dei offisielle drivarane koplar til med databasebrukaren og passordet.

## 3. Lukk han igjen

Fjern `compose.bolt.yaml` frå kommandolinja, tøm
`OPENCDE_GRAPH_PUBLIC_BOLT_URL` i `.env`, og køyr `up -d` igjen. Porten
forsvinn frå verten, og `bolt` går tilbake til `null` i kapabilitetsdokumentet.
Roter databasepassordet etterpå om det vart delt breiare enn tenkt.

## Memgraph

Med `compose.memgraph.yaml` publiserer det same overlegget porten, men
TLS-innstillingane over er Neo4j sine. Legg i staden flagga til Memgraph til
`command` (`--bolt-cert-file=/certs/bolt/public.crt
--bolt-key-file=/certs/bolt/private.key`) og monter den same mappa; Memgraph
snakkar då Bolt over TLS på den same porten.
