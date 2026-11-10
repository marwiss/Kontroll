# Beside what already runs on a server (nginx)

A server that already has a reverse proxy, such as nginx with Let's Encrypt
certificates for other sites, and containers of its own keeps all of it.
Dataregium runs as a Compose project of its own, with its own network and
volumes, and publishes one port on `127.0.0.1` only; the proxy there gets one
new site for Dataregium's name. [docker/compose.proxied.yaml](../../../docker/compose.proxied.yaml)
is the production overlay without its Caddy.

What it leaves alone: ports 80 and 443, the proxy's other sites and
certificates, and every container, network and volume that is there. What it
adds: the folder `/opt/dataregium`, the Compose project `dataregium` (the API,
Neo4j and the nightly backup), the port `127.0.0.1:8010`, one nginx site and
one certificate for the new name.

## 1. Check

```sh
ss -ltn | grep -q ':8010 ' && echo "8010 is taken: choose another OPENCDE_PROXIED_PORT"
free -h            # 2 GB free or more
docker compose version
```

A DNS name for the server, here `cde.example.org`, points at the machine.

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

## 3. The new site in nginx

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

`certbot --nginx` adds the certificate and the HTTPS server to this site only.
The last command prints the first administrator's password once; sign in at
`https://cde.example.org/signin`. The server trusts the forwarded headers from
the Docker networks (`OPENCDE_TRUSTED_PROXIES` in `.env`); if Docker on the
machine uses other address pools, add them there. When nginx itself runs in a
container, set `OPENCDE_PROXIED_ADDRESS` to the Docker bridge's address (often
`172.17.0.1`) and use it in `proxy_pass`.

## Removing it again

```sh
cd /opt/dataregium && sudo docker compose down -v
sudo rm /etc/nginx/sites-enabled/dataregium /etc/nginx/sites-available/dataregium
sudo nginx -t && sudo systemctl reload nginx
sudo certbot delete --cert-name cde.example.org
sudo rm -rf /opt/dataregium
```

`down -v` deletes Dataregium's database, documents and backups; copy a backup
off the machine first if they are to be kept (see [backup and restore](backup.md)).
