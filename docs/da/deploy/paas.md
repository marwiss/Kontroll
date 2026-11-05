# Selvhostede platforme (Coolify, Dokploy, Portainer)

Disse platforme læser en compose-fil, giver den et domæne med automatisk TLS
og tilbyder en webgrænseflade til logs, genstarter og opdateringer. De er en
bekvem måde at køre serveren på, når du allerede bruger en af dem.

## Compose-fil

Brug `compose.yaml` sammen med `compose.prod.yaml` **uden tjenesten `proxy`**:
platformens egen proxy (Traefik i Coolify og Dokploy) terminerer TLS. Det
enkleste er en lille overstyringsfil ved siden af dem:

```yaml
# compose.paas.yaml
services:
  proxy:
    profiles: ["disabled"]
  api:
    labels:
      # Dokploy / Coolify læser disse for at dirigere domænet til containeren.
      traefik.enable: "true"
      traefik.http.services.opencde.loadbalancer.server.port: "8000"
```

og udrul `compose.yaml compose.prod.yaml compose.paas.yaml` som én stak.

## Miljø

Sæt variablerne fra `.env.example` i platformens miljøeditor. Minimum for
produktion:

```
OPENCDE_ENVIRONMENT=production
OPENCDE_PUBLIC_URL=https://cde.example.org
OPENCDE_SECRET_KEY=<48 tilfældige tegn>
OPENCDE_GRAPH_PASSWORD=<24 tilfældige tegn>
OPENCDE_TRUSTED_PROXIES=["172.16.0.0/12", "10.0.0.0/8", "192.168.0.0/16"]
```

`OPENCDE_DOMAIN` behøves kun af Caddy og kan udelades.

## Bemærkninger

- Hold selve platformen opdateret: Coolify udgav for eksempel rettelser til
  alvorlige sårbarheder i januar 2026. Platformens administrationsgrænseflade
  bør ikke kunne nås fra det åbne internet.
- Databasevolumen og lagervolumen er dataene; tag dem med i platformens
  sikkerhedskopiering, og behold også volumen for den natlige tjeneste
  `backup`.
- Første administrator: åbn en konsol på tjenesten `api`, og kør
  `opencde user create admin --admin`.
