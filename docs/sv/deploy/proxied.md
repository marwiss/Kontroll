# Bredvid det som redan körs på en server (nginx)

En server som redan har en omvänd proxy, som nginx med Let's Encrypt-certifikat
för andra webbplatser, och egna containrar behåller allt det. Dataregium körs
som ett eget Compose-projekt, med eget nätverk och egna volymer, och publicerar
en port, bara på `127.0.0.1`; proxyn där får en ny webbplats för Dataregiums
namn. [docker/compose.proxied.yaml](../../../docker/compose.proxied.yaml) är
produktionsöverlagringen utan sin Caddy.

Det som lämnas orört: portarna 80 och 443, proxyns andra webbplatser och
certifikat, och varje container, nätverk och volym som finns där. Det som
läggs till: mappen `/opt/dataregium`, Compose-projektet `dataregium` (API:t,
Neo4j och den nattliga säkerhetskopian), porten `127.0.0.1:8010`, en
nginx-webbplats och ett certifikat för det nya namnet.

## 1. Kontrollera

```sh
ss -ltn | grep -q ':8010 ' && echo "8010 is taken: choose another OPENCDE_PROXIED_PORT"
free -h            # 2 GB free or more
docker compose version
```

Ett DNS-namn för servern, här `cde.example.org`, pekar på maskinen.

## 2. Starta Dataregium

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

## 3. Den nya webbplatsen i nginx

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

`certbot --nginx` lägger till certifikatet och HTTPS-servern för den här
webbplatsen enbart. Det sista kommandot skriver ut första administratörens
lösenord en gång; logga in på `https://cde.example.org/signin`. Servern litar
på de vidarebefordrade huvudena från Docker-nätverken (`OPENCDE_TRUSTED_PROXIES`
i `.env`); använder Docker på maskinen andra adressområden, lägg till dem där.
När nginx själv körs i en container, sätt `OPENCDE_PROXIED_ADDRESS` till
Docker-bryggans adress (ofta `172.17.0.1`) och använd den i `proxy_pass`.

## Ta bort det igen

```sh
cd /opt/dataregium && sudo docker compose down -v
sudo rm /etc/nginx/sites-enabled/dataregium /etc/nginx/sites-available/dataregium
sudo nginx -t && sudo systemctl reload nginx
sudo certbot delete --cert-name cde.example.org
sudo rm -rf /opt/dataregium
```

`down -v` tar bort Dataregiums databas, dokument och säkerhetskopior; kopiera
en säkerhetskopia från maskinen först om de ska sparas (se
[säkerhetskopiering och återställning](backup.md)).
