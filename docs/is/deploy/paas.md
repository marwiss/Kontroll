# Sjálfhýstir vettvangar (Coolify, Dokploy, Portainer)

Þessir vettvangar lesa compose-skrá, gefa henni lén með sjálfvirku TLS og
bjóða vefviðmót fyrir atvikaskrár, endurræsingar og uppfærslur. Þeir eru
þægileg leið til að keyra þjóninn þegar þú notar einn þeirra þegar.

## Compose-skrá

Notaðu `docker/compose.yaml` saman með `docker/compose.prod.yaml` **án þjónustunnar
`proxy`**: eigin milliþjónn vettvangsins (Traefik í Coolify og Dokploy) lýkur
TLS. Einfaldast er lítil yfirskriftarskrá við hlið þeirra:

```yaml
# docker/compose.paas.yaml
services:
  proxy:
    profiles: ["disabled"]
  api:
    labels:
      # Dokploy / Coolify lesa þetta til að beina léninu á gáminn.
      traefik.enable: "true"
      traefik.http.services.opencde.loadbalancer.server.port: "8000"
```

og settu `docker/compose.yaml docker/compose.prod.yaml docker/compose.paas.yaml` upp sem einn
stafla.

## Umhverfi

Settu breyturnar úr `.env.example` í umhverfisritil vettvangsins. Lágmark
fyrir rekstur:

```
OPENCDE_ENVIRONMENT=production
OPENCDE_PUBLIC_URL=https://cde.example.org
OPENCDE_SECRET_KEY=<48 slembin tákn>
OPENCDE_GRAPH_PASSWORD=<24 slembin tákn>
OPENCDE_TRUSTED_PROXIES=["172.16.0.0/12", "10.0.0.0/8", "192.168.0.0/16"]
```

`OPENCDE_DOMAIN` þarf aðeins Caddy og má sleppa.

## Athugasemdir

- Haltu vettvanginum sjálfum uppfærðum: Coolify gaf til dæmis út lagfæringar
  á alvarlegum veikleikum í janúar 2026. Stjórnviðmót vettvangsins ætti ekki
  að vera aðgengilegt af opnu internetinu.
- Gagnagrunnsgeymslan og skráageymslan eru gögnin; hafðu þær með í
  öryggisafritun vettvangsins og haltu líka geymslu næturþjónustunnar
  `backup`.
- Fyrsti stjórnandi: opnaðu stjórnborð (console) á þjónustunni `api` og
  keyrðu `opencde user create admin --admin`.
