# Tietokantaportin (Bolt) julkaiseminen tuotannossa

Oletuksena tuotantoisännässä ei kuuntele mikään muu kuin Caddy:
graafitietokanta on yksityisessä compose-verkossa, ja vain palvelin puhuu
sille. Jotkin asiakkaat haluavat kysellä IFC-graafia suoraan Cypherillä
Boltin yli, kuten Dataspatiumin graafinäkymä tekee kehityspinoa vastaan. Tämä
sivu kertoo, miten järjestelmänvalvoja julkaisee portin tarkoituksella, mitä
se maksaa ja miten portti suljetaan taas. Vaihtoehto, joka pitää tietokannan
yksityisenä, on palvelimen vain luku -graafikysely järjestelmänvalvojille,
`POST /admin/api/graph/query` asetuksen `OPENCDE_GRAPH_QUERY_ENABLED` takana
([client-guide.md §7](../../client-guide.md)); julkaise portti vain, kun
asiakas tarvitsee nimenomaan Boltia.

## Mitä avoin portti tarkoittaa

- **Täydet oikeudet.** Neo4j:n ja Memgraphin community-versioissa ei ole vain
  luku -tietokantakäyttäjiä: tietokantakäyttäjän ja salasanan haltija voi
  lukea ja kirjoittaa kaiken, myös käyttäjät, tokenit ja tapahtumalokin. Anna
  salasana vain henkilöille, joista tekisit järjestelmänvalvojia.
- **Aina salattu.** Kerros ottaa TLS:n käyttöön Boltille (`bolt+s://`), ja
  palvelin kieltäytyy ilmoittamasta salaamatonta `bolt://`-osoitetta
  tuotannossa. Selainasiakkaat, kuten Dataspatium, tarvitsevat varmenteen,
  johon selain luottaa, joten itse allekirjoitetut varmenteet eivät toimi
  niille.
- **Ilmoitettu asiakkaille.** `OPENCDE_GRAPH_PUBLIC_BOLT_URL` julkaistaan
  kyvykkyysasiakirjassa (`/.well-known/kontroll`, `extensions.ifcgraph.bolt`),
  josta Dataspatium lukee sen, ja näytetään hallinnan Asetukset-sivulla. Jätä
  se tyhjäksi, kun portti on suljettu.

## 1. Varmenne Bolt-portille

Bolt tarvitsee varmenteen isäntänimelle, jota asiakkaat käyttävät,
PEM-muodossa: `certs/bolt/public.crt` (varmenne ketjuineen) ja
`certs/bolt/private.key`. Kontti lukee ne käyttäjänä `7474`, joten niiden on
oltava kaikkien luettavissa (`chmod 644`), minkä vuoksi ne ovat omassa
hakemistossaan.

Tuotantokerroksen kanssa Caddylla on jo Let's Encrypt -varmenne
`OPENCDE_DOMAIN`-nimelle. Kopioi se ulos (polut ovat Caddyn rakenteen
mukaiset):

```sh
D=cde.example.org
mkdir -p certs/bolt
docker compose -f compose.yaml -f compose.prod.yaml cp \
  "proxy:/data/caddy/certificates/acme-v02.api.letsencrypt.org-directory/$D/$D.crt" certs/bolt/public.crt
docker compose -f compose.yaml -f compose.prod.yaml cp \
  "proxy:/data/caddy/certificates/acme-v02.api.letsencrypt.org-directory/$D/$D.key" certs/bolt/private.key
chmod 644 certs/bolt/public.crt certs/bolt/private.key
```

Let's Encrypt -varmenteet ovat voimassa 90 päivää, ja Caddy uusii ne noin 60
päivän jälkeen. Toista kopiointi (cron-työ tai systemd-ajastin kerran kuussa)
ja käynnistä `graph`-palvelu uudelleen; Neo4j lukee tiedostot
käynnistyksessä.

## 2. Ilmoita osoite ja käynnistä

`.env`-tiedostoon:

```sh
OPENCDE_GRAPH_PUBLIC_BOLT_URL=bolt+s://cde.example.org:7687
# OPENCDE_BOLT_PORT=7687          # isännän portti, jos 7687 on varattu
```

Käynnistä sitten tavallinen komentosi kerroksella täydennettynä:

```sh
docker compose -f compose.yaml -f compose.prod.yaml -f compose.bolt.yaml up -d
```

Avaa palomuuri portille vain niille osoitteille, jotka sitä tarvitsevat
(toimiston verkko, VPN), ei koskaan koko maailmalle. Tarkista tulos:

```sh
curl -s https://cde.example.org/.well-known/kontroll | grep -o '"bolt":"[^"]*"'
```

Dataspatiumin graafinäkymä, Neo4j Browser (`bolt+s://cde.example.org:7687`)
ja viralliset ajurit yhdistävät tietokantakäyttäjällä ja salasanalla.

## 3. Sulje se taas

Poista `compose.bolt.yaml` komentoriviltä, tyhjennä
`OPENCDE_GRAPH_PUBLIC_BOLT_URL` `.env`-tiedostosta ja aja `up -d` uudelleen.
Portti katoaa isännästä, ja `bolt` palaa arvoon `null` kyvykkyysasiakirjassa.
Kierrätä tietokannan salasana jälkeenpäin, jos se jaettiin laajemmalle kuin
oli tarkoitus (`docs/security/controls.md`).

## Memgraph

`compose.memgraph.yaml`-tiedoston kanssa sama kerros julkaisee portin, mutta
edellä olevat TLS-asetukset ovat Neo4j:n. Lisää sen sijaan Memgraphin liput
sen `command`-kohtaan (`--bolt-cert-file=/certs/bolt/public.crt
--bolt-key-file=/certs/bolt/private.key`) ja liitä sama hakemisto; Memgraph
puhuu silloin Boltia TLS:n yli samassa portissa.
