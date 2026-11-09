# Udgivelse af databaseporten (Bolt) i produktion

Som standard lytter intet andet end Caddy på en produktionsvært:
grafdatabasen ligger på det private compose-netværk, og kun serveren taler med
den. Nogle klienter vil spørge IFC-grafen direkte med Cypher over Bolt, som
Dataspatiums grafvisning gør mod udviklingsstakken. Denne side beskriver,
hvordan en administrator udgiver porten med vilje, hvad det koster, og hvordan
den lukkes igen. Alternativet, der holder databasen privat, er serverens
skrivebeskyttede grafforespørgsel for administratorer,
`POST /admin/api/graph/query` bag `OPENCDE_GRAPH_QUERY_ENABLED`
([client-guide.md §7](../client-guide.md)); udgiv kun porten, når en klient
har brug for selve Bolt.

## Hvad en åben port betyder

- **Fuld adgang.** Community-udgaverne af Neo4j og Memgraph har ingen
  skrivebeskyttede databasebrugere: den, der har databasebrugeren og
  kodeordet, kan læse og skrive alt, herunder brugere, tokens og
  revisionsposter. Giv kun kodeordet til personer, du ville gøre til
  administratorer.
- **Altid krypteret.** Overlejringen slår TLS til for Bolt (`bolt+s://`), og
  serveren afviser at annoncere en ukrypteret `bolt://`-adresse i produktion.
  Browserklienter som Dataspatium har brug for et certifikat, browseren stoler
  på, så selvsignerede certifikater virker ikke for dem.
- **Annonceret til klienter.** `OPENCDE_GRAPH_PUBLIC_BOLT_URL` udgives i
  kapabilitetsdokumentet (`/.well-known/dataregium`, `extensions.ifcgraph.bolt`),
  hvor Dataspatium læser den, og vises på administrationens side
  Indstillinger. Lad den være tom, mens porten er lukket.

## 1. Et certifikat til Bolt-porten

Bolt har brug for et certifikat til det værtsnavn, klienterne skal bruge, i
PEM-format: `certs/bolt/public.crt` (certifikatet med sin kæde) og
`certs/bolt/private.key`. Containeren læser dem som bruger `7474`, så de skal
kunne læses af alle (`chmod 644`), og derfor ligger de i deres egen mappe.

Med produktionsoverlejringen har Caddy allerede et Let's Encrypt-certifikat
til `OPENCDE_DOMAIN`. Kopiér det ud (stierne er Caddys layout):

```sh
D=cde.example.org
mkdir -p certs/bolt
docker compose -f compose.yaml -f compose.prod.yaml cp \
  "proxy:/data/caddy/certificates/acme-v02.api.letsencrypt.org-directory/$D/$D.crt" certs/bolt/public.crt
docker compose -f compose.yaml -f compose.prod.yaml cp \
  "proxy:/data/caddy/certificates/acme-v02.api.letsencrypt.org-directory/$D/$D.key" certs/bolt/private.key
chmod 644 certs/bolt/public.crt certs/bolt/private.key
```

Let's Encrypt-certifikater gælder 90 dage, og Caddy fornyer dem efter cirka
60. Gentag kopieringen (et cron-job eller en systemd-timer én gang om
måneden), og genstart tjenesten `graph`; Neo4j læser filerne ved start.

## 2. Annoncér adressen, og start

I `.env`:

```sh
OPENCDE_GRAPH_PUBLIC_BOLT_URL=bolt+s://cde.example.org:7687
# OPENCDE_BOLT_PORT=7687          # værtsporten, hvis 7687 er optaget
```

Start derefter med overlejringen tilføjet til din sædvanlige kommando:

```sh
docker compose -f compose.yaml -f compose.prod.yaml -f compose.bolt.yaml up -d
```

Åbn kun firewallen for porten mod de adresser, der har brug for den (et
kontornetværk, en VPN), aldrig mod hele verden. Tjek resultatet:

```sh
curl -s https://cde.example.org/.well-known/dataregium | grep -o '"bolt":"[^"]*"'
```

Dataspatiums grafvisning, Neo4j Browser (`bolt+s://cde.example.org:7687`) og de
officielle drivere forbinder med databasebrugeren og kodeordet.

## 3. Luk den igen

Fjern `compose.bolt.yaml` fra kommandolinjen, ryd
`OPENCDE_GRAPH_PUBLIC_BOLT_URL` i `.env`, og kør `up -d` igen. Porten
forsvinder fra værten, og `bolt` bliver igen `null` i kapabilitetsdokumentet.
Rotér databasekodeordet bagefter, hvis det blev delt bredere end tiltænkt
(`docs/da/security/controls.md`).

## Memgraph

Med `compose.memgraph.yaml` udgiver den samme overlejring porten, men
TLS-indstillingerne ovenfor er Neo4js. Tilføj i stedet Memgraphs flag til dens
`command` (`--bolt-cert-file=/certs/bolt/public.crt
--bolt-key-file=/certs/bolt/private.key`), og montér den samme mappe; Memgraph
taler så Bolt over TLS på den samme port.
