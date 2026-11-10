# Ved siden av det som allerede kjører på en server (nginx)

En server som allerede har en omvendt proxy, som nginx med Let's
Encrypt-sertifikater for andre nettsteder, og egne containere, beholder alt
det. Dataregium kjører som sitt eget Compose-prosjekt, med eget nettverk og
egne volumer, og publiserer én port, bare på `127.0.0.1`; proxyen der får ett
nytt nettsted for Dataregiums navn. [docker/compose.proxied.yaml](../../../docker/compose.proxied.yaml)
er produksjonsoverlegget uten sin Caddy.

Det som får være i fred: portene 80 og 443, proxyens andre nettsteder og
sertifikater, og hver container, hvert nettverk og hvert volum som er der. Det
som legges til: mappen `/opt/dataregium`, Compose-prosjektet `dataregium`
(API-et, Neo4j og den nattlige sikkerhetskopien), porten `127.0.0.1:8010`, ett
nginx-nettsted og ett sertifikat for det nye navnet.

## 1. Kontroller

```sh
ss -ltn | grep -q ':8010 ' && echo "8010 is taken: choose another OPENCDE_PROXIED_PORT"
free -h            # 2 GB free or more
docker compose version
```

Et DNS-navn for serveren, her `cde.example.org`, peker på maskinen.

## 2. Start Dataregium

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

## 3. Det nye nettstedet i nginx

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

`certbot --nginx` legger til sertifikatet og HTTPS-serveren for dette
nettstedet alene. Den siste kommandoen skriver ut passordet til den første
administratoren én gang; logg inn på `https://cde.example.org/signin`. Serveren
stoler på de videresendte hodene fra Docker-nettverkene
(`OPENCDE_TRUSTED_PROXIES` i `.env`); bruker Docker på maskinen andre
adresseområder, legg dem til der. Når nginx selv kjører i en container, sett
`OPENCDE_PROXIED_ADDRESS` til Docker-broens adresse (ofte `172.17.0.1`) og
bruk den i `proxy_pass`.

## Fjerne det igjen

```sh
cd /opt/dataregium && sudo docker compose down -v
sudo rm /etc/nginx/sites-enabled/dataregium /etc/nginx/sites-available/dataregium
sudo nginx -t && sudo systemctl reload nginx
sudo certbot delete --cert-name cde.example.org
sudo rm -rf /opt/dataregium
```

`down -v` sletter Dataregiums database, dokumenter og sikkerhetskopier; kopier
en sikkerhetskopi bort fra maskinen først hvis de skal tas vare på (se
[sikkerhetskopiering og gjenoppretting](backup.md)).
