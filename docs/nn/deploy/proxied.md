# Ved sida av det som alt køyrer på ein server (nginx)

Ein server som alt har ein omvend proxy, som nginx med Let's
Encrypt-sertifikat for andre nettstader, og eigne containerar, held på alt
det. Dataregium køyrer som sitt eige Compose-prosjekt, med eige nettverk og
eigne volum, og publiserer éin port, berre på `127.0.0.1`; proxyen der får éin
ny nettstad for namnet til Dataregium. [docker/compose.proxied.yaml](../../../docker/compose.proxied.yaml)
er produksjonsoverlegget utan Caddy.

Det som får vere i fred: portane 80 og 443, dei andre nettstadene og
sertifikata til proxyen, og kvar container, kvart nettverk og kvart volum som
er der. Det som blir lagt til: mappa `/opt/dataregium`, Compose-prosjektet
`dataregium` (API-et, Neo4j og den nattlege tryggingskopien), porten
`127.0.0.1:8010`, éin nginx-nettstad og eitt sertifikat for det nye namnet.

## 1. Kontroller

```sh
ss -ltn | grep -q ':8010 ' && echo "8010 is taken: choose another OPENCDE_PROXIED_PORT"
free -h            # 2 GB free or more
docker compose version
```

Eit DNS-namn for serveren, her `cde.example.org`, peikar på maskina.

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

## 3. Den nye nettstaden i nginx

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

`certbot --nginx` legg til sertifikatet og HTTPS-serveren for denne nettstaden
åleine. Den siste kommandoen skriv ut passordet til den første
administratoren éin gong; logg inn på `https://cde.example.org/signin`.
Serveren stolar på dei vidaresende hovuda frå Docker-nettverka
(`OPENCDE_TRUSTED_PROXIES` i `.env`); brukar Docker på maskina andre
adresseområde, legg dei til der. Når nginx sjølv køyrer i ein container, set
`OPENCDE_PROXIED_ADDRESS` til adressa til Docker-brua (ofte `172.17.0.1`) og
bruk ho i `proxy_pass`.

## Fjerne det att

```sh
cd /opt/dataregium && sudo docker compose down -v
sudo rm /etc/nginx/sites-enabled/dataregium /etc/nginx/sites-available/dataregium
sudo nginx -t && sudo systemctl reload nginx
sudo certbot delete --cert-name cde.example.org
sudo rm -rf /opt/dataregium
```

`down -v` slettar databasen, dokumenta og tryggingskopiane til Dataregium;
kopier ein tryggingskopi bort frå maskina først om dei skal takast vare på
(sjå [tryggingskopiering og gjenoppretting](backup.md)).
