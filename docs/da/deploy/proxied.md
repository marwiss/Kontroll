# Ved siden af det, der allerede kører på en server (nginx)

En server, der allerede har en omvendt proxy, som nginx med Let's
Encrypt-certifikater til andre websteder, og egne containere, beholder det
hele. Dataregium kører som sit eget Compose-projekt, med eget netværk og egne
volumener, og udgiver én port, kun på `127.0.0.1`; proxyen der får ét nyt
websted til Dataregiums navn. [docker/compose.proxied.yaml](../../../docker/compose.proxied.yaml)
er produktionsoverlejringen uden sin Caddy.

Det, der lades i fred: portene 80 og 443, proxyens andre websteder og
certifikater, og hver container, hvert netværk og hvert volumen, der er der.
Det, der lægges til: mappen `/opt/dataregium`, Compose-projektet `dataregium`
(API'et, Neo4j og den natlige sikkerhedskopi), porten `127.0.0.1:8010`, ét
nginx-websted og ét certifikat til det nye navn.

## 1. Kontrollér

```sh
ss -ltn | grep -q ':8010 ' && echo "8010 is taken: choose another OPENCDE_PROXIED_PORT"
free -h            # 2 GB free or more
docker compose version
```

Et DNS-navn til serveren, her `cde.example.org`, peger på maskinen.

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

## 3. Det nye websted i nginx

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

`certbot --nginx` tilføjer certifikatet og HTTPS-serveren til dette websted
alene. Den sidste kommando udskriver den første administrators adgangskode én
gang; log ind på `https://cde.example.org/signin`. Serveren stoler på de
videresendte headere fra Docker-netværkene (`OPENCDE_TRUSTED_PROXIES` i
`.env`); bruger Docker på maskinen andre adresseområder, så tilføj dem der.
Når nginx selv kører i en container, så sæt `OPENCDE_PROXIED_ADDRESS` til
Docker-broens adresse (ofte `172.17.0.1`) og brug den i `proxy_pass`.

## Fjern det igen

```sh
cd /opt/dataregium && sudo docker compose down -v
sudo rm /etc/nginx/sites-enabled/dataregium /etc/nginx/sites-available/dataregium
sudo nginx -t && sudo systemctl reload nginx
sudo certbot delete --cert-name cde.example.org
sudo rm -rf /opt/dataregium
```

`down -v` sletter Dataregiums database, dokumenter og sikkerhedskopier; kopiér
en sikkerhedskopi væk fra maskinen først, hvis de skal gemmes (se
[sikkerhedskopiering og gendannelse](backup.md)).
