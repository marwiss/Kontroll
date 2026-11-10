# Við hlið þess sem þegar keyrir á þjóni (nginx)

Þjónn sem hefur þegar öfugan milliþjón (reverse proxy), eins og nginx með
Let's Encrypt-skírteinum fyrir aðra vefi, og eigin gáma heldur því öllu.
Dataregium keyrir sem eigið Compose-verkefni, með eigið net og eigin geyma, og
birtir eina gátt, aðeins á `127.0.0.1`; milliþjónninn þar fær einn nýjan vef
fyrir nafn Dataregium. [docker/compose.proxied.yaml](../../../docker/compose.proxied.yaml)
er rekstrarlagið án Caddy.

Það sem er látið í friði: gáttir 80 og 443, aðrir vefir og skírteini
milliþjónsins, og hver gámur, net og geymir sem þar er. Það sem bætist við:
mappan `/opt/dataregium`, Compose-verkefnið `dataregium` (forritaskilin, Neo4j
og næturlega afritið), gáttin `127.0.0.1:8010`, einn nginx-vefur og eitt
skírteini fyrir nýja nafnið.

## 1. Athugaðu

```sh
ss -ltn | grep -q ':8010 ' && echo "8010 is taken: choose another OPENCDE_PROXIED_PORT"
free -h            # 2 GB free or more
docker compose version
```

DNS-nafn fyrir þjóninn, hér `cde.example.org`, vísar á vélina.

## 2. Ræstu Dataregium

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

## 3. Nýi vefurinn í nginx

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

`certbot --nginx` bætir skírteininu og HTTPS-þjóninum aðeins við þennan vef.
Síðasta skipunin prentar lykilorð fyrsta stjórnandans einu sinni; skráðu þig
inn á `https://cde.example.org/signin`. Þjónninn treystir áframsendum hausum
frá Docker-netunum (`OPENCDE_TRUSTED_PROXIES` í `.env`); ef Docker á vélinni
notar önnur vistfangasvið, bættu þeim við þar. Þegar nginx keyrir sjálft í
gámi, settu `OPENCDE_PROXIED_ADDRESS` á vistfang Docker-brúarinnar (oft
`172.17.0.1`) og notaðu það í `proxy_pass`.

## Að fjarlægja það aftur

```sh
cd /opt/dataregium && sudo docker compose down -v
sudo rm /etc/nginx/sites-enabled/dataregium /etc/nginx/sites-available/dataregium
sudo nginx -t && sudo systemctl reload nginx
sudo certbot delete --cert-name cde.example.org
sudo rm -rf /opt/dataregium
```

`down -v` eyðir gagnagrunni, skjölum og afritum Dataregium; afritaðu fyrst
afrit af vélinni ef á að halda þeim (sjá [afritun og endurheimt](backup.md)).
