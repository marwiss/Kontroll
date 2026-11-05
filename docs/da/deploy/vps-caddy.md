# Produktion på egen server (Docker Compose + Caddy)

En Linux-vært (2 vCPU og 4 GB RAM er rigeligt til at begynde med), Docker med
compose-pluginet, et DNS-navn, der peger på den, portene 80 og 443 åbne. Caddy
henter og fornyer TLS-certifikatet; API'et, databasen og
sikkerhedskopieringsjobbet kører på et privat netværk.

## 1. Forbered

```sh
git clone https://github.com/marwiss/Kontroll.git /opt/kontroll
cd /opt/kontroll
uv run opencde init --public-url https://cde.example.org
```

`init` skriver `.env` med `OPENCDE_ENVIRONMENT=production`, en hemmelig nøgle,
et databasekodeord og `OPENCDE_DOMAIN`. Tilføj
`OPENCDE_ACME_EMAIL=dig@example.org`, så Let's Encrypt kan kontakte dig om
certifikaterne. Hold `.env` privat (den er git-ignoreret); det er den eneste
fil med hemmeligheder.

Uden uv på serveren: kopiér `.env.example` til `.env`, og udfyld værdierne i
hånden (`python3 -c "import secrets; print(secrets.token_urlsafe(48))"` til
den hemmelige nøgle).

## 2. Start

```sh
docker compose -f compose.yaml -f compose.prod.yaml pull
docker compose -f compose.yaml -f compose.prod.yaml up -d
docker compose -f compose.yaml -f compose.prod.yaml exec api opencde doctor
docker compose -f compose.yaml -f compose.prod.yaml exec api opencde user create admin --admin
```

Den sidste kommando udskriver administratorens kodeord én gang. Log ind på
`https://cde.example.org/signin`, åbn `/admin`, og opret de projekter, brugere
og OAuth2-klienter, dine programmer har brug for.

## 3. Drift

| Opgave | Kommando |
|---|---|
| Opdatér til det nyeste image | `docker compose -f compose.yaml -f compose.prod.yaml pull && docker compose -f compose.yaml -f compose.prod.yaml up -d` |
| Fastlås en version | `OPENCDE_IMAGE_TAG=2.2.0` i `.env` (tags følger GitHub-udgivelserne) |
| Logs | `docker compose -f compose.yaml -f compose.prod.yaml logs -f api` (JSON-linjer) |
| Helbred | `https://cde.example.org/readyz`; siden Indstillinger i administrationen |
| Sikkerhedskopier | hver nat til volumen `backups` af tjenesten `backup`; se [backup.md](backup.md) |
| Tilbagekald adgang ved en hændelse | `docker compose ... exec api opencde revoke --all` (eller `--user`, `--client`) |

## 4. Tjekliste for hærdning

- Databasen udgives ikke; kun Caddy lytter på værten. At udgive Bolt-porten
  til grafklienter er et bevidst skridt med sin egen overlejring og TLS, se
  [bolt.md](bolt.md); en åben port giver fuld databaseadgang til den, der har
  kodeordet.
- API-containeren er skrivebeskyttet, kører uden root og uden capabilities;
  lageret er en navngivet volume.
- `OPENCDE_TRUSTED_PROXIES` dækker compose-netværket, så klientadressen i
  revisionsloggen er den rigtige; lad den være, medmindre du ændrer netværket.
- Behold `OPENCDE_DYNAMIC_CLIENT_REGISTRATION=false`, medmindre du har brug for
  selvbetjent klientregistrering (Foundation API 2.2.3); registrér klienter i
  `/admin`.
- Rotér den hemmelige nøgle og databasekodeordet efter din politik
  (`docs/da/security/controls.md`), genstart, og log ind igen.
- Kør `testssl.sh https://cde.example.org`, og tjek
  <https://observatory.mozilla.org> efter den første start.
- Firewall: tillad kun 22 (fra dine adresser), 80 og 443.
