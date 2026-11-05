# Sjølvhosta plattformer (Coolify, Dokploy, Portainer)

Desse plattformene les ei compose-fil, gjev henne eit domene med automatisk
TLS og tilbyr eit webgrensesnitt for loggar, omstartar og oppdateringar. Dei
er ein behageleg måte å køyre serveren på når du alt bruker ei av dei.

## Compose-fil

Bruk `compose.yaml` saman med `compose.prod.yaml` **utan tenesta `proxy`**:
plattforma sin eigen proxy (Traefik i Coolify og Dokploy) terminerer TLS. Det
enklaste er ei lita overstyringsfil ved sida av dei:

```yaml
# compose.paas.yaml
services:
  proxy:
    profiles: ["disabled"]
  api:
    labels:
      # Dokploy / Coolify les desse for å rute domenet til containeren.
      traefik.enable: "true"
      traefik.http.services.opencde.loadbalancer.server.port: "8000"
```

og distribuer `compose.yaml compose.prod.yaml compose.paas.yaml` som éin stakk.

## Miljø

Set variablane frå `.env.example` i miljøredigeringa til plattforma. Minimum
for produksjon:

```
OPENCDE_ENVIRONMENT=production
OPENCDE_PUBLIC_URL=https://cde.example.org
OPENCDE_SECRET_KEY=<48 tilfeldige teikn>
OPENCDE_GRAPH_PASSWORD=<24 tilfeldige teikn>
OPENCDE_TRUSTED_PROXIES=["172.16.0.0/12", "10.0.0.0/8", "192.168.0.0/16"]
```

`OPENCDE_DOMAIN` trengst berre av Caddy og kan sløyfast.

## Merknader

- Hald sjølve plattforma oppdatert: Coolify publiserte til dømes rettingar for
  alvorlege sårbarheiter i januar 2026. Administrasjonsgrensesnittet til
  plattforma bør ikkje kunne nåast frå det opne internettet.
- Databasevolumet og lagringsvolumet er dataa; ta dei med i
  tryggingskopieringa til plattforma, og hald òg på volumet til den nattlege
  tenesta `backup`.
- Første administrator: opne ein konsoll på tenesta `api` og køyr
  `opencde user create admin --admin`.
