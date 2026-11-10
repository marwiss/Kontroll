# Palvelimella jo toimivan rinnalla (nginx)

Palvelin, jolla on jo käänteinen välityspalvelin, kuten nginx Let's Encrypt
-varmenteineen muille sivustoille, ja omia kontteja, säilyttää ne kaikki.
Dataregium toimii omana Compose-projektinaan omine verkkoineen ja taltioineen
ja julkaisee yhden portin vain osoitteessa `127.0.0.1`; välityspalvelin saa
yhden uuden sivuston Dataregiumin nimelle. [docker/compose.proxied.yaml](../../../docker/compose.proxied.yaml)
on tuotantokerros ilman Caddya.

Mihin ei kosketa: portit 80 ja 443, välityspalvelimen muut sivustot ja
varmenteet sekä jokainen siellä oleva kontti, verkko ja taltio. Mitä lisätään:
hakemisto `/opt/dataregium`, Compose-projekti `dataregium` (rajapinta, Neo4j ja
yöllinen varmuuskopio), portti `127.0.0.1:8010`, yksi nginx-sivusto ja yksi
varmenne uudelle nimelle.

## 1. Tarkista

```sh
ss -ltn | grep -q ':8010 ' && echo "8010 is taken: choose another OPENCDE_PROXIED_PORT"
free -h            # 2 GB free or more
docker compose version
```

Palvelimen DNS-nimi, tässä `cde.example.org`, osoittaa koneeseen.

## 2. Käynnistä Dataregium

```sh
sudo git clone --depth 1 --branch v3.0.0 https://github.com/marwiss/Dataregium.git /opt/dataregium
cd /opt/dataregium
sudo docker run --rm --user 0:0 -v /opt/dataregium:/work -w /work ghcr.io/marwiss/opencdeserver:3.0.0 \
  init --public-url https://cde.example.org --path /work/.env
sudo sed -i 's#^COMPOSE_FILE=.*#COMPOSE_FILE=docker/compose.yaml:docker/compose.prod.yaml:docker/compose.proxied.yaml#' .env
echo "COMPOSE_PROJECT_NAME=dataregium" | sudo tee -a .env
echo "OPENCDE_PROXIED_PORT=8010" | sudo tee -a .env
sudo chmod 600 .env
sudo docker compose up -d --wait
curl -s http://127.0.0.1:8010/readyz
```

## 3. Uusi sivusto nginxissä

```nginx
# /etc/nginx/sites-available/dataregium
server {
    listen 80;
    server_name cde.example.org;

    client_max_body_size 1100m;
    proxy_request_buffering off;
    proxy_read_timeout 600s;
    proxy_send_timeout 600s;

    location / {
        proxy_pass http://127.0.0.1:8010;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $host;
    }
}
```

```sh
sudo ln -s /etc/nginx/sites-available/dataregium /etc/nginx/sites-enabled/dataregium
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d cde.example.org
sudo docker compose exec api opencde user create admin --admin
```

`certbot --nginx` lisää varmenteen ja HTTPS-palvelimen vain tälle sivustolle.
Viimeinen komento tulostaa ensimmäisen ylläpitäjän salasanan kerran; kirjaudu
osoitteessa `https://cde.example.org/signin`. Palvelin luottaa Docker-verkoista
välitettyihin otsakkeisiin (`OPENCDE_TRUSTED_PROXIES` tiedostossa `.env`); jos
koneen Docker käyttää muita osoitealueita, lisää ne sinne. Kun nginx itse
toimii kontissa, aseta `OPENCDE_PROXIED_ADDRESS` Docker-sillan osoitteeksi
(usein `172.17.0.1`) ja käytä sitä kohdassa `proxy_pass`.

## Poistaminen

```sh
cd /opt/dataregium && sudo docker compose down -v
sudo rm /etc/nginx/sites-enabled/dataregium /etc/nginx/sites-available/dataregium
sudo nginx -t && sudo systemctl reload nginx
sudo certbot delete --cert-name cde.example.org
sudo rm -rf /opt/dataregium
```

`down -v` poistaa Dataregiumin tietokannan, dokumentit ja varmuuskopiot;
kopioi varmuuskopio ensin pois koneelta, jos ne halutaan säilyttää (katso
[varmuuskopiointi ja palautus](backup.md)).
