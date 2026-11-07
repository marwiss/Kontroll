# Produksjon på eigen server (Docker Compose + Caddy)

Éin Linux-blir (2 vCPU og 4 GB RAM er rikeleg til å byrje med), Docker med
compose-tillegget, eit DNS-namn som peikar på han, portane 80 og 443 opne.
Caddy hentar og fornyar TLS-sertifikatet; API-et, databasen og
tryggingskopieringsjobben køyrer på eit privat nettverk.

## 1. Førebu

```sh
git clone https://github.com/marwiss/Kontroll.git /opt/kontroll
cd /opt/kontroll
uv run opencde init --public-url https://cde.example.org
```

Utan `--public-url` spør `opencde init` etter verdiane og skriv deretter ut kommandoane som kjem etterpå, òg for administratoren og den første klienten.

`init` skriv `.env` med `OPENCDE_ENVIRONMENT=production`, ein løynd nøkkel,
eit databasepassord og `OPENCDE_DOMAIN`. Legg til
`OPENCDE_ACME_EMAIL=deg@example.org` slik at Let's Encrypt kan nå deg om
sertifikata. Hald `.env` privat (han er git-ignorert); det er den einaste fila
med løyndomar.

Utan uv på serveren: kopier `.env.example` til `.env` og fyll inn verdiane for
hand (`python3 -c "import secrets; print(secrets.token_urlsafe(48))"` for den
løynde nøkkelen).

## 2. Start

```sh
docker compose -f compose.yaml -f compose.prod.yaml pull
docker compose -f compose.yaml -f compose.prod.yaml up -d
docker compose -f compose.yaml -f compose.prod.yaml exec api opencde doctor
docker compose -f compose.yaml -f compose.prod.yaml exec api opencde user create admin --admin
```

Den siste kommandoen skriv ut passordet til administratoren éin gong. Logg inn
på `https://cde.example.org/signin`, opne `/admin`, og opprett prosjekta,
brukarane og OAuth2-klientane programma dine treng.

## 3. Drift

| Oppgåve | Kommando |
|---|---|
| Oppdater til nyaste image | `docker compose -f compose.yaml -f compose.prod.yaml pull && docker compose -f compose.yaml -f compose.prod.yaml up -d` |
| Lås ein versjon | `OPENCDE_IMAGE_TAG=2.0.1` i `.env` (taggane følgjer GitHub-utgåvene) |
| Loggar | `docker compose -f compose.yaml -f compose.prod.yaml logs -f api` (JSON-linjer) |
| Helse | `https://cde.example.org/readyz`; sida Innstillingar i administrasjonen |
| Tryggingskopiar | kvar natt til volumet `backups` av tenesta `backup`; sjå [backup.md](backup.md) |
| Trekk tilbake tilgang ved ei hending | `docker compose ... exec api opencde revoke --all` (eller `--user`, `--client`) |

## 4. Sjekkliste for herding

- Databasen blir ikkje publisert; berre Caddy lyttar på verten. Å publisere
  Bolt-porten for grafklientar er eit medvite steg med eige overlegg og TLS,
  sjå [bolt.md](bolt.md); ein open port gjev full databasetilgang til den som
  har passordet.
- API-containeren er skriveverna, køyrer utan root og utan capabilities;
  lagringa er eit namngjeve volum.
- `OPENCDE_TRUSTED_PROXIES` dekkjer compose-nettverket slik at klientadressa i
  revisjonsloggen er den verkelege; lat han stå med mindre du endrar
  nettverket.
- Administrasjonen kan haldast til interne adresser. Legg dette til i nettstadblokka i `Caddyfile`, og tilpass adressene; `/admin/api` følgjer med, så administrasjonen i Dataspatium verkar berre frå dei adressene:

  ```caddyfile
  @admin_outside {
  	path /admin /admin/*
  	not remote_ip 10.0.0.0/8 192.168.0.0/16
  }
  respond @admin_outside 404
  ```

- API-et tillèt 600 førespurnader i minuttet per adresse. Alle bak same adresse deler dei, så hev grensa for eit stort kontor, til dømes `OPENCDE_RATE_LIMIT_API=3000/minute`. Det same gjeld dei 10 innloggingsforsøka i minuttet, `OPENCDE_RATE_LIMIT_SIGN_IN=60/minute`; ventetida per brukarnamn stoppar gjetting uansett.
- Hald på `OPENCDE_DYNAMIC_CLIENT_REGISTRATION=false` med mindre du treng
  sjølvbetent klientregistrering (Foundation API 2.2.3); registrer klientar i
  `/admin`.
- Roter den løynde nøkkelen og databasepassordet etter din policy
  (`docs/nn/security/controls.md`), start på nytt og logg inn igjen.
- Køyr `testssl.sh https://cde.example.org` og sjekk
  <https://observatory.mozilla.org> etter første start.
- Brannmur: tillat berre 22 (frå adressene dine), 80 og 443.
