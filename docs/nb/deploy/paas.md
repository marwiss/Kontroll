# Selvhostede plattformer (Coolify, Dokploy, Portainer)

Disse plattformene leser en compose-fil, gir den et domene med automatisk TLS
og tilbyr et webgrensesnitt for logger, omstarter og oppdateringer. De er en
behagelig måte å kjøre serveren på når du allerede bruker en av dem.

## Compose-fil

Bruk `compose.yaml` sammen med `compose.prod.yaml` **uten tjenesten `proxy`**:
plattformens egen proxy (Traefik i Coolify og Dokploy) terminerer TLS. Det
enkleste er en liten overstyringsfil ved siden av dem:

```yaml
# compose.paas.yaml
services:
  proxy:
    profiles: ["disabled"]
  api:
    labels:
      # Dokploy / Coolify leser disse for å rute domenet til containeren.
      traefik.enable: "true"
      traefik.http.services.opencde.loadbalancer.server.port: "8000"
```

og distribuer `compose.yaml compose.prod.yaml compose.paas.yaml` som én stakk.

## Miljø

Sett variablene fra `.env.example` i plattformens miljøredigering. Minimum for
produksjon:

```
OPENCDE_ENVIRONMENT=production
OPENCDE_PUBLIC_URL=https://cde.example.org
OPENCDE_SECRET_KEY=<48 tilfeldige tegn>
OPENCDE_GRAPH_PASSWORD=<24 tilfeldige tegn>
OPENCDE_TRUSTED_PROXIES=["172.16.0.0/12", "10.0.0.0/8", "192.168.0.0/16"]
```

`OPENCDE_DOMAIN` trengs bare av Caddy og kan utelates.

## Merknader

- Hold selve plattformen oppdatert: Coolify publiserte for eksempel rettelser
  for alvorlige sårbarheter i januar 2026. Plattformens
  administrasjonsgrensesnitt bør ikke kunne nås fra det åpne internettet.
- Databasevolumet og lagringsvolumet er dataene; ta dem med i plattformens
  sikkerhetskopiering, og behold også volumet til den nattlige tjenesten
  `backup`.
- Første administrator: åpne en konsoll på tjenesten `api` og kjør
  `opencde user create admin --admin`.
