# Produksjon på egen server (Docker Compose + Caddy)

Én Linux-vert (2 vCPU og 4 GB RAM er rikelig til å begynne med), Docker med
compose-tillegget, et DNS-navn som peker på den, portene 80 og 443 åpne. Caddy
henter og fornyer TLS-sertifikatet; API-et, databasen og
sikkerhetskopieringsjobben kjører på et privat nettverk.

## 1. Forbered

```sh
git clone https://github.com/marwiss/Kontroll.git /opt/kontroll
cd /opt/kontroll
uv run opencde init --public-url https://cde.example.org
```

`init` skriver `.env` med `OPENCDE_ENVIRONMENT=production`, en hemmelig nøkkel,
et databasepassord og `OPENCDE_DOMAIN`. Legg til
`OPENCDE_ACME_EMAIL=deg@example.org` slik at Let's Encrypt kan nå deg om
sertifikatene. Hold `.env` privat (den er git-ignorert); det er den eneste
filen med hemmeligheter.

Uten uv på serveren: kopier `.env.example` til `.env` og fyll inn verdiene for
hånd (`python3 -c "import secrets; print(secrets.token_urlsafe(48))"` for den
hemmelige nøkkelen).

## 2. Start

```sh
docker compose -f compose.yaml -f compose.prod.yaml pull
docker compose -f compose.yaml -f compose.prod.yaml up -d
docker compose -f compose.yaml -f compose.prod.yaml exec api opencde doctor
docker compose -f compose.yaml -f compose.prod.yaml exec api opencde user create admin --admin
```

Den siste kommandoen skriver ut administratorens passord én gang. Logg inn på
`https://cde.example.org/signin`, åpne `/admin`, og opprett prosjektene,
brukerne og OAuth2-klientene programmene dine trenger.

## 3. Drift

| Oppgave | Kommando |
|---|---|
| Oppdater til nyeste image | `docker compose -f compose.yaml -f compose.prod.yaml pull && docker compose -f compose.yaml -f compose.prod.yaml up -d` |
| Lås en versjon | `OPENCDE_IMAGE_TAG=2.2.0` i `.env` (taggene følger GitHub-utgivelsene) |
| Logger | `docker compose -f compose.yaml -f compose.prod.yaml logs -f api` (JSON-linjer) |
| Helse | `https://cde.example.org/readyz`; siden Innstillinger i administrasjonen |
| Sikkerhetskopier | hver natt til volumet `backups` av tjenesten `backup`; se [backup.md](backup.md) |
| Trekk tilbake tilgang ved en hendelse | `docker compose ... exec api opencde revoke --all` (eller `--user`, `--client`) |

## 4. Sjekkliste for herding

- Databasen publiseres ikke; bare Caddy lytter på verten. Å publisere
  Bolt-porten for grafklienter er et bevisst skritt med eget overlegg og TLS,
  se [bolt.md](bolt.md); en åpen port gir full databasetilgang til den som har
  passordet.
- API-containeren er skrivebeskyttet, kjører uten root og uten capabilities;
  lagringen er et navngitt volum.
- `OPENCDE_TRUSTED_PROXIES` dekker compose-nettverket slik at klientadressen i
  revisjonsloggen er den virkelige; la den stå med mindre du endrer nettverket.
- Behold `OPENCDE_DYNAMIC_CLIENT_REGISTRATION=false` med mindre du trenger
  selvbetjent klientregistrering (Foundation API 2.2.3); registrer klienter i
  `/admin`.
- Roter den hemmelige nøkkelen og databasepassordet etter din policy
  (`docs/nb/security/controls.md`), start på nytt og logg inn igjen.
- Kjør `testssl.sh https://cde.example.org` og sjekk
  <https://observatory.mozilla.org> etter første start.
- Brannmur: tillat bare 22 (fra dine adresser), 80 og 443.
