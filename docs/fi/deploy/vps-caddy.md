# Tuotanto omalla palvelimella (Docker Compose + Caddy)

Yksi Linux-isäntä (2 vCPU ja 4 Gt RAM riittää hyvin alkuun), Docker
compose-liitännäisellä, siihen osoittava DNS-nimi, portit 80 ja 443 auki.
Caddy hankkii ja uusii TLS-varmenteen; API, tietokanta ja
varmuuskopiointityö toimivat yksityisessä verkossa.

## 1. Valmistele

```sh
git clone https://github.com/marwiss/Kontroll.git /opt/kontroll
cd /opt/kontroll
uv run opencde init --public-url https://cde.example.org
```

Ilman asetusta `--public-url` `opencde init` kysyy arvot ja tulostaa sitten seuraavat komennot, myös ylläpitäjälle ja ensimmäiselle asiakkaalle.

`init` kirjoittaa `.env`-tiedoston, jossa on `OPENCDE_ENVIRONMENT=production`,
salainen avain, tietokannan salasana ja `OPENCDE_DOMAIN`. Lisää
`OPENCDE_ACME_EMAIL=you@example.org`, jotta Let's Encrypt voi tavoittaa
sinut varmenteista. Pidä `.env` yksityisenä (git ohittaa sen); se on ainoa
tiedosto, jossa on salaisuuksia.

Ilman uv:tä palvelimella: kopioi `.env.example` nimelle `.env` ja täytä arvot
käsin (salaiselle avaimelle
`python3 -c "import secrets; print(secrets.token_urlsafe(48))"`).

## 2. Käynnistä

```sh
docker compose -f compose.yaml -f compose.prod.yaml pull
docker compose -f compose.yaml -f compose.prod.yaml up -d
docker compose -f compose.yaml -f compose.prod.yaml exec api opencde doctor
docker compose -f compose.yaml -f compose.prod.yaml exec api opencde user create admin --admin
```

Viimeinen komento tulostaa järjestelmänvalvojan salasanan kerran. Kirjaudu
osoitteessa `https://cde.example.org/signin`, avaa `/admin` ja luo projektit,
käyttäjät ja OAuth2-asiakkaat, joita sovelluksesi tarvitsevat.

## 3. Käyttö

| Tehtävä | Komento |
|---|---|
| Päivitä uusimpaan imageen | `docker compose -f compose.yaml -f compose.prod.yaml pull && docker compose -f compose.yaml -f compose.prod.yaml up -d` |
| Kiinnitä versio | `OPENCDE_IMAGE_TAG=2.0.0` `.env`-tiedostossa (tagit seuraavat GitHub-julkaisuja) |
| Lokit | `docker compose -f compose.yaml -f compose.prod.yaml logs -f api` (JSON-rivejä) |
| Kuntotarkistus | `https://cde.example.org/readyz`; hallinnan Asetukset-sivu |
| Varmuuskopiot | joka yö `backups`-taltioon `backup`-palvelun toimesta; katso [backup.md](backup.md) |
| Peru käyttöoikeudet tietoturvapoikkeamassa | `docker compose ... exec api opencde revoke --all` (tai `--user`, `--client`) |

## 4. Kovennuksen tarkistuslista

- Tietokantaa ei julkaista; vain Caddy kuuntelee isännässä. Bolt-portin
  julkaiseminen graafiasiakkaille on tietoinen askel, jolla on oma kerroksensa
  ja TLS, katso [bolt.md](bolt.md); avoin portti antaa täydet
  tietokantaoikeudet salasanan haltijalle.
- API-kontti on vain luku -tilassa, ei aja roottina eikä
  capability-oikeuksilla; tallennustila on nimetty taltio.
- `OPENCDE_TRUSTED_PROXIES` kattaa compose-verkon, jotta tapahtumalokin
  asiakasosoite on oikea; jätä se ennalleen, ellet muuta verkkoa.
- Hallinnan voi rajata sisäisiin osoitteisiin. Lisää tämä `Caddyfile`-tiedoston sivustolohkoon ja mukauta osoitteet; `/admin/api` kuuluu mukaan, joten Dataspatiumin hallinta toimii vain niistä osoitteista:

  ```caddyfile
  @admin_outside {
  	path /admin /admin/*
  	not remote_ip 10.0.0.0/8 192.168.0.0/16
  }
  respond @admin_outside 404
  ```

- API sallii 600 pyyntöä minuutissa osoitetta kohden. Kaikki saman osoitteen takana jakavat ne, joten nosta rajaa suurelle toimistolle, esimerkiksi `OPENCDE_RATE_LIMIT_API=3000/minute`. Sama koskee 10 kirjautumisyritystä minuutissa, `OPENCDE_RATE_LIMIT_SIGN_IN=60/minute`; käyttäjänimikohtainen odotus pysäyttää arvailun joka tapauksessa.
- Pidä `OPENCDE_DYNAMIC_CLIENT_REGISTRATION=false`, ellet tarvitse
  itsepalveluna tapahtuvaa asiakasrekisteröintiä (Foundation API 2.2.3);
  rekisteröi asiakkaat `/admin`-sivulla.
- Kierrätä salainen avain ja tietokannan salasana käytäntösi mukaan
  (`docs/fi/security/controls.md`), käynnistä uudelleen ja kirjaudu taas.
- Aja `testssl.sh https://cde.example.org` ja tarkista
  <https://observatory.mozilla.org> ensimmäisen käynnistyksen jälkeen.
- Palomuuri: salli vain 22 (omista osoitteistasi), 80 ja 443.
