# Að birta gagnagrunnsgáttina (Bolt) í rekstri

Sjálfgefið hlustar ekkert annað en Caddy á rekstrarhýsli: grafgagnagrunnurinn
situr á lokaða compose-netinu og aðeins þjónninn talar við hann. Sumir
biðlarar vilja spyrja IFC-grafið beint með Cypher yfir Bolt, eins og grafsýn
Dataspatium gerir gegn þróunarstaflanum. Þessi síða lýsir því hvernig
stjórnandi birtir gáttina af ásettu ráði, hvað það kostar og hvernig henni er
lokað aftur. Kosturinn sem heldur gagnagrunninum lokuðum er skrifvarða
graffyrirspurn þjónsins fyrir stjórnendur, `POST /admin/api/graph/query` að
baki `OPENCDE_GRAPH_QUERY_ENABLED` ([client-guide.md §7](../client-guide.md));
birtu gáttina aðeins þegar biðlari þarf Bolt sjálft.

## Hvað opin gátt þýðir

- **Fullur aðgangur.** Community-útgáfur Neo4j og Memgraph hafa enga
  skrifvarða gagnagrunnsnotendur: sá sem hefur gagnagrunnsnotandann og
  lykilorðið getur lesið og skrifað allt, þar á meðal notendur, tóka og
  endurskoðunarfærslur. Gefðu lykilorðið aðeins fólki sem þú myndir gera að
  stjórnendum.
- **Alltaf dulkóðað.** Yfirlagið kveikir á TLS fyrir Bolt (`bolt+s://`) og
  þjónninn neitar að tilkynna ódulkóðað `bolt://`-vistfang í rekstri.
  Vafrabiðlarar eins og Dataspatium þurfa skírteini sem vafrinn treystir, svo
  sjálfundirrituð skírteini virka ekki fyrir þá.
- **Tilkynnt biðlurum.** `OPENCDE_GRAPH_PUBLIC_BOLT_URL` er birt í getuskjalinu
  (`/.well-known/dataregium`, `extensions.ifcgraph.bolt`), þar sem Dataspatium
  les hana, og sýnd á síðunni Stillingar í stjórnuninni. Láttu hana vera tóma
  meðan gáttin er lokuð.

## 1. Skírteini fyrir Bolt-gáttina

Bolt þarf skírteini fyrir hýsilheitið sem biðlarar munu nota, á PEM-sniði:
`certs/bolt/public.crt` (skírteinið með keðju sinni) og
`certs/bolt/private.key`. Gámurinn les þau sem notandi `7474`, svo þau verða
að vera lesanleg öllum (`chmod 644`), og þess vegna eru þau í eigin möppu.

Með rekstraryfirlaginu hefur Caddy þegar Let's Encrypt-skírteini fyrir
`OPENCDE_DOMAIN`. Afritaðu það út (slóðirnar eru uppsetning Caddy):

```sh
D=cde.example.org
mkdir -p certs/bolt
docker compose cp \
  "proxy:/data/caddy/certificates/acme-v02.api.letsencrypt.org-directory/$D/$D.crt" certs/bolt/public.crt
docker compose cp \
  "proxy:/data/caddy/certificates/acme-v02.api.letsencrypt.org-directory/$D/$D.key" certs/bolt/private.key
chmod 644 certs/bolt/public.crt certs/bolt/private.key
```

Let's Encrypt-skírteini gilda 90 daga og Caddy endurnýjar þau eftir um 60.
Endurtaktu afritunina (cron-verk eða systemd-tímamælir einu sinni í mánuði)
og endurræstu þjónustuna `graph`; Neo4j les skrárnar við ræsingu.

## 2. Tilkynna vistfangið og ræsa

Í `.env`:

```sh
OPENCDE_GRAPH_PUBLIC_BOLT_URL=bolt+s://cde.example.org:7687
# OPENCDE_BOLT_PORT=7687          # gátt hýsilsins, ef 7687 er upptekin
```

Ræstu síðan með yfirlaginu bætt við venjulegu skipunina þína:

```sh
# .env: COMPOSE_FILE=docker/compose.yaml:docker/compose.prod.yaml:docker/compose.bolt.yaml
docker compose up -d
```

Opnaðu eldvegginn fyrir gáttina aðeins fyrir þau vistföng sem þurfa hana
(skrifstofunet, VPN), aldrei fyrir allan heiminn. Athugaðu niðurstöðuna:

```sh
curl -s https://cde.example.org/.well-known/dataregium | grep -o '"bolt":"[^"]*"'
```

Grafsýn Dataspatium, Neo4j Browser (`bolt+s://cde.example.org:7687`) og
opinberu reklarnir tengjast með gagnagrunnsnotandanum og lykilorðinu.

## 3. Loka henni aftur

Fjarlægðu `docker/compose.bolt.yaml` úr `COMPOSE_FILE`, hreinsaðu
`OPENCDE_GRAPH_PUBLIC_BOLT_URL` í `.env` og keyrðu `up -d` aftur. Gáttin
hverfur af hýslinum og `bolt` verður aftur `null` í getuskjalinu. Skiptu um
lykilorð gagnagrunnsins eftir á ef því var deilt víðar en ætlað var.

## Memgraph

Með `docker/compose.memgraph.yaml` birtir sama yfirlagið gáttina, en
TLS-stillingarnar hér að ofan eru Neo4j. Bættu í staðinn flöggum Memgraph við
`command` þess (`--bolt-cert-file=/certs/bolt/public.crt
--bolt-key-file=/certs/bolt/private.key`) og tengdu sömu möppuna; Memgraph
talar þá Bolt yfir TLS á sömu gáttinni.
