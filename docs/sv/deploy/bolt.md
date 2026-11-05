# Publicera databasporten (Bolt) i produktion

Som standard lyssnar ingenting annat än Caddy på en produktionsvärd:
grafdatabasen ligger på det privata compose-nätet och bara servern talar med
den. Vissa klienter vill fråga IFC-grafen direkt med Cypher över Bolt, som
Dataspatiums grafvy gör mot utvecklingsstacken. Den här sidan beskriver hur en
administratör publicerar porten med avsikt, vad det kostar och hur porten
stängs igen. Alternativet som håller databasen privat är serverns
skrivskyddade graffråga för administratörer, `POST /admin/api/graph/query`
bakom `OPENCDE_GRAPH_QUERY_ENABLED` ([client-guide.md §7](../client-guide.md));
publicera porten bara när en klient behöver Bolt i sig.

## Vad en öppen port innebär

- **Full åtkomst.** Communityutgåvorna av Neo4j och Memgraph har inga
  skrivskyddade databasanvändare: den som har databasanvändaren och lösenordet
  kan läsa och skriva allt, inklusive användare, tokens och revisionsposter.
  Ge lösenordet bara till personer du skulle göra till administratörer.
- **Alltid krypterat.** Överlagringen slår på TLS för Bolt (`bolt+s://`) och
  servern vägrar att annonsera en okrypterad `bolt://`-adress i produktion.
  Webbläsarklienter som Dataspatium behöver ett certifikat som webbläsaren
  litar på, så självsignerade certifikat fungerar inte för dem.
- **Annonserad för klienter.** `OPENCDE_GRAPH_PUBLIC_BOLT_URL` publiceras i
  kapabilitetsdokumentet (`/.well-known/kontroll`, `extensions.ifcgraph.bolt`),
  där Dataspatium läser den, och visas på administrationens sida Inställningar.
  Lämna den tom medan porten är stängd.

## 1. Ett certifikat för Bolt-porten

Bolt behöver ett certifikat för värdnamnet klienterna ska använda, i
PEM-format: `certs/bolt/public.crt` (certifikatet med sin kedja) och
`certs/bolt/private.key`. Containern läser dem som användare `7474`, så de
måste vara läsbara för alla (`chmod 644`), vilket är anledningen till att de
ligger i en egen katalog.

Med produktionsöverlagringen har Caddy redan ett Let's Encrypt-certifikat för
`OPENCDE_DOMAIN`. Kopiera ut det (sökvägarna är Caddys layout):

```sh
D=cde.example.org
mkdir -p certs/bolt
docker compose -f compose.yaml -f compose.prod.yaml cp \
  "proxy:/data/caddy/certificates/acme-v02.api.letsencrypt.org-directory/$D/$D.crt" certs/bolt/public.crt
docker compose -f compose.yaml -f compose.prod.yaml cp \
  "proxy:/data/caddy/certificates/acme-v02.api.letsencrypt.org-directory/$D/$D.key" certs/bolt/private.key
chmod 644 certs/bolt/public.crt certs/bolt/private.key
```

Let's Encrypt-certifikat gäller 90 dagar och Caddy förnyar dem efter ungefär
60. Upprepa kopieringen (ett cron-jobb eller en systemd-timer en gång i
månaden) och starta om tjänsten `graph`; Neo4j läser filerna vid start.

## 2. Annonsera adressen och starta

I `.env`:

```sh
OPENCDE_GRAPH_PUBLIC_BOLT_URL=bolt+s://cde.example.org:7687
# OPENCDE_BOLT_PORT=7687          # värdporten, om 7687 är upptagen
```

Starta sedan med överlagringen tillagd i ditt vanliga kommando:

```sh
docker compose -f compose.yaml -f compose.prod.yaml -f compose.bolt.yaml up -d
```

Öppna brandväggen för porten bara mot de adresser som behöver den (ett
kontorsnät, ett VPN), aldrig mot hela världen. Kontrollera resultatet:

```sh
curl -s https://cde.example.org/.well-known/kontroll | grep -o '"bolt":"[^"]*"'
```

Dataspatiums grafvy, Neo4j Browser (`bolt+s://cde.example.org:7687`) och de
officiella drivrutinerna ansluter med databasanvändaren och lösenordet.

## 3. Stäng den igen

Ta bort `compose.bolt.yaml` från kommandoraden, töm
`OPENCDE_GRAPH_PUBLIC_BOLT_URL` i `.env` och kör `up -d` igen. Porten
försvinner från värden och `bolt` blir `null` igen i kapabilitetsdokumentet.
Rotera databaslösenordet efteråt om det delades bredare än avsett
(`docs/sv/security/controls.md`).

## Memgraph

Med `compose.memgraph.yaml` publicerar samma överlagring porten, men
TLS-inställningarna ovan är Neo4js. Lägg i stället till Memgraphs flaggor i
dess `command` (`--bolt-cert-file=/certs/bolt/public.crt
--bolt-key-file=/certs/bolt/private.key`) och montera samma katalog; Memgraph
talar då Bolt över TLS på samma port.
